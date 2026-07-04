import logging
from collections.abc import Callable

from app.agents.nodes.common import error_update, log_entry
from app.agents.state import ScrapeState
from app.models.schemas import ScrapeStatus
from app.services.dom_service import DOMService

logger = logging.getLogger(__name__)


def make_structure_dom_node(dom_service: DOMService) -> Callable[[ScrapeState], ScrapeState]:
    def structure_dom(state: ScrapeState) -> ScrapeState:
        raw_html = state.get("raw_html")
        if not raw_html:
            return error_update("structure_dom", "NO_HTML", "No HTML available to parse")

        structured = dom_service.extract_structure(raw_html)
        if not structured:
            return error_update(
                "structure_dom", "PARSE_FAILED", "Could not find a <body> element in the page"
            )

        node_count = dom_service.count_nodes(structured)
        logger.info("structured DOM: %d nodes kept", node_count)
        return {
            "structured_dom": structured,
            "status": ScrapeStatus.PLANNING,
            "execution_log": [
                log_entry("structure_dom", "DOM structured and compressed", node_count=node_count)
            ],
        }

    return structure_dom
