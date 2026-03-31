from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from decimal import Decimal
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
    guidance: Dict[str, Any]


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
            'body': safe_json_dumps(self.body),
        }


def to_json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, dict):
        return {key: to_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [to_json_safe(item) for item in value]
    return value


def safe_json_dumps(value: Any) -> str:
    return json.dumps(to_json_safe(value))
