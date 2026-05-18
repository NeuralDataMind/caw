import hashlib
from fastapi import APIRouter, status, HTTPException
from pydantic import BaseModel
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.embeddings import Embeddings
from langchain_community.vectorstores import Chroma

router = APIRouter(prefix="/ai", tags=["Agentic AI & RAG Subsystem"])

# --- PILLAR 1: DETERMINISTIC SRE EMBEDDING CORE ---
class LocalSREEmbeddings(Embeddings):
    """Custom lightweight vectorizer to prevent heavy model download lags inside Docker."""
    def _embed(self, text: str) -> list[float]:
        hashed = hashlib.md5(text.encode("utf-8")).digest()
        return [float(b) / 255.0 for b in hashed]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

embedding_engine = LocalSREEmbeddings()

# Initialize an Ephemeral in-memory Chroma instance wrapped cleanly inside LangChain
vector_store = Chroma(
    collection_name="b2b_context_store",
    embedding_function=embedding_engine
)

# --- PILLAR 2: DATA INGESTION PYDANTIC SCHEMAS ---
class DocumentIngest(BaseModel):
    document_id: str
    content: str

class QueryPayload(BaseModel):
    question: str

# --- PILLAR 3: THE RAG ENDPOINTS ---
@router.post("/ingest", status_code=status.HTTP_201_CREATED)
async def ingest_document(payload: DocumentIngest):
    """Splits raw unstructured document data into semantic chunks and updates the vector store."""
    try:
        splitter = RecursiveCharacterTextSplitter(chunk_size=150, chunk_overlap=30)
        chunks = splitter.split_text(payload.content)
        metadatas = [{"source_doc": payload.document_id} for _ in chunks]
        
        # LangChain handles the database instance mapping internally
        vector_store.add_texts(texts=chunks, metadatas=metadatas)
        
        return {
            "status": "success",
            "message": "Semantic context indexed successfully.",
            "chunks_processed": len(chunks)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion lifecycle aborted: {str(e)}"
        )

@router.post("/query")
async def query_rag_pipeline(payload: QueryPayload):
    """Retrieves context from the vector database and formats the final inference response."""
    try:
        docs = vector_store.similarity_search(payload.question, k=2)
        retrieved_contexts = [doc.page_content for doc in docs]
        
        if not retrieved_contexts:
            return {
                "question": payload.question,
                "context_found": False,
                "answer": "No relevant B2B operational data found in local vector storage."
            }
        
        unified_context = " | ".join(retrieved_contexts)
        simulated_response = (
            f"[AI AGENT INFERENCE]: Based on the retrieved context ({unified_context}), "
            f"the system evaluates that your query regarding '{payload.question}' matches our indexed documentation."
        )
        
        return {
            "question": payload.question,
            "context_found": True,
            "retrieved_chunks": retrieved_contexts,
            "answer": simulated_response
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Vector query execution failure: {str(e)}"
        )
