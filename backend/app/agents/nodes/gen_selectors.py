import logging
from collections.abc import Awaitable, Callable

from app.agents.nodes.common import error_update, log_entry
from app.agents.state import ScrapeState
from app.core.exceptions import ExtractionError
from app.services.extraction import SelectorGenerator
from app.services.extraction.models import ExtractionPlan

logger = logging.getLogger(__name__)


def make_gen_selectors_node(
    generator: SelectorGenerator,
) -> Callable[[ScrapeState], Awaitable[ScrapeState]]:
    async def gen_selectors(state: ScrapeState) -> ScrapeState:
        plan = ExtractionPlan.model_validate(state["extraction_plan"])
        structured_dom = state["structured_dom"] or {}

        try:
            selector_plan = await generator.generate(
                plan, structured_dom, feedback=state.get("last_failure_feedback")
            )
        except ExtractionError as e:
            return error_update("gen_selectors", e.error_code, e.message)

        return {
            "selector_plan": selector_plan.model_dump(),
            "execution_log": [
                log_entry(
                    "gen_selectors",
                    f"generated selectors for {len(selector_plan.fields)} field(s)",
                    record_selector=selector_plan.record_selector,
                )
            ],
        }

    return gen_selectors
