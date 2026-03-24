from __future__ import annotations

import json
from typing import Any

from models.types import ApiResponse
from services.data_store import (
    ConflictError,
    DataStore,
    DataStoreError,
    NotAuthenticatedError,
    ValidationError,
    get_user_from_event,
)
from services.framework_registry import load_framework_catalog


def health(_event: dict[str, Any], _context: Any) -> dict[str, Any]:
    return ApiResponse(
        status_code=200,
        body={
            'status': 'ok',
            'ok': True,
            'service': 'dataprotection-backend',
        },
    ).to_dict()


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


def create_assessment(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    try:
        user = get_user_from_event(event)
        payload = _load_body(event)
        framework_id = payload.get('frameworkId', 'zim-dpa')
        return ApiResponse(
            status_code=201,
            body={
                'assessmentId': 'pending',
                'frameworkId': framework_id,
                'status': 'coming_next',
                'requestedBy': user['sub'],
                'message': 'Assessment creation is ready for future implementation.',
            },
        ).to_dict()
    except NotAuthenticatedError as error:
        return ApiResponse(status_code=401, body={'message': str(error)}).to_dict()


def _load_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get('body') or '{}'
    if isinstance(body, str):
        return json.loads(body)
    return body
