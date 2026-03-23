from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, TypedDict


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
    sections: list[dict[str, str]]


@dataclass(slots=True)
class ApiResponse:
    status_code: int
    body: dict[str, Any] | list[Any]
    headers: dict[str, str] = field(
        default_factory=lambda: {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': os.environ.get('ALLOWED_FRONTEND_ORIGIN', '*'),
        }
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            'statusCode': self.status_code,
            'headers': self.headers,
            'body': json.dumps(self.body),
        }
