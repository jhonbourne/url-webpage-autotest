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


def _agent(
    html,
    *,
    plan,
    selector_plan=None,
    llm_records=None,
    selector_generator=None,
    llm_extractor=None,
    max_retries=2,
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
