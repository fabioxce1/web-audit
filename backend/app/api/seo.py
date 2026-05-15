import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from pydantic import BaseModel
from datetime import datetime

from app.db import get_db, async_session
from app.models.project import Project, CrawlSession
from app.models.seo import SeoScan, SeoCheck
from app.seo.scanner import SeoScanner

logger = logging.getLogger(__name__)

router = APIRouter()

active_seo_scanners: dict[int, SeoScanner] = {}
active_seo_ws: dict[int, list[WebSocket]] = {}


class SeoScanResponse(BaseModel):
    id: int
    project_id: int
    session_id: int
    status: str
    urls_scanned: int
    total_checks: int
    critical_count: int
    warning_count: int
    good_count: int
    info_count: int
    score: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class SeoCheckResponse(BaseModel):
    id: int
    scan_id: int
    url: str
    url_id: Optional[int]
    category: str
    check_name: str
    severity: str
    value_found: Optional[str]
    value_expected: Optional[str]
    score_impact: int
    recommendation: Optional[str]
    passed: bool

    model_config = {"from_attributes": True}


class SeoCheckListResponse(BaseModel):
    checks: list[SeoCheckResponse]
    total: int
    page: int
    page_size: int


@router.post("/{project_id}/seo/scan", response_model=SeoScanResponse)
async def start_seo_scan(project_id: int, db: AsyncSession = Depends(get_db)):
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
        raise HTTPException(status_code=404, detail="No hay sesión de crawling")

    scan = SeoScan(project_id=project.id, session_id=crawl_session.id, status="pending")
    db.add(scan)
    await db.commit()
    await db.refresh(scan)

    scanner = SeoScanner(
        session_factory=async_session,
        project_id=project.id,
        scan_id=scan.id,
        on_progress=lambda data: _broadcast_seo_progress(project.id, data),
    )
    active_seo_scanners[scan.id] = scanner

    asyncio.create_task(_run_seo_scanner(scanner, scan.id))

    return SeoScanResponse.model_validate(scan)


@router.get("/{project_id}/seo/scan", response_model=SeoScanResponse)
async def get_latest_seo_scan(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SeoScan)
        .where(SeoScan.project_id == project_id)
        .order_by(desc(SeoScan.started_at))
        .limit(1)
    )
    scan = result.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="No hay escaneo SEO")
    return SeoScanResponse.model_validate(scan)


@router.get("/{project_id}/seo/checks", response_model=SeoCheckListResponse)
async def get_seo_checks(
    project_id: int,
    page: int = 1,
    page_size: int = 50,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    passed: Optional[bool] = None,
    url: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    scan_result = await db.execute(
        select(SeoScan)
        .where(SeoScan.project_id == project_id)
        .order_by(desc(SeoScan.started_at))
        .limit(1)
    )
    scan = scan_result.scalar_one_or_none()
    if not scan:
        return SeoCheckListResponse(checks=[], total=0, page=page, page_size=page_size)

    query = select(SeoCheck).where(SeoCheck.scan_id == scan.id)
    count_base = select(func.count()).select_from(SeoCheck).where(SeoCheck.scan_id == scan.id)

    if category:
        query = query.where(SeoCheck.category == category)
        count_base = count_base.where(SeoCheck.category == category)
    if severity:
        query = query.where(SeoCheck.severity == severity)
        count_base = count_base.where(SeoCheck.severity == severity)
    if passed is not None:
        query = query.where(SeoCheck.passed == (1 if passed else 0))
        count_base = count_base.where(SeoCheck.passed == (1 if passed else 0))
    if url:
        query = query.where(SeoCheck.url.ilike(f"%{url}%"))
        count_base = count_base.where(SeoCheck.url.ilike(f"%{url}%"))

    total_result = await db.execute(count_base)
    total = total_result.scalar() or 0

    query = query.order_by(
        SeoCheck.severity.desc(),
        SeoCheck.check_name,
    ).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    checks = result.scalars().all()

    return SeoCheckListResponse(
        checks=[SeoCheckResponse.model_validate(c) for c in checks],
        total=total, page=page, page_size=page_size,
    )


@router.get("/{project_id}/seo/summary")
async def get_seo_summary(project_id: int, db: AsyncSession = Depends(get_db)):
    scan_result = await db.execute(
        select(SeoScan)
        .where(SeoScan.project_id == project_id)
        .order_by(desc(SeoScan.started_at))
        .limit(1)
    )
    scan = scan_result.scalar_one_or_none()
    if not scan:
        return {"has_scan": False}

    categories = await db.execute(
        select(SeoCheck.category, func.count(SeoCheck.id))
        .where(SeoCheck.scan_id == scan.id)
        .group_by(SeoCheck.category)
    )
    category_counts = {cat: count for cat, count in categories}

    failed_by_severity = await db.execute(
        select(SeoCheck.severity, func.count(SeoCheck.id))
        .where(SeoCheck.scan_id == scan.id, SeoCheck.passed == 0)
        .group_by(SeoCheck.severity)
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
        "warning_count": scan.warning_count,
        "good_count": scan.good_count,
        "info_count": scan.info_count,
        "category_counts": category_counts,
        "severity_failed": severity_failed,
    }


@router.websocket("/ws/{project_id}/seo")
async def websocket_seo_progress(websocket: WebSocket, project_id: int):
    await websocket.accept()
    if project_id not in active_seo_ws:
        active_seo_ws[project_id] = []
    active_seo_ws[project_id].append(websocket)
    try:
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        if project_id in active_seo_ws:
            active_seo_ws[project_id].remove(websocket)
            if not active_seo_ws[project_id]:
                del active_seo_ws[project_id]


async def _broadcast_seo_progress(project_id: int, data: dict):
    ws_list = active_seo_ws.get(project_id, [])
    for ws in ws_list:
        try:
            await ws.send_json(data)
        except Exception:
            pass


async def _run_seo_scanner(scanner: SeoScanner, scan_id: int):
    try:
        await scanner.run()
    except Exception as e:
        logger.error(f"Error en escaneo SEO {scan_id}: {e}", exc_info=True)
    finally:
        if scan_id in active_seo_scanners:
            del active_seo_scanners[scan_id]