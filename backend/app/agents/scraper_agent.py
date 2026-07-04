"""LangGraph workflow for agent-driven webpage content extraction.

P0 graph: fetch_page -> structure_dom -> END (plus error routing).
P1 adds:  plan_extraction -> choose_strategy -> {gen_selectors|llm_extract}
          -> execute -> validate_result (with retry loop back to choose_strategy).
"""

from datetime import UTC, datetime
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from app.agents.nodes import make_fetch_page_node, make_structure_dom_node
from app.agents.state import ScrapeState
from app.models.schemas import ScrapeStatus
from app.services.dom_service import DOMService
from app.services.fetch_service import FetchService


class ScraperAgent:
    def __init__(self, fetch_service: FetchService, dom_service: DOMService):
        self._fetch_service = fetch_service
        self._dom_service = dom_service
        self._graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(ScrapeState)

        workflow.add_node("fetch_page", make_fetch_page_node(self._fetch_service))
        workflow.add_node("structure_dom", make_structure_dom_node(self._dom_service))
        workflow.add_node("finalize", self._finalize)
        workflow.add_node("handle_error", self._handle_error)

        workflow.set_entry_point("fetch_page")
        workflow.add_conditional_edges(
            "fetch_page", self._route, {"continue": "structure_dom", "error": "handle_error"}
        )
        workflow.add_conditional_edges(
            "structure_dom", self._route, {"continue": "finalize", "error": "handle_error"}
        )
        workflow.add_edge("finalize", END)
        workflow.add_edge("handle_error", END)

        return workflow.compile()

    @staticmethod
    def _route(state: ScrapeState) -> Literal["continue", "error"]:
        return "error" if state.get("status") == ScrapeStatus.FAILED else "continue"

    @staticmethod
    def _finalize(state: ScrapeState) -> ScrapeState:
        return {
            "status": ScrapeStatus.COMPLETED,
            "finished_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _handle_error(state: ScrapeState) -> ScrapeState:
        return {"finished_at": datetime.now(UTC).isoformat()}

    async def run(
        self, url: str, prompt: str | None = None, options: dict[str, Any] | None = None
    ) -> ScrapeState:
        initial: ScrapeState = {
            "url": url,
            "prompt": prompt,
            "options": options or {},
            "status": ScrapeStatus.FETCHING,
            "execution_log": [],
            "started_at": datetime.now(UTC).isoformat(),
        }
        return await self._graph.ainvoke(initial)
