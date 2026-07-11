"""LangGraph workflow for agent-driven webpage content extraction.

P1 graph:
    fetch_page -> structure_dom -> plan_extraction -> route_strategy
      -> {gen_selectors -> execute_selectors | llm_extract} -> finalize
    (plus error routing to handle_error)

route_strategy is a deterministic read of the plan's suggested_strategy. P2 upgrades
it to an LLM-driven decision edge and adds validate_result with a reflection retry loop.
"""

from datetime import UTC, datetime
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from app.agents.nodes import (
    make_execute_selectors_node,
    make_fetch_page_node,
    make_gen_selectors_node,
    make_llm_extract_node,
    make_plan_extraction_node,
    make_structure_dom_node,
)
from app.agents.state import ScrapeState
from app.models.schemas import ScrapeStatus
from app.services.dom_service import DOMService
from app.services.extraction import (
    ExtractionPlanner,
    LLMExtractor,
    SelectorExecutor,
    SelectorGenerator,
)
from app.services.fetch_service import FetchService


class ScraperAgent:
    def __init__(
        self,
        fetch_service: FetchService,
        dom_service: DOMService,
        planner: ExtractionPlanner,
        selector_generator: SelectorGenerator,
        selector_executor: SelectorExecutor,
        llm_extractor: LLMExtractor,
    ):
        self._fetch_service = fetch_service
        self._dom_service = dom_service
        self._planner = planner
        self._selector_generator = selector_generator
        self._selector_executor = selector_executor
        self._llm_extractor = llm_extractor
        self._graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(ScrapeState)

        workflow.add_node("fetch_page", make_fetch_page_node(self._fetch_service))
        workflow.add_node("structure_dom", make_structure_dom_node(self._dom_service))
        workflow.add_node("plan_extraction", make_plan_extraction_node(self._planner))
        workflow.add_node("gen_selectors", make_gen_selectors_node(self._selector_generator))
        workflow.add_node("execute_selectors", make_execute_selectors_node(self._selector_executor))
        workflow.add_node("llm_extract", make_llm_extract_node(self._llm_extractor))
        workflow.add_node("finalize", self._finalize)
        workflow.add_node("handle_error", self._handle_error)

        workflow.set_entry_point("fetch_page")
        workflow.add_conditional_edges(
            "fetch_page", self._route, {"continue": "structure_dom", "error": "handle_error"}
        )
        workflow.add_conditional_edges(
            "structure_dom",
            self._route_after_structure,
            {"plan": "plan_extraction", "skip": "finalize", "error": "handle_error"},
        )
        workflow.add_conditional_edges(
            "plan_extraction",
            self._route_strategy,
            {"selector": "gen_selectors", "llm": "llm_extract", "error": "handle_error"},
        )
        workflow.add_conditional_edges(
            "gen_selectors",
            self._route,
            {"continue": "execute_selectors", "error": "handle_error"},
        )
        workflow.add_edge("execute_selectors", "finalize")
        workflow.add_conditional_edges(
            "llm_extract", self._route, {"continue": "finalize", "error": "handle_error"}
        )
        workflow.add_edge("finalize", END)
        workflow.add_edge("handle_error", END)

        return workflow.compile()

    @staticmethod
    def _route(state: ScrapeState) -> Literal["continue", "error"]:
        return "error" if state.get("status") == ScrapeStatus.FAILED else "continue"

    @staticmethod
    def _route_after_structure(state: ScrapeState) -> Literal["plan", "skip", "error"]:
        if state.get("status") == ScrapeStatus.FAILED:
            return "error"
        # No prompt => structure-only mode (no LLM spend), stop after structuring.
        return "plan" if state.get("prompt") else "skip"

    @staticmethod
    def _route_strategy(state: ScrapeState) -> Literal["selector", "llm", "error"]:
        if state.get("status") == ScrapeStatus.FAILED:
            return "error"
        plan = state.get("extraction_plan") or {}
        return "selector" if plan.get("suggested_strategy") == "selector" else "llm"

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
