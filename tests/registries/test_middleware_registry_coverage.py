from __future__ import annotations

from typing import Any
import pytest

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.registries.middleware import (
    create_middleware,
    create_middlewares,
    register_middleware,
    validate_middleware_definition,
)


class _DummyMiddleware:
    def __init__(self, **_opts: Any) -> None:  # noqa: D401
        return None


def test_middleware_definition_validation_and_creation():
    register_middleware(
        "dummy",
        lambda options, context: _DummyMiddleware(**options),
        schema={
            "type": "object",
            "properties": {"tag": {"type": "string"}},
            "required": ["tag"],
            "additionalProperties": False,
        },
    )

    # Valid definition should pass
    validate_middleware_definition(
        {"name": "dummy", "security_level": "OFFICIAL", "determinism_level": "guaranteed", "options": {"tag": "x"}}
    )

    # Optional batch creation with None input returns empty list
    assert create_middlewares(None) == []

    # Create single middleware using controls pattern
    parent = PluginContext(plugin_name="suite", plugin_kind="suite", security_level="OFFICIAL")
    mw = create_middleware(
        {"name": "dummy", "security_level": "OFFICIAL", "determinism_level": "guaranteed", "options": {"tag": "x"}},
        parent_context=parent,
    )
    assert mw is not None


def test_middleware_definition_errors():
    from elspeth.core.validation.base import ConfigurationError

    # Unknown plugin name
    with pytest.raises(ConfigurationError):
        validate_middleware_definition({"name": "does_not_exist", "options": {}})

    # Options must be a mapping
    register_middleware("dummy2", lambda options, context: _DummyMiddleware(**options))
    with pytest.raises(ConfigurationError):
        validate_middleware_definition({"name": "dummy2", "options": "oops"})
