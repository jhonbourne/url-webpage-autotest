from datetime import UTC, datetime
from typing import Any

from app.agents.state import ScrapeState
from app.models.schemas import ScrapeStatus


def log_entry(step: str, message: str, **detail: Any) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "step": step,
        "message": message,
        "detail": detail,
    }


def error_update(step: str, code: str, message: str) -> ScrapeState:
    """Partial state update that routes the graph to the error handler."""
    return {
        "status": ScrapeStatus.FAILED,
        "error_code": code,
        "error_message": message,
        "execution_log": [log_entry(step, f"failed: {message}", error_code=code)],
    }
