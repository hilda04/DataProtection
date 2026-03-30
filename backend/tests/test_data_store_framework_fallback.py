from __future__ import annotations

from typing import Any

import services.data_store as data_store_module
from services.data_store import DataStore


class FakeTable:
    def __init__(self, framework_item: dict[str, Any]):
        self.framework_item = framework_item
        self.update_calls: list[dict[str, Any]] = []

    def query(self, **_kwargs: Any) -> dict[str, Any]:
        return {'Items': [self.framework_item]}

    def get_item(self, *, Key: dict[str, str]) -> dict[str, Any]:
        if Key == {'pk': 'FRAMEWORKS', 'sk': f"FRAMEWORK#{self.framework_item['frameworkId']}"}:
            return {'Item': self.framework_item}
        return {}

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        self.update_calls.append(kwargs)
        return {}


def test_get_framework_uses_local_definition_when_seeded_framework_has_no_questions(
    monkeypatch,
) -> None:
    stale_framework = {
        'frameworkId': 'zim-dpa',
        'name': 'Zimbabwe Cyber and Data Protection Act',
        'version': '2021',
        'description': 'Outdated framework metadata',
        'sections': [
            {
                'sectionId': 'governance-accountability',
                'name': 'Governance and accountability',
            }
        ],
    }
    table = FakeTable(stale_framework)
    store = DataStore(table=table)

    local_definition = {
        'frameworkId': 'zim-dpa',
        'name': 'Zimbabwe Cyber and Data Protection Act',
        'version': '2021',
        'description': 'Current framework metadata',
        'sections': [
            {
                'sectionId': 'governance-accountability',
                'name': 'Governance and accountability',
                'questions': [
                    {'questionId': 'has-dpo', 'text': 'Assigned accountable person?'}
                ],
            }
        ],
    }
    monkeypatch.setattr(data_store_module, 'load_framework_definition', lambda: local_definition)

    framework = store._get_framework('zim-dpa')

    assert framework == local_definition
    assert len(table.update_calls) == 1
    assert (
        table.update_calls[0]['ExpressionAttributeValues'][':sections']
        == local_definition['sections']
    )


def test_normalise_framework_sections_accepts_legacy_control_shape() -> None:
    table = FakeTable(
        {
            'frameworkId': 'zim-dpa',
            'name': 'Zimbabwe Cyber and Data Protection Act',
            'version': '2021',
            'description': 'Framework metadata',
            'sections': [],
        }
    )
    store = DataStore(table=table)

    normalised = store._normalise_framework_sections(
        [
            {
                'id': 'governance-accountability',
                'title': 'Governance and accountability',
                'summary': 'Leadership ownership',
                'controls': [
                    {
                        'controlId': 'has-dpo',
                        'prompt': (
                            'Has your organisation assigned a person accountable '
                            'for data protection?'
                        ),
                        'helpText': 'Formal role or named responsible officer.',
                    }
                ],
            }
        ]
    )

    assert normalised == [
        {
            'sectionId': 'governance-accountability',
            'name': 'Governance and accountability',
            'description': 'Leadership ownership',
            'questions': [
                {
                    'questionId': 'has-dpo',
                    'text': (
                        'Has your organisation assigned a person accountable '
                        'for data protection?'
                    ),
                    'helpText': 'Formal role or named responsible officer.',
                }
            ],
        }
    ]


def test_load_assessment_sections_falls_back_when_framework_sections_have_no_questions(
    monkeypatch,
) -> None:
    table = FakeTable(
        {
            'frameworkId': 'custom-zim-dpa',
            'name': 'Zimbabwe Cyber and Data Protection Act',
            'version': '2021',
            'description': 'Framework metadata',
            'sections': [{'sectionId': 'governance-accountability', 'name': 'Governance'}],
        }
    )
    store = DataStore(table=table)

    monkeypatch.setattr(
        data_store_module,
        'load_framework_definition',
        lambda: {
            'frameworkId': 'zim-dpa',
            'name': 'Zimbabwe Cyber and Data Protection Act',
            'version': '2021',
            'description': 'Current framework metadata',
            'sections': [
                {
                    'sectionId': 'governance-accountability',
                    'name': 'Governance and accountability',
                    'questions': [
                        {'questionId': 'has-dpo', 'text': 'Assigned accountable person?'}
                    ],
                }
            ],
        },
    )

    sections = store._load_assessment_sections(table.framework_item)

    assert len(sections) == 1
    assert len(sections[0]['questions']) == 1
    assert sections[0]['questions'][0]['questionId'] == 'has-dpo'
