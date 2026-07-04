from fastapi import APIRouter, Request

from app.agents.scraper_agent import ScraperAgent
from app.models.schemas import ScrapeRequest, ScrapeResponse, ScrapeStatus

router = APIRouter(tags=["scrape"])


@router.post("/scrape", response_model=ScrapeResponse)
async def scrape(request: Request, payload: ScrapeRequest) -> ScrapeResponse:
    agent: ScraperAgent = request.app.state.agent

    final_state = await agent.run(
        url=str(payload.url),
        prompt=payload.prompt,
        options=payload.options.model_dump(exclude_none=True),
    )

    status = final_state.get("status", ScrapeStatus.FAILED)
    error = None
    if status == ScrapeStatus.FAILED:
        error = {
            "code": final_state.get("error_code") or "UNKNOWN",
            "message": final_state.get("error_message") or "Unknown failure",
        }

    data = None
    if final_state.get("structured_dom") is not None:
        # P0 payload: the compressed DOM tree. P1 replaces this with extracted records.
        data = {"structured_dom": final_state["structured_dom"]}

    return ScrapeResponse(
        status=status,
        url=final_state["url"],
        fetch_method=final_state.get("fetch_method"),
        data=data,
        error=error,
        execution_log=final_state.get("execution_log", []),
        started_at=final_state.get("started_at"),
        finished_at=final_state.get("finished_at"),
    )
