from fastapi import APIRouter
from app.api.projects import router as projects_router
from app.api.crawl import router as crawl_router
from app.api.security import router as security_router
from app.api.seo import router as seo_router

router = APIRouter()
router.include_router(projects_router, prefix="/projects", tags=["projects"])
router.include_router(crawl_router, prefix="/projects", tags=["crawl"])
router.include_router(security_router, prefix="/projects", tags=["security"])
router.include_router(seo_router, prefix="/projects", tags=["seo"])
