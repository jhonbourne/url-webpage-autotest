"""Persistence access layer for scrape tasks and their results."""

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.agents.state import ScrapeState
from app.models.orm import ScrapeResult, ScrapeTask
from app.models.schemas import ScrapeStatus


class TaskRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def mark_stale_interrupted(self) -> int:
        """Reconcile rows left non-terminal by a previous process (a crash or restart
        mid-run) to 'interrupted'. Run once at startup. Returns the count swept."""
        terminal = (
            str(ScrapeStatus.COMPLETED),
            str(ScrapeStatus.FAILED),
            str(ScrapeStatus.INTERRUPTED),
        )
        async with self._session_factory() as session:
            result = cast(
                CursorResult[Any],
                await session.execute(
                    update(ScrapeTask)
                    .where(ScrapeTask.status.not_in(terminal))
                    .values(status=str(ScrapeStatus.INTERRUPTED), finished_at=datetime.now(UTC))
                ),
            )
            await session.commit()
            return result.rowcount or 0

    async def create_running(self, task_id: str, url: str, prompt: str | None) -> None:
        """Record a just-accepted run before it starts, so a crash or a dropped
        client connection still leaves a trace (a task stuck in 'pending' is the
        signal). save_from_state later updates this same row on completion."""
        async with self._session_factory() as session:
            session.add(
                ScrapeTask(id=task_id, url=url, prompt=prompt, status=str(ScrapeStatus.PENDING))
            )
            await session.commit()

    async def save_from_state(self, task_id: str, state: ScrapeState) -> None:
        """Persist a finished run: the task metadata and, if any, its result.

        Upserts — updates the row created by create_running, or inserts a fresh
        one if the run was never pre-registered."""
        result_data = state.get("extraction_result") or {}
        async with self._session_factory() as session:
            task = await session.scalar(
                select(ScrapeTask)
                .options(selectinload(ScrapeTask.result))
                .where(ScrapeTask.id == task_id)
            )
            if task is None:
                task = ScrapeTask(id=task_id)
                session.add(task)

            task.url = state["url"]
            task.prompt = state.get("prompt")
            task.status = str(state.get("status"))
            task.fetch_method = state.get("fetch_method")
            task.strategy = result_data.get("strategy")
            task.row_count = result_data.get("row_count")
            usage = state.get("token_usage") or {}
            task.input_tokens = usage.get("input_tokens")
            task.output_tokens = usage.get("output_tokens")
            task.total_tokens = usage.get("total_tokens")
            task.error_code = state.get("error_code")
            task.error_message = state.get("error_message")
            task.plan = state.get("extraction_plan")
            task.selector_plan = state.get("selector_plan")
            task.execution_log = state.get("execution_log", [])
            task.finished_at = _parse_dt(state.get("finished_at"))
            if result_data.get("records") is not None:
                task.result = ScrapeResult(
                    task_id=task_id,
                    fields=result_data.get("fields", []),
                    records=result_data.get("records", []),
                    field_coverage=result_data.get("field_coverage", {}),
                    validation=state.get("validation_report"),
                )
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
