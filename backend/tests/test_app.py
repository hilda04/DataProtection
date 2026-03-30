from __future__ import annotations

import json
from typing import Any, Dict, Optional

from app import lambda_handler


def make_event(
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    *,
    stage: str = 'dev-sam',
    include_raw_path: bool = True,
    include_event_path: bool = False,
    include_request_context_path: bool = False,
) -> Dict[str, Any]:
    event: Dict[str, Any] = {
        'requestContext': {
            'stage': stage,
            'http': {
                'method': method,
            },
            'authorizer': {
                'jwt': {
                    'claims': {
                        'sub': 'user-123',
                        'email': 'user@example.com',
                    }
                }
            },
        },
    }

    if include_raw_path:
        event['rawPath'] = path

    if include_event_path:
        event['path'] = path

    if include_request_context_path:
        event['requestContext']['http']['path'] = path

    if body is not None:
        event['body'] = json.dumps(body)
    return event


def test_health_route_returns_ok() -> None:
    response = lambda_handler(make_event('GET', '/health'), None)
    payload = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert payload['ok'] is True


def test_health_route_supports_stage_prefixed_raw_path() -> None:
    response = lambda_handler(make_event('GET', '/dev-sam/health'), None)
    payload = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert payload['ok'] is True


def test_health_route_supports_event_path_when_raw_path_missing() -> None:
    event = make_event('GET', '/dev-sam/health', include_raw_path=False, include_event_path=True)

    response = lambda_handler(event, None)
    payload = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert payload['ok'] is True


def test_health_route_supports_request_context_http_path_when_raw_path_missing() -> None:
    event = make_event(
        'GET',
        '/dev-sam/health',
        include_raw_path=False,
        include_request_context_path=True,
    )

    response = lambda_handler(event, None)
    payload = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert payload['ok'] is True


def test_unknown_route_returns_404() -> None:
    response = lambda_handler(make_event('GET', '/missing'), None)
    payload = json.loads(response['body'])

    assert response['statusCode'] == 404
    assert payload['message'] == 'Route not found.'


def test_assessment_detail_dynamic_route() -> None:
    response = lambda_handler(make_event('GET', '/assessments/asm_123'), None)

    assert response['statusCode'] != 404


def test_assessment_responses_dynamic_route() -> None:
    response = lambda_handler(
        make_event(
            'POST',
            '/assessments/asm_123/responses',
            body={'sectionId': 'governance-accountability', 'responses': []},
        ),
        None,
    )

    assert response['statusCode'] != 404


def test_assessment_report_dynamic_route() -> None:
    response = lambda_handler(make_event('GET', '/assessments/asm_123/report'), None)

    assert response['statusCode'] != 404
