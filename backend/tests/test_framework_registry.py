from __future__ import annotations

from pathlib import Path

import pytest

from services import framework_registry


def test_resolve_framework_path_prefers_packaged_framework_directory() -> None:
    path = framework_registry.resolve_framework_path()

    assert path.name == 'zimbabwe-dpa.json'
    assert path.is_file()
    assert 'frameworks' in path.parts


def test_resolve_framework_path_raises_with_clear_locations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing_roots = (tmp_path / 'a', tmp_path / 'b')
    monkeypatch.setattr(framework_registry, '_framework_search_roots', lambda: missing_roots)

    with pytest.raises(FileNotFoundError) as error:
        framework_registry.resolve_framework_path('missing.json')

    message = str(error.value)
    assert str(missing_roots[0] / 'missing.json') in message
    assert str(missing_roots[1] / 'missing.json') in message
