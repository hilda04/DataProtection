from __future__ import annotations

from typing import Any

MATURITY_SCALE = 4
RISK_LEVELS = {
    "high": 1.5,
    "medium": 2.5,
}


def calculate_weighted_score(responses: list[dict[str, Any]]) -> dict[str, Any]:
    total_weight = sum(item["weight"] for item in responses)
    weighted_sum = sum(item["weight"] * item["score"] for item in responses)
    percentage = round((weighted_sum / (total_weight * MATURITY_SCALE)) * 100) if total_weight else 0
    return {
        "overallScore": percentage,
        "sectionScores": _calculate_section_scores(responses),
    }


def generate_findings(responses: list[dict[str, Any]]) -> list[dict[str, str]]:
    findings = []
    for response in responses:
        threshold = RISK_LEVELS.get(response["priority"], 3.0)
        if response["score"] < threshold:
            findings.append(
                {
                    "controlId": response["controlId"],
                    "riskLevel": response["priority"].capitalize(),
                    "summary": response["findingTemplate"],
                    "recommendedAction": response["recommendation"],
                }
            )
    return findings


def _calculate_section_scores(responses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, float]] = {}
    for response in responses:
        bucket = buckets.setdefault(response["sectionId"], {"weighted": 0.0, "weight": 0.0})
        bucket["weighted"] += response["score"] * response["weight"]
        bucket["weight"] += response["weight"]

    return [
        {
            "sectionId": section_id,
            "score": round((values["weighted"] / (values["weight"] * MATURITY_SCALE)) * 100),
        }
        for section_id, values in buckets.items()
    ]
