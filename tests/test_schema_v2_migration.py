"""
Tests for Pydantic v2 migration of schema validation.

This test suite verifies that the DataFrameSchema system correctly uses
Pydantic v2 patterns and APIs.
"""

import pandas as pd
import pytest

from elspeth.core.schema import (
    DataFrameSchema,
    SchemaCompatibilityError,
    infer_schema_from_dataframe,
    schema_from_config,
    validate_dataframe,
    validate_row,
    validate_schema_compatibility,
)


class TestPydanticV2ModelConfig:
    """Test that DataFrameSchema uses Pydantic v2 model_config."""

    def test_dataframe_schema_has_model_config(self):
        """Verify DataFrameSchema has model_config attribute (v2 pattern)."""
        assert hasattr(DataFrameSchema, "model_config")
        assert isinstance(DataFrameSchema.model_config, dict)

    def test_model_config_has_extra_allow(self):
        """Verify extra='allow' is set in model_config."""
        assert DataFrameSchema.model_config["extra"] == "allow"

    def test_model_config_has_arbitrary_types_allowed(self):
        """Verify arbitrary_types_allowed is set in model_config."""
        assert DataFrameSchema.model_config["arbitrary_types_allowed"] is True

    def test_dynamically_created_schema_inherits_config(self):
        """Verify schemas created with create_model inherit model_config."""
        schema = schema_from_config({"name": "str", "age": "int"})
        assert hasattr(schema, "model_config")
        assert schema.model_config["extra"] == "allow"


class TestPydanticV2ValidationAPI:
    """Test that validation uses Pydantic v2 model_validate API."""

    def test_model_validate_method_exists(self):
        """Verify schemas have model_validate method (v2 API)."""
        schema = schema_from_config({"name": "str", "age": "int"})
        assert hasattr(schema, "model_validate")
        assert callable(schema.model_validate)

    def test_model_validate_with_valid_data(self):
        """Test model_validate accepts valid data."""
        schema = schema_from_config({"name": "str", "age": "int"})
        instance = schema.model_validate({"name": "Alice", "age": 30})
        assert instance.name == "Alice"
        assert instance.age == 30

    def test_model_validate_with_extra_fields(self):
        """Test model_validate allows extra fields (extra='allow')."""
        schema = schema_from_config({"name": "str"})
        instance = schema.model_validate({"name": "Bob", "extra_field": "value"})
        assert instance.name == "Bob"
        assert instance.extra_field == "value"  # Should be allowed

    def test_model_validate_rejects_invalid_data(self):
        """Test model_validate raises ValidationError for invalid data."""
        from pydantic import ValidationError

        schema = schema_from_config({"name": "str", "age": "int"})
        with pytest.raises(ValidationError):
            schema.model_validate({"name": "Charlie", "age": "not_an_int"})


class TestOptionalFieldHandling:
    """Test that optional fields use Optional[T] type hints in v2."""

    def test_optional_field_accepts_none(self):
        """Test optional fields accept None values."""
        schema = schema_from_config({"required": "str", "optional": {"type": "int", "required": False}})
        valid, violation = validate_row({"required": "test"}, schema)
        assert valid is True
        assert violation is None

    def test_optional_field_accepts_value(self):
        """Test optional fields accept actual values."""
        schema = schema_from_config({"required": "str", "optional": {"type": "int", "required": False}})
        valid, violation = validate_row({"required": "test", "optional": 42}, schema)
        assert valid is True

    def test_required_field_missing_fails(self):
        """Test missing required field fails validation."""
        schema = schema_from_config({"required": "str"})
        valid, violation = validate_row({}, schema, row_index=0)
        assert valid is False
        assert violation is not None
        assert "required" in str(violation.errors)

    def test_inferred_optional_fields(self):
        """Test schema inference with optional columns."""
        df = pd.DataFrame({"id": [1, 2, 3], "name": ["A", "B", "C"], "score": [95, 87, 92]})
        schema = infer_schema_from_dataframe(
            df,
            schema_name="TestSchema",
            required_columns=["id", "name"],  # score is optional
        )

        # Should accept row missing optional 'score'
        valid, _ = validate_row({"id": 4, "name": "D"}, schema)
        assert valid is True


class TestTypeCoercionBehavior:
    """Test Pydantic v2 type coercion rules."""

    def test_string_to_int_coercion(self):
        """Test v2 allows string → int coercion by default."""
        schema = schema_from_config({"score": "int"})
        valid, _ = validate_row({"score": "95"}, schema)
        assert valid is True

    def test_invalid_string_to_int_fails(self):
        """Test invalid string → int conversion fails."""
        schema = schema_from_config({"score": "int"})
        valid, violation = validate_row({"score": "not_a_number"}, schema)
        assert valid is False
        assert violation is not None

    def test_int_to_float_widening(self):
        """Test int → float widening is allowed."""
        schema = schema_from_config({"value": "float"})
        valid, _ = validate_row({"value": 42}, schema)
        assert valid is True


class TestSchemaCompatibility:
    """Test schema compatibility validation with v2."""

    def test_compatible_schemas_pass(self):
        """Test compatible schemas pass validation."""
        datasource_schema = schema_from_config({"id": "int", "name": "str", "score": "int"})
        plugin_schema = schema_from_config({"id": "int", "score": "int"})

        # Should not raise
        validate_schema_compatibility(datasource_schema, plugin_schema, plugin_name="test_plugin")

    def test_missing_required_column_fails(self):
        """Test missing required column raises SchemaCompatibilityError."""
        datasource_schema = schema_from_config({"id": "int"})
        plugin_schema = schema_from_config({"id": "int", "name": "str"})

        with pytest.raises(SchemaCompatibilityError) as exc_info:
            validate_schema_compatibility(datasource_schema, plugin_schema, plugin_name="test_plugin")

        assert "name" in str(exc_info.value)
        assert "test_plugin" in str(exc_info.value)

    def test_optional_column_missing_currently_fails(self):
        """Test missing optional column currently raises error.

        Note: This is a known limitation - validate_schema_compatibility
        does not yet distinguish between required and optional fields.
        It treats all plugin schema fields as required.

        This test documents the current behavior. Future enhancement
        could check field.is_required() to skip optional fields.
        """
        datasource_schema = schema_from_config({"id": "int"})
        plugin_schema = schema_from_config({"id": "int", "optional_name": {"type": "str", "required": False}})

        # Currently raises even for optional fields (known limitation)
        with pytest.raises(SchemaCompatibilityError) as exc_info:
            validate_schema_compatibility(datasource_schema, plugin_schema, plugin_name="test_plugin")

        assert "optional_name" in str(exc_info.value)


class TestErrorMessageFormat:
    """Test that error messages follow v2 format."""

    def test_validation_error_structure(self):
        """Test SchemaViolation captures v2 error format."""
        schema = schema_from_config({"name": "str", "age": "int"})
        valid, violation = validate_row({"name": "test", "age": "invalid"}, schema, row_index=5)

        assert valid is False
        assert violation is not None
        assert violation.row_index == 5
        assert len(violation.errors) > 0

        # Check error dict structure
        error = violation.errors[0]
        assert "field" in error
        assert "type" in error
        assert "message" in error
        assert error["field"] == "age"

    def test_error_dict_conversion(self):
        """Test SchemaViolation.to_dict() includes all fields."""
        schema = schema_from_config({"value": "int"})
        valid, violation = validate_row({"value": "bad"}, schema, row_index=10)

        error_dict = violation.to_dict()
        assert error_dict["row_index"] == 10
        assert error_dict["schema_name"] == schema.__name__
        assert "timestamp" in error_dict
        assert "validation_errors" in error_dict
        assert "malformed_data" in error_dict


class TestDataFrameValidation:
    """Test DataFrame-level validation with v2."""

    def test_validate_dataframe_all_valid(self):
        """Test validating DataFrame with all valid rows."""
        df = pd.DataFrame({"name": ["Alice", "Bob", "Charlie"], "age": [30, 25, 35]})
        schema = schema_from_config({"name": "str", "age": "int"})

        valid, violations = validate_dataframe(df, schema)
        assert valid is True
        assert len(violations) == 0

    def test_validate_dataframe_with_errors(self):
        """Test validating DataFrame with invalid rows."""
        df = pd.DataFrame({"name": ["Alice", "Bob", "Charlie"], "age": [30, "invalid", 35]})
        schema = schema_from_config({"name": "str", "age": "int"})

        valid, violations = validate_dataframe(df, schema, early_stop=False)
        assert valid is False
        assert len(violations) == 1
        assert violations[0].row_index == 1  # Bob's row

    def test_validate_dataframe_early_stop(self):
        """Test early_stop parameter stops on first error."""
        df = pd.DataFrame({"value": ["1", "bad", "also_bad"]})
        schema = schema_from_config({"value": "int"})

        valid, violations = validate_dataframe(df, schema, early_stop=True)
        assert valid is False
        assert len(violations) == 1  # Should stop after first error


class TestBackwardsCompatibility:
    """Test that v2 migration maintains backwards compatibility."""

    def test_existing_simple_schema_works(self):
        """Test simple schemas from config still work."""
        schema = schema_from_config({"APPID": "str", "question": "str", "expected_answer": "str"})

        valid, _ = validate_row({"APPID": "A1", "question": "What?", "expected_answer": "Answer"}, schema)
        assert valid is True

    def test_schema_inference_works(self):
        """Test DataFrame schema inference still works."""
        df = pd.DataFrame({"id": [1, 2, 3], "value": [10.5, 20.3, 30.1]})
        schema = infer_schema_from_dataframe(df, "InferredSchema")

        assert hasattr(schema, "__annotations__")
        assert "id" in schema.__annotations__
        assert "value" in schema.__annotations__

    def test_constraint_validation_works(self):
        """Test field constraints (min, max) still work."""
        schema = schema_from_config({"score": {"type": "int", "min": 0, "max": 100}})

        # Valid score
        valid, _ = validate_row({"score": 50}, schema)
        assert valid is True

        # Score too high
        valid, violation = validate_row({"score": 150}, schema)
        assert valid is False
        assert "score" in str(violation.errors)
