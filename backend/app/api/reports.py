from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import io

from app.db import get_db
from app.reports.generator import get_dashboard_data, get_json_export, generate_pdf

router = APIRouter()


@router.get("/{project_id}/dashboard")
async def get_dashboard(project_id: int, db: AsyncSession = Depends(get_db)):
    data = await get_dashboard_data(db, project_id)
    if not data:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return data


@router.get("/{project_id}/export/json")
async def export_json(project_id: int, db: AsyncSession = Depends(get_db)):
    data = await get_json_export(db, project_id)
    if not data:
        raise HTTPException(status_code=404, detail="No hay datos para exportar")

    import json
    json_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    return Response(
        content=json_str,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=webaudit-{project_id}.json"},
    )


@router.get("/{project_id}/export/pdf")
async def export_pdf(project_id: int, db: AsyncSession = Depends(get_db)):
    pdf_bytes = await generate_pdf(db, project_id)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="No se pudo generar el PDF. Realiza un escaneo de seguridad y SEO primero.")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=webaudit-report-{project_id}.pdf"},
    )