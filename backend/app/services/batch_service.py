"""Batch mode: one extraction request applied to a list of homogeneous URLs.

Cost is the whole point. Run naively, every URL would pay for planning *and*
selector generation. Instead the batch runs one warm-up URL first: that single run
produces the extraction plan and (on the selector strategy) populates the selector
cache. Every remaining URL is then seeded with that plan and hits the cached
selectors, so it does no LLM work at all — the batch costs roughly one page's worth
of tokens regardless of how many URLs follow.

The remaining URLs run concurrently under a semaphore; failures are recorded
per-URL and never abort the batch.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

from app.agents.state import ScrapeState
from app.models.schemas import ScrapeStatus
from app.repository import BatchRepository, TaskRepository

logger = logging.getLogger(__name__)


class _Agent(Protocol):
    async def run(
        self,
        url: str,
        prompt: str | None = None,
        options: dict[str, Any] | None = None,
        preset_plan: dict[str, Any] | None = None,
    ) -> ScrapeState: ...


class BatchRunner:
    def __init__(
        self,
        agent: _Agent,
        task_repo: TaskRepository,
        batch_repo: BatchRepository,
        concurrency: int = 3,
    ):
        self._agent = agent
        self._task_repo = task_repo
        self._batch_repo = batch_repo
        self._concurrency = max(1, concurrency)

    async def run(
        self,
        batch_id: str,
        urls: list[str],
        prompt: str,
        options: dict[str, Any] | None = None,
    ) -> None:
        """Execute a whole batch. Intended to be awaited in a background task."""
        try:
            warm_url, rest = urls[0], urls[1:]

            # 1. Warm-up run: the only one allowed to spend tokens on planning.
            warm_state = await self._run_one(batch_id, warm_url, prompt, options, None)
            shared_plan = warm_state.get("extraction_plan")
            await self._batch_repo.set_running(batch_id, shared_plan)

            if shared_plan is None and rest:
                # The warm-up never produced a plan (e.g. fetch failed), so there is
                # nothing to reuse. Let the rest plan for themselves rather than
                # failing the batch outright.
                logger.warning(
                    "batch %s warm-up produced no plan; members will plan individually",
                    batch_id,
                )

            # 2. Remaining URLs reuse the plan and the warmed selector cache.
            if rest:
                semaphore = asyncio.Semaphore(self._concurrency)

                async def worker(url: str) -> None:
                    async with semaphore:
                        await self._run_one(batch_id, url, prompt, options, shared_plan)

                await asyncio.gather(*(worker(u) for u in rest))

            await self._batch_repo.finish(batch_id, ScrapeStatus.COMPLETED)
            logger.info("batch %s finished (%d url(s))", batch_id, len(urls))
        except Exception as exc:  # noqa: BLE001 - a batch must always reach a terminal state
            logger.exception("batch %s failed", batch_id)
            await self._batch_repo.finish(batch_id, ScrapeStatus.FAILED, str(exc))

    async def _run_one(
        self,
        batch_id: str,
        url: str,
        prompt: str,
        options: dict[str, Any] | None,
        preset_plan: dict[str, Any] | None,
    ) -> ScrapeState:
        task_id = uuid.uuid4().hex
        await self._task_repo.create_running(task_id, url, prompt, batch_id=batch_id)
        try:
            state = await self._agent.run(
                url=url, prompt=prompt, options=options, preset_plan=preset_plan
            )
        except Exception as exc:  # noqa: BLE001 - one bad URL must not sink the batch
            logger.exception("batch %s: url %s crashed", batch_id, url)
            state = {
                "url": url,
                "prompt": prompt,
                "status": ScrapeStatus.FAILED,
                "error_code": "INTERNAL_ERROR",
                "error_message": str(exc),
                "execution_log": [],
                "finished_at": datetime.now(UTC).isoformat(),
            }

        await self._task_repo.save_from_state(task_id, state)
        await self._batch_repo.record_outcome(
            batch_id, ok=state.get("status") == ScrapeStatus.COMPLETED
        )
        return state
