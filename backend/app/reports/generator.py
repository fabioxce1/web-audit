import io
import json
import datetime
from typing import Optional

from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, CrawlSession
from app.models.security import SecurityScan, SecurityCheck
from app.models.seo import SeoScan, SeoCheck


async def get_dashboard_data(db: AsyncSession, project_id: int) -> dict | None:
    """Consolidated dashboard data for a project."""
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        return None

    security = (await db.execute(
        select(SecurityScan).where(SecurityScan.project_id == project_id).order_by(desc(SecurityScan.started_at)).limit(1)
    )).scalar_one_or_none()

    seo = (await db.execute(
        select(SeoScan).where(SeoScan.project_id == project_id).order_by(desc(SeoScan.started_at)).limit(1)
    )).scalar_one_or_none()

    session = (await db.execute(
        select(CrawlSession).where(CrawlSession.project_id == project_id).order_by(desc(CrawlSession.started_at)).limit(1)
    )).scalar_one_or_none()

    result = {
        "project": {
            "id": project.id,
            "name": project.name,
            "seed_url": project.seed_url,
            "status": project.status.value if hasattr(project.status, 'value') else project.status,
            "created_at": project.created_at.isoformat() if project.created_at else None,
        },
        "crawl": _session_data(session),
        "security": _security_data(security),
        "seo": _seo_data(seo),
        "overall_score": 0,
    }

    scores = []
    if security and security.score is not None:
        scores.append(security.score)
    if seo and seo.score is not None:
        scores.append(seo.score)

    if scores:
        result["overall_score"] = round(sum(scores) / len(scores))

    return result


async def get_json_export(db: AsyncSession, project_id: int) -> dict | None:
    """Full structured JSON export of all scan data."""
    dashboard = await get_dashboard_data(db, project_id)
    if not dashboard:
        return None

    security = (await db.execute(
        select(SecurityScan).where(SecurityScan.project_id == project_id).order_by(desc(SecurityScan.started_at)).limit(1)
    )).scalar_one_or_none()

    seo = (await db.execute(
        select(SeoScan).where(SeoScan.project_id == project_id).order_by(desc(SeoScan.started_at)).limit(1)
    )).scalar_one_or_none()

    if security:
        checks = (await db.execute(
            select(SecurityCheck).where(SecurityCheck.scan_id == security.id).order_by(SecurityCheck.severity.desc())
        )).scalars().all()
        dashboard["security"]["checks"] = [
            {"id": c.id, "url": c.url, "category": c.category, "check_name": c.check_name,
             "severity": c.severity, "value_found": c.value_found, "value_expected": c.value_expected,
             "recommendation": c.recommendation, "passed": bool(c.passed)}
            for c in checks
        ]

    if seo:
        checks = (await db.execute(
            select(SeoCheck).where(SeoCheck.scan_id == seo.id).order_by(SeoCheck.severity.desc())
        )).scalars().all()
        dashboard["seo"]["checks"] = [
            {"id": c.id, "url": c.url, "category": c.category, "check_name": c.check_name,
             "severity": c.severity, "value_found": c.value_found, "value_expected": c.value_expected,
             "recommendation": c.recommendation, "score_impact": c.score_impact, "passed": bool(c.passed)}
            for c in checks
        ]

    dashboard["exported_at"] = datetime.datetime.utcnow().isoformat()
    dashboard["version"] = "1.0"
    return dashboard


async def generate_pdf(db: AsyncSession, project_id: int) -> bytes | None:
    """Generate a professional PDF audit report."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.lib.units import mm, cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

    dashboard = await get_dashboard_data(db, project_id)
    if not dashboard:
        return None

    security = (await db.execute(
        select(SecurityScan).where(SecurityScan.project_id == project_id).order_by(desc(SecurityScan.started_at)).limit(1)
    )).scalar_one_or_none()

    seo = (await db.execute(
        select(SeoScan).where(SeoScan.project_id == project_id).order_by(desc(SeoScan.started_at)).limit(1)
    )).scalar_one_or_none()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('CustomTitle', parent=styles['Title'], fontSize=22, spaceAfter=6, textColor=HexColor('#1a56db'))
    heading1 = ParagraphStyle('Heading1', parent=styles['Heading1'], fontSize=16, spaceBefore=20, spaceAfter=10, textColor=HexColor('#1e293b'))
    heading2 = ParagraphStyle('Heading2', parent=styles['Heading2'], fontSize=13, spaceBefore=14, spaceAfter=6, textColor=HexColor('#334155'))
    normal = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=10, leading=14, spaceAfter=8)
    small = ParagraphStyle('Small', parent=styles['Normal'], fontSize=8, leading=10, textColor=HexColor('#64748b'))
    good = ParagraphStyle('Good', parent=normal, textColor=HexColor('#16a34a'))
    warning = ParagraphStyle('Warning', parent=normal, textColor=HexColor('#d97706'))
    critical = ParagraphStyle('Critical', parent=normal, textColor=HexColor('#dc2626'))
    info = ParagraphStyle('Info', parent=normal, textColor=HexColor('#6b7280'))

    story = []

    # ─── Cover ───
    story.append(Spacer(1, 3*cm))
    story.append(Paragraph("WebAudit Report", title_style))
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(f"<b>Project:</b> {dashboard['project']['name']}", normal))
    story.append(Paragraph(f"<b>URL:</b> {dashboard['project']['seed_url']}", normal))
    story.append(Paragraph(f"<b>Date:</b> {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC", normal))
    story.append(Paragraph(f"<b>Generated by:</b> WebAudit v1.0", normal))
    story.append(Spacer(1, 2*cm))

    overall = dashboard.get("overall_score", 0)
    score_color = HexColor('#16a34a') if overall >= 70 else HexColor('#d97706') if overall >= 40 else HexColor('#dc2626')
    score_style = ParagraphStyle('Score', parent=title_style, fontSize=28, textColor=score_color)
    story.append(Paragraph(f"Overall Score: {overall}/100", score_style))
    story.append(Spacer(1, 1*cm))

    s = dashboard.get("security") or {}
    ss = dashboard.get("seo") or {}
    score_data = [
        ["Category", "Score", "Critical/High", "Warnings/Info"],
        ["Security", str(s.get("score", "N/A")), f"{s.get('critical_count',0)}+{s.get('high_count',0)}", f"{s.get('medium_count',0)}+{s.get('low_count',0)}"],
        ["SEO", str(ss.get("score", "N/A")), str(ss.get("critical_count", 0)), f"{ss.get('warning_count',0)}+{ss.get('info_count',0)}"],
        ["Overall", str(overall), "", ""],
    ]
    score_table = Table(score_data, colWidths=[4*cm, 3*cm, 4*cm, 4*cm])
    score_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#1e293b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#475569')),
        ('BACKGROUND', (0, 1), (-1, 1), HexColor('#f1f5f9')),
        ('BACKGROUND', (0, 2), (-1, 2), HexColor('#ffffff')),
        ('BACKGROUND', (0, 3), (-1, 3), HexColor('#f8fafc')),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(score_table)
    story.append(PageBreak())

    # ─── Security Findings ───
    story.append(Paragraph("1. Security Findings", heading1))
    if security:
        security_checks = (await db.execute(
            select(SecurityCheck).where(SecurityCheck.scan_id == security.id).where(SecurityCheck.passed == 0).order_by(SecurityCheck.severity.desc())
        )).scalars().all()

        if security_checks:
            story.append(Paragraph(f"<b>{len(security_checks)} security issues found</b> — {s.get('critical_count',0)} critical, {s.get('high_count',0)} high, {s.get('medium_count',0)} medium, {s.get('low_count',0)} low", normal))
            story.append(Spacer(1, 0.5*cm))

            sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
            security_checks.sort(key=lambda c: sev_order.get(c.severity, 99))

            for check in security_checks[:30]:
                sev_color = '#dc2626' if check.severity == 'critical' else '#d97706' if check.severity == 'high' else '#ca8a04' if check.severity == 'medium' else '#6b7280'
                story.append(Paragraph(f"<font color='{sev_color}'><b>[{check.severity.upper()}]</b></font> {check.check_name}", heading2))
                if check.recommendation:
                    story.append(Paragraph(f"<b>Recommendation:</b> {check.recommendation}", normal))
                if check.value_found:
                    story.append(Paragraph(f"<font size='8'>Found: {check.value_found[:150]}</font>", small))
        else:
            story.append(Paragraph("No security issues found.", good))
    else:
        story.append(Paragraph("No security scan has been performed.", info))
    story.append(PageBreak())

    # ─── SEO Findings ───
    story.append(Paragraph("2. SEO Findings", heading1))
    if seo:
        seo_checks = (await db.execute(
            select(SeoCheck).where(SeoCheck.scan_id == seo.id).where(SeoCheck.passed == 0).order_by(SeoCheck.severity.desc())
        )).scalars().all()

        if seo_checks:
            story.append(Paragraph(f"<b>{len(seo_checks)} SEO issues found</b> — {ss.get('critical_count',0)} critical, {ss.get('warning_count',0)} warnings, {ss.get('info_count',0)} info", normal))
            story.append(Spacer(1, 0.5*cm))

            seo_sev = {"critical": 0, "warning": 1, "info": 2, "good": 3}
            seo_checks.sort(key=lambda c: seo_sev.get(c.severity, 99))

            for check in seo_checks[:30]:
                sev_color = '#dc2626' if check.severity == 'critical' else '#d97706' if check.severity == 'warning' else '#6b7280'
                story.append(Paragraph(f"<font color='{sev_color}'><b>[{check.severity.upper()}]</b></font> {check.check_name} — <font size='8'>{check.url[:60]}</font>", heading2))
                if check.recommendation:
                    story.append(Paragraph(f"<b>Recommendation:</b> {check.recommendation}", normal))
                if check.value_found:
                    story.append(Paragraph(f"<font size='8'>Found: {check.value_found[:150]}</font>", small))
        else:
            story.append(Paragraph("No SEO issues found.", good))
    else:
        story.append(Paragraph("No SEO analysis has been performed.", info))

    story.append(PageBreak())

    # ─── Methodology ───
    story.append(Paragraph("3. Methodology & Disclaimer", heading1))
    story.append(Paragraph("<b>Security:</b> Tests include HTTP security headers, SSL/TLS validation, cookie attributes, CORS configuration, WAF detection, open port scanning, email security (SPF/DMARC), information disclosure, technology fingerprinting, and access control checks. Active pentest includes injection (SQL/NoSQL/CMD), XSS, SSRF, BOLA/IDOR, and mass assignment testing.", normal))
    story.append(Paragraph("<b>SEO:</b> Analysis covers meta tags (title, description, viewport, robots), Open Graph and Twitter Cards, canonical URLs, heading structure, image optimization (alt text, lazy loading), content quality, structured data, and performance metrics.", normal))
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph("<b>Disclaimer:</b> This report is generated automatically by WebAudit. It is intended for the authorized owner of the audited website only. Findings should be manually verified before taking action. Scores are based on automated heuristics and may not reflect all security or SEO aspects of the site.", small))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def _session_data(session) -> dict | None:
    if not session:
        return None
    return {
        "id": session.id,
        "status": session.status.value if hasattr(session.status, 'value') else session.status,
        "urls_found": session.urls_found,
        "urls_crawled": session.urls_crawled,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "completed_at": session.completed_at.isoformat() if session.completed_at else None,
    }


def _security_data(scan) -> dict | None:
    if not scan:
        return None
    return {
        "id": scan.id, "status": scan.status,
        "score": scan.score, "urls_scanned": scan.urls_scanned,
        "total_checks": scan.total_checks,
        "critical_count": scan.critical_count, "high_count": scan.high_count,
        "medium_count": scan.medium_count, "low_count": scan.low_count, "info_count": scan.info_count,
        "started_at": scan.started_at.isoformat() if scan.started_at else None,
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
    }


def _seo_data(scan) -> dict | None:
    if not scan:
        return None
    return {
        "id": scan.id, "status": scan.status,
        "score": scan.score, "urls_scanned": scan.urls_scanned,
        "total_checks": scan.total_checks,
        "critical_count": scan.critical_count, "warning_count": scan.warning_count,
        "good_count": scan.good_count, "info_count": scan.info_count,
        "started_at": scan.started_at.isoformat() if scan.started_at else None,
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
    }