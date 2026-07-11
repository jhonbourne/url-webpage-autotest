"""Turn a natural-language request + page structure into a typed ExtractionPlan."""

import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel

from app.core.exceptions import PlanningError
from app.services.extraction.models import ExtractionPlan

logger = logging.getLogger(__name__)

_SYSTEM = """You plan web-data extraction jobs. Given a user's request in natural \
language and a compressed JSON view of a page's DOM, decide:
- whether the request can be satisfied from this page (is_extractable),
- whether the page contains many repeated records or a single record (is_list),
- the concrete fields to extract, each with a snake_case name, a short description, \
and a type (string | number | url | boolean),
- a suggested strategy: "selector" when the target data sits in regular, repeated \
markup (lists, tables, cards); "llm" when it is irregular prose or scattered.
Only include fields the user actually asked for. If the page clearly does not \
contain the requested data, set is_extractable to false and explain in reason."""


class ExtractionPlanner:
    def __init__(self, llm: BaseChatModel):
        self._llm = llm

    async def plan(self, prompt: str, structured_dom: dict[str, Any]) -> ExtractionPlan:
        model = self._llm.with_structured_output(ExtractionPlan)
        dom_json = json.dumps(structured_dom, ensure_ascii=False)
        user = (
            f"User request:\n{prompt}\n\n"
            f"Compressed DOM (truncated JSON):\n{dom_json[:12000]}"
        )
        try:
            result = await model.ainvoke(
                [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]
            )
        except Exception as e:
            raise PlanningError(f"Planner LLM call failed: {e}") from e

        if not isinstance(result, ExtractionPlan):  # defensive; structured output should type it
            raise PlanningError("Planner returned an unexpected type")

        logger.info(
            "extraction plan: extractable=%s list=%s fields=%d strategy=%s",
            result.is_extractable,
            result.is_list,
            len(result.fields),
            result.suggested_strategy,
        )
        return result
