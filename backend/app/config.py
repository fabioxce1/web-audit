from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WEB_AUDIT_", env_file=".env")

    db_path: str = str(Path(__file__).parent.parent / "data" / "web_audit.db")
    snapshot_dir: str = str(Path(__file__).parent.parent / "data" / "snapshots")

    max_workers: int = 5
    crawl_delay: float = 1.0
    respect_robots_txt: bool = True
    use_playwright: bool = True
    follow_redirects: bool = True
    max_redirects: int = 5
    timeout: int = 15
    max_urls: int = 500
    max_depth: int = 0
    crawl_assets: bool = False
    exclude_patterns: list[str] = [
        "/tag/", "/category/", "/categories/", "/author/", "/authors/",
        "/20",  # date archives like /2024/01/
        "/feed/", "/feed", "/rss", "/rss/", "/atom/",
        "/trackback/", "/trackback",
        "/wp-content/", "/wp-includes/", "/wp-admin/", "/wp-json/",
        "/xmlrpc.php", "/wp-login.php",
        "/cdn-cgi/",
        "/page/",
        "/?s=", "/search/",
        "/comments/", "/comment-page-",
        "/share/", "/print/",
    ]
    save_html_snapshots: bool = True
    enumerate_dirs: bool = True
    headless: bool = True
    viewport_width: int = 1920
    viewport_height: int = 1080

    user_agent: str = "WebAudit/1.0 (+https://github.com/webaudit)"


settings = Settings()
