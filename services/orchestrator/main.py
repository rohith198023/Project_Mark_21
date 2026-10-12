import os
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, List, Union
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import httpx
import uvicorn

from shared.contracts.schemas import (
    ChatRequest, ChatResponse, HealthResponse, ReadinessResponse,
    PermissionLevel, TaskStatus, Task, RoutingRequest, RoutingResponse,
    MemoryQueryRequest, BrowserActionRequest, BrowserSearchRequest, VoiceSynthesisRequest,
    PlannerOutput, PlannerFailure, RiskLevel, TargetAgent, IntentType
)
from shared.config.settings import settings
from shared.security.permissions import classify_risk, requires_confirmation, request_user_confirmation
import planner_service

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("orchestrator")

app = FastAPI(
    title="JARVIS Orchestrator",
    description="Central coordination engine for Project JARVIS.",
    version="1.0.0"
)

MEMORY_URL = settings.get_service_url("memory")
BROWSER_URL = settings.get_service_url("browser")
VOICE_URL = settings.get_service_url("voice")
DESKTOP_URL = settings.get_service_url("desktop")

# In-memory Task Database
tasks_db: Dict[str, Task] = {}

# Agent Registry definitions
AGENT_REGISTRY = {
    "desktop": {
        "name": "desktop",
        "description": "Manages local OS applications, launch requests, folder navigation, and screenshots.",
        "supported_intents": [
            "open_app", "close_app", "focus_app", "list_open_apps", "open_folder", "screenshot"
        ],
        "risk_level": PermissionLevel.MEDIUM,
        "endpoint": DESKTOP_URL
    },
    "browser": {
        "name": "browser",
        "description": "Navigates websites, performs web searches, and extracts data from pages.",
        "supported_intents": ["browse_web", "search_web", "navigate_url"],
        "risk_level": PermissionLevel.MEDIUM,
        "endpoint": BROWSER_URL
    },
    "memory": {
        "name": "memory",
        "description": "Handles vector memory indexing and relational contextual recall.",
        "supported_intents": ["remember", "recall"],
        "risk_level": PermissionLevel.LOW,
        "endpoint": MEMORY_URL
    },
    "voice": {
        "name": "voice",
        "description": "Processes audio transcriptions (STT) and voice synthesis (TTS).",
        "supported_intents": ["transcribe", "speak"],
        "risk_level": PermissionLevel.LOW,
        "endpoint": VOICE_URL
    },
    "research": {
        "name": "research",
        "description": "Coordinates search tasks, page crawls, and merges document synthesis.",
        "supported_intents": ["research", "compare"],
        "risk_level": PermissionLevel.MEDIUM,
        "endpoint": "placeholder"
    },
    "code": {
        "name": "code",
        "description": "Compiles and debugs local scripts inside a sandbox environment.",
        "supported_intents": ["code", "debug"],
        "risk_level": PermissionLevel.HIGH,
        "endpoint": "placeholder"
    },
    "documents": {
        "name": "documents",
        "description": "Ingests files, parses documents, and generates textual summaries.",
        "supported_intents": ["document", "summarize"],
        "risk_level": PermissionLevel.LOW,
        "endpoint": "placeholder"
    },
    "tasks": {
        "name": "tasks",
        "description": "Sets local background reminders, timers, and scheduled jobs.",
        "supported_intents": ["task", "reminder"],
        "risk_level": PermissionLevel.LOW,
        "endpoint": "placeholder"
    },
    "meeting": {
        "name": "meeting",
        "description": "Schedules calendar invites, manages rooms, and logs transcripts.",
        "supported_intents": ["meeting"],
        "risk_level": PermissionLevel.MEDIUM,
        "endpoint": "placeholder"
    }
}

# --------------------------------------------------------------------------- #
# Legacy keyword-based router (fallback when planner is unavailable)
# --------------------------------------------------------------------------- #

def classify_intent_and_route(user_input: str) -> tuple[str, str]:
    """
    Keyword-based fallback intent classifier. Used when the LLM planner is
    unavailable (missing API key, network error, or validation failure).
    """
    text = user_input.lower()

    if any(k in text for k in ["close", "shutdown", "exit", "terminate"]):
        return "close_app", "desktop"
    elif any(k in text for k in ["focus", "switch to", "bring to front"]):
        return "focus_app", "desktop"
    elif any(k in text for k in ["list open apps", "show running apps", "list apps", "running apps"]):
        return "list_open_apps", "desktop"
    elif any(k in text for k in ["screenshot", "screen capture", "capture screen"]):
        return "screenshot", "desktop"
    elif any(k in text for k in ["downloads folder", "documents folder", "desktop folder",
                                   "open folder", "my downloads", "my documents"]):
        return "open_folder", "desktop"
    elif any(k in text for k in ["open", "launch", "app", "notepad", "calculator", "terminal", "explorer"]):
        return "open_app", "desktop"
    elif any(k in text for k in ["search", "google", "find online", "look up"]):
        return "search_web", "browser"
    elif any(k in text for k in ["browse", "website", "scrap", "navigate to"]):
        return "browse_web", "browser"
    elif any(k in text for k in ["remember", "store", "save to memory"]):
        return "remember", "memory"
    elif any(k in text for k in ["recall", "retrieve", "get memory", "recall memory"]):
        return "recall", "memory"
    elif any(k in text for k in ["speak", "say", "talk", "voice"]):
        return "speak", "voice"
    elif any(k in text for k in ["transcribe", "stt", "audio to text"]):
        return "transcribe", "voice"
    elif any(k in text for k in ["code", "program", "script", "write script"]):
        return "code", "code"
    elif any(k in text for k in ["debug", "fix code", "compile"]):
        return "debug", "code"
    elif any(k in text for k in ["research", "compare", "analyze"]):
        return "research", "research"
    elif any(k in text for k in ["document", "pdf", "summarize", "summary"]):
        return "summarize", "documents"
    elif any(k in text for k in ["task", "todo", "reminder", "remind"]):
        return "reminder", "tasks"
    elif any(k in text for k in ["meeting", "calendar", "invite"]):
        return "meeting", "meeting"

    return "unknown", "orchestrator"


def _build_task_from_planner(
    planner_output: PlannerOutput,
    task_id: str,
    timestamp: str
) -> Task:
    """Creates a Task from a validated PlannerOutput."""
    # Map planner risk_level to PermissionLevel
    risk_map = {
        RiskLevel.LOW: PermissionLevel.LOW,
        RiskLevel.MEDIUM: PermissionLevel.MEDIUM,
        RiskLevel.HIGH: PermissionLevel.HIGH,
    }
    permission_level = risk_map.get(planner_output.risk_level, PermissionLevel.LOW)

    status = TaskStatus.PENDING
    if planner_output.requires_confirmation or planner_output.risk_level == RiskLevel.HIGH:
        status = TaskStatus.REQUIRES_CONFIRMATION

    return Task(
        id=task_id,
        user_input=planner_output.raw_user_input,
        intent=planner_output.intent,
        target_agent=planner_output.target_agent.value,
        status=status,
        permission_level=permission_level,
        created_at=timestamp,
        updated_at=timestamp,
        parameters=planner_output.parameters or {},
        planner_metadata={
            "schema_version": planner_output.schema_version,
            "action": planner_output.action,
            "target": planner_output.target,
            "confidence": planner_output.confidence,
            "risk_level": planner_output.risk_level.value,
            "reasoning_summary": planner_output.reasoning_summary,
            "planner_prompt_version": planner_service.PLANNER_PROMPT_VERSION,
            "model_name": settings.groq_model,
            "routing_method": "llm_planner",
        }
    )


# --------------------------------------------------------------------------- #
# Health probes
# --------------------------------------------------------------------------- #

@app.get("/healthz", response_model=HealthResponse)
def healthz():
    """Liveness probe."""
    return HealthResponse(status="healthy", service="orchestrator", version="1.0.0")

@app.get("/readyz", response_model=ReadinessResponse)
async def readyz():
    """Readiness probe checking liveness of downstream memory, browser, voice, and desktop containers."""
    checks = {}
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{MEMORY_URL}/healthz", timeout=1.0)
            checks["memory"] = "online" if resp.status_code == 200 else f"unhealthy ({resp.status_code})"
        except Exception as e:
            checks["memory"] = f"offline ({str(e)})"

        try:
            resp = await client.get(f"{BROWSER_URL}/healthz", timeout=1.0)
            checks["browser"] = "online" if resp.status_code == 200 else f"unhealthy ({resp.status_code})"
        except Exception as e:
            checks["browser"] = f"offline ({str(e)})"

        try:
            resp = await client.get(f"{VOICE_URL}/healthz", timeout=1.0)
            checks["voice"] = "online" if resp.status_code == 200 else f"unhealthy ({resp.status_code})"
        except Exception as e:
            checks["voice"] = f"offline ({str(e)})"

        try:
            resp = await client.get(f"{DESKTOP_URL}/healthz", timeout=1.0)
            checks["desktop"] = "online" if resp.status_code == 200 else f"unhealthy ({resp.status_code})"
        except Exception as e:
            checks["desktop"] = f"offline ({str(e)})"

    # Report planner status
    checks["planner"] = "ready" if settings.groq_api_key else "degraded (GROQ_API_KEY not set, keyword fallback active)"

    if any("offline" in v or "unhealthy" in v for v in checks.values()):
        return JSONResponse(
            status_code=503,
            content=ReadinessResponse(status="not_ready", service="orchestrator", checks=checks).model_dump()
        )

    return ReadinessResponse(status="ready", service="orchestrator", checks=checks)

@app.get("/api/v1/agents")
def get_agents():
    """Lists registered system agents."""
    logger.info("Listing registered Monorepo agents...")
    return AGENT_REGISTRY

@app.get("/api/v1/tasks/{task_id}", response_model=Task)
def get_task(task_id: str):
    """Fetches a task from the in-memory store."""
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_db[task_id]

@app.post("/api/v1/route", response_model=RoutingResponse)
def route_command(request: RoutingRequest):
    """Parses user input, classifies intent, maps to an agent, and creates a task payload (legacy keyword fallback)."""
    intent, target = classify_intent_and_route(request.user_input)
    risk_level = classify_risk(request.user_input)

    timestamp = datetime.utcnow().isoformat() + "Z"
    task_id = f"task_{uuid.uuid4().hex[:10]}"

    status = TaskStatus.PENDING
    if requires_confirmation(request.user_input, risk_level):
        status = TaskStatus.REQUIRES_CONFIRMATION

    task = Task(
        id=task_id,
        user_input=request.user_input,
        intent=intent,
        target_agent=target,
        status=status,
        permission_level=risk_level,
        created_at=timestamp,
        updated_at=timestamp
    )

    explanation = f"Routed query based on keyword mapping to '{target}' agent with risk level '{risk_level.upper()}'."
    return RoutingResponse(task=task, explanation=explanation)

@app.post("/api/v1/tasks", response_model=Task)
def create_task(request: RoutingRequest):
    """Registers and queues a user command in the task manager (legacy keyword fallback)."""
    logger.info(f"Registering new task for user input: '{request.user_input[:40]}'")
    route_res = route_command(request)
    task = route_res.task
    tasks_db[task.id] = task
    return task


# --------------------------------------------------------------------------- #
# Task Execution Dispatcher
# --------------------------------------------------------------------------- #

async def run_task_execution(task: Task) -> tuple[str, List[Dict[str, Any]]]:
    """Helper to dispatch task executions to downstream microservices and build responses."""
    actions_taken = []
    response_text = ""

    if task.target_agent == "memory":
        logger.info(f"Routing to Memory service at {MEMORY_URL}...")
        async with httpx.AsyncClient() as client:
            try:
                mem_resp = await client.post(
                    f"{MEMORY_URL}/api/v1/query",
                    json={"query": task.user_input, "limit": 2},
                    timeout=2.0
                )
                if mem_resp.status_code == 200:
                    actions_taken.append({
                        "service": "memory", "action": "semantic_search",
                        "status": "success", "output": mem_resp.json()
                    })
                    response_text += " [Fetched memory context]"
                else:
                    actions_taken.append({
                        "service": "memory", "action": "semantic_search",
                        "status": "failed", "error": f"HTTP {mem_resp.status_code}"
                    })
            except Exception as e:
                actions_taken.append({
                    "service": "memory", "action": "semantic_search",
                    "status": "down", "error": str(e)
                })

    elif task.target_agent == "browser":
        logger.info(f"Routing to Browser service at {BROWSER_URL}...")
        search_target = (task.planner_metadata or {}).get("target") or task.user_input
        intent = task.intent

        async with httpx.AsyncClient() as client:
            try:
                # search_web → POST /api/v1/search
                if intent in ("search_web", "search"):
                    logger.info(f"[Browser] Dispatching search for: '{search_target}'")
                    browser_resp = await client.post(
                        f"{BROWSER_URL}/api/v1/search",
                        json={"query": search_target, "max_results": 5},
                        timeout=25.0  # Playwright can take up to 20s
                    )
                    if browser_resp.status_code == 200:
                        res = browser_resp.json()
                        results = res.get("results", [])
                        if res.get("success") and results:
                            # Build a readable summary of top results
                            summary_lines = [f"{i+1}. {r['title']} — {r['url']}" for i, r in enumerate(results[:5])]
                            summary = "\n".join(summary_lines)
                            actions_taken.append({
                                "service": "browser", "action": "search_web",
                                "status": "success", "output": res
                            })
                            response_text += f" [Search results for '{search_target}':\n{summary}]"
                            task.status = TaskStatus.SUCCESS
                        else:
                            err = res.get("error") or "No results returned (search engine returned empty results)"
                            actions_taken.append({
                                "service": "browser", "action": "search_web",
                                "status": "failed", "error": err
                            })
                            response_text += f" [Browser search failed: {err}]"
                            task.status = TaskStatus.FAILED
                    else:
                        actions_taken.append({
                            "service": "browser", "action": "search_web",
                            "status": "failed", "error": f"HTTP {browser_resp.status_code}"
                        })
                        task.status = TaskStatus.FAILED

                # navigate_url / browse_web → POST /api/v1/browse
                elif intent in ("navigate_url", "browse_web", "navigate"):
                    url_target = search_target if search_target.startswith("http") else f"https://{search_target}"
                    logger.info(f"[Browser] Dispatching navigate to: '{url_target}'")
                    browser_resp = await client.post(
                        f"{BROWSER_URL}/api/v1/browse",
                        json={"action": "navigate", "url": url_target},
                        timeout=25.0
                    )
                    if browser_resp.status_code == 200:
                        res = browser_resp.json()
                        if res.get("success"):
                            page_title = res.get("page_title", "")
                            excerpt = (res.get("extracted_text") or "")[:400]
                            actions_taken.append({
                                "service": "browser", "action": "navigate_url",
                                "status": "success", "output": res
                            })
                            response_text += f" [Navigated to '{url_target}'. Page: '{page_title}'. Excerpt: {excerpt}...]"
                            task.status = TaskStatus.SUCCESS
                        else:
                            err = res.get("error", "Navigation failed")
                            actions_taken.append({
                                "service": "browser", "action": "navigate_url",
                                "status": "failed", "error": err
                            })
                            response_text += f" [Browser navigate failed: {err}]"
                            task.status = TaskStatus.FAILED
                    else:
                        actions_taken.append({
                            "service": "browser", "action": "navigate_url",
                            "status": "failed", "error": f"HTTP {browser_resp.status_code}"
                        })
                        task.status = TaskStatus.FAILED

                else:
                    # Unrecognised browser intent — pass through to generic browse action
                    logger.info(f"[Browser] Dispatching generic browse action: '{intent}'")
                    browser_resp = await client.post(
                        f"{BROWSER_URL}/api/v1/browse",
                        json={"action": intent, "url": search_target},
                        timeout=25.0
                    )
                    if browser_resp.status_code == 200:
                        res = browser_resp.json()
                        actions_taken.append({
                            "service": "browser", "action": intent,
                            "status": "success" if res.get("success") else "failed",
                            "output": res
                        })
                        if res.get("success"):
                            response_text += f" [Browser '{intent}' completed for '{search_target}']"
                            task.status = TaskStatus.SUCCESS
                        else:
                            response_text += f" [Browser '{intent}' failed: {res.get('error')}]"
                            task.status = TaskStatus.FAILED
                    else:
                        actions_taken.append({
                            "service": "browser", "action": intent,
                            "status": "failed", "error": f"HTTP {browser_resp.status_code}"
                        })
                        task.status = TaskStatus.FAILED

            except httpx.TimeoutException:
                logger.error(f"[Browser] Request timed out for intent='{intent}'")
                actions_taken.append({
                    "service": "browser", "action": intent,
                    "status": "timeout", "error": "Browser service request timed out (>25s)"
                })
                response_text += f" [Browser service timed out for '{intent}']"
                task.status = TaskStatus.FAILED
            except Exception as e:
                logger.error(f"[Browser] Connection error: {e}")
                actions_taken.append({
                    "service": "browser", "action": intent,
                    "status": "down", "error": str(e)
                })
                task.status = TaskStatus.FAILED

    elif task.target_agent == "voice":
        logger.info(f"Routing to Voice service at {VOICE_URL}...")
        async with httpx.AsyncClient() as client:
            try:
                voice_resp = await client.post(
                    f"{VOICE_URL}/api/v1/tts",
                    json={"text": "Hello, I am processing your query now."},
                    timeout=3.0
                )
                if voice_resp.status_code == 200:
                    actions_taken.append({
                        "service": "voice", "action": "text_to_speech",
                        "status": "success", "output": voice_resp.json()
                    })
                    response_text += " [Audio output synthesized]"
                else:
                    actions_taken.append({
                        "service": "voice", "action": "text_to_speech",
                        "status": "failed", "error": f"HTTP {voice_resp.status_code}"
                    })
            except Exception as e:
                actions_taken.append({
                    "service": "voice", "action": "text_to_speech",
                    "status": "down", "error": str(e)
                })

    elif task.target_agent == "desktop":
        logger.info(f"Routing to Desktop service at {DESKTOP_URL}...")
        async with httpx.AsyncClient() as client:
            try:
                desktop_resp = await client.post(
                    f"{DESKTOP_URL}/api/v1/desktop/execute",
                    json=task.model_dump(),
                    timeout=10.0
                )
                if desktop_resp.status_code == 200:
                    res = desktop_resp.json()
                    success = res.get("success", False)
                    output = res.get("output", "")
                    error = res.get("error")

                    actions_taken.append({
                        "service": "desktop",
                        "action": task.intent,
                        "status": "success" if success else "failed",
                        "output": res
                    })

                    if success:
                        response_text += f" [Executed: {output}]"
                        task.status = TaskStatus.SUCCESS
                    else:
                        response_text += f" [Failed: {error}]"
                        task.status = TaskStatus.FAILED
                else:
                    actions_taken.append({
                        "service": "desktop", "action": task.intent,
                        "status": "failed", "error": f"HTTP {desktop_resp.status_code}"
                    })
                    task.status = TaskStatus.FAILED
            except Exception as e:
                actions_taken.append({
                    "service": "desktop", "action": task.intent,
                    "status": "down", "error": str(e)
                })
                task.status = TaskStatus.FAILED

    # Default responses for other routed agents (placeholder logs only)
    elif task.target_agent not in ["orchestrator", "unknown"]:
        actions_taken.append({
            "service": task.target_agent,
            "action": task.intent,
            "status": "success",
            "output": f"Mock executed {task.intent} on placeholder agent {task.target_agent}."
        })
        response_text += f" [Routed to {task.target_agent} agent]"

    # Update status to Success if not already set to FAILED
    if task.status != TaskStatus.FAILED:
        task.status = TaskStatus.SUCCESS
    task.updated_at = datetime.utcnow().isoformat() + "Z"

    clean_text = response_text.strip()
    if clean_text.startswith("[") and clean_text.endswith("]"):
        clean_text = clean_text[1:-1].strip()
    if not clean_text:
        clean_text = f"Task completed successfully on {task.target_agent} agent."

    return clean_text, actions_taken


# --------------------------------------------------------------------------- #
# Main Coordinate Endpoint — with LLM Planner integration
# --------------------------------------------------------------------------- #

@app.post("/api/v1/coordinate", response_model=ChatResponse)
async def coordinate(request: ChatRequest):
    """
    Main routing adapter with LLM Planner/Refiner integration.

    Flow:
      raw user input
        → LLM Planner (Groq)
        → Pydantic Validation
        → Confidence gate (route / clarify / reject)
        → Risk gate (block high-risk / require confirmation)
        → Specialist Agent execution
        → [Fallback] keyword-based router if planner unavailable
    """
    session_id = request.session_id or str(uuid.uuid4())
    logger.info(f"Coordinating query in session {session_id}: '{request.message}'")

    actions_taken = []
    timestamp = datetime.utcnow().isoformat() + "Z"
    task_id = f"task_{uuid.uuid4().hex[:10]}"

    # ------------------------------------------------------------------ #
    # Stage 1: LLM Planner
    # ------------------------------------------------------------------ #
    planner_result: Union[PlannerOutput, PlannerFailure] = planner_service.plan(request.message)

    planner_log: Dict[str, Any] = {
        "service": "orchestrator",
        "action": "llm_planner",
        "status": "success" if isinstance(planner_result, PlannerOutput) else "failed",
        "output": planner_result.model_dump()
    }
    actions_taken.append(planner_log)

    # ------------------------------------------------------------------ #
    # Stage 2: Intent routing + Conversational AI gate + Risk gate
    # ------------------------------------------------------------------ #
    if isinstance(planner_result, PlannerOutput):
        confidence = planner_result.confidence
        route_threshold = settings.planner_confidence_route_threshold
        clarify_threshold = settings.planner_confidence_clarify_threshold

        logger.info(
            f"[Planner gate] intent={planner_result.intent} target_agent={planner_result.target_agent} "
            f"confidence={confidence:.2f} risk={planner_result.risk_level} "
            f"requires_confirmation={planner_result.requires_confirmation}"
        )

        # 2a. Conversational / Q&A / Generic Assistant Task handling
        # Direct conversational response if it's conversation, general question, audio check, or generic task
        is_conversational = (
            planner_result.intent in ("conversation", "chat", "ask", "greeting", "reply", "general_qa")
            or planner_result.target_agent in (TargetAgent.SYSTEM, TargetAgent.UNKNOWN)
            or (confidence < route_threshold and not any(kw in request.message.lower() for kw in [
                "open", "close", "launch", "search", "browse", "screenshot", "remember",
                "recall", "terminate", "delete", "whatsapp", "teams", "notepad", "chrome",
                "calc", "folder"
            ]))
        )

        if is_conversational:
            logger.info(f"[Planner gate] Responding via Conversational AI: '{request.message}'")
            ans = planner_service.generate_conversational_response(request.message)
            actions_taken.append({
                "service": "orchestrator",
                "action": "conversational_ai",
                "status": "success",
                "output": {"reply": ans}
            })
            return ChatResponse(
                response=ans,
                session_id=session_id,
                actions_taken=actions_taken
            )

        # 2b. Low confidence OS action — ask for clarification
        if confidence < route_threshold:
            logger.info(f"[Planner gate] CLARIFY — confidence {confidence:.2f} below route threshold {route_threshold}")
            intent_hint = planner_result.reasoning_summary or f"intent={planner_result.intent}"
            return ChatResponse(
                response=(
                    f"I think you want to: {intent_hint}. "
                    f"Could you confirm or rephrase with more specific details?"
                ),
                session_id=session_id,
                actions_taken=actions_taken
            )

        # Build task from planner output
        task = _build_task_from_planner(planner_result, task_id, timestamp)
        tasks_db[task.id] = task

        routing_log: Dict[str, Any] = {
            "service": "orchestrator",
            "action": "task_routing",
            "status": "pending_confirmation" if task.status == TaskStatus.REQUIRES_CONFIRMATION else "success",
            "output": task.model_dump()
        }
        actions_taken.append(routing_log)

        # High risk / confirmation gate
        if task.status == TaskStatus.REQUIRES_CONFIRMATION:
            logger.warning(
                f"[Security] Task {task.id} BLOCKED — "
                f"risk={planner_result.risk_level} requires_confirmation={planner_result.requires_confirmation}"
            )
            return ChatResponse(
                response=(
                    f"⚠️ [CONFIRMATION REQUIRED] The action '{request.message}' is classified as "
                    f"{planner_result.risk_level.upper()} risk. "
                    f"Reasoning: {planner_result.reasoning_summary or 'High-risk operation detected.'}. "
                    f"Task ID: {task.id}. "
                    f"To proceed, call POST /api/v1/tasks/{task.id}/confirm"
                ),
                session_id=session_id,
                actions_taken=actions_taken
            )

        # Medium risk — warn in logs, proceed
        if planner_result.risk_level == RiskLevel.MEDIUM:
            logger.warning(f"[Security] Task {task.id} running with MEDIUM risk — proceeding.")

        # Execute
        response_msg, execution_actions = await run_task_execution(task)
        actions_taken.extend(execution_actions)

        # Update routing log with final status
        routing_log["output"] = task.model_dump()
        if task.status == TaskStatus.FAILED:
            routing_log["status"] = "failed"

        return ChatResponse(
            response=response_msg,
            session_id=session_id,
            actions_taken=actions_taken
        )

    # ------------------------------------------------------------------ #
    # Stage 3: Planner failed — fallback to keyword routing
    # ------------------------------------------------------------------ #
    logger.warning(
        f"[Planner fallback] Planner failed: {planner_result.failure_reason}. "
        f"Using keyword-based routing."
    )

    planner_result.fallback_used = True
    planner_log["output"] = planner_result.model_dump()

    # Use legacy keyword router
    routing_req = RoutingRequest(user_input=request.message)
    task = create_task(routing_req)

    routing_log_fallback: Dict[str, Any] = {
        "service": "orchestrator",
        "action": "task_routing_keyword_fallback",
        "status": "failed" if task.status == TaskStatus.REQUIRES_CONFIRMATION else "success",
        "output": task.model_dump()
    }
    if task.target_agent in ("orchestrator", "unknown"):
        ans = planner_service.generate_conversational_response(request.message)
        actions_taken.append({
            "service": "orchestrator",
            "action": "conversational_ai_fallback",
            "status": "success",
            "output": {"reply": ans}
        })
        return ChatResponse(
            response=ans,
            session_id=session_id,
            actions_taken=actions_taken
        )

    if task.status == TaskStatus.REQUIRES_CONFIRMATION:
        logger.warning(f"[Security] Task {task.id} requires user confirmation (keyword fallback path).")
        return ChatResponse(
            response=(
                f"[SECURITY WARNING: BLOCKED - HIGH RISK] Action '{request.message}' classified as "
                f"HIGH risk. Task execution has been halted. (Task ID: {task.id})"
            ),
            session_id=session_id,
            actions_taken=actions_taken
        )

    if task.permission_level == PermissionLevel.MEDIUM:
        logger.warning(f"[Security] Task {task.id} running with MEDIUM risk (keyword fallback).")

    response_msg, execution_actions = await run_task_execution(task)
    actions_taken.extend(execution_actions)

    routing_log_fallback["output"] = task.model_dump()
    if task.status == TaskStatus.FAILED:
        routing_log_fallback["status"] = "failed"

    return ChatResponse(
        response=response_msg,
        session_id=session_id,
        actions_taken=actions_taken
    )


# --------------------------------------------------------------------------- #
# Confirmation / Cancellation endpoints
# --------------------------------------------------------------------------- #

@app.post("/api/v1/tasks/{task_id}/confirm", response_model=ChatResponse)
async def confirm_task(task_id: str):
    """Approves a blocked high-risk task and resumes its execution flow."""
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="Task not found")
    task = tasks_db[task_id]
    if task.status != TaskStatus.REQUIRES_CONFIRMATION:
        raise HTTPException(status_code=400, detail=f"Task is in status {task.status}, cannot confirm.")

    logger.info(f"[Security] [APPROVED] Task {task_id} approved by user. Executing now.")
    task.status = TaskStatus.RUNNING
    task.updated_at = datetime.utcnow().isoformat() + "Z"

    response_msg, execution_actions = await run_task_execution(task)

    actions_taken = [{
        "service": "orchestrator",
        "action": "task_confirmation",
        "status": "success",
        "output": task.model_dump()
    }] + execution_actions

    return ChatResponse(
        response=f"[CONFIRMED & EXECUTED] {response_msg}",
        session_id=str(uuid.uuid4()),
        actions_taken=actions_taken
    )


@app.post("/api/v1/tasks/{task_id}/cancel", response_model=ChatResponse)
async def cancel_task(task_id: str):
    """Rejects a blocked high-risk task and marks it as FAILED."""
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="Task not found")
    task = tasks_db[task_id]
    if task.status != TaskStatus.REQUIRES_CONFIRMATION:
        raise HTTPException(status_code=400, detail=f"Task is in status {task.status}, cannot cancel.")

    logger.info(f"[Security] [REJECTED] Task {task_id} rejected by user.")
    task.status = TaskStatus.FAILED
    task.updated_at = datetime.utcnow().isoformat() + "Z"

    actions_taken = [{
        "service": "orchestrator",
        "action": "task_confirmation",
        "status": "failed",
        "output": task.model_dump()
    }]

    return ChatResponse(
        response=f"[BLOCKED & CANCELLED] Action was cancelled by user choice. (Task ID: {task.id})",
        session_id=str(uuid.uuid4()),
        actions_taken=actions_taken
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    logger.info(f"Starting Orchestrator on port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
