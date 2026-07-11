import logging
from collections.abc import Callable

from app.agents.nodes.common import log_entry
from app.agents.state import ScrapeState
from app.models.schemas import ScrapeStatus
from app.services.extraction import SelectorExecutor
from app.services.extraction.models import ExtractionPlan, SelectorPlan
from app.services.extraction.result import build_result

logger = logging.getLogger(__name__)


def make_execute_selectors_node(
    executor: SelectorExecutor,
) -> Callable[[ScrapeState], ScrapeState]:
    def execute_selectors(state: ScrapeState) -> ScrapeState:
        plan = ExtractionPlan.model_validate(state["extraction_plan"])
        selector_plan = SelectorPlan.model_validate(state["selector_plan"])
        html = state["raw_html"]

        records = executor.execute(html, selector_plan, plan.is_list)
        result = build_result(records, plan, strategy="selector")

        return {
            "extraction_result": result,
            "attempted_strategies": ["selector"],
            "status": ScrapeStatus.VALIDATING,
            "execution_log": [
                log_entry(
                    "execute_selectors",
                    f"extracted {result['row_count']} record(s)",
                    row_count=result["row_count"],
                    field_coverage=result["field_coverage"],
                )
            ],
        }

    return execute_selectors
