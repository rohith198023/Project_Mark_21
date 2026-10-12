import os
from typing import Dict, Any

class BaseSettings:
    """Base settings loader that extracts values from environment variables."""
    
    @property
    def environment(self) -> str:
        return os.getenv("ENV", "development")

    @property
    def is_debug(self) -> bool:
        return os.getenv("DEBUG", "true").lower() in ("true", "1", "yes")

    @property
    def postgres_uri(self) -> str:
        return os.getenv(
            "DATABASE_URL", 
            "postgresql://jarvis_user:jarvis_secure_pass@postgres:5432/jarvis_db"
        )

    @property
    def qdrant_host(self) -> str:
        return os.getenv("QDRANT_HOST", "qdrant")

    @property
    def qdrant_port(self) -> int:
        return int(os.getenv("QDRANT_PORT", "6333"))

    @property
    def api_port(self) -> int:
        return int(os.getenv("API_PORT", "8000"))

    @property
    def orchestrator_port(self) -> int:
        return int(os.getenv("ORCHESTRATOR_PORT", "8001"))

    @property
    def memory_port(self) -> int:
        return int(os.getenv("MEMORY_PORT", "8002"))

    @property
    def browser_port(self) -> int:
        return int(os.getenv("BROWSER_PORT", "8003"))

    @property
    def voice_port(self) -> int:
        return int(os.getenv("VOICE_PORT", "8004"))

    @property
    def desktop_port(self) -> int:
        return int(os.getenv("DESKTOP_PORT", "8005"))

    # ------------------------------------------------------------------
    # LLM Planner (Groq) configuration
    # ------------------------------------------------------------------

    @property
    def groq_api_key(self) -> str:
        """Groq API key. Required for the LLM Planner layer. Never logged."""
        return os.getenv("GROQ_API_KEY", "")

    @property
    def groq_model(self) -> str:
        """Groq model identifier. Defaults to llama-3.3-70b-versatile."""
        return os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    @property
    def planner_confidence_route_threshold(self) -> float:
        """Minimum confidence for the planner output to be routed normally (default 0.80)."""
        return float(os.getenv("PLANNER_CONFIDENCE_ROUTE", "0.80"))

    @property
    def planner_confidence_clarify_threshold(self) -> float:
        """Minimum confidence to request clarification rather than reject (default 0.50)."""
        return float(os.getenv("PLANNER_CONFIDENCE_CLARIFY", "0.50"))

    def get_service_url(self, service_name: str) -> str:
        """Retrieves base URL for internal services."""
        default_ports = {
            "api": self.api_port,
            "orchestrator": self.orchestrator_port,
            "memory": self.memory_port,
            "browser": self.browser_port,
            "voice": self.voice_port,
            "desktop": self.desktop_port
        }
        port = os.getenv(f"{service_name.upper()}_PORT", str(default_ports.get(service_name, 8000)))
        host = os.getenv(f"{service_name.upper()}_HOST", service_name)
        return f"http://{host}:{port}"

settings = BaseSettings()
