"""Tests for FieldContract dataclass.

FieldContract represents a single field in a schema contract with:
- normalized_name: Python identifier for dict access (e.g., "amount_usd")
- original_name: Display name from source (e.g., "'Amount USD'")
- python_type: Python primitive type (int, str, float, bool, etc.)
- required: Whether field must be present
- source: "declared" (from config) or "inferred" (from first row)

The dataclass is frozen (immutable) and uses __slots__ for memory efficiency.
"""

import pytest


class TestFieldContractCreation:
    """Tests for creating FieldContract instances."""

    def test_create_declared_field(self) -> None:
        """Can create a declared field with all attributes."""
        from elspeth.contracts.schema_contract import FieldContract

        field = FieldContract(
            normalized_name="amount_usd",
            original_name="Amount USD",
            python_type=float,
            required=True,
            source="declared",
        )

        assert field.normalized_name == "amount_usd"
        assert field.original_name == "Amount USD"
        assert field.python_type is float
        assert field.required is True
        assert field.source == "declared"

    def test_create_inferred_field(self) -> None:
        """Can create an inferred field (typically from first row observation)."""
        from elspeth.contracts.schema_contract import FieldContract

        field = FieldContract(
            normalized_name="customer_id",
            original_name="Customer ID",
            python_type=str,
            required=False,
            source="inferred",
        )

        assert field.normalized_name == "customer_id"
        assert field.original_name == "Customer ID"
        assert field.python_type is str
        assert field.required is False
        assert field.source == "inferred"

    def test_python_type_accepts_primitives(self) -> None:
        """python_type can be any Python type object."""
        from datetime import datetime

        from elspeth.contracts.schema_contract import FieldContract

        # Common primitive types
        int_field = FieldContract(
            normalized_name="count",
            original_name="count",
            python_type=int,
            required=True,
            source="declared",
        )
        assert int_field.python_type is int

        str_field = FieldContract(
            normalized_name="name",
            original_name="name",
            python_type=str,
            required=True,
            source="declared",
        )
        assert str_field.python_type is str

        bool_field = FieldContract(
            normalized_name="active",
            original_name="active",
            python_type=bool,
            required=True,
            source="declared",
        )
        assert bool_field.python_type is bool

        # datetime is also supported
        dt_field = FieldContract(
            normalized_name="created_at",
            original_name="created_at",
            python_type=datetime,
            required=True,
            source="declared",
        )
        assert dt_field.python_type is datetime

        # NoneType for nullable fields
        none_field = FieldContract(
            normalized_name="optional_value",
            original_name="optional_value",
            python_type=type(None),
            required=False,
            source="declared",
        )
        assert none_field.python_type is type(None)


class TestFieldContractImmutability:
    """Tests for frozen dataclass behavior."""

    def test_frozen_cannot_modify_normalized_name(self) -> None:
        """Frozen dataclass - cannot modify normalized_name after creation."""
        from elspeth.contracts.schema_contract import FieldContract

        field = FieldContract(
            normalized_name="original",
            original_name="Original",
            python_type=str,
            required=True,
            source="declared",
        )

        with pytest.raises(AttributeError):
            field.normalized_name = "modified"  # type: ignore[misc]

    def test_frozen_cannot_modify_original_name(self) -> None:
        """Frozen dataclass - cannot modify original_name after creation."""
        from elspeth.contracts.schema_contract import FieldContract

        field = FieldContract(
            normalized_name="field",
            original_name="Original",
            python_type=str,
            required=True,
            source="declared",
        )

        with pytest.raises(AttributeError):
            field.original_name = "Modified"  # type: ignore[misc]

    def test_frozen_cannot_modify_python_type(self) -> None:
        """Frozen dataclass - cannot modify python_type after creation."""
        from elspeth.contracts.schema_contract import FieldContract

        field = FieldContract(
            normalized_name="field",
            original_name="field",
            python_type=str,
            required=True,
            source="declared",
        )

        with pytest.raises(AttributeError):
            field.python_type = int  # type: ignore[misc]

    def test_frozen_cannot_modify_required(self) -> None:
        """Frozen dataclass - cannot modify required after creation."""
        from elspeth.contracts.schema_contract import FieldContract

        field = FieldContract(
            normalized_name="field",
            original_name="field",
            python_type=str,
            required=True,
            source="declared",
        )

        with pytest.raises(AttributeError):
            field.required = False  # type: ignore[misc]

    def test_frozen_cannot_modify_source(self) -> None:
        """Frozen dataclass - cannot modify source after creation."""
        from elspeth.contracts.schema_contract import FieldContract

        field = FieldContract(
            normalized_name="field",
            original_name="field",
            python_type=str,
            required=True,
            source="declared",
        )

        with pytest.raises(AttributeError):
            field.source = "inferred"  # type: ignore[misc]


class TestFieldContractSlots:
    """Tests for __slots__ behavior (memory optimization)."""

    def test_uses_slots_no_dict(self) -> None:
        """FieldContract uses __slots__ - no __dict__ attribute."""
        from elspeth.contracts.schema_contract import FieldContract

        field = FieldContract(
            normalized_name="field",
            original_name="field",
            python_type=str,
            required=True,
            source="declared",
        )

        # slots=True means no __dict__
        assert not hasattr(field, "__dict__")

    def test_cannot_add_arbitrary_attributes(self) -> None:
        """Cannot add arbitrary attributes (slots + frozen).

        Note: Python may raise either AttributeError or TypeError depending on
        how __setattr__ is overridden in frozen dataclasses with slots.
        """
        from elspeth.contracts.schema_contract import FieldContract

        field = FieldContract(
            normalized_name="field",
            original_name="field",
            python_type=str,
            required=True,
            source="declared",
        )

        # Frozen + slots prevents adding arbitrary attributes
        # May raise AttributeError or TypeError depending on Python version
        with pytest.raises((AttributeError, TypeError)):
            field.arbitrary_attr = "value"  # type: ignore[attr-defined]


class TestFieldContractEquality:
    """Tests for equality and hashing."""

    def test_equality_same_values(self) -> None:
        """Two FieldContracts with same values are equal."""
        from elspeth.contracts.schema_contract import FieldContract

        field1 = FieldContract(
            normalized_name="amount",
            original_name="Amount",
            python_type=float,
            required=True,
            source="declared",
        )
        field2 = FieldContract(
            normalized_name="amount",
            original_name="Amount",
            python_type=float,
            required=True,
            source="declared",
        )

        assert field1 == field2

    def test_equality_different_normalized_name(self) -> None:
        """Different normalized_name means not equal."""
        from elspeth.contracts.schema_contract import FieldContract

        field1 = FieldContract(
            normalized_name="amount",
            original_name="Amount",
            python_type=float,
            required=True,
            source="declared",
        )
        field2 = FieldContract(
            normalized_name="price",
            original_name="Amount",
            python_type=float,
            required=True,
            source="declared",
        )

        assert field1 != field2

    def test_equality_different_type(self) -> None:
        """Different python_type means not equal."""
        from elspeth.contracts.schema_contract import FieldContract

        field1 = FieldContract(
            normalized_name="value",
            original_name="value",
            python_type=int,
            required=True,
            source="declared",
        )
        field2 = FieldContract(
            normalized_name="value",
            original_name="value",
            python_type=float,
            required=True,
            source="declared",
        )

        assert field1 != field2

    def test_equality_different_source(self) -> None:
        """Different source means not equal."""
        from elspeth.contracts.schema_contract import FieldContract

        field1 = FieldContract(
            normalized_name="field",
            original_name="field",
            python_type=str,
            required=True,
            source="declared",
        )
        field2 = FieldContract(
            normalized_name="field",
            original_name="field",
            python_type=str,
            required=True,
            source="inferred",
        )

        assert field1 != field2


class TestFieldContractHashable:
    """Tests for hashability (can use in sets/dict keys)."""

    def test_hashable_can_use_in_set(self) -> None:
        """FieldContract is hashable - can be used in sets."""
        from elspeth.contracts.schema_contract import FieldContract

        field1 = FieldContract(
            normalized_name="amount",
            original_name="Amount",
            python_type=float,
            required=True,
            source="declared",
        )
        field2 = FieldContract(
            normalized_name="amount",
            original_name="Amount",
            python_type=float,
            required=True,
            source="declared",
        )
        field3 = FieldContract(
            normalized_name="count",
            original_name="Count",
            python_type=int,
            required=True,
            source="declared",
        )

        # Can add to set
        field_set = {field1, field2, field3}

        # field1 and field2 are equal, so set should have 2 items
        assert len(field_set) == 2
        assert field1 in field_set
        assert field3 in field_set

    def test_hashable_can_use_as_dict_key(self) -> None:
        """FieldContract is hashable - can be used as dict key."""
        from elspeth.contracts.schema_contract import FieldContract

        field = FieldContract(
            normalized_name="status",
            original_name="Status",
            python_type=str,
            required=True,
            source="declared",
        )

        # Can use as dict key
        field_dict = {field: "some_value"}

        assert field_dict[field] == "some_value"

    def test_equal_fields_have_same_hash(self) -> None:
        """Equal FieldContracts have the same hash (hash consistency)."""
        from elspeth.contracts.schema_contract import FieldContract

        field1 = FieldContract(
            normalized_name="x",
            original_name="X",
            python_type=int,
            required=True,
            source="declared",
        )
        field2 = FieldContract(
            normalized_name="x",
            original_name="X",
            python_type=int,
            required=True,
            source="declared",
        )

        assert field1 == field2
        assert hash(field1) == hash(field2)


class TestFieldContractSourceValidation:
    """Tests for source field validation.

    Source must be Literal["declared", "inferred"] - this is enforced
    by the type system, but we document the expected values here.
    """

    def test_source_declared_accepted(self) -> None:
        """source='declared' is valid."""
        from elspeth.contracts.schema_contract import FieldContract

        field = FieldContract(
            normalized_name="field",
            original_name="field",
            python_type=str,
            required=True,
            source="declared",
        )
        assert field.source == "declared"

    def test_source_inferred_accepted(self) -> None:
        """source='inferred' is valid."""
        from elspeth.contracts.schema_contract import FieldContract

        field = FieldContract(
            normalized_name="field",
            original_name="field",
            python_type=str,
            required=False,
            source="inferred",
        )
        assert field.source == "inferred"

    def test_source_literal_type_annotation(self) -> None:
        """source field has Literal type annotation (verified via get_type_hints).

        Note: With `from __future__ import annotations`, dataclass field.type
        is a string. We use get_type_hints() to resolve the actual type.
        """
        from typing import Literal, get_args, get_origin, get_type_hints

        from elspeth.contracts.schema_contract import FieldContract

        # get_type_hints resolves string annotations to actual types
        hints = get_type_hints(FieldContract)
        source_type = hints["source"]

        # Check it's a Literal type
        assert get_origin(source_type) is Literal
        # Check the allowed values
        assert get_args(source_type) == ("declared", "inferred")
