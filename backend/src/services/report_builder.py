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
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ModuleNotFoundError:
        return (
            'Data Protection Assessment Report\n'
            f"Organisation: {report.get('organisation', {}).get('name', 'N/A')}\n"
            f"Framework: {report.get('framework', {}).get('name', 'N/A')}\n"
            f"Score: {float(report.get('score') or 0.0):.2f}%\n"
        ).encode('utf-8')

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title='Data Protection Assessment Report',
    )

    styles = getSampleStyleSheet()
    heading_style = styles['Heading1']
    heading_style.fontName = 'Helvetica-Bold'
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#444444'),
    )
    section_heading = styles['Heading3']
    section_heading.textColor = colors.HexColor('#1f3c88')

    organisation = report.get('organisation', {})
    framework = report.get('framework', {})
    score = float(report.get('score') or 0.0)
    maturity = str(report.get('maturity_level') or map_maturity_level(score))
    completed_at = str(report.get('completed_at') or '')
    sections = report.get('sections') or []
    risks = report.get('risks') or []
    recommendations = report.get('recommendations') or []

    content: list[Any] = [
        Paragraph('Data Protection Compliance Assessment Report', heading_style),
        Spacer(1, 6),
        Paragraph(
            (
                f"Organisation: <b>{organisation.get('name', 'N/A')}</b><br/>"
                f"Framework: <b>{framework.get('name', 'N/A')}</b> "
                f"(v{framework.get('version', 'N/A')})<br/>"
                f"Completion Date: <b>{completed_at or 'N/A'}</b>"
            ),
            subtitle_style,
        ),
        Spacer(1, 14),
        Paragraph('Executive Summary', section_heading),
        Paragraph(
            (
                'This report summarises your latest control responses and identifies key '
                'areas to improve data protection readiness.'
            ),
            styles['BodyText'],
        ),
        Spacer(1, 8),
        Paragraph(f'Overall Score: <b>{score:.2f}%</b>', styles['BodyText']),
        Paragraph(f'Maturity Level: <b>{maturity}</b>', styles['BodyText']),
        Spacer(1, 12),
        Paragraph('Section Score Breakdown', section_heading),
    ]

    table_data = [['Section', 'Score (%)']]
    for item in sections:
        table_data.append(
            [str(item.get('name') or 'Unknown'), f"{float(item.get('score') or 0):.2f}"]
        )
    if len(table_data) == 1:
        table_data.append(['No section scores available', '-'])

    table = Table(table_data, hAlign='LEFT', colWidths=[120 * mm, 40 * mm])
    table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f3c88')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]
        )
    )
    content.extend([table, Spacer(1, 12), Paragraph('Key Findings / Gaps', section_heading)])

    if risks:
        for risk in risks[:20]:
            content.append(
                Paragraph(
                    (
                        f"• [{risk.get('risk_level', 'MEDIUM')}] "
                        f"{risk.get('question', 'Control gap identified')}"
                    ),
                    styles['BodyText'],
                )
            )
    else:
        content.append(Paragraph('• No significant gaps identified.', styles['BodyText']))

    content.extend([Spacer(1, 12), Paragraph('Recommendations', section_heading)])
    if recommendations:
        for recommendation in recommendations[:20]:
            content.append(
                Paragraph(
                    f"• {recommendation.get('recommendation', 'Improve identified control gaps.')}",
                    styles['BodyText'],
                )
            )
    else:
        content.append(
            Paragraph('• Maintain current controls and continue monitoring.', styles['BodyText'])
        )

    document.build(content)
    return buffer.getvalue()


def map_maturity_level(score: float) -> str:
    if score <= 40:
        return "Basic"
    if score <= 60:
        return "Developing"
    if score <= 80:
        return "Defined"
    return "Managed"
