import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from pydantic import BaseModel
from datetime import datetime

from app.db import get_db, async_session
from app.models.project import Project, CrawlSession, ProjectStatus
from app.models.url import DiscoveredURL
from app.models.security import SecurityScan, SecurityCheck
from app.security.scanner import SecurityScanner

logger = logging.getLogger(__name__)

router = APIRouter()

active_scanners: dict[int, SecurityScanner] = {}
active_security_ws: dict[int, list[WebSocket]] = {}


class SecurityScanResponse(BaseModel):
    id: int
    project_id: int
    session_id: int
    status: str
    urls_scanned: int
    total_checks: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    info_count: int
    score: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class SecurityCheckResponse(BaseModel):
    id: int
    scan_id: int
    url: str
    url_id: Optional[int]
    category: str
    check_name: str
    severity: str
    value_found: Optional[str]
    value_expected: Optional[str]
    recommendation: Optional[str]
    passed: bool

    model_config = {"from_attributes": True}


class SecurityCheckListResponse(BaseModel):
    checks: list[SecurityCheckResponse]
    total: int
    page: int
    page_size: int


@router.post("/{project_id}/security/scan", response_model=SecurityScanResponse)
async def start_security_scan(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    session_result = await db.execute(
        select(CrawlSession)
        .where(CrawlSession.project_id == project_id)
        .order_by(desc(CrawlSession.started_at))
        .limit(1)
    )
    crawl_session = session_result.scalar_one_or_none()
    if not crawl_session:
        raise HTTPException(status_code=404, detail="No hay sesión de crawling para este proyecto")

    existing = await db.execute(
        select(SecurityScan)
        .where(SecurityScan.session_id == crawl_session.id)
        .where(SecurityScan.status.in_(["pending", "running"]))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ya hay un escaneo de seguridad en curso")

    scan = SecurityScan(
        project_id=project.id,
        session_id=crawl_session.id,
        status="pending",
    )
    db.add(scan)
    await db.commit()
    await db.refresh(scan)

    scanner = SecurityScanner(
        session_factory=async_session,
        project_id=project.id,
        scan_id=scan.id,
        on_progress=lambda data: _broadcast_security_progress(project_id, data),
    )
    active_scanners[scan.id] = scanner

    asyncio.create_task(_run_scanner(scanner, scan.id, project.seed_url))

    return SecurityScanResponse.model_validate(scan)


@router.get("/{project_id}/security/scan", response_model=SecurityScanResponse)
async def get_latest_scan(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SecurityScan)
        .where(SecurityScan.project_id == project_id)
        .order_by(desc(SecurityScan.started_at))
        .limit(1)
    )
    scan = result.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="No hay escaneo de seguridad")
    return SecurityScanResponse.model_validate(scan)


@router.get("/{project_id}/security/checks", response_model=SecurityCheckListResponse)
async def get_security_checks(
    project_id: int,
    page: int = 1,
    page_size: int = 50,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    passed: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    scan_result = await db.execute(
        select(SecurityScan)
        .where(SecurityScan.project_id == project_id)
        .order_by(desc(SecurityScan.started_at))
        .limit(1)
    )
    scan = scan_result.scalar_one_or_none()
    if not scan:
        return SecurityCheckListResponse(checks=[], total=0, page=page, page_size=page_size)

    query = select(SecurityCheck).where(SecurityCheck.scan_id == scan.id)
    count_base = select(func.count()).select_from(SecurityCheck).where(SecurityCheck.scan_id == scan.id)

    if category:
        query = query.where(SecurityCheck.category == category)
        count_base = count_base.where(SecurityCheck.category == category)
    if severity:
        query = query.where(SecurityCheck.severity == severity)
        count_base = count_base.where(SecurityCheck.severity == severity)
    if passed is not None:
        query = query.where(SecurityCheck.passed == (1 if passed else 0))
        count_base = count_base.where(SecurityCheck.passed == (1 if passed else 0))

    total_result = await db.execute(count_base)
    total = total_result.scalar() or 0

    query = query.order_by(
        SecurityCheck.severity.desc(),
        SecurityCheck.check_name,
    ).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    checks = result.scalars().all()

    return SecurityCheckListResponse(
        checks=[SecurityCheckResponse.model_validate(c) for c in checks],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{project_id}/security/summary")
async def get_security_summary(project_id: int, db: AsyncSession = Depends(get_db)):
    scan_result = await db.execute(
        select(SecurityScan)
        .where(SecurityScan.project_id == project_id)
        .order_by(desc(SecurityScan.started_at))
        .limit(1)
    )
    scan = scan_result.scalar_one_or_none()
    if not scan:
        return {"has_scan": False}

    categories = await db.execute(
        select(SecurityCheck.category, SecurityCheck.severity, func.count(SecurityCheck.id))
        .where(SecurityCheck.scan_id == scan.id)
        .group_by(SecurityCheck.category, SecurityCheck.severity)
    )
    category_counts = {}
    for cat, sev, count in categories:
        if cat not in category_counts:
            category_counts[cat] = {}
        category_counts[cat][sev] = count

    failed_by_severity = await db.execute(
        select(SecurityCheck.severity, func.count(SecurityCheck.id))
        .where(SecurityCheck.scan_id == scan.id, SecurityCheck.passed == 0)
        .group_by(SecurityCheck.severity)
    )
    severity_failed = {sev: count for sev, count in failed_by_severity}

    return {
        "has_scan": True,
        "scan_id": scan.id,
        "status": scan.status,
        "score": scan.score,
        "urls_scanned": scan.urls_scanned,
        "total_checks": scan.total_checks,
        "critical_count": scan.critical_count,
        "high_count": scan.high_count,
        "medium_count": scan.medium_count,
        "low_count": scan.low_count,
        "info_count": scan.info_count,
        "category_counts": category_counts,
        "severity_failed": severity_failed,
    }


@router.websocket("/ws/{project_id}/security")
async def websocket_security_progress(websocket: WebSocket, project_id: int):
    await websocket.accept()

    if project_id not in active_security_ws:
        active_security_ws[project_id] = []
    active_security_ws[project_id].append(websocket)

    try:
        while True:
            try:
                data = await websocket.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        if project_id in active_security_ws:
            active_security_ws[project_id].remove(websocket)
            if not active_security_ws[project_id]:
                del active_security_ws[project_id]


async def _broadcast_security_progress(project_id: int, data: dict):
    ws_list = active_security_ws.get(project_id, [])
    for ws in ws_list:
        try:
            await ws.send_json(data)
        except Exception:
            pass


async def _run_scanner(scanner: SecurityScanner, scan_id: int, seed_url: str):
    try:
        await scanner.run(seed_url)
    except Exception as e:
        logger.error(f"Error en escaneo de seguridad {scan_id}: {e}", exc_info=True)
    finally:
        if scan_id in active_scanners:
            del active_scanners[scan_id]