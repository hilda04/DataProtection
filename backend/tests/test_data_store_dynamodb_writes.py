from __future__ import annotations

from decimal import Decimal
from typing import Any

from services.data_store import DataStore


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_float(item) for item in value)
    if isinstance(value, tuple):
        return any(_contains_float(item) for item in value)
    return False


class AssessmentCreateTable:
    def __init__(self) -> None:
        self.saved_item: dict[str, Any] | None = None

    def put_item(self, *, Item: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        self.saved_item = Item
        return {}


class FrameworkRefreshTable:
    def __init__(self) -> None:
        self.update_values: dict[str, Any] | None = None

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        self.update_values = kwargs['ExpressionAttributeValues']
        return {}


def test_create_or_resume_assessment_converts_score_to_decimal() -> None:
    table = AssessmentCreateTable()
    store = DataStore(table=table)
    store._require_membership = lambda _user_sub: {'organisationId': 'org_123'}  # type: ignore[method-assign]
    store._get_framework = lambda _framework_id: {  # type: ignore[method-assign]
        'frameworkId': 'zim-dpa',
        'name': 'Zimbabwe Cyber and Data Protection Act',
        'version': '2021',
        'description': 'Framework metadata',
        'sections': [
            {
                'sectionId': 'governance-accountability',
                'name': 'Governance',
                'questions': [{'questionId': 'has-dpo', 'text': 'Has DPO?'}],
            }
        ],
    }
    store._list_assessment_items = lambda _org_id, _framework_id=None: []  # type: ignore[method-assign]

    summary, resumed = store.create_or_resume_assessment(
        {'sub': 'user-123', 'email': 'user@example.com'},
        'zim-dpa',
    )

    assert resumed is False
    assert summary['status'] == 'NOT_STARTED'
    assert table.saved_item is not None
    assert table.saved_item['score'] == Decimal('0.0')
    assert _contains_float(table.saved_item) is False


def test_refresh_framework_sections_converts_nested_floats_to_decimal() -> None:
    table = FrameworkRefreshTable()
    store = DataStore(table=table)

    store._refresh_framework_sections(
        existing_framework={'frameworkId': 'zim-dpa'},
        framework_definition={
            'sections': [
                {
                    'sectionId': 'governance-accountability',
                    'weights': [0.25, {'followup': 0.75}],
                }
            ]
        },
    )

    assert table.update_values is not None
    assert table.update_values[':sections'][0]['weights'][0] == Decimal('0.25')
    assert table.update_values[':sections'][0]['weights'][1]['followup'] == Decimal('0.75')
    assert _contains_float(table.update_values) is False
