# tests/property/plugins/llm/test_multi_query_properties.py
"""Property-based tests for multi-query pure data transformations.

The multi-query system evaluates a cross-product of (case_study x criterion)
against each row. These tests cover the pure logic:

1. OutputFieldConfig.to_json_schema: type mapping correctness
2. QuerySpec.build_template_context: positional variable mapping
3. OutputFieldConfig validation: enum requires values, others reject values
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.plugins.llm.multi_query import (
    OutputFieldConfig,
    OutputFieldType,
    QuerySpec,
)

# =============================================================================
# Strategies
# =============================================================================

field_names = st.text(min_size=1, max_size=15, alphabet="abcdefghijklmnopqrstuvwxyz_")

string_values = st.text(min_size=0, max_size=30)

# Non-enum field types
non_enum_types = st.sampled_from(
    [
        OutputFieldType.STRING,
        OutputFieldType.INTEGER,
        OutputFieldType.NUMBER,
        OutputFieldType.BOOLEAN,
    ]
)


# =============================================================================
# OutputFieldConfig.to_json_schema Properties
# =============================================================================


class TestOutputFieldSchemaProperties:
    """to_json_schema must produce valid JSON Schema fragments."""

    @given(field_type=non_enum_types)
    @settings(max_examples=20)
    def test_non_enum_schema_has_type_key(self, field_type: OutputFieldType) -> None:
        """Property: Non-enum types produce {"type": type_value}."""
        config = OutputFieldConfig(suffix="test", type=field_type)
        schema = config.to_json_schema()
        assert "type" in schema
        assert schema["type"] == field_type.value

    @given(values=st.lists(string_values, min_size=1, max_size=5, unique=True))
    @settings(max_examples=50)
    def test_enum_schema_has_enum_list(self, values: list[str]) -> None:
        """Property: Enum type produces {"type": "string", "enum": values}."""
        config = OutputFieldConfig(suffix="test", type=OutputFieldType.ENUM, values=values)
        schema = config.to_json_schema()
        assert schema["type"] == "string"
        assert "enum" in schema
        assert schema["enum"] == values

    def test_enum_without_values_rejected(self) -> None:
        """Property: Enum type without values raises ValidationError."""
        import pydantic

        with pytest.raises(pydantic.ValidationError, match="non-empty"):
            OutputFieldConfig(suffix="test", type=OutputFieldType.ENUM, values=[])

    def test_enum_with_none_values_rejected(self) -> None:
        """Property: Enum type with None values raises ValidationError."""
        import pydantic

        with pytest.raises(pydantic.ValidationError, match="non-empty"):
            OutputFieldConfig(suffix="test", type=OutputFieldType.ENUM, values=None)

    @given(field_type=non_enum_types, values=st.lists(string_values, min_size=1, max_size=3))
    @settings(max_examples=20)
    def test_non_enum_with_values_rejected(self, field_type: OutputFieldType, values: list[str]) -> None:
        """Property: Non-enum types with values raises ValidationError."""
        import pydantic

        with pytest.raises(pydantic.ValidationError, match="only valid for enum"):
            OutputFieldConfig(suffix="test", type=field_type, values=values)

    @given(field_type=non_enum_types)
    @settings(max_examples=20)
    def test_schema_has_no_extra_keys(self, field_type: OutputFieldType) -> None:
        """Property: Non-enum schemas only have 'type' key."""
        config = OutputFieldConfig(suffix="test", type=field_type)
        schema = config.to_json_schema()
        assert set(schema.keys()) == {"type"}


# =============================================================================
# QuerySpec.build_template_context Properties
# =============================================================================


class TestQuerySpecContextProperties:
    """build_template_context must create correct positional mappings."""

    @given(
        n_fields=st.integers(min_value=1, max_value=5),
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_positional_mapping(self, n_fields: int, data: st.DataObject) -> None:
        """Property: input_fields[i] maps to context['input_{i+1}']."""
        names = data.draw(st.lists(field_names, min_size=n_fields, max_size=n_fields, unique=True))
        values = data.draw(st.lists(string_values, min_size=n_fields, max_size=n_fields))
        row = dict(zip(names, values, strict=False))

        spec = QuerySpec(
            case_study_name="cs1",
            criterion_name="cr1",
            input_fields=names,
            output_prefix="cs1_cr1",
            criterion_data={"name": "cr1"},
            case_study_data={"name": "cs1"},
        )

        ctx = spec.build_template_context(row)

        for i, name in enumerate(names, start=1):
            assert f"input_{i}" in ctx
            assert ctx[f"input_{i}"] == row[name]

    @given(data=st.data())
    @settings(max_examples=50)
    def test_context_includes_criterion_and_case_study(self, data: st.DataObject) -> None:
        """Property: Context always includes criterion and case_study dicts."""
        name = data.draw(field_names)
        row = {name: "value"}
        criterion_data = {"name": "test_criterion"}
        case_study_data = {"name": "test_case_study"}

        spec = QuerySpec(
            case_study_name="cs1",
            criterion_name="cr1",
            input_fields=[name],
            output_prefix="cs1_cr1",
            criterion_data=criterion_data,
            case_study_data=case_study_data,
        )

        ctx = spec.build_template_context(row)
        assert ctx["criterion"] == criterion_data
        assert ctx["case_study"] == case_study_data

    @given(data=st.data())
    @settings(max_examples=50)
    def test_context_includes_full_row(self, data: st.DataObject) -> None:
        """Property: Context['row'] contains the full original row."""
        name = data.draw(field_names)
        value = data.draw(string_values)
        row = {name: value}

        spec = QuerySpec(
            case_study_name="cs1",
            criterion_name="cr1",
            input_fields=[name],
            output_prefix="cs1_cr1",
            criterion_data={},
            case_study_data={},
        )

        ctx = spec.build_template_context(row)
        assert ctx["row"] == row

    def test_missing_field_raises_key_error(self) -> None:
        """Property: Missing required field raises KeyError."""
        spec = QuerySpec(
            case_study_name="cs1",
            criterion_name="cr1",
            input_fields=["required_field"],
            output_prefix="cs1_cr1",
            criterion_data={},
            case_study_data={},
        )

        with pytest.raises(KeyError, match="required_field"):
            spec.build_template_context({"other_field": "value"})

    @given(
        n_fields=st.integers(min_value=1, max_value=5),
        data=st.data(),
    )
    @settings(max_examples=50)
    def test_context_has_exactly_expected_keys(self, n_fields: int, data: st.DataObject) -> None:
        """Property: Context has input_N, criterion, case_study, and row only."""
        names = data.draw(st.lists(field_names, min_size=n_fields, max_size=n_fields, unique=True))
        row = dict.fromkeys(names, "v")

        spec = QuerySpec(
            case_study_name="cs1",
            criterion_name="cr1",
            input_fields=names,
            output_prefix="cs1_cr1",
            criterion_data={},
            case_study_data={},
        )

        ctx = spec.build_template_context(row)

        expected_keys = {f"input_{i}" for i in range(1, n_fields + 1)}
        expected_keys |= {"criterion", "case_study", "row"}
        assert set(ctx.keys()) == expected_keys
