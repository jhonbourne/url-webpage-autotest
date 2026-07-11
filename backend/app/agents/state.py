import operator
from typing import Annotated, Any, TypedDict

from app.models.schemas import ScrapeStatus


class ScrapeState(TypedDict, total=False):
    # --- input ---
    url: str
    prompt: str | None
    options: dict[str, Any]

    # --- intermediate artifacts ---
    raw_html: str | None
    fetch_method: str | None  # "static" | "browser"
    structured_dom: dict[str, Any] | None
    extraction_plan: dict[str, Any] | None
    selector_plan: dict[str, Any] | None  # only set on the "selector" strategy path
    extraction_result: dict[str, Any] | None

    # --- reflection loop ---
    validation_report: dict[str, Any] | None
    retry_count: int
    # strategies already tried; operator.add so each strategy node appends one
    attempted_strategies: Annotated[list[str], operator.add]
    next_strategy: str | None  # routing decision out of validate_result
    last_failure_feedback: str | None

    # --- control ---
    status: ScrapeStatus
    error_code: str | None
    error_message: str | None

    # --- metadata ---
    # Annotated with operator.add so each node appends by returning a one-item list
    execution_log: Annotated[list[dict[str, Any]], operator.add]
    started_at: str
    finished_at: str | None
