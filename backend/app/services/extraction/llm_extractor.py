"""The 'llm' strategy: have the model read the DOM and return records directly."""

import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel

from app.core.exceptions import ExtractionError
from app.services.extraction.models import ExtractionPlan
from app.services.llm import parse_json_response

logger = logging.getLogger(__name__)

_SYSTEM = """You extract structured data from web pages. Given target fields and a \
compressed JSON view of the page DOM, return ONLY a JSON array of records. Each \
record is an object whose keys are exactly the field names. Use null when a value \
is missing. Do not invent data that is not present on the page."""


class LLMExtractor:
    def __init__(self, llm: BaseChatModel):
        self._llm = llm

    async def extract(
        self,
        plan: ExtractionPlan,
        structured_dom: dict[str, Any],
        feedback: str | None = None,
    ) -> list[dict[str, Any]]:
        fields_desc = "\n".join(f"- {f.name}: {f.description} ({f.type})" for f in plan.fields)
        dom_json = json.dumps(structured_dom, ensure_ascii=False)
        expectation = "many records" if plan.is_list else "exactly one record"
        feedback_block = f"A previous attempt had problems: {feedback}\n\n" if feedback else ""
        user = (
            f"Target fields:\n{fields_desc}\n\n"
            f"Expect {expectation}.\n\n"
            f"{feedback_block}"
            f"Compressed DOM (truncated JSON):\n{dom_json[:12000]}"
        )
        try:
            response = await self._llm.ainvoke(
                [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]
            )
            content = response.content
            data = parse_json_response(content if isinstance(content, str) else str(content))
        except Exception as e:
            raise ExtractionError(f"LLM extraction failed: {e}") from e

        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ExtractionError("LLM extraction did not return a list of records")

        records = [r for r in data if isinstance(r, dict)]
        logger.info("llm extraction produced %d record(s)", len(records))
        return records
