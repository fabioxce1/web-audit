import re
import logging
from urllib.parse import urlparse, urljoin
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.config import settings

logger = logging.getLogger(__name__)

META_CHECK_RULES = {
    "title": {
        "check": "Meta Title",
        "severity": "critical",
        "min_len": 30,
        "max_len": 60,
        "recommendation": "El título debe tener entre 30 y 60 caracteres, ser único por página, e incluir la keyword principal al inicio.",
    },
    "description": {
        "check": "Meta Description",
        "severity": "warning",
        "min_len": 70,
        "max_len": 160,
        "recommendation": "La meta description debe tener entre 70 y 160 caracteres, ser descriptiva y contener un call-to-action.",
    },
    "keywords": {
        "check": "Meta Keywords",
        "severity": "info",
        "recommendation": "Las meta keywords ya no son usadas por Google. Se recomienda no usarlas o eliminarlas.",
    },
    "robots": {
        "check": "Meta Robots",
        "severity": "info",
        "recommendation": "El meta robots debe usarse solo si se quiere restringir indexación. Verificar que no bloquee accidentalmente.",
    },
    "viewport": {
        "check": "Meta Viewport",
        "severity": "critical",
        "recommendation": "El meta viewport es esencial para responsive design. Debe ser: width=device-width, initial-scale=1",
    },
}


class SeoScanner:
    def __init__(self, session_factory, project_id: int, scan_id: int, on_progress=None):
        self.session_factory = session_factory
        self.project_id = project_id
        self.scan_id = scan_id
        self.on_progress = on_progress
        self._stop_requested = False
        self._checks: list[dict] = []
        self._urls_scanned = 0
        self._client = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=15, follow_redirects=True, max_redirects=5,
                headers={"User-Agent": settings.user_agent},
            )
        return self._client

    async def _close_client(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _add_check(self, url: str, category: str, check_name: str, severity: str,
                   passed: bool, value_found: str = "", value_expected: str = "",
                   recommendation: str = "", score_impact: int = 0, url_id: int | None = None):
        self._checks.append({
            "url": url, "url_id": url_id, "category": category,
            "check_name": check_name, "severity": severity, "passed": passed,
            "value_found": value_found, "value_expected": value_expected,
            "recommendation": recommendation, "score_impact": score_impact,
        })

    async def run(self):
        from app.models.seo import SeoScan, SeoCheck
        from app.models.url import DiscoveredURL
        from app.models.project import CrawlSession
        from sqlalchemy import select

        try:
            async with self.session_factory() as session:
                scan = await session.get(SeoScan, self.scan_id)
                if scan:
                    scan.status = "running"
                    scan.started_at = datetime.utcnow()
                    await session.commit()

            await self._emit_progress({"type": "seo_scan_started"})

            async with self.session_factory() as session:
                crawl_result = await session.execute(
                    select(CrawlSession)
                    .where(CrawlSession.project_id == self.project_id)
                    .order_by(CrawlSession.started_at.desc())
                    .limit(1)
                )
                crawl_session = crawl_result.scalar_one_or_none()

                urls_to_scan = []
                if crawl_session:
                    urls_result = await session.execute(
                        select(DiscoveredURL)
                        .where(DiscoveredURL.session_id == crawl_session.id)
                        .where(DiscoveredURL.is_broken == False)
                        .where(DiscoveredURL.content_type.ilike("%text/html%"))
                    )
                    urls_to_scan = urls_result.scalars().all()

                for url_obj in urls_to_scan:
                    if self._stop_requested:
                        break
                    await self._scan_page(url_obj.url, url_obj.id)
                    self._urls_scanned += 1
                    await self._emit_progress({
                        "type": "seo_scan_progress",
                        "urls_scanned": self._urls_scanned,
                        "total_checks": len(self._checks),
                    })

            score = self._calculate_score()

            severity_counts = {"critical": 0, "warning": 0, "good": 0, "info": 0}
            for check in self._checks:
                sev = check.get("severity", "info")
                severity_counts[sev] = severity_counts.get(sev, 0) + 1

            async with self.session_factory() as session:
                scan = await session.get(SeoScan, self.scan_id)
                if scan:
                    scan.status = "completed"
                    scan.urls_scanned = self._urls_scanned
                    scan.total_checks = len(self._checks)
                    scan.critical_count = severity_counts.get("critical", 0)
                    scan.warning_count = severity_counts.get("warning", 0)
                    scan.good_count = severity_counts.get("good", 0)
                    scan.info_count = severity_counts.get("info", 0)
                    scan.score = score
                    scan.completed_at = datetime.utcnow()
                    await session.commit()

                for check_data in self._checks:
                    db_check = SeoCheck(
                        scan_id=self.scan_id,
                        url=check_data["url"],
                        url_id=check_data.get("url_id"),
                        category=check_data["category"],
                        check_name=check_data["check_name"],
                        severity=check_data["severity"],
                        value_found=check_data.get("value_found", ""),
                        value_expected=check_data.get("value_expected", ""),
                        score_impact=check_data.get("score_impact", 0),
                        recommendation=check_data.get("recommendation", ""),
                        passed=1 if check_data.get("passed") else 0,
                    )
                    session.add(db_check)
                await session.commit()

            await self._emit_progress({
                "type": "seo_scan_completed",
                "total_checks": len(self._checks),
                "score": score,
            })

        except Exception as e:
            logger.error(f"Error en escaneo SEO: {e}", exc_info=True)
            async with self.session_factory() as session:
                scan = await session.get(SeoScan, self.scan_id)
                if scan:
                    scan.status = "failed"
                    await session.commit()
        finally:
            await self._close_client()

    async def _scan_page(self, url: str, url_id: int | None = None):
        client = await self._get_client()
        try:
            resp = await client.get(url)
            html = resp.text

            if "text/html" not in resp.headers.get("Content-Type", ""):
                return

            soup = BeautifulSoup(html, "lxml")

            self._check_meta_tags(url, soup, url_id)
            self._check_open_graph(url, soup, url_id)
            self._check_twitter_cards(url, soup, url_id)
            self._check_canonical(url, soup, url_id)
            self._check_headings(url, soup, url_id)
            self._check_images(url, soup, url_id)
            self._check_content(url, soup, html, url_id)
            self._check_structured_data(url, soup, url_id)
            self._check_performance(url, resp, len(html), url_id)
            self._check_links(url, soup, url_id)

        except Exception as e:
            logger.debug(f"Error escaneando SEO de {url}: {e}")

    def _check_meta_tags(self, url: str, soup: BeautifulSoup, url_id: int | None):
        title_tag = soup.find("title")
        title_text = title_tag.get_text(strip=True) if title_tag else ""

        if not title_text:
            self._add_check(url, "meta", "Meta Title", "critical", False,
                          "Ausente", "Título de página presente y único",
                          META_CHECK_RULES["title"]["recommendation"], score_impact=10)
        elif len(title_text) < META_CHECK_RULES["title"]["min_len"]:
            self._add_check(url, "meta", "Meta Title demasiado corto", "warning", False,
                          f"{len(title_text)} caracteres: '{title_text[:80]}'",
                          f"Al menos {META_CHECK_RULES['title']['min_len']} caracteres",
                          META_CHECK_RULES["title"]["recommendation"], score_impact=3)
        elif len(title_text) > META_CHECK_RULES["title"]["max_len"]:
            self._add_check(url, "meta", "Meta Title demasiado largo", "warning", False,
                          f"{len(title_text)} caracteres: '{title_text[:80]}'",
                          f"Máximo {META_CHECK_RULES['title']['max_len']} caracteres",
                          META_CHECK_RULES["title"]["recommendation"], score_impact=3)
        else:
            self._add_check(url, "meta", "Meta Title", "good", True,
                          f"{len(title_text)} caracteres: '{title_text[:80]}'",
                          f"Entre {META_CHECK_RULES['title']['min_len']}-{META_CHECK_RULES['title']['max_len']} caracteres",
                          "", score_impact=0)

        desc_tag = soup.find("meta", attrs={"name": "description"})
        desc = desc_tag.get("content", "") if desc_tag else ""

        if not desc:
            self._add_check(url, "meta", "Meta Description", "warning", False,
                          "Ausente", "Meta description presente y descriptiva",
                          META_CHECK_RULES["description"]["recommendation"], score_impact=5)
        elif len(desc) < META_CHECK_RULES["description"]["min_len"]:
            self._add_check(url, "meta", "Meta Description corta", "warning", False,
                          f"{len(desc)} caracteres", f"Al menos {META_CHECK_RULES['description']['min_len']} caracteres",
                          META_CHECK_RULES["description"]["recommendation"], score_impact=2)
        elif len(desc) > META_CHECK_RULES["description"]["max_len"]:
            self._add_check(url, "meta", "Meta Description larga", "info", False,
                          f"{len(desc)} caracteres", f"Máximo {META_CHECK_RULES['description']['max_len']} caracteres",
                          META_CHECK_RULES["description"]["recommendation"], score_impact=1)
        else:
            self._add_check(url, "meta", "Meta Description", "good", True,
                          f"{len(desc)} caracteres", "Entre 70-160 caracteres", "", score_impact=0)

        viewport = soup.find("meta", attrs={"name": "viewport"})
        if not viewport:
            self._add_check(url, "meta", "Meta Viewport", "critical", False,
                          "Ausente", "Meta viewport presente",
                          META_CHECK_RULES["viewport"]["recommendation"], score_impact=8)
        elif "width=device-width" in (viewport.get("content", "")):
            self._add_check(url, "meta", "Meta Viewport", "good", True,
                          "Presente y correcto", "width=device-width, initial-scale=1", "", score_impact=0)
        else:
            self._add_check(url, "meta", "Meta Viewport incorrecto", "critical", False,
                          viewport.get("content", ""), "width=device-width, initial-scale=1",
                          META_CHECK_RULES["viewport"]["recommendation"], score_impact=8)

        robots = soup.find("meta", attrs={"name": "robots"})
        robots_content = robots.get("content", "") if robots else ""
        if robots_content and ("noindex" in robots_content.lower() or "nofollow" in robots_content.lower()):
            self._add_check(url, "meta", "Meta Robots — Página bloqueada", "warning", False,
                          robots_content, "Index, Follow para páginas públicas",
                          "Esta página tiene noindex/nofollow y no será indexada. Si es intencional, ignorar.", score_impact=4)

    def _check_open_graph(self, url: str, soup: BeautifulSoup, url_id: int | None):
        og_tags = {
            "og:title": soup.find("meta", property="og:title"),
            "og:description": soup.find("meta", property="og:description"),
            "og:image": soup.find("meta", property="og:image"),
            "og:url": soup.find("meta", property="og:url"),
            "og:type": soup.find("meta", property="og:type"),
        }

        missing = [k for k, v in og_tags.items() if not v]
        present = [k for k, v in og_tags.items() if v]

        if missing:
            self._add_check(url, "og", "Open Graph — Tags faltantes", "warning", False,
                          f"Faltan: {', '.join(missing)}; Presentes: {len(present)}/5",
                          "Todos los tags OG básicos presentes (og:title, og:description, og:image, og:url, og:type)",
                          "Agregar meta tags Open Graph para mejorar la apariencia al compartir en redes sociales (Facebook, LinkedIn, WhatsApp).",
                          score_impact=4)
        else:
            og_image = og_tags["og:image"].get("content", "")
            self._add_check(url, "og", "Open Graph — Completo", "good", True,
                          f"5/5 tags OG presentes (imagen: {'Sí' if og_image else 'URL vacía'})",
                          "5/5 tags OG básicos presentes", "", score_impact=0)

    def _check_twitter_cards(self, url: str, soup: BeautifulSoup, url_id: int | None):
        twitter_tags = {
            "twitter:card": soup.find("meta", attrs={"name": "twitter:card"}),
            "twitter:title": soup.find("meta", attrs={"name": "twitter:title"}),
            "twitter:description": soup.find("meta", attrs={"name": "twitter:description"}),
            "twitter:image": soup.find("meta", attrs={"name": "twitter:image"}),
        }

        missing = [k for k, v in twitter_tags.items() if not v]
        present = [k for k, v in twitter_tags.items() if v]

        if missing:
            self._add_check(url, "social", "Twitter Cards — Tags faltantes", "info", False,
                          f"Faltan: {', '.join(missing)}; Presentes: {len(present)}/4",
                          "Twitter Card tags completos",
                          "Agregar meta tags Twitter Card para mejorar la previsualización al compartir en X/Twitter.",
                          score_impact=2)
        else:
            self._add_check(url, "social", "Twitter Cards — Completo", "good", True,
                          "4/4 tags Twitter Card presentes",
                          "4/4 tags Twitter Card", "", score_impact=0)

    def _check_canonical(self, url: str, soup: BeautifulSoup, url_id: int | None):
        canonical = soup.find("link", rel="canonical")
        if not canonical:
            self._add_check(url, "technical", "Canonical URL ausente", "warning", False,
                          "No se encontró canonical link",
                          "Etiqueta canonical presente",
                          "Agregar <link rel='canonical' href='...'> para evitar contenido duplicado. Apuntar a la URL preferida.",
                          score_impact=4)
        else:
            canonical_url = canonical.get("href", "")
            self._add_check(url, "technical", "Canonical URL", "good", True,
                          canonical_url[:150], "URL canónica correcta", "", score_impact=0)

    def _check_headings(self, url: str, soup: BeautifulSoup, url_id: int | None):
        h1_tags = soup.find_all("h1")
        h2_tags = soup.find_all("h2")
        h3_tags = soup.find_all("h3")
        h4_tags = soup.find_all("h4")

        if len(h1_tags) == 0:
            self._add_check(url, "headings", "H1 — Ausente", "critical", False,
                          "No se encontró ningún H1",
                          "Exactamente un H1 por página",
                          "Agregar un H1 único que describa el contenido principal de la página. Usar la keyword principal.",
                          score_impact=10)
        elif len(h1_tags) > 1:
            h1_texts = [h.get_text(strip=True)[:50] for h in h1_tags]
            self._add_check(url, "headings", "H1 — Múltiples", "warning", False,
                          f"Se encontraron {len(h1_tags)} H1s: {'; '.join(h1_texts[:3])}",
                          "Exactamente un H1 por página",
                          "Usar un solo H1 por página. Los demás headings deben ser H2, H3, etc.",
                          score_impact=5)
        else:
            h1_text = h1_tags[0].get_text(strip=True)[:80]
            if len(h1_text) < 10:
                self._add_check(url, "headings", "H1 — Demasiado corto", "warning", False,
                              f"'{h1_text}' ({len(h1_text)} caracteres)",
                              "H1 descriptivo de al menos 10 caracteres",
                              "El H1 debe describir claramente el contenido de la página.",
                              score_impact=3)
            else:
                self._add_check(url, "headings", "H1", "good", True,
                              f"'{h1_text}'", "Un H1 descriptivo", "", score_impact=0)

        if len(h2_tags) == 0:
            self._add_check(url, "headings", "H2 — Sin subencabezados", "info", False,
                          "No se encontraron H2s",
                          "Usar H2s para estructurar el contenido",
                          "Agregar H2s para dividir el contenido en secciones y mejorar la legibilidad.",
                          score_impact=2)

        total_headings = len(h1_tags) + len(h2_tags) + len(h3_tags) + len(h4_tags)
        if total_headings > 0:
            self._add_check(url, "headings", "Jerarquía de Headings", "info", True,
                          f"H1: {len(h1_tags)}, H2: {len(h2_tags)}, H3: {len(h3_tags)}, H4: {len(h4_tags)}",
                          "Estructura jerárquica correcta", "", score_impact=0)

    def _check_images(self, url: str, soup: BeautifulSoup, url_id: int | None):
        images = soup.find_all("img")
        if not images:
            return

        missing_alt = [img.get("src", "")[:60] for img in images if not img.get("alt")]
        total = len(images)

        if missing_alt:
            pct = round(len(missing_alt) / total * 100)
            severity = "critical" if pct > 50 else "warning" if pct > 20 else "info"
            self._add_check(url, "images", f"Imágenes sin alt — {len(missing_alt)}/{total} ({pct}%)",
                          severity, False,
                          f"{len(missing_alt)} imágenes sin alt text",
                          "Todas las imágenes con alt text descriptivo",
                          "Agregar atributo alt descriptivo a todas las imágenes para accesibilidad y SEO de imágenes.",
                          score_impact=5 if pct > 50 else 3)
        else:
            self._add_check(url, "images", f"Alt text — {total} imágenes OK", "good", True,
                          f"Todas las {total} imágenes tienen alt text",
                          "Alt text presente en todas las imágenes", "", score_impact=0)

        lazy_loaded = sum(1 for img in images if img.get("loading") == "lazy")
        if total > 3 and lazy_loaded == 0:
            self._add_check(url, "images", "Imágenes sin lazy loading", "info", False,
                          "Ninguna imagen usa loading='lazy'",
                          "Usar loading='lazy' para imágenes below-the-fold",
                          "Agregar loading='lazy' a imágenes que no están en el viewport inicial para mejorar LCP.",
                          score_impact=1)

    def _check_content(self, url: str, soup: BeautifulSoup, html: str, url_id: int | None):
        body = soup.find("body")
        if not body:
            return

        for tag in body.find_all(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()

        text = body.get_text(separator=" ", strip=True)
        words = text.split()
        word_count = len(words)

        if word_count < 100:
            self._add_check(url, "content", "Contenido escaso (Thin Content)", "critical", False,
                          f"Solo {word_count} palabras en el cuerpo de la página",
                          "Al menos 300 palabras de contenido sustancial",
                          "Agregar contenido de calidad. Google penaliza páginas con thin content. Apuntar a 300+ palabras.",
                          score_impact=10)
        elif word_count < 300:
            self._add_check(url, "content", "Contenido limitado", "warning", False,
                          f"{word_count} palabras en el cuerpo",
                          "300+ palabras de contenido",
                          "Ampliar el contenido a al menos 300 palabras con información valiosa y original.",
                          score_impact=5)
        elif word_count < 600:
            self._add_check(url, "content", "Contenido adecuado", "good", True,
                          f"{word_count} palabras", "300+ palabras", "", score_impact=0)
        else:
            self._add_check(url, "content", "Contenido extenso", "good", True,
                          f"{word_count} palabras", "300+ palabras", "", score_impact=0)

    def _check_structured_data(self, url: str, soup: BeautifulSoup, url_id: int | None):
        json_ld = soup.find_all("script", type="application/ld+json")
        microdata = soup.find_all(attrs={"itemtype": True})

        if json_ld or microdata:
            types_found = []
            for ld in json_ld:
                ld_text = ld.string or ""
                types_found.extend(re.findall(r'@type["\']\s*:\s*["\']([^"\']+)["\']', ld_text))
            for md in microdata:
                itemtype = md.get("itemtype", "")
                if itemtype:
                    types_found.append(itemtype.split("/")[-1])

            types_str = ", ".join(types_found[:5]) if types_found else "presente"
            self._add_check(url, "structured", "Structured Data — Detectada", "good", True,
                          types_str, "Datos estructurados presentes",
                          "", score_impact=0)
        else:
            self._add_check(url, "structured", "Structured Data — Ausente", "info", False,
                          "No se detectó JSON-LD ni Microdata",
                          "Datos estructurados (JSON-LD) implementados",
                          "Implementar JSON-LD structured data para rich snippets en Google (Organization, Article, Product, FAQ, etc.).",
                          score_impact=2)

    def _check_performance(self, url: str, resp, content_length: int, url_id: int | None):
        if content_length > 0:
            kb = round(content_length / 1024, 1)
            if kb > 500:
                self._add_check(url, "performance", "Tamaño de página excesivo", "warning", False,
                              f"{kb} KB", "Idealmente < 200 KB",
                              "Reducir el tamaño de la página optimizando imágenes, minificando CSS/JS y eliminando recursos innecesarios.",
                              score_impact=4)
            elif kb > 200:
                self._add_check(url, "performance", "Tamaño de página moderado", "info", False,
                              f"{kb} KB", "Idealmente < 200 KB",
                              "Considerar reducir el tamaño de la página para mejorar velocidad de carga.",
                              score_impact=2)
            else:
                self._add_check(url, "performance", "Tamaño de página", "good", True,
                              f"{kb} KB", "< 200 KB", "", score_impact=0)

        response_time = resp.elapsed.total_seconds() if hasattr(resp, 'elapsed') else 0
        if response_time > 3:
            self._add_check(url, "performance", "Tiempo de respuesta lento", "critical", False,
                          f"{response_time:.2f}s", "Menos de 1 segundo",
                          "Optimizar el servidor y la aplicación. Considerar caching, CDN, y optimización de base de datos.",
                          score_impact=8)
        elif response_time > 1:
            self._add_check(url, "performance", "Tiempo de respuesta moderado", "warning", False,
                          f"{response_time:.2f}s", "Menos de 1 segundo",
                          "Mejorar el tiempo de respuesta con caching y optimización de backend.",
                          score_impact=4)
        else:
            self._add_check(url, "performance", "Tiempo de respuesta", "good", True,
                          f"{response_time:.2f}s", "< 1 segundo", "", score_impact=0)

    def _check_links(self, url: str, soup: BeautifulSoup, url_id: int | None):
        links = soup.find_all("a", href=True)
        if not links:
            return

        absolute_links = 0
        relative_links = 0
        for link in links:
            href = link.get("href", "")
            if href.startswith(("http://", "https://")):
                absolute_links += 1
            elif not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                relative_links += 1

        total = absolute_links + relative_links
        if total > 0:
            pct_absolute = round(absolute_links / total * 100)
            if pct_absolute > 80:
                pass
            else:
                self._add_check(url, "technical", "Links relativos vs absolutos", "info", True,
                              f"Absolutos: {absolute_links}, Relativos: {relative_links}",
                              "Links absolutos para evitar canonicalización incorrecta",
                              "", score_impact=0)

            nofollow_links = len(soup.find_all("a", rel=re.compile(r"nofollow")))
            external_links = [l for l in links if l.get("href", "").startswith(("http://", "https://"))
                            and urlparse(l.get("href", "")).netloc != urlparse(url).netloc]
            external_no_nofollow = [l for l in external_links if "nofollow" not in (l.get("rel", "") or "")]
            if external_no_nofollow:
                self._add_check(url, "technical", "Links externos sin nofollow", "info", False,
                              f"{len(external_no_nofollow)} links externos sin rel='nofollow'",
                              "Links externos con rel='nofollow' o rel='sponsored'",
                              "Agregar rel='nofollow' o rel='sponsored' a links externos para no transferir PageRank.",
                              score_impact=1)

    def _calculate_score(self) -> int:
        max_score = 100
        total_impact = 0
        seen_checks: set[str] = set()

        for check in self._checks:
            if check.get("passed"):
                continue
            key = f"{check['category']}:{check['check_name']}"
            if key in seen_checks:
                continue
            seen_checks.add(key)
            total_impact += check.get("score_impact", 0)

        return max(0, max_score - min(total_impact, 90))

    async def stop(self):
        self._stop_requested = True

    async def _emit_progress(self, data: dict):
        if self.on_progress:
            try:
                await self.on_progress(data)
            except Exception:
                pass