import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base import Base


class DiscoveredURL(Base):
    __tablename__ = "discovered_urls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("crawl_sessions.id"), nullable=False)
    url = Column(String(2048), nullable=False)
    normalized_url = Column(String(2048), nullable=False, index=True)
    status_code = Column(Integer, nullable=True)
    content_type = Column(String(255), nullable=True)
    depth = Column(Integer, default=0)
    parent_url = Column(String(2048), nullable=True)
    title = Column(String(512), nullable=True)
    html_snapshot_path = Column(String(1024), nullable=True)
    links_count = Column(Integer, default=0)
    crawled_at = Column(DateTime, default=datetime.datetime.utcnow)
    is_external = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    content_length = Column(Integer, nullable=True)
    content_hash = Column(String(64), nullable=True, index=True)
    is_duplicate = Column(Boolean, default=False)
    is_broken = Column(Boolean, default=False)
    redirect_url = Column(String(2048), nullable=True)
    discovery_method = Column(String(50), default="crawl")

    session = relationship("CrawlSession", back_populates="urls")
