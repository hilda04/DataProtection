from __future__ import annotations

from typing import Any

from services.assessment_engine import calculate_weighted_score, generate_findings
from services.framework_registry import load_framework_catalog
from services.report_builder import build_report_summary
from models.types import ApiResponse

SAMPLE_RESPONSES = [
    {
        "sectionId": "governance",
        "controlId": "ZW-DPA-GOV-01",
        "score": 2,
        "weight": 5,
        "priority": "high",
        "findingTemplate": "Privacy governance ownership is not consistently formalised.",
        "recommendation": "Assign a documented privacy lead and approve governance terms of reference.",
    },
    {
        "sectionId": "security",
        "controlId": "ZW-DPA-SEC-02",
        "score": 1,
        "weight": 4,
        "priority": "high",
        "findingTemplate": "Breach response activities are not fully documented or rehearsed.",
        "recommendation": "Create and test a breach management workflow with escalation criteria.",
    },
]


def onboard_organization(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    payload = event.get("body", {})
    return ApiResponse(
        status_code=201,
        body={
            "organizationId": "org_demo",
            "tenantId": "tenant_demo",
            "profile": payload,
        },
    ).to_dict()


def list_frameworks(_event: dict[str, Any], _context: Any) -> dict[str, Any]:
    return ApiResponse(status_code=200, body={"frameworks": load_framework_catalog()}).to_dict()


def start_assessment(_event: dict[str, Any], _context: Any) -> dict[str, Any]:
    return ApiResponse(
        status_code=201,
        body={
            "assessmentId": "asm_demo_001",
            "status": "in_progress",
            "frameworkId": "zw-cdpa-2021",
        },
    ).to_dict()


def calculate_results(_event: dict[str, Any], _context: Any) -> dict[str, Any]:
    scorecard = calculate_weighted_score(SAMPLE_RESPONSES)
    findings = generate_findings(SAMPLE_RESPONSES)
    report = build_report_summary(
        organization={"organizationId": "org_demo", "name": "Demo Organization"},
        scorecard=scorecard,
        findings=findings,
    )
    return ApiResponse(status_code=200, body=report).to_dict()
