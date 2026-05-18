from fastapi import APIRouter
from ..schemas.link import LinkCreate

router = APIRouter(prefix="/links", tags=["Links"])

@router.post("/")
async def create_link(link_in: LinkCreate):
    return {"status": "success", "received": link_in.long_url}
