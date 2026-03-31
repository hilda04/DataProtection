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
        "summary": (
            f"Overall maturity is {maturity_level} with a score of {score:.2f}%. "
            "Review remediation priorities and evidence requirements in the Audit Pack."
        ),
        "completed_at": datetime.utcnow().isoformat() + "Z",
        "sections": sections,
        "risks": risks,
        "recommendations": recommendations,
    }


def build_assessment_report_pdf(report: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    organisation = report.get('organisation', {})
    framework = report.get('framework', {})
    score = float(report.get('score') or 0.0)
    maturity = str(report.get('maturity_level') or map_maturity_level(score))
    sections = report.get('sections') or []
    recommended_actions = report.get('recommendedActions') or report.get('recommendations') or []
    summary = str(report.get('summary') or '').strip()

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title='Data Protection Assessment Report',
    )
    styles = getSampleStyleSheet()
    story: list[Any] = []

    story.append(Paragraph('Data Protection Assessment Report', styles['Title']))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Organisation: {organisation.get('name', 'N/A')}", styles['BodyText']))
    story.append(
        Paragraph(
            f"Framework: {framework.get('name', 'N/A')} (v{framework.get('version', 'N/A')})",
            styles['BodyText'],
        )
    )
    completed_at = report.get('completed_at', datetime.utcnow().isoformat() + 'Z')
    story.append(Paragraph(f'Date: {completed_at}', styles['BodyText']))
    story.append(Spacer(1, 14))

    story.append(Paragraph('Executive Summary', styles['Heading2']))
    story.append(Paragraph(f"Overall score: <b>{score:.2f}%</b>", styles['BodyText']))
    story.append(Paragraph(f"Maturity level: <b>{maturity}</b>", styles['BodyText']))
    if summary:
        story.append(Spacer(1, 4))
        story.append(Paragraph(summary, styles['BodyText']))
    story.append(Spacer(1, 14))

    story.append(Paragraph('Section Scores', styles['Heading2']))
    section_rows = [['Section', 'Score']]
    for section in sections:
        section_rows.append(
            [
                str(section.get('name', 'Section')),
                f"{float(section.get('score', 0)):.2f}%",
            ]
        )
    section_table = Table(section_rows, colWidths=[120 * mm, 35 * mm])
    section_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E2E8F0')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
            ]
        )
    )
    story.append(section_table)
    story.append(Spacer(1, 14))

    story.append(Paragraph('Remediation Plan', styles['Heading2']))
    if not recommended_actions:
        story.append(
            Paragraph(
                'No critical gaps were found for this assessment.',
                styles['BodyText'],
            )
        )
    else:
        for item in recommended_actions:
            issue = str(
                item.get('title')
                or item.get('issue')
                or item.get('question')
                or 'Control gap identified'
            )
            risk = str(item.get('risk') or item.get('risk_level') or 'Risk not specified')
            actions = item.get('actions')
            if not isinstance(actions, list) or not actions:
                fallback_action = item.get('action') or item.get('recommendation')
                actions = [
                    str(fallback_action or 'Define and implement corrective controls.').strip()
                ]
            priority = str(item.get('priority') or item.get('severity') or 'MEDIUM').upper()
            story.append(Paragraph(f"<b>Gap:</b> {issue}", styles['BodyText']))
            story.append(Paragraph(f"<b>Priority:</b> {priority}", styles['BodyText']))
            story.append(Paragraph(f"<b>Risk:</b> {risk}", styles['BodyText']))
            story.append(Paragraph("<b>Actions:</b>", styles['BodyText']))
            for action in actions:
                story.append(Paragraph(f"[ ] {str(action).strip()}", styles['BodyText']))
            story.append(Spacer(1, 8))

    story.append(Spacer(1, 8))
    story.append(Paragraph('Evidence Checklist', styles['Heading2']))
    if not recommended_actions:
        story.append(Paragraph('No additional evidence requested.', styles['BodyText']))
    else:
        for item in recommended_actions:
            issue = str(
                item.get('title')
                or item.get('issue')
                or item.get('question')
                or 'Control gap identified'
            )
            evidence = item.get('evidence')
            if not isinstance(evidence, list) or not evidence:
                evidence = ['Implementation plan and approval records.']
            story.append(Paragraph(f"<b>{issue}</b>", styles['BodyText']))
            for evidence_item in evidence:
                story.append(Paragraph(f"- {str(evidence_item).strip()}", styles['BodyText']))
            story.append(Spacer(1, 8))

    document.build(story)
    return buffer.getvalue()


def map_maturity_level(score: float) -> str:
    if score <= 40:
        return "Basic"
    if score <= 60:
        return "Developing"
    if score <= 80:
        return "Defined"
    return "Managed"
