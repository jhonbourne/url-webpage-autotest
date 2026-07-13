"""Persistence for the selector-plan reuse cache (see services.extraction.cache)."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.orm import SelectorCacheEntry


class SelectorCacheRepository:
    """SQL-backed SelectorCache. Satisfies the SelectorCache protocol."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def get(self, key: str) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            entry = await session.get(SelectorCacheEntry, key)
            if entry is None:
                return None
            entry.hit_count += 1
            entry.last_used_at = datetime.now(UTC)
            plan = entry.selector_plan
            await session.commit()
            return plan

    async def put(
        self,
        key: str,
        host: str,
        prompt: str | None,
        fields: list[str],
        selector_plan: dict[str, Any],
    ) -> None:
        async with self._session_factory() as session:
            entry = await session.get(SelectorCacheEntry, key)
            if entry is None:
                session.add(
                    SelectorCacheEntry(
                        key=key,
                        host=host,
                        prompt=prompt,
                        fields=fields,
                        selector_plan=selector_plan,
                    )
                )
            else:
                entry.selector_plan = selector_plan
                entry.fields = fields
                entry.last_used_at = datetime.now(UTC)
            await session.commit()

    async def invalidate(self, key: str) -> None:
        async with self._session_factory() as session:
            entry = await session.get(SelectorCacheEntry, key)
            if entry is not None:
                await session.delete(entry)
                await session.commit()
