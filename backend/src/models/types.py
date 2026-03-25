from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, TypedDict, Union


class UserSummary(TypedDict):
    sub: str
    email: str


class OrganisationSummary(TypedDict):
    organisationId: str
    name: str
    sector: str
    size: str
    country: str
    primaryContactName: str
    primaryContactEmail: str
    createdBy: str
    createdAt: str


class FrameworkSummary(TypedDict):
    frameworkId: str
    name: str
    version: str
    description: str
    sections: List[Dict[str, str]]


class FrameworkQuestion(TypedDict, total=False):
    id: str
    text: str
    helpText: str


class FrameworkSection(TypedDict, total=False):
    id: str
    title: str
    summary: str
    questions: List[FrameworkQuestion]


class FrameworkDefinition(TypedDict, total=False):
    frameworkId: str
    name: str
    version: str
    description: str
    sections: List[FrameworkSection]


@dataclass
class ApiResponse:
    status_code: int
    body: Union[Dict[str, Any], List[Any]]
    headers: Dict[str, str] = field(
        default_factory=lambda: {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': os.environ.get('ALLOWED_FRONTEND_ORIGIN', '*'),
        }
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'statusCode': self.status_code,
            'headers': self.headers,
            'body': json.dumps(self.body),
        }
