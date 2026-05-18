from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # Security Gates
    SSRF_PROTECTION_ENABLED: bool = True
    ALLOWED_DOMAINS: List[str] = ["example.com", "localhost"]
    
    # Infrastructure placeholders for the interview
    DATABASE_URL: str = "postgresql://postgres:secret@db:5432/links_db"
    REDIS_URL: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"
        extra = "ignore"

# This instantiates the object so 'from app.config import settings' works perfectly
settings = Settings()