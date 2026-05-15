import asyncio
import datetime
import hashlib
import logging
import json
from pathlib import Path
from urllib.parse import urlparse
from sqlalchemy import select, update

from app.config import settings
from app.crawler.fetcher import Fetcher
from app.crawler.parser import Parser
from app.crawler.robots import RobotsChecker
from app.crawler.sitemap import SitemapParser
from app.crawler.normalizer import normalize_url, is_internal_url, extract_domain, is_crawlable, is_path_excluded, is_not_found_redirect
from app.crawler.enumerator import DirectoryEnumerator
from app.models.url import DiscoveredURL
from app.models.project import Project, CrawlSession, ProjectStatus, CrawlSessionStatus

logger = logging.getLogger(__name__)


ProgressCallback = callable


class CrawlerEngine:
    def __init__(
        self,
        session_factory,
        project_id: int,
        session_id: int,
        config: dict = None,
        on_progress: ProgressCallback = None,
    ):
        self.session_factory = session_factory
        self.project_id = project_id
        self.session_id = session_id
        self.config = config or {}
        self.on_progress = on_progress

        self.max_workers = self.config.get("max_workers", settings.max_workers)
        self.crawl_delay = self.config.get("crawl_delay", settings.crawl_delay)
        self.respect_robots = self.config.get("respect_robots_txt", settings.respect_robots_txt)
        self.use_playwright = self.config.get("use_playwright", settings.use_playwright)
        self.timeout = self.config.get("timeout", settings.timeout)
        self.max_urls = self.config.get("max_urls", settings.max_urls)
        self.max_depth = self.config.get("max_depth", settings.max_depth)
        self.save_snapshots = self.config.get("save_html_snapshots", settings.save_html_snapshots)
        self.crawl_assets = self.config.get("crawl_assets", False)
        self.exclude_patterns = self.config.get("exclude_patterns", settings.exclude_patterns)
        self.enumerate_dirs = self.config.get("enumerate_dirs", settings.enumerate_dirs)

        self.queue: asyncio.Queue = asyncio.Queue()
        self.seen: set[str] = set()
        self._running = False
        self._paused = False
        self._stop_requested = False
        self._workers: list[asyncio.Task] = []
        self._stats = {"urls_found": 0, "urls_crawled": 0, "errors": 0}
        self._content_hashes: set[str] = set()
        self._stop_event = asyncio.Event()

        self.fetcher: Fetcher = None
        self.robots: RobotsChecker = None
        self.domain: str = ""

    async def run(self, seed_url: str):
        self._running = True
        self._stop_event.clear()
        self.domain = extract_domain(seed_url)
        self.fetcher = Fetcher(
            user_agent=self.config.get("user_agent", settings.user_agent),
            timeout=self.timeout,
            use_playwright=self.use_playwright,
        )
        self.robots = RobotsChecker(
            user_agent=self.config.get("user_agent", settings.user_agent)
        )

        await self._update_session_status(CrawlSessionStatus.running)
        await self._update_project_status(ProjectStatus.crawling)

        await self._emit_progress({"type": "crawl_started", "seed_url": seed_url, "domain": self.domain})

        await self._discover_seed_urls(seed_url)

        self._workers = [
            asyncio.create_task(self._worker(i))
            for i in range(self.max_workers)
        ]

        try:
            await self.queue.join()
        except asyncio.CancelledError:
            pass

        for worker in self._workers:
            worker.cancel()
        self._workers.clear()

        if not self._stop_requested and self.enumerate_dirs:
            await self._emit_progress({"type": "enumeration_started", "domain": self.domain})
            try:
                enumerator = DirectoryEnumerator(
                    base_url=f"https://{self.domain}",
                    session_factory=self.session_factory,
                    session_id=self.session_id,
                    max_workers=10,
                    timeout=self.timeout,
                    on_progress=self.on_progress,
                    already_seen=self.seen,
                )
                enum_found = await enumerator.run()
                self._stats["urls_found"] += len(enum_found)
                await self._update_session_counts()
                await self._emit_progress({
                    "type": "enumeration_completed",
                    "found": len(enum_found),
                })
            except Exception as e:
                logger.error(f"Error en enumeración de directorios: {e}")

        final_status = CrawlSessionStatus.stopped if self._stop_requested else CrawlSessionStatus.completed
        await self._update_session_status(final_status, completed=True)
        await self._update_project_status(
            ProjectStatus.completed if final_status == CrawlSessionStatus.completed else ProjectStatus.idle
        )

        await self.fetcher.close()
        self._running = False

        await self._emit_progress({
            "type": "crawl_completed",
            "status": final_status.value,
            "stats": self._stats,
        })

    async def stop(self):
        self._running = False
        self._stop_requested = True
        self._stop_event.set()
        for worker in self._workers:
            worker.cancel()
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except asyncio.QueueEmpty:
                break

    async def pause(self):
        self._paused = True

    async def resume(self):
        self._paused = False

    async def _discover_seed_urls(self, seed_url: str):
        normalized = normalize_url(seed_url)
        await self._add_to_queue(normalized, depth=0, parent_url=None)

        try:
            sitemap_parser = SitemapParser()
            sitemap_urls = await sitemap_parser.fetch_from_domain(self.domain, self.timeout)
            for url in sitemap_urls:
                normalized = normalize_url(url)
                if normalized and normalized not in self.seen and is_internal_url(normalized, self.domain):
                    if not self.crawl_assets and not is_crawlable(normalized):
                        continue
                    if is_path_excluded(normalized, self.exclude_patterns):
                        continue
                    self.seen.add(normalized)
                    await self._add_to_queue(normalized, depth=0, parent_url="sitemap")

            if self.respect_robots:
                robots_sitemaps = await self.robots.get_sitemaps(self.domain)
                for sm_url in robots_sitemaps:
                    extra_urls = await sitemap_parser.fetch_urls(sm_url, self.domain, self.timeout)
                    for url in extra_urls:
                        normalized = normalize_url(url)
                        if normalized and normalized not in self.seen and is_internal_url(normalized, self.domain):
                            if not self.crawl_assets and not is_crawlable(normalized):
                                continue
                            if is_path_excluded(normalized, self.exclude_patterns):
                                continue
                            self.seen.add(normalized)
                            await self._add_to_queue(normalized, depth=0, parent_url="robots.txt")
        except Exception as e:
            logger.warning(f"Error descubriendo URLs semilla: {e}")

    async def _add_to_queue(self, url: str, depth: int, parent_url: str = None):
        if not self._running or self._stop_requested:
            return

        if self.max_depth > 0 and depth > self.max_depth:
            return

        if depth > 0 and is_path_excluded(url, self.exclude_patterns):
            return

        async with self.session_factory() as session:
            existing = await session.execute(
                select(DiscoveredURL).where(
                    DiscoveredURL.session_id == self.session_id,
                    DiscoveredURL.normalized_url == url,
                )
            )
            if existing.scalar_one_or_none():
                return

            entry = DiscoveredURL(
                session_id=self.session_id,
                url=url,
                normalized_url=url,
                depth=depth,
                parent_url=parent_url,
            )
            session.add(entry)
            await session.commit()

        await self.queue.put({"url": url, "depth": depth, "parent_url": parent_url})
        self._stats["urls_found"] += 1

        await self._emit_progress({
            "type": "url_discovered",
            "url": url,
            "total_found": self._stats["urls_found"],
        })

    async def _worker(self, worker_id: int):
        try:
            while self._running and not self._stop_requested:
                try:
                    item = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                except TimeoutError:
                    if self._stop_requested:
                        break
                    if self.queue.empty() and self._running:
                        continue
                    else:
                        break

                if self._paused:
                    await asyncio.sleep(0.5)
                    self.queue.task_done()
                    continue

                url = item["url"]
                depth = item["depth"]
                parent_url = item.get("parent_url")

                if self.respect_robots:
                    allowed = await self.robots.is_allowed(url, self.domain)
                    if not allowed:
                        self.queue.task_done()
                        continue

                    robots_delay = await self.robots.get_crawl_delay(self.domain)
                    delay = robots_delay if robots_delay else self.crawl_delay
                else:
                    delay = self.crawl_delay

                try:
                    await self._crawl_url(url, depth, parent_url)

                    if not self._stop_requested:
                        self._stats["urls_crawled"] += 1

                    await self._update_session_counts()

                    await self._emit_progress({
                        "type": "url_crawled",
                        "url": url,
                        "total_crawled": self._stats["urls_crawled"],
                        "total_found": self._stats["urls_found"],
                    })
                finally:
                    self.queue.task_done()

                if self._stop_requested:
                    break

                await asyncio.sleep(delay)

        except asyncio.CancelledError:
            pass

    async def _crawl_url(self, url: str, depth: int, parent_url: str = None):
        if self._stop_requested:
            return

        try:
            result = await self.fetcher.fetch(url)

            status_code = result.get("status_code", 0)
            is_error = status_code >= 400 or status_code == 0
            content_type = result.get("content_type", "")
            page_is_html = "text/html" in content_type

            redirect_chain = result.get("redirect_chain", [])
            redirect_url = None
            if redirect_chain:
                redirect_url = redirect_chain[-1].get("to")

            is_soft_404 = False
            if redirect_url and is_not_found_redirect(redirect_url):
                is_soft_404 = True
                is_error = True

            is_broken = is_error

            content_hash = None
            if page_is_html and result["html"] and not is_error:
                content_hash = hashlib.sha256(result["html"].encode("utf-8", errors="replace")).hexdigest()

            is_dup = content_hash and content_hash in self._content_hashes

            links = []
            title = ""
            if page_is_html and result["html"] and not is_dup and not is_error:
                links = Parser.extract_links(result["html"], url)
                title = Parser.extract_title(result["html"]) or result.get("title", "")
                if content_hash:
                    self._content_hashes.add(content_hash)

            snapshot_path = None
            if page_is_html and self.save_snapshots and result["html"] and not is_dup and not is_error:
                snapshot_path = self._save_snapshot(url, result["html"])

            async with self.session_factory() as session:
                stmt = (
                    update(DiscoveredURL)
                    .where(
                        DiscoveredURL.session_id == self.session_id,
                        DiscoveredURL.normalized_url == url,
                    )
                    .values(
                        status_code=status_code,
                        content_type=result["content_type"],
                        content_hash=content_hash,
                        is_duplicate=is_dup,
                        is_broken=is_broken,
                        redirect_url=redirect_url,
                        depth=depth,
                        parent_url=parent_url,
                        title=title,
                        html_snapshot_path=snapshot_path,
                        links_count=len(links),
                        crawled_at=datetime.datetime.utcnow(),
                        error_message=result.get("error"),
                        response_time_ms=result.get("response_time_ms"),
                        content_length=result.get("content_length"),
                    )
                )
                await session.execute(stmt)
                await session.commit()

            if is_broken:
                logger.info(f"Saltando links de URL rota ({status_code}): {url}")
                return

            if page_is_html and not self._stop_requested and not is_dup:
                for link in links:
                    if self._stop_requested:
                        break
                    if self.max_urls > 0 and self._stats["urls_found"] >= self.max_urls:
                        break

                    normalized = normalize_url(link)
                    if not normalized:
                        continue

                    if normalized in self.seen:
                        continue

                    if is_internal_url(normalized, self.domain):
                        if not self.crawl_assets and not is_crawlable(normalized):
                            continue

                        self.seen.add(normalized)
                        await self._add_to_queue(normalized, depth=depth + 1, parent_url=url)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            if not self._stop_requested:
                logger.error(f"Error crawleando {url}: {e}")
            self._stats["errors"] += 1

    def _save_snapshot(self, url: str, html: str) -> str | None:
        try:
            parsed = urlparse(url)
            filename = parsed.netloc.replace(":", "_") + parsed.path.replace("/", "_") or "_index"
            filename = filename[:200] + ".html"

            snapshot_dir = Path(settings.snapshot_dir) / str(self.session_id)
            snapshot_dir.mkdir(parents=True, exist_ok=True)

            filepath = snapshot_dir / filename
            filepath.write_text(html, encoding="utf-8")
            return str(filepath)
        except Exception as e:
            logger.warning(f"No se pudo guardar snapshot de {url}: {e}")
            return None

    async def _update_session_counts(self):
        async with self.session_factory() as session:
            await session.execute(
                update(CrawlSession)
                .where(CrawlSession.id == self.session_id)
                .values(
                    urls_found=self._stats["urls_found"],
                    urls_crawled=self._stats["urls_crawled"],
                )
            )
            await session.commit()

    async def _update_session_status(self, status: CrawlSessionStatus, completed: bool = False):
        async with self.session_factory() as session:
            values = {"status": status}
            if completed:
                values["completed_at"] = datetime.datetime.utcnow()
            await session.execute(
                update(CrawlSession).where(CrawlSession.id == self.session_id).values(**values)
            )
            await session.commit()

    async def _update_project_status(self, status: ProjectStatus):
        async with self.session_factory() as session:
            await session.execute(
                update(Project).where(Project.id == self.project_id).values(status=status)
            )
            await session.commit()

    async def _emit_progress(self, data: dict):
        if self.on_progress:
            try:
                await self.on_progress(data)
            except Exception as e:
                logger.error(f"Error en callback de progreso: {e}")
