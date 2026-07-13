import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db import create_session_factory, init_db
from app.models.schemas import ScrapeStatus
from app.repository import TaskRepository
from app.services.export_service import to_csv, to_xlsx
from app.services.sinks.null_sink import NullSink
from app.services.sinks.sql_sink import SqlResultSink


@pytest.fixture
async def repo():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    yield TaskRepository(create_session_factory(engine))
    await engine.dispose()


def _completed_state():
    return {
        "url": "https://example.com/",
        "prompt": "get names and prices",
        "status": ScrapeStatus.COMPLETED,
        "fetch_method": "static",
        "extraction_result": {
            "records": [{"name": "A", "price": "1"}, {"name": "B", "price": "2"}],
            "fields": ["name", "price"],
            "strategy": "selector",
            "row_count": 2,
            "field_coverage": {"name": 1.0, "price": 1.0},
        },
        "validation_report": {"ok": True, "issues": [], "metrics": {}},
        "token_usage": {"input_tokens": 800, "output_tokens": 120, "total_tokens": 920},
        "execution_log": [{"timestamp": "t", "step": "fetch_page", "message": "ok", "detail": {}}],
        "finished_at": "2026-07-12T00:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_save_and_get_task_with_result(repo: TaskRepository):
    await repo.save_from_state("task1", _completed_state())

    task = await repo.get_task("task1", with_result=True)
    assert task is not None
    assert task.status == "completed"
    assert task.strategy == "selector"
    assert task.row_count == 2
    assert task.result.records[0] == {"name": "A", "price": "1"}
    assert task.result.field_coverage["name"] == 1.0
    assert task.total_tokens == 920
    assert task.input_tokens == 800


@pytest.mark.asyncio
async def test_create_running_then_finalize_updates_same_row(repo: TaskRepository):
    await repo.create_running("t1", "https://example.com/", "get names and prices")

    # The pre-registered row is visible immediately as pending.
    pending = await repo.get_task("t1")
    assert pending is not None
    assert pending.status == ScrapeStatus.PENDING
    created_at = pending.created_at

    # Finishing the run updates that same row in place (no duplicate).
    await repo.save_from_state("t1", _completed_state())

    _, total = await repo.list_tasks()
    assert total == 1
    task = await repo.get_task("t1", with_result=True)
    assert task.status == "completed"
    assert task.row_count == 2
    assert task.created_at == created_at  # submission time preserved
    assert task.result.records[0] == {"name": "A", "price": "1"}


@pytest.mark.asyncio
async def test_mark_stale_interrupted_sweeps_only_nonterminal(repo: TaskRepository):
    await repo.create_running("running", "https://example.com/", "p")  # pending
    await repo.save_from_state("done", _completed_state())  # completed (terminal)

    swept = await repo.mark_stale_interrupted()
    assert swept == 1

    stale = await repo.get_task("running")
    assert stale.status == ScrapeStatus.INTERRUPTED
    assert stale.finished_at is not None
    # Terminal rows are left untouched.
    assert (await repo.get_task("done")).status == ScrapeStatus.COMPLETED

    # Idempotent: a second sweep finds nothing to do.
    assert await repo.mark_stale_interrupted() == 0


@pytest.mark.asyncio
async def test_list_tasks_pagination(repo: TaskRepository):
    for i in range(3):
        state = _completed_state()
        await repo.save_from_state(f"task{i}", state)

    tasks, total = await repo.list_tasks(limit=2, offset=0)
    assert total == 3
    assert len(tasks) == 2


@pytest.mark.asyncio
async def test_save_failed_state_without_result(repo: TaskRepository):
    state = {
        "url": "https://x.com/",
        "prompt": "p",
        "status": ScrapeStatus.FAILED,
        "error_code": "NOT_EXTRACTABLE",
        "error_message": "nope",
        "execution_log": [],
        "finished_at": "2026-07-12T00:00:00+00:00",
    }
    await repo.save_from_state("bad", state)
    task = await repo.get_task("bad", with_result=True)
    assert task.error_code == "NOT_EXTRACTABLE"
    assert task.result is None


def test_export_csv_and_xlsx_with_array_field():
    records = [{"name": "A", "tags": ["x", "y"]}, {"name": "B", "tags": []}]
    csv = to_csv(records)
    assert b"name" in csv and b"x, y" in csv  # array joined
    xlsx = to_xlsx(records)
    assert xlsx[:2] == b"PK"  # xlsx is a zip container


@pytest.mark.asyncio
async def test_null_sink_is_noop():
    sink = NullSink()
    await sink.write("t", "u", [{"a": 1}])
    await sink.aclose()


@pytest.mark.asyncio
async def test_sql_sink_writes_records():
    sink = SqlResultSink("sqlite+aiosqlite:///:memory:")
    # Same engine instance persists the in-memory DB across calls
    await sink.write("task1", "https://x.com", [{"a": "1"}, {"a": "2"}])
    from sqlalchemy import text

    async with sink._engine.connect() as conn:  # noqa: SLF001 - test introspection
        count = await conn.scalar(text("SELECT COUNT(*) FROM scraped_records"))
    assert count == 2
    await sink.aclose()
