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
    method = event.get('requestContext', {}).get('http', {}).get('method', '')
    path = event.get('rawPath', '')
    handler = ROUTES.get((method, path))

    if handler is None:
        return ApiResponse(status_code=404, body={'message': 'Route not found.'}).to_dict()

    return handler(event, context)
