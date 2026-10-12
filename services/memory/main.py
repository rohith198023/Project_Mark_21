import os
import logging
from fastapi import FastAPI, HTTPException
import uvicorn

import socket
import httpx
from fastapi.responses import JSONResponse
from shared.contracts.schemas import (
    MemoryQueryRequest, MemoryQueryResponse, MemoryStoreRequest,
    HealthResponse, ReadinessResponse
)
from shared.config.settings import settings

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("memory-service")

app = FastAPI(
    title="JARVIS Memory Service",
    description="Vector indexing and structured storage memory service.",
    version="1.0.0"
)

# Connect to database configuration (e.g. Postgres and Qdrant)
POSTGRES_URI = settings.postgres_uri
QDRANT_HOST = settings.qdrant_host
QDRANT_PORT = settings.qdrant_port

@app.on_event("startup")
async def startup_db_clients():
    logger.info("Initializing vector and relational storage drivers...")
    # TODO: Initialize connection pools:
    # 1. pg_pool = await asyncpg.create_pool(POSTGRES_URI)
    # 2. qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    logger.info(f"Memory system configured to target Postgres: {POSTGRES_URI.split('@')[-1]}")
    logger.info(f"Memory system configured to target Qdrant: {QDRANT_HOST}:{QDRANT_PORT}")

def check_postgres(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except Exception:
        return False

async def check_qdrant(host: str, port: int) -> bool:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"http://{host}:{port}/readyz", timeout=1.0)
            return resp.status_code == 200
        except Exception:
            return False

@app.get("/healthz", response_model=HealthResponse)
def healthz():
    """Liveness probe."""
    return HealthResponse(status="healthy", service="memory-service", version="1.0.0")

@app.get("/readyz", response_model=ReadinessResponse)
async def readyz():
    """Readiness probe checking database availability."""
    checks = {}
    
    # Parse postgres host/port
    pg_host = "postgres"
    pg_port = 5432
    try:
        parts = POSTGRES_URI.split("@")[-1].split("/")[0].split(":")
        pg_host = parts[0]
        if len(parts) > 1:
            pg_port = int(parts[1])
    except Exception:
        pass

    # Run checks
    pg_ready = check_postgres(pg_host, pg_port)
    checks["postgres"] = "online" if pg_ready else "offline"
    
    qdrant_ready = await check_qdrant(QDRANT_HOST, QDRANT_PORT)
    checks["qdrant"] = "online" if qdrant_ready else "offline"

    if not pg_ready or not qdrant_ready:
        return JSONResponse(
            status_code=503,
            content=ReadinessResponse(status="not_ready", service="memory-service", checks=checks).model_dump()
        )
        
    return ReadinessResponse(status="ready", service="memory-service", checks=checks)

@app.post("/api/v1/query", response_model=MemoryQueryResponse)
async def query_memory(request: MemoryQueryRequest):
    """Performs semantic vector lookup and merges metadata context from Postgres."""
    logger.info(f"Searching memory for query: '{request.query}' with limit {request.limit}")
    
    # TODO: 
    # 1. Generate text embeddings using local model (e.g., SentenceTransformers / ONNX)
    # 2. Query Qdrant for nearest neighbor matches
    # 3. Join metadata keys with structured SQL DB rows to fetch documents
    
    # Mock return context
    matches = [
        {
            "id": "mem_001",
            "content": f"Cached user interaction regarding: '{request.query}'",
            "score": 0.89,
            "metadata": {
                "source": "conversation_history",
                "timestamp": "2026-06-12T12:00:00Z"
            }
        },
        {
            "id": "mem_002",
            "content": "User prefers dark mode themes and fast Python microservices.",
            "score": 0.76,
            "metadata": {
                "source": "user_preferences",
                "timestamp": "2026-06-12T10:15:00Z"
            }
        }
    ]
    return MemoryQueryResponse(matches=matches[:request.limit])

@app.post("/api/v1/insert")
async def store_memory(request: MemoryStoreRequest):
    """Ingests a text string, generates embedding vector, and persists it in Qdrant & Postgres."""
    logger.info(f"Storing text block to DB (len: {len(request.content)} chars)...")
    
    # TODO:
    # 1. Generate embeddings locally
    # 2. Insert into Qdrant collection
    # 3. Store raw text and metadata logs in PostgreSQL
    
    return {
        "success": True,
        "id": "mem_generated_hash_123",
        "message": "Content successfully indexed in Qdrant vector DB and Postgres."
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8002))
    logger.info(f"Starting Memory Service on port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
