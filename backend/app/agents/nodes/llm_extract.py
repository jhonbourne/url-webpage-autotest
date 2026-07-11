import logging
from collections.abc import Awaitable, Callable

from app.agents.nodes.common import error_update, log_entry
from app.agents.state import ScrapeState
from app.core.exceptions import ExtractionError
from app.models.schemas import ScrapeStatus
from app.services.extraction import LLMExtractor
from app.services.extraction.models import ExtractionPlan
from app.services.extraction.result import build_result

logger = logging.getLogger(__name__)


def make_llm_extract_node(
    extractor: LLMExtractor,
) -> Callable[[ScrapeState], Awaitable[ScrapeState]]:
    async def llm_extract(state: ScrapeState) -> ScrapeState:
        plan = ExtractionPlan.model_validate(state["extraction_plan"])
        structured_dom = state["structured_dom"]

        try:
            records = await extractor.extract(plan, structured_dom)
        except ExtractionError as e:
            return error_update("llm_extract", e.error_code, e.message)

        result = build_result(records, plan, strategy="llm")

        return {
            "extraction_result": result,
            "status": ScrapeStatus.VALIDATING,
            "execution_log": [
                log_entry(
                    "llm_extract",
                    f"extracted {result['row_count']} record(s)",
                    row_count=result["row_count"],
                    field_coverage=result["field_coverage"],
                )
            ],
        }

    return llm_extract
