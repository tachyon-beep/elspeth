"""Tests for contract audit record types.

These types bridge SchemaContract (runtime) to Landscape storage (JSON).
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from elspeth.contracts.errors import (
    ContractViolation,
    ExtraFieldViolation,
    MissingFieldViolation,
    TypeMismatchViolation,
)
from elspeth.contracts.schema_contract import FieldContract, SchemaContract

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_field_contract() -> FieldContract:
    """Sample FieldContract for testing."""
    return FieldContract(
        normalized_name="amount_usd",
        original_name="'Amount USD'",
        python_type=float,
        required=True,
        source="declared",
    )


@pytest.fixture
def sample_schema_contract() -> SchemaContract:
    """Sample SchemaContract for testing."""
    return SchemaContract(
        mode="FLEXIBLE",
        fields=(
            FieldContract(
                normalized_name="customer_id",
                original_name="Customer ID",
                python_type=str,
                required=True,
                source="declared",
            ),
            FieldContract(
                normalized_name="amount",
                original_name="'Amount'",
                python_type=int,
                required=True,
                source="declared",
            ),
            FieldContract(
                normalized_name="note",
                original_name="Note",
                python_type=str,
                required=False,
                source="inferred",
            ),
        ),
        locked=True,
    )


# =============================================================================
# FieldAuditRecord Tests
# =============================================================================


class TestFieldAuditRecord:
    """Tests for FieldAuditRecord."""

    def test_create_from_field_contract(self, sample_field_contract: FieldContract) -> None:
        """Create FieldAuditRecord from FieldContract."""
        from elspeth.contracts.contract_records import FieldAuditRecord

        record = FieldAuditRecord.from_field_contract(sample_field_contract)

        assert record.normalized_name == "amount_usd"
        assert record.original_name == "'Amount USD'"
        assert record.python_type == "float"
        assert record.required is True
        assert record.source == "declared"

    def test_frozen_immutable(self, sample_field_contract: FieldContract) -> None:
        """FieldAuditRecord is immutable (frozen dataclass)."""
        from elspeth.contracts.contract_records import FieldAuditRecord

        record = FieldAuditRecord.from_field_contract(sample_field_contract)

        with pytest.raises(AttributeError):
            record.normalized_name = "other"  # type: ignore[misc]

    def test_to_dict(self, sample_field_contract: FieldContract) -> None:
        """to_dict() returns JSON-serializable dict."""
        from elspeth.contracts.contract_records import FieldAuditRecord

        record = FieldAuditRecord.from_field_contract(sample_field_contract)
        d = record.to_dict()

        assert d == {
            "normalized_name": "amount_usd",
            "original_name": "'Amount USD'",
            "python_type": "float",
            "required": True,
            "source": "declared",
        }

        # Verify JSON serializable
        json_str = json.dumps(d)
        assert '"python_type": "float"' in json_str

    def test_all_supported_types(self) -> None:
        """Test all supported python types are converted correctly."""
        from elspeth.contracts.contract_records import FieldAuditRecord

        type_tests = [
            (int, "int"),
            (str, "str"),
            (float, "float"),
            (bool, "bool"),
            (type(None), "NoneType"),
            (datetime, "datetime"),
            (object, "object"),
        ]

        for python_type, expected_name in type_tests:
            fc = FieldContract(
                normalized_name="test",
                original_name="Test",
                python_type=python_type,
                required=True,
                source="declared",
            )
            record = FieldAuditRecord.from_field_contract(fc)
            assert record.python_type == expected_name, f"Failed for {python_type}"


# =============================================================================
# ContractAuditRecord Tests
# =============================================================================


class TestContractAuditRecord:
    """Tests for ContractAuditRecord."""

    def test_create_from_contract(self, sample_schema_contract: SchemaContract) -> None:
        """Create ContractAuditRecord from SchemaContract."""
        from elspeth.contracts.contract_records import ContractAuditRecord

        record = ContractAuditRecord.from_contract(sample_schema_contract)

        assert record.mode == "FLEXIBLE"
        assert record.locked is True
        assert len(record.fields) == 3
        assert record.version_hash == sample_schema_contract.version_hash()

    def test_frozen_immutable(self, sample_schema_contract: SchemaContract) -> None:
        """ContractAuditRecord is immutable (frozen dataclass)."""
        from elspeth.contracts.contract_records import ContractAuditRecord

        record = ContractAuditRecord.from_contract(sample_schema_contract)

        with pytest.raises(AttributeError):
            record.mode = "FIXED"  # type: ignore[misc]

    def test_to_json_uses_canonical(self, sample_schema_contract: SchemaContract) -> None:
        """to_json() uses canonical JSON serialization."""
        from elspeth.contracts.contract_records import ContractAuditRecord

        record = ContractAuditRecord.from_contract(sample_schema_contract)
        json_str = record.to_json()

        # Verify it's valid JSON
        parsed = json.loads(json_str)
        assert parsed["mode"] == "FLEXIBLE"
        assert parsed["locked"] is True

        # Verify deterministic (no whitespace, sorted keys)
        json_str2 = record.to_json()
        assert json_str == json_str2

    def test_from_json_round_trip(self, sample_schema_contract: SchemaContract) -> None:
        """ContractAuditRecord survives JSON round-trip."""
        from elspeth.contracts.contract_records import ContractAuditRecord

        original = ContractAuditRecord.from_contract(sample_schema_contract)
        json_str = original.to_json()
        restored = ContractAuditRecord.from_json(json_str)

        assert restored.mode == original.mode
        assert restored.locked == original.locked
        assert restored.version_hash == original.version_hash
        assert len(restored.fields) == len(original.fields)

        # Verify fields match
        for orig_field, rest_field in zip(original.fields, restored.fields, strict=True):
            assert orig_field.normalized_name == rest_field.normalized_name
            assert orig_field.python_type == rest_field.python_type

    def test_to_schema_contract_round_trip(self, sample_schema_contract: SchemaContract) -> None:
        """to_schema_contract() restores equivalent SchemaContract."""
        from elspeth.contracts.contract_records import ContractAuditRecord

        record = ContractAuditRecord.from_contract(sample_schema_contract)
        restored = record.to_schema_contract()

        assert restored.mode == sample_schema_contract.mode
        assert restored.locked == sample_schema_contract.locked
        assert len(restored.fields) == len(sample_schema_contract.fields)

        # Verify hash matches (integrity)
        assert restored.version_hash() == sample_schema_contract.version_hash()

    def test_to_schema_contract_verifies_integrity(self) -> None:
        """to_schema_contract() raises on integrity violation."""
        from elspeth.contracts.contract_records import (
            ContractAuditRecord,
            FieldAuditRecord,
        )

        # Manually create a record with mismatched hash
        record = ContractAuditRecord(
            mode="FIXED",
            locked=True,
            version_hash="corrupted_hash",
            fields=(
                FieldAuditRecord(
                    normalized_name="x",
                    original_name="X",
                    python_type="int",
                    required=True,
                    source="declared",
                ),
            ),
        )

        with pytest.raises(ValueError, match="integrity"):
            record.to_schema_contract()

    def test_fields_tuple_immutable(self, sample_schema_contract: SchemaContract) -> None:
        """fields is a tuple (immutable)."""
        from elspeth.contracts.contract_records import ContractAuditRecord

        record = ContractAuditRecord.from_contract(sample_schema_contract)

        assert isinstance(record.fields, tuple)

    def test_all_modes(self) -> None:
        """Test all schema modes are supported."""
        from elspeth.contracts.contract_records import ContractAuditRecord

        for mode in ("FIXED", "FLEXIBLE", "OBSERVED"):
            contract = SchemaContract(mode=mode, fields=(), locked=True)  # type: ignore[arg-type]
            record = ContractAuditRecord.from_contract(contract)
            assert record.mode == mode

            # Round-trip
            restored = record.to_schema_contract()
            assert restored.mode == mode

    def test_nonetype_round_trip(self) -> None:
        """type(None) survives full round-trip."""
        from elspeth.contracts.contract_records import ContractAuditRecord

        contract = SchemaContract(
            mode="OBSERVED",
            fields=(FieldContract("x", "X", type(None), False, "inferred"),),
            locked=True,
        )
        record = ContractAuditRecord.from_contract(contract)
        json_str = record.to_json()
        restored_record = ContractAuditRecord.from_json(json_str)
        restored_contract = restored_record.to_schema_contract()

        assert restored_contract.fields[0].python_type is type(None)

    def test_datetime_round_trip(self) -> None:
        """datetime type survives full round-trip."""
        from elspeth.contracts.contract_records import ContractAuditRecord

        contract = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("ts", "Timestamp", datetime, True, "declared"),),
            locked=True,
        )
        record = ContractAuditRecord.from_contract(contract)
        json_str = record.to_json()
        restored_record = ContractAuditRecord.from_json(json_str)
        restored_contract = restored_record.to_schema_contract()

        assert restored_contract.fields[0].python_type is datetime

    def test_object_type_round_trip(self) -> None:
        """object type (any) survives full round-trip."""
        from elspeth.contracts.contract_records import ContractAuditRecord

        contract = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("data", "Data", object, True, "declared"),),
            locked=True,
        )
        record = ContractAuditRecord.from_contract(contract)
        json_str = record.to_json()
        restored_record = ContractAuditRecord.from_json(json_str)
        restored_contract = restored_record.to_schema_contract()

        assert restored_contract.fields[0].python_type is object


# =============================================================================
# ValidationErrorWithContract Tests
# =============================================================================


class TestValidationErrorWithContract:
    """Tests for ValidationErrorWithContract."""

    def test_from_missing_field_violation(self) -> None:
        """Create from MissingFieldViolation."""
        from elspeth.contracts.contract_records import ValidationErrorWithContract

        violation = MissingFieldViolation(
            normalized_name="customer_id",
            original_name="Customer ID",
        )
        record = ValidationErrorWithContract.from_violation(violation)

        assert record.violation_type == "missing_field"
        assert record.normalized_field_name == "customer_id"
        assert record.original_field_name == "Customer ID"
        assert record.expected_type is None
        assert record.actual_type is None

    def test_from_type_mismatch_violation(self) -> None:
        """Create from TypeMismatchViolation."""
        from elspeth.contracts.contract_records import ValidationErrorWithContract

        violation = TypeMismatchViolation(
            normalized_name="amount",
            original_name="'Amount'",
            expected_type=int,
            actual_type=str,
            actual_value="not_a_number",
        )
        record = ValidationErrorWithContract.from_violation(violation)

        assert record.violation_type == "type_mismatch"
        assert record.normalized_field_name == "amount"
        assert record.original_field_name == "'Amount'"
        assert record.expected_type == "int"
        assert record.actual_type == "str"

    def test_from_extra_field_violation(self) -> None:
        """Create from ExtraFieldViolation."""
        from elspeth.contracts.contract_records import ValidationErrorWithContract

        violation = ExtraFieldViolation(
            normalized_name="unknown",
            original_name="Unknown Col",
        )
        record = ValidationErrorWithContract.from_violation(violation)

        assert record.violation_type == "extra_field"
        assert record.normalized_field_name == "unknown"
        assert record.original_field_name == "Unknown Col"
        assert record.expected_type is None
        assert record.actual_type is None

    def test_frozen_immutable(self) -> None:
        """ValidationErrorWithContract is immutable (frozen dataclass)."""
        from elspeth.contracts.contract_records import ValidationErrorWithContract

        violation = MissingFieldViolation(
            normalized_name="x",
            original_name="X",
        )
        record = ValidationErrorWithContract.from_violation(violation)

        with pytest.raises(AttributeError):
            record.violation_type = "other"  # type: ignore[assignment,misc]

    def test_unknown_violation_type_raises(self) -> None:
        """Unknown violation type raises ValueError."""
        from elspeth.contracts.contract_records import ValidationErrorWithContract

        # Create a custom violation type not in our mapping
        class CustomViolation(ContractViolation):
            pass

        violation = CustomViolation(normalized_name="x", original_name="X")

        with pytest.raises(ValueError, match="Unknown violation type"):
            ValidationErrorWithContract.from_violation(violation)


# =============================================================================
# Integration Tests
# =============================================================================


class TestContractRecordsIntegration:
    """Integration tests for contract audit records."""

    def test_full_audit_trail_round_trip(self, sample_schema_contract: SchemaContract) -> None:
        """Full round-trip: SchemaContract -> JSON -> ContractAuditRecord -> SchemaContract."""
        from elspeth.contracts.contract_records import ContractAuditRecord

        # Convert to audit record
        audit_record = ContractAuditRecord.from_contract(sample_schema_contract)

        # Serialize to JSON (as would be stored in Landscape)
        json_str = audit_record.to_json()

        # Verify JSON is deterministic
        assert json_str == audit_record.to_json()

        # Restore from JSON
        restored_record = ContractAuditRecord.from_json(json_str)

        # Convert back to SchemaContract
        restored_contract = restored_record.to_schema_contract()

        # Verify equivalence
        assert restored_contract.mode == sample_schema_contract.mode
        assert restored_contract.locked == sample_schema_contract.locked
        assert restored_contract.version_hash() == sample_schema_contract.version_hash()

        # Verify validation still works
        violations = restored_contract.validate({"customer_id": "C123", "amount": 100})
        assert violations == []

    def test_audit_record_with_validation_errors(self, sample_schema_contract: SchemaContract) -> None:
        """Audit record can capture validation errors."""
        from elspeth.contracts.contract_records import ValidationErrorWithContract

        # Generate violations
        violations = sample_schema_contract.validate(
            {"customer_id": 123}  # Wrong type for customer_id, missing amount
        )

        # Convert to audit records
        error_records = [ValidationErrorWithContract.from_violation(v) for v in violations]

        # Verify we captured the errors
        assert len(error_records) == 2

        # Find the type mismatch
        type_errors = [e for e in error_records if e.violation_type == "type_mismatch"]
        assert len(type_errors) == 1
        assert type_errors[0].normalized_field_name == "customer_id"

        # Find the missing field
        missing_errors = [e for e in error_records if e.violation_type == "missing_field"]
        assert len(missing_errors) == 1
        assert missing_errors[0].normalized_field_name == "amount"
