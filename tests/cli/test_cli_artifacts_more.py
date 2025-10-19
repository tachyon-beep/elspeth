from __future__ import annotations

import json
from pathlib import Path

import pytest

from elspeth import cli


class _Settings:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path


def test_write_simple_artifacts_handles_settings_copy_failure(tmp_path: Path, monkeypatch):
    art_dir = tmp_path / "artifacts"
    art_dir.mkdir()
    payload = {"results": [{"row": {"x": 1}}]}
    cfg_file = tmp_path / "s.yaml"
    cfg_file.write_text("a: 1", encoding="utf-8")
    settings = _Settings(cfg_file)

    # Patch Path.read_text to raise UnicodeError when copying config snapshot
    _orig_read = Path.read_text

    def _boom(self: Path, *args, **kwargs):  # noqa: D401
        if self == cfg_file:
            raise UnicodeError("bad encoding")
        return _orig_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _boom, raising=True)

    # Should not raise despite copy failure; writes results JSON successfully
    cli._write_simple_artifacts(art_dir, "single", payload, settings)
    out = json.loads((art_dir / "single_results.json").read_text(encoding="utf-8"))
    assert out["results"][0]["row"]["x"] == 1


def test_load_yaml_json_rejects_non_mapping(tmp_path: Path):
    p = tmp_path / "cfg.yaml"
    p.write_text("- 1\n- 2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        cli._load_yaml_json(p)
