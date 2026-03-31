from __future__ import annotations

from decimal import Decimal
from numbers import Real
from typing import Any

ANSWER_TO_SCORE = {
    "yes": 1.0,
    "partial": 0.5,
    "no": 0.0,
}
MATURITY_SCALE = 4
RISK_LEVELS = {
    "high": 1.5,
    "medium": 2.5,
}


def calculate_assessment_score(
    responses_by_section: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    total_possible = 0.0
    achieved = 0.0
    section_scores: list[dict[str, Any]] = []

    for section_id, responses in responses_by_section.items():
        section_total = float(len(responses))
        section_achieved = sum(normalize_response_value(item) for item in responses)
        total_possible += section_total
        achieved += section_achieved
        section_score = round((section_achieved / section_total) * 100, 2) if section_total else 0.0
        section_scores.append({"sectionId": section_id, "score": section_score})

    overall_score = round((achieved / total_possible) * 100, 2) if total_possible else 0.0
    return {"score": overall_score, "sectionScores": section_scores}


def normalize_response_value(value: Any) -> float:
    if isinstance(value, dict):
        for candidate_key in ('value', 'answer', 'response', 'selectedOption'):
            if candidate_key in value:
                return normalize_response_value(value.get(candidate_key))

    if isinstance(value, Decimal):
        value = float(value)

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ANSWER_TO_SCORE:
            return ANSWER_TO_SCORE[normalized]

    if isinstance(value, Real):
        numeric = float(value)
        if numeric <= 0:
            return 0.0
        if numeric < 3:
            return 0.5
        return 1.0

    return 0.0


def calculate_weighted_score(responses: list[dict[str, Any]]) -> dict[str, Any]:
    total_weight = sum(item["weight"] for item in responses)
    weighted_sum = sum(item["weight"] * item["score"] for item in responses)
    percentage = (
        round((weighted_sum / (total_weight * MATURITY_SCALE)) * 100) if total_weight else 0
    )
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
