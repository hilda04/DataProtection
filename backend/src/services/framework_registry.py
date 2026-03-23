from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.types import FrameworkSummary

FRAMEWORK_PATH = Path(__file__).resolve().parents[3] / 'frameworks' / 'zimbabwe-dpa.json'


def load_framework_catalog() -> list[FrameworkSummary]:
    framework = json.loads(FRAMEWORK_PATH.read_text())
    return [
        {
            'frameworkId': framework['frameworkId'],
            'name': framework['name'],
            'version': framework['version'],
            'description': framework['description'],
            'sections': [
                {
                    'sectionId': section['id'],
                    'name': section['title'],
                }
                for section in framework.get('sections', [])
            ],
        }
    ]


def build_framework_seed_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for framework in load_framework_catalog():
        items.append(
            {
                'pk': f"FRAMEWORK#{framework['frameworkId']}",
                'sk': 'META',
                'entityType': 'FRAMEWORK',
                **framework,
            }
        )

    return items
