"""Schema reconciliation for databases created by an older version.

create_all() only creates missing tables, so a pre-existing scrape_tasks kept its
old column set and every query touching a newly mapped column failed with
"no such column". init_db() now additively adds those columns.
"""

import sqlite3

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db import create_session_factory, init_db
from app.repository import TaskRepository

# scrape_tasks exactly as the pre-"Harden" release created it: no token counts,
# no plan / selector_plan, and no selector_cache table at all.
_LEGACY_SCHEMA = """
CREATE TABLE scrape_tasks (
    id VARCHAR(32) NOT NULL PRIMARY KEY,
    url TEXT,
    prompt TEXT,
    status VARCHAR(20),
    fetch_method VARCHAR(20),
    strategy VARCHAR(20),
    row_count INTEGER,
    error_code VARCHAR(40),
    error_message TEXT,
    execution_log JSON,
    created_at DATETIME,
    finished_at DATETIME
);
CREATE TABLE scrape_results (
    task_id VARCHAR(32) NOT NULL PRIMARY KEY,
    fields JSON,
    records JSON,
    field_coverage JSON,
    validation JSON
);
"""

_NEW_TASK_COLUMNS = {"input_tokens", "output_tokens", "total_tokens", "plan", "selector_plan"}


@pytest.fixture
def legacy_db(tmp_path):
    """A populated database on the old schema. Must be a file, not :memory:,
    since the engine has to reopen the same database the fixture wrote."""
    path = tmp_path / "legacy.db"
    con = sqlite3.connect(path)
    con.executescript(_LEGACY_SCHEMA)
    con.execute(
        "INSERT INTO scrape_tasks (id, url, status, created_at) VALUES (?, ?, ?, ?)",
        ("legacy1", "https://example.com/", "completed", "2026-01-01 00:00:00"),
    )
    con.commit()
    con.close()
    return path


def _columns(path: str) -> set[str]:
    con = sqlite3.connect(path)
    try:
        return {row[1] for row in con.execute("PRAGMA table_info(scrape_tasks)")}
    finally:
        con.close()


@pytest.mark.asyncio
async def test_init_db_adds_columns_missing_from_an_existing_table(legacy_db):
    assert not (_columns(legacy_db) & _NEW_TASK_COLUMNS)  # precondition: old schema

    engine = create_async_engine(f"sqlite+aiosqlite:///{legacy_db}")
    try:
        await init_db(engine)
    finally:
        await engine.dispose()

    assert _NEW_TASK_COLUMNS <= _columns(legacy_db)


@pytest.mark.asyncio
async def test_queries_work_and_legacy_rows_survive(legacy_db):
    engine = create_async_engine(f"sqlite+aiosqlite:///{legacy_db}")
    try:
        await init_db(engine)
        repo = TaskRepository(create_session_factory(engine))
        # This raised OperationalError("no such column: scrape_tasks.input_tokens")
        # before the reconciliation step existed.
        tasks, total = await repo.list_tasks()
    finally:
        await engine.dispose()

    assert total == 1
    assert tasks[0].id == "legacy1"
    assert tasks[0].url == "https://example.com/"
    assert tasks[0].input_tokens is None  # back-filled as NULL


@pytest.mark.asyncio
async def test_init_db_is_idempotent(legacy_db):
    engine = create_async_engine(f"sqlite+aiosqlite:///{legacy_db}")
    try:
        await init_db(engine)
        await init_db(engine)  # a second startup must not re-add anything
        repo = TaskRepository(create_session_factory(engine))
        _, total = await repo.list_tasks()
    finally:
        await engine.dispose()

    assert total == 1
    assert len(_columns(legacy_db)) == len(set(_columns(legacy_db)))


@pytest.mark.asyncio
async def test_missing_table_is_still_created(legacy_db):
    """selector_cache did not exist in the old schema at all."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{legacy_db}")
    try:
        await init_db(engine)
    finally:
        await engine.dispose()

    con = sqlite3.connect(legacy_db)
    try:
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    assert "selector_cache" in names
