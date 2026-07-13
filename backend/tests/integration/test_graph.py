"""Full-graph runs with fake LLM services + the real executor and DOM parser.

Verifies routing (selector vs llm strategy, structure-only, error) without network
or LLM credits. The selector path exercises the real controlled executor end-to-end.
"""

import pytest

from app.agents.scraper_agent import ScraperAgent
from app.models.schemas import ScrapeStatus
from app.services.dom_service import DOMService
from app.services.extraction import ResultValidator
from app.services.extraction.executor import SelectorExecutor
from app.services.extraction.models import (
    ExtractionPlan,
    FieldSelector,
    FieldSpec,
    SelectorPlan,
)
from app.services.fetch_service import FetchResult


class FakeFetchService:
    def __init__(self, html: str):
        self._html = html

    async def fetch(self, url, **_kwargs):
        return FetchResult(html=self._html, final_url=url, method="static")


class FakePlanner:
    def __init__(self, plan: ExtractionPlan):
        self._plan = plan

    async def plan(self, _prompt, _dom):
        return self._plan


class FakeSelectorGenerator:
    def __init__(self, selector_plan: SelectorPlan):
        self._selector_plan = selector_plan
        self.feedback_seen: list[str | None] = []

    async def generate(self, _plan, _dom, feedback=None):
        self.feedback_seen.append(feedback)
        return self._selector_plan


class FakeLLMExtractor:
    def __init__(self, records):
        self._records = records
        self.feedback_seen: list[str | None] = []

    async def extract(self, _plan, _dom, feedback=None):
        self.feedback_seen.append(feedback)
        return self._records


class FakeSelectorCache:
    def __init__(self, initial=None):
        self.store = dict(initial or {})

    async def get(self, key):
        return self.store.get(key)

    async def put(self, key, host, prompt, fields, selector_plan):
        self.store[key] = selector_plan

    async def invalidate(self, key):
        self.store.pop(key, None)


def _agent(
    html,
    *,
    plan,
    selector_plan=None,
    llm_records=None,
    selector_generator=None,
    llm_extractor=None,
    max_retries=2,
    dom_char_budget=12000,
    selector_cache=None,
):
    return ScraperAgent(
        fetch_service=FakeFetchService(html),
        dom_service=DOMService(),
        planner=FakePlanner(plan),
        selector_generator=(
            selector_generator or FakeSelectorGenerator(selector_plan or SelectorPlan())
        ),
        selector_executor=SelectorExecutor(),
        llm_extractor=llm_extractor or FakeLLMExtractor(llm_records or []),
        validator=ResultValidator(min_field_coverage=0.5),
        max_retries=max_retries,
        dom_char_budget=dom_char_budget,
        selector_cache=selector_cache,
    )


PRODUCT_FIELDS = [
    FieldSpec(name="name", description="product name"),
    FieldSpec(name="price", description="price"),
]


@pytest.mark.asyncio
async def test_selector_strategy_end_to_end(products_html: str):
    plan = ExtractionPlan(
        is_extractable=True, is_list=True, fields=PRODUCT_FIELDS, suggested_strategy="selector"
    )
    selector_plan = SelectorPlan(
        record_selector="li.product",
        fields={
            "name": FieldSelector(selector="a.name", attr="text"),
            "price": FieldSelector(selector="span.price", attr="text"),
        },
    )
    agent = _agent(products_html, plan=plan, selector_plan=selector_plan)

    state = await agent.run("get product names and prices", prompt="get names and prices")

    assert state["status"] == ScrapeStatus.COMPLETED
    result = state["extraction_result"]
    assert result["strategy"] == "selector"
    assert result["row_count"] == 3
    assert result["records"][0] == {"name": "Wireless Mouse", "price": "29.90"}
    assert result["field_coverage"]["name"] == 1.0


@pytest.mark.asyncio
async def test_llm_strategy_end_to_end(products_html: str):
    plan = ExtractionPlan(
        is_extractable=True, is_list=True, fields=PRODUCT_FIELDS, suggested_strategy="llm"
    )
    records = [{"name": "Wireless Mouse", "price": "29.90"}]
    agent = _agent(products_html, plan=plan, llm_records=records)

    state = await agent.run("x", prompt="get names and prices")

    assert state["status"] == ScrapeStatus.COMPLETED
    assert state["extraction_result"]["strategy"] == "llm"
    assert state["extraction_result"]["row_count"] == 1
    # Token usage is attached at the agent boundary (zeros here: fakes emit no usage).
    assert set(state["token_usage"]) == {
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "by_model",
    }


@pytest.mark.asyncio
async def test_not_extractable_routes_to_error(products_html: str):
    plan = ExtractionPlan(is_extractable=False, reason="no such data here", fields=[])
    agent = _agent(products_html, plan=plan)

    state = await agent.run("x", prompt="get the stock ticker")

    assert state["status"] == ScrapeStatus.FAILED
    assert state["error_code"] == "NOT_EXTRACTABLE"


@pytest.mark.asyncio
async def test_structure_only_mode_without_prompt(products_html: str):
    plan = ExtractionPlan(is_extractable=True, fields=PRODUCT_FIELDS)
    agent = _agent(products_html, plan=plan)

    state = await agent.run("x", prompt=None)

    assert state["status"] == ScrapeStatus.COMPLETED
    assert state.get("extraction_result") is None
    assert state["structured_dom"]["tag"] == "body"


# --- P2: reflection loop, strategy fallback, SSE ---


@pytest.mark.asyncio
async def test_selector_failure_reflects_and_falls_back_to_llm(products_html: str):
    """A selector plan that extracts nothing should trigger a fallback to LLM."""
    plan = ExtractionPlan(
        is_extractable=True, is_list=True, fields=PRODUCT_FIELDS, suggested_strategy="selector"
    )
    # Selectors match no records -> validation fails (row_count 0)
    broken_selectors = SelectorPlan(
        record_selector="div.does-not-exist",
        fields={"name": FieldSelector(selector="a.name", attr="text")},
    )
    good_records = [{"name": "Wireless Mouse", "price": "29.90"}]
    llm_extractor = FakeLLMExtractor(good_records)
    agent = _agent(
        products_html,
        plan=plan,
        selector_plan=broken_selectors,
        llm_extractor=llm_extractor,
    )

    state = await agent.run("x", prompt="get names and prices")

    assert state["status"] == ScrapeStatus.COMPLETED
    assert state["extraction_result"]["strategy"] == "llm"  # fell back
    assert state["validation_report"]["ok"] is True
    assert state["retry_count"] == 1
    assert set(state["attempted_strategies"]) == {"selector", "llm"}
    # The reflection carried failure feedback into the LLM extractor
    assert any(fb for fb in llm_extractor.feedback_seen)


@pytest.mark.asyncio
async def test_best_effort_when_all_strategies_fail(products_html: str):
    plan = ExtractionPlan(
        is_extractable=True, is_list=True, fields=PRODUCT_FIELDS, suggested_strategy="selector"
    )
    broken_selectors = SelectorPlan(
        record_selector="div.nope", fields={"name": FieldSelector(selector="x", attr="text")}
    )
    agent = _agent(
        products_html,
        plan=plan,
        selector_plan=broken_selectors,
        llm_records=[],  # llm also yields nothing
    )

    state = await agent.run("x", prompt="get names and prices")

    # Completes with a best-effort (empty) result and a failing validation report
    assert state["status"] == ScrapeStatus.COMPLETED
    assert state["validation_report"]["ok"] is False
    assert state["extraction_result"]["row_count"] == 0
    assert set(state["attempted_strategies"]) == {"selector", "llm"}


@pytest.mark.asyncio
async def test_dom_truncation_surfaces_as_warning(products_html: str):
    """A page over the char budget completes, but flags the result as possibly incomplete."""
    plan = ExtractionPlan(
        is_extractable=True, is_list=True, fields=PRODUCT_FIELDS, suggested_strategy="llm"
    )
    agent = _agent(
        products_html,
        plan=plan,
        llm_records=[{"name": "Wireless Mouse", "price": "29.90"}],
        dom_char_budget=1,  # force truncation
    )

    state = await agent.run("x", prompt="get names and prices")

    assert state["status"] == ScrapeStatus.COMPLETED
    assert state["dom_truncated"] is True
    report = state["validation_report"]
    assert report["ok"] is True  # truncation is advisory, not a failure
    assert any("truncated" in w for w in report["warnings"])


@pytest.mark.asyncio
async def test_keeps_best_attempt_when_retry_regresses(products_html: str):
    """A failing-but-partial first attempt must not be discarded by a worse retry."""
    plan = ExtractionPlan(
        is_extractable=True, is_list=True, fields=PRODUCT_FIELDS, suggested_strategy="selector"
    )
    # Selector finds the 3 records and names, but never the price -> fails validation
    # (price coverage 0), yet is clearly better than the empty LLM fallback below.
    partial_selectors = SelectorPlan(
        record_selector="li.product",
        fields={
            "name": FieldSelector(selector="a.name", attr="text"),
            "price": FieldSelector(selector="span.does-not-exist", attr="text"),
        },
    )
    agent = _agent(
        products_html,
        plan=plan,
        selector_plan=partial_selectors,
        llm_records=[],  # retry regresses to nothing
    )

    state = await agent.run("x", prompt="get names and prices")

    assert state["status"] == ScrapeStatus.COMPLETED
    assert state["validation_report"]["ok"] is False
    # Best-effort returns the stronger selector attempt, not the empty retry.
    assert state["extraction_result"]["strategy"] == "selector"
    assert state["extraction_result"]["row_count"] == 3
    assert set(state["attempted_strategies"]) == {"selector", "llm"}


@pytest.mark.asyncio
async def test_llm_hallucination_reflects_to_selector(products_html: str):
    """LLM records absent from the page are flagged and the agent falls back to selectors."""
    plan = ExtractionPlan(
        is_extractable=True, is_list=True, fields=PRODUCT_FIELDS, suggested_strategy="llm"
    )
    hallucinated = [{"name": f"Fake Item {i}", "price": "0.00"} for i in range(5)]
    good_selectors = SelectorPlan(
        record_selector="li.product",
        fields={
            "name": FieldSelector(selector="a.name", attr="text"),
            "price": FieldSelector(selector="span.price", attr="text"),
        },
    )
    agent = _agent(
        products_html, plan=plan, llm_records=hallucinated, selector_plan=good_selectors
    )

    state = await agent.run("x", prompt="get names and prices")

    assert state["status"] == ScrapeStatus.COMPLETED
    assert state["retry_count"] == 1
    assert state["extraction_result"]["strategy"] == "selector"  # fell back after flagging
    assert set(state["attempted_strategies"]) == {"llm", "selector"}


@pytest.mark.asyncio
async def test_selector_cache_stores_then_reuses(products_html: str):
    """A validated selector plan is cached, and a second run reuses it without the LLM."""
    plan = ExtractionPlan(
        is_extractable=True, is_list=True, fields=PRODUCT_FIELDS, suggested_strategy="selector"
    )
    selector_plan = SelectorPlan(
        record_selector="li.product",
        fields={
            "name": FieldSelector(selector="a.name", attr="text"),
            "price": FieldSelector(selector="span.price", attr="text"),
        },
    )
    gen = FakeSelectorGenerator(selector_plan)
    cache = FakeSelectorCache()

    first = _agent(products_html, plan=plan, selector_generator=gen, selector_cache=cache)
    s1 = await first.run("x", prompt="get names and prices")
    assert s1["status"] == ScrapeStatus.COMPLETED
    assert len(gen.feedback_seen) == 1  # generated once
    assert cache.store  # stored after it validated

    # A fresh run (same url + prompt) should hit the cache and skip generation.
    second = _agent(products_html, plan=plan, selector_generator=gen, selector_cache=cache)
    s2 = await second.run("x", prompt="get names and prices")
    assert s2["status"] == ScrapeStatus.COMPLETED
    assert s2["selector_from_cache"] is True
    assert len(gen.feedback_seen) == 1  # NOT regenerated
    assert s2["extraction_result"]["row_count"] == 3


@pytest.mark.asyncio
async def test_cached_selector_failure_invalidates_and_falls_back(products_html: str):
    from app.services.extraction.cache import selector_cache_key

    plan = ExtractionPlan(
        is_extractable=True, is_list=True, fields=PRODUCT_FIELDS, suggested_strategy="selector"
    )
    bad = SelectorPlan(
        record_selector="div.nope", fields={"name": FieldSelector(selector="x", attr="text")}
    )
    key = selector_cache_key("x", "get names and prices", ["name", "price"])
    cache = FakeSelectorCache({key: bad.model_dump()})

    agent = _agent(
        products_html,
        plan=plan,
        llm_records=[{"name": "Wireless Mouse", "price": "29.90"}],
        selector_cache=cache,
    )
    state = await agent.run("x", prompt="get names and prices")

    assert state["status"] == ScrapeStatus.COMPLETED
    assert key not in cache.store  # the stale cached plan was invalidated
    assert state["extraction_result"]["strategy"] == "llm"  # and the run fell back


@pytest.mark.asyncio
async def test_astream_emits_node_progress(products_html: str):
    plan = ExtractionPlan(
        is_extractable=True, is_list=True, fields=PRODUCT_FIELDS, suggested_strategy="llm"
    )
    agent = _agent(products_html, plan=plan, llm_records=[{"name": "A", "price": "1"}])

    steps = []
    final = None
    async for state in agent.astream_run("x", prompt="get names and prices"):
        final = state
        for entry in state.get("execution_log", []):
            if entry["step"] not in steps:
                steps.append(entry["step"])

    assert final["status"] == ScrapeStatus.COMPLETED
    # The pipeline's node sequence surfaced through the stream
    assert steps == [
        "fetch_page",
        "structure_dom",
        "plan_extraction",
        "llm_extract",
        "validate_result",
    ]
