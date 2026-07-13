import logging
from collections.abc import Awaitable, Callable

from app.agents.nodes.common import error_update, log_entry
from app.agents.state import ScrapeState
from app.core.exceptions import ExtractionError
from app.services.extraction import SelectorGenerator
from app.services.extraction.cache import SelectorCache, selector_cache_key
from app.services.extraction.models import ExtractionPlan

logger = logging.getLogger(__name__)


def make_gen_selectors_node(
    generator: SelectorGenerator,
    cache: SelectorCache | None = None,
) -> Callable[[ScrapeState], Awaitable[ScrapeState]]:
    async def gen_selectors(state: ScrapeState) -> ScrapeState:
        plan = ExtractionPlan.model_validate(state["extraction_plan"])
        structured_dom = state["structured_dom"] or {}

        key = selector_cache_key(state["url"], state.get("prompt"), [f.name for f in plan.fields])
        feedback = state.get("last_failure_feedback")

        # Reuse a validated plan on a cache hit — but not on a reflection retry, where
        # the whole point is to produce something different from the failed attempt.
        if cache is not None and not feedback:
            cached = await cache.get(key)
            if cached is not None:
                logger.info("reusing cached selector plan for %s", key)
                return {
                    "selector_plan": cached,
                    "selector_cache_key": key,
                    "selector_from_cache": True,
                    "execution_log": [
                        log_entry("gen_selectors", "reused cached selector plan", cache_key=key)
                    ],
                }

        try:
            selector_plan = await generator.generate(plan, structured_dom, feedback=feedback)
        except ExtractionError as e:
            return error_update("gen_selectors", e.error_code, e.message)

        return {
            "selector_plan": selector_plan.model_dump(),
            "selector_cache_key": key,
            "selector_from_cache": False,
            "execution_log": [
                log_entry(
                    "gen_selectors",
                    f"generated selectors for {len(selector_plan.fields)} field(s)",
                    record_selector=selector_plan.record_selector,
                )
            ],
        }

    return gen_selectors
