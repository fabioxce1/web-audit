import logging
from urllib.parse import urljoin
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class SitemapParser:
    def __init__(self):
        self._parsed: set[str] = set()

    async def fetch_urls(self, sitemap_url: str, domain: str, timeout: int = 30) -> list[str]:
        urls: list[str] = []
        self._parsed.clear()

        await self._parse(sitemap_url, urls, domain, timeout)
        return urls

    async def _parse(self, url: str, urls: list[str], domain: str, timeout: int):
        if url in self._parsed:
            return
        self._parsed.add(url)

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return

                content_type = response.headers.get("content-type", "")
                soup = BeautifulSoup(response.text, "xml" if "xml" in content_type else "lxml")

                sitemaps = soup.find_all("sitemap")
                if sitemaps:
                    for sm in sitemaps:
                        loc = sm.find("loc")
                        if loc and loc.text.strip():
                            await self._parse(loc.text.strip(), urls, domain, timeout)
                    return

                url_tags = soup.find_all("url")
                for url_tag in url_tags:
                    loc = url_tag.find("loc")
                    if loc and loc.text.strip():
                        urls.append(loc.text.strip())

        except Exception as e:
            logger.warning(f"Error parseando sitemap {url}: {e}")

    async def fetch_from_domain(self, domain: str, timeout: int = 30) -> list[str]:
        sitemap_url = f"https://{domain}/sitemap.xml"
        return await self.fetch_urls(sitemap_url, domain, timeout)
