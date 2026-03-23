from __future__ import annotations

import json
from typing import Any

from models.types import ApiResponse
from services.assessment_engine import calculate_weighted_score, generate_findings
from services.data_store import (
    ConflictError,
    DataStore,
    DataStoreError,
    NotAuthenticatedError,
    ValidationError,
    get_user_from_event,
)
from services.framework_registry import load_framework_catalog
from services.report_builder import build_report_summary

SAMPLE_RESPONSES = [
    {
        'sectionId': 'governance',
        'controlId': 'ZW-DPA-GOV-01',
        'score': 2,
        'weight': 5,
        'priority': 'high',
        'findingTemplate': 'Privacy governance ownership is not consistently formalised.',
        'recommendation': (
            'Assign a documented privacy lead and approve governance terms of '
            'reference.'
        ),
    },
    {
        'sectionId': 'security',
        'controlId': 'ZW-DPA-SEC-02',
        'score': 1,
        'weight': 4,
        'priority': 'high',
        'findingTemplate': 'Breach response activities are not fully documented or rehearsed.',
        'recommendation': 'Create and test a breach management workflow with escalation criteria.',
    },
]


def get_bootstrap(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    try:
        store = DataStore()
        user = get_user_from_event(event)
        return ApiResponse(status_code=200, body=store.get_bootstrap(user)).to_dict()
    except NotAuthenticatedError as error:
        return ApiResponse(status_code=401, body={'message': str(error)}).to_dict()
    except DataStoreError as error:
        return ApiResponse(status_code=500, body={'message': str(error)}).to_dict()


def onboard_organization(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    try:
        store = DataStore()
        user = get_user_from_event(event)
        payload = _load_body(event)
        organisation = store.create_organisation(user, payload)
        return ApiResponse(status_code=201, body=organisation).to_dict()
    except NotAuthenticatedError as error:
        return ApiResponse(status_code=401, body={'message': str(error)}).to_dict()
    except ValidationError as error:
        return ApiResponse(status_code=400, body={'message': str(error)}).to_dict()
    except ConflictError as error:
        return ApiResponse(status_code=409, body={'message': str(error)}).to_dict()
    except DataStoreError as error:
        return ApiResponse(status_code=500, body={'message': str(error)}).to_dict()


def list_frameworks(_event: dict[str, Any], _context: Any) -> dict[str, Any]:
    try:
        store = DataStore()
        return ApiResponse(status_code=200, body=store.list_frameworks()).to_dict()
    except DataStoreError:
        return ApiResponse(status_code=200, body=load_framework_catalog()).to_dict()


def start_assessment(_event: dict[str, Any], _context: Any) -> dict[str, Any]:
    return ApiResponse(
        status_code=201,
        body={
            'assessmentId': 'asm_demo_001',
            'status': 'coming_next',
            'frameworkId': 'zim-dpa',
            'message': 'Assessment creation is coming next.',
        },
    ).to_dict()


def calculate_results(_event: dict[str, Any], _context: Any) -> dict[str, Any]:
    scorecard = calculate_weighted_score(SAMPLE_RESPONSES)
    findings = generate_findings(SAMPLE_RESPONSES)
    report = build_report_summary(
        organization={'organizationId': 'org_demo', 'name': 'Demo Organization'},
        scorecard=scorecard,
        findings=findings,
    )
    return ApiResponse(status_code=200, body=report).to_dict()


def _load_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get('body') or '{}'
    if isinstance(body, str):
        return json.loads(body)
    return body
