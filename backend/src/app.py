from __future__ import annotations

from typing import Any, Callable, Dict, Tuple

from handlers.api import (
    create_assessment,
    get_assessment,
    get_assessment_report,
    get_bootstrap,
    health,
    list_assessments,
    list_frameworks,
    onboard_organization,
    save_assessment_responses,
)
from models.types import ApiResponse

RouteHandler = Callable[[Dict[str, Any], Any], Dict[str, Any]]

ROUTES: Dict[Tuple[str, str], RouteHandler] = {
    ('GET', '/health'): health,
    ('GET', '/frameworks'): list_frameworks,
    ('GET', '/app/bootstrap'): get_bootstrap,
    ('POST', '/organisations'): onboard_organization,
    ('POST', '/assessments'): create_assessment,
    ('GET', '/assessments'): list_assessments,
}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    method = _resolve_http_method(event)
    path = _resolve_route_path(event)
    handler = ROUTES.get((method, path))
    routed_event = event

    if handler is None and method == 'GET' and path.startswith('/assessments/'):
        assessment_id = path.split('/')[2] if len(path.split('/')) > 2 else ''
        if assessment_id:
            routed_event = {**event, 'pathParameters': {'assessmentId': assessment_id}}
            handler = get_assessment

    if (
        handler is None
        and method == 'POST'
        and path.startswith('/assessments/')
        and path.endswith('/responses')
    ):
        parts = path.strip('/').split('/')
        if len(parts) == 3 and parts[0] == 'assessments' and parts[2] == 'responses':
            routed_event = {**event, 'pathParameters': {'assessmentId': parts[1]}}
            handler = save_assessment_responses

    if (
        handler is None
        and method == 'GET'
        and path.startswith('/assessments/')
        and path.endswith('/report')
    ):
        parts = path.strip('/').split('/')
        if len(parts) == 3 and parts[0] == 'assessments' and parts[2] == 'report':
            routed_event = {**event, 'pathParameters': {'assessmentId': parts[1]}}
            handler = get_assessment_report

    if handler is None:
        return ApiResponse(status_code=404, body={'message': 'Route not found.'}).to_dict()

    return handler(routed_event, context)


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
