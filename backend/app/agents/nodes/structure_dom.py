import json
import logging
from collections.abc import Callable

from app.agents.nodes.common import error_update, log_entry
from app.agents.state import ScrapeState
from app.models.schemas import ScrapeStatus
from app.services.dom_service import DOMService

logger = logging.getLogger(__name__)


def make_structure_dom_node(
    dom_service: DOMService, char_budget: int = 12000
) -> Callable[[ScrapeState], ScrapeState]:
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
        # Single source of truth for truncation: the extractors slice the same
        # serialised DOM at char_budget, so compare against it here once.
        dom_chars = len(json.dumps(structured, ensure_ascii=False))
        dom_truncated = dom_chars > char_budget
        if dom_truncated:
            logger.warning("DOM %d chars exceeds budget %d; model sees a truncated view",
                           dom_chars, char_budget)
        logger.info("structured DOM: %d nodes kept", node_count)
        return {
            "structured_dom": structured,
            "dom_truncated": dom_truncated,
            "status": ScrapeStatus.PLANNING,
            "execution_log": [
                log_entry(
                    "structure_dom",
                    "DOM structured and compressed",
                    node_count=node_count,
                    dom_chars=dom_chars,
                    truncated=dom_truncated,
                )
            ],
        }

    return structure_dom
