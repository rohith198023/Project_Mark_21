import os
import asyncio
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import uvicorn

from shared.contracts.schemas import (
    ChatRequest, ChatResponse, HealthResponse, ReadinessResponse,
    RoutingRequest, Task
)
from shared.config.settings import settings

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("api-gateway")

app = FastAPI(
    title="JARVIS API Gateway",
    description="Gateway API router for Project JARVIS local services.",
    version="1.0.0"
)

# Enable CORS for local web interface
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In development, allow all. In production, restrict to local frontend.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ORCHESTRATOR_URL = settings.get_service_url("orchestrator")

# List of services to monitor
MONITORED_SERVICES = {
    "orchestrator": settings.get_service_url("orchestrator"),
    "memory": settings.get_service_url("memory"),
    "browser": settings.get_service_url("browser"),
    "voice": settings.get_service_url("voice"),
    "desktop": settings.get_service_url("desktop"),
}

@app.get("/healthz", response_model=HealthResponse)
def healthz():
    """Liveness probe endpoint."""
    return HealthResponse(status="healthy", service="api-gateway", version="1.0.0")

@app.get("/readyz", response_model=ReadinessResponse)
async def readyz():
    """Readiness probe checking downstream orchestrator container availability."""
    checks = {}
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{ORCHESTRATOR_URL}/healthz", timeout=1.0)
            if resp.status_code == 200:
                checks["orchestrator"] = "online"
            else:
                checks["orchestrator"] = f"unhealthy (status: {resp.status_code})"
        except Exception as e:
            checks["orchestrator"] = f"offline ({str(e)})"
            
    if any("offline" in v or "unhealthy" in v for v in checks.values()):
        return JSONResponse(
            status_code=503,
            content=ReadinessResponse(status="not_ready", service="api-gateway", checks=checks).model_dump()
        )
        
    return ReadinessResponse(status="ready", service="api-gateway", checks=checks)

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Routes user chat queries directly to the Orchestrator service coordinate endpoint."""
    logger.info(f"Routing chat request to Orchestrator: {request.message[:40]}...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{ORCHESTRATOR_URL}/api/v1/coordinate",
                json=request.model_dump(),
                timeout=30.0
            )
            if response.status_code != 200:
                logger.error(f"Orchestrator returned error {response.status_code}: {response.text}")
                raise HTTPException(status_code=response.status_code, detail="Orchestrator service error")
            return response.json()
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to Orchestrator at {ORCHESTRATOR_URL}: {e}")
            raise HTTPException(status_code=503, detail="Orchestrator service unavailable")

@app.post("/api/v1/command", response_model=Task)
async def command(request: RoutingRequest):
    """Directly submits a routing command, creating a managed task in the Orchestrator."""
    logger.info(f"Routing command task request: {request.user_input[:40]}...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{ORCHESTRATOR_URL}/api/v1/tasks",
                json=request.model_dump(),
                timeout=10.0
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Orchestrator task engine error")
            return response.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail="Orchestrator service unavailable")

@app.get("/api/v1/tasks/{task_id}", response_model=Task)
async def get_task(task_id: str):
    """Proxies Task status queries to the Orchestrator."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{ORCHESTRATOR_URL}/api/v1/tasks/{task_id}", timeout=2.0)
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Task not found")
            elif response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Orchestrator error")
            return response.json()
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Orchestrator unavailable")

@app.get("/api/v1/agents")
async def get_agents():
    """Proxies Agent Registry listings to the Orchestrator."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{ORCHESTRATOR_URL}/api/v1/agents", timeout=2.0)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Orchestrator error")
            return response.json()
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Orchestrator unavailable")

@app.get("/api/v1/services/health")
async def check_all_services_health():
    """Polls health endpoints of all internal services and returns consolidated health."""
    results = {}
    
    async def get_health(name: str, url: str):
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{url}/healthz", timeout=1.5)
                if resp.status_code == 200:
                    results[name] = {
                        "status": "healthy",
                        "details": resp.json()
                    }
                else:
                    results[name] = {
                        "status": "unhealthy",
                        "error": f"Status code: {resp.status_code}"
                    }
            except Exception as e:
                results[name] = {
                    "status": "down",
                    "error": str(e)
                }

    tasks = [get_health(name, url) for name, url in MONITORED_SERVICES.items()]
    await asyncio.gather(*tasks)
    return {
        "gateway": "healthy",
        "services": results
    }

@app.post("/api/v1/tasks/{task_id}/confirm", response_model=ChatResponse)
async def confirm_task(task_id: str):
    """Proxies Task approval confirmation to the Orchestrator."""
    logger.info(f"Confirming task {task_id}...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{ORCHESTRATOR_URL}/api/v1/tasks/{task_id}/confirm", timeout=30.0)
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Task not found")
            elif response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Orchestrator error")
            return response.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail="Orchestrator unavailable")

@app.post("/api/v1/tasks/{task_id}/cancel", response_model=ChatResponse)
async def cancel_task(task_id: str):
    """Proxies Task rejection to the Orchestrator."""
    logger.info(f"Cancelling task {task_id}...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{ORCHESTRATOR_URL}/api/v1/tasks/{task_id}/cancel", timeout=10.0)
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Task not found")
            elif response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Orchestrator error")
            return response.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail="Orchestrator unavailable")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting API Gateway on port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
