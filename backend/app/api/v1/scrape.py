import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.agents.scraper_agent import ScraperAgent
from app.agents.state import ScrapeState
from app.models.schemas import ScrapeRequest, ScrapeResponse, ScrapeStatus

router = APIRouter(tags=["scrape"])


def _build_response(final_state: ScrapeState) -> ScrapeResponse:
    status = final_state.get("status", ScrapeStatus.FAILED)
    error = None
    if status == ScrapeStatus.FAILED:
        error = {
            "code": final_state.get("error_code") or "UNKNOWN",
            "message": final_state.get("error_message") or "Unknown failure",
        }

    # Extracted records + quality metrics. Falls back to the compressed DOM when no
    # prompt was given (pipeline stops after structuring).
    data = final_state.get("extraction_result")
    if data is None and final_state.get("structured_dom") is not None:
        data = {"structured_dom": final_state["structured_dom"]}

    return ScrapeResponse(
        status=status,
        url=final_state["url"],
        fetch_method=final_state.get("fetch_method"),
        data=data,
        error=error,
        validation=final_state.get("validation_report"),
        execution_log=final_state.get("execution_log", []),
        started_at=final_state.get("started_at"),
        finished_at=final_state.get("finished_at"),
    )


@router.post("/scrape", response_model=ScrapeResponse)
async def scrape(request: Request, payload: ScrapeRequest) -> ScrapeResponse:
    agent: ScraperAgent = request.app.state.agent
    final_state = await agent.run(
        url=str(payload.url),
        prompt=payload.prompt,
        options=payload.options.model_dump(exclude_none=True),
    )
    return _build_response(final_state)


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/scrape/stream")
async def scrape_stream(request: Request, payload: ScrapeRequest) -> StreamingResponse:
    """Same pipeline as /scrape, streaming node-level progress as Server-Sent Events."""
    agent: ScraperAgent = request.app.state.agent

    async def event_generator():
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
            yield _sse("error", {"code": "STREAM_FAILED", "message": str(e)})
            return

        if final_state is not None:
            yield _sse("completed", _build_response(final_state).model_dump(mode="json"))

    return StreamingResponse(event_generator(), media_type="text/event-stream")
