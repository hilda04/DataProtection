from __future__ import annotations

import re
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
        KeepTogether,
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
        "slate": colors.HexColor("#334E68"),
        "green": colors.HexColor("#2E7D32"),
        "amber": colors.HexColor("#F9A825"),
        "orange": colors.HexColor("#EF6C00"),
        "red": colors.HexColor("#C62828"),
        "off_white": colors.HexColor("#F5F8FC"),
        "row_alt": colors.HexColor("#FAFCFE"),
        "light_border": colors.HexColor("#D9E2EC"),
        "body": colors.HexColor("#243B53"),
        "muted": colors.HexColor("#5C6B7A"),
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

    score_box = _value_pill(f"{score:.2f}%", _score_band_fill(score, palette), styles)
    maturity_pill = _value_pill(maturity, _maturity_band_fill(maturity, palette), styles)
    cover_score = Table(
        [
            [
                Paragraph("Overall Score", styles["LabelStyle"]),
                score_box,
            ],
            [
                Paragraph("Maturity Level", styles["LabelStyle"]),
                maturity_pill,
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
                ("LINEBEFORE", (1, 0), (1, -1), 0.8, palette["light_border"]),
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

    story.append(Paragraph("01  Executive Summary", styles["SectionHeading"]))
    story.append(Paragraph("Assessment Overview", styles["SectionSubheading"]))
    story.append(Spacer(1, 10))
    metric_values = [
        ["Overall Score", _value_pill(f"{score:.2f}%", _score_band_fill(score, palette), styles)],
        ["Maturity Level", _value_pill(maturity, _maturity_band_fill(maturity, palette), styles)],
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
    metric_table = Table([metric_cards], colWidths=[56 * mm, 56 * mm, 56 * mm])
    metric_table.setStyle(
        TableStyle([("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 2)])
    )
    story.append(metric_table)

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
    story.append(Spacer(1, 8))
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

    story.append(Paragraph("02  Section Performance", styles["SectionHeading"]))
    story.append(Paragraph("Control Domain Breakdown", styles["SectionSubheading"]))
    story.append(Spacer(1, 10))
    section_rows = [["Section", "Score", "Status"]]
    score_backgrounds: list[tuple[int, Any]] = []
    status_backgrounds: list[tuple[int, Any]] = []
    for section in sections:
        section_score = float(section.get("score", 0))
        section_status = _score_status(section_score)
        score_fill = _score_band_fill(section_score, palette)
        status_fill = _maturity_band_fill(section_status, palette)
        row_index = len(section_rows)
        score_backgrounds.append((row_index, score_fill))
        status_backgrounds.append((row_index, status_fill))
        section_rows.append(
            [
                Paragraph(str(section.get("name", "Section")), styles["BodyStyle"]),
                Paragraph(f"{section_score:.2f}%", styles["BodyStyle"]),
                Paragraph(f"<b>{section_status}</b>", styles["BodyStyleCentered"]),
            ]
        )

    section_table = Table(
        section_rows,
        colWidths=[100 * mm, 28 * mm, 40 * mm],
        rowHeights=9 * mm,
    )
    alternating_rows = [
        ("BACKGROUND", (0, row), (-1, row), palette["row_alt"])
        for row in range(1, len(section_rows), 2)
    ]
    section_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), palette["off_white"]),
                ("BACKGROUND", (0, 0), (-1, 0), palette["navy"]),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, palette["light_border"]),
                ("BOX", (0, 0), (-1, -1), 0.8, palette["light_border"]),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, palette["light_border"]),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                ("ALIGN", (1, 0), (2, -1), "CENTER"),
                *alternating_rows,
            ]
            + [
                ("BACKGROUND", (1, row), (1, row), color)
                for row, color in score_backgrounds
            ]
            + [
                ("BACKGROUND", (2, row), (2, row), color)
                for row, color in status_backgrounds
            ]
        )
    )
    story.append(section_table)
    story.append(PageBreak())

    story.append(Paragraph("03  Remediation Plan", styles["SectionHeading"]))
    story.append(Paragraph("Prioritised Corrective Actions", styles["SectionSubheading"]))
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
            priority_color = _priority_color(gap["priority"], palette)
            actions_list = ListFlowable(
                [ListItem(Paragraph(action, styles["BodyStyle"])) for action in gap["actions"]],
                bulletType="bullet",
                leftIndent=12,
                bulletFontSize=8,
            )
            evidence_list = ListFlowable(
                [
                    ListItem(Paragraph(evidence, styles["BodyStyle"]))
                    for evidence in gap["evidence"]
                ],
                bulletType="bullet",
                leftIndent=12,
                bulletFontSize=8,
            )

            # Keep priority + gap heading + first risk block together.
            detail_block = [
                [Paragraph(_badge_html(gap["priority"], priority_color), styles["BadgeStyle"])],
                [Paragraph(f"Gap {gap_number}", styles["MutedStyle"])],
                [Paragraph(gap["title"], styles["CardTitle"])],
                [Paragraph("Risk", styles["LabelStyle"])],
                [Paragraph(gap["risk"], styles["BodyStyle"])],
                [Paragraph("Recommended Actions", styles["LabelStyle"])],
                [actions_list],
                [Paragraph("Evidence Required", styles["LabelStyle"])],
                [evidence_list],
            ]
            card = Table(detail_block, colWidths=[168 * mm], splitByRow=0)
            card.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), palette["off_white"]),
                        ("BOX", (0, 0), (-1, -1), 0.8, palette["light_border"]),
                        ("LINEBEFORE", (0, 0), (0, -1), 2.2, priority_color),
                        ("LEFTPADDING", (0, 0), (-1, -1), 10),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 2), (0, 2), 1),
                        ("BOTTOMPADDING", (0, 2), (0, 2), 4),
                        ("TOPPADDING", (0, 3), (0, 3), 3),
                        ("TOPPADDING", (0, 5), (0, 5), 5),
                        ("TOPPADDING", (0, 7), (0, 7), 5),
                    ]
                )
            )
            # Keep each gap as one cohesive block for cleaner pagination.
            story.append(KeepTogether([card]))
            story.append(Spacer(1, 12))

    if normalized_actions:
        story.append(PageBreak())
        story.append(
            Paragraph(
                "Appendix A: Evidence Checklist for Audit Readiness",
                styles["SectionHeading"],
            )
        )
        story.append(Paragraph("Documentary Evidence Tracker", styles["SectionSubheading"]))
        story.append(Spacer(1, 8))
        appendix_rows: list[list[Any]] = [["Gap", "Priority", "Evidence Required", "Status"]]
        for idx, gap in enumerate(normalized_actions, start=1):
            evidence_lines = "<br/>".join(f"• {item}" for item in gap["evidence"])
            status_lines = "<br/>".join(
                [
                    "☐ Available",
                    "☐ In progress",
                    "☐ Not available",
                ]
            )
            appendix_rows.append(
                [
                    Paragraph(f"Gap {idx}: {gap['title']}", styles["BodyStyle"]),
                    Paragraph(
                        _value_pill(
                            gap["priority"],
                            _priority_fill(gap["priority"], palette),
                            styles,
                        ),
                        styles["BodyStyleCentered"],
                    ),
                    Paragraph(evidence_lines, styles["BodyStyle"]),
                    Paragraph(status_lines, styles["ChecklistStyle"]),
                ]
            )

        appendix = Table(
            appendix_rows, colWidths=[52 * mm, 24 * mm, 57 * mm, 35 * mm], repeatRows=1
        )
        appendix.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), palette["navy"]),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BOX", (0, 0), (-1, -1), 0.8, palette["light_border"]),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, palette["light_border"]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (1, 1), (1, -1), "CENTER"),
                    ("ALIGN", (3, 1), (3, -1), "LEFT"),
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
        "SectionSubheading": paragraph_style(
            "SectionSubheading",
            parent=base,
            fontName="Helvetica",
            fontSize=10,
            leading=13,
            textColor=palette["slate"],
            spaceAfter=1,
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
        "BodyStyleCentered": paragraph_style(
            "BodyStyleCentered",
            parent=base,
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=palette["body"],
            alignment=1,
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
        "BadgeStyle": paragraph_style(
            "BadgeStyle",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=12,
            textColor=palette["body"],
            alignment=1,
        ),
        "ScoreBoxStyle": paragraph_style(
            "ScoreBoxStyle",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=palette["body"],
        ),
        "ChecklistStyle": paragraph_style(
            "ChecklistStyle",
            parent=base,
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=palette["body"],
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
        issue = _sanitize_visible_text(issue)
        risk = _sanitize_visible_text(
            str(item.get("risk") or item.get("risk_level") or "Risk not specified")
        )
        actions = item.get("actions")
        if not isinstance(actions, list) or not actions:
            fallback = str(item.get("action") or item.get("recommendation") or "").strip()
            actions = (
                [_sanitize_visible_text(fallback)]
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
                "priority": priority if priority in {"HIGH", "MEDIUM", "LOW"} else "MEDIUM",
                "actions": [
                    _sanitize_visible_text(str(action).strip())
                    for action in actions
                    if _sanitize_visible_text(str(action).strip())
                ],
                "evidence": [
                    _sanitize_visible_text(str(entry).strip())
                    for entry in evidence
                    if _sanitize_visible_text(str(entry).strip())
                ],
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


def _sanitize_visible_text(value: str) -> str:
    # Remove internal IDs, normalize spacing, and patch common sentence fragments.
    cleaned = re.sub(r"\b[a-z0-9]+(?:-[a-z0-9]+)*-q\d+\b", "", value, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    replacements = {
        r"\bmapped to and section\b": "mapped to this control and its respective section",
        r"tracking for \.": "tracking for this control.",
        r"\bFor\s*,\s*this control\b": "This control",
        r"\bFor\s*,": "This control",
    }
    for pattern, replacement in replacements.items():
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    return cleaned


def _score_band_fill(score: float, palette: dict[str, Any]) -> Any:
    if score >= 80:
        return colors_whiter(palette["green"])
    if score >= 60:
        return colors_whiter(palette["teal"])
    if score >= 40:
        return colors_whiter(palette["amber"])
    if score >= 20:
        return colors_whiter(palette["orange"])
    return colors_whiter(palette["red"])


def _maturity_band_fill(maturity: str, palette: dict[str, Any]) -> Any:
    label = maturity.strip().lower()
    if label in {"advanced", "strong"}:
        return colors_whiter(palette["green"])
    if label in {"managed", "established", "defined"}:
        return colors_whiter(palette["teal"])
    if label in {"developing", "needs improvement"}:
        return colors_whiter(palette["amber"])
    if label in {"weak", "initial", "basic", "critical", "poor"}:
        return colors_whiter(palette["red"])
    return colors_whiter(palette["teal"])


def _priority_color(priority: str, palette: dict[str, Any]) -> Any:
    if priority == "HIGH":
        return palette["red"]
    if priority == "MEDIUM":
        return palette["amber"]
    return palette["teal"]


def _priority_fill(priority: str, palette: dict[str, Any]) -> Any:
    return colors_whiter(_priority_color(priority, palette))


def _color_hex(color: Any) -> str:
    return getattr(color, "hexval", lambda: "#12344D")().replace("0x", "#")


def _badge_html(label: str, color: Any) -> str:
    return f"<font color='#243B53' backColor='{_color_hex(color)}'>  {label}  </font>"


def _value_pill(label: str, fill_color: Any, styles: dict[str, Any]) -> str:
    safe_label = _sanitize_visible_text(str(label))
    return (
        f"<font color='#243B53' backColor='{_color_hex(fill_color)}'>"
        f"&nbsp;&nbsp;<b>{safe_label}</b>&nbsp;&nbsp;"
        "</font>"
    )


def colors_whiter(color: Any) -> Any:
    from reportlab.lib import colors

    return colors.Whiter(color, 0.82)


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
