"""Ask the LLM for a declarative CSS-selector plan (the 'selector' strategy)."""

import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel

from app.core.exceptions import ExtractionError
from app.services.extraction.models import ExtractionPlan, SelectorPlan

logger = logging.getLogger(__name__)

_SYSTEM = """You write CSS selector plans for web scraping. Given the target fields \
and a compressed JSON view of the page DOM, produce a JSON object:
{
  "record_selector": "<CSS selector matching each repeated record container, or \
empty string for a single-record page>",
  "fields": {
    "<field_name>": {"selector": "<CSS selector relative to the record container>", \
"attr": "text" | "<html attribute like href/src>", "multiple": false}
  }
}
Set "multiple": true for list-valued fields (type "array", e.g. tags): the selector \
should then match every item and the value becomes a list. \
Use selectors that are as robust as possible (prefer stable class/tag structure). \
Return ONLY the JSON object, no prose."""


class SelectorGenerator:
    def __init__(self, llm: BaseChatModel):
        self._llm = llm

    async def generate(
        self,
        plan: ExtractionPlan,
        structured_dom: dict[str, Any],
        feedback: str | None = None,
    ) -> SelectorPlan:
        model = self._llm.with_structured_output(SelectorPlan, method="function_calling")
        fields_desc = "\n".join(f"- {f.name}: {f.description} ({f.type})" for f in plan.fields)
        dom_json = json.dumps(structured_dom, ensure_ascii=False)
        feedback_block = f"\nA previous attempt had problems: {feedback}\n" if feedback else ""
        user = (
            f"is_list: {plan.is_list}\n"
            f"Target fields:\n{fields_desc}\n"
            f"{feedback_block}\n"
            f"Compressed DOM (truncated JSON):\n{dom_json[:12000]}"
        )
        try:
            result = await model.ainvoke(
                [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]
            )
        except Exception as e:
            raise ExtractionError(f"Selector generation failed: {e}") from e

        if not isinstance(result, SelectorPlan):
            raise ExtractionError("Selector generator returned an unexpected type")

        logger.info(
            "selector plan: record_selector=%r fields=%d",
            result.record_selector,
            len(result.fields),
        )
        return result
