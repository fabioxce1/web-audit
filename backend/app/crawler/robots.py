import logging
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser
import httpx

logger = logging.getLogger(__name__)


class RobotsChecker:
    def __init__(self, user_agent: str = "WebAudit/1.0"):
        self.user_agent = user_agent
        self._parsers: dict[str, RobotFileParser] = {}

    async def fetch(self, domain: str) -> RobotFileParser | None:
        if domain in self._parsers:
            return self._parsers[domain]

        robots_url = f"https://{domain}/robots.txt"
        rp = RobotFileParser()
        rp.allow_all = True

        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                response = await client.get(robots_url)
                if response.status_code == 200:
                    rp.parse(response.text.splitlines())
                    rp.allow_all = False
                else:
                    rp.allow_all = True
        except Exception as e:
            logger.warning(f"No se pudo obtener robots.txt para {domain}: {e}")
            rp.allow_all = True

        self._parsers[domain] = rp
        return rp

    async def is_allowed(self, url: str, domain: str) -> bool:
        rp = await self.fetch(domain)
        if rp.allow_all:
            return True
        return rp.can_fetch(self.user_agent, url)

    async def get_crawl_delay(self, domain: str) -> float | None:
        rp = await self.fetch(domain)
        if rp.allow_all:
            return None
        delay = rp.crawl_delay(self.user_agent)
        return delay if delay else None

    async def get_sitemaps(self, domain: str) -> list[str]:
        rp = await self.fetch(domain)
        if rp.allow_all:
            return []
        return list(rp.site_maps() or [])
