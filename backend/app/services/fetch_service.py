"""Page fetching: httpx fast path for static pages, Playwright fallback for JS-rendered ones.

Owns the browser lifecycle (start lazily, closed via aclose() on app shutdown) and
enforces the SSRF guard on every URL it touches.
"""

import asyncio
import ipaddress
import logging
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import Browser, Playwright, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.core.config import Settings
from app.core.exceptions import (
    BlockedUrlError,
    EmptyPageError,
    FetchError,
    FetchTimeoutError,
)

logger = logging.getLogger(__name__)


class FetchResult:
    __slots__ = ("html", "final_url", "method")

    def __init__(self, html: str, final_url: str, method: str):
        self.html = html
        self.final_url = final_url
        self.method = method


class FetchService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._browser_lock = asyncio.Lock()

    # ---------- public API ----------

    async def fetch(
        self,
        url: str,
        *,
        wait_for_selector: str | None = None,
        timeout_ms: int | None = None,
        force_browser: bool = False,
    ) -> FetchResult:
        timeout_ms = timeout_ms or self._settings.fetch_timeout_ms
        await self._guard_url(url)

        if not force_browser:
            result = await self._fetch_static(url, timeout_ms)
            if result is not None:
                return result
            logger.info("static fetch insufficient, falling back to browser: %s", url)

        return await self._fetch_browser(url, wait_for_selector, timeout_ms)

    async def aclose(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    # ---------- strategies ----------

    async def _fetch_static(self, url: str, timeout_ms: int) -> FetchResult | None:
        """Try plain HTTP first; return None if the page looks JS-rendered."""
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=timeout_ms / 1000,
                headers={"User-Agent": self._settings.user_agent},
            ) as client:
                response = await client.get(url)
        except httpx.TimeoutException as e:
            raise FetchTimeoutError(f"Timed out fetching {url}") from e
        except httpx.HTTPError as e:
            logger.info("static fetch failed (%s), will try browser", e)
            return None

        if response.status_code >= 400:
            logger.info("static fetch got HTTP %s, will try browser", response.status_code)
            return None

        content_type = response.headers.get("content-type", "")
        if "html" not in content_type:
            raise FetchError(f"Unsupported content type: {content_type or 'unknown'}")

        # Redirects may have moved us; re-check the landing host
        final_url = str(response.url)
        await self._guard_url(final_url)

        html = response.text
        if self._visible_text_length(html) < self._settings.static_fetch_min_text:
            return None  # likely a JS shell, needs rendering

        return FetchResult(html=html, final_url=final_url, method="static")

    async def _fetch_browser(
        self, url: str, wait_for_selector: str | None, timeout_ms: int
    ) -> FetchResult:
        browser = await self._get_browser()
        page = await browser.new_page(user_agent=self._settings.user_agent)
        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            if wait_for_selector:
                await page.wait_for_selector(wait_for_selector, timeout=timeout_ms)
            html = await page.content()
            final_url = page.url
        except PlaywrightTimeoutError as e:
            raise FetchTimeoutError(f"Timed out rendering {url}") from e
        except Exception as e:
            raise FetchError(f"Failed to render {url}: {e}") from e
        finally:
            await page.close()

        if not html or len(html.strip()) < 100:
            raise EmptyPageError(f"Rendered page is empty: {url}")
        return FetchResult(html=html, final_url=final_url, method="browser")

    async def _get_browser(self) -> Browser:
        async with self._browser_lock:
            if self._browser is None or not self._browser.is_connected():
                if self._playwright is None:
                    self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(headless=True)
            return self._browser

    # ---------- SSRF guard ----------

    async def _guard_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise BlockedUrlError(f"Only http/https URLs are allowed, got: {parsed.scheme}")
        if not parsed.hostname:
            raise BlockedUrlError("URL has no hostname")

        if not self._settings.block_private_addresses:
            return

        try:
            loop = asyncio.get_running_loop()
            infos = await loop.getaddrinfo(parsed.hostname, None)
        except OSError as e:
            raise FetchError(f"Cannot resolve host: {parsed.hostname}") from e

        for info in infos:
            address = ipaddress.ip_address(info[4][0])
            if (
                address.is_private
                or address.is_loopback
                or address.is_link_local
                or address.is_reserved
            ):
                raise BlockedUrlError(
                    f"Host {parsed.hostname} resolves to a non-public address and was blocked"
                )

    @staticmethod
    def _visible_text_length(html: str) -> int:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return len(soup.get_text(strip=True))
