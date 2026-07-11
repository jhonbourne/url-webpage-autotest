"""API request/response models. Agent-internal state lives in app.agents.state."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class ScrapeStatus(StrEnum):
    PENDING = "pending"
    FETCHING = "fetching"
    PARSING = "parsing"
    PLANNING = "planning"
    EXTRACTING = "extracting"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"


class ScrapeOptions(BaseModel):
    wait_for_selector: str | None = Field(
        default=None, description="CSS selector to await before reading the page"
    )
    timeout_ms: int | None = Field(default=None, ge=1000, le=120000)
    force_browser: bool = Field(
        default=False,
        description="Skip the static-fetch fast path and always render with a browser",
    )


class ScrapeRequest(BaseModel):
    url: HttpUrl
    # What to extract, in natural language. Optional until the planning node
    # lands (P1); without it the pipeline stops after DOM structuring.
    prompt: str | None = Field(default=None, max_length=4000)
    options: ScrapeOptions = Field(default_factory=ScrapeOptions)


class ExecutionLogEntry(BaseModel):
    timestamp: str
    step: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ScrapeResponse(BaseModel):
    status: ScrapeStatus
    url: str
    fetch_method: str | None = None
    # Extracted records + quality metrics, or the DOM summary in structure-only mode
    data: dict[str, Any] | None = None
    error: dict[str, str] | None = None
    # Quality report from the reflection loop (row count, coverage, any issues)
    validation: dict[str, Any] | None = None
    execution_log: list[ExecutionLogEntry] = Field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
