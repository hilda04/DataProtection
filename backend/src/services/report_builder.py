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
    from reportlab import rl_config
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        ListFlowable,
        ListItem,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    rl_config.pageCompression = 0

    palette = {
        "navy": colors.HexColor("#12344D"),
        "teal": colors.HexColor("#1F8A8A"),
        "off_white": colors.HexColor("#F7F9FB"),
        "light_border": colors.HexColor("#D9E2EC"),
        "body": colors.HexColor("#243B53"),
        "muted": colors.HexColor("#5C6B7A"),
        "high": colors.HexColor("#C0392B"),
        "medium": colors.HexColor("#D68910"),
    }
    styles = _build_pdf_styles(palette, getSampleStyleSheet(), ParagraphStyle, colors)

    organisation = report.get("organisation", {})
    framework = report.get("framework", {})
    score = float(report.get("score") or 0.0)
    maturity = str(report.get("maturity_level") or map_maturity_level(score))
    sections = report.get("sections") or []
    recommended_actions = report.get("recommendedActions") or report.get("recommendations") or []
    summary = str(report.get("summary") or "").strip()
    completed_at = report.get("completed_at", datetime.utcnow().isoformat() + "Z")
    completion_date = str(completed_at).split("T", 1)[0]
    generated_on = datetime.utcnow().strftime("%Y-%m-%d")
    organisation_name = str(organisation.get("name") or "N/A")
    framework_name = str(framework.get("name") or "N/A")
    framework_version = str(framework.get("version") or "N/A")

    normalized_actions = _normalize_recommendations(recommended_actions)
    high_medium = [item for item in normalized_actions if item["priority"] in {"HIGH", "MEDIUM"}]

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=17 * mm,
        bottomMargin=17 * mm,
        title=f"{framework_name} Assessment Report",
    )
    story: list[Any] = []

    cover_score = Table(
        [
            [
                Paragraph("Overall Score", styles["LabelStyle"]),
                Paragraph(f"{score:.2f}%", styles["CoverMetric"]),
            ],
            [
                Paragraph("Maturity Level", styles["LabelStyle"]),
                Paragraph(maturity, styles["CoverMetric"]),
            ],
            [
                Paragraph("Summary", styles["LabelStyle"]),
                Paragraph(
                    summary
                    or (
                        f"Assessment indicates a {maturity.lower()} control posture with targeted "
                        "remediation opportunities."
                    ),
                    styles["BodyStyle"],
                ),
            ],
        ],
        colWidths=[40 * mm, 128 * mm],
    )
    cover_score.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), palette["off_white"]),
                ("BOX", (0, 0), (-1, -1), 0.8, palette["light_border"]),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, palette["light_border"]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    story.extend(
        [
            Spacer(1, 80),
            Paragraph(f"{framework_name} Assessment Report", styles["CoverTitle"]),
            Spacer(1, 10),
            Paragraph(f"{framework_name} v{framework_version}", styles["CoverSubtitle"]),
            Spacer(1, 14),
            Paragraph(f"Organisation  {organisation_name}", styles["BodyStyle"]),
            Paragraph(f"Assessment Date  {completion_date}", styles["MutedStyle"]),
            Spacer(1, 22),
            cover_score,
            Spacer(1, 120),
            Paragraph("Confidential", styles["FooterStyle"]),
            Paragraph("Generated by DataProtection App", styles["FooterStyle"]),
            PageBreak(),
        ]
    )

    story.append(Paragraph("Executive Summary", styles["SectionHeading"]))
    story.append(Spacer(1, 10))
    metric_values = [
        ["Overall Score", f"{score:.2f}%"],
        ["Maturity Level", maturity],
        ["Priority Gaps", str(len(high_medium))],
    ]
    metric_cards = []
    for label, value in metric_values:
        metric = Table(
            [[Paragraph(label, styles["MutedStyle"])], [Paragraph(value, styles["CardMetric"])]],
            colWidths=[56 * mm],
        )
        metric.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), palette["off_white"]),
                    ("BOX", (0, 0), (-1, -1), 0.8, palette["light_border"]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ]
            )
        )
        metric_cards.append(metric)
    story.append(Table([metric_cards], colWidths=[56 * mm, 56 * mm, 56 * mm]))

    strongest, weakest = _section_highlights(sections)
    story.append(Spacer(1, 14))
    story.append(Paragraph("Management Insight", styles["CardTitle"]))
    story.append(
        Paragraph(
            (
                f"Strongest area: {strongest}. Primary weakness: {weakest}. "
                "Immediate remediation focus should address high-risk control gaps first."
            ),
            styles["BodyStyle"],
        )
    )

    story.append(Spacer(1, 10))
    story.append(Paragraph("Top 5 Immediate Actions", styles["CardTitle"]))
    top_actions = high_medium[:5] if high_medium else normalized_actions[:5]
    story.append(
        ListFlowable(
            [
                ListItem(
                    Paragraph(
                        action["actions"][0] if action["actions"] else action["title"],
                        styles["BodyStyle"],
                    )
                )
                for action in top_actions
            ],
            bulletType="bullet",
        )
    )
    story.append(PageBreak())

    story.append(Paragraph("Section Performance", styles["SectionHeading"]))
    story.append(Spacer(1, 10))
    section_rows = [["Section", "Score", "Status"]]
    for section in sections:
        section_score = float(section.get("score", 0))
        section_rows.append(
            [
                Paragraph(str(section.get("name", "Section")), styles["BodyStyle"]),
                Paragraph(
                    f"{section_score:.2f}%  {_score_bar(section_score)}",
                    styles["BodyStyle"],
                ),
                Paragraph(_score_status(section_score), styles["BodyStyle"]),
            ]
        )

    section_table = Table(section_rows, colWidths=[93 * mm, 44 * mm, 31 * mm])
    section_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), palette["off_white"]),
                ("TEXTCOLOR", (0, 0), (-1, 0), palette["navy"]),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, palette["light_border"]),
                ("BOX", (0, 0), (-1, -1), 0.8, palette["light_border"]),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, palette["light_border"]),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(section_table)
    story.append(PageBreak())

    story.append(Paragraph("Remediation Plan", styles["SectionHeading"]))
    story.append(Spacer(1, 8))
    if not normalized_actions:
        story.append(
            Paragraph(
                "No critical gaps were identified for this assessment.",
                styles["BodyStyle"],
            )
        )
    else:
        for gap_number, gap in enumerate(normalized_actions, start=1):
            priority_style = (
                styles["PriorityHigh"]
                if gap["priority"] == "HIGH"
                else styles["PriorityMedium"]
            )
            actions_list = ListFlowable(
                [ListItem(Paragraph(action, styles["BodyStyle"])) for action in gap["actions"]],
                bulletType="bullet",
                start="☐",
            )
            evidence_list = ListFlowable(
                [
                    ListItem(Paragraph(evidence, styles["BodyStyle"]))
                    for evidence in gap["evidence"]
                ],
                bulletType="bullet",
            )

            card_content = [
                Paragraph(f"Gap {gap_number}", styles["MutedStyle"]),
                Paragraph(gap["title"], styles["CardTitle"]),
                Spacer(1, 6),
                Paragraph("Risk", styles["LabelStyle"]),
                Paragraph(gap["risk"], styles["BodyStyle"]),
                Spacer(1, 4),
                Paragraph("Recommended Actions", styles["LabelStyle"]),
                actions_list,
                Spacer(1, 4),
                Paragraph("Evidence Required", styles["LabelStyle"]),
                evidence_list,
            ]
            compliance_relevance = str(gap.get("compliance_relevance") or "").strip()
            if compliance_relevance:
                card_content.extend(
                    [
                        Spacer(1, 4),
                        Paragraph("Compliance Relevance", styles["LabelStyle"]),
                        Paragraph(compliance_relevance, styles["BodyStyle"]),
                    ]
                )

            card = Table(
                [[Paragraph(gap["priority"], priority_style)], [card_content]],
                colWidths=[168 * mm],
            )
            card.setStyle(
                TableStyle(
                    [
                        (
                            "BACKGROUND",
                            (0, 0),
                            (-1, 0),
                            palette["high"] if gap["priority"] == "HIGH" else palette["medium"],
                        ),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("BACKGROUND", (0, 1), (-1, 1), palette["off_white"]),
                        ("BOX", (0, 0), (-1, -1), 0.8, palette["light_border"]),
                        ("LEFTPADDING", (0, 0), (-1, -1), 10),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                        ("TOPPADDING", (0, 0), (-1, -1), 7),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(card)
            story.append(Spacer(1, 12))

    story.append(PageBreak())
    story.append(
        Paragraph(
            "Appendix A: Evidence Checklist for Audit Readiness",
            styles["SectionHeading"],
        )
    )
    story.append(Spacer(1, 8))
    appendix_rows: list[list[Any]] = [["Gap", "Priority", "Evidence Required", "Status"]]
    for idx, gap in enumerate(normalized_actions, start=1):
        evidence_lines = "<br/>".join(f"• {item}" for item in gap["evidence"])
        status_lines = "<br/>".join(
            [
                "&#9633; Available",
                "&#9633; In progress",
                "&#9633; Not available",
            ]
        )
        appendix_rows.append(
            [
                Paragraph(f"Gap {idx}: {gap['title']}", styles["BodyStyle"]),
                Paragraph(gap["priority"], styles["BodyStyle"]),
                Paragraph(evidence_lines, styles["BodyStyle"]),
                Paragraph(status_lines, styles["BodyStyle"]),
            ]
        )

    appendix = Table(appendix_rows, colWidths=[40 * mm, 22 * mm, 64 * mm, 42 * mm])
    appendix.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), palette["off_white"]),
                ("TEXTCOLOR", (0, 0), (-1, 0), palette["navy"]),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOX", (0, 0), (-1, -1), 0.8, palette["light_border"]),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, palette["light_border"]),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(appendix)

    def _cover_page(canvas_obj: Any, doc: Any) -> None:
        _draw_page_chrome(
            canvas_obj,
            doc,
            organisation_name=organisation_name,
            generated_on=generated_on,
            show_header=False,
            palette=palette,
            page_size=A4,
        )

    def _content_page(canvas_obj: Any, doc: Any) -> None:
        _draw_page_chrome(
            canvas_obj,
            doc,
            organisation_name=organisation_name,
            generated_on=generated_on,
            show_header=True,
            palette=palette,
            page_size=A4,
        )

    document.build(story, onFirstPage=_cover_page, onLaterPages=_content_page)
    return buffer.getvalue()


def _build_pdf_styles(
    palette: dict[str, Any], sample_styles: Any, paragraph_style: Any, colors_mod: Any
) -> dict[str, Any]:
    base = sample_styles["BodyText"]
    return {
        "CoverTitle": paragraph_style(
            "CoverTitle",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=30,
            textColor=palette["navy"],
            spaceAfter=2,
        ),
        "CoverSubtitle": paragraph_style(
            "CoverSubtitle",
            parent=base,
            fontName="Helvetica",
            fontSize=13,
            leading=17,
            textColor=palette["teal"],
        ),
        "SectionHeading": paragraph_style(
            "SectionHeading",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            textColor=palette["navy"],
        ),
        "CardTitle": paragraph_style(
            "CardTitle",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=12.5,
            leading=16,
            textColor=palette["navy"],
            spaceAfter=2,
        ),
        "LabelStyle": paragraph_style(
            "LabelStyle",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=palette["navy"],
        ),
        "BodyStyle": paragraph_style(
            "BodyStyle",
            parent=base,
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=palette["body"],
        ),
        "MutedStyle": paragraph_style(
            "MutedStyle",
            parent=base,
            fontName="Helvetica",
            fontSize=9.7,
            leading=13,
            textColor=palette["muted"],
        ),
        "PriorityHigh": paragraph_style(
            "PriorityHigh",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=12,
            textColor=colors_mod.white,
        ),
        "PriorityMedium": paragraph_style(
            "PriorityMedium",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=12,
            textColor=colors_mod.white,
        ),
        "FooterStyle": paragraph_style(
            "FooterStyle",
            parent=base,
            fontName="Helvetica",
            fontSize=9.5,
            leading=12,
            textColor=palette["muted"],
            alignment=1,
        ),
        "CoverMetric": paragraph_style(
            "CoverMetric",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=17,
            textColor=palette["navy"],
        ),
        "CardMetric": paragraph_style(
            "CardMetric",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=palette["navy"],
        ),
    }


def _normalize_recommendations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_actions: list[dict[str, Any]] = []
    for item in items:
        issue = str(
            item.get("title")
            or item.get("issue")
            or item.get("question")
            or "Control gap identified"
        )
        risk = str(item.get("risk") or item.get("risk_level") or "Risk not specified")
        actions = item.get("actions")
        if not isinstance(actions, list) or not actions:
            fallback = str(item.get("action") or item.get("recommendation") or "").strip()
            actions = (
                [fallback]
                if fallback
                else ["Review this control and define a remediation plan."]
            )
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            evidence = ["Documented remediation plan and implementation evidence."]
        priority = str(item.get("priority") or item.get("severity") or "MEDIUM").upper()
        normalized_actions.append(
            {
                "title": issue,
                "risk": risk,
                "priority": priority if priority in {"HIGH", "MEDIUM"} else "MEDIUM",
                "actions": [str(action).strip() for action in actions if str(action).strip()],
                "evidence": [str(entry).strip() for entry in evidence if str(entry).strip()],
                "compliance_relevance": _compliance_relevance(item),
            }
        )
    return normalized_actions


def _compliance_relevance(item: dict[str, Any]) -> str:
    explicit = item.get("compliance_relevance") or item.get("complianceRelevance")
    if explicit:
        return str(explicit).strip()
    legal_context = item.get("legal_context") or item.get("legalContext")
    if legal_context:
        return str(legal_context).strip()
    return ""


def _section_highlights(sections: list[dict[str, Any]]) -> tuple[str, str]:
    if not sections:
        return ("No section data available", "No section data available")
    scored = [
        (str(section.get("name", "Section")), float(section.get("score", 0)))
        for section in sections
    ]
    strongest_name, strongest_score = max(scored, key=lambda item: item[1])
    weakest_name, weakest_score = min(scored, key=lambda item: item[1])
    return (
        f"{strongest_name} ({strongest_score:.1f}%)",
        f"{weakest_name} ({weakest_score:.1f}%)",
    )


def _score_status(score: float) -> str:
    if score < 40:
        return "Critical"
    if score < 60:
        return "Needs Improvement"
    if score < 80:
        return "Moderate"
    return "Strong"


def _score_bar(score: float) -> str:
    filled = max(0, min(10, round(score / 10)))
    return "■" * filled + "□" * (10 - filled)


def _draw_page_chrome(
    canvas_obj: Any,
    doc: Any,
    *,
    organisation_name: str,
    generated_on: str,
    show_header: bool,
    palette: dict[str, Any],
    page_size: tuple[float, float],
) -> None:
    canvas_obj.saveState()
    page_width, page_height = page_size

    if show_header:
        canvas_obj.setFont("Helvetica", 9)
        canvas_obj.setFillColor(palette["muted"])
        canvas_obj.drawString(
            doc.leftMargin,
            page_height - 24,
            f"Data Protection Compliance Assessment | {organisation_name}",
        )
        canvas_obj.setStrokeColor(palette["light_border"])
        canvas_obj.setLineWidth(0.4)
        canvas_obj.line(
            doc.leftMargin,
            page_height - 28,
            page_width - doc.rightMargin,
            page_height - 28,
        )

    canvas_obj.setFont("Helvetica", 8.7)
    canvas_obj.setFillColor(palette["muted"])
    footer = f"Confidential | Generated on {generated_on} | Page {doc.page}"
    canvas_obj.drawString(doc.leftMargin, 18, footer)
    canvas_obj.restoreState()


def map_maturity_level(score: float) -> str:
    if score <= 40:
        return "Basic"
    if score <= 60:
        return "Developing"
    if score <= 80:
        return "Defined"
    return "Managed"
