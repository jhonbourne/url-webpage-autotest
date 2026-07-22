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


class ScrapeBatch(Base):
    """One batch run: a single extraction request applied to many URLs.

    Counters are updated as member tasks finish, so progress is pollable while the
    batch is still running."""

    __tablename__ = "scrape_batches"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    total: Mapped[int] = mapped_column(default=0)
    completed: Mapped[int] = mapped_column(default=0)
    failed: Mapped[int] = mapped_column(default=0)
    # Set from the first (warm-up) URL and reused for the rest of the batch.
    shared_plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    tasks: Mapped[list["ScrapeTask"]] = relationship(back_populates="batch")


class ScrapeTask(Base):
    __tablename__ = "scrape_tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    url: Mapped[str] = mapped_column(Text)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    fetch_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    strategy: Mapped[str | None] = mapped_column(String(20), nullable=True)
    row_count: Mapped[int | None] = mapped_column(nullable=True)
    # LLM token usage for the run (cost visibility).
    input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The plan the agent acted on and, on the selector path, the selectors it applied.
    # Persisted so a wrong result can be diagnosed after the fact.
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    selector_plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    execution_log: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=_now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Set when this task is a member of a batch run; NULL for single scrapes.
    batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("scrape_batches.id", ondelete="CASCADE"), nullable=True, index=True
    )

    result: Mapped["ScrapeResult | None"] = relationship(
        back_populates="task", uselist=False, cascade="all, delete-orphan"
    )
    batch: Mapped["ScrapeBatch | None"] = relationship(back_populates="tasks")


class SelectorCacheEntry(Base):
    """A validated selector plan, reusable across runs with the same cache key.

    A standalone table, so create_all() adds it to existing databases. Newly mapped
    *columns* on existing tables are handled separately by init_db()'s reconciliation."""

    __tablename__ = "selector_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    host: Mapped[str] = mapped_column(Text)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    selector_plan: Mapped[dict[str, Any]] = mapped_column(JSON)
    hit_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    last_used_at: Mapped[datetime] = mapped_column(default=_now)


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
