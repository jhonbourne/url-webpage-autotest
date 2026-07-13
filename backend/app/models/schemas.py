"""API request/response models. Agent-internal state lives in app.agents.state."""

from datetime import datetime
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
    # A run that never reached a terminal state (e.g. the server restarted mid-run);
    # set by the startup sweep so pre-registered rows don't linger as pending.
    INTERRUPTED = "interrupted"


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
    task_id: str | None = None
    status: ScrapeStatus
    url: str
    fetch_method: str | None = None
    # Extracted records + quality metrics, or the DOM summary in structure-only mode
    data: dict[str, Any] | None = None
    # The plan the agent produced, if it got that far — returned even on failure so a
    # failed run still shows what fields were understood and where it stopped.
    plan: dict[str, Any] | None = None
    error: dict[str, str] | None = None
    # Quality report from the reflection loop (row count, coverage, any issues)
    validation: dict[str, Any] | None = None
    # Aggregate LLM token usage: {input_tokens, output_tokens, total_tokens, by_model}
    token_usage: dict[str, Any] | None = None
    execution_log: list[ExecutionLogEntry] = Field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None


class TaskSummary(BaseModel):
    id: str
    url: str
    prompt: str | None
    status: ScrapeStatus
    strategy: str | None
    row_count: int | None
    total_tokens: int | None = None
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None


class TaskListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[TaskSummary]


class TaskDetail(TaskSummary):
    fetch_method: str | None
    error_message: str | None
    input_tokens: int | None = None
    output_tokens: int | None = None
    execution_log: list[ExecutionLogEntry] = Field(default_factory=list)
    # The plan acted on and the selectors applied — for diagnosing a wrong result.
    plan: dict[str, Any] | None = None
    selector_plan: dict[str, Any] | None = None
    fields: list[str] = Field(default_factory=list)
    records: list[dict[str, Any]] = Field(default_factory=list)
    field_coverage: dict[str, float] = Field(default_factory=dict)
    validation: dict[str, Any] | None = None
