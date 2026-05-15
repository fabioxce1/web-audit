from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

PAGE_LINK_ATTRS = [
    ("a", "href"),
    ("iframe", "src"),
    ("form", "action"),
    ("area", "href"),
]

ASSET_LINK_ATTRS = [
    ("link", "href"),
    ("script", "src"),
    ("img", "src"),
    ("source", "src"),
    ("video", "src"),
    ("audio", "src"),
    ("embed", "src"),
    ("object", "data"),
]


class Parser:
    @staticmethod
    def extract_links(html: str, base_url: str) -> list[str]:
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        links: list[str] = []

        for tag, attr in PAGE_LINK_ATTRS:
            for element in soup.find_all(tag):
                value = element.get(attr)
                if value and isinstance(value, str):
                    absolute = urljoin(base_url, value.strip())
                    parsed = urlparse(absolute)
                    if parsed.scheme in ("http", "https") and parsed.netloc:
                        links.append(absolute)

        return list(dict.fromkeys(links))

    @staticmethod
    def extract_title(html: str) -> str:
        if not html:
            return ""

        soup = BeautifulSoup(html, "lxml")
        title_tag = soup.find("title")
        if title_tag and title_tag.text:
            return title_tag.text.strip()[:512]
        return ""

    @staticmethod
    def extract_meta_description(html: str) -> str:
        if not html:
            return ""

        soup = BeautifulSoup(html, "lxml")
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            return meta["content"].strip()
        return ""
