import asyncio
import logging
import re
import ssl
import socket
from urllib.parse import urlparse, urljoin
from datetime import datetime

import httpx

from app.config import settings
from app.crawler.normalizer import extract_domain, normalize_url, is_not_found_redirect

logger = logging.getLogger(__name__)

SECURITY_HEADERS = {
    "content-security-policy": {
        "severity": "high",
        "check_name": "Content-Security-Policy",
        "recommendation": "Implementar CSP para prevenir ataques XSS y data injection. Usar: Content-Security-Policy: default-src 'self'",
        "expected": "Presente con directivas restrictivas",
    },
    "strict-transport-security": {
        "severity": "high",
        "check_name": "HSTS",
        "recommendation": "Implementar HSTS para forzar conexiones HTTPS. Usar: Strict-Transport-Security: max-age=31536000; includeSubDomains",
        "expected": "max-age >= 31536000 con includeSubDomains",
    },
    "x-frame-options": {
        "severity": "medium",
        "check_name": "X-Frame-Options",
        "recommendation": "Configurar X-Frame-Options para prevenir clickjacking. Preferible: Content-Security-Policy: frame-ancestors 'self'",
        "expected": "DENY o SAMEORIGIN",
    },
    "x-content-type-options": {
        "severity": "medium",
        "check_name": "X-Content-Type-Options",
        "recommendation": "Configurar X-Content-Type-Options: nosniff para prevenir MIME type sniffing",
        "expected": "nosniff",
    },
    "referrer-policy": {
        "severity": "low",
        "check_name": "Referrer-Policy",
        "recommendation": "Implementar Referrer-Policy para controlar información de referencia. Recomendado: Referrer-Policy: strict-origin-when-cross-origin",
        "expected": "strict-origin-when-cross-origin o no-referrer",
    },
    "permissions-policy": {
        "severity": "low",
        "check_name": "Permissions-Policy",
        "recommendation": "Implementar Permissions-Policy para restringir acceso a APIs del navegador (cámara, micrófono, geolocalización)",
        "expected": "Presente con políticas restrictivas",
    },
}

SENSITIVE_PATTERNS = [
    (re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', re.IGNORECASE), "email", "medium"),
    (re.compile(r'(?:api[_-]?key|apikey|access[_-]?token|secret[_-]?key|private[_-]?key)\s*[=:]\s*["\']?[a-zA-Z0-9+/=_-]{16,}', re.IGNORECASE), "api_key", "critical"),
    (re.compile(r'(?:password|passwd|pwd)\s*[=:]\s*["\']?[^\s"\'<>{]{8,}', re.IGNORECASE), "password", "critical"),
    (re.compile(r'(?:AKIA|ASIA)[A-Z0-9]{16}', re.IGNORECASE), "aws_key", "critical"),
    (re.compile(r'eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+', re.IGNORECASE), "jwt_token", "high"),
    (re.compile(r'(?:Bearer|token)\s+[a-zA-Z0-9\-._~+/]+=*', re.IGNORECASE), "bearer_token", "high"),
]

TECH_SIGNATURES = {
    "server": {
        "Apache": re.compile(r"apache", re.IGNORECASE),
        "Nginx": re.compile(r"nginx", re.IGNORECASE),
        "IIS": re.compile(r"microsoft-iis", re.IGNORECASE),
        "LiteSpeed": re.compile(r"litespeed", re.IGNORECASE),
        "Caddy": re.compile(r"caddy", re.IGNORECASE),
        "Cloudflare": re.compile(r"cloudflare", re.IGNORECASE),
    },
    "x-powered-by": {
        "PHP": re.compile(r"php", re.IGNORECASE),
        "Express": re.compile(r"express", re.IGNORECASE),
        "ASP.NET": re.compile(r"asp\.net", re.IGNORECASE),
        "Next.js": re.compile(r"next", re.IGNORECASE),
    },
    "html": {
        "WordPress": re.compile(r'<meta[^>]+content=["\']WordPress', re.IGNORECASE),
        "Joomla": re.compile(r'<meta[^>]+content=["\']Joomla', re.IGNORECASE),
        "Drupal": re.compile(r'<meta[^>]+content=["\']Drupal', re.IGNORECASE),
        "React": re.compile(r'react|react-dom|__NEXT__', re.IGNORECASE),
        "Vue.js": re.compile(r'vue\.js|vue\.min\.js|v-cloak', re.IGNORECASE),
        "Angular": re.compile(r'ng-version|angular\.js|angular\.min\.js', re.IGNORECASE),
        "jQuery": re.compile(r'jquery|jquery-\d', re.IGNORECASE),
        "Bootstrap": re.compile(r'bootstrap(\.min)?\.(css|js)', re.IGNORECASE),
        "Laravel": re.compile(r'laravel_session|laravel', re.IGNORECASE),
        "Tailwind CSS": re.compile(r'tailwind', re.IGNORECASE),
        "Google Analytics": re.compile(r'google-analytics\.com|gtag|GA-', re.IGNORECASE),
        "Google Tag Manager": re.compile(r'googletagmanager\.com|GTM-', re.IGNORECASE),
        "WooCommerce": re.compile(r'woocommerce', re.IGNORECASE),
        "Elementor": re.compile(r'elementor', re.IGNORECASE),
    },
}

WAF_SIGNATURES = {
    "Cloudflare": {
        "headers": ["cf-ray", "cf-cache-status", "cf-connecting-ip", "cloudflare-"],
        "cookies": ["__cfduid", "cf_clearance"],
        "body": ["cloudflare", "cf-browser-verification"],
    },
    "Sucuri": {
        "headers": ["x-sucuri-id", "x-sucuri-cache", "server: Sucuri"],
        "cookies": ["sucuri-cloudproxy"],
        "body": ["sucuri.net", "Sucuri WebSite Firewall"],
    },
    "ModSecurity": {
        "headers": ["server: ModSecurity", "x-mod-security"],
        "cookies": [],
        "body": ["ModSecurity", "mod_security"],
    },
    "AWS WAF": {
        "headers": ["x-amzn-requestid", "x-amz-cf-id"],
        "cookies": ["aws-waf-token"],
        "body": ["AWS WAF", "Request blocked"],
    },
    "Imperva/Incapsula": {
        "headers": ["x-iinfo", "x-cdn", "incap_ses"],
        "cookies": ["visid_incap", "incap_ses", "nlbi_"],
        "body": ["Incapsula", "Incapsula incident"],
    },
    "Akamai": {
        "headers": ["x-akamai-transformed", "x-cache", "akamai"],
        "cookies": ["akamai"],
        "body": [],
    },
    "F5 BIG-IP": {
        "headers": ["x-f5-"],
        "cookies": ["BIGipServer", "F5_httponly"],
        "body": ["F5 Networks", "BIG-IP"],
    },
    "Barracuda": {
        "headers": ["x-barracuda"],
        "cookies": ["BNI_persistence", "BARRACUDA"],
        "body": ["Barracuda", "barracudanetworks"],
    },
}

COMMON_PORT_DESCRIPTIONS = {
    21: "FTP",
    22: "SSH",
    25: "SMTP",
    80: "HTTP",
    110: "POP3",
    143: "IMAP",
    443: "HTTPS",
    465: "SMTPS",
    587: "SMTP Submission",
    993: "IMAPS",
    995: "POP3S",
    1433: "MSSQL",
    3306: "MySQL",
    3389: "RDP",
    5432: "PostgreSQL",
    6379: "Redis",
    8080: "HTTP Alt",
    8443: "HTTPS Alt",
    9200: "Elasticsearch",
    27017: "MongoDB",
}


class SecurityScanner:
    def __init__(self, session_factory, project_id: int, scan_id: int, on_progress=None):
        self.session_factory = session_factory
        self.project_id = project_id
        self.scan_id = scan_id
        self.on_progress = on_progress
        self._stop_requested = False
        self._checks: list[dict] = []
        self._seen_checks: set[str] = set()
        self._urls_scanned = 0
        self._client: httpx.AsyncClient | None = None
        self._domain = ""

    def _dedup_key(self, url: str, check_name: str) -> str:
        parsed = urlparse(url)
        domain_key = f"{parsed.netloc.lower()}:{check_name}"
        return domain_key

    def _add_check(self, url: str, category: str, check_name: str, severity: str,
                   passed: bool, value_found: str = "", value_expected: str = "",
                   recommendation: str = "", url_id: int | None = None,
                   dedup: bool = True):
        key = self._dedup_key(url, check_name)
        if dedup and key in self._seen_checks:
            return
        if dedup:
            self._seen_checks.add(key)
        self._checks.append({
            "url": url,
            "url_id": url_id,
            "category": category,
            "check_name": check_name,
            "severity": severity,
            "passed": passed,
            "value_found": value_found,
            "value_expected": value_expected,
            "recommendation": recommendation,
        })

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

    async def run(self, seed_url: str):
        from app.models.security import SecurityScan, SecurityCheck

        self._domain = extract_domain(seed_url)
        base_url = f"https://{self._domain}"

        try:
            async with self.session_factory() as session:
                scan = await session.get(SecurityScan, self.scan_id)
                if scan:
                    scan.status = "running"
                    scan.started_at = datetime.utcnow()
                    await session.commit()

            await self._emit_progress({"type": "security_scan_started", "domain": self._domain})

            await self._scan_headers(base_url)
            await self._scan_ssl(self._domain)
            await self._scan_cookies(base_url)
            await self._scan_info_disclosure(base_url)
            await self._scan_tech_detection(base_url)
            await self._scan_waf(base_url)
            await self._scan_cors(base_url)
            await self._scan_https_enforcement(self._domain)
            await self._scan_open_ports(self._domain)
            await self._scan_email_security(self._domain)
            await self._scan_access(base_url)

            async with self.session_factory() as session:
                from sqlalchemy import select
                from app.models.url import DiscoveredURL
                from app.models.project import CrawlSession

                crawl_result = await session.execute(
                    select(CrawlSession)
                    .where(CrawlSession.project_id == self.project_id)
                    .order_by(CrawlSession.started_at.desc())
                    .limit(1)
                )
                crawl_session = crawl_result.scalar_one_or_none()

                html_urls = []
                if crawl_session:
                    urls_result = await session.execute(
                        select(DiscoveredURL)
                        .where(DiscoveredURL.session_id == crawl_session.id)
                        .where(DiscoveredURL.is_broken == False)
                        .where(DiscoveredURL.content_type.ilike("%text/html%"))
                    )
                    html_urls = urls_result.scalars().all()

                    scan_limit = min(len(html_urls), 20)
                    for i, url_obj in enumerate(html_urls[:scan_limit]):
                        if self._stop_requested:
                            break
                        await self._scan_page_cookies(url_obj.url)
                        self._urls_scanned += 1
                        await self._emit_progress({
                            "type": "security_scan_progress",
                            "urls_scanned": self._urls_scanned,
                            "total_checks": len(self._checks),
                        })

            if not self._stop_requested and html_urls:
                await self._emit_progress({"type": "pentest_started"})
                try:
                    from app.pentest.scanner import PentestScanner
                    pentest = PentestScanner(
                        scanner_ref=self,
                        domain=self._domain,
                        base_url=f"https://{self._domain}",
                    )
                    await pentest.run_all(html_urls)
                    await pentest.close()
                    await self._emit_progress({
                        "type": "pentest_completed",
                        "total_checks": len(self._checks),
                    })
                except Exception as e:
                    logger.error(f"Error en pentest activo: {e}")

            score = self._calculate_score()

            severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
            for check in self._checks:
                sev = check.get("severity", "info")
                severity_counts[sev] = severity_counts.get(sev, 0) + 1

            async with self.session_factory() as session:
                scan = await session.get(SecurityScan, self.scan_id)
                if scan:
                    scan.status = "completed"
                    scan.urls_scanned = self._urls_scanned
                    scan.total_checks = len(self._checks)
                    scan.critical_count = severity_counts.get("critical", 0)
                    scan.high_count = severity_counts.get("high", 0)
                    scan.medium_count = severity_counts.get("medium", 0)
                    scan.low_count = severity_counts.get("low", 0)
                    scan.info_count = severity_counts.get("info", 0)
                    scan.score = score
                    scan.completed_at = datetime.utcnow()
                    await session.commit()

                for check_data in self._checks:
                    db_check = SecurityCheck(
                        scan_id=self.scan_id,
                        url=check_data["url"],
                        url_id=check_data.get("url_id"),
                        category=check_data["category"],
                        check_name=check_data["check_name"],
                        severity=check_data["severity"],
                        value_found=check_data.get("value_found", ""),
                        value_expected=check_data.get("value_expected", ""),
                        recommendation=check_data.get("recommendation", ""),
                        passed=1 if check_data.get("passed") else 0,
                    )
                    session.add(db_check)
                await session.commit()

            await self._emit_progress({
                "type": "security_scan_completed",
                "total_checks": len(self._checks),
                "score": score,
                "severity_counts": severity_counts,
            })

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error en escaneo de seguridad: {e}", exc_info=True)
            async with self.session_factory() as session:
                scan = await session.get(SecurityScan, self.scan_id)
                if scan:
                    scan.status = "failed"
                    await session.commit()
            await self._emit_progress({"type": "security_scan_error", "error": str(e)})
        finally:
            await self._close_client()

    async def stop(self):
        self._stop_requested = True

    # ─── Header Checks ───

    async def _scan_headers(self, url: str):
        client = await self._get_client()
        try:
            resp = await client.get(url)
            headers_lower = {k.lower(): v for k, v in resp.headers.items()}

            for header_name, config in SECURITY_HEADERS.items():
                value = headers_lower.get(header_name)
                if value:
                    passed = True
                    if header_name == "strict-transport-security":
                        match = re.search(r"max-age=(\d+)", value)
                        if match and int(match.group(1)) < 31536000:
                            passed = False
                        if "includesubdomains" not in value.lower():
                            passed = False
                    self._add_check(
                        url=url, category="headers", check_name=config["check_name"],
                        severity=config["severity"], passed=passed,
                        value_found=value, value_expected=config["expected"],
                        recommendation=config["recommendation"] if not passed else "",
                    )
                else:
                    self._add_check(
                        url=url, category="headers", check_name=config["check_name"],
                        severity=config["severity"], passed=False,
                        value_found="Ausente", value_expected=config["expected"],
                        recommendation=config["recommendation"],
                    )

            server = headers_lower.get("server", "")
            powered_by = headers_lower.get("x-powered-by", "")
            if server:
                self._add_check(
                    url=url, category="info_disclosure", check_name="Server Header Expuesto",
                    severity="low", passed=False, value_found=f"Server: {server}",
                    value_expected="Ocultar header Server",
                    recommendation="Remover o ofuscar el header Server para dificultar fingerprinting",
                )
            if powered_by:
                self._add_check(
                    url=url, category="info_disclosure", check_name="X-Powered-By Expuesto",
                    severity="medium", passed=False, value_found=f"X-Powered-By: {powered_by}",
                    value_expected="Ocultar header X-Powered-By",
                    recommendation="Remover el header X-Powered-By para no revelar tecnología del servidor",
                )
        except Exception as e:
            logger.debug(f"Error escaneando headers de {url}: {e}")

    # ─── SSL/TLS ───

    async def _scan_ssl(self, domain: str):
        url = f"https://{domain}"
        try:
            context = ssl.create_default_context()
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED

            sock = socket.create_connection((domain, 443), timeout=10)
            ssock = context.wrap_socket(sock, server_hostname=domain)
            cert = ssock.getpeercert()
            ssock.close()
            sock.close()

            expires_str = cert.get("notAfter", "")
            if expires_str:
                from datetime import datetime as dt
                try:
                    expires = dt.strptime(expires_str, "%b %d %H:%M:%S %Y %Z")
                    days_left = (expires - dt.utcnow()).days
                    if days_left < 30:
                        severity = "critical" if days_left < 7 else "high"
                        self._add_check(
                            url=url, category="ssl", check_name="Certificado SSL Próximo a Expirar",
                            severity=severity, passed=False,
                            value_found=f"Expira en {days_left} días ({expires_str})",
                            value_expected="Al menos 30 días antes de expiración",
                            recommendation="Renovar el certificado SSL antes de que expire",
                        )
                    else:
                        self._add_check(
                            url=url, category="ssl", check_name="Certificado SSL Válido",
                            severity="info", passed=True,
                            value_found=f"Expira en {days_left} días ({expires_str})",
                            value_expected="Certificado válido", recommendation="",
                        )
                except ValueError:
                    pass

            protocol = ssock.version() if hasattr(ssock, "version") else "unknown"
            if protocol and "1.2" not in protocol and "1.3" not in protocol:
                self._add_check(
                    url=url, category="ssl", check_name="Versión TLS Obsoleta",
                    severity="medium", passed=False,
                    value_found=f"TLS {protocol}", value_expected="TLS 1.2 o superior",
                    recommendation="Actualizar el servidor para usar TLS 1.2 o 1.3",
                )

            issuer = dict(cert.get("issuer", {}))
            issuer_name = issuer.get("commonName", issuer.get("organizationName", "Desconocido"))
            self._add_check(
                url=url, category="ssl", check_name="Emisor del Certificado",
                severity="info", passed=True,
                value_found=issuer_name, value_expected="Emisor confiable", recommendation="",
            )

        except ssl.SSLCertVerificationError as e:
            self._add_check(
                url=url, category="ssl", check_name="Certificado SSL Inválido",
                severity="critical", passed=False,
                value_found=str(e)[:200],
                value_expected="Certificado SSL válido y verificado",
                recommendation="Instalar un certificado SSL válido emitido por una CA reconocida",
            )
        except Exception as e:
            self._add_check(
                url=url, category="ssl", check_name="SSL No Disponible",
                severity="high", passed=False,
                value_found=str(e)[:200],
                value_expected="Servidor HTTPS accesible en puerto 443",
                recommendation="Habilitar HTTPS en el servidor web",
            )

    # ─── Cookies ───

    async def _scan_cookies(self, url: str):
        client = await self._get_client()
        try:
            resp = await client.get(url)
            cookies = resp.cookies
            if not cookies:
                return

            for name, cookie in cookies.items():
                if not cookie.secure:
                    self._add_check(
                        url=url, category="cookies", check_name=f"Cookie '{name}' sin flag Secure",
                        severity="high", passed=False,
                        value_found=f"{name} (sin Secure)", value_expected="Flag Secure habilitado",
                        recommendation="Marcar todas las cookies con el flag Secure para que solo se transmitan por HTTPS",
                        dedup=True,
                    )
                if not cookie.has_httponly:
                    self._add_check(
                        url=url, category="cookies", check_name=f"Cookie '{name}' sin flag HttpOnly",
                        severity="medium", passed=False,
                        value_found=f"{name} (sin HttpOnly)", value_expected="Flag HttpOnly habilitado",
                        recommendation="Marcar las cookies de sesión con HttpOnly para prevenir acceso desde JavaScript",
                        dedup=True,
                    )
                samesite = cookie.samesite
                if not samesite or samesite.lower() == "none":
                    self._add_check(
                        url=url, category="cookies", check_name=f"Cookie '{name}' sin SameSite",
                        severity="low", passed=False,
                        value_found=f"{name} (SameSite={samesite or 'ausente'})",
                        value_expected="SameSite=Lax o Strict",
                        recommendation="Configurar SameSite=Lax o Strict en cookies para prevenir ataques CSRF",
                        dedup=True,
                    )
        except Exception as e:
            logger.debug(f"Error escaneando cookies de {url}: {e}")

    async def _scan_page_cookies(self, url: str):
        await self._scan_cookies(url)

    # ─── Info Disclosure ───

    async def _scan_info_disclosure(self, url: str):
        client = await self._get_client()
        try:
            resp = await client.get(url)
            html = resp.text

            for pattern, check_name, severity in SENSITIVE_PATTERNS:
                matches = pattern.findall(html)
                if matches:
                    self._add_check(
                        url=url, category="info_disclosure", check_name=f"Exposición de {check_name}",
                        severity=severity, passed=False,
                        value_found=f"{len(matches)} ocurrencia(s) encontrada(s)",
                        value_expected="Sin información sensible expuesta",
                        recommendation=f"Remover o proteger {check_name} del código fuente del sitio",
                    )

            comments = re.findall(r'<!--(.*?)-->', html, re.DOTALL)
            sensitive_comments = []
            for comment in comments:
                comment_lower = comment.lower()
                if any(kw in comment_lower for kw in ["password", "secret", "token", "api key", "debug", "todo", "fixme", "hack", "temp"]):
                    sensitive_comments.append(comment.strip()[:100])
            if sensitive_comments:
                self._add_check(
                    url=url, category="info_disclosure", check_name="Comentarios HTML Sensibles",
                    severity="low", passed=False,
                    value_found=f"{len(sensitive_comments)} comentario(s) potencialmente sensible(s)",
                    value_expected="Sin comentarios sensibles en HTML",
                    recommendation="Remover comentarios HTML que contengan información sensible antes de producción",
                )
        except Exception as e:
            logger.debug(f"Error escaneando info disclosure de {url}: {e}")

    # ─── Tech Detection ───

    async def _scan_tech_detection(self, url: str):
        client = await self._get_client()
        try:
            resp = await client.get(url)
            headers_lower = {k.lower(): v for k, v in resp.headers.items()}
            html = resp.text

            detected_techs: set[str] = set()
            server = headers_lower.get("server", "")
            powered_by = headers_lower.get("x-powered-by", "")

            for tech_name, pattern in TECH_SIGNATURES.get("server", {}).items():
                if pattern.search(server):
                    detected_techs.add(tech_name)
            for tech_name, pattern in TECH_SIGNATURES.get("x-powered-by", {}).items():
                if pattern.search(powered_by):
                    detected_techs.add(tech_name)
            for tech_name, pattern in TECH_SIGNATURES.get("html", {}).items():
                if pattern.search(html):
                    detected_techs.add(tech_name)

            for tech in detected_techs:
                self._add_check(
                    url=url, category="tech_detection", check_name=f"Tecnología: {tech}",
                    severity="info", passed=True,
                    value_found=tech, value_expected="Detección de tecnologías",
                    recommendation="Revisar si esta tecnología tiene vulnerabilidades conocidas (CVEs) y mantenerla actualizada",
                )
        except Exception as e:
            logger.debug(f"Error detectando tecnologías de {url}: {e}")

    # ─── WAF Detection ───

    async def _scan_waf(self, url: str):
        client = await self._get_client()
        try:
            resp = await client.get(url)
            headers_lower = {k.lower(): v for k, v in resp.headers.items()}
            html = resp.text
            header_str = "\n".join(f"{k}: {v}" for k, v in resp.headers.items())
            cookie_names = [c.name.lower() for c in resp.cookies.jar]

            detected_wafs: list[str] = []

            for waf_name, sigs in WAF_SIGNATURES.items():
                found = False
                for h in sigs["headers"]:
                    if h.lower() in header_str.lower():
                        found = True
                        break
                if not found:
                    for c in sigs["cookies"]:
                        if any(c.lower() in name for name in cookie_names):
                            found = True
                            break
                if not found:
                    for b in sigs["body"]:
                        if b.lower() in html.lower():
                            found = True
                            break
                if found:
                    detected_wafs.append(waf_name)

            if detected_wafs:
                for waf in detected_wafs:
                    self._add_check(
                        url=url, category="waf", check_name=f"WAF Detectado: {waf}",
                        severity="info", passed=True,
                        value_found=f"WAF {waf} detectado",
                        value_expected="Presencia de WAF",
                        recommendation="El WAF proporciona protección adicional contra ataques web. Verificar que las reglas estén actualizadas.",
                    )
            else:
                self._add_check(
                    url=url, category="waf", check_name="Sin WAF Detectado",
                    severity="medium", passed=False,
                    value_found="No se detectó ningún WAF",
                    value_expected="WAF presente para protección contra ataques",
                    recommendation="Considerar implementar un WAF (Web Application Firewall) como Cloudflare, Sucuri, o ModSecurity",
                )
        except Exception as e:
            logger.debug(f"Error detectando WAF de {url}: {e}")

    # ─── CORS ───

    async def _scan_cors(self, url: str):
        client = await self._get_client()
        try:
            resp = await client.get(url, headers={"Origin": "https://evil.example.com"})
            acao = resp.headers.get("access-control-allow-origin", "")
            acac = resp.headers.get("access-control-allow-credentials", "")

            if acao == "*":
                self._add_check(
                    url=url, category="cors", check_name="CORS Permisivo (Wildcard)",
                    severity="high", passed=False,
                    value_found="Access-Control-Allow-Origin: *",
                    value_expected="Orígenes específicos, no wildcard",
                    recommendation="Restringir CORS a orígenes confiados. Evitar usar '*' en Access-Control-Allow-Origin",
                )
            elif acao == "https://evil.example.com":
                if acac.lower() == "true":
                    severity = "critical"
                    rec = "CRÍTICO: El servidor refleja cualquier origen con credenciales. Esto permite a atacantes robar datos del usuario autenticado."
                else:
                    severity = "medium"
                    rec = "El servidor refleja orígenes arbitrarios sin credenciales. Restringir a dominios confiados."
                self._add_check(
                    url=url, category="cors", check_name="CORS Refleja Origen Arbitrario",
                    severity=severity, passed=False,
                    value_found=f"ACA-Origin refleja: {acao}, ACA-Credentials: {acac or 'no'}",
                    value_expected="Solo orígenes confiados",
                    recommendation=rec,
                )
            elif acao and acao != "":
                self._add_check(
                    url=url, category="cors", check_name="CORS Configurado",
                    severity="info", passed=True,
                    value_found=f"Origen permitido: {acao}",
                    value_expected="Orígenes específicos",
                    recommendation="",
                )
        except Exception as e:
            logger.debug(f"Error escaneando CORS de {url}: {e}")

    # ─── HTTPS Enforcement ───

    async def _scan_https_enforcement(self, domain: str):
        http_url = f"http://{domain}"
        https_url = f"https://{domain}"

        try:
            client = await self._get_client()
            try:
                resp = await client.get(http_url, follow_redirects=False)
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("location", "")
                    if location.startswith("https://"):
                        self._add_check(
                            url=http_url, category="https", check_name="Redirección HTTP a HTTPS",
                            severity="info", passed=True,
                            value_found=f"HTTP redirige a {location[:80]}",
                            value_expected="Redirigir todo tráfico HTTP a HTTPS",
                            recommendation="",
                        )
                    else:
                        self._add_check(
                            url=http_url, category="https", check_name="HTTP No Redirige a HTTPS",
                            severity="high", passed=False,
                            value_found=f"HTTP redirige a {location[:80] if location else 'sin destino'}",
                            value_expected="Redirigir todo tráfico HTTP a HTTPS",
                            recommendation="Configurar el servidor web para redirigir todo tráfico HTTP (puerto 80) a HTTPS (puerto 443)",
                        )
                elif resp.status_code >= 200 and resp.status_code < 300:
                    self._add_check(
                        url=http_url, category="https", check_name="HTTP Accesible sin Redirigir",
                        severity="high", passed=False,
                        value_found=f"HTTP retorna {resp.status_code} sin redirigir",
                        value_expected="Redirigir todo tráfico HTTP a HTTPS",
                        recommendation="Configurar el servidor web para redirigir todo tráfico HTTP (puerto 80) a HTTPS (puerto 443)",
                    )
            except httpx.RedirectStatus:
                pass
            except (httpx.TimeoutException, httpx.ConnectError):
                pass
        except Exception as e:
            logger.debug(f"Error verificando HTTPS enforcement: {e}")

    # ─── Open Ports ───

    async def _scan_open_ports(self, domain: str):
        ports_to_scan = [21, 22, 25, 80, 110, 143, 443, 465, 587, 993, 995, 3306, 5432, 6379, 8080, 8443, 9200, 27017, 3389, 1433]

        open_ports: list[int] = []
        expected_open = {80, 443}

        async def check_port(port: int):
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(domain, port), timeout=3
                )
                writer.close()
                await writer.wait_closed()
                return port
            except (OSError, asyncio.TimeoutError):
                return None

        results = await asyncio.gather(*[check_port(p) for p in ports_to_scan])

        for result in results:
            if result is not None:
                open_ports.append(result)

        unexpected = [p for p in open_ports if p not in expected_open]
        if unexpected:
            port_details = ", ".join(f"{p} ({COMMON_PORT_DESCRIPTIONS.get(p, 'Desconocido')})" for p in sorted(unexpected))
            self._add_check(
                url=f"{domain}:{','.join(str(p) for p in sorted(unexpected))}",
                category="ports", check_name=f"Puertos Abiertos Inesperados ({len(unexpected)})",
                severity="medium" if any(p in (3306, 5432, 6379, 9200, 27017, 1433, 3389) for p in unexpected) else "low",
                passed=False,
                value_found=port_details,
                value_expected="Solo puertos necesarios expuestos (80, 443)",
                recommendation="Cerrar o restringir acceso a puertos innecesarios. Usar firewall para bloquear acceso externo.",
            )
        else:
            self._add_check(
                url=domain, category="ports", check_name="Puertos — Solo HTTP/HTTPS Expuestos",
                severity="info", passed=True,
                value_expected="Solo puertos 80 y 443 accesibles",
                value_found="Solo puertos de servicio web accesibles públicamente",
                recommendation="",
            )

    # ─── Email Security (DNS) ───

    async def _scan_email_security(self, domain: str):
        try:
            import dns.resolver
            has_dns = True
        except ImportError:
            has_dns = False

        if not has_dns:
            self._add_check(
                url=f"mailto:{domain}", category="email_security", check_name="Verificación DNS No Disponible",
                severity="info", passed=True,
                value_found="dnspython no instalado",
                value_expected="Verificar registros SPF, DKIM, DMARC",
                recommendation="Instalar dnspython: pip install dnspython",
            )
            return

        try:
            import dns.resolver

            try:
                spf_records = dns.resolver.resolve(domain, "TXT")
                spf_found = False
                for rdata in spf_records:
                    txt = rdata.to_text()
                    if "v=spf1" in txt:
                        spf_found = True
                        if "~all" in txt or "-all" in txt:
                            self._add_check(
                                url=f"mailto:{domain}", category="email_security", check_name="Registro SPF",
                                severity="info", passed=True,
                                value_found=txt[:150],
                                value_expected="v=spf1 con política restrictiva (~all o -all)",
                                recommendation="",
                            )
                        elif "?all" in txt or "+all" in txt:
                            self._add_check(
                                url=f"mailto:{domain}", category="email_security", check_name="Registro SPF Permisivo",
                                severity="medium", passed=False,
                                value_found=txt[:150],
                                value_expected="v=spf1 con ~all o -all",
                                recommendation="Cambiar política SPF a ~all (softfail) o -all (fail) para prevenir suplantación de correo",
                            )
                        else:
                            self._add_check(
                                url=f"mailto:{domain}", category="email_security", check_name="Registro SPF Presente",
                                severity="low", passed=True,
                                value_found=txt[:150],
                                value_expected="v=spf1 con política restrictiva",
                                recommendation="Verificar que la política SPF termina con ~all o -all",
                            )
                        break
                if not spf_found:
                    self._add_check(
                        url=f"mailto:{domain}", category="email_security", check_name="Registro SPF Ausente",
                        severity="high", passed=False,
                        value_found="No se encontró registro SPF",
                        value_expected="v=spf1 con política restrictiva",
                        recommendation="Agregar un registro SPF TXT para prevenir suplantación de correo. Ejemplo: v=spf1 include:_spf.google.com ~all",
                    )
            except dns.resolver.NoAnswer:
                self._add_check(
                    url=f"mailto:{domain}", category="email_security", check_name="Registro SPF Ausente",
                    severity="high", passed=False,
                    value_found="No se encontró registro SPF",
                    value_expected="v=spf1 con política restrictiva",
                    recommendation="Agregar un registro SPF TXT para prevenir suplantación de correo",
                )
            except Exception:
                pass

            try:
                dmarc_records = dns.resolver.resolve(f"_dmarc.{domain}", "TXT")
                dmarc_found = False
                for rdata in dmarc_records:
                    txt = rdata.to_text()
                    if "v=dmarc1" in txt:
                        dmarc_found = True
                        if "p=reject" in txt or "p=quarantine" in txt:
                            self._add_check(
                                url=f"mailto:{domain}", category="email_security", check_name="Registro DMARC",
                                severity="info", passed=True,
                                value_found=txt[:150],
                                value_expected="v=DMARC1; p=reject o p=quarantine",
                                recommendation="",
                            )
                        elif "p=none" in txt:
                            self._add_check(
                                url=f"mailto:{domain}", category="email_security", check_name="DMARC Política Permisiva",
                                severity="medium", passed=False,
                                value_found=txt[:150],
                                value_expected="v=DMARC1; p=reject o p=quarantine",
                                recommendation="Cambiar política DMARC a p=reject o p=quarantine para proteger contra suplantación de correo",
                            )
                        break
                if not dmarc_found:
                    self._add_check(
                        url=f"mailto:{domain}", category="email_security", check_name="Registro DMARC Ausente",
                        severity="high", passed=False,
                        value_found="No se encontró registro DMARC",
                        value_expected="v=DMARC1; p=reject",
                        recommendation="Agregar registro DMARC TXT en _dmarc.{domain} para proteger contra suplantación de correo",
                    )
            except dns.resolver.NoAnswer:
                self._add_check(
                    url=f"mailto:{domain}", category="email_security", check_name="Registro DMARC Ausente",
                    severity="high", passed=False,
                    value_found="No se encontró registro DMARC",
                    value_expected="v=DMARC1; p=reject",
                    recommendation="Agregar registro DMARC TXT en _dmarc.{domain}",
                )
            except Exception:
                pass

        except Exception as e:
            logger.debug(f"Error verificando email security para {domain}: {e}")

    # ─── Access / Auth ───

    async def _scan_access(self, url: str):
        client = await self._get_client()
        admin_paths = [
            "/admin", "/admin/", "/wp-admin", "/wp-admin/", "/wp-login.php",
            "/login", "/login.php", "/administrator", "/administrator/",
            "/dashboard", "/panel", "/cpanel", "/phpmyadmin", "/phpmyadmin/",
        ]

        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        homepage = normalize_url(f"{parsed.scheme}://{parsed.netloc}/")

        async def _check_admin_path(path: str) -> tuple[str, int, str] | None:
            try:
                check_url = f"{base}{path}"

                resp = await client.get(check_url, follow_redirects=True)

                if resp.status_code >= 400:
                    return None

                final_url = normalize_url(str(resp.url))
                if is_not_found_redirect(final_url):
                    return None

                if final_url == homepage:
                    return None

                if resp.status_code == 200:
                    return (path, resp.status_code, "directo")

                return None

            except (httpx.TimeoutException, httpx.ConnectError):
                return None
            except Exception:
                return None

        results = await asyncio.gather(*[_check_admin_path(p) for p in admin_paths])
        found_admin = [r for r in results if r is not None]

        if found_admin:
            paths_str = ", ".join(f"{p} ({s})" for p, s, _ in found_admin)
            severity = "high"
            self._add_check(
                url=url, category="access", check_name=f"Paneles de Admin Accesibles ({len(found_admin)})",
                severity=severity, passed=False,
                value_found=paths_str[:300],
                value_expected="Paneles de administración no expuestos públicamente",
                recommendation="Restringir acceso a paneles de administración con autenticación, IP whitelist o VPN",
            )
        else:
            self._add_check(
                url=url, category="access", check_name="Paneles Admin No Expuestos",
                severity="info", passed=True,
                value_found="No se detectaron paneles de administración públicos",
                value_expected="Paneles de administración no accesibles públicamente",
                recommendation="",
            )

        try:
            for i in range(5):
                resp = await client.get(url)
            rate_limit_headers = [h for h in resp.headers if "rate" in h[0].lower() or "retry" in h[0].lower() or "throttl" in h[0].lower()]
            if rate_limit_headers:
                self._add_check(
                    url=url, category="access", check_name="Rate Limiting Detectado",
                    severity="info", passed=True,
                    value_found=f"Headers: {', '.join(f'{h[0]}: {h[1]}' for h in rate_limit_headers)}",
                    value_expected="Mecanismo de rate limiting presente",
                    recommendation="",
                )
            else:
                self._add_check(
                    url=url, category="access", check_name="Sin Rate Limiting Visible",
                    severity="low", passed=False,
                    value_found="No se detectaron headers de rate limiting",
                    value_expected="Headers como X-RateLimit-* presentes",
                    recommendation="Implementar rate limiting para proteger contra ataques de fuerza bruta y abuso de API",
                )
        except Exception as e:
            logger.debug(f"Error verificando rate limiting: {e}")

    # ─── Score ───

    def _calculate_score(self) -> int:
        check_dedup: set[str] = set()
        severity_weights = {"critical": 20, "high": 10, "medium": 5, "low": 2, "info": 0}
        total_penalty = 0

        for check in self._checks:
            if check.get("passed"):
                continue

            key = check["check_name"]
            if key in check_dedup:
                continue
            check_dedup.add(key)

            total_penalty += severity_weights.get(check.get("severity", "info"), 0)

        score = max(0, 100 - total_penalty)
        return min(score, 100)

    async def _emit_progress(self, data: dict):
        if self.on_progress:
            try:
                await self.on_progress(data)
            except Exception:
                pass