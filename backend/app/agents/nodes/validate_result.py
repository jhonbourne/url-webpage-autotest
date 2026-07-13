import logging
from collections.abc import Awaitable, Callable

from app.agents.nodes.common import log_entry
from app.agents.state import ScrapeState
from app.services.extraction import ResultValidator
from app.services.extraction.cache import SelectorCache, host_of

logger = logging.getLogger(__name__)

_ALL_STRATEGIES = {"selector", "llm"}


async def _maintain_cache(cache: SelectorCache, state: ScrapeState, ok: bool) -> None:
    """Store a selector plan once it validates; drop a cached one that just failed."""
    key = state.get("selector_cache_key")
    result = state.get("extraction_result") or {}
    if not key or result.get("strategy") != "selector":
        return
    if ok:
        plan = state.get("extraction_plan") or {}
        fields = [f["name"] for f in plan.get("fields", [])]
        await cache.put(key, host_of(state["url"]), state.get("prompt"),
                        fields, state.get("selector_plan") or {})
    elif state.get("selector_from_cache"):
        logger.info("cached selector plan failed validation, invalidating %s", key)
        await cache.invalidate(key)


def _score(ok: bool, metrics: dict) -> float:
    """Rank an attempt so the best across strategies can be kept.

    A passing result always beats a failing one; among equals, having records
    beats none, then higher average field coverage wins.
    """
    row_count = metrics.get("row_count", 0)
    return (
        (10.0 if ok else 0.0)
        + (1.0 if row_count > 0 else 0.0)
        + float(metrics.get("avg_coverage", 0.0))
    )


def make_validate_result_node(
    validator: ResultValidator, max_retries: int, cache: SelectorCache | None = None
) -> Callable[[ScrapeState], Awaitable[ScrapeState]]:
    async def validate_result(state: ScrapeState) -> ScrapeState:
        result = state["extraction_result"] or {}
        report = validator.validate(
            result,
            dom_truncated=state.get("dom_truncated", False),
            source_text=state.get("raw_html"),
        )
        score = _score(report.ok, report.metrics)

        # Outcome-driven cache maintenance for the selector-plan reuse cache.
        if cache is not None:
            await _maintain_cache(cache, state, report.ok)

        # Track the best-scoring attempt seen so far, so a retry that comes back
        # worse doesn't discard a better earlier result.
        prev_best = state.get("best_score")
        best: ScrapeState
        if prev_best is None or score > prev_best:
            best = {
                "best_result": result,
                "best_validation": report.model_dump(),
                "best_score": score,
            }
        else:
            best = {
                "best_result": state.get("best_result"),
                "best_validation": state.get("best_validation"),
                "best_score": prev_best,
            }

        if report.ok:
            return {
                "validation_report": report.model_dump(),
                "next_strategy": "done",
                **best,
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
                **best,
                "execution_log": [
                    log_entry(
                        "validate_result",
                        f"validation failed, retrying via {next_strategy} strategy",
                        issues=report.issues,
                        retry_count=retry_count + 1,
                    )
                ],
            }

        # No retries left (or both strategies tried): return the best attempt seen,
        # which may be an earlier one if this final retry regressed.
        logger.info("validation failed, no retries left, returning best-effort result")
        return {
            "validation_report": best["best_validation"],
            "extraction_result": best["best_result"],
            "next_strategy": "done",
            **best,
            "execution_log": [
                log_entry(
                    "validate_result",
                    "validation failed, returning best-effort result",
                    issues=report.issues,
                )
            ],
        }

    return validate_result
