import hashlib
from fastapi import APIRouter, status, HTTPException
from fastapi.responses import RedirectResponse
from app.schemas.link import LinkCreate
from app.database import db_breaker, db_insert_link, db_get_long_url, CircuitBreakerOpenException
from app.config import settings
import redis.asyncio as aioredis

router = APIRouter(prefix="/links", tags=["B2B Core Links Engine"])

# Connect to the live network-isolated Redis container
redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_link(link_in: LinkCreate):
    # Generate deterministic 6-character code token
    short_code = hashlib.md5(link_in.long_url.encode()).hexdigest()[:6]

    try:
        # 1. Check Redis Network Cache
        cached_url = await redis_client.get(short_code)
        if cached_url:
            return {
                "status": "success", 
                "code": short_code, 
                "source": "cache", 
                "short_url": f"http://localhost:8000/links/{short_code}"
            }

        # 2. Fallback to Database wrapped inside Circuit Breaker
        await db_breaker.call(db_insert_link, short_code, link_in.long_url)
        db_breaker.handle_success()

        # 3. Populate Redis with a strict 5-minute production TTL
        await redis_client.set(short_code, link_in.long_url, ex=300)

        return {
            "status": "success", 
            "code": short_code, 
            "source": "database", 
            "short_url": f"http://localhost:8000/links/{short_code}"
        }

    except CircuitBreakerOpenException:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="Database degraded. Load shedding active."
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/{short_code}")
async def redirect_to_long_url(short_code: str):
    """Intercepts short codes and implements full Cache-Aside database fallback logic."""
    try:
        # STEP 1: Query the network cache for immediate redirection
        long_url = await redis_client.get(short_code)
        
        if long_url:
            print(f"[CACHE HIT]: Token '{short_code}' found in Redis memory.")
            return RedirectResponse(url=long_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
            
        # STEP 2: Cache Miss occurred. Fall back to PostgreSQL database via Circuit Breaker
        print(f"[CACHE MISS]: Token '{short_code}' not in Redis. Querying PostgreSQL...")
        db_url = await db_breaker.call(db_get_long_url, short_code)
        db_breaker.handle_success()
        
        if not db_url:
            # Token doesn't exist in the database either
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Requested short code route does not exist anywhere in the system."
            )
            
        # STEP 3: Cache Repair. Hydrate Redis so subsequent lookups are zero-latency
        print(f"[CACHE REPAIR]: Hydrating Redis with token '{short_code}' for 5 minutes.")
        await redis_client.set(short_code, db_url, ex=300)
        
        # STEP 4: Execute redirect
        return RedirectResponse(url=db_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
        
    except CircuitBreakerOpenException:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="Database connectivity degraded. Cache fallback failed."
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
