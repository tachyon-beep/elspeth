"""Tests for common registry schemas."""


from elspeth.core.registry.schemas import (
    ARTIFACT_DESCRIPTOR_SCHEMA,
    ARTIFACTS_SECTION_SCHEMA,
    DETERMINISM_LEVEL_SCHEMA,
    ON_ERROR_ENUM,
    SECURITY_LEVEL_SCHEMA,
    with_artifact_properties,
    with_error_handling,
    with_security_properties,
)

# Schema constant tests


def test_on_error_enum():
    """ON_ERROR_ENUM has correct structure."""
    assert ON_ERROR_ENUM == {"type": "string", "enum": ["abort", "skip"]}


def test_security_level_schema():
    """SECURITY_LEVEL_SCHEMA has correct structure."""
    assert SECURITY_LEVEL_SCHEMA == {"type": "string"}


def test_determinism_level_schema():
    """DETERMINISM_LEVEL_SCHEMA has correct structure."""
    assert DETERMINISM_LEVEL_SCHEMA == {"type": "string"}


def test_artifact_descriptor_schema():
    """ARTIFACT_DESCRIPTOR_SCHEMA has required fields."""
    assert ARTIFACT_DESCRIPTOR_SCHEMA["type"] == "object"
    assert "name" in ARTIFACT_DESCRIPTOR_SCHEMA["required"]
    assert "type" in ARTIFACT_DESCRIPTOR_SCHEMA["required"]
    assert "properties" in ARTIFACT_DESCRIPTOR_SCHEMA


def test_artifacts_section_schema():
    """ARTIFACTS_SECTION_SCHEMA has produces and consumes."""
    assert ARTIFACTS_SECTION_SCHEMA["type"] == "object"
    assert "produces" in ARTIFACTS_SECTION_SCHEMA["properties"]
    assert "consumes" in ARTIFACTS_SECTION_SCHEMA["properties"]


# with_security_properties tests


def test_with_security_properties_adds_properties():
    """Add security properties to schema."""
    schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
    }

    enhanced = with_security_properties(schema)

    assert "security_level" in enhanced["properties"]
    assert "determinism_level" in enhanced["properties"]
    assert "path" in enhanced["properties"]  # original preserved


def test_with_security_properties_require_security():
    """Add security_level to required fields."""
    schema = {
        "type": "object",
        "properties": {},
        "required": ["path"],
    }

    enhanced = with_security_properties(schema, require_security=True)

    assert "security_level" in enhanced["required"]
    assert "path" in enhanced["required"]  # original preserved


def test_with_security_properties_require_determinism():
    """Add determinism_level to required fields."""
    schema = {
        "type": "object",
        "properties": {},
    }

    enhanced = with_security_properties(schema, require_determinism=True)

    assert "determinism_level" in enhanced.get("required", [])


def test_with_security_properties_no_duplicate_required():
    """Don't duplicate required fields."""
    schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    enhanced = with_security_properties(schema, require_security=True)
    enhanced = with_security_properties(enhanced, require_security=True)

    # Should only appear once
    assert enhanced["required"].count("security_level") == 1


def test_with_security_properties_creates_copy():
    """Create copy, don't modify original."""
    schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
    }

    enhanced = with_security_properties(schema)

    assert "security_level" not in schema["properties"]
    assert "security_level" in enhanced["properties"]


# with_artifact_properties tests


def test_with_artifact_properties_adds_artifacts():
    """Add artifact section to schema."""
    schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
    }

    enhanced = with_artifact_properties(schema)

    assert "artifacts" in enhanced["properties"]
    assert enhanced["properties"]["artifacts"] == ARTIFACTS_SECTION_SCHEMA


def test_with_artifact_properties_creates_copy():
    """Create copy, don't modify original."""
    schema = {
        "type": "object",
        "properties": {},
    }

    enhanced = with_artifact_properties(schema)

    assert "artifacts" not in schema["properties"]
    assert "artifacts" in enhanced["properties"]


# with_error_handling tests


def test_with_error_handling_adds_on_error():
    """Add on_error property to schema."""
    schema = {
        "type": "object",
        "properties": {},
    }

    enhanced = with_error_handling(schema)

    assert "on_error" in enhanced["properties"]
    assert enhanced["properties"]["on_error"] == ON_ERROR_ENUM


def test_with_error_handling_creates_copy():
    """Create copy, don't modify original."""
    schema = {
        "type": "object",
        "properties": {},
    }

    enhanced = with_error_handling(schema)

    assert "on_error" not in schema["properties"]
    assert "on_error" in enhanced["properties"]


# Composition tests


def test_schema_builders_composition():
    """Schema builders can be composed."""
    schema = {"type": "object", "properties": {}}

    enhanced = with_security_properties(schema, require_security=True)
    enhanced = with_artifact_properties(enhanced)
    enhanced = with_error_handling(enhanced)

    assert "security_level" in enhanced["properties"]
    assert "determinism_level" in enhanced["properties"]
    assert "artifacts" in enhanced["properties"]
    assert "on_error" in enhanced["properties"]
    assert "security_level" in enhanced["required"]
