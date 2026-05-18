from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # Security Gates
    SSRF_PROTECTION_ENABLED: bool 
    
    
    DATABASE_URL: str 
    REDIS_URL: str 

    class Config:
        env_file = ".env"
        extra = "ignore"

# This instantiates the object so 'from app.config import settings' works perfectly
settings = Settings()