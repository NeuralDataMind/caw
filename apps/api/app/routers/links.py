import hashlib
from urllib.parse import urlparse
from fastapi import APIRouter, status, HTTPException
from fastapi.responses import RedirectResponse
from app.schemas.link import LinkCreate
from app.database import (
    db_breaker, 
    db_insert_link, 
    db_get_long_url, 
    db_is_domain_whitelisted, 
    db_add_whitelisted_domain,
    CircuitBreakerOpenException
)
from app.config import settings
import redis.asyncio as aioredis

router = APIRouter(prefix="/links", tags=["B2B Core Links Engine"])
redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

@router.post("/domains", status_code=status.HTTP_201_CREATED)
async def add_custom_domain(domain: str):
    """Admin gateway to register new corporate client domains dynamically into the database."""
    clean_domain = domain.strip().lower()
    if not clean_domain:
        raise HTTPException(status_code=400, detail="Domain value cannot be blank.")
    
    await db_add_whitelisted_domain(clean_domain)
    # Clear or sync to Redis memory would happen here in production
    return {"status": "success", "message": f"Domain '{clean_domain}' whitelisted successfully."}

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_link(link_in: LinkCreate):
    # 1. Isolate and parse the incoming hostname string asynchronously
    try:
        parsed_url = urlparse(link_in.long_url)
        hostname = parsed_url.hostname
        if not hostname or not parsed_url.scheme:
            raise ValueError()
        hostname = hostname.lower()
        if hostname.startswith("www."):
            hostname = hostname[4:]
    except Exception:
        raise HTTPException(status_code=422, detail="Malformed payload: Invalid URL structural geometry.")

    # 2. Query the storage layer dynamically for domain access authorization
    is_allowed = await db_is_domain_whitelisted(hostname)
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Domain access violation: target host '{hostname}' is not whitelisted in the database."
        )

    # 3. Proceed with deterministic link generation and cache execution
    short_code = hashlib.md5(link_in.long_url.encode()).hexdigest()[:6]

    try:
        cached_url = await redis_client.get(short_code)
        if cached_url:
            return {"status": "success", "code": short_code, "source": "cache", "short_url": f"http://localhost:8000/links/{short_code}"}

        await db_breaker.call(db_insert_link, short_code, link_in.long_url)
        db_breaker.handle_success()
        await redis_client.set(short_code, link_in.long_url, ex=300)

        return {"status": "success", "code": short_code, "source": "database", "short_url": f"http://localhost:8000/links/{short_code}"}

    except CircuitBreakerOpenException:
        raise HTTPException(status_code=503, detail="Database degraded. Load shedding active.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{short_code}")
async def redirect_to_long_url(short_code: str):
    try:
        long_url = await redis_client.get(short_code)
        if long_url:
            return RedirectResponse(url=long_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
            
        db_url = await db_breaker.call(db_get_long_url, short_code)
        db_breaker.handle_success()
        
        if not db_url:
            raise HTTPException(status_code=404, detail="Requested short code route does not exist.")
            
        await redis_client.set(short_code, db_url, ex=300)
        return RedirectResponse(url=db_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
        
    except CircuitBreakerOpenException:
        raise HTTPException(status_code=503, detail="Database connectivity degraded.")
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))
