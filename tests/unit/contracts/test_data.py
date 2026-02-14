"""Tests for data contracts."""

from __future__ import annotations

from typing import Annotated, Optional

import pytest
from pydantic import ValidationError

from elspeth.contracts.data import (
    PluginSchema,
    _types_compatible,
    _unwrap_annotated,
    check_compatibility,
)


class TestPluginSchema:
    """Tests for PluginSchema base class."""

    def test_subclass_validates_input(self) -> None:
        """PluginSchema subclasses validate input."""
        from elspeth.contracts import PluginSchema

        class MySchema(PluginSchema):
            name: str
            value: int

        schema = MySchema(name="test", value=42)
        assert schema.name == "test"

        with pytest.raises(ValidationError):
            MySchema(name="test", value="not_an_int")

    def test_coercion_with_strict_false(self) -> None:
        """PluginSchema coerces compatible types (strict=False)."""
        from elspeth.contracts import PluginSchema

        class MySchema(PluginSchema):
            name: str
            value: int

        schema = MySchema(name="test", value="42")  # type: ignore[arg-type]
        assert schema.value == 42
        assert type(schema.value) is int

    def test_schema_is_mutable(self) -> None:
        """PluginSchema instances are mutable (Their Data trust boundary)."""
        from elspeth.contracts import PluginSchema

        class MySchema(PluginSchema):
            name: str

        schema = MySchema(name="test")
        schema.name = "changed"
        assert schema.name == "changed"

    def test_schema_ignores_extra(self) -> None:
        """PluginSchema ignores unknown fields (Their Data trust boundary)."""
        from elspeth.contracts import PluginSchema

        class MySchema(PluginSchema):
            name: str

        schema = MySchema(name="test", unknown_field="value")  # type: ignore[call-arg]
        assert schema.name == "test"
        field_names = set(MySchema.model_fields.keys())
        assert "unknown_field" not in field_names


class TestUnwrapAnnotated:
    """Tests for _unwrap_annotated helper."""

    def test_plain_type_unchanged(self) -> None:
        """Plain types pass through unchanged."""
        assert _unwrap_annotated(float) is float
        assert _unwrap_annotated(int) is int
        assert _unwrap_annotated(str) is str

    def test_annotated_unwraps_to_base_type(self) -> None:
        """Annotated[T, ...] unwraps to T."""
        assert _unwrap_annotated(Annotated[float, "metadata"]) is float
        assert _unwrap_annotated(Annotated[int, "constraint"]) is int

    def test_nested_annotated_fully_unwraps(self) -> None:
        """Nested Annotated types are fully unwrapped."""
        nested = Annotated[Annotated[float, "inner"], "outer"]
        assert _unwrap_annotated(nested) is float

    def test_optional_not_unwrapped(self) -> None:
        """Optional (Union) is not unwrapped by _unwrap_annotated."""
        from typing import Union, get_origin

        result = _unwrap_annotated(Optional[float])  # noqa: UP045
        # Optional[float] is Union[float, None] - should not be unwrapped
        assert get_origin(result) is Union


class TestTypesCompatibleAnnotated:
    """Tests for _types_compatible with Annotated type handling.

    Regression tests for P1 bug: check_compatibility incorrectly rejects
    float -> Optional[Annotated[float, ...]] because Annotated metadata
    was not unwrapped before comparison.
    """

    def test_float_compatible_with_annotated_float(self) -> None:
        """float is compatible with Annotated[float, ...]."""
        assert _types_compatible(float, Annotated[float, "constraint"]) is True

    def test_annotated_float_compatible_with_float(self) -> None:
        """Annotated[float, ...] is compatible with float."""
        assert _types_compatible(Annotated[float, "constraint"], float) is True

    def test_float_compatible_with_optional_annotated_float(self) -> None:
        """float is compatible with Optional[Annotated[float, ...]]."""
        assert _types_compatible(float, Optional[Annotated[float, "constraint"]]) is True  # noqa: UP045

    def test_int_compatible_with_annotated_float_nonstrict(self) -> None:
        """int -> Annotated[float, ...] is compatible when not strict."""
        assert _types_compatible(int, Annotated[float, "constraint"], consumer_strict=False) is True

    def test_int_incompatible_with_annotated_float_strict(self) -> None:
        """int -> Annotated[float, ...] is rejected when strict."""
        assert _types_compatible(int, Annotated[float, "constraint"], consumer_strict=True) is False

    def test_annotated_int_compatible_with_optional_annotated_float(self) -> None:
        """Annotated[int, ...] -> Optional[Annotated[float, ...]] compatible (int->float coercion)."""
        assert (
            _types_compatible(
                Annotated[int, "producer_meta"],
                Optional[Annotated[float, "consumer_meta"]],  # noqa: UP045
                consumer_strict=False,
            )
            is True
        )

    def test_annotated_str_incompatible_with_annotated_float(self) -> None:
        """Annotated[str, ...] is NOT compatible with Annotated[float, ...]."""
        assert (
            _types_compatible(
                Annotated[str, "meta"],
                Annotated[float, "meta"],
            )
            is False
        )


class TestCheckCompatibilityAnnotated:
    """Integration tests for check_compatibility with Annotated schemas.

    Tests the full path from PluginSchema through check_compatibility,
    ensuring config-generated schemas with FiniteFloat work correctly.
    """

    def test_float_producer_optional_annotated_float_consumer(self) -> None:
        """Producer float field compatible with consumer Optional[Annotated[float, ...]]."""

        class ProducerSchema(PluginSchema):
            score: float

        class ConsumerSchema(PluginSchema):
            score: Optional[Annotated[float, "finite"]] = None  # noqa: UP045

        result = check_compatibility(ProducerSchema, ConsumerSchema)
        assert result.compatible is True
        assert result.type_mismatches == []

    def test_annotated_producer_plain_consumer(self) -> None:
        """Producer with Annotated[float, ...] compatible with consumer plain float."""

        class ProducerSchema(PluginSchema):
            score: Annotated[float, "constrained"]

        class ConsumerSchema(PluginSchema):
            score: float

        result = check_compatibility(ProducerSchema, ConsumerSchema)
        assert result.compatible is True
