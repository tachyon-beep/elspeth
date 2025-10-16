"""Schema definitions and validation helpers for experiment configs."""

from __future__ import annotations

from typing import Any, Mapping

from elspeth.core.validation.base import ConfigurationError, validate_schema

_PLUGIN_DEF_SCHEMA = {
    """Base schema for plugin definitions referencing a name and options.""" "type": "object",
    "properties": {
        "name": {"type": "string"},
        "options": {"type": "object"},
    },
    "required": ["name"],
    "additionalProperties": True,
}


EXPERIMENT_CONFIG_SCHEMA = {
    """JSON schema describing individual experiment configuration entries.""" "type": "object",
    "required": ["name", "temperature", "max_tokens", "enabled"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "hypothesis": {"type": "string"},
        "author": {"type": "string"},
        "temperature": {"type": "number", "minimum": 0, "maximum": 2},
        "max_tokens": {"type": "integer", "minimum": 1, "maximum": 8192},
        "enabled": {"type": "boolean"},
        "is_baseline": {"type": "boolean"},
        "tags": {
            "type": "array",
            "items": {"type": "string"},
        },
        "prompt_pack": {"type": "string"},
        "security_level": {"type": "string"},
        "validation_plugins": {
            "type": "array",
            "items": _PLUGIN_DEF_SCHEMA,
        },
    },
    "additionalProperties": True,
}


def validate_experiment_config(config: Mapping[str, Any]) -> None:
    """Validate experiment configuration dictionaries against the JSON schema."""

    errors = list(validate_schema(config, EXPERIMENT_CONFIG_SCHEMA, context="experiment_config"))
    if errors:
        message = "\n".join(msg.format() for msg in errors)
        raise ConfigurationError(message)
