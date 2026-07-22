"""Persistence access layer for batch runs."""

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.models.orm import ScrapeBatch, ScrapeTask
from app.models.schemas import ScrapeStatus


class BatchRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def mark_stale_interrupted(self) -> int:
        """Sweep batches left non-terminal by a previous process. Mirrors the task
        sweep; run once at startup."""
        terminal = (
            str(ScrapeStatus.COMPLETED),
            str(ScrapeStatus.FAILED),
            str(ScrapeStatus.INTERRUPTED),
        )
        async with self._session_factory() as session:
            result = cast(
                CursorResult[Any],
                await session.execute(
                    update(ScrapeBatch)
                    .where(ScrapeBatch.status.not_in(terminal))
                    .values(status=str(ScrapeStatus.INTERRUPTED), finished_at=datetime.now(UTC))
                ),
            )
            await session.commit()
            return result.rowcount or 0

    async def create(self, batch_id: str, prompt: str | None, total: int) -> None:
        async with self._session_factory() as session:
            session.add(
                ScrapeBatch(
                    id=batch_id,
                    prompt=prompt,
                    status=str(ScrapeStatus.PENDING),
                    total=total,
                )
            )
            await session.commit()

    async def set_running(self, batch_id: str, shared_plan: dict[str, Any] | None) -> None:
        async with self._session_factory() as session:
            batch = await session.get(ScrapeBatch, batch_id)
            if batch is None:
                return
            batch.status = str(ScrapeStatus.EXTRACTING)
            batch.shared_plan = shared_plan
            await session.commit()

    async def record_outcome(self, batch_id: str, *, ok: bool) -> None:
        """Increment the completed/failed counters as each member task finishes.

        The increment is done in SQL rather than read-modify-write in Python:
        members run concurrently, so two workers reading the same value and each
        writing back +1 would silently lose one of the two outcomes."""
        column = ScrapeBatch.completed if ok else ScrapeBatch.failed
        async with self._session_factory() as session:
            await session.execute(
                update(ScrapeBatch)
                .where(ScrapeBatch.id == batch_id)
                .values({column: column + 1})
            )
            await session.commit()

    async def finish(
        self, batch_id: str, status: ScrapeStatus, error_message: str | None = None
    ) -> None:
        async with self._session_factory() as session:
            batch = await session.get(ScrapeBatch, batch_id)
            if batch is None:
                return
            batch.status = str(status)
            batch.error_message = error_message
            batch.finished_at = datetime.now(UTC)
            await session.commit()

    async def get(self, batch_id: str, *, with_tasks: bool = False) -> ScrapeBatch | None:
        async with self._session_factory() as session:
            stmt = select(ScrapeBatch).where(ScrapeBatch.id == batch_id)
            if with_tasks:
                stmt = stmt.options(selectinload(ScrapeBatch.tasks))
            return await session.scalar(stmt)

    async def list_batches(
        self, limit: int = 50, offset: int = 0
    ) -> tuple[list[ScrapeBatch], int]:
        async with self._session_factory() as session:
            total = await session.scalar(select(func.count()).select_from(ScrapeBatch))
            rows = await session.scalars(
                select(ScrapeBatch)
                .order_by(ScrapeBatch.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(rows), int(total or 0)

    async def records_for_export(self, batch_id: str) -> list[dict[str, Any]]:
        """Flatten every member task's records, tagged with their source URL so the
        combined export stays traceable back to individual pages."""
        async with self._session_factory() as session:
            tasks = await session.scalars(
                select(ScrapeTask)
                .options(selectinload(ScrapeTask.result))
                .where(ScrapeTask.batch_id == batch_id)
                .order_by(ScrapeTask.created_at)
            )
            rows: list[dict[str, Any]] = []
            for task in tasks:
                if task.result is None:
                    continue
                for record in task.result.records:
                    rows.append({"source_url": task.url, **record})
            return rows
