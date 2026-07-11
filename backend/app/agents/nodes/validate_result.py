import logging
from collections.abc import Callable

from app.agents.nodes.common import log_entry
from app.agents.state import ScrapeState
from app.services.extraction import ResultValidator

logger = logging.getLogger(__name__)

_ALL_STRATEGIES = {"selector", "llm"}


def make_validate_result_node(
    validator: ResultValidator, max_retries: int
) -> Callable[[ScrapeState], ScrapeState]:
    def validate_result(state: ScrapeState) -> ScrapeState:
        result = state["extraction_result"]
        report = validator.validate(result)

        if report.ok:
            return {
                "validation_report": report.model_dump(),
                "next_strategy": "done",
                "execution_log": [
                    log_entry("validate_result", "validation passed", metrics=report.metrics)
                ],
            }

        # Failed. Decide whether to reflect and retry with the other strategy.
        attempted = set(state.get("attempted_strategies", []))
        remaining = _ALL_STRATEGIES - attempted
        retry_count = state.get("retry_count", 0)
        current = result.get("strategy", "unknown")

        if retry_count < max_retries and remaining:
            next_strategy = "llm" if "llm" in remaining else "selector"
            feedback = (
                f"The '{current}' strategy produced a low-quality result: "
                f"{'; '.join(report.issues)}. Extract more completely."
            )
            logger.info("validation failed, reflecting -> retry via %s", next_strategy)
            return {
                "validation_report": report.model_dump(),
                "retry_count": retry_count + 1,
                "next_strategy": next_strategy,
                "last_failure_feedback": feedback,
                "execution_log": [
                    log_entry(
                        "validate_result",
                        f"validation failed, retrying via {next_strategy} strategy",
                        issues=report.issues,
                        retry_count=retry_count + 1,
                    )
                ],
            }

        # No retries left (or both strategies tried): return best effort.
        logger.info("validation failed, no retries left, returning best-effort result")
        return {
            "validation_report": report.model_dump(),
            "next_strategy": "done",
            "execution_log": [
                log_entry(
                    "validate_result",
                    "validation failed, returning best-effort result",
                    issues=report.issues,
                )
            ],
        }

    return validate_result
