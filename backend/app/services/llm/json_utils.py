import json
import re
from typing import Any

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_response(content: str) -> Any:
    """Parse a JSON payload from an LLM reply, tolerating markdown code fences.

    Raises ValueError if no JSON object/array can be recovered.
    """
    text = content.strip()
    text = _FENCE_RE.sub("", text).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fall back to the first {...} or [...] span in the text.
    start = min(
        (i for i in (text.find("{"), text.find("[")) if i != -1),
        default=-1,
    )
    if start != -1:
        end = max(text.rfind("}"), text.rfind("]"))
        if end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

    raise ValueError(f"Could not parse JSON from LLM response: {content[:200]!r}")
