from __future__ import annotations

import re
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parents[1] / 'template.yaml'


def test_template_deploys_public_health_route() -> None:
    template = TEMPLATE_PATH.read_text(encoding='utf-8')
    assert re.search(
        r"HealthRoute:\n(?:\s+.*\n)*?\s+Path:\s+/health\n(?:\s+.*\n)*?\s+Authorizer:\s+NONE",
        template,
    )


def test_template_keeps_frameworks_route_protected() -> None:
    template = TEMPLATE_PATH.read_text(encoding='utf-8')
    match = re.search(
        r"FrameworksRoute:\n(?P<body>(?:\s+.*\n)+?)\s+\w+Route:",
        template,
    )
    assert match is not None
    assert 'Path: /frameworks' in match.group('body')
    assert 'Authorizer: NONE' not in match.group('body')
