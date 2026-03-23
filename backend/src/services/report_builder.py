from __future__ import annotations

from typing import Any


def build_report_summary(
    organization: dict[str, Any],
    scorecard: dict[str, Any],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "organization": organization,
        "summary": scorecard,
        "findings": findings,
        "recommendations": [item["recommendedAction"] for item in findings],
        "legalMapping": [item["controlId"] for item in findings],
    }
