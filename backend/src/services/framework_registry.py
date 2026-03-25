from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.types import FrameworkDefinition, FrameworkSummary

FRAMEWORK_FILENAME = 'zimbabwe-dpa.json'


def _framework_search_roots() -> tuple[Path, ...]:
    service_dir = Path(__file__).resolve().parent
    src_root = service_dir.parent
    repository_root = service_dir.parents[2]
    return (src_root / 'frameworks', repository_root / 'frameworks')


def resolve_framework_path(file_name: str = FRAMEWORK_FILENAME) -> Path:
    for root in _framework_search_roots():
        candidate = root / file_name
        if candidate.is_file():
            return candidate

    searched = ', '.join(str(root / file_name) for root in _framework_search_roots())
    raise FileNotFoundError(f'Framework file not found. Looked in: {searched}')


def load_framework_definition() -> FrameworkDefinition:
    framework_path = resolve_framework_path()
    return json.loads(framework_path.read_text(encoding='utf-8'))


def load_framework_catalog() -> list[FrameworkSummary]:
    framework = load_framework_definition()
    return [
        {
            'frameworkId': framework['frameworkId'],
            'name': framework['name'],
            'version': framework['version'],
            'description': framework['description'],
            'sections': [
                {
                    'sectionId': section.get('sectionId') or section.get('id'),
                    'name': section.get('name') or section.get('title'),
                }
                for section in framework.get('sections', [])
                if section.get('sectionId') or section.get('id')
            ],
        }
    ]


def build_framework_seed_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for framework in [load_framework_definition()]:
        items.append(
            {
                'pk': f"FRAMEWORK#{framework['frameworkId']}",
                'sk': 'META',
                'entityType': 'FRAMEWORK',
                'frameworkId': framework['frameworkId'],
                'name': framework['name'],
                'version': framework['version'],
                'description': framework['description'],
                'sections': framework.get('sections', []),
            }
        )

    return items
