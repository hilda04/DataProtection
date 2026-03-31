from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any


def build_assessment_report(
    organisation: dict[str, Any],
    framework: dict[str, Any],
    score: float,
    sections: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
) -> dict[str, Any]:
    maturity_level = map_maturity_level(score)

    return {
        "organisation": organisation,
        "framework": framework,
        "score": score,
        "maturity_level": maturity_level,
        "completed_at": datetime.utcnow().isoformat() + "Z",
        "sections": sections,
        "risks": risks,
        "recommendations": recommendations,
    }


def build_assessment_report_pdf(report: dict[str, Any]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    organisation = report.get('organisation', {})
    framework = report.get('framework', {})
    score = float(report.get('score') or 0.0)
    maturity = str(report.get('maturity_level') or map_maturity_level(score))
    sections = report.get('sections') or []
    recommendations = report.get('recommendations') or []

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    y = 800
    pdf.setTitle('Data Protection Assessment Report')
    pdf.setFont('Helvetica-Bold', 16)
    pdf.drawString(72, y, 'Data Protection Assessment Report')
    y -= 30

    pdf.setFont('Helvetica', 11)
    pdf.drawString(72, y, f"Organisation: {organisation.get('name', 'N/A')}")
    y -= 18
    pdf.drawString(
        72,
        y,
        f"Framework: {framework.get('name', 'N/A')} (v{framework.get('version', 'N/A')})",
    )
    y -= 18
    pdf.drawString(72, y, f'Score: {score:.2f}%')
    y -= 18
    pdf.drawString(72, y, f'Maturity Level: {maturity}')
    y -= 30

    pdf.setFont('Helvetica-Bold', 12)
    pdf.drawString(72, y, 'Section Scores')
    y -= 20
    pdf.setFont('Helvetica', 10)
    for section in sections:
        pdf.drawString(
            90,
            y,
            f"{section.get('name', 'Section')}: {float(section.get('score', 0)):.2f}%",
        )
        y -= 16
        if y < 72:
            pdf.showPage()
            y = 800
            pdf.setFont('Helvetica', 10)

    if recommendations:
        y -= 8
        pdf.setFont('Helvetica-Bold', 12)
        pdf.drawString(72, y, 'Top Recommendations')
        y -= 18
        pdf.setFont('Helvetica', 10)
        for recommendation in recommendations[:10]:
            text = str(recommendation.get('recommendation', 'Improve identified control gaps.'))
            pdf.drawString(90, y, f'- {text[:110]}')
            y -= 14
            if y < 72:
                pdf.showPage()
                y = 800
                pdf.setFont('Helvetica', 10)

    pdf.save()
    return buffer.getvalue()


def map_maturity_level(score: float) -> str:
    if score <= 40:
        return "Basic"
    if score <= 60:
        return "Developing"
    if score <= 80:
        return "Defined"
    return "Managed"
