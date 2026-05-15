import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Float
from sqlalchemy.orm import relationship
from app.models.base import Base


class SeoScan(Base):
    __tablename__ = "seo_scans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("crawl_sessions.id"), nullable=False)
    status = Column(String(20), default="pending")
    urls_scanned = Column(Integer, default=0)
    total_checks = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    good_count = Column(Integer, default=0)
    info_count = Column(Integer, default=0)
    score = Column(Integer, default=0)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="seo_scans")
    checks = relationship("SeoCheck", back_populates="scan", cascade="all, delete-orphan")


class SeoCheck(Base):
    __tablename__ = "seo_checks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Integer, ForeignKey("seo_scans.id"), nullable=False)
    url_id = Column(Integer, ForeignKey("discovered_urls.id"), nullable=True)
    url = Column(String(2048), nullable=False)
    category = Column(String(50), nullable=False)
    check_name = Column(String(150), nullable=False)
    severity = Column(String(20), nullable=False)
    value_found = Column(Text, nullable=True)
    value_expected = Column(Text, nullable=True)
    score_impact = Column(Integer, default=0)
    recommendation = Column(Text, nullable=True)
    passed = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    scan = relationship("SeoScan", back_populates="checks")