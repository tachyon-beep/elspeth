from typing import Optional

import pandas as pd
import pytest

from elspeth.core.base.schema.base import DataFrameSchema, SchemaCompatibilityError, SchemaViolation
from elspeth.core.base.schema.validation import validate_dataframe, validate_row, validate_schema_compatibility


class SampleDatasourceSchema(DataFrameSchema):
    colour: str
    score: float
    notes: str | None = None


class SamplePluginSchema(DataFrameSchema):
    colour: str
    score: Optional[float] = None


def test_validate_row_success_returns_true():
    is_valid, violation = validate_row({"colour": "red", "score": 7.0}, SampleDatasourceSchema)

    assert is_valid is True
    assert violation is None


def test_validate_row_failure_captures_schema_violation():
    is_valid, violation = validate_row({"colour": 9, "score": "bad"}, SampleDatasourceSchema, row_index=5)

    assert is_valid is False
    assert isinstance(violation, SchemaViolation)
    payload = violation.to_dict()
    assert payload["row_index"] == 5
    assert payload["schema_name"] == "SampleDatasourceSchema"
    error_fields = {err["field"] for err in payload["validation_errors"]}
    assert {"colour", "score"} & error_fields


def test_validate_dataframe_collects_all_rows_when_not_early_stopping():
    df = pd.DataFrame(
        [
            {"colour": "red", "score": 1.0},
            {"colour": 5, "score": "bad"},
            {"colour": "blue", "score": None},
        ]
    )

    is_valid, violations = validate_dataframe(df, SampleDatasourceSchema, early_stop=False)

    assert is_valid is False
    assert len(violations) == 2
    assert violations[0].row_index == 1
    assert violations[1].row_index == 2


def test_validate_schema_compatibility_passes_for_matching_optional_types():
    # No exception should be raised when datasource covers plugin requirements.
    validate_schema_compatibility(SampleDatasourceSchema, SamplePluginSchema, plugin_name="aggregator")


def test_validate_schema_compatibility_missing_columns_raise_error():
    class PluginNeedsExtra(DataFrameSchema):
        colour: str
        rating: float

    with pytest.raises(SchemaCompatibilityError) as excinfo:
        validate_schema_compatibility(SampleDatasourceSchema, PluginNeedsExtra, plugin_name="rating_plugin")

    error = excinfo.value
    assert "rating_plugin" in str(error)
    assert error.missing_columns == ["rating"]


def test_validate_schema_compatibility_type_mismatch_raises_error():
    class PluginNeedsInt(DataFrameSchema):
        colour: str
        score: int

    with pytest.raises(SchemaCompatibilityError) as excinfo:
        validate_schema_compatibility(SampleDatasourceSchema, PluginNeedsInt, plugin_name="scoring")

    error = excinfo.value
    assert error.type_mismatches == {"score": ("float", "int")}
    assert "scoring" in str(error)
