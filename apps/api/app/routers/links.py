import hashlib
from fastapi import APIRouter, status, HTTPException
from app.schemas.link import LinkCreate
from app.database import db_breaker, db_insert_link, CircuitBreakerOpenException # type: ignore
from app.config import settings
import redis.asyncio as aioredis  # Native async Redis driver

router = APIRouter(prefix="/links", tags=["B2B Core Links Engine"])

# Initialize the actual network connection pool targeting the Redis container
redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_link(link_in: LinkCreate):
    # Generate deterministic 6-character unique identifier hash
    short_code = hashlib.md5(link_in.long_url.encode()).hexdigest()[:6]

    try:
        # --- TRUE REDIS CACHE-ASIDE PATTERN ---
        # Query the actual Redis container over the Docker bridge network
        cached_url = await redis_client.get(short_code)
        
        if cached_url:
            print("[REDIS CACHE HIT]: Returning verified resource mapping from network cache.")
            return {"status": "success", "code": short_code, "source": "cache"}

        print("[REDIS CACHE MISS]: Routing stream to relational database infrastructure...")
        
        # --- DATABASE INFRASTRUCTURE VIA CIRCUIT BREAKER ---
        # Wrap database interactions inside the circuit breaker pool context
        db_result = await db_breaker.call(db_insert_link, short_code, link_in.long_url)
        db_breaker.handle_success()
        
        # Write to the actual Redis container with a strict production TTL of 5 minutes
        await redis_client.set(short_code, link_in.long_url, ex=300)
        
        return {"status": "success", "code": short_code, "source": "database"}
        
    except CircuitBreakerOpenException:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database degraded. System shedding load gracefully to maintain SLA uptime."
        )
    except Exception as e:
        print(f"[SYSTEM SYSTEM ERROR]: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Downstream dependency communication failure."
        )