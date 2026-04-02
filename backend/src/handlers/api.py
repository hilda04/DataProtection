from __future__ import annotations

import json
import logging
from typing import Any

from models.types import ApiResponse
from services.data_store import (
    ConflictError,
    DataStore,
    DataStoreError,
    NotAuthenticatedError,
    ReportUnavailableError,
    ValidationError,
    get_user_from_event,
)
from services.framework_registry import load_framework_catalog

logger = logging.getLogger(__name__)


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
        query_params = event.get('queryStringParameters') or {}
        framework_id = None
        if isinstance(query_params, dict):
            framework_id = query_params.get('framework_id') or query_params.get('frameworkId')
        return ApiResponse(
            status_code=200,
            body=store.get_bootstrap_for_framework(user=user, framework_id=framework_id),
        ).to_dict()
    except NotAuthenticatedError as error:
        return ApiResponse(status_code=401, body={'message': str(error)}).to_dict()
    except ValidationError as error:
        return ApiResponse(status_code=400, body={'message': str(error)}).to_dict()
    except DataStoreError as error:
        return ApiResponse(status_code=500, body={'message': str(error)}).to_dict()


def onboard_organization(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    route_name = 'POST /organisations'
    claims_present = _has_claims(event)

    try:
        store = DataStore()

        try:
            user = get_user_from_event(event)
        except NotAuthenticatedError:
            logger.exception(
                'Failed to extract authenticated user for organisation creation.',
                extra={
                    'route': route_name,
                    'claims_present': claims_present,
                },
            )
            raise

        try:
            payload = _load_body(event)
        except (TypeError, json.JSONDecodeError):
            logger.exception(
                'Failed to parse organisation creation request body.',
                extra={
                    'route': route_name,
                    'claims_present': claims_present,
                },
            )
            return ApiResponse(
                status_code=400,
                body={'message': 'Invalid request payload.'},
            ).to_dict()

        parsed_request_fields = {
            field: payload.get(field)
            for field in (
                'name',
                'sector',
                'size',
                'country',
                'primaryContactName',
                'primaryContactEmail',
            )
        }

        try:
            organisation = store.create_organisation(user, payload)
        except DataStoreError:
            logger.exception(
                'Organisation creation failed in data store.',
                extra={
                    'route': route_name,
                    'claims_present': claims_present,
                    'parsed_request_fields': parsed_request_fields,
                },
            )
            raise

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
        store = DataStore()
        user = get_user_from_event(event)
        payload = _load_body(event)
        framework_id = payload.get('frameworkId', 'cdpa')
        assessment, resumed = store.create_or_resume_assessment(user, str(framework_id))
        return ApiResponse(status_code=200 if resumed else 201, body=assessment).to_dict()
    except NotAuthenticatedError as error:
        return ApiResponse(status_code=401, body={'message': str(error)}).to_dict()
    except ValidationError as error:
        return ApiResponse(status_code=400, body={'message': str(error)}).to_dict()
    except DataStoreError as error:
        return ApiResponse(status_code=500, body={'message': str(error)}).to_dict()


def list_assessments(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    try:
        store = DataStore()
        user = get_user_from_event(event)
        query_params = event.get('queryStringParameters') or {}
        framework_id = None
        if isinstance(query_params, dict):
            framework_id = query_params.get('framework_id') or query_params.get('frameworkId')
        assessments = store.list_assessments(user, framework_id=framework_id)
        return ApiResponse(status_code=200, body=assessments).to_dict()
    except NotAuthenticatedError as error:
        return ApiResponse(status_code=401, body={'message': str(error)}).to_dict()
    except ValidationError as error:
        return ApiResponse(status_code=400, body={'message': str(error)}).to_dict()
    except DataStoreError as error:
        return ApiResponse(status_code=500, body={'message': str(error)}).to_dict()


def get_assessment(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    try:
        store = DataStore()
        user = get_user_from_event(event)
        assessment_id = str((event.get('pathParameters') or {}).get('assessmentId', '')).strip()
        if not assessment_id:
            return ApiResponse(
                status_code=400, body={'message': 'assessmentId is required.'}
            ).to_dict()
        assessment = store.get_assessment_detail(user, assessment_id)
        return ApiResponse(status_code=200, body=assessment).to_dict()
    except NotAuthenticatedError as error:
        return ApiResponse(status_code=401, body={'message': str(error)}).to_dict()
    except ValidationError as error:
        return ApiResponse(status_code=400, body={'message': str(error)}).to_dict()
    except DataStoreError as error:
        return ApiResponse(status_code=500, body={'message': str(error)}).to_dict()


def save_assessment_responses(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    try:
        store = DataStore()
        user = get_user_from_event(event)
        assessment_id = str((event.get('pathParameters') or {}).get('assessmentId', '')).strip()
        if not assessment_id:
            return ApiResponse(
                status_code=400, body={'message': 'assessmentId is required.'}
            ).to_dict()

        payload = _load_body(event)
        section_id = str(payload.get('sectionId', '')).strip()
        responses = payload.get('responses')
        if not section_id:
            return ApiResponse(
                status_code=400, body={'message': 'sectionId is required.'}
            ).to_dict()
        if not isinstance(responses, list):
            return ApiResponse(
                status_code=400, body={'message': 'responses must be an array.'}
            ).to_dict()

        assessment = store.save_assessment_responses(user, assessment_id, section_id, responses)
        return ApiResponse(status_code=200, body=assessment).to_dict()
    except NotAuthenticatedError as error:
        return ApiResponse(status_code=401, body={'message': str(error)}).to_dict()
    except ValidationError as error:
        return ApiResponse(status_code=400, body={'message': str(error)}).to_dict()
    except DataStoreError as error:
        return ApiResponse(status_code=500, body={'message': str(error)}).to_dict()


def get_assessment_report(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    try:
        store = DataStore()
        user = get_user_from_event(event)
        assessment_id = str((event.get('pathParameters') or {}).get('assessmentId', '')).strip()
        if not assessment_id:
            return ApiResponse(
                status_code=400, body={'message': 'assessmentId is required.'}
            ).to_dict()
        report = store.get_assessment_report_download_url(user, assessment_id)
        return ApiResponse(status_code=200, body=report).to_dict()
    except NotAuthenticatedError as error:
        return ApiResponse(status_code=401, body={'message': str(error)}).to_dict()
    except ValidationError as error:
        return ApiResponse(status_code=400, body={'message': str(error)}).to_dict()
    except ReportUnavailableError as error:
        return ApiResponse(status_code=404, body={'message': str(error)}).to_dict()
    except DataStoreError as error:
        return ApiResponse(status_code=500, body={'message': str(error)}).to_dict()


def restart_assessment(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    try:
        store = DataStore()
        user = get_user_from_event(event)
        assessment_id = str((event.get('pathParameters') or {}).get('assessmentId', '')).strip()
        if not assessment_id:
            return ApiResponse(
                status_code=400, body={'message': 'assessmentId is required.'}
            ).to_dict()
        restarted = store.restart_assessment(user, assessment_id)
        return ApiResponse(status_code=201, body=restarted).to_dict()
    except NotAuthenticatedError as error:
        return ApiResponse(status_code=401, body={'message': str(error)}).to_dict()
    except ValidationError as error:
        return ApiResponse(status_code=400, body={'message': str(error)}).to_dict()
    except DataStoreError as error:
        return ApiResponse(status_code=500, body={'message': str(error)}).to_dict()


def update_remediation_actions(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    try:
        store = DataStore()
        user = get_user_from_event(event)
        assessment_id = str((event.get('pathParameters') or {}).get('assessmentId', '')).strip()
        if not assessment_id:
            return ApiResponse(
                status_code=400, body={'message': 'assessmentId is required.'}
            ).to_dict()

        payload = _load_body(event)
        updates = payload.get('actions')
        if not isinstance(updates, list):
            return ApiResponse(
                status_code=400, body={'message': 'actions must be an array.'}
            ).to_dict()

        assessment = store.update_remediation_actions(user, assessment_id, updates)
        return ApiResponse(status_code=200, body=assessment).to_dict()
    except NotAuthenticatedError as error:
        return ApiResponse(status_code=401, body={'message': str(error)}).to_dict()
    except ValidationError as error:
        return ApiResponse(status_code=400, body={'message': str(error)}).to_dict()
    except DataStoreError as error:
        return ApiResponse(status_code=500, body={'message': str(error)}).to_dict()


def _load_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get('body') or '{}'
    if isinstance(body, str):
        return json.loads(body)
    if isinstance(body, dict):
        return body
    raise TypeError('Request body must be JSON object.')


def _has_claims(event: dict[str, Any]) -> bool:
    authorizer = event.get('requestContext', {}).get('authorizer', {})
    jwt_claims = authorizer.get('jwt', {}).get('claims')
    rest_claims = authorizer.get('claims')
    return isinstance(jwt_claims, dict) or isinstance(rest_claims, dict)
