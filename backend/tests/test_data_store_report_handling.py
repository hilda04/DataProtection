from __future__ import annotations

import sys
from decimal import Decimal
from typing import Any

from services.data_store import DataStore, ReportUnavailableError, _convert_floats_to_decimal


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
        self.last_update_expression_values: dict[str, Any] | None = None

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
        if self.response_item:
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
        self.last_update_expression_values = values
        if ':status' in values:
            self.assessment_item['status'] = values[':status']
        if ':section' in values:
            self.assessment_item['currentSectionId'] = values[':section']
        if ':updatedAt' in values:
            self.assessment_item['updatedAt'] = values[':updatedAt']
        if ':score' in values:
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
        self.assessment_item['reportS3Key'] = 'reports/asm_123.pdf'


class HistoryTable(FakeTable):
    pass


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

    nested_responses = [
        {
            'questionId': 'has-dpo',
            'value': 2,
            'weight': 0.75,
            'metadata': {
                'confidence': 0.8,
                'scores': [0.1, 1, True, None, {'inner': 0.33}],
            },
        }
    ]

    result = store.save_assessment_responses(
        {'sub': 'user-123', 'email': 'user@example.com'},
        'asm_123',
        'governance-accountability',
        nested_responses,
    )

    assert result['status'] == 'COMPLETED'
    assert result['score'] == 50.0
    assert result['completedAt'] is not None
    assert result['reportS3Key'] is None
    assert result['reportUrl'] is None
    assert isinstance(table.response_item['responses'][0]['weight'], Decimal)
    assert isinstance(table.response_item['responses'][0]['metadata']['confidence'], Decimal)
    assert isinstance(table.response_item['responses'][0]['metadata']['scores'][0], Decimal)
    assert table.response_item['responses'][0]['metadata']['scores'][1] == 1
    assert table.response_item['responses'][0]['metadata']['scores'][2] is True
    assert table.response_item['responses'][0]['metadata']['scores'][3] is None
    assert isinstance(
        table.response_item['responses'][0]['metadata']['scores'][4]['inner'], Decimal
    )
    assert isinstance(table.last_update_expression_values[':score'], Decimal)


def test_convert_floats_to_decimal_preserves_supported_types() -> None:
    payload = {
        'float_value': 0.5,
        'int_value': 2,
        'string_value': 'ok',
        'bool_value': True,
        'none_value': None,
        'list_value': [1.2, {'nested_float': 3.4, 'nested_bool': False}],
        'tuple_value': (4.5, 'x'),
    }

    converted = _convert_floats_to_decimal(payload)

    assert converted['float_value'] == Decimal('0.5')
    assert converted['int_value'] == 2
    assert converted['string_value'] == 'ok'
    assert converted['bool_value'] is True
    assert converted['none_value'] is None
    assert converted['list_value'][0] == Decimal('1.2')
    assert converted['list_value'][1]['nested_float'] == Decimal('3.4')
    assert converted['list_value'][1]['nested_bool'] is False
    assert converted['tuple_value'][0] == Decimal('4.5')
    assert converted['tuple_value'][1] == 'x'


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
            assert Key == 'reports/asm_123.pdf'
            return {}

        def generate_presigned_url(
            self,
            _operation_name: str,
            *,
            Params: dict[str, str],
            ExpiresIn: int,
        ) -> str:
            assert Params == {'Bucket': 'reports-bucket', 'Key': 'reports/asm_123.pdf'}
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


def test_get_assessment_report_download_url_generates_missing_report_on_demand(monkeypatch) -> None:
    class FakeS3Client:
        def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
            assert Bucket == 'reports-bucket'
            assert Key == 'reports/asm_123.pdf'
            return {}

        def generate_presigned_url(
            self,
            _operation_name: str,
            *,
            Params: dict[str, str],
            ExpiresIn: int,
        ) -> str:
            assert Params == {'Bucket': 'reports-bucket', 'Key': 'reports/asm_123.pdf'}
            assert ExpiresIn == 3600
            return 'https://example.com/generated-report-url'

    class FakeBoto3Module:
        @staticmethod
        def client(name: str) -> FakeS3Client:
            assert name == 's3'
            return FakeS3Client()

    monkeypatch.setenv('REPORTS_BUCKET_NAME', 'reports-bucket')
    monkeypatch.setitem(sys.modules, 'boto3', FakeBoto3Module())

    table = MissingReportKeyTable()
    table.response_item = {
        'pk': 'ASSESSMENT#asm_123',
        'sk': 'RESPONSE#governance-accountability',
        'sectionId': 'governance-accountability',
        'responses': [{'questionId': 'has-dpo', 'value': Decimal('2')}],
    }
    store = DataStore(table=table)
    store._require_membership = lambda _user_sub: {'organisationId': 'org_123'}  # type: ignore[method-assign]
    monkeypatch.setattr(store, '_build_assessment_report', lambda *_args, **_kwargs: {'ok': True})
    monkeypatch.setattr(
        store,
        '_save_report_to_s3',
        lambda *_args, **_kwargs: 'reports/asm_123.pdf',
    )
    monkeypatch.setattr(
        store,
        '_get_framework',
        lambda _framework_id: {
            'frameworkId': 'zim-dpa',
            'name': 'Framework',
            'version': '2021',
            'description': 'desc',
            'sections': [
                {
                    'sectionId': 'governance-accountability',
                    'name': 'Governance and accountability',
                    'questions': [],
                }
            ],
        },
    )

    result = store.get_assessment_report_download_url(
        {'sub': 'user-123', 'email': 'user@example.com'},
        'asm_123',
    )

    assert result['url'] == 'https://example.com/generated-report-url'
    assert result['reportUrl'] == 'https://example.com/generated-report-url'
    assert result['signedUrl'] == 'https://example.com/generated-report-url'
    assert table.assessment_item['score'] == Decimal('50.0')
    assert table.last_update_expression_values[':score'] == Decimal('50.0')


def test_serialize_assessment_summary_includes_presigned_report_url(monkeypatch) -> None:
    class FakeS3Client:
        def generate_presigned_url(
            self,
            _operation_name: str,
            *,
            Params: dict[str, str],
            ExpiresIn: int,
        ) -> str:
            assert Params == {'Bucket': 'reports-bucket', 'Key': 'reports/asm_123.pdf'}
            assert ExpiresIn == 3600
            return 'https://example.com/detail-report-url'

    class FakeBoto3Module:
        @staticmethod
        def client(name: str) -> FakeS3Client:
            assert name == 's3'
            return FakeS3Client()

    monkeypatch.setenv('REPORTS_BUCKET_NAME', 'reports-bucket')
    monkeypatch.setitem(sys.modules, 'boto3', FakeBoto3Module())

    store = DataStore(table=ExistingReportKeyTable())
    summary = store._serialize_assessment_summary(store.table.assessment_item)

    assert summary['reportS3Key'] == 'reports/asm_123.pdf'
    assert summary['reportUrl'] == 'https://example.com/detail-report-url'


def test_restart_assessment_creates_new_record_without_overwrite(monkeypatch) -> None:
    table = FakeTable()
    store = DataStore(table=table)
    store._require_membership = lambda _user_sub: {'organisationId': 'org_123'}  # type: ignore[method-assign]
    monkeypatch.setattr(
        store,
        '_get_framework',
        lambda _framework_id: {
            'frameworkId': 'zim-dpa',
            'name': 'Framework',
            'version': '2021',
            'description': 'desc',
            'sections': [
                {
                    'sectionId': 'governance-accountability',
                    'name': 'Governance',
                    'questions': [],
                }
            ],
        },
    )
    table.assessment_item['status'] = 'COMPLETED'
    previous_assessment_id = table.assessment_item['assessmentId']

    restarted = store.restart_assessment(
        {'sub': 'user-123', 'email': 'user@example.com'},
        previous_assessment_id,
    )

    assert restarted['assessmentId'] != previous_assessment_id
    assert restarted['previousAssessmentId'] == previous_assessment_id
    assert restarted['status'] == 'NOT_STARTED'
    assert table.assessment_item['assessmentId'] == previous_assessment_id


def test_save_report_to_s3_uploads_pdf(monkeypatch) -> None:
    uploaded: dict[str, Any] = {}

    class FakeS3Client:
        def put_object(self, **kwargs: Any) -> dict[str, Any]:
            uploaded.update(kwargs)
            return {}

    class FakeBoto3Module:
        @staticmethod
        def client(name: str) -> FakeS3Client:
            assert name == 's3'
            return FakeS3Client()

    monkeypatch.setenv('REPORTS_BUCKET_NAME', 'reports-bucket')
    monkeypatch.setitem(sys.modules, 'boto3', FakeBoto3Module())
    store = DataStore(table=FakeTable())

    key = store._save_report_to_s3('asm_123', {'score': 75.0, 'sections': []})

    assert key == 'reports/asm_123.pdf'
    assert uploaded['Bucket'] == 'reports-bucket'
    assert uploaded['Key'] == 'reports/asm_123.pdf'
    assert uploaded['ContentType'] == 'application/pdf'
    assert isinstance(uploaded['Body'], bytes)


def test_list_assessment_history_returns_most_recent_first() -> None:
    store = DataStore(table=HistoryTable())
    store._require_membership = lambda _user_sub: {'organisationId': 'org_123'}  # type: ignore[method-assign]
    store._list_assessment_items = lambda _org_id, _framework_id=None: [  # type: ignore[method-assign]
        {
            **store.table.assessment_item,
            'assessmentId': 'asm_old',
            'updatedAt': '2026-01-01T00:00:00+00:00',
        },
        {
            **store.table.assessment_item,
            'assessmentId': 'asm_new',
            'updatedAt': '2026-02-01T00:00:00+00:00',
        },
    ]

    history = store.list_assessments({'sub': 'user-123', 'email': 'user@example.com'}, 'zim-dpa')

    assert [item['assessmentId'] for item in history] == ['asm_old', 'asm_new']
