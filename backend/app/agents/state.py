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
    # True when the serialised DOM exceeds the prompt char budget, so the model saw
    # only a truncated view. Surfaced as an advisory warning on the result.
    dom_truncated: bool
    extraction_plan: dict[str, Any] | None
    selector_plan: dict[str, Any] | None  # only set on the "selector" strategy path
    # Selector-plan reuse cache bookkeeping (see services.extraction.cache).
    selector_cache_key: str | None
    selector_from_cache: bool
    extraction_result: dict[str, Any] | None

    # --- reflection loop ---
    validation_report: dict[str, Any] | None
    retry_count: int
    # strategies already tried; operator.add so each strategy node appends one
    attempted_strategies: Annotated[list[str], operator.add]
    next_strategy: str | None  # routing decision out of validate_result
    last_failure_feedback: str | None
    # Best result seen across reflection attempts, so a retry that regresses does not
    # throw away a better earlier attempt. best_score ranks them (see validate_result).
    best_result: dict[str, Any] | None
    best_validation: dict[str, Any] | None
    best_score: float | None

    # --- control ---
    status: ScrapeStatus
    error_code: str | None
    error_message: str | None

    # --- metadata ---
    # Annotated with operator.add so each node appends by returning a one-item list
    execution_log: Annotated[list[dict[str, Any]], operator.add]
    # Aggregate LLM token usage for the run, attached at the agent boundary (not by
    # nodes): {input_tokens, output_tokens, total_tokens, by_model}.
    token_usage: dict[str, Any] | None
    started_at: str
    finished_at: str | None
