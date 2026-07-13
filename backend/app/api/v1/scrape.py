import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.agents.scraper_agent import ScraperAgent
from app.agents.state import ScrapeState
from app.models.schemas import ExecutionLogEntry, ScrapeRequest, ScrapeResponse, ScrapeStatus

logger = logging.getLogger(__name__)
router = APIRouter(tags=["scrape"])


def _build_response(final_state: ScrapeState, task_id: str | None = None) -> ScrapeResponse:
    status = final_state.get("status", ScrapeStatus.FAILED)
    error = None
    if status == ScrapeStatus.FAILED:
        error = {
            "code": final_state.get("error_code") or "UNKNOWN",
            "message": final_state.get("error_message") or "Unknown failure",
        }

    # Extracted records + quality metrics. Falls back to the compressed DOM when no
    # prompt was given, or on failure — so a failed run still returns partial output
    # (the plan below, plus whatever structure was recovered) rather than nothing.
    data = final_state.get("extraction_result")
    if data is None and final_state.get("structured_dom") is not None:
        data = {"structured_dom": final_state["structured_dom"]}

    return ScrapeResponse(
        task_id=task_id,
        status=status,
        url=final_state["url"],
        fetch_method=final_state.get("fetch_method"),
        data=data,
        plan=final_state.get("extraction_plan"),
        error=error,
        validation=final_state.get("validation_report"),
        token_usage=final_state.get("token_usage"),
        execution_log=[ExecutionLogEntry(**e) for e in final_state.get("execution_log", [])],
        started_at=final_state.get("started_at"),
        finished_at=final_state.get("finished_at"),
    )


async def _finalize(request: Request, task_id: str, final_state: ScrapeState) -> None:
    """Update the pre-registered task with its final state and (optionally) push
    result records to the external sink."""
    await request.app.state.task_repo.save_from_state(task_id, final_state)

    result = final_state.get("extraction_result") or {}
    records = result.get("records")
    if records:
        try:
            await request.app.state.result_sink.write(task_id, final_state["url"], records)
        except Exception:  # noqa: BLE001 - external sink is best-effort; local store is authoritative
            logger.exception("external result sink failed for task %s", task_id)


async def _mark_failed(
    request: Request, task_id: str, payload: ScrapeRequest, exc: Exception
) -> None:
    """Record an unexpected crash so the pre-registered row doesn't linger as pending."""
    await request.app.state.task_repo.save_from_state(
        task_id,
        {
            "url": str(payload.url),
            "prompt": payload.prompt,
            "status": ScrapeStatus.FAILED,
            "error_code": "INTERNAL_ERROR",
            "error_message": str(exc),
            "execution_log": [],
            "finished_at": datetime.now(UTC).isoformat(),
        },
    )


@router.post("/scrape", response_model=ScrapeResponse)
async def scrape(request: Request, payload: ScrapeRequest) -> ScrapeResponse:
    agent: ScraperAgent = request.app.state.agent
    task_id = uuid.uuid4().hex
    await request.app.state.task_repo.create_running(task_id, str(payload.url), payload.prompt)
    try:
        final_state = await agent.run(
            url=str(payload.url),
            prompt=payload.prompt,
            options=payload.options.model_dump(exclude_none=True),
        )
    except Exception as exc:
        await _mark_failed(request, task_id, payload, exc)
        raise
    await _finalize(request, task_id, final_state)
    return _build_response(final_state, task_id)


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/scrape/stream")
async def scrape_stream(request: Request, payload: ScrapeRequest) -> StreamingResponse:
    """Same pipeline as /scrape, streaming node-level progress as Server-Sent Events."""
    agent: ScraperAgent = request.app.state.agent
    task_id = uuid.uuid4().hex
    await request.app.state.task_repo.create_running(task_id, str(payload.url), payload.prompt)

    async def event_generator():
        # Hand the client its task id up front so a dropped connection can still be
        # reconciled against history. (Unknown events are ignored by the client.)
        yield _sse("started", {"task_id": task_id})
        emitted_logs = 0
        final_state: ScrapeState | None = None
        try:
            async for state in agent.astream_run(
                url=str(payload.url),
                prompt=payload.prompt,
                options=payload.options.model_dump(exclude_none=True),
            ):
                final_state = state
                # Emit each newly-appended execution-log entry as a progress event.
                logs = state.get("execution_log", [])
                for entry in logs[emitted_logs:]:
                    yield _sse("progress", {"status": state.get("status"), **entry})
                emitted_logs = len(logs)
        except Exception as e:  # noqa: BLE001 - surface any failure to the client
            await _mark_failed(request, task_id, payload, e)
            yield _sse("error", {"code": "STREAM_FAILED", "message": str(e)})
            return

        if final_state is not None:
            await _finalize(request, task_id, final_state)
            yield _sse("completed", _build_response(final_state, task_id).model_dump(mode="json"))

    return StreamingResponse(event_generator(), media_type="text/event-stream")
