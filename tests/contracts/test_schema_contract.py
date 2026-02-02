"""Tests for SchemaContract - core structure and name resolution.

Task 4 of Phase 1: Core Contracts Implementation.
"""

from __future__ import annotations

import pytest

from elspeth.contracts.schema_contract import FieldContract, SchemaContract

# --- Fixtures ---


@pytest.fixture
def sample_fields() -> tuple[FieldContract, ...]:
    """Sample fields for testing schema contracts."""
    return (
        FieldContract(
            normalized_name="amount_usd",
            original_name="'Amount USD'",
            python_type=float,
            required=True,
            source="declared",
        ),
        FieldContract(
            normalized_name="customer_id",
            original_name="customer_id",
            python_type=str,
            required=True,
            source="declared",
        ),
        FieldContract(
            normalized_name="is_active",
            original_name="'Is Active?'",
            python_type=bool,
            required=False,
            source="inferred",
        ),
    )


# --- Creation Tests ---


class TestSchemaContractCreation:
    """Tests for SchemaContract creation."""

    def test_create_fixed_mode_contract(self, sample_fields: tuple[FieldContract, ...]) -> None:
        """Create FIXED mode contract with fields tuple and locked=True."""
        contract = SchemaContract(
            mode="FIXED",
            fields=sample_fields,
            locked=True,
        )

        assert contract.mode == "FIXED"
        assert contract.fields == sample_fields
        assert contract.locked is True

    def test_create_flexible_mode_contract(self, sample_fields: tuple[FieldContract, ...]) -> None:
        """Create FLEXIBLE mode contract with locked=False."""
        contract = SchemaContract(
            mode="FLEXIBLE",
            fields=sample_fields,
            locked=False,
        )

        assert contract.mode == "FLEXIBLE"
        assert contract.fields == sample_fields
        assert contract.locked is False

    def test_create_observed_mode_contract(self) -> None:
        """Create OBSERVED mode contract with no declared fields."""
        contract = SchemaContract(
            mode="OBSERVED",
            fields=(),
            locked=False,
        )

        assert contract.mode == "OBSERVED"
        assert contract.fields == ()
        assert contract.locked is False

    def test_frozen_immutable_raises_attribute_error(self, sample_fields: tuple[FieldContract, ...]) -> None:
        """Frozen dataclass - assigning raises AttributeError."""
        contract = SchemaContract(
            mode="FIXED",
            fields=sample_fields,
            locked=False,
        )

        with pytest.raises(AttributeError):
            contract.mode = "FLEXIBLE"  # type: ignore[misc]

        with pytest.raises(AttributeError):
            contract.locked = True  # type: ignore[misc]

        with pytest.raises(AttributeError):
            contract.fields = ()  # type: ignore[misc]

    def test_locked_defaults_to_false(self, sample_fields: tuple[FieldContract, ...]) -> None:
        """locked defaults to False when not specified."""
        contract = SchemaContract(
            mode="FIXED",
            fields=sample_fields,
        )

        assert contract.locked is False


# --- Name Resolution Tests (O(1) dual-name access) ---


class TestSchemaContractNameResolution:
    """Tests for SchemaContract name resolution."""

    def test_resolve_name_already_normalized(self, sample_fields: tuple[FieldContract, ...]) -> None:
        """resolve_name("amount_usd") returns "amount_usd" (already normalized)."""
        contract = SchemaContract(
            mode="FIXED",
            fields=sample_fields,
        )

        result = contract.resolve_name("amount_usd")
        assert result == "amount_usd"

    def test_resolve_name_original_to_normalized(self, sample_fields: tuple[FieldContract, ...]) -> None:
        """resolve_name("'Amount USD'") returns "amount_usd" (original -> normalized)."""
        contract = SchemaContract(
            mode="FIXED",
            fields=sample_fields,
        )

        result = contract.resolve_name("'Amount USD'")
        assert result == "amount_usd"

    def test_resolve_name_nonexistent_raises_keyerror(self, sample_fields: tuple[FieldContract, ...]) -> None:
        """resolve_name("nonexistent") raises KeyError."""
        contract = SchemaContract(
            mode="FIXED",
            fields=sample_fields,
        )

        with pytest.raises(KeyError, match="'nonexistent' not found in schema contract"):
            contract.resolve_name("nonexistent")

    def test_indices_populated(self, sample_fields: tuple[FieldContract, ...]) -> None:
        """_by_normalized and _by_original indices are populated."""
        contract = SchemaContract(
            mode="FIXED",
            fields=sample_fields,
        )

        # _by_normalized maps normalized_name -> FieldContract
        assert "amount_usd" in contract._by_normalized
        assert "customer_id" in contract._by_normalized
        assert "is_active" in contract._by_normalized
        assert len(contract._by_normalized) == 3

        # _by_original maps original_name -> normalized_name
        assert contract._by_original["'Amount USD'"] == "amount_usd"
        assert contract._by_original["customer_id"] == "customer_id"
        assert contract._by_original["'Is Active?'"] == "is_active"
        assert len(contract._by_original) == 3

    def test_get_field_returns_field_contract(self, sample_fields: tuple[FieldContract, ...]) -> None:
        """get_field("amount_usd") returns the FieldContract."""
        contract = SchemaContract(
            mode="FIXED",
            fields=sample_fields,
        )

        field = contract.get_field("amount_usd")
        assert field is not None
        assert field.normalized_name == "amount_usd"
        assert field.original_name == "'Amount USD'"
        assert field.python_type is float

    def test_get_field_nonexistent_returns_none(self, sample_fields: tuple[FieldContract, ...]) -> None:
        """get_field("nonexistent") returns None."""
        contract = SchemaContract(
            mode="FIXED",
            fields=sample_fields,
        )

        result = contract.get_field("nonexistent")
        assert result is None

    def test_resolve_all_fields_both_directions(self, sample_fields: tuple[FieldContract, ...]) -> None:
        """All fields resolve correctly in both directions."""
        contract = SchemaContract(
            mode="FIXED",
            fields=sample_fields,
        )

        # Test all fields can be resolved by normalized name
        for fc in sample_fields:
            assert contract.resolve_name(fc.normalized_name) == fc.normalized_name

        # Test all fields can be resolved by original name
        for fc in sample_fields:
            assert contract.resolve_name(fc.original_name) == fc.normalized_name


# --- Edge Cases ---


class TestSchemaContractEdgeCases:
    """Edge case tests for SchemaContract."""

    def test_empty_fields_tuple(self) -> None:
        """Schema with no fields works correctly."""
        contract = SchemaContract(
            mode="OBSERVED",
            fields=(),
        )

        assert len(contract._by_normalized) == 0
        assert len(contract._by_original) == 0
        assert contract.get_field("anything") is None

        with pytest.raises(KeyError):
            contract.resolve_name("anything")

    def test_field_where_original_equals_normalized(self) -> None:
        """Field where original_name == normalized_name is indexed correctly."""
        field = FieldContract(
            normalized_name="simple_field",
            original_name="simple_field",
            python_type=str,
            required=True,
            source="declared",
        )
        contract = SchemaContract(
            mode="FIXED",
            fields=(field,),
        )

        # Both lookups should work
        assert contract.resolve_name("simple_field") == "simple_field"
        assert contract.get_field("simple_field") == field

        # Indices should both contain it
        assert "simple_field" in contract._by_normalized
        assert "simple_field" in contract._by_original


# --- Mutation Tests ---


class TestSchemaContractMutation:
    """Test immutable 'mutation' methods that return new instances."""

    def test_with_locked_returns_new_instance(self) -> None:
        """with_locked() returns new contract with locked=True."""
        original = SchemaContract(mode="OBSERVED", fields=(), locked=False)
        locked = original.with_locked()

        assert locked.locked is True
        assert original.locked is False  # Original unchanged
        assert locked is not original

    def test_with_locked_preserves_fields(self) -> None:
        """with_locked() preserves all fields."""
        fc = FieldContract("x", "X", int, True, "declared")
        original = SchemaContract(mode="FLEXIBLE", fields=(fc,), locked=False)
        locked = original.with_locked()

        assert locked.fields == original.fields
        assert locked.mode == original.mode

    def test_with_field_adds_inferred_field(self) -> None:
        """with_field() adds new inferred field to contract."""
        original = SchemaContract(mode="OBSERVED", fields=(), locked=False)
        updated = original.with_field("amount", "'Amount'", 100)

        assert len(updated.fields) == 1
        assert updated.fields[0].normalized_name == "amount"
        assert updated.fields[0].original_name == "'Amount'"
        assert updated.fields[0].python_type is int
        assert updated.fields[0].source == "inferred"
        assert updated.fields[0].required is False

    def test_with_field_normalizes_numpy_type(self) -> None:
        """with_field() normalizes numpy.int64 to int."""
        import numpy as np

        original = SchemaContract(mode="OBSERVED", fields=(), locked=False)
        updated = original.with_field("count", "Count", np.int64(42))

        assert updated.fields[0].python_type is int  # Not numpy.int64

    def test_with_field_normalizes_pandas_timestamp(self) -> None:
        """with_field() normalizes pandas.Timestamp to datetime."""
        from datetime import datetime

        import pandas as pd

        original = SchemaContract(mode="OBSERVED", fields=(), locked=False)
        updated = original.with_field("ts", "Timestamp", pd.Timestamp("2024-01-01"))

        assert updated.fields[0].python_type is datetime

    def test_with_field_rejects_nan(self) -> None:
        """with_field() rejects NaN values."""
        original = SchemaContract(mode="OBSERVED", fields=(), locked=False)

        with pytest.raises(ValueError, match="non-finite"):
            original.with_field("bad", "Bad", float("nan"))

    def test_with_field_locked_rejects_existing(self) -> None:
        """with_field() raises if field already exists and contract is locked."""
        fc = FieldContract("amount", "'Amount'", int, True, "declared")
        locked = SchemaContract(mode="FLEXIBLE", fields=(fc,), locked=True)

        with pytest.raises(TypeError, match="already locked"):
            locked.with_field("amount", "'Amount'", 200)

    def test_with_field_unlocked_allows_update(self) -> None:
        """with_field() allows adding fields when not locked."""
        fc = FieldContract("a", "A", int, True, "declared")
        unlocked = SchemaContract(mode="FLEXIBLE", fields=(fc,), locked=False)

        # Can add new field
        updated = unlocked.with_field("b", "B", "hello")
        assert len(updated.fields) == 2

    def test_with_field_updates_indices(self) -> None:
        """with_field() updates name resolution indices."""
        original = SchemaContract(mode="OBSERVED", fields=(), locked=False)
        updated = original.with_field("amount", "'Amount USD'", 100)

        # Both names should resolve
        assert updated.resolve_name("amount") == "amount"
        assert updated.resolve_name("'Amount USD'") == "amount"
