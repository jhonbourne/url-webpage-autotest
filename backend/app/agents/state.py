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
    # P1: extraction_plan, extraction_result, validation_report

    # --- control ---
    status: ScrapeStatus
    error_code: str | None
    error_message: str | None

    # --- metadata ---
    # Annotated with operator.add so each node appends by returning a one-item list
    execution_log: Annotated[list[dict[str, Any]], operator.add]
    started_at: str
    finished_at: str | None
