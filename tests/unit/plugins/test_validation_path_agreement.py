"""Test that pre-validation and engine-validation paths agree on rejection.

Pre-validation calls config_cls.from_dict(config) — Pydantic validators only.
Engine calls plugin_cls(config) — __init__() guards + Pydantic validators.

If a guard lives only in __init__, pre-validation says "valid" but the engine
rejects at runtime — a confusing false positive. All rejection logic should
live in the Pydantic config model so from_dict() catches it.

This parametric test feeds configs that SHOULD be rejected to BOTH paths and
asserts both reject. A failure means a guard was added to __init__ without a
corresponding model_validator — a regression of the H2 divergence bug.
"""

import pytest

from elspeth.plugins.infrastructure.config_base import PluginConfigError
from elspeth.plugins.infrastructure.validation import (
    validate_sink_config,
    validate_source_config,
    validate_transform_config,
)


def _make_observed_schema() -> dict:
    return {"mode": "observed"}


# ── Invalid configs that both paths must reject ─────────────────────────

_TRANSFORM_REJECTION_CASES = [
    pytest.param(
        "batch_stats",
        {
            "schema": _make_observed_schema(),
            "value_field": "amount",
            "group_by": "count",  # collides with aggregate output key
        },
        "group_by.*collides",
        id="batch_stats-group_by-collision",
    ),
    pytest.param(
        "batch_stats",
        {
            "schema": _make_observed_schema(),
            "value_field": "amount",
            "group_by": "mean",  # collides when compute_mean=True (default)
        },
        "group_by.*collides",
        id="batch_stats-group_by-mean-collision",
    ),
    pytest.param(
        "batch_stats",
        {
            "schema": _make_observed_schema(),
            "value_field": "amount",
            "group_by": "sum",  # collides with sum output key
        },
        "group_by.*collides",
        id="batch_stats-group_by-sum-collision",
    ),
]

_SOURCE_REJECTION_CASES = [
    pytest.param(
        "json",
        {
            "path": "/tmp/test.jsonl",
            "schema": _make_observed_schema(),
            "on_validation_failure": "quarantine",
            "data_key": "results",  # data_key + .jsonl extension = invalid
            # format is None (auto-detected from .jsonl extension)
        },
        "data_key.*not supported.*JSONL",
        id="json-data_key-auto-detected-jsonl",
    ),
    pytest.param(
        "json",
        {
            "path": "/tmp/test.json",
            "schema": _make_observed_schema(),
            "on_validation_failure": "quarantine",
            "format": "jsonl",
            "data_key": "results",  # explicit jsonl + data_key = invalid
        },
        "data_key.*not supported",
        id="json-data_key-explicit-jsonl",
    ),
]

_SINK_REJECTION_CASES = [
    pytest.param(
        "dataverse",
        {
            "schema": _make_observed_schema(),
            "environment_url": "https://myorg.crm.dynamics.com",
            "auth": {
                "method": "managed_identity",
            },
            "entity": "contacts",
            "field_mapping": {"name": "fullname", "email": "emailaddress1"},
            "alternate_key": "contactid",  # not in field_mapping values
        },
        "alternate_key.*not found in field_mapping",
        id="dataverse-alternate_key-missing",
    ),
]


# ── Parametric test: pre-validation path ────────────────────────────────


@pytest.mark.parametrize("transform_type,config,error_pattern", _TRANSFORM_REJECTION_CASES)
def test_prevalidation_rejects_invalid_transform(transform_type, config, error_pattern):
    """Pre-validation (from_dict path) rejects known-invalid transform configs."""
    errors = validate_transform_config(transform_type, config)
    assert errors, f"Expected pre-validation to reject {transform_type} config, but it passed"
    error_text = " ".join(e.message for e in errors)
    assert pytest.importorskip("re").search(error_pattern, error_text, flags=2), (
        f"Expected error matching {error_pattern!r}, got: {error_text}"
    )


@pytest.mark.parametrize("source_type,config,error_pattern", _SOURCE_REJECTION_CASES)
def test_prevalidation_rejects_invalid_source(source_type, config, error_pattern):
    """Pre-validation (from_dict path) rejects known-invalid source configs."""
    errors = validate_source_config(source_type, config)
    assert errors, f"Expected pre-validation to reject {source_type} config, but it passed"
    error_text = " ".join(e.message for e in errors)
    assert pytest.importorskip("re").search(error_pattern, error_text, flags=2), (
        f"Expected error matching {error_pattern!r}, got: {error_text}"
    )


@pytest.mark.parametrize("sink_type,config,error_pattern", _SINK_REJECTION_CASES)
def test_prevalidation_rejects_invalid_sink(sink_type, config, error_pattern):
    """Pre-validation (from_dict path) rejects known-invalid sink configs."""
    errors = validate_sink_config(sink_type, config)
    assert errors, f"Expected pre-validation to reject {sink_type} config, but it passed"
    error_text = " ".join(e.message for e in errors)
    assert pytest.importorskip("re").search(error_pattern, error_text, flags=2), (
        f"Expected error matching {error_pattern!r}, got: {error_text}"
    )


# ── Parametric test: engine-instantiation path ──────────────────────────


@pytest.mark.parametrize("transform_type,config,error_pattern", _TRANSFORM_REJECTION_CASES)
def test_engine_rejects_invalid_transform(transform_type, config, error_pattern):
    """Engine path (plugin_cls(config)) rejects known-invalid transform configs."""
    from elspeth.plugins.infrastructure.manager import PluginManager

    manager = PluginManager()
    manager.register_builtin_plugins()
    plugin_cls = manager.get_transform_by_name(transform_type)

    with pytest.raises((ValueError, PluginConfigError)):
        plugin_cls(config)


@pytest.mark.parametrize("source_type,config,error_pattern", _SOURCE_REJECTION_CASES)
def test_engine_rejects_invalid_source(source_type, config, error_pattern):
    """Engine path (plugin_cls(config)) rejects known-invalid source configs."""
    from elspeth.plugins.infrastructure.manager import PluginManager

    manager = PluginManager()
    manager.register_builtin_plugins()
    plugin_cls = manager.get_source_by_name(source_type)

    with pytest.raises((ValueError, PluginConfigError)):
        plugin_cls(config)


@pytest.mark.parametrize("sink_type,config,error_pattern", _SINK_REJECTION_CASES)
def test_engine_rejects_invalid_sink(sink_type, config, error_pattern):
    """Engine path (plugin_cls(config)) rejects known-invalid sink configs."""
    from elspeth.plugins.infrastructure.manager import PluginManager

    manager = PluginManager()
    manager.register_builtin_plugins()
    plugin_cls = manager.get_sink_by_name(sink_type)

    with pytest.raises((ValueError, PluginConfigError)):
        plugin_cls(config)
