from types import SimpleNamespace

import pytest

from elspeth.core.controls import registry as controls_registry
from elspeth.core.validation import ConfigurationError


def test_create_rate_limiter_validates_schema():
    with pytest.raises(ConfigurationError):
        controls_registry.create_rate_limiter(
            {
                "plugin": "fixed_window",
                "options": {"requests": 0, "per_seconds": 0},
            }
        )


def test_validate_rate_limiter_unknown():
    with pytest.raises(ConfigurationError):
        controls_registry.validate_rate_limiter({"plugin": "missing"})


def test_register_custom_rate_limiter(monkeypatch):
    created = SimpleNamespace()

    def factory(options, context):
        assert options == {"tag": "blue"}
        return created

    controls_registry.register_rate_limiter("custom", factory, declared_security_level="OFFICIAL")
    limiter = controls_registry.create_rate_limiter(
        {"plugin": "custom", "determinism_level": "guaranteed", "options": {"tag": "blue"}}
    )
    assert limiter is created


def test_create_cost_tracker_validates_schema():
    with pytest.raises(ConfigurationError):
        controls_registry.create_cost_tracker(
            {
                "plugin": "fixed_price",
                "options": {"prompt_token_price": -1, "completion_token_price": 0.0},
            }
        )


def test_register_custom_cost_tracker():
    created = SimpleNamespace()

    def factory(options, context):
        assert options == {"tier": "gold"}
        return created

    controls_registry.register_cost_tracker("custom_cost", factory, declared_security_level="OFFICIAL")
    tracker = controls_registry.create_cost_tracker(
        {"plugin": "custom_cost", "determinism_level": "guaranteed", "options": {"tier": "gold"}}
    )
    assert tracker is created


def test_create_helpers_return_none_for_missing_definitions():
    assert controls_registry.create_rate_limiter(None) is None
    assert controls_registry.create_cost_tracker(None) is None
    controls_registry.validate_rate_limiter(None)
    controls_registry.validate_cost_tracker(None)


def test_create_cost_tracker_unknown_plugin():
    with pytest.raises(ValueError):
        controls_registry.create_cost_tracker({"plugin": "unknown"})


def test_validate_cost_tracker_success():
    assert (
        controls_registry.validate_cost_tracker(
            {
                "plugin": "noop",
            }
        )
        is None
    )
    assert (
        controls_registry.validate_cost_tracker(
            {
                "plugin": "fixed_price",
                "options": {"prompt_token_price": 0.1, "completion_token_price": 0.05},
            }
        )
        is None
    )


def test_create_rate_limiter_unknown_plugin():
    with pytest.raises(ValueError):
        controls_registry.create_rate_limiter({"plugin": "unknown"})


def test_validate_rate_limiter_success():
    assert (
        controls_registry.validate_rate_limiter(
            {
                "plugin": "noop",
            }
        )
        is None
    )
