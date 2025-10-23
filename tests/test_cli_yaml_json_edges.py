from __future__ import annotations

from pathlib import Path

import pytest

import elspeth.cli as cli


def test_load_yaml_json_requires_mapping(tmp_path: Path):
    p = tmp_path / "not_a_mapping.yaml"
    p.write_text("- 1\n- 2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        cli._load_yaml_json(p)


def test_load_yaml_json_invalid_yaml(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text("a: [1,2", encoding="utf-8")
    with pytest.raises(ValueError):
        cli._load_yaml_json(p)
