"""Planner and LLM extractor with fake chat models (no network / no credits)."""

import pytest

from app.services.extraction.llm_extractor import LLMExtractor
from app.services.extraction.models import ExtractionPlan, FieldSpec
from app.services.extraction.planner import ExtractionPlanner


class _FakeStructuredModel:
    def __init__(self, result):
        self._result = result

    async def ainvoke(self, _messages):
        return self._result


class FakeStructuredLLM:
    """Mimics a chat model whose .with_structured_output returns typed objects."""

    def __init__(self, result):
        self._result = result

    def with_structured_output(self, _schema, **_kwargs):
        return _FakeStructuredModel(self._result)


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class FakeContentLLM:
    def __init__(self, content: str):
        self._content = content

    async def ainvoke(self, _messages):
        return _FakeMessage(self._content)


class FakeSequenceLLM:
    """Returns a different reply per call, to exercise the repair retry."""

    def __init__(self, *contents: str):
        self._contents = list(contents)
        self.calls = 0

    async def ainvoke(self, _messages):
        content = self._contents[min(self.calls, len(self._contents) - 1)]
        self.calls += 1
        return _FakeMessage(content)


@pytest.mark.asyncio
async def test_planner_returns_typed_plan():
    plan = ExtractionPlan(
        is_extractable=True,
        is_list=True,
        fields=[FieldSpec(name="title", description="the title")],
        suggested_strategy="selector",
    )
    planner = ExtractionPlanner(FakeStructuredLLM(plan))
    result = await planner.plan("get titles", {"tag": "body"})
    assert result.is_extractable
    assert result.fields[0].name == "title"


@pytest.mark.asyncio
async def test_llm_extractor_parses_records():
    plan = ExtractionPlan(
        is_extractable=True, fields=[FieldSpec(name="title", description="t")]
    )
    llm = FakeContentLLM('[{"title": "A"}, {"title": "B"}]')
    records = await LLMExtractor(llm).extract(plan, {"tag": "body"})
    assert records == [{"title": "A"}, {"title": "B"}]


@pytest.mark.asyncio
async def test_llm_extractor_wraps_single_object():
    plan = ExtractionPlan(is_extractable=True, fields=[FieldSpec(name="title", description="t")])
    llm = FakeContentLLM('{"title": "solo"}')
    records = await LLMExtractor(llm).extract(plan, {"tag": "body"})
    assert records == [{"title": "solo"}]


@pytest.mark.asyncio
async def test_llm_extractor_repairs_unparseable_reply():
    plan = ExtractionPlan(is_extractable=True, fields=[FieldSpec(name="title", description="t")])
    llm = FakeSequenceLLM("sorry, here you go: not json", '[{"title": "A"}]')
    records = await LLMExtractor(llm).extract(plan, {"tag": "body"})
    assert records == [{"title": "A"}]
    assert llm.calls == 2  # first reply failed, repaired on retry


@pytest.mark.asyncio
async def test_llm_extractor_gives_up_after_repair():
    from app.core.exceptions import ExtractionError

    plan = ExtractionPlan(is_extractable=True, fields=[FieldSpec(name="title", description="t")])
    llm = FakeSequenceLLM("nope", "still nope")
    with pytest.raises(ExtractionError):
        await LLMExtractor(llm).extract(plan, {"tag": "body"})
    assert llm.calls == 2  # capped at max_attempts
