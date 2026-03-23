from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FRAMEWORK_PATH = Path(__file__).resolve().parents[3] / "frameworks" / "zimbabwe-dpa.json"


def load_framework_catalog() -> list[dict[str, Any]]:
    framework = json.loads(FRAMEWORK_PATH.read_text())
    return [
        {
            "frameworkId": framework["frameworkId"],
            "name": framework["name"],
            "version": framework["version"],
            "jurisdiction": framework["jurisdiction"],
            "sections": len(framework["sections"]),
        }
    ]
