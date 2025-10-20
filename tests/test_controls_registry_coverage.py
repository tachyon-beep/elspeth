"""Coverage tests for controls registry to reach 80% coverage.

Focuses on uncovered lines:
- Lines 39-42: Single-parameter factory backward compatibility (rate limiter)
- Lines 59-62: Single-parameter factory backward compatibility (cost tracker)
- Lines 127, 132, 134: Rate limiter validation edge cases
- Lines 166, 171, 173: Cost tracker validation edge cases
- Lines 178-179, 188-191: ConfigurationError conversion
"""

from __future__ import annotations

import pytest

from elspeth.core.controls.registry import (
    create_cost_tracker,
    create_rate_limiter,
    register_cost_tracker,
    register_rate_limiter,
    validate_cost_tracker,
    validate_rate_limiter,
)
from elspeth.core.validation.base import ConfigurationError


def test_register_rate_limiter_single_param_factory():
    """Test backward compatibility with single-parameter factory - lines 39-42."""
    # Old-style factory (only options parameter)
    def old_factory(options):
        from elspeth.core.controls.rate_limit import NoopRateLimiter
        return NoopRateLimiter()

    # Should work with old-style factory
    register_rate_limiter("test_old_rl", old_factory, schema={"type": "object"})

    # Should be able to create with it (need security_level)
    result = create_rate_limiter({
        "name": "test_old_rl",
        "security_level": "internal",
        "options": {}
    })
    assert result is not None


def test_register_rate_limiter_two_param_factory():
    """Test new-style factory with context parameter."""
    # New-style factory (options and context)
    def new_factory(options, context):
        from elspeth.core.controls.rate_limit import NoopRateLimiter
        limiter = NoopRateLimiter()
        return limiter

    register_rate_limiter("test_new_rl", new_factory, schema={"type": "object"})

    result = create_rate_limiter({
        "name": "test_new_rl",
        "security_level": "internal",
        "options": {}
    })
    assert result is not None


def test_register_cost_tracker_single_param_factory():
    """Test backward compatibility with single-parameter factory - lines 59-62."""
    # Old-style factory (only options parameter)
    def old_factory(options):
        from elspeth.core.controls.cost_tracker import NoopCostTracker
        return NoopCostTracker()

    register_cost_tracker("test_old_ct", old_factory, schema={"type": "object"})

    result = create_cost_tracker({
        "name": "test_old_ct",
        "security_level": "internal",
        "options": {}
    })
    assert result is not None


def test_register_cost_tracker_two_param_factory():
    """Test new-style factory with context parameter."""
    # New-style factory (options and context)
    def new_factory(options, context):
        from elspeth.core.controls.cost_tracker import NoopCostTracker
        tracker = NoopCostTracker()
        return tracker

    register_cost_tracker("test_new_ct", new_factory, schema={"type": "object"})

    result = create_cost_tracker({
        "name": "test_new_ct",
        "security_level": "internal",
        "options": {}
    })
    assert result is not None


def test_validate_rate_limiter_none_definition():
    """Test validation with None definition - line 122."""
    # Should not raise for None (optional plugin)
    validate_rate_limiter(None)


def test_validate_rate_limiter_empty_definition():
    """Test validation with empty dict - line 122."""
    # Should not raise for empty dict
    validate_rate_limiter({})


def test_validate_rate_limiter_missing_name():
    """Test validation with missing name field - lines 127."""
    with pytest.raises(ConfigurationError, match="missing 'name'/'plugin' field"):
        validate_rate_limiter({"options": {}})


def test_validate_rate_limiter_invalid_name_type():
    """Test validation with non-string name - line 127."""
    with pytest.raises(ConfigurationError, match="name is not a string"):
        validate_rate_limiter({"name": 123, "options": {}})


def test_validate_rate_limiter_none_options():
    """Test validation with None options - lines 132."""
    # Should treat None as empty dict
    try:
        validate_rate_limiter({"name": "noop", "options": None})
    except ConfigurationError as exc:
        # May fail on unknown plugin, but shouldn't fail on None options
        assert "options" not in str(exc)


def test_validate_rate_limiter_invalid_options_type():
    """Test validation with non-dict options - line 134."""
    with pytest.raises(ConfigurationError, match="options must be a mapping"):
        validate_rate_limiter({"name": "noop", "options": "string"})


def test_validate_rate_limiter_unknown_plugin():
    """Test validation with unknown plugin raises ConfigurationError - line 152."""
    with pytest.raises(ConfigurationError):
        validate_rate_limiter({
            "name": "totally_unknown_plugin",
            "options": {},
            "security_level": "internal"
        })


def test_validate_cost_tracker_none_definition():
    """Test validation with None definition - line 161."""
    # Should not raise for None (optional plugin)
    validate_cost_tracker(None)


def test_validate_cost_tracker_empty_definition():
    """Test validation with empty dict - line 161."""
    # Should not raise for empty dict
    validate_cost_tracker({})


def test_validate_cost_tracker_missing_name():
    """Test validation with missing name field - line 166."""
    with pytest.raises(ConfigurationError, match="missing 'name'/'plugin' field"):
        validate_cost_tracker({"options": {}})


def test_validate_cost_tracker_invalid_name_type():
    """Test validation with non-string name - line 166."""
    with pytest.raises(ConfigurationError, match="name is not a string"):
        validate_cost_tracker({"name": 123, "options": {}})


def test_validate_cost_tracker_none_options():
    """Test validation with None options - line 171."""
    # Should treat None as empty dict
    try:
        validate_cost_tracker({"name": "noop", "options": None})
    except ConfigurationError as exc:
        # May fail on unknown plugin, but shouldn't fail on None options
        assert "options" not in str(exc)


def test_validate_cost_tracker_invalid_options_type():
    """Test validation with non-dict options - line 173."""
    with pytest.raises(ConfigurationError, match="options must be a mapping"):
        validate_cost_tracker({"name": "noop", "options": "string"})


def test_validate_cost_tracker_unknown_plugin():
    """Test validation with unknown plugin raises ConfigurationError - line 191."""
    with pytest.raises(ConfigurationError):
        validate_cost_tracker({
            "name": "totally_unknown_plugin",
            "options": {},
            "security_level": "internal"
        })


def test_validate_rate_limiter_conflicting_security_levels():
    """Test validation with conflicting security levels - line 140."""
    with pytest.raises(ConfigurationError, match="rate_limiter:noop"):
        validate_rate_limiter({
            "name": "noop",
            "security_level": "public",
            "options": {"security_level": "restricted"}  # Conflict
        })


def test_validate_cost_tracker_conflicting_security_levels():
    """Test validation with conflicting security levels - line 179."""
    with pytest.raises(ConfigurationError, match="cost_tracker:noop"):
        validate_cost_tracker({
            "name": "noop",
            "security_level": "public",
            "options": {"security_level": "restricted"}  # Conflict
        })


def test_create_rate_limiter_none():
    """Test create with None returns None (optional plugin pattern)."""
    result = create_rate_limiter(None)
    assert result is None


def test_create_cost_tracker_none():
    """Test create with None returns None (optional plugin pattern)."""
    result = create_cost_tracker(None)
    assert result is None


def test_backward_compatibility_dicts_exposed():
    """Test that _rate_limiters and _cost_trackers are exposed for backward compatibility."""
    from elspeth.core.controls.registry import _cost_trackers, _rate_limiters

    # Should be dict-like
    assert isinstance(_rate_limiters, dict)
    assert isinstance(_cost_trackers, dict)

    # Should contain default plugins
    assert "noop" in _rate_limiters
    assert "noop" in _cost_trackers
