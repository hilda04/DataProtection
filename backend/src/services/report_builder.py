from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO
from typing import Any

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


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


def map_maturity_level(score: float) -> str:
    if score <= 40:
        return "Basic"
    if score <= 60:
        return "Developing"
    if score <= 80:
        return "Defined"
    return "Managed"


# ---------------------------------------------------------------------------
# PDF builder
# ---------------------------------------------------------------------------


def build_assessment_report_pdf(report: dict[str, Any]) -> bytes:
    from reportlab import rl_config
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        HRFlowable,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    rl_config.pageCompression = 0

    P = _palette(colors)
    styles = _build_styles(P, getSampleStyleSheet(), ParagraphStyle, colors)

    organisation = report.get("organisation", {}) or {}
    framework = report.get("framework", {}) or {}
    score = float(report.get("score") or 0.0)
    maturity = str(report.get("maturity_level") or map_maturity_level(score))
    sections = report.get("sections") or []
    raw_actions = report.get("recommendedActions") or report.get("recommendations") or []
    summary = str(report.get("summary") or "").strip()
    completed_at = report.get("completed_at", datetime.utcnow().isoformat() + "Z")
    completion_date = str(completed_at).split("T", 1)[0]
    generated_on = datetime.utcnow().strftime("%d %B %Y")
    org_name = str(organisation.get("name") or "N/A")
    fw_name = str(framework.get("name") or "N/A")
    fw_version = str(framework.get("version") or "N/A")

    actions = _normalize_recommendations(raw_actions)
    high_medium = [a for a in actions if a["priority"] in {"HIGH", "MEDIUM"}]
    top_actions = (high_medium or actions)[:5]

    buffer = BytesIO()
    page_w, _ = A4
    mx = 18 * mm
    my = 22 * mm
    cw = page_w - 2 * mx

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=mx,
        rightMargin=mx,
        topMargin=my,
        bottomMargin=my,
        title=f"{fw_name} Assessment Report - {org_name}",
    )

    story: list[Any] = []

    # ----------------------------------------------------------------------
    # COVER PAGE
    # ----------------------------------------------------------------------
    story.append(Spacer(1, 6 * mm))

    fw_pill = _build_pill(
        f"{fw_name.upper()}  v{fw_version}",
        P["accent"],
        styles,
        width_mm=42,
        text_color=P["white"],
    )
    story.append(fw_pill)
    story.append(Spacer(1, 8 * mm))

    story.append(Paragraph("Compliance Assessment", styles["CoverEyebrow"]))
    story.append(Paragraph("Report", styles["CoverTitle"]))
    story.append(
        HRFlowable(
            width=cw * 0.13,
            thickness=3.5,
            color=P["accent"],
            spaceAfter=0,
            spaceBefore=5,
        )
    )
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(org_name, styles["CoverOrg"]))
    story.append(Paragraph(f"Assessment Date: {completion_date}", styles["CoverMeta"]))
    story.append(Spacer(1, 13 * mm))

    hero_data = [
        ("Overall Score", f"{score:.1f}%", _score_band_color(score, P)),
        ("Maturity Level", maturity, _maturity_band_color(maturity, P)),
        ("Priority Gaps", str(len(high_medium)), P["slate"]),
    ]
    hero_cells = [
        _hero_stat(label, value, color, styles, P, colors, cw / 3)
        for label, value, color in hero_data
    ]
    hero = Table([hero_cells], colWidths=[cw / 3] * 3)
    hero.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(hero)
    story.append(Spacer(1, 10 * mm))

    summary_text = summary or (
        f"This assessment evaluates {org_name}'s control posture against {fw_name}. "
        f"The organisation has achieved a <b>{maturity.lower()}</b> maturity level. "
        "Prioritised remediation actions and audit evidence "
        "requirements are detailed in this report."
    )
    story.append(_callout(summary_text, styles["CoverSummary"], P, colors, cw))
    story.append(Spacer(1, 20 * mm))
    story.append(Paragraph("Confidential - Not for external distribution", styles["CoverFootnote"]))
    story.append(
        Paragraph(f"Generated by DataProtection App  |  {generated_on}", styles["CoverFootnote"])
    )
    story.append(PageBreak())

    # ----------------------------------------------------------------------
    # 01 - EXECUTIVE SUMMARY
    # ----------------------------------------------------------------------
    story.extend(_section_header("01", "Executive Summary", P, styles, cw))
    story.append(Spacer(1, 3 * mm))

    kpi_data = [
        ("Overall Score", f"{score:.1f}%", _score_band_color(score, P)),
        ("Maturity Level", maturity, _maturity_band_color(maturity, P)),
        ("Priority Gaps", str(len(high_medium)), P["red"]),
        ("Sections Assessed", str(len(sections)), P["slate"]),
    ]
    kpi_cells = [
        _kpi_card(label, value, color, styles, P, colors, cw / 4)
        for label, value, color in kpi_data
    ]
    kpi_row = Table([kpi_cells], colWidths=[cw / 4] * 4)
    kpi_row.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(kpi_row)
    story.append(Spacer(1, 5 * mm))

    strongest, weakest = _section_highlights(sections)
    insight = (
        f"<b>Strongest area:</b> {strongest}. "
        f"<b>Primary weakness:</b> {weakest}. "
        "Immediate remediation focus should address high-risk control gaps to "
        "reduce regulatory exposure and strengthen evidence of control operation."
    )
    story.append(_callout(insight, styles["Body"], P, colors, cw, accent_bar=True))
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("Top Immediate Actions", styles["SubHeading"]))
    story.append(Spacer(1, 2 * mm))

    if top_actions:
        action_rows: list[list[Any]] = []
        for i, act in enumerate(top_actions, 1):
            label = act["actions"][0] if act["actions"] else act["title"]
            priority = act["priority"]
            pc = _priority_color(priority, P)
            action_rows.append(
                [
                    Paragraph(f"<b>{i}</b>", styles["ActionNum"]),
                    _build_pill(priority, _whiter(pc, colors, 0.86), styles, width_mm=20),
                    Paragraph(_sanitize(label), styles["Body"]),
                ]
            )

        act_bgs = [
            ("BACKGROUND", (0, r), (-1, r), P["surface"] if r % 2 == 0 else P["row_alt"])
            for r in range(len(action_rows))
        ]
        act_table = Table(
            action_rows,
            colWidths=[10 * mm, 26 * mm, cw - 36 * mm],
        )
        act_table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.6, P["border"]),
                    ("LINEBELOW", (0, 0), (-1, -2), 0.35, P["border"]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (0, -1), "CENTER"),
                    ("ALIGN", (1, 0), (1, -1), "CENTER"),
                    *act_bgs,
                ]
            )
        )
        story.append(act_table)
    else:
        story.append(
            Paragraph(
                "No immediate remediation actions were generated from this assessment.",
                styles["Body"],
            )
        )

    story.append(PageBreak())

    # ----------------------------------------------------------------------
    # 02 - SECTION PERFORMANCE
    # ----------------------------------------------------------------------
    story.extend(_section_header("02", "Section Performance", P, styles, cw))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Control Domain Breakdown", styles["SubHeading"]))
    story.append(Spacer(1, 2 * mm))

    sec_rows: list[list[Any]] = [
        [
            Paragraph("Control Domain", styles["TH"]),
            Paragraph("Score", styles["THC"]),
            Paragraph("Status", styles["THC"]),
        ]
    ]

    for section in sections:
        s_score = float(section.get("score", 0))
        s_status = _score_status(s_score)
        sec_rows.append(
            [
                Paragraph(str(section.get("name", "-")), styles["Body"]),
                _build_pill(
                    f"{s_score:.1f}%",
                    _whiter(_score_band_color(s_score, P), colors, 0.82),
                    styles,
                    width_mm=22,
                ),
                _build_pill(
                    s_status,
                    _whiter(_maturity_band_color(s_status, P), colors, 0.78),
                    styles,
                    width_mm=30,
                ),
            ]
        )

    if len(sec_rows) == 1:
        sec_rows.append(
            [
                Paragraph("No section data available", styles["Body"]),
                Paragraph("N/A", styles["BodyCenter"]),
                Paragraph("N/A", styles["BodyCenter"]),
            ]
        )

    alt_rows = [("BACKGROUND", (0, r), (-1, r), P["row_alt"]) for r in range(2, len(sec_rows), 2)]

    sec_table = Table(
        sec_rows,
        colWidths=[cw * 0.52, cw * 0.18, cw * 0.30],
        repeatRows=1,
    )
    sec_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), P["navy"]),
                ("TEXTCOLOR", (0, 0), (-1, 0), P["white"]),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOX", (0, 0), (-1, -1), 0.7, P["border"]),
                ("LINEBELOW", (0, 0), (-1, 0), 0.7, P["border"]),
                ("LINEBELOW", (0, 1), (-1, -2), 0.35, P["border"]),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (2, -1), "CENTER"),
                *alt_rows,
            ]
        )
    )
    story.append(sec_table)

    story.append(Spacer(1, 3 * mm))
    legend_data = [
        ("Strong  >= 80%", P["green"]),
        ("Moderate  60-79%", P["gold"]),
        ("Needs Impr.  40-59%", P["amber"]),
        ("Critical  < 40%", P["red"]),
    ]
    legend_cells = []
    for lbl, lc in legend_data:
        swatch = Table([[""]], colWidths=[3 * mm], rowHeights=[3 * mm])
        swatch.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), _whiter(lc, colors, 0.65))]))
        cell = Table(
            [[swatch, Paragraph(lbl, styles["Legend"])]],
            colWidths=[4 * mm, 36 * mm],
        )
        cell.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        legend_cells.append(cell)

    legend_row = Table([legend_cells], colWidths=[40 * mm] * 4)
    legend_row.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(legend_row)
    story.append(PageBreak())

    # ----------------------------------------------------------------------
    # 03 - REMEDIATION PLAN
    # ----------------------------------------------------------------------
    story.extend(_section_header("03", "Remediation Plan", P, styles, cw))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Prioritised Corrective Actions", styles["SubHeading"]))
    story.append(Spacer(1, 3 * mm))

    if not actions:
        story.append(
            _callout(
                "No critical gaps were identified for this assessment. "
                "The organisation should still retain "
                "evidence supporting the controls assessed and maintain ongoing monitoring.",
                styles["Body"],
                P,
                colors,
                cw,
                accent_bar=True,
            )
        )
    else:
        for idx, gap in enumerate(actions, 1):
            story.append(_gap_card(idx, gap, styles, P, colors, cw))
            story.append(Spacer(1, 4 * mm))

    # ----------------------------------------------------------------------
    # APPENDIX A - EVIDENCE CHECKLIST
    # ----------------------------------------------------------------------
    story.append(PageBreak())
    story.extend(_section_header("A", "Evidence Checklist", P, styles, cw, appendix=True))
    story.append(Spacer(1, 1 * mm))
    story.append(
        Paragraph("Documentary Evidence Tracker for Audit Readiness", styles["SubHeading"])
    )
    story.append(Spacer(1, 3 * mm))

    if not actions:
        story.append(
            _callout(
                "No remediation-specific evidence items were generated from this assessment. "
                "This appendix may still be used to track supporting "
                "governance, policy, procedure, "
                "approval, and operational evidence.",
                styles["Body"],
                P,
                colors,
                cw,
                accent_bar=True,
            )
        )
    else:
        app_rows: list[list[Any]] = [
            [
                Paragraph("Gap", styles["TH"]),
                Paragraph("Priority", styles["THC"]),
                Paragraph("Evidence Required", styles["TH"]),
                Paragraph("Status", styles["THC"]),
            ]
        ]
        for i, gap in enumerate(actions, 1):
            ev_text = "<br/>".join(f"• {_sanitize(e)}" for e in gap["evidence"])
            app_rows.append(
                [
                    Paragraph(
                        f"<b>Gap {i}</b><br/><font size='8' "
                        f"color='{_hex(P['muted'])}'>{_sanitize(gap['title'])}</font>",
                        styles["Body"],
                    ),
                    _build_pill(
                        gap["priority"],
                        _whiter(_priority_color(gap["priority"], P), colors, 0.86),
                        styles,
                        width_mm=20,
                    ),
                    Paragraph(ev_text, styles["Small"]),
                    Paragraph("☐ Available<br/>☐ In progress<br/>☐ Not available", styles["Small"]),
                ]
            )

        app_alt = [
            ("BACKGROUND", (0, r), (-1, r), P["row_alt"]) for r in range(2, len(app_rows), 2)
        ]
        app_table = Table(
            app_rows,
            colWidths=[cw * 0.28, cw * 0.12, cw * 0.38, cw * 0.22],
            repeatRows=1,
        )
        app_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), P["navy"]),
                    ("TEXTCOLOR", (0, 0), (-1, 0), P["white"]),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BOX", (0, 0), (-1, -1), 0.7, P["border"]),
                    ("LINEBELOW", (0, 0), (-1, -2), 0.35, P["border"]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (1, 0), (1, -1), "CENTER"),
                    ("ALIGN", (3, 0), (3, -1), "LEFT"),
                    *app_alt,
                ]
            )
        )
        story.append(app_table)

    def _on_cover(cv: Any, d: Any) -> None:
        _draw_chrome(
            cv,
            d,
            org_name=org_name,
            date=generated_on,
            fw=fw_name,
            is_cover=True,
            P=P,
            page_size=A4,
        )

    def _on_page(cv: Any, d: Any) -> None:
        _draw_chrome(
            cv,
            d,
            org_name=org_name,
            date=generated_on,
            fw=fw_name,
            is_cover=False,
            P=P,
            page_size=A4,
        )

    doc.build(story, onFirstPage=_on_cover, onLaterPages=_on_page)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------


def _palette(colors: Any) -> dict[str, Any]:
    return {
        "navy": colors.HexColor("#0D1F3C"),
        "slate": colors.HexColor("#2D4A6E"),
        "accent": colors.HexColor("#2563EB"),
        "green": colors.HexColor("#16A34A"),
        "gold": colors.HexColor("#CA8A04"),
        "amber": colors.HexColor("#D97706"),
        "orange": colors.HexColor("#EA580C"),
        "red": colors.HexColor("#DC2626"),
        "surface": colors.HexColor("#FFFFFF"),
        "row_alt": colors.HexColor("#F5F8FC"),
        "border": colors.HexColor("#CBD5E1"),
        "ink_1": colors.HexColor("#F0F4F9"),
        "body": colors.HexColor("#1E293B"),
        "muted": colors.HexColor("#64748B"),
        "white": colors.white,
    }


def _build_styles(P: dict, base: Any, PS: Any, colors: Any) -> dict[str, Any]:
    B = base["BodyText"]

    def s(name: str, **kw: Any) -> Any:
        return PS(name, parent=B, **kw)

    return {
        "Pill": s(
            "Pill",
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10,
            textColor=P["body"],
            alignment=1,
        ),
        "CoverEyebrow": s(
            "CovEye", fontName="Helvetica", fontSize=11, leading=14, textColor=P["muted"]
        ),
        "CoverTitle": s(
            "CovTit", fontName="Helvetica-Bold", fontSize=44, leading=50, textColor=P["navy"]
        ),
        "CoverOrg": s(
            "CovOrg", fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=P["slate"]
        ),
        "CoverMeta": s(
            "CovMet", fontName="Helvetica", fontSize=9.5, leading=13, textColor=P["muted"]
        ),
        "CoverSummary": s(
            "CovSum", fontName="Helvetica", fontSize=10.5, leading=16, textColor=P["body"]
        ),
        "CoverFootnote": s(
            "CovFn",
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=P["muted"],
            alignment=1,
        ),
        "SectionTag": s(
            "SecTag", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=P["accent"]
        ),
        "SectionTitle": s(
            "SecTit", fontName="Helvetica-Bold", fontSize=20, leading=26, textColor=P["navy"]
        ),
        "SubHeading": s(
            "SubHd", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=P["slate"]
        ),
        "Body": s("Body", fontName="Helvetica", fontSize=9.5, leading=14, textColor=P["body"]),
        "BodyRight": s(
            "BodyR",
            fontName="Helvetica",
            fontSize=9.5,
            leading=14,
            textColor=P["body"],
            alignment=2,
        ),
        "BodyCenter": s(
            "BodyC",
            fontName="Helvetica",
            fontSize=9.5,
            leading=14,
            textColor=P["body"],
            alignment=1,
        ),
        "Small": s("Small", fontName="Helvetica", fontSize=8.5, leading=12, textColor=P["body"]),
        "Muted": s("Muted", fontName="Helvetica", fontSize=9, leading=13, textColor=P["muted"]),
        "Legend": s("Leg", fontName="Helvetica", fontSize=8, leading=11, textColor=P["muted"]),
        "TH": s("TH", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=colors.white),
        "THC": s(
            "THC",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=colors.white,
            alignment=1,
        ),
        "GapNum": s(
            "GapN", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=P["muted"]
        ),
        "GapTitle": s(
            "GapT",
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=P["navy"],
            spaceAfter=2,
        ),
        "Label": s(
            "Lbl",
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=P["slate"],
            spaceBefore=3,
        ),
        "ActionNum": s(
            "ActN",
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=P["accent"],
            alignment=1,
        ),
        "StatValue": s(
            "StatV",
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=P["navy"],
            alignment=1,
        ),
        "StatLabel": s(
            "StatL",
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=P["muted"],
            alignment=1,
        ),
        "KpiValue": s(
            "KpiV",
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=P["navy"],
            alignment=1,
        ),
        "KpiLabel": s(
            "KpiL",
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=P["muted"],
            alignment=1,
        ),
    }


# ---------------------------------------------------------------------------
# Layout atoms
# ---------------------------------------------------------------------------


def _hex(color: Any) -> str:
    raw = getattr(color, "hexval", lambda: "#000000")()
    h = raw.replace("0x", "").replace("#", "").upper()
    return f"#{h}"


def _whiter(color: Any, colors: Any, factor: float = 0.80) -> Any:
    return colors.Whiter(color, factor)


def _build_pill(
    label: str,
    fill_color: Any,
    styles: dict[str, Any],
    width_mm: float = 28,
    text_color: Any | None = None,
) -> Any:
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table, TableStyle

    safe_label = _sanitize(str(label))
    fg = _hex(text_color) if text_color is not None else _hex(styles["Pill"].textColor)
    pill = Table(
        [[Paragraph(f"<font color='{fg}'><b>{safe_label}</b></font>", styles["Pill"])]],
        colWidths=[width_mm * mm],
    )
    pill.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), fill_color),
                ("BOX", (0, 0), (-1, -1), 0, fill_color),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return pill


def _hero_stat(
    label: str, value: str, color: Any, styles: dict, P: dict, colors: Any, col_w: float
) -> Any:
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle

    font_pt = min(26, max(13, int((col_w - 28) / (max(len(value), 1) * 0.62))))
    val_style = ParagraphStyle(
        f"_HeroV_{label}",
        parent=styles["StatValue"],
        fontSize=font_pt,
        leading=font_pt + 5,
    )

    inner = Table(
        [
            [Paragraph(value, val_style)],
            [Paragraph(label, styles["StatLabel"])],
        ],
        colWidths=[col_w - 8],
    )
    inner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _whiter(color, colors, 0.88)),
                ("LINEBEFORE", (0, 0), (0, -1), 3.5, color),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 11),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    wrap = Table([[inner]], colWidths=[col_w])
    wrap.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return wrap


def _kpi_card(
    label: str, value: str, color: Any, styles: dict, P: dict, colors: Any, col_w: float
) -> Any:
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle

    font_pt = min(20, max(11, int((col_w - 30) / (max(len(value), 1) * 0.62))))
    val_style = ParagraphStyle(
        f"_KpiV_{label}",
        parent=styles["KpiValue"],
        fontSize=font_pt,
        leading=font_pt + 4,
    )

    inner = Table(
        [
            [Paragraph(value, val_style)],
            [Paragraph(label, styles["KpiLabel"])],
        ],
        colWidths=[col_w - 8],
    )
    inner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _whiter(color, colors, 0.90)),
                ("LINEBEFORE", (0, 0), (0, -1), 3, color),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    wrap = Table([[inner]], colWidths=[col_w])
    wrap.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return wrap


def _callout(
    text: str,
    style: Any,
    P: dict,
    colors: Any,
    width: float,
    accent_bar: bool = False,
) -> Any:
    from reportlab.platypus import Paragraph, Table, TableStyle

    rules = [
        ("BACKGROUND", (0, 0), (-1, -1), P["ink_1"]),
        ("BOX", (0, 0), (-1, -1), 0.6, P["border"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 14 if accent_bar else 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]
    if accent_bar:
        rules.append(("LINEBEFORE", (0, 0), (0, -1), 3.5, P["accent"]))
    t = Table([[Paragraph(text, style)]], colWidths=[width])
    t.setStyle(TableStyle(rules))
    return t


def _section_header(
    num: str,
    title: str,
    P: dict,
    styles: dict,
    width: float,
    appendix: bool = False,
) -> list[Any]:
    from reportlab.platypus import HRFlowable, Paragraph

    prefix = f"APPENDIX {num}" if appendix else f"SECTION  {num}"
    return [
        Paragraph(prefix, styles["SectionTag"]),
        Paragraph(title, styles["SectionTitle"]),
        HRFlowable(width=width, thickness=0.5, color=P["border"], spaceAfter=2, spaceBefore=1),
    ]


def _gap_card(idx: int, gap: dict, styles: dict, P: dict, colors: Any, width: float) -> Any:
    from reportlab.platypus import ListFlowable, ListItem, Paragraph, Table, TableStyle

    priority = gap["priority"]
    pc = _priority_color(priority, P)
    hdr_fill = _whiter(pc, colors, 0.90)

    def _num_list(items: list[str]) -> ListFlowable:
        return ListFlowable(
            [ListItem(Paragraph(_sanitize(i), styles["Body"])) for i in items],
            bulletType="1",
            start="1",
            leftIndent=14,
            bulletFontSize=8,
        )

    def _bullet_list(items: list[str]) -> ListFlowable:
        return ListFlowable(
            [ListItem(Paragraph(_sanitize(i), styles["Body"])) for i in items],
            bulletType="bullet",
            leftIndent=12,
            bulletFontSize=8,
        )

    hdr = Table(
        [
            [
                Paragraph(f"GAP {idx:02d}", styles["GapNum"]),
                _build_pill(priority, _whiter(pc, colors, 0.86), styles, width_mm=24),
            ]
        ],
        colWidths=[width * 0.72, width * 0.28],
    )
    hdr.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), hdr_fill),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ]
        )
    )

    risk_box = Table([[Paragraph(_sanitize(gap["risk"]), styles["Body"])]], colWidths=[width - 24])
    risk_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), P["ink_1"]),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("BOX", (0, 0), (-1, -1), 0.5, P["border"]),
            ]
        )
    )

    evidence_box = Table([[_bullet_list(gap["evidence"])]], colWidths=[width - 24])
    evidence_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), P["row_alt"]),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("BOX", (0, 0), (-1, -1), 0.5, P["border"]),
            ]
        )
    )

    body = Table(
        [
            [Paragraph(gap["title"], styles["GapTitle"])],
            [Paragraph("Risk implication", styles["Label"])],
            [risk_box],
            [Paragraph("Recommended actions", styles["Label"])],
            [_num_list(gap["actions"])],
            [Paragraph("Required evidence", styles["Label"])],
            [evidence_box],
        ],
        colWidths=[width],
    )
    body.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), P["surface"]),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (0, 0), 10),
                ("BOTTOMPADDING", (0, 6), (0, 6), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    card = Table([[hdr], [body]], colWidths=[width])
    card.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.7, P["border"]),
                ("LINEBEFORE", (0, 0), (0, -1), 4, pc),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return card


# ---------------------------------------------------------------------------
# Canvas chrome
# ---------------------------------------------------------------------------


def _draw_chrome(
    c: Any,
    doc: Any,
    *,
    org_name: str,
    date: str,
    fw: str,
    is_cover: bool,
    P: dict,
    page_size: tuple,
) -> None:
    from reportlab.lib.units import mm

    c.saveState()
    w, h = page_size
    lm, rm = doc.leftMargin, doc.rightMargin

    if is_cover:
        c.setFillColor(P["navy"])
        c.rect(0, h - 16 * mm, w, 16 * mm, fill=1, stroke=0)

        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(P["border"])
        c.drawString(lm, h - 10 * mm, f"{fw.upper()}  |  COMPLIANCE ASSESSMENT REPORT")

        c.setFont("Helvetica", 8)
        c.setFillColor(P["muted"])
        c.drawRightString(w - rm, h - 10 * mm, date)

        c.setFillColor(P["accent"])
        c.rect(0, 11 * mm, 5 * mm, h - 16 * mm - 11 * mm, fill=1, stroke=0)

        c.setFillColor(P["navy"])
        c.rect(0, 0, w, 11 * mm, fill=1, stroke=0)

        c.setFont("Helvetica", 7.5)
        c.setFillColor(P["border"])
        c.drawString(
            lm + 7 * mm,
            4 * mm,
            f"Confidential  |  Generated {date}  |  DataProtection App",
        )
    else:
        c.setFillColor(P["navy"])
        c.rect(0, h - 11 * mm, w, 11 * mm, fill=1, stroke=0)

        c.setFillColor(P["accent"])
        c.rect(0, h - 11 * mm, 4 * mm, 11 * mm, fill=1, stroke=0)

        c.setFont("Helvetica", 7.5)
        c.setFillColor(P["border"])
        c.drawString(
            lm + 2 * mm,
            h - 7 * mm,
            f"{fw.upper()}  |  COMPLIANCE ASSESSMENT  |  {org_name}",
        )

        c.setFont("Helvetica-Bold", 8)
        c.drawRightString(w - rm, h - 7 * mm, f"Page {doc.page}")

        c.setStrokeColor(P["border"])
        c.setLineWidth(0.4)
        c.line(lm, 14 * mm, w - rm, 14 * mm)

        c.setFont("Helvetica", 7.5)
        c.setFillColor(P["muted"])
        c.drawString(lm, 9 * mm, f"Confidential  |  Generated {date}")
        c.drawRightString(w - rm, 9 * mm, "DataProtection App")

    c.restoreState()


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _normalize_recommendations(items: list[dict]) -> list[dict]:
    out: list[dict[str, Any]] = []
    for item in items:
        title = _sanitize(
            str(
                item.get("title")
                or item.get("issue")
                or item.get("question")
                or "Control gap identified"
            )
        )

        risk = _sanitize(
            str(
                item.get("risk")
                or item.get("risk_level")
                or (
                    "The absence or weakness of this control may reduce "
                    "the organisation’s ability to demonstrate compliance "
                    "and sustain effective risk management."
                )
            )
        )

        actions = item.get("actions")
        if not isinstance(actions, list) or not actions:
            fb = str(item.get("action") or item.get("recommendation") or "").strip()
            actions = (
                [_sanitize(fb)]
                if fb
                else [
                    "Define and document a corrective action plan, "
                    "assign ownership, and establish target completion "
                    "dates for this control gap."
                ]
            )

        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            evidence = [
                "Approved remediation plan, implementation records, and "
                "evidence demonstrating control operation."
            ]

        priority = str(item.get("priority") or item.get("severity") or "MEDIUM").upper()

        out.append(
            {
                "title": title,
                "risk": risk,
                "priority": priority if priority in {"HIGH", "MEDIUM", "LOW"} else "MEDIUM",
                "actions": [
                    _sanitize(str(a).strip()) for a in actions if _sanitize(str(a).strip())
                ],
                "evidence": [
                    _sanitize(str(e).strip()) for e in evidence if _sanitize(str(e).strip())
                ],
            }
        )
    return out


def _section_highlights(sections: list[dict]) -> tuple[str, str]:
    if not sections:
        return ("No data", "No data")
    scored = [(str(s.get("name", "Section")), float(s.get("score", 0))) for s in sections]
    best = max(scored, key=lambda x: x[1])
    worst = min(scored, key=lambda x: x[1])
    return f"{best[0]} ({best[1]:.1f}%)", f"{worst[0]} ({worst[1]:.1f}%)"


def _score_status(score: float) -> str:
    if score < 40:
        return "Critical"
    if score < 60:
        return "Needs Impr."
    if score < 80:
        return "Moderate"
    return "Strong"


def _score_band_color(score: float, P: dict) -> Any:
    if score >= 80:
        return P["green"]
    if score >= 60:
        return P["gold"]
    if score >= 40:
        return P["amber"]
    if score >= 20:
        return P["orange"]
    return P["red"]


def _maturity_band_color(maturity: str, P: dict) -> Any:
    m = maturity.strip().lower()
    if m in {"advanced", "strong", "managed"}:
        return P["green"]
    if m in {"defined", "established", "moderate"}:
        return P["gold"]
    if m in {"developing", "needs improvement", "basic", "needs impr."}:
        return P["amber"]
    if m in {"critical", "weak", "initial", "poor"}:
        return P["red"]
    return P["gold"]


def _priority_color(priority: str, P: dict) -> Any:
    if priority == "HIGH":
        return P["red"]
    if priority == "MEDIUM":
        return P["amber"]
    return P["slate"]


def _sanitize(value: str) -> str:
    cleaned = re.sub(r"\b[a-z0-9]+(?:-[a-z0-9]+)*-q\d+\b", "", value, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    return cleaned
