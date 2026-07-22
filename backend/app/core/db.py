"""Async SQLAlchemy engine, schema reconciliation and session lifecycle."""

import logging
from collections.abc import AsyncIterator

from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.schema import CreateColumn

from app.models.orm import Base

logger = logging.getLogger(__name__)


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, future=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def _add_missing_columns(conn: Connection) -> list[str]:
    """Add mapped columns that are absent from already-existing tables.

    create_all() only creates missing *tables*, so a database created by an older
    version keeps its old columns and every query for a newly mapped column fails.
    This reconciles that additively (ALTER TABLE ... ADD COLUMN), which covers the
    only kind of schema change made so far. Drops, renames and type changes are NOT
    handled — those need a real migration tool (Alembic).
    """
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    dialect = conn.dialect
    added: list[str] = []

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all() just made it, so it is already current
        present = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            if not column.nullable and column.default is None and column.server_default is None:
                # Cannot back-fill existing rows safely; leave it to a real migration.
                logger.error(
                    "cannot auto-add NOT NULL column %s.%s without a default; "
                    "a manual migration is required",
                    table.name,
                    column.name,
                )
                continue
            ddl = CreateColumn(column).compile(dialect=dialect)
            conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {ddl}"))
            added.append(f"{table.name}.{column.name}")

    return added


async def init_db(engine: AsyncEngine) -> None:
    """Create missing tables, then additively reconcile columns on existing ones."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        added = await conn.run_sync(_add_missing_columns)
    if added:
        logger.info("schema reconciled, added column(s): %s", ", ".join(added))


async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
