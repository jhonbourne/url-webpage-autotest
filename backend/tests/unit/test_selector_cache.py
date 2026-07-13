import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db import create_session_factory, init_db
from app.repository import SelectorCacheRepository
from app.services.extraction.cache import host_of, selector_cache_key


def test_key_is_stable_across_equivalent_requests():
    a = selector_cache_key("https://shop.com/p/1", "Get Names", ["name", "price"])
    b = selector_cache_key("https://shop.com/p/2", "  get   names ", ["price", "name"])
    # Same host, normalised prompt, same field set (order-insensitive) -> same key.
    assert a == b


def test_key_differs_on_host_prompt_or_fields():
    base = selector_cache_key("https://shop.com/x", "get names", ["name"])
    assert base != selector_cache_key("https://other.com/x", "get names", ["name"])
    assert base != selector_cache_key("https://shop.com/x", "get prices", ["name"])
    assert base != selector_cache_key("https://shop.com/x", "get names", ["name", "price"])


def test_host_of():
    assert host_of("https://a.example.com/path?q=1") == "a.example.com"
    assert host_of("not a url") == ""


@pytest.fixture
async def cache():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    yield SelectorCacheRepository(create_session_factory(engine))
    await engine.dispose()


@pytest.mark.asyncio
async def test_put_get_invalidate(cache: SelectorCacheRepository):
    plan = {"record_selector": "li.item", "fields": {"name": {"selector": "a"}}}
    await cache.put("k1", "shop.com", "get names", ["name"], plan)

    assert await cache.get("k1") == plan
    assert await cache.get("missing") is None

    await cache.invalidate("k1")
    assert await cache.get("k1") is None


@pytest.mark.asyncio
async def test_put_overwrites_existing(cache: SelectorCacheRepository):
    await cache.put("k", "h", "p", ["a"], {"v": 1})
    await cache.put("k", "h", "p", ["a", "b"], {"v": 2})
    assert (await cache.get("k")) == {"v": 2}
