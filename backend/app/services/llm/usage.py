"""Aggregate LLM token usage collected by a UsageMetadataCallbackHandler.

LangGraph propagates the run's callbacks to every nested LLM call, so a single
handler passed at the graph boundary captures usage across planning, selector
generation and extraction — even for structured-output calls whose parsed return
value drops the usage metadata.
"""

from typing import Any


def summarize_usage(by_model: dict[str, Any] | None) -> dict[str, Any]:
    """Fold the handler's per-model usage into run totals plus a per-model breakdown."""
    input_tokens = output_tokens = total_tokens = 0
    models: dict[str, dict[str, int]] = {}
    for model, um in (by_model or {}).items():
        it = int(um.get("input_tokens", 0))
        ot = int(um.get("output_tokens", 0))
        tt = int(um.get("total_tokens", it + ot))
        input_tokens += it
        output_tokens += ot
        total_tokens += tt
        models[model] = {"input_tokens": it, "output_tokens": ot, "total_tokens": tt}
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "by_model": models,
    }
