from fastapi import FastAPI
from pydantic import BaseModel, field_validator
import re

app = FastAPI()

class LinkCreate(BaseModel):
    long_url: str

    @field_validator("long_url")
    @classmethod
    def validate_safety(cls, v: str):
        v = re.sub(r"[\s\x00-\x1F\x7F]", "", v)
        if v.lower().startswith(("javascript:", "data:", "file:", "vbscript:")):
            raise ValueError("Forbidden protocol")
        return v

@app.post("/links")
def create_link(link_in: LinkCreate):
    return {"status": "success"}

@app.get("/health")
def health():
    return {"ok": True}
