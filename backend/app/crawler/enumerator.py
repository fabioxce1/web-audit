import asyncio
import logging
from urllib.parse import urlparse

import httpx

from app.crawler.normalizer import normalize_url, extract_domain, is_not_found_redirect
from app.crawler.dirlist import get_paths_for_domain
from app.models.url import DiscoveredURL
from sqlalchemy import select

logger = logging.getLogger(__name__)


class DirectoryEnumerator:
    def __init__(
        self,
        base_url: str,
        session_factory,
        session_id: int,
        max_workers: int = 10,
        timeout: int = 10,
        on_progress=None,
        already_seen: set[str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.session_factory = session_factory
        self.session_id = session_id
        self.max_workers = max_workers
        self.timeout = timeout
        self.on_progress = on_progress
        self.already_seen = already_seen or set()
        self._stop_requested = False
        self.domain = extract_domain(base_url)

    def _is_redirect_homepage(self, original_url: str, final_url: str, status_code: int) -> bool:
        if status_code in (301, 302, 303, 307, 308):
            return True

        original_path = urlparse(original_url).path.rstrip("/")
        final_path = urlparse(final_url).path.rstrip("/")

        if not original_path:
            return False

        if not final_path or final_path == "":
            return True

        if is_not_found_redirect(final_url):
            return True

        if final_path == "" and original_path != "":
            return True

        if final_path != original_path and original_path not in final_path and final_path not in original_path:
            final_domain = urlparse(final_url).netloc.lower().replace("www.", "")
            probe_domain = urlparse(original_url).netloc.lower().replace("www.", "")
            if final_domain == probe_domain:
                normalized_final = normalize_url(final_url)
                normalized_home = normalize_url(f"https://{self.domain}/")
                if normalized_final == normalized_home:
                    return True

        return False

    async def run(self):
        paths = get_paths_for_domain()
        urls_to_probe: list[str] = []

        for path in paths:
            full_url = f"https://{self.domain}{path}"
            normalized = normalize_url(full_url)
            if not normalized or normalized in self.already_seen:
                continue
            urls_to_probe.append(normalized)

        if not urls_to_probe:
            return set()

        logger.info(f"Enumerando {len(urls_to_probe)} paths en {self.domain}")

        found: set[str] = set()
        semaphore = asyncio.Semaphore(self.max_workers)

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=False,
            max_redirects=1,
            headers={
                "User-Agent": "WebAudit/1.0 (+https://github.com/webaudit)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            },
        ) as client:

            async def probe(url: str):
                if self._stop_requested:
                    return
                async with semaphore:
                    if self._stop_requested:
                        return

                    try:
                        resp = await client.head(url)

                        if resp.status_code in (301, 302, 303, 307, 308):
                            redirected_url = resp.headers.get("location", "")
                            if redirected_url:
                                from urllib.parse import urljoin
                                final_url = urljoin(url, redirected_url)

                                if is_not_found_redirect(final_url):
                                    return

                                try:
                                    resp2 = await client.get(final_url)
                                    if self._is_redirect_homepage(url, final_url, resp2.status_code):
                                        return
                                    if resp2.status_code >= 400:
                                        return
                                    status_code = resp2.status_code
                                    final_resolved = str(resp2.url)
                                    content_type = resp2.headers.get("content-type", "").split(";")[0].strip()
                                    content_length = len(resp2.content)
                                    redirect_url = final_url if final_url != url else None
                                except (httpx.TimeoutException, httpx.ConnectError):
                                    return
                                except Exception:
                                    return
                            else:
                                return
                        elif resp.status_code >= 400:
                            return
                        else:
                            status_code = resp.status_code
                            final_resolved = url
                            content_type = resp.headers.get("content-type", "").split(";")[0].strip()
                            content_length = int(resp.headers.get("content-length", 0))
                            redirect_url = None

                        if self._is_redirect_homepage(url, final_resolved, status_code):
                            return

                        found.add(url)

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
                                status_code=status_code,
                                content_type=content_type,
                                content_length=content_length,
                                discovery_method="enumeration",
                                is_broken=status_code >= 400,
                                redirect_url=redirect_url,
                            )
                            session.add(entry)
                            await session.commit()

                        if self.on_progress:
                            try:
                                await self.on_progress({
                                    "type": "url_discovered",
                                    "url": url,
                                    "total_found": len(found),
                                    "source": "enumeration",
                                })
                            except Exception:
                                pass

                    except (httpx.TimeoutException, httpx.ConnectError):
                        pass
                    except Exception as e:
                        logger.debug(f"Error probing {url}: {e}")

            tasks = [asyncio.create_task(probe(url)) for url in urls_to_probe]
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(f"Enumeración completada: {len(found)} paths encontrados de {len(urls_to_probe)} probados")
        return found

    async def stop(self):
        self._stop_requested = True