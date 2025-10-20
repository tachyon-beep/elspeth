from __future__ import annotations

from pathlib import Path

import yaml

from elspeth.core.validation.settings import validate_settings


def _write_yaml(path: Path, payload: dict) -> Path:
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_validate_settings_valid_top_level_sinks(tmp_path: Path):
    payload = {
        "default": {
            "datasource": {
                "plugin": "local_csv",
                "security_level": "OFFICIAL",
                "determinism_level": "guaranteed",
                "options": {"path": str(tmp_path / "in.csv"), "retain_local": False},
            },
            "llm": {
                "plugin": "mock",
                "security_level": "OFFICIAL",
                "determinism_level": "guaranteed",
                "options": {"seed": 1},
            },
            "sinks": [
                {
                    "plugin": "csv",
                    "security_level": "OFFICIAL",
                    "determinism_level": "guaranteed",
                    "options": {"path": str(tmp_path / "out.csv")},
                }
            ],
            "retry": {"max_attempts": 1},
            "checkpoint": {},
            "concurrency": {},
        }
    }
    path = _write_yaml(tmp_path / "settings.yaml", payload)
    report = validate_settings(path, profile="default")
    assert not report.has_errors()


def test_validate_settings_invalid_types_and_fallbacks(tmp_path: Path):
    # No top-level sinks; provide via prompt pack
    payload = {
        "default": {
            "datasource": {
                "plugin": "local_csv",
                "security_level": "OFFICIAL",
                "determinism_level": "guaranteed",
                "options": {"path": str(tmp_path / "in.csv"), "retain_local": False},
            },
            "llm": {
                "plugin": "mock",
                "security_level": "OFFICIAL",
                "determinism_level": "guaranteed",
                "options": {"seed": 1},
            },
            "prompt_pack": "packA",
            "prompt_packs": {
                "packA": {
                    "sinks": [
                        {
                            "plugin": "csv",
                            "security_level": "OFFICIAL",
                            "determinism_level": "guaranteed",
                            "options": {"path": str(tmp_path / "out.csv")},
                        }
                    ]
                }
            },
            # Invalid type to exercise _validate_additional_mappings error path
            "retry": ["not", "a", "mapping"],
        }
    }
    path = _write_yaml(tmp_path / "settings2.yaml", payload)
    report = validate_settings(path, profile="default")
    # Should have at least one error (retry or other section), but not about missing sinks
    assert report.has_errors()
    assert not any("must be provided either at the profile level" in m.format() for m in report.errors)


def test_validate_settings_top_level_sinks_wrong_type(tmp_path: Path):
    payload = {
        "default": {
            "datasource": {
                "plugin": "local_csv",
                "security_level": "OFFICIAL",
                "determinism_level": "guaranteed",
                "options": {"path": str(tmp_path / "in.csv"), "retain_local": False},
            },
            "llm": {
                "plugin": "mock",
                "security_level": "OFFICIAL",
                "determinism_level": "guaranteed",
                "options": {"seed": 1},
            },
            "sinks": {"plugin": "csv"},  # wrong type
        }
    }
    path = _write_yaml(tmp_path / "settings3.yaml", payload)
    report = validate_settings(path, profile="default")
    assert report.has_errors()
