"""Batch mode: plan reuse, bounded concurrency, per-URL failure isolation.

The cost claim (only the warm-up URL pays for LLM work) is what these assert; a
regression there would be invisible in the API response but expensive in practice.
"""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db import create_session_factory, init_db
from app.models.schemas import ScrapeStatus
from app.repository import BatchRepository, TaskRepository
from app.services.batch_service import BatchRunner


class RecordingAgent:
    """Stands in for ScraperAgent, recording how each URL was run."""

    def __init__(self, fail_urls: set[str] | None = None, crash_urls: set[str] | None = None):
        self.calls: list[tuple[str, bool]] = []  # (url, had_preset_plan)
        self.concurrent = 0
        self.max_concurrent = 0
        self._fail = fail_urls or set()
        self._crash = crash_urls or set()

    async def run(self, url, prompt=None, options=None, preset_plan=None):
        self.calls.append((url, preset_plan is not None))
        self.concurrent += 1
        self.max_concurrent = max(self.max_concurrent, self.concurrent)
        try:
            await asyncio.sleep(0.01)  # hold the slot so overlap is observable
            if url in self._crash:
                raise RuntimeError("boom")
            if url in self._fail:
                return {
                    "url": url,
                    "prompt": prompt,
                    "status": ScrapeStatus.FAILED,
                    "error_code": "FETCH_FAILED",
                    "error_message": "nope",
                    "execution_log": [],
                }
            return {
                "url": url,
                "prompt": prompt,
                "status": ScrapeStatus.COMPLETED,
                "extraction_plan": preset_plan or {"fields": [{"name": "title"}], "is_list": True},
                "extraction_result": {
                    "records": [{"title": f"from {url}"}],
                    "fields": ["title"],
                    "strategy": "selector",
                    "row_count": 1,
                    "field_coverage": {"title": 1.0},
                },
                "execution_log": [],
            }
        finally:
            self.concurrent -= 1


@pytest.fixture
async def repos():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    factory = create_session_factory(engine)
    yield TaskRepository(factory), BatchRepository(factory)
    await engine.dispose()


URLS = [f"https://example.com/p/{i}" for i in range(5)]


@pytest.mark.asyncio
async def test_only_warmup_url_plans_the_rest_reuse_it(repos):
    task_repo, batch_repo = repos
    agent = RecordingAgent()
    await batch_repo.create("b1", "get titles", len(URLS))

    await BatchRunner(agent, task_repo, batch_repo, concurrency=2).run("b1", URLS, "get titles")

    assert len(agent.calls) == 5
    # The first URL plans; every later one is seeded with the shared plan.
    assert agent.calls[0] == (URLS[0], False)
    assert all(had_plan for _, had_plan in agent.calls[1:])

    batch = await batch_repo.get("b1")
    assert batch.status == ScrapeStatus.COMPLETED
    assert batch.completed == 5 and batch.failed == 0
    assert batch.shared_plan is not None


@pytest.mark.asyncio
async def test_concurrency_is_bounded(repos):
    task_repo, batch_repo = repos
    agent = RecordingAgent()
    await batch_repo.create("b2", "p", len(URLS))

    await BatchRunner(agent, task_repo, batch_repo, concurrency=2).run("b2", URLS, "p")

    assert agent.max_concurrent <= 2


@pytest.mark.asyncio
async def test_warmup_runs_alone_before_the_others(repos):
    """If members started alongside the warm-up they would all miss the cache."""
    task_repo, batch_repo = repos
    agent = RecordingAgent()
    await batch_repo.create("b3", "p", len(URLS))

    await BatchRunner(agent, task_repo, batch_repo, concurrency=4).run("b3", URLS, "p")

    # The warm-up is the first call and nothing overlapped it, so a plan existed
    # by the time any member started.
    assert agent.calls[0][0] == URLS[0]
    assert all(had_plan for _, had_plan in agent.calls[1:])


@pytest.mark.asyncio
async def test_failed_and_crashing_urls_do_not_abort_the_batch(repos):
    task_repo, batch_repo = repos
    agent = RecordingAgent(fail_urls={URLS[1]}, crash_urls={URLS[2]})
    await batch_repo.create("b4", "p", len(URLS))

    await BatchRunner(agent, task_repo, batch_repo, concurrency=3).run("b4", URLS, "p")

    batch = await batch_repo.get("b4")
    assert batch.status == ScrapeStatus.COMPLETED  # the batch itself still finishes
    assert batch.completed == 3
    assert batch.failed == 2

    tasks, _ = await task_repo.list_tasks()
    codes = {t.url: t.error_code for t in tasks}
    assert codes[URLS[1]] == "FETCH_FAILED"
    assert codes[URLS[2]] == "INTERNAL_ERROR"  # the crash was contained


@pytest.mark.asyncio
async def test_export_flattens_records_tagged_with_source_url(repos):
    task_repo, batch_repo = repos
    agent = RecordingAgent()
    await batch_repo.create("b5", "p", 3)

    await BatchRunner(agent, task_repo, batch_repo, concurrency=2).run("b5", URLS[:3], "p")

    rows = await batch_repo.records_for_export("b5")
    assert len(rows) == 3
    assert {r["source_url"] for r in rows} == set(URLS[:3])
    assert all("title" in r for r in rows)


@pytest.mark.asyncio
async def test_single_url_batch_still_works(repos):
    task_repo, batch_repo = repos
    agent = RecordingAgent()
    await batch_repo.create("b6", "p", 1)

    await BatchRunner(agent, task_repo, batch_repo, concurrency=3).run("b6", URLS[:1], "p")

    assert len(agent.calls) == 1
    batch = await batch_repo.get("b6")
    assert batch.status == ScrapeStatus.COMPLETED
    assert batch.completed == 1


@pytest.mark.asyncio
async def test_batch_reaches_terminal_state_when_warmup_crashes(repos):
    task_repo, batch_repo = repos
    agent = RecordingAgent(crash_urls={URLS[0]})
    await batch_repo.create("b7", "p", len(URLS))

    await BatchRunner(agent, task_repo, batch_repo, concurrency=2).run("b7", URLS, "p")

    batch = await batch_repo.get("b7")
    # Warm-up produced no plan, but the batch still runs the rest and terminates.
    assert batch.status == ScrapeStatus.COMPLETED
    assert batch.failed >= 1
    assert batch.shared_plan is None
