from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.types import FrameworkDefinition, FrameworkSummary

DEFAULT_FRAMEWORK_ID = 'cdpa'
LEGACY_FRAMEWORK_IDS = {'zim-dpa': DEFAULT_FRAMEWORK_ID}
REGISTERED_FRAMEWORK_FILES = (
    'zimbabwe-dpa.json',
    'rbz_nps.json',
    'ipec.json',
    'rbz_cyber.json',
    'nist_csf_2.json',
    'iso_27001_2022.json',
    'pci_dss_4_0_1.json',
)
# Developer note:
# New framework question banks must define `recommendation`, `evidence_required`, and
# `compliance_relevance` on every question to keep report output framework-specific
# and audit-grade.


def _framework_search_roots() -> tuple[Path, ...]:
    service_dir = Path(__file__).resolve().parent
    src_root = service_dir.parent
    repository_root = service_dir.parents[2]
    return (src_root / 'frameworks', repository_root / 'frameworks')


def resolve_framework_path(file_name: str) -> Path:
    for root in _framework_search_roots():
        candidate = root / file_name
        if candidate.is_file():
            return candidate

    searched = ', '.join(str(root / file_name) for root in _framework_search_roots())
    raise FileNotFoundError(f'Framework file not found. Looked in: {searched}')


def _framework_file_candidates() -> list[Path]:
    # Developer note:
    # Framework files used by the API must be listed in REGISTERED_FRAMEWORK_FILES.
    # This keeps the API's framework catalog explicit and predictable.
    candidates: list[Path] = []
    seen_names: set[str] = set()

    for file_name in REGISTERED_FRAMEWORK_FILES:
        candidates.append(resolve_framework_path(file_name))
        seen_names.add(file_name)

    # Include extra files during local development without overriding registered entries.
    for root in _framework_search_roots():
        if not root.is_dir():
            continue
        for file_path in sorted(root.glob('*.json')):
            if file_path.name in seen_names:
                continue
            seen_names.add(file_path.name)
            candidates.append(file_path)
    return candidates


def canonical_framework_id(framework_id: str) -> str:
    value = str(framework_id or '').strip()
    return LEGACY_FRAMEWORK_IDS.get(value, value)


def load_framework_definitions() -> list[FrameworkDefinition]:
    frameworks: list[FrameworkDefinition] = []
    for framework_path in _framework_file_candidates():
        framework = json.loads(framework_path.read_text(encoding='utf-8'))
        framework_id = str(framework.get('frameworkId') or '').strip()
        if not framework_id:
            continue
        framework['frameworkId'] = canonical_framework_id(framework_id)
        frameworks.append(framework)
    return frameworks


def load_framework_definition(framework_id: str = DEFAULT_FRAMEWORK_ID) -> FrameworkDefinition:
    target_framework_id = canonical_framework_id(framework_id)
    definitions = load_framework_definitions()
    for framework in definitions:
        if canonical_framework_id(str(framework.get('frameworkId') or '')) == target_framework_id:
            return framework

    raise FileNotFoundError(f'Framework not found: {target_framework_id}')


def load_framework_catalog() -> list[FrameworkSummary]:
    catalog: list[FrameworkSummary] = []
    for framework in load_framework_definitions():
        catalog.append(
            {
                'frameworkId': framework['frameworkId'],
                'id': framework['frameworkId'],
                'name': framework['name'],
                'version': framework.get('version', ''),
                'description': framework.get('description', ''),
                'sections': [
                    {
                        'sectionId': section.get('sectionId') or section.get('id'),
                        'name': section.get('name') or section.get('title'),
                    }
                    for section in framework.get('sections', [])
                    if section.get('sectionId') or section.get('id')
                ],
            }
        )
    return catalog


def build_framework_seed_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for framework in load_framework_definitions():
        items.append(
            {
                'pk': f"FRAMEWORK#{framework['frameworkId']}",
                'sk': 'META',
                'entityType': 'FRAMEWORK',
                'frameworkId': framework['frameworkId'],
                'id': framework['frameworkId'],
                'name': framework['name'],
                'version': framework.get('version', ''),
                'description': framework.get('description', ''),
                'sections': framework.get('sections', []),
            }
        )

    return items
