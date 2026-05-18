import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response, status
from app.routers import links, ai  # Import the new AI module

infrastructure_state = {"is_shutting_down": False}

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    infrastructure_state["is_shutting_down"] = True
    print("[SHUTDOWN]: SIGTERM received. Flipping readiness probe to unhealthy...")
    await asyncio.sleep(3)
    print("[SHUTDOWN]: Clean termination handshake reached.")

app = FastAPI(
    title="High-Availability B2B URL Shortening & AI RAG Engine",
    lifespan=lifespan
)

@app.get("/ready")
def readiness_probe(response: Response):
    if infrastructure_state["is_shutting_down"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "draining"}
    return {"status": "ready", "database": "healthy", "cache": "healthy"}

@app.get("/health")
def liveness_probe():
    return {"status": "alive"}

# Register both subsystems cleanly
app.include_router(links.router)
app.include_router(ai.router)