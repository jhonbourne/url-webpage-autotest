import logging
from collections.abc import Awaitable, Callable

from app.agents.nodes.common import error_update, log_entry
from app.agents.state import ScrapeState
from app.core.exceptions import FetchError
from app.models.schemas import ScrapeStatus
from app.services.fetch_service import FetchService

logger = logging.getLogger(__name__)


def make_fetch_page_node(
    fetch_service: FetchService,
) -> Callable[[ScrapeState], Awaitable[ScrapeState]]:
    async def fetch_page(state: ScrapeState) -> ScrapeState:
        url = state["url"]
        options = state.get("options") or {}
        try:
            result = await fetch_service.fetch(
                url,
                wait_for_selector=options.get("wait_for_selector"),
                timeout_ms=options.get("timeout_ms"),
                force_browser=options.get("force_browser", False),
            )
        except FetchError as e:
            return error_update("fetch_page", e.error_code, e.message)

        logger.info("fetched %s via %s (%d bytes)", url, result.method, len(result.html))
        return {
            "raw_html": result.html,
            "fetch_method": result.method,
            "status": ScrapeStatus.PARSING,
            "execution_log": [
                log_entry(
                    "fetch_page",
                    f"fetched via {result.method}",
                    final_url=result.final_url,
                    html_bytes=len(result.html),
                )
            ],
        }

    return fetch_page
