from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from app.db import get_db
from app.models.project import Project, ProjectStatus
from app.config import settings

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    seed_url: str = Field(..., min_length=1, max_length=2048)
    config: dict = Field(default_factory=dict)


class ProjectResponse(BaseModel):
    id: int
    name: str
    seed_url: str
    config: dict
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
    total: int


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_db)):
    default_config = {
        "user_agent": settings.user_agent,
        "max_workers": settings.max_workers,
        "crawl_delay": settings.crawl_delay,
        "respect_robots_txt": settings.respect_robots_txt,
        "use_playwright": settings.use_playwright,
        "follow_redirects": settings.follow_redirects,
        "max_redirects": settings.max_redirects,
        "timeout": settings.timeout,
        "max_urls": settings.max_urls,
        "max_depth": settings.max_depth,
        "crawl_assets": False,
        "exclude_patterns": settings.exclude_patterns,
        "save_html_snapshots": settings.save_html_snapshots,
        "headless": settings.headless,
        "viewport_width": settings.viewport_width,
        "viewport_height": settings.viewport_height,
    }
    default_config.update(data.config or {})

    project = Project(
        name=data.name,
        seed_url=data.seed_url,
        config=default_config,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("", response_model=ProjectListResponse)
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    projects = result.scalars().all()
    return ProjectListResponse(
        projects=[ProjectResponse.model_validate(p) for p in projects],
        total=len(projects),
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    await db.delete(project)
    await db.commit()


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    project.name = data.name
    project.seed_url = data.seed_url
    if data.config:
        project.config = {**project.config, **data.config}

    await db.commit()
    await db.refresh(project)
    return project
