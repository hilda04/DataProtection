from __future__ import annotations

import json
from typing import Any, Dict, Optional

from app import lambda_handler


def make_event(method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    event: Dict[str, Any] = {
        'rawPath': path,
        'requestContext': {
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
    if body is not None:
        event['body'] = json.dumps(body)
    return event


def test_health_route_returns_ok() -> None:
    response = lambda_handler(make_event('GET', '/health'), None)
    payload = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert payload['ok'] is True


def test_unknown_route_returns_404() -> None:
    response = lambda_handler(make_event('GET', '/missing'), None)
    payload = json.loads(response['body'])

    assert response['statusCode'] == 404
    assert payload['message'] == 'Route not found.'
