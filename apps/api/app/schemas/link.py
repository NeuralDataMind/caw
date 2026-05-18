from pydantic import BaseModel

class LinkCreate(BaseModel):
    """Data Transfer Object capturing raw incoming link shortener payloads."""
    long_url: str
