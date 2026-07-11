"""Persistence access layer for scrape tasks and their results."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.agents.state import ScrapeState
from app.models.orm import ScrapeResult, ScrapeTask


class TaskRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def save_from_state(self, task_id: str, state: ScrapeState) -> None:
        """Persist a finished run: the task metadata and, if any, its result."""
        result_data = state.get("extraction_result") or {}
        async with self._session_factory() as session:
            task = ScrapeTask(
                id=task_id,
                url=state["url"],
                prompt=state.get("prompt"),
                status=str(state.get("status")),
                fetch_method=state.get("fetch_method"),
                strategy=result_data.get("strategy"),
                row_count=result_data.get("row_count"),
                error_code=state.get("error_code"),
                error_message=state.get("error_message"),
                execution_log=state.get("execution_log", []),
                finished_at=_parse_dt(state.get("finished_at")),
            )
            if result_data.get("records") is not None:
                task.result = ScrapeResult(
                    task_id=task_id,
                    fields=result_data.get("fields", []),
                    records=result_data.get("records", []),
                    field_coverage=result_data.get("field_coverage", {}),
                    validation=state.get("validation_report"),
                )
            session.add(task)
            await session.commit()

    async def list_tasks(self, limit: int = 50, offset: int = 0) -> tuple[list[ScrapeTask], int]:
        async with self._session_factory() as session:
            total = await session.scalar(select(func.count()).select_from(ScrapeTask))
            rows = await session.scalars(
                select(ScrapeTask)
                .order_by(ScrapeTask.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(rows), int(total or 0)

    async def get_task(self, task_id: str, *, with_result: bool = False) -> ScrapeTask | None:
        async with self._session_factory() as session:
            stmt = select(ScrapeTask).where(ScrapeTask.id == task_id)
            if with_result:
                stmt = stmt.options(selectinload(ScrapeTask.result))
            return await session.scalar(stmt)

    async def get_result(self, task_id: str) -> ScrapeResult | None:
        async with self._session_factory() as session:
            return await session.get(ScrapeResult, task_id)


def _parse_dt(value: Any):
    from datetime import datetime

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return value
