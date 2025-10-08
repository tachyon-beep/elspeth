"""Schema definitions and validation helpers for experiment configs."""

from __future__ import annotations

from typing import Mapping, Any

from dmp.core.validation import validate_schema, ConfigurationError


EXPERIMENT_CONFIG_SCHEMA = {
    "type": "object",
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
    },
    "additionalProperties": True,
}


def validate_experiment_config(config: Mapping[str, Any]) -> None:
    errors = list(validate_schema(config, EXPERIMENT_CONFIG_SCHEMA, context="experiment_config"))
    if errors:
        message = "\n".join(msg.format() for msg in errors)
        raise ConfigurationError(message)

