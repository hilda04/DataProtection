from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ApiResponse:
    status_code: int
    body: dict[str, Any]
    headers: dict[str, str] = field(
        default_factory=lambda: {"Content-Type": "application/json"}
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "statusCode": self.status_code,
            "headers": self.headers,
            "body": self.body,
        }
