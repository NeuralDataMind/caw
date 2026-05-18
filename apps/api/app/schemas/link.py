from pydantic import BaseModel, field_validator
import re
from urllib.parse import urlparse
from app.config import settings  # Wire up your config variables

class LinkCreate(BaseModel):
    long_url: str

    @field_validator("long_url")
    @classmethod
    def validate_safety(cls, v: str) -> str:
        # 1. Strip hidden whitespace, null bytes, and control blocks
        v = re.sub(r"[\s\x00-\x1F\x7F]", "", v)

        # 2. XSS Protocol Blacklist Check (FIXED THE TYPO HERE)
        if v.lower().startswith(("javascript:", "data:", "file:", "vbscript:")):
            raise ValueError("Forbidden protocol")

        # 3. Dynamic SSRF Whitelist Validation
        if settings.SSRF_PROTECTION_ENABLED:
            parsed_url = urlparse(v)
            hostname = parsed_url.hostname
            
            if not hostname or hostname not in settings.ALLOWED_DOMAINS:
                raise ValueError("Domain access violation: target host not whitelisted.")

        return v