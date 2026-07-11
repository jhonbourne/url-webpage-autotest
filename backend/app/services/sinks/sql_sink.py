"""Optional sink that appends result records to an external SQL database.

Uses a single generic table so any SQLAlchemy-supported target works without a
bespoke schema. Enable by setting result_sink_url (e.g. the team's Postgres).
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime, MetaData, String, Table, Text, insert
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)

_metadata = MetaData()
scraped_records = Table(
    "scraped_records",
    _metadata,
    Column("task_id", String(32), index=True),
    Column("url", Text),
    Column("record", Text),  # JSON-encoded single record
    Column("scraped_at", DateTime(timezone=True)),
)


class SqlResultSink:
    def __init__(self, sink_url: str):
        self._engine = create_async_engine(sink_url, future=True)
        self._ready = False

    async def _ensure_table(self) -> None:
        if not self._ready:
            async with self._engine.begin() as conn:
                await conn.run_sync(_metadata.create_all)
            self._ready = True

    async def write(self, task_id: str, url: str, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        await self._ensure_table()
        now = datetime.now(UTC)
        rows = [
            {
                "task_id": task_id,
                "url": url,
                "record": json.dumps(r, ensure_ascii=False),
                "scraped_at": now,
            }
            for r in records
        ]
        async with self._engine.begin() as conn:
            await conn.execute(insert(scraped_records), rows)
        logger.info("wrote %d record(s) for task %s to external sink", len(rows), task_id)

    async def aclose(self) -> None:
        await self._engine.dispose()
