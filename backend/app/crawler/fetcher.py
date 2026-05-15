import time
import logging
from pathlib import Path
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    logger.warning("Playwright no instalado. Solo se usará HTTP fetcher.")


class Fetcher:
    def __init__(self, user_agent: str = None, timeout: int = None, use_playwright: bool = None):
        self.user_agent = user_agent or settings.user_agent
        self.timeout = timeout or settings.timeout
        self.use_playwright = use_playwright if use_playwright is not None else settings.use_playwright
        self._playwright = None
        self._browser = None
        self._context = None

    async def _ensure_playwright(self):
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright no está instalado")

        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=settings.headless
            )
            self._context = await self._browser.new_context(
                user_agent=self.user_agent,
                viewport={"width": settings.viewport_width, "height": settings.viewport_height},
            )

    async def fetch_http(self, url: str) -> dict:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        }

        redirect_chain = []
        start_time = time.monotonic()

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=False,
                headers=headers,
            ) as client:
                current_url = url
                for _ in range(settings.max_redirects):
                    response = await client.get(current_url)
                    status = response.status_code

                    if status in (301, 302, 303, 307, 308):
                        location = response.headers.get("location", "")
                        if not location:
                            break
                        from urllib.parse import urljoin
                        redirect_to = urljoin(current_url, location)
                        redirect_chain.append({"from": current_url, "to": redirect_to, "status": status})
                        current_url = redirect_to
                        continue

                    elapsed_ms = int((time.monotonic() - start_time) * 1000)

                    return {
                        "url": current_url,
                        "status_code": status,
                        "content_type": response.headers.get("content-type", "").split(";")[0].strip(),
                        "html": response.text if "text/html" in response.headers.get("content-type", "") else "",
                        "headers": dict(response.headers),
                        "content_length": len(response.content),
                        "redirect_chain": redirect_chain,
                        "response_time_ms": elapsed_ms,
                        "error": None,
                    }

                elapsed_ms = int((time.monotonic() - start_time) * 1000)
                return {
                    "url": url,
                    "status_code": 0,
                    "content_type": "",
                    "html": "",
                    "headers": {},
                    "content_length": 0,
                    "redirect_chain": redirect_chain,
                    "response_time_ms": elapsed_ms,
                    "error": "Too many redirects",
                }

        except httpx.TimeoutException:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            return self._error_result(url, "Timeout", elapsed_ms)
        except httpx.ConnectError:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            return self._error_result(url, "Connection failed", elapsed_ms)
        except Exception as e:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            return self._error_result(url, str(e), elapsed_ms)

    async def fetch_playwright(self, url: str) -> dict:
        if not PLAYWRIGHT_AVAILABLE:
            return await self.fetch_http(url)

        await self._ensure_playwright()

        start_time = time.monotonic()
        page = await self._context.new_page()

        try:
            response = await page.goto(url, wait_until="networkidle", timeout=self.timeout * 1000)

            status = response.status if response else 0
            content_type = response.headers.get("content-type", "") if response else ""
            content_type_clean = content_type.split(";")[0].strip()

            html = await page.content()
            title = await page.title()

            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            return {
                "url": url,
                "status_code": status,
                "content_type": content_type_clean,
                "html": html,
                "title": title,
                "headers": dict(response.headers) if response else {},
                "content_length": len(html),
                "redirect_chain": [],
                "response_time_ms": elapsed_ms,
                "error": None,
            }

        except Exception as e:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            return self._error_result(url, str(e), elapsed_ms)
        finally:
            await page.close()

    async def fetch(self, url: str, use_playwright: bool = None) -> dict:
        use_pw = use_playwright if use_playwright is not None else self.use_playwright
        if use_pw:
            return await self.fetch_playwright(url)
        return await self.fetch_http(url)

    def _error_result(self, url: str, error: str, elapsed_ms: int) -> dict:
        return {
            "url": url,
            "status_code": 0,
            "content_type": "",
            "html": "",
            "headers": {},
            "content_length": 0,
            "redirect_chain": [],
            "response_time_ms": elapsed_ms,
            "error": error,
        }

    async def close(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._context = None
        self._browser = None
        self._playwright = None
