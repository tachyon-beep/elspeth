"""Tests for PluginSchema in contracts module."""

import pytest


class TestPluginSchemaLocation:
    """Verify PluginSchema is importable from contracts."""

    def test_plugin_schema_importable_from_contracts(self) -> None:
        """PluginSchema should be importable from elspeth.contracts."""
        from elspeth.contracts import PluginSchema

        assert PluginSchema.model_config["extra"] == "ignore"
        assert PluginSchema.model_config["frozen"] is False
        assert PluginSchema.model_config["strict"] is False

    def test_schema_validation_error_importable_from_contracts(self) -> None:
        """SchemaValidationError should be importable from contracts."""
        from elspeth.contracts import SchemaValidationError

        error = SchemaValidationError("field", "message", "value")
        assert error.field == "field"
        assert error.message == "message"
        assert error.value == "value"

    def test_compatibility_result_importable_from_contracts(self) -> None:
        """CompatibilityResult should be importable from contracts."""
        from elspeth.contracts import CompatibilityResult

        result = CompatibilityResult(compatible=True)
        assert result.compatible is True

    def test_validate_row_importable_from_contracts(self) -> None:
        """validate_row should be importable from contracts."""
        from elspeth.contracts import PluginSchema, validate_row

        class TestSchema(PluginSchema):
            name: str

        errors = validate_row({"name": "test"}, TestSchema)
        assert errors == []

    def test_check_compatibility_importable_from_contracts(self) -> None:
        """check_compatibility should be importable from contracts."""
        from elspeth.contracts import PluginSchema, check_compatibility

        class SchemaA(PluginSchema):
            name: str

        class SchemaB(PluginSchema):
            name: str

        result = check_compatibility(SchemaA, SchemaB)
        assert result.compatible is True


class TestCompatibilityResultErrorMessage:
    """Tests for CompatibilityResult.error_message formatting logic."""

    def test_compatible_result_returns_none(self) -> None:
        from elspeth.contracts import CompatibilityResult

        result = CompatibilityResult(compatible=True)
        assert result.error_message is None

    def test_missing_fields_only(self) -> None:
        from elspeth.contracts import CompatibilityResult

        result = CompatibilityResult(compatible=False, missing_fields=("name", "age"))
        assert result.error_message == "Missing fields: name, age"

    def test_type_mismatches_only(self) -> None:
        from elspeth.contracts import CompatibilityResult

        result = CompatibilityResult(
            compatible=False,
            type_mismatches=(("score", "int", "str"),),
        )
        assert result.error_message == "Type mismatches: score (expected int, got str)"

    def test_constraint_mismatches_only(self) -> None:
        from elspeth.contracts import CompatibilityResult

        result = CompatibilityResult(
            compatible=False,
            constraint_mismatches=(("age", "must be positive"),),
        )
        assert result.error_message == "Constraint mismatches: age: must be positive"

    def test_extra_fields_only(self) -> None:
        from elspeth.contracts import CompatibilityResult

        result = CompatibilityResult(compatible=False, extra_fields=("secret", "debug"))
        assert result.error_message == "Extra fields forbidden by consumer: secret, debug"

    def test_combined_errors_joined_with_semicolon(self) -> None:
        """When multiple error categories exist, they're joined with '; '."""
        from elspeth.contracts import CompatibilityResult

        result = CompatibilityResult(
            compatible=False,
            missing_fields=("name",),
            type_mismatches=(("age", "int", "str"),),
            constraint_mismatches=(("score", "out of range"),),
            extra_fields=("debug",),
        )
        msg = result.error_message
        assert msg is not None
        parts = msg.split("; ")
        assert len(parts) == 4
        assert parts[0] == "Missing fields: name"
        assert parts[1] == "Type mismatches: age (expected int, got str)"
        assert parts[2] == "Constraint mismatches: score: out of range"
        assert parts[3] == "Extra fields forbidden by consumer: debug"

    def test_incompatible_with_no_details_returns_empty_string(self) -> None:
        """Edge case: compatible=False but no error details produces empty string."""
        from elspeth.contracts import CompatibilityResult

        result = CompatibilityResult(compatible=False)
        assert result.error_message == ""


class TestPluginSchemaNotInOldLocation:
    """Verify plugins/schemas.py has been deleted."""

    def test_old_import_path_removed(self) -> None:
        """Importing from plugins.schemas should fail - module deleted."""

        with pytest.raises(ModuleNotFoundError):
            from elspeth.plugins.schemas import (  # type: ignore[import-not-found]
                PluginSchema,  # noqa: F401
            )
