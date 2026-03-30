from __future__ import annotations

import json
from typing import Any

import pytest

from handlers import api
from services.data_store import ConflictError, ValidationError


class FakeStore:
    def __init__(self, membership: bool = False):
        self.membership = membership
        self.organisation = {
            'organisationId': 'org_123',
            'name': 'Example Org',
            'sector': 'Finance',
            'size': '51-200',
            'country': 'Zimbabwe',
            'primaryContactName': 'Tariro Dube',
            'primaryContactEmail': 'tariro@example.com',
            'createdBy': 'user-123',
            'createdAt': '2026-03-23T00:00:00+00:00',
        }

    def get_bootstrap(self, user: dict[str, str]) -> dict[str, Any]:
        return {
            'user': user,
            'hasOrganisation': self.membership,
            'organisation': self.organisation if self.membership else None,
            'frameworks': [
                {
                    'frameworkId': 'zim-dpa',
                    'name': 'Zimbabwe Cyber and Data Protection Act',
                    'version': '2021',
                    'description': (
                        'Self-assessment against key data protection requirements '
                        'for Zimbabwean organisations.'
                    ),
                    'sections': [],
                }
            ],
        }

    def create_organisation(self, _user: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
        if self.membership:
            raise ConflictError('You already belong to an organisation.')
        if not payload.get('name'):
            raise ValidationError('name is required.')
        return {
            **self.organisation,
            **payload,
            'organisationId': 'org_new',
            'createdBy': self.organisation['createdBy'],
        }

    def list_frameworks(self) -> list[dict[str, Any]]:
        return [
            {
                'frameworkId': 'zim-dpa',
                'name': 'Zimbabwe Cyber and Data Protection Act',
                'version': '2021',
                'description': (
                    'Self-assessment against key data protection requirements for '
                    'Zimbabwean organisations.'
                ),
                'sections': [],
            }
        ]

    def create_or_resume_assessment(
        self, user: dict[str, str], framework_id: str
    ) -> tuple[dict[str, Any], bool]:
        return (
            {
                'assessmentId': 'asm_123',
                'frameworkId': framework_id,
                'organisationId': 'org_123',
                'createdBy': user['sub'],
                'createdAt': '2026-03-23T00:00:00+00:00',
                'updatedAt': '2026-03-23T00:00:00+00:00',
                'status': 'IN_PROGRESS',
                'score': 32.5,
                'completedAt': None,
                'reportS3Key': None,
                'currentSectionId': 'governance-accountability',
            },
            False,
        )

    def list_assessments(
        self, _user: dict[str, str], framework_id: str | None = None
    ) -> list[dict[str, Any]]:
        return [
            {
                'assessmentId': 'asm_123',
                'frameworkId': framework_id or 'zim-dpa',
                'organisationId': 'org_123',
                'createdBy': 'user-123',
                'createdAt': '2026-03-23T00:00:00+00:00',
                'updatedAt': '2026-03-23T00:00:00+00:00',
                'status': 'IN_PROGRESS',
                'score': 32.5,
                'completedAt': None,
                'reportS3Key': None,
                'currentSectionId': 'governance-accountability',
            }
        ]

    def get_assessment_detail(self, _user: dict[str, str], assessment_id: str) -> dict[str, Any]:
        return {
            'assessmentId': assessment_id,
            'frameworkId': 'zim-dpa',
            'organisationId': 'org_123',
            'createdBy': 'user-123',
            'createdAt': '2026-03-23T00:00:00+00:00',
            'updatedAt': '2026-03-23T00:00:00+00:00',
            'status': 'IN_PROGRESS',
            'score': 32.5,
            'completedAt': None,
            'reportS3Key': None,
            'currentSectionId': 'governance-accountability',
            'framework': {
                'frameworkId': 'zim-dpa',
                'name': 'Zimbabwe Cyber and Data Protection Act',
                'version': '2021',
                'description': 'desc',
                'sections': [],
            },
            'responses': {},
        }

    def save_assessment_responses(
        self,
        _user: dict[str, str],
        assessment_id: str,
        section_id: str,
        _responses: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            'assessmentId': assessment_id,
            'frameworkId': 'zim-dpa',
            'organisationId': 'org_123',
            'createdBy': 'user-123',
            'createdAt': '2026-03-23T00:00:00+00:00',
            'updatedAt': '2026-03-23T00:00:00+00:00',
            'status': 'IN_PROGRESS',
            'score': 50.0,
            'completedAt': None,
            'reportS3Key': None,
            'currentSectionId': section_id,
        }

    def get_assessment_report_download_url(
        self, _user: dict[str, str], _assessment_id: str
    ) -> dict[str, str]:
        return {'url': 'https://example.com/report.json'}


@pytest.fixture
def auth_event() -> dict[str, Any]:
    return {
        'requestContext': {
            'authorizer': {
                'jwt': {
                    'claims': {
                        'sub': 'user-123',
                        'email': 'user@example.com',
                    }
                }
            }
        }
    }


@pytest.fixture
def auth_event_rest_claims() -> dict[str, Any]:
    return {
        'requestContext': {
            'authorizer': {
                'claims': {
                    'sub': 'user-legacy',
                    'email': 'legacy@example.com',
                }
            }
        }
    }


def test_get_bootstrap_returns_existing_organisation(
    monkeypatch: pytest.MonkeyPatch, auth_event: dict[str, Any]
) -> None:
    monkeypatch.setattr(api, 'DataStore', lambda: FakeStore(membership=True))

    response = api.get_bootstrap(auth_event, None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert body['hasOrganisation'] is True
    assert body['organisation']['organisationId'] == 'org_123'


def test_get_bootstrap_accepts_rest_authorizer_claims(
    monkeypatch: pytest.MonkeyPatch, auth_event_rest_claims: dict[str, Any]
) -> None:
    monkeypatch.setattr(api, 'DataStore', lambda: FakeStore(membership=True))

    response = api.get_bootstrap(auth_event_rest_claims, None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert body['user']['sub'] == 'user-legacy'
    assert body['user']['email'] == 'legacy@example.com'


def test_create_organisation_uses_authenticated_user(
    monkeypatch: pytest.MonkeyPatch, auth_event: dict[str, Any]
) -> None:
    monkeypatch.setattr(api, 'DataStore', lambda: FakeStore(membership=False))
    event = {
        **auth_event,
        'body': json.dumps(
            {
                'name': 'Example Org',
                'sector': 'Finance',
                'size': '51-200',
                'country': 'Zimbabwe',
                'primaryContactName': 'Tariro Dube',
                'primaryContactEmail': 'tariro@example.com',
                'createdBy': 'frontend-user-should-not-win',
            }
        ),
    }

    response = api.onboard_organization(event, None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 201
    assert body['createdBy'] != 'frontend-user-should-not-win'


def test_create_organisation_allows_missing_email_claim(
    monkeypatch: pytest.MonkeyPatch, auth_event: dict[str, Any]
) -> None:
    monkeypatch.setattr(api, 'DataStore', lambda: FakeStore(membership=False))
    event = {
        'requestContext': {
            'authorizer': {
                'jwt': {
                    'claims': {
                        'sub': auth_event['requestContext']['authorizer']['jwt']['claims']['sub'],
                    }
                }
            }
        },
        'body': json.dumps(
            {
                'name': 'Example Org',
                'sector': 'Finance',
                'size': '51-200',
                'country': 'Zimbabwe',
                'primaryContactName': 'Tariro Dube',
                'primaryContactEmail': 'tariro@example.com',
            }
        ),
    }

    response = api.onboard_organization(event, None)

    assert response['statusCode'] == 201




def test_create_organisation_rejects_invalid_json_body(
    monkeypatch: pytest.MonkeyPatch, auth_event: dict[str, Any]
) -> None:
    monkeypatch.setattr(api, 'DataStore', lambda: FakeStore(membership=False))
    event = {
        **auth_event,
        'body': '{"name": "Example Org"',
    }

    response = api.onboard_organization(event, None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 400
    assert body['message'] == 'Invalid request payload.'

def test_create_organisation_requires_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, 'DataStore', lambda: FakeStore(membership=False))

    response = api.onboard_organization({'body': '{}'}, None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 401
    assert 'claims' in body['message']


def test_list_frameworks_returns_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, 'DataStore', lambda: FakeStore(membership=False))

    response = api.list_frameworks({}, None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert body[0]['frameworkId'] == 'zim-dpa'
    assert 'description' in body[0]


def test_create_assessment_returns_record(
    monkeypatch: pytest.MonkeyPatch, auth_event: dict[str, Any]
) -> None:
    monkeypatch.setattr(api, 'DataStore', lambda: FakeStore(membership=True))
    event = {
        **auth_event,
        'body': json.dumps({'frameworkId': 'zim-dpa'}),
    }

    response = api.create_assessment(event, None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 201
    assert body['frameworkId'] == 'zim-dpa'
    assert body['status'] == 'IN_PROGRESS'


def test_list_assessments_returns_latest(
    monkeypatch: pytest.MonkeyPatch, auth_event: dict[str, Any]
) -> None:
    monkeypatch.setattr(api, 'DataStore', lambda: FakeStore(membership=True))
    event = {
        **auth_event,
        'queryStringParameters': {'frameworkId': 'zim-dpa'},
    }
    response = api.list_assessments(event, None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert len(body) == 1
    assert body[0]['frameworkId'] == 'zim-dpa'


def test_get_assessment_returns_detail(
    monkeypatch: pytest.MonkeyPatch, auth_event: dict[str, Any]
) -> None:
    monkeypatch.setattr(api, 'DataStore', lambda: FakeStore(membership=True))
    event = {
        **auth_event,
        'pathParameters': {'assessmentId': 'asm_123'},
    }
    response = api.get_assessment(event, None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert body['assessmentId'] == 'asm_123'
    assert 'framework' in body


def test_save_assessment_responses_updates_assessment(
    monkeypatch: pytest.MonkeyPatch, auth_event: dict[str, Any]
) -> None:
    monkeypatch.setattr(api, 'DataStore', lambda: FakeStore(membership=True))
    event = {
        **auth_event,
        'pathParameters': {'assessmentId': 'asm_123'},
        'body': json.dumps(
            {
                'sectionId': 'governance-accountability',
                'responses': [{'questionId': 'has-dpo', 'value': 2}],
            }
        ),
    }
    response = api.save_assessment_responses(event, None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert body['currentSectionId'] == 'governance-accountability'


def test_get_assessment_report_returns_signed_url(
    monkeypatch: pytest.MonkeyPatch, auth_event: dict[str, Any]
) -> None:
    monkeypatch.setattr(api, 'DataStore', lambda: FakeStore(membership=True))
    event = {
        **auth_event,
        'pathParameters': {'assessmentId': 'asm_123'},
    }
    response = api.get_assessment_report(event, None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert body['url'].startswith('https://')
