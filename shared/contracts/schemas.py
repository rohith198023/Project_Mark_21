from enum import Enum
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any

# ==============================================================================
# Enums
# ==============================================================================

class PermissionLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    CLARIFICATION_NEEDED = "clarification_needed"

class TargetAgent(str, Enum):
    DESKTOP = "desktop"
    BROWSER = "browser"
    SYSTEM = "system"
    MEMORY = "memory"
    VOICE = "voice"
    UNKNOWN = "unknown"

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class IntentType(str, Enum):
    # Desktop intents
    OPEN_APP = "open_app"
    CLOSE_APP = "close_app"
    FOCUS_APP = "focus_app"
    LIST_OPEN_APPS = "list_open_apps"
    OPEN_FOLDER = "open_folder"
    SCREENSHOT = "screenshot"
    # Browser intents
    SEARCH_WEB = "search_web"
    BROWSE_WEB = "browse_web"
    NAVIGATE_URL = "navigate_url"
    # Memory intents
    REMEMBER = "remember"
    RECALL = "recall"
    # Voice intents
    SPEAK = "speak"
    TRANSCRIBE = "transcribe"
    # System intents
    SYSTEM_CONTROL = "system_control"
    # Conversational & generic tasks
    CONVERSATION = "conversation"
    # Misc
    UNKNOWN = "unknown"


# ==============================================================================
# Planner Models
# ==============================================================================

class PlannerOutput(BaseModel):
    """Strict Pydantic model representing one structured task produced by the LLM Planner."""
    schema_version: str = Field(..., description="Schema version string, e.g. '1.0'")
    raw_user_input: str = Field(..., description="The exact original user input, always preserved")
    intent: str = Field(..., description="Classified user intent (e.g. open_app, search_web)")
    target_agent: TargetAgent = Field(..., description="Target specialist agent to handle this task")
    action: str = Field(..., description="Atomic action to perform (e.g. open, close, search)")
    target: Optional[str] = Field(None, description="Target resource, app name, URL, or folder")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Extra structured parameters for the action")
    confidence: float = Field(..., description="Planner confidence score between 0.0 and 1.0")
    requires_confirmation: bool = Field(..., description="Whether user confirmation is required before execution")
    risk_level: RiskLevel = Field(..., description="Risk classification: low, medium, or high")
    reasoning_summary: Optional[str] = Field(None, description="Short natural-language summary of planner reasoning")

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {v}")
        return round(v, 4)

    @field_validator("raw_user_input")
    @classmethod
    def raw_input_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("raw_user_input must not be empty")
        return v

    model_config = {"extra": "forbid"}


class PlannerFailure(BaseModel):
    """Returned when the planner cannot produce a valid structured output after all retries."""
    raw_user_input: str = Field(..., description="The original user input that triggered the failure")
    failure_reason: str = Field(..., description="Human-readable reason for planner failure")
    retry_count: int = Field(default=0, description="Number of LLM call attempts made")
    fallback_used: bool = Field(default=False, description="Whether keyword-based fallback was applied")


# ==============================================================================
# Core Task Models
# ==============================================================================

class Task(BaseModel):
    id: str = Field(..., description="Unique task identifier")
    user_input: str = Field(..., description="The original query or prompt typed by the user")
    intent: str = Field(..., description="The classified user intent (e.g. open_app, browse_web)")
    target_agent: str = Field(..., description="The target microservice mapped to handle the intent")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current status of the task")
    permission_level: PermissionLevel = Field(default=PermissionLevel.LOW, description="Determined risk level for this task")
    created_at: str = Field(..., description="ISO 8601 formatted timestamp of creation")
    updated_at: str = Field(..., description="ISO 8601 formatted timestamp of last state transition")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Arbitrary execution logs or outcomes")
    # New optional fields added in Phase 2, Chunk 5 — fully backward compatible
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Structured parameters from planner (e.g. folder name, search query)")
    planner_metadata: Optional[Dict[str, Any]] = Field(default=None, description="Full planner output metadata for observability")


class RoutingRequest(BaseModel):
    user_input: str = Field(..., description="The user query to be routed")

class RoutingResponse(BaseModel):
    task: Task = Field(..., description="The generated and classified task status")
    explanation: str = Field(..., description="Brief details explaining the routing decision")

class ActionResult(BaseModel):
    success: bool = Field(..., description="Whether execution of task completed without errors")
    output: str = Field(..., description="Standard output results of the task")
    error: Optional[str] = Field(None, description="Detailed error description if execution failed")
    match_type: Optional[str] = Field(None, description="Fuzzy/exact/fallback category for application resolution")
    resolved_app: Optional[str] = Field(None, description="The resolved application name or executable path")
    launch_strategy: Optional[str] = Field(None, description="The chosen launching strategy (e.g. URI launch, Direct path launch, Windows Search fallback)")
    verification_status: Optional[str] = Field(None, description="Verification result (e.g. verified_window, window_not_verified, etc.)")

class HealthResponse(BaseModel):
    status: str = Field("healthy", description="Liveness indicator status")
    service: str = Field(..., description="Target service name")
    version: str = Field("1.0.0", description="SemVer version of the microservice")

class ReadinessResponse(BaseModel):
    status: str = Field(..., description="Readiness status ('ready' or 'not_ready')")
    service: str = Field(..., description="Target service name")
    checks: Dict[str, str] = Field(default_factory=dict, description="Status mapping of dependent systems")

class ChatRequest(BaseModel):
    message: str = Field(..., description="The user's query or message")
    session_id: Optional[str] = Field(None, description="Active session ID for conversation tracking")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadata and client context")

class ChatResponse(BaseModel):
    response: str = Field(..., description="The textual response generated by the orchestrator")
    session_id: str = Field(..., description="Active session ID")
    actions_taken: List[Dict[str, Any]] = Field(default_factory=list, description="List of sub-agent or tool calls executed")

class MemoryQueryRequest(BaseModel):
    query: str = Field(..., description="Semantic search query")
    limit: int = Field(default=5, description="Maximum number of context matches")
    filter_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Key-value filters")

class MemoryQueryResponse(BaseModel):
    matches: List[Dict[str, Any]] = Field(default_factory=list, description="Matched documents/memories with scores")

class MemoryStoreRequest(BaseModel):
    content: str = Field(..., description="Text content to persist")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Associated details (source, timestamp, etc.)")

class BrowserSearchResult(BaseModel):
    title: str = Field(..., description="Result page title")
    url: str = Field(..., description="Result page URL")
    snippet: Optional[str] = Field(None, description="Short text excerpt from the result")

class BrowserSearchRequest(BaseModel):
    query: str = Field(..., description="Search query string")
    max_results: int = Field(default=5, description="Maximum number of results to return")

class BrowserSearchResponse(BaseModel):
    query: str = Field(..., description="The original search query")
    results: List[BrowserSearchResult] = Field(default_factory=list, description="Ordered list of search results")
    success: bool = Field(..., description="Whether the search executed without error")
    error: Optional[str] = Field(None, description="Error message if the search failed")

class BrowserActionRequest(BaseModel):
    action: str = Field(..., description="Browser command (e.g., navigate, search, screenshot)")
    url: Optional[str] = Field(None, description="URL for navigation")
    query: Optional[str] = Field(None, description="Search query (used when action='search')")
    selector: Optional[str] = Field(None, description="Target DOM selector")
    payload: Optional[str] = Field(None, description="Input data or text")
    max_results: int = Field(default=5, description="Maximum search results to return (action='search' only)")

class BrowserActionResponse(BaseModel):
    success: bool = Field(..., description="Whether action executed without error")
    screenshot_path: Optional[str] = Field(None, description="Saved screenshot location, if requested")
    extracted_text: Optional[str] = Field(None, description="Page title + visible text excerpt")
    page_title: Optional[str] = Field(None, description="Title of the navigated page")
    search_results: Optional[List[BrowserSearchResult]] = Field(None, description="Structured search results (action='search' only)")
    error: Optional[str] = Field(None, description="Error message if failed")

class VoiceSynthesisRequest(BaseModel):
    text: str = Field(..., description="Text content to speak")
    voice_id: Optional[str] = Field(None, description="ID of voice configuration")

class VoiceSynthesisResponse(BaseModel):
    audio_url: str = Field(..., description="URL or local path to generated WAV/MP3")
    duration: float = Field(..., description="Length of spoken audio in seconds")
