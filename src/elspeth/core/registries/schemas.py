"""Common JSON schemas for plugin validation.

This module centralizes schema definitions that were previously
duplicated across multiple registry files.
"""

from typing import Any

# Standard enums
ON_ERROR_ENUM = {"type": "string", "enum": ["abort", "skip"]}

# Security and determinism schemas
SECURITY_LEVEL_SCHEMA = {"type": "string"}
DETERMINISM_LEVEL_SCHEMA = {"type": "string"}

# Artifact descriptor schema (used by sinks)
ARTIFACT_DESCRIPTOR_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "type": {"type": "string"},
        "schema_id": {"type": "string"},
        "persist": {"type": "boolean"},
        "alias": {"type": "string"},
        "security_level": {"type": "string"},
        "determinism_level": {"type": "string"},
    },
    "required": ["name", "type"],
    "additionalProperties": False,
}

# Artifacts section schema (produces/consumes)
ARTIFACTS_SECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "produces": {
            "type": "array",
            "items": ARTIFACT_DESCRIPTOR_SCHEMA,
        },
        "consumes": {
            "type": "array",
            "items": {
                "oneOf": [
                    {"type": "string"},
                    {
                        "type": "object",
                        "properties": {
                            "token": {"type": "string"},
                            "mode": {"type": "string", "enum": ["single", "all"]},
                        },
                        "required": ["token"],
                        "additionalProperties": False,
                    },
                ]
            },
        },
    },
    "additionalProperties": False,
}


def with_security_properties(
    schema: dict[str, Any],
    *,
    require_security: bool = False,
    require_determinism: bool = False,
) -> dict[str, Any]:
    """
    Add standard security and determinism properties to a schema.

    Creates a copy of the schema with security_level and determinism_level
    properties added. Optionally marks them as required.

    Args:
        schema: Base schema dictionary
        require_security: Add security_level to required fields
        require_determinism: Add determinism_level to required fields

    Returns:
        Schema with security properties added (new dictionary)

    Example:
        >>> schema = {"type": "object", "properties": {"path": {"type": "string"}}}
        >>> enhanced = with_security_properties(schema, require_security=True)
        >>> print(enhanced["properties"].keys())
        dict_keys(['path', 'security_level', 'determinism_level'])
        >>> print(enhanced["required"])
        ['security_level']
    """
    # Create a shallow copy of the schema
    result = dict(schema)
    # Create a copy of properties to avoid mutating the original
    result["properties"] = dict(schema.get("properties", {}))
    result["properties"]["security_level"] = SECURITY_LEVEL_SCHEMA
    result["properties"]["determinism_level"] = DETERMINISM_LEVEL_SCHEMA

    if require_security or require_determinism:
        # Create a copy of required list to avoid mutating the original
        required: list[str] = list(schema.get("required", []))
        if require_security and "security_level" not in required:
            required.append("security_level")
        if require_determinism and "determinism_level" not in required:
            required.append("determinism_level")
        result["required"] = required

    return result


def with_artifact_properties(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Add artifact section properties to a schema.

    Adds the standard artifacts section (produces/consumes) to a schema,
    typically used by sink plugins.

    Args:
        schema: Base schema dictionary

    Returns:
        Schema with artifacts property added (new dictionary)

    Example:
        >>> schema = {"type": "object", "properties": {}}
        >>> enhanced = with_artifact_properties(schema)
        >>> print("artifacts" in enhanced["properties"])
        True
    """
    # Create a shallow copy of the schema
    result = dict(schema)
    # Create a copy of properties to avoid mutating the original
    result["properties"] = dict(schema.get("properties", {}))
    result["properties"]["artifacts"] = ARTIFACTS_SECTION_SCHEMA
    return result


def with_error_handling(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Add on_error property to a schema.

    Adds the standard on_error enum property for error handling
    configuration.

    Args:
        schema: Base schema dictionary

    Returns:
        Schema with on_error property added (new dictionary)

    Example:
        >>> schema = {"type": "object", "properties": {}}
        >>> enhanced = with_error_handling(schema)
        >>> print(enhanced["properties"]["on_error"])
        {'type': 'string', 'enum': ['abort', 'skip']}
    """
    # Create a shallow copy of the schema
    result = dict(schema)
    # Create a copy of properties to avoid mutating the original
    result["properties"] = dict(schema.get("properties", {}))
    result["properties"]["on_error"] = ON_ERROR_ENUM
    return result


__all__ = [
    # Constants
    "ON_ERROR_ENUM",
    "SECURITY_LEVEL_SCHEMA",
    "DETERMINISM_LEVEL_SCHEMA",
    "ARTIFACT_DESCRIPTOR_SCHEMA",
    "ARTIFACTS_SECTION_SCHEMA",
    # Schema builders
    "with_security_properties",
    "with_artifact_properties",
    "with_error_handling",
]
