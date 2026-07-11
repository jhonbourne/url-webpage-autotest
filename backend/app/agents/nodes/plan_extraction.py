import logging
from collections.abc import Awaitable, Callable

from app.agents.nodes.common import error_update, log_entry
from app.agents.state import ScrapeState
from app.core.exceptions import PlanningError
from app.models.schemas import ScrapeStatus
from app.services.extraction import ExtractionPlanner

logger = logging.getLogger(__name__)


def make_plan_extraction_node(
    planner: ExtractionPlanner,
) -> Callable[[ScrapeState], Awaitable[ScrapeState]]:
    async def plan_extraction(state: ScrapeState) -> ScrapeState:
        prompt = state.get("prompt")
        if not prompt:
            return error_update("plan_extraction", "NO_PROMPT", "No extraction request provided")

        structured_dom = state.get("structured_dom")
        if not structured_dom:
            return error_update(
                "plan_extraction", "NO_DOM", "No structured DOM available to plan against"
            )

        try:
            plan = await planner.plan(prompt, structured_dom)
        except PlanningError as e:
            return error_update("plan_extraction", e.error_code, e.message)

        if not plan.is_extractable:
            return error_update(
                "plan_extraction",
                "NOT_EXTRACTABLE",
                plan.reason or "The page does not contain the requested data",
            )

        return {
            "extraction_plan": plan.model_dump(),
            "status": ScrapeStatus.EXTRACTING,
            "execution_log": [
                log_entry(
                    "plan_extraction",
                    f"planned {len(plan.fields)} field(s) via {plan.suggested_strategy} strategy",
                    fields=[f.name for f in plan.fields],
                    is_list=plan.is_list,
                    suggested_strategy=plan.suggested_strategy,
                )
            ],
        }

    return plan_extraction
