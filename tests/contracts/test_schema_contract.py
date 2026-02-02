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


# --- Validation Tests ---


class TestSchemaContractValidation:
    """Test contract validation."""

    def test_validate_valid_row_returns_empty(self) -> None:
        """Valid row returns empty violations list."""
        contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("id", "ID", int, True, "declared"),),
            locked=True,
        )
        violations = contract.validate({"id": 42})
        assert violations == []

    def test_validate_missing_required_field(self) -> None:
        """Missing required field returns MissingFieldViolation."""
        from elspeth.contracts.errors import MissingFieldViolation

        contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("id", "ID", int, True, "declared"),),
            locked=True,
        )
        violations = contract.validate({})

        assert len(violations) == 1
        assert isinstance(violations[0], MissingFieldViolation)
        assert violations[0].normalized_name == "id"

    def test_validate_optional_field_can_be_missing(self) -> None:
        """Optional field (required=False) can be missing."""
        contract = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("note", "Note", str, False, "declared"),),
            locked=True,
        )
        violations = contract.validate({})
        assert violations == []

    def test_validate_type_mismatch(self) -> None:
        """Wrong type returns TypeMismatchViolation."""
        from elspeth.contracts.errors import TypeMismatchViolation

        contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("id", "ID", int, True, "declared"),),
            locked=True,
        )
        violations = contract.validate({"id": "not_an_int"})

        assert len(violations) == 1
        assert isinstance(violations[0], TypeMismatchViolation)
        assert violations[0].expected_type is int
        assert violations[0].actual_type is str

    def test_validate_numpy_type_matches_primitive(self) -> None:
        """numpy.int64 value matches int contract type."""
        import numpy as np

        contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("count", "Count", int, True, "declared"),),
            locked=True,
        )
        violations = contract.validate({"count": np.int64(42)})
        assert violations == []  # np.int64 normalizes to int

    def test_validate_none_matches_nonetype(self) -> None:
        """None value matches type(None) contract."""
        contract = SchemaContract(
            mode="OBSERVED",
            fields=(FieldContract("x", "X", type(None), False, "inferred"),),
            locked=True,
        )
        violations = contract.validate({"x": None})
        assert violations == []

    def test_validate_fixed_rejects_extras(self) -> None:
        """FIXED mode rejects extra fields."""
        from elspeth.contracts.errors import ExtraFieldViolation

        contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("id", "ID", int, True, "declared"),),
            locked=True,
        )
        violations = contract.validate({"id": 1, "extra": "field"})

        assert len(violations) == 1
        assert isinstance(violations[0], ExtraFieldViolation)
        assert violations[0].normalized_name == "extra"

    def test_validate_flexible_allows_extras(self) -> None:
        """FLEXIBLE mode allows extra fields (returns no violation)."""
        contract = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("id", "ID", int, True, "declared"),),
            locked=True,
        )
        violations = contract.validate({"id": 1, "extra": "field"})
        assert violations == []

    def test_validate_observed_allows_extras(self) -> None:
        """OBSERVED mode allows extra fields."""
        contract = SchemaContract(
            mode="OBSERVED",
            fields=(),
            locked=True,
        )
        violations = contract.validate({"anything": "goes"})
        assert violations == []

    def test_validate_multiple_violations(self) -> None:
        """Multiple problems return multiple violations."""
        from elspeth.contracts.errors import MissingFieldViolation, TypeMismatchViolation

        contract = SchemaContract(
            mode="FIXED",
            fields=(
                FieldContract("a", "A", int, True, "declared"),
                FieldContract("b", "B", str, True, "declared"),
            ),
            locked=True,
        )
        violations = contract.validate({"a": "wrong_type"})  # Missing b, wrong type a

        assert len(violations) == 2
        types = {type(v) for v in violations}
        assert MissingFieldViolation in types
        assert TypeMismatchViolation in types


# --- Checkpoint Serialization Tests ---


class TestSchemaContractCheckpoint:
    """Test checkpoint serialization/deserialization."""

    @pytest.fixture
    def sample_contract(self) -> SchemaContract:
        """Sample contract for testing."""
        return SchemaContract(
            mode="FLEXIBLE",
            fields=(
                FieldContract("amount", "'Amount USD'", int, True, "declared"),
                FieldContract("note", "Note", str, False, "inferred"),
            ),
            locked=True,
        )

    def test_version_hash_deterministic(self, sample_contract: SchemaContract) -> None:
        """version_hash() returns same value for same contract."""
        hash1 = sample_contract.version_hash()
        hash2 = sample_contract.version_hash()
        assert hash1 == hash2
        assert len(hash1) == 16  # Truncated SHA-256

    def test_version_hash_changes_on_field_change(self) -> None:
        """Different fields produce different hashes."""
        c1 = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("a", "A", int, True, "declared"),),
            locked=True,
        )
        c2 = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("b", "B", int, True, "declared"),),
            locked=True,
        )
        assert c1.version_hash() != c2.version_hash()

    def test_version_hash_changes_on_type_change(self) -> None:
        """Different type produces different hash."""
        c1 = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("a", "A", int, True, "declared"),),
            locked=True,
        )
        c2 = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("a", "A", str, True, "declared"),),
            locked=True,
        )
        assert c1.version_hash() != c2.version_hash()

    def test_to_checkpoint_format(self, sample_contract: SchemaContract) -> None:
        """to_checkpoint_format() returns serializable dict."""
        data = sample_contract.to_checkpoint_format()

        assert data["mode"] == "FLEXIBLE"
        assert data["locked"] is True
        assert "version_hash" in data
        assert len(data["fields"]) == 2
        assert data["fields"][0]["normalized_name"] == "amount"
        assert data["fields"][0]["python_type"] == "int"

    def test_from_checkpoint_round_trip(self, sample_contract: SchemaContract) -> None:
        """Contract survives checkpoint round-trip."""
        data = sample_contract.to_checkpoint_format()
        restored = SchemaContract.from_checkpoint(data)

        assert restored.mode == sample_contract.mode
        assert restored.locked == sample_contract.locked
        assert len(restored.fields) == len(sample_contract.fields)
        assert restored.fields[0].normalized_name == "amount"
        assert restored.fields[0].python_type is int

    def test_from_checkpoint_validates_hash(self, sample_contract: SchemaContract) -> None:
        """from_checkpoint() validates hash integrity."""
        data = sample_contract.to_checkpoint_format()
        data["version_hash"] = "corrupted_hash"

        with pytest.raises(ValueError, match="integrity"):
            SchemaContract.from_checkpoint(data)

    def test_from_checkpoint_unknown_type_crashes(self) -> None:
        """from_checkpoint() crashes on unknown type (Tier 1 integrity)."""
        data = {
            "mode": "FIXED",
            "locked": True,
            "fields": [
                {
                    "normalized_name": "x",
                    "original_name": "X",
                    "python_type": "UnknownType",
                    "required": True,
                    "source": "declared",
                }
            ],
        }
        with pytest.raises(KeyError):
            SchemaContract.from_checkpoint(data)

    def test_from_checkpoint_nonetype_round_trip(self) -> None:
        """type(None) survives checkpoint round-trip."""
        contract = SchemaContract(
            mode="OBSERVED",
            fields=(FieldContract("x", "X", type(None), False, "inferred"),),
            locked=True,
        )
        data = contract.to_checkpoint_format()
        restored = SchemaContract.from_checkpoint(data)

        assert restored.fields[0].python_type is type(None)


# --- Merge Tests for Coalesce ---


class TestSchemaContractMerge:
    """Test contract merging for fork/join coalesce."""

    def test_merge_same_field_same_type(self) -> None:
        """Same field, same type merges successfully."""
        from elspeth.contracts.errors import ContractMergeError  # noqa: F401 - imported for test setup

        c1 = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("x", "X", int, True, "declared"),),
            locked=True,
        )
        c2 = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("x", "X", int, True, "declared"),),
            locked=True,
        )
        merged = c1.merge(c2)

        assert len(merged.fields) == 1
        assert merged.fields[0].python_type is int

    def test_merge_different_types_raises(self) -> None:
        """Different types raise ContractMergeError."""
        from elspeth.contracts.errors import ContractMergeError

        c1 = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("x", "X", int, True, "declared"),),
            locked=True,
        )
        c2 = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("x", "X", str, True, "declared"),),
            locked=True,
        )
        with pytest.raises(ContractMergeError, match="conflicting types"):
            c1.merge(c2)

    def test_merge_field_only_in_one_path_becomes_optional(self) -> None:
        """Field in only one path becomes optional (required=False)."""
        c1 = SchemaContract(
            mode="FLEXIBLE",
            fields=(
                FieldContract("x", "X", int, True, "declared"),
                FieldContract("y", "Y", str, True, "declared"),
            ),
            locked=True,
        )
        c2 = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("x", "X", int, True, "declared"),),
            locked=True,
        )
        merged = c1.merge(c2)

        # y is only in c1, so becomes optional in merged
        y_field = next(f for f in merged.fields if f.normalized_name == "y")
        assert y_field.required is False

    def test_merge_mode_precedence(self) -> None:
        """Most restrictive mode wins: FIXED > FLEXIBLE > OBSERVED."""
        fixed = SchemaContract(mode="FIXED", fields=(), locked=True)
        flexible = SchemaContract(mode="FLEXIBLE", fields=(), locked=True)
        observed = SchemaContract(mode="OBSERVED", fields=(), locked=True)

        assert fixed.merge(observed).mode == "FIXED"
        assert observed.merge(fixed).mode == "FIXED"
        assert flexible.merge(observed).mode == "FLEXIBLE"

    def test_merge_locked_if_either_locked(self) -> None:
        """Merged contract is locked if either input is locked."""
        locked = SchemaContract(mode="OBSERVED", fields=(), locked=True)
        unlocked = SchemaContract(mode="OBSERVED", fields=(), locked=False)

        assert locked.merge(unlocked).locked is True
        assert unlocked.merge(locked).locked is True

    def test_merge_required_if_either_required(self) -> None:
        """Field is required if required in either path."""
        c1 = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("x", "X", int, True, "declared"),),
            locked=True,
        )
        c2 = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("x", "X", int, False, "inferred"),),
            locked=True,
        )
        merged = c1.merge(c2)

        assert merged.fields[0].required is True

    def test_merge_source_declared_wins(self) -> None:
        """Field source is 'declared' if either is declared."""
        c1 = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("x", "X", int, True, "declared"),),
            locked=True,
        )
        c2 = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("x", "X", int, True, "inferred"),),
            locked=True,
        )
        merged = c1.merge(c2)

        assert merged.fields[0].source == "declared"

    def test_merge_empty_contracts(self) -> None:
        """Merging empty contracts works."""
        c1 = SchemaContract(mode="OBSERVED", fields=(), locked=True)
        c2 = SchemaContract(mode="OBSERVED", fields=(), locked=True)
        merged = c1.merge(c2)

        assert len(merged.fields) == 0
