"""Full-graph runs with fake LLM services + the real executor and DOM parser.

Verifies routing (selector vs llm strategy, structure-only, error) without network
or LLM credits. The selector path exercises the real controlled executor end-to-end.
"""

import pytest

from app.agents.scraper_agent import ScraperAgent
from app.models.schemas import ScrapeStatus
from app.services.dom_service import DOMService
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

    async def generate(self, _plan, _dom):
        return self._selector_plan


class FakeLLMExtractor:
    def __init__(self, records):
        self._records = records

    async def extract(self, _plan, _dom):
        return self._records


def _agent(html, *, plan, selector_plan=None, llm_records=None):
    return ScraperAgent(
        fetch_service=FakeFetchService(html),
        dom_service=DOMService(),
        planner=FakePlanner(plan),
        selector_generator=FakeSelectorGenerator(selector_plan or SelectorPlan()),
        selector_executor=SelectorExecutor(),
        llm_extractor=FakeLLMExtractor(llm_records or []),
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
