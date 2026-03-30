from __future__ import annotations

import sys
from typing import Any

from services.data_store import DataStore, ReportUnavailableError


class FakeTable:
    def __init__(self) -> None:
        self.assessment_item = {
            'pk': 'ORG#org_123',
            'sk': 'ASSESSMENT#asm_123',
            'entityType': 'ASSESSMENT',
            'assessmentId': 'asm_123',
            'frameworkId': 'zim-dpa',
            'organisationId': 'org_123',
            'createdBy': 'user-123',
            'createdAt': '2026-03-23T00:00:00+00:00',
            'updatedAt': '2026-03-23T00:00:00+00:00',
            'status': 'IN_PROGRESS',
            'score': 0.0,
            'completedAt': None,
            'reportS3Key': None,
            'currentSectionId': 'governance-accountability',
        }
        self.response_item: dict[str, Any] | None = None

    def query(self, **kwargs: Any) -> dict[str, Any]:
        expression = str(kwargs.get('KeyConditionExpression', ''))
        if 'USER#' in expression:
            return {
                'Items': [
                    {
                        'pk': 'USER#user-123',
                        'sk': 'MEMBERSHIP#ORG#org_123',
                        'organisationId': 'org_123',
                    }
                ]
            }
        if 'ASSESSMENT#asm_123' in expression and self.response_item:
            return {'Items': [self.response_item]}
        return {'Items': []}

    def get_item(self, *, Key: dict[str, str]) -> dict[str, Any]:
        if Key == {'pk': 'ORG#org_123', 'sk': 'ASSESSMENT#asm_123'}:
            return {'Item': self.assessment_item}
        return {}

    def put_item(self, *, Item: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        self.response_item = Item
        return {}

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        values = kwargs['ExpressionAttributeValues']
        self.assessment_item['status'] = values[':status']
        self.assessment_item['currentSectionId'] = values[':section']
        self.assessment_item['updatedAt'] = values[':updatedAt']
        self.assessment_item['score'] = values[':score']
        if ':completedAt' in values:
            self.assessment_item['completedAt'] = values[':completedAt']
        if ':reportS3Key' in values:
            self.assessment_item['reportS3Key'] = values[':reportS3Key']
        return {}


class MissingReportKeyTable(FakeTable):
    def __init__(self) -> None:
        super().__init__()
        self.assessment_item['status'] = 'COMPLETED'
        self.assessment_item['reportS3Key'] = None


class ExistingReportKeyTable(FakeTable):
    def __init__(self) -> None:
        super().__init__()
        self.assessment_item['status'] = 'COMPLETED'
        self.assessment_item['reportS3Key'] = 'reports/asm_123.json'


def test_save_assessment_responses_completes_when_report_upload_fails(monkeypatch) -> None:
    table = FakeTable()
    store = DataStore(table=table)
    monkeypatch.setattr(
        store,
        '_require_membership',
        lambda _user_sub: {'organisationId': 'org_123'},
    )

    monkeypatch.setattr(
        store,
        '_get_framework',
        lambda _framework_id: {
            'frameworkId': 'zim-dpa',
            'name': 'Zimbabwe Cyber and Data Protection Act',
            'version': '2021',
            'description': 'desc',
            'sections': [
                {
                    'sectionId': 'governance-accountability',
                    'name': 'Governance and accountability',
                    'questions': [{'questionId': 'has-dpo', 'text': 'Has a DPO?'}],
                }
            ],
        },
    )
    monkeypatch.setattr(
        store,
        '_save_report_to_s3',
        lambda _assessment_id, _report: (_ for _ in ()).throw(RuntimeError('s3 failed')),
    )

    result = store.save_assessment_responses(
        {'sub': 'user-123', 'email': 'user@example.com'},
        'asm_123',
        'governance-accountability',
        [{'questionId': 'has-dpo', 'value': 2}],
    )

    assert result['status'] == 'COMPLETED'
    assert result['completedAt'] is not None
    assert result['reportS3Key'] is None


def test_get_assessment_report_download_url_raises_unavailable_when_report_key_missing() -> None:
    store = DataStore(table=MissingReportKeyTable())
    store._require_membership = lambda _user_sub: {'organisationId': 'org_123'}  # type: ignore[method-assign]

    try:
        store.get_assessment_report_download_url(
            {'sub': 'user-123', 'email': 'user@example.com'},
            'asm_123',
        )
    except ReportUnavailableError as error:
        assert str(error) == 'Report is not available for this assessment.'
    else:
        raise AssertionError('Expected ReportUnavailableError to be raised.')


def test_get_assessment_report_download_url_returns_signed_url_when_report_exists(
    monkeypatch,
) -> None:
    class FakeS3Client:
        def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
            assert Bucket == 'reports-bucket'
            assert Key == 'reports/asm_123.json'
            return {}

        def generate_presigned_url(
            self,
            _operation_name: str,
            *,
            Params: dict[str, str],
            ExpiresIn: int,
        ) -> str:
            assert Params == {'Bucket': 'reports-bucket', 'Key': 'reports/asm_123.json'}
            assert ExpiresIn == 3600
            return 'https://example.com/signed-report-url'

    class FakeBoto3Module:
        @staticmethod
        def client(name: str) -> FakeS3Client:
            assert name == 's3'
            return FakeS3Client()

    monkeypatch.setenv('REPORTS_BUCKET_NAME', 'reports-bucket')
    monkeypatch.setitem(sys.modules, 'boto3', FakeBoto3Module())

    store = DataStore(table=ExistingReportKeyTable())
    store._require_membership = lambda _user_sub: {'organisationId': 'org_123'}  # type: ignore[method-assign]
    result = store.get_assessment_report_download_url(
        {'sub': 'user-123', 'email': 'user@example.com'},
        'asm_123',
    )

    assert result['url'] == 'https://example.com/signed-report-url'
