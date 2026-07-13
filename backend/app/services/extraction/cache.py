"""Selector-plan reuse cache.

The 'selector' strategy is the cheap, reusable one: the LLM emits a declarative
CSS-selector plan that fixed code executes. For a team re-scraping similar pages
(same site, same extraction intent), regenerating that plan every run is the main
avoidable LLM cost. This cache lets a validated plan be reused across runs.

The agent depends only on the SelectorCache protocol; the concrete store lives in
app.repository.selector_cache_repo. Cache maintenance is outcome-driven: a plan is
stored only after it passes validation, and a cached plan that later fails is
invalidated — so stale selectors self-heal instead of failing forever.
"""

import hashlib
from typing import Any, Protocol
from urllib.parse import urlparse


def host_of(url: str) -> str:
    return urlparse(url).hostname or ""


def selector_cache_key(url: str, prompt: str | None, field_names: list[str]) -> str:
    """Stable key over (host, normalised prompt, field set).

    Keyed by host rather than full URL so sibling pages of the same site share a
    plan; the field set guards against reusing a plan built for a different request.
    """
    norm_prompt = " ".join((prompt or "").lower().split())
    fields_sig = ",".join(sorted(field_names))
    raw = f"{host_of(url)}|{norm_prompt}|{fields_sig}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class SelectorCache(Protocol):
    async def get(self, key: str) -> dict[str, Any] | None: ...

    async def put(
        self,
        key: str,
        host: str,
        prompt: str | None,
        fields: list[str],
        selector_plan: dict[str, Any],
    ) -> None: ...

    async def invalidate(self, key: str) -> None: ...
