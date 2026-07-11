"""SQLAlchemy ORM models for application state (tasks + result snapshots).

This is the app's own runtime metadata store, deliberately separate from any
business/analysis database the team may run. Business results can additionally be
pushed to an external store via app.services.sinks (see ResultSink).
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


class ScrapeTask(Base):
    __tablename__ = "scrape_tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    url: Mapped[str] = mapped_column(Text)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    fetch_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    strategy: Mapped[str | None] = mapped_column(String(20), nullable=True)
    row_count: Mapped[int | None] = mapped_column(nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_log: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=_now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    result: Mapped["ScrapeResult | None"] = relationship(
        back_populates="task", uselist=False, cascade="all, delete-orphan"
    )


class ScrapeResult(Base):
    __tablename__ = "scrape_results"

    task_id: Mapped[str] = mapped_column(
        ForeignKey("scrape_tasks.id", ondelete="CASCADE"), primary_key=True
    )
    fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    records: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    field_coverage: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    validation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    task: Mapped[ScrapeTask] = relationship(back_populates="result")
