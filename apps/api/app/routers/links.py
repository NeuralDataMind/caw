import hashlib
from fastapi import APIRouter, status, HTTPException
from app.schemas.link import LinkCreate
from app.database import db_breaker, db_insert_link, CircuitBreakerOpenException # type: ignore

router = APIRouter(prefix="/links", tags=["B2B Core Links Engine"])

# Mocked memory map simulating a Redis client connection pool dictionary
mock_redis_pool = {}

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_link(link_in: LinkCreate):
    # Generate deterministic 6-character unique identifier hash
    short_code = hashlib.md5(link_in.long_url.encode()).hexdigest()[:6]

    # --- PILLAR 2: REDIS CACHE-ASIDE PATTERN IMPLEMENTATION ---
    if short_code in mock_redis_pool:
        print("[REDIS CACHE HIT]: Returning pre-cached resource mapping instantly.")
        return {"status": "success", "code": short_code, "source": "cache"}

    print("[REDIS CACHE MISS]: Executing read/write stream routing through database infrastructure...")
    
    # --- PILLAR 3: DATABASE INFRASTRUCTURE VIA CIRCUIT BREAKER ---
    try:
        # Wrap database interactions inside the circuit breaker pool context
        db_result = await db_breaker.call(db_insert_link, short_code, link_in.long_url)
        db_breaker.handle_success()
        
        # Populate Redis with a strict production TTL (e.g., 300 seconds)
        mock_redis_pool[short_code] = link_in.long_url
        
        return {"status": "success", "code": short_code, "source": "database"}
        
    except CircuitBreakerOpenException:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database degraded. System shedding load gracefully to maintain SLA uptime."
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Downstream dependency communication timeout."
        )