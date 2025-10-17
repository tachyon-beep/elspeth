"""JSON schemas used by validation helpers."""

from __future__ import annotations

PLUGIN_REFERENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "plugin": {"type": "string"},
        "options": {"type": "object"},
    },
    "required": ["plugin"],
    "additionalProperties": True,
}

MIDDLEWARE_DEF_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "plugin": {"type": "string"},
        "options": {"type": "object"},
    },
    "anyOf": [
        {"required": ["name"]},
        {"required": ["plugin"]},
    ],
    "additionalProperties": True,
}

PLUGIN_DEF_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "options": {"type": "object"},
    },
    "required": ["name"],
    "additionalProperties": True,
}

SETTINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "datasource": PLUGIN_REFERENCE_SCHEMA,
        "llm": PLUGIN_REFERENCE_SCHEMA,
        "sinks": {
            "type": "array",
            "items": PLUGIN_REFERENCE_SCHEMA,
        },
        "prompt_packs": {"type": "object"},
        "suite_defaults": {"type": "object"},
        "retry": {"type": "object"},
        "checkpoint": {"type": "object"},
        "concurrency": {"type": "object"},
        "early_stop": {"type": "object"},
        "early_stop_plugins": {"type": "array", "items": PLUGIN_DEF_SCHEMA},
        "validation_plugins": {"type": "array", "items": PLUGIN_DEF_SCHEMA},
    },
    "required": ["datasource", "llm"],
    "additionalProperties": True,
}

EXPERIMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "temperature": {"type": "number"},
        "max_tokens": {"type": "integer", "minimum": 1},
        "enabled": {"type": "boolean"},
        "is_baseline": {"type": "boolean"},
        "prompt_pack": {"type": "string"},
        "criteria": {"type": "array"},
        "row_plugins": {"type": "array", "items": PLUGIN_DEF_SCHEMA},
        "aggregator_plugins": {"type": "array", "items": PLUGIN_DEF_SCHEMA},
        "baseline_plugins": {"type": "array", "items": PLUGIN_DEF_SCHEMA},
        "validation_plugins": {"type": "array", "items": PLUGIN_DEF_SCHEMA},
        "llm_middlewares": {"type": "array", "items": MIDDLEWARE_DEF_SCHEMA},
        "sinks": {"type": "array", "items": PLUGIN_REFERENCE_SCHEMA},
        "rate_limiter": {"type": "object"},
        "cost_tracker": {"type": "object"},
        "prompt_defaults": {"type": "object"},
        "concurrency": {"type": "object"},
        "early_stop_plugins": {"type": "array", "items": PLUGIN_DEF_SCHEMA},
    },
    "required": ["temperature", "max_tokens"],
    "additionalProperties": True,
}

__all__ = [
    "PLUGIN_REFERENCE_SCHEMA",
    "MIDDLEWARE_DEF_SCHEMA",
    "PLUGIN_DEF_SCHEMA",
    "SETTINGS_SCHEMA",
    "EXPERIMENT_SCHEMA",
]
