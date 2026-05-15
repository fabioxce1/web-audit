import asyncio
import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from pydantic import BaseModel
from datetime import datetime

from app.db import get_db, async_session
from app.models.project import Project, CrawlSession, ProjectStatus, CrawlSessionStatus
from app.models.url import DiscoveredURL
from app.crawler.engine import CrawlerEngine

logger = logging.getLogger(__name__)

router = APIRouter()

active_engines: dict[int, CrawlerEngine] = {}
active_websockets: dict[int, list[WebSocket]] = {}


class CrawlStartResponse(BaseModel):
    session_id: int
    status: str
    message: str


class UrlResponse(BaseModel):
    id: int
    url: str
    normalized_url: str
    status_code: Optional[int]
    content_type: Optional[str]
    depth: int
    parent_url: Optional[str]
    title: Optional[str]
    links_count: int
    crawled_at: Optional[datetime]
    is_external: Optional[bool] = False
    is_duplicate: Optional[bool] = False
    is_broken: Optional[bool] = False
    content_hash: Optional[str] = None
    redirect_url: Optional[str] = None
    error_message: Optional[str]
    response_time_ms: Optional[int]
    discovery_method: Optional[str] = "crawl"

    model_config = {"from_attributes": True}

    @classmethod
    def _coerce_bools(cls, v):
        if v is None:
            return False
        return v

    def __init__(self, **data):
        for field in ('is_external', 'is_duplicate', 'is_broken'):
            if field in data and data[field] is None:
                data[field] = False
        if 'discovery_method' in data and data['discovery_method'] is None:
            data['discovery_method'] = 'crawl'
        super().__init__(**data)


class UrlListResponse(BaseModel):
    urls: list[UrlResponse]
    total: int
    page: int
    page_size: int
    total_broken: int = 0
    total_ok: int = 0


class CrawlStatsResponse(BaseModel):
    session_id: int
    status: str
    urls_found: int
    urls_crawled: int
    total_broken: int
    total_ok: int
    started_at: datetime | None = None
    completed_at: datetime | None = None


@router.post("/{project_id}/crawl", response_model=CrawlStartResponse)
async def start_crawl(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    if project.status == ProjectStatus.crawling:
        raise HTTPException(status_code=409, detail="El proyecto ya tiene un crawling en curso")

    session = CrawlSession(project_id=project.id, status=CrawlSessionStatus.running)
    db.add(session)
    await db.commit()
    await db.refresh(session)

    engine = CrawlerEngine(
        session_factory=async_session,
        project_id=project.id,
        session_id=session.id,
        config=project.config or {},
        on_progress=lambda data: _broadcast_progress(project.id, data),
    )

    active_engines[session.id] = engine

    asyncio.create_task(_run_engine(engine, session.id, project.id, project.seed_url))

    return CrawlStartResponse(
        session_id=session.id,
        status="running",
        message="Crawling iniciado",
    )


@router.post("/{project_id}/crawl/stop")
async def stop_crawl(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CrawlSession)
        .where(CrawlSession.project_id == project_id)
        .where(CrawlSession.status == CrawlSessionStatus.running)
        .order_by(desc(CrawlSession.started_at))
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="No hay crawling activo para este proyecto")

    engine = active_engines.get(session.id)
    if engine:
        await engine.stop()

    return {"message": "Crawling detenido", "session_id": session.id}


@router.get("/{project_id}/stats", response_model=CrawlStatsResponse)
async def get_crawl_stats(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CrawlSession)
        .where(CrawlSession.project_id == project_id)
        .order_by(desc(CrawlSession.started_at))
        .limit(1)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="No hay sesión de crawling")

    total_broken_result = await db.execute(
        select(func.count()).select_from(DiscoveredURL).where(
            DiscoveredURL.session_id == session.id,
            DiscoveredURL.is_broken == True,
        )
    )
    total_broken = total_broken_result.scalar() or 0

    total_ok_result = await db.execute(
        select(func.count()).select_from(DiscoveredURL).where(
            DiscoveredURL.session_id == session.id,
            DiscoveredURL.is_broken == False,
        )
    )
    total_ok = total_ok_result.scalar() or 0

    return CrawlStatsResponse(
        session_id=session.id,
        status=session.status.value if hasattr(session.status, 'value') else session.status,
        urls_found=session.urls_found,
        urls_crawled=session.urls_crawled,
        total_broken=total_broken,
        total_ok=total_ok,
        started_at=session.started_at,
        completed_at=session.completed_at,
    )


@router.get("/{project_id}/urls", response_model=UrlListResponse)
async def list_urls(
    project_id: int,
    page: int = 1,
    page_size: int = 50,
    status_code: Optional[int] = None,
    content_type: Optional[str] = None,
    is_broken: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CrawlSession)
        .where(CrawlSession.project_id == project_id)
        .order_by(desc(CrawlSession.started_at))
        .limit(1)
    )
    session = result.scalar_one_or_none()

    if not session:
        return UrlListResponse(urls=[], total=0, page=page, page_size=page_size)

    total_broken_result = await db.execute(
        select(func.count()).select_from(DiscoveredURL).where(
            DiscoveredURL.session_id == session.id,
            DiscoveredURL.is_broken == True,
        )
    )
    total_broken = total_broken_result.scalar() or 0

    total_ok_result = await db.execute(
        select(func.count()).select_from(DiscoveredURL).where(
            DiscoveredURL.session_id == session.id,
            DiscoveredURL.is_broken == False,
        )
    )
    total_ok = total_ok_result.scalar() or 0

    query = select(DiscoveredURL).where(DiscoveredURL.session_id == session.id)

    if status_code is not None:
        query = query.where(DiscoveredURL.status_code == status_code)
    if content_type:
        query = query.where(DiscoveredURL.content_type.ilike(f"%{content_type}%"))
    if is_broken is not None:
        query = query.where(DiscoveredURL.is_broken == is_broken)

    count_query = select(DiscoveredURL).where(DiscoveredURL.session_id == session.id)
    if status_code is not None:
        count_query = count_query.where(DiscoveredURL.status_code == status_code)
    if content_type:
        count_query = count_query.where(DiscoveredURL.content_type.ilike(f"%{content_type}%"))
    if is_broken is not None:
        count_query = count_query.where(DiscoveredURL.is_broken == is_broken)

    total_result = await db.execute(count_query)
    total = len(total_result.scalars().all())

    query = query.order_by(DiscoveredURL.crawled_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    urls = result.scalars().all()

    return UrlListResponse(
        urls=[UrlResponse.model_validate(u) for u in urls],
        total=total,
        page=page,
        page_size=page_size,
        total_broken=total_broken,
        total_ok=total_ok,
    )


@router.get("/{project_id}/tree")
async def get_url_tree(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CrawlSession)
        .where(CrawlSession.project_id == project_id)
        .order_by(desc(CrawlSession.started_at))
        .limit(1)
    )
    session = result.scalar_one_or_none()

    if not session:
        return {"tree": [], "root_url": ""}

    result = await db.execute(
        select(DiscoveredURL).where(DiscoveredURL.session_id == session.id)
    )
    urls = result.scalars().all()

    url_map: dict = {}
    for u in urls:
        url_map[u.normalized_url] = {
            "id": u.id,
            "url": u.url,
            "normalized_url": u.normalized_url,
            "status_code": u.status_code,
            "title": u.title,
            "depth": u.depth,
            "parent_url": u.parent_url,
            "content_type": u.content_type,
            "is_broken": u.is_broken,
            "discovery_method": u.discovery_method,
            "children": [],
        }

    root_urls = []
    for u in urls:
        node = url_map[u.normalized_url]
        parent = url_map.get(u.parent_url) if u.parent_url else None
        if parent and node is not parent:
            parent["children"].append(node)
        else:
            root_urls.append(node)

    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()

    return {
        "tree": root_urls,
        "root_url": project.seed_url if project else "",
    }


@router.websocket("/ws/{project_id}/crawl")
async def websocket_crawl_progress(websocket: WebSocket, project_id: int):
    await websocket.accept()

    if project_id not in active_websockets:
        active_websockets[project_id] = []
    active_websockets[project_id].append(websocket)

    try:
        while True:
            try:
                data = await websocket.receive_text()
                msg = json.loads(data)

                if msg.get("action") == "stop":
                    result = await _get_active_engine(project_id)
                    if result:
                        await result.stop()
                    await websocket.send_json({"type": "stopped"})
                    break
                elif msg.get("action") == "pause":
                    result = await _get_active_engine(project_id)
                    if result:
                        await result.pause()
                    await websocket.send_json({"type": "paused"})
                elif msg.get("action") == "resume":
                    result = await _get_active_engine(project_id)
                    if result:
                        await result.resume()
                    await websocket.send_json({"type": "resumed"})

            except WebSocketDisconnect:
                break
    finally:
        if project_id in active_websockets:
            active_websockets[project_id].remove(websocket)
            if not active_websockets[project_id]:
                del active_websockets[project_id]


async def _get_active_engine(project_id: int):
    async with async_session() as db:
        result = await db.execute(
            select(CrawlSession)
            .where(CrawlSession.project_id == project_id)
            .where(CrawlSession.status == CrawlSessionStatus.running)
            .order_by(desc(CrawlSession.started_at))
            .limit(1)
        )
        session = result.scalar_one_or_none()
    if session and session.id in active_engines:
        return active_engines[session.id]
    return None


async def _broadcast_progress(project_id: int, data: dict):
    ws_list = active_websockets.get(project_id, [])
    for ws in ws_list:
        try:
            await ws.send_json(data)
        except Exception:
            pass


async def _run_engine(engine: CrawlerEngine, session_id: int, project_id: int, seed_url: str):
    try:
        await engine.run(seed_url)
    except Exception as e:
        logger.error(f"Error en el motor de crawling para sesión {session_id}: {e}", exc_info=True)
        await _broadcast_progress(project_id, {
            "type": "crawl_error",
            "error": str(e),
        })
    finally:
        if session_id in active_engines:
            del active_engines[session_id]
        await engine.fetcher.close() if engine.fetcher else None
