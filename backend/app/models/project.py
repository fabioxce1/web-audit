import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, JSON, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from app.models.base import Base
import enum


class ProjectStatus(str, enum.Enum):
    idle = "idle"
    crawling = "crawling"
    paused = "paused"
    completed = "completed"
    failed = "failed"


class CrawlSessionStatus(str, enum.Enum):
    running = "running"
    paused = "paused"
    completed = "completed"
    stopped = "stopped"
    failed = "failed"


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    seed_url = Column(String(2048), nullable=False)
    config = Column(JSON, nullable=False, default=dict)
    status = Column(SAEnum(ProjectStatus), default=ProjectStatus.idle, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    sessions = relationship("CrawlSession", back_populates="project", cascade="all, delete-orphan")
    security_scans = relationship("SecurityScan", back_populates="project", cascade="all, delete-orphan")
    seo_scans = relationship("SeoScan", back_populates="project", cascade="all, delete-orphan")


class CrawlSession(Base):
    __tablename__ = "crawl_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    status = Column(SAEnum(CrawlSessionStatus), default=CrawlSessionStatus.running, nullable=False)
    urls_found = Column(Integer, default=0)
    urls_crawled = Column(Integer, default=0)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="sessions")
    urls = relationship("DiscoveredURL", back_populates="session", cascade="all, delete-orphan")
