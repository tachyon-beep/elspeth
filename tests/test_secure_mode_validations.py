from __future__ import annotations

import pytest

from elspeth.core.security.secure_mode import (
    SecureMode,
    get_path_contained_sink_types,
    validate_sink_config,
)


def test_path_contained_sink_types_env_merge(monkeypatch) -> None:
    monkeypatch.setenv("ELSPETH_PATH_CONTAINED_SINKS", "csv, parquet , new_sink")
    types = get_path_contained_sink_types()
    assert "csv" in types and "parquet" in types and "new_sink" in types


def test_validate_sink_requires_allowed_base_in_strict() -> None:
    cfg = {"type": "csv", "sanitize_formulas": True}
    with pytest.raises(ValueError):
        validate_sink_config(cfg, mode=SecureMode.STRICT)


def test_validate_sink_sanitization_required_in_strict() -> None:
    cfg = {"type": "csv", "sanitize_formulas": False, "allowed_base_path": "/tmp"}
    with pytest.raises(ValueError):
        validate_sink_config(cfg, mode=SecureMode.STRICT)

