from urllib.parse import urlparse, urlunparse, urljoin


TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "gclsrc", "dclid", "msclkid", "twclid",
    "igshid", "ref", "source", "mc_cid", "mc_eid",
    "_ga", "_gl", "_gcl_au", "_gcl_aw", "_gcl_dc",
}

PAGINATION_PARAMS = {
    "page", "paged", "p", "pg",
    "sort", "order", "orderby", "dir",
    "filter", "f",
    "view", "display", "layout", "mode",
    "per_page", "limit", "show",
    "lang",
}


def strip_query_params(url: str, keep_params: set[str] | None = None) -> str:
    parsed = urlparse(url)
    if not parsed.query:
        return url

    keep = (keep_params or set()) | {"q", "s", "id", "post", "pagename"}
    qs_parts = []
    query = parsed.query
    for part in query.split("&"):
        if "=" in part:
            key = part.split("=", 1)[0].lower()
            if key in TRACKING_PARAMS:
                continue
            if key in PAGINATION_PARAMS:
                continue
            if key not in keep:
                continue
            qs_parts.append(part)
        else:
            qs_parts.append(part)

    query = "&".join(qs_parts)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment))


def normalize_url(url: str, base_domain: str | None = None) -> str:
    url = url.strip()
    if not url:
        return ""

    parsed = urlparse(url)

    if not parsed.netloc and base_domain:
        url = urljoin(f"https://{base_domain}", url)
        parsed = urlparse(url)

    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()

    if netloc.startswith("www."):
        netloc = netloc[4:]

    path = parsed.path or "/"
    path = path.rstrip("/") if path != "/" else "/"

    query = parsed.query
    if query:
        qs_parts = []
        for part in query.split("&"):
            if "=" in part:
                key = part.split("=", 1)[0].lower()
                if key in TRACKING_PARAMS:
                    continue
                if key in PAGINATION_PARAMS:
                    continue
                if key not in {"q", "s", "id", "post"}:
                    qs_parts.append(part)
            else:
                qs_parts.append(part)
        query = "&".join(qs_parts)

    normalized = urlunparse((scheme, netloc, path, "", query, ""))

    return normalized


def is_same_domain(url1: str, url2: str) -> bool:
    def _extract_domain(u: str) -> str:
        parsed = urlparse(u)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc

    return _extract_domain(url1) == _extract_domain(url2)


def is_internal_url(url: str, base_domain: str) -> bool:
    if not url or url.startswith("#") or url.startswith("javascript:") or url.startswith("mailto:") or url.startswith("tel:"):
        return False

    parsed = urlparse(url)

    if not parsed.netloc:
        return True

    return is_same_domain(url, f"https://{base_domain}")


NON_CRAWLABLE_EXTENSIONS = {
    ".css", ".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".coffee",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp", ".tiff", ".avif",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".tar", ".gz", ".rar",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ogg", ".wav",
    ".xml", ".rss", ".atom", ".txt", ".csv", ".vtt", ".srt",
}

NON_CRAWLABLE_CONTENT_TYPES = {
    "text/css",
    "application/javascript", "text/javascript", "application/x-javascript", "module",
    "image/png", "image/jpeg", "image/gif", "image/svg+xml", "image/webp", "image/x-icon", "image/vnd.microsoft.icon", "image/avif",
    "font/woff", "font/woff2", "font/ttf", "font/otf", "application/font-woff", "application/font-woff2",
    "application/pdf", "application/msword", "application/zip",
    "audio/mpeg", "audio/ogg", "audio/wav", "video/mp4", "video/webm", "video/ogg",
    "application/xml", "text/xml", "application/rss+xml", "application/atom+xml", "text/plain",
}


def is_crawlable(url: str, content_type: str | None = None) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()

    for ext in NON_CRAWLABLE_EXTENSIONS:
        if path.endswith(ext):
            return False

    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        if ct in NON_CRAWLABLE_CONTENT_TYPES:
            return False

    return True


NOT_FOUND_PATH_PATTERNS = [
    "/not-found",
    "/404",
    "/error-404",
    "/page-not-found",
    "/pageNotFound",
    "/pagenotfound",
    "/notfound",
    "/not_found",
    "/error-page",
    "/errorpage",
]


def is_not_found_redirect(url: str) -> bool:
    path = urlparse(url).path.lower().rstrip("/")
    for pattern in NOT_FOUND_PATH_PATTERNS:
        if pattern in path:
            return True
    return False


def is_path_excluded(url: str, patterns: list[str]) -> bool:
    if not patterns:
        return False
    parsed = urlparse(url)
    path_and_query = (parsed.path + ("?" + parsed.query if parsed.query else "")).lower()
    for pattern in patterns:
        if pattern.lower() in path_and_query:
            return True
    return False


def extract_domain(url: str) -> str:
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc
