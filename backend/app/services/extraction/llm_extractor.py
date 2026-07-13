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


_REPAIR = (
    "Your previous reply could not be parsed as JSON. Reply again with ONLY a JSON "
    "array of records and no prose or code fences."
)


class LLMExtractor:
    def __init__(self, llm: BaseChatModel, char_budget: int = 12000, max_attempts: int = 2):
        self._llm = llm
        self._char_budget = char_budget
        self._max_attempts = max(1, max_attempts)

    async def extract(
        self,
        plan: ExtractionPlan,
        structured_dom: dict[str, Any],
        feedback: str | None = None,
    ) -> list[dict[str, Any]]:
        fields_desc = "\n".join(f"- {f.name}: {f.description} ({f.type})" for f in plan.fields)
        # Truncation is detected and surfaced once in the structure_dom node; here we
        # just slice to the same budget for the prompt.
        dom_json = json.dumps(structured_dom, ensure_ascii=False)
        expectation = "many records" if plan.is_list else "exactly one record"
        feedback_block = f"A previous attempt had problems: {feedback}\n\n" if feedback else ""
        user = (
            f"Target fields:\n{fields_desc}\n\n"
            f"Expect {expectation}.\n\n"
            f"{feedback_block}"
            f"Compressed DOM (truncated JSON):\n{dom_json[: self._char_budget]}"
        )

        # Retry once on an unparseable reply, nudging the model back to strict JSON.
        # (Transient HTTP failures are retried a layer down, in the chat client.)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ]
        data: Any = None
        last_error: Exception | None = None
        for attempt in range(self._max_attempts):
            try:
                response = await self._llm.ainvoke(messages)
                content = response.content
                data = parse_json_response(content if isinstance(content, str) else str(content))
                break
            except Exception as e:  # noqa: BLE001 - reclassified below as ExtractionError
                last_error = e
                if attempt + 1 < self._max_attempts:
                    logger.info("llm extraction reply unparseable, repair retry: %s", e)
                    messages = messages + [{"role": "user", "content": _REPAIR}]
        else:
            raise ExtractionError(f"LLM extraction failed: {last_error}") from last_error

        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ExtractionError("LLM extraction did not return a list of records")

        records = [r for r in data if isinstance(r, dict)]
        logger.info("llm extraction produced %d record(s)", len(records))
        return records
