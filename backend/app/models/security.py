import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Float
from sqlalchemy.orm import relationship
from app.models.base import Base


class SecurityScan(Base):
    __tablename__ = "security_scans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("crawl_sessions.id"), nullable=False)
    status = Column(String(20), default="pending")
    urls_scanned = Column(Integer, default=0)
    total_checks = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    high_count = Column(Integer, default=0)
    medium_count = Column(Integer, default=0)
    low_count = Column(Integer, default=0)
    info_count = Column(Integer, default=0)
    score = Column(Integer, default=0)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="security_scans")
    checks = relationship("SecurityCheck", back_populates="scan", cascade="all, delete-orphan")


class SecurityCheck(Base):
    __tablename__ = "security_checks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Integer, ForeignKey("security_scans.id"), nullable=False)
    url_id = Column(Integer, ForeignKey("discovered_urls.id"), nullable=True)
    url = Column(String(2048), nullable=False)
    category = Column(String(50), nullable=False)
    check_name = Column(String(100), nullable=False)
    severity = Column(String(20), nullable=False)
    value_found = Column(Text, nullable=True)
    value_expected = Column(Text, nullable=True)
    recommendation = Column(Text, nullable=True)
    passed = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    scan = relationship("SecurityScan", back_populates="checks")