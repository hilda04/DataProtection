from __future__ import annotations

from typing import Any, Callable, Dict, Tuple

from handlers.api import (
    create_assessment,
    get_bootstrap,
    health,
    list_frameworks,
    onboard_organization,
)
from models.types import ApiResponse

RouteHandler = Callable[[Dict[str, Any], Any], Dict[str, Any]]

ROUTES: Dict[Tuple[str, str], RouteHandler] = {
    ('GET', '/health'): health,
    ('GET', '/frameworks'): list_frameworks,
    ('GET', '/app/bootstrap'): get_bootstrap,
    ('POST', '/organisations'): onboard_organization,
    ('POST', '/assessments'): create_assessment,
}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    method = _resolve_http_method(event)
    path = _resolve_route_path(event)
    handler = ROUTES.get((method, path))

    if handler is None:
        return ApiResponse(status_code=404, body={'message': 'Route not found.'}).to_dict()

    return handler(event, context)


def _resolve_http_method(event: Dict[str, Any]) -> str:
    request_context = event.get('requestContext', {})
    http_context = request_context.get('http', {})

    method = http_context.get('method') or event.get('httpMethod') or ''
    return str(method).upper()


def _resolve_route_path(event: Dict[str, Any]) -> str:
    request_context = event.get('requestContext', {})
    http_context = request_context.get('http', {})

    raw_candidates = [
        event.get('rawPath'),
        event.get('path'),
        http_context.get('path'),
        request_context.get('path'),
    ]

    stage = request_context.get('stage')
    for candidate in raw_candidates:
        if not candidate:
            continue

        normalised = _normalise_path(str(candidate), stage)
        if normalised:
            return normalised

    return ''


def _normalise_path(path: str, stage: Any = None) -> str:
    path_only = path.strip()
    if not path_only:
        return ''

    if '?' in path_only:
        path_only = path_only.split('?', 1)[0]

    if not path_only.startswith('/'):
        path_only = f'/{path_only}'

    while '//' in path_only:
        path_only = path_only.replace('//', '/')

    if len(path_only) > 1:
        path_only = path_only.rstrip('/')

    stage_value = str(stage).strip('/') if stage else ''
    if stage_value:
        stage_prefix = f'/{stage_value}'
        if path_only == stage_prefix:
            return '/'
        if path_only.startswith(f'{stage_prefix}/'):
            path_only = path_only[len(stage_prefix) :]
            if not path_only:
                return '/'

    return path_only
