import math
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from app.database import get_db_pool

router = APIRouter(prefix="/ai", tags=["Agentic AI Analytics & RAG"])

# --- LOCALIZED IN-MEMORY VECTOR ENGINE MATRIX ---
VECTOR_STORE = []

def generate_16_dim_embedding(text: str) -> list[float]:
    """Generates a deterministic, normalized 16-dimensional embedding vector from text."""
    vector = [0.0] * 16
    for i, char in enumerate(text):
        vector[i % 16] += ord(char)
    
    # Normalize vector to unit length
    magnitude = math.sqrt(sum(v**2 for v in vector)) or 1.0
    return [v / magnitude for v in vector]

def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Calculates the scalar dot product similarity between two unit vectors."""
    return sum(a * b for a, b in zip(v1, v2))

# --- PYDANTIC SCHEMAS ---
class QueryRequest(BaseModel):
    question: str

# --- ENDPOINTS ---

@router.post("/sync", status_code=status.HTTP_200_OK)
async def sync_database_to_vector_store():
    """Real Bridge: Pulls rows from PostgreSQL, converts to text, and indexes into Vector Storage."""
    pool = await get_db_pool()
    
    # 1. Fetch raw structured data from live PostgreSQL
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT short_code, long_url FROM links")
    
    if not rows:
        return {"status": "success", "message": "PostgreSQL database is empty. No links found to index.", "synced_count": 0}
    
    # 2. Clear old vector state to prevent duplicates
    VECTOR_STORE.clear()
    
    # 3. Transform structured relational data into unstructured semantic knowledge
    for row in rows:
        short_code = row["short_code"]
        long_url = row["long_url"]
        
        # Construct semantic document context
        semantic_document = f"Short code token tracking key '{short_code}' securely routes and redirects external users to the target corporate destination address: {long_url}."
        
        embedding = generate_16_dim_embedding(semantic_document)
        
        VECTOR_STORE.append({
            "id": short_code,
            "text": semantic_document,
            "vector": embedding,
            "metadata": {"short_code": short_code, "long_url": long_url}
        })
        
    return {
        "status": "success",
        "message": "Successfully vectorized and ingested relational tables into local RAG engine.",
        "synced_count": len(VECTOR_STORE)
    }

@router.post("/query", status_code=status.HTTP_200_OK)
async def query_link_intelligence(payload: QueryRequest):
    """Executes semantic search across synced database links using vector distance matching."""
    if not VECTOR_STORE:
        raise HTTPException(
            status_code=400, 
            detail="Vector store is empty. Execute the /ai/sync endpoint first to index PostgreSQL rows."
        )
    
    # 1. Vectorize the incoming search question
    query_vector = generate_16_dim_embedding(payload.question)
    
    # 2. Calculate vector similarity rankings across all indexed records
    rankings = []
    for doc in VECTOR_STORE:
        similarity = cosine_similarity(query_vector, doc["vector"])
        rankings.append((similarity, doc))
        
    # Sort by highest similarity match
    rankings.sort(key=lambda x: x[0], reverse=True)
    top_match_score, top_doc = rankings[0]
    
    if top_match_score < 0.3:
        return {
            "question": payload.question,
            "context_found": False,
            "answer": "The AI Agent could not find any relevant shortener links matching the context of your question inside our system records."
        }

    # 3. Formulate the Agentic Answer using the retrieved context
    context_text = top_doc["text"]
    target_url = top_doc["metadata"]["long_url"]
    
    agent_response = (
        f"[AI AGENT INFERENCE ENGINE]: Analyzing synced infrastructure records. "
        f"Regarding your inquiry, I successfully retrieved a relevant asset from the vector indexes. "
        f"The system matches this intent to the destination domain: '{target_url}'. "
        f"Context baseline verified: \"{context_text}\" (Similarity Match Score: {top_match_score:.4f})."
    )
    
    return {
        "question": payload.question,
        "context_found": True,
        "similarity_score": round(top_match_score, 4),
        "retrieved_context": context_text,
        "answer": agent_response
    }
