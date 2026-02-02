# tests/contracts/test_pipeline_row.py
"""Tests for PipelineRow wrapper class."""

import pytest

from elspeth.contracts.schema_contract import (
    FieldContract,
    PipelineRow,
    SchemaContract,
)


class TestPipelineRowAccess:
    """Test PipelineRow data access patterns."""

    @pytest.fixture
    def sample_row(self) -> PipelineRow:
        """Sample row with dual-name access."""
        contract = SchemaContract(
            mode="FLEXIBLE",
            fields=(
                FieldContract("amount_usd", "'Amount USD'", int, True, "declared"),
                FieldContract("customer_id", "Customer ID", str, True, "declared"),
            ),
            locked=True,
        )
        data = {"amount_usd": 100, "customer_id": "C123"}
        return PipelineRow(data, contract)

    def test_getitem_normalized_name(self, sample_row: PipelineRow) -> None:
        """Access by normalized name via bracket notation."""
        assert sample_row["amount_usd"] == 100

    def test_getitem_original_name(self, sample_row: PipelineRow) -> None:
        """Access by original name via bracket notation."""
        assert sample_row["'Amount USD'"] == 100

    def test_getattr_normalized_name(self, sample_row: PipelineRow) -> None:
        """Access by normalized name via dot notation."""
        assert sample_row.amount_usd == 100

    def test_getattr_unknown_raises(self, sample_row: PipelineRow) -> None:
        """Unknown attribute raises AttributeError."""
        with pytest.raises(AttributeError):
            _ = sample_row.nonexistent

    def test_getitem_unknown_raises(self, sample_row: PipelineRow) -> None:
        """Unknown key raises KeyError."""
        with pytest.raises(KeyError):
            _ = sample_row["nonexistent"]

    def test_contains_normalized(self, sample_row: PipelineRow) -> None:
        """'in' operator works with normalized name."""
        assert "amount_usd" in sample_row

    def test_contains_original(self, sample_row: PipelineRow) -> None:
        """'in' operator works with original name."""
        assert "'Amount USD'" in sample_row

    def test_contains_unknown_false(self, sample_row: PipelineRow) -> None:
        """'in' returns False for unknown fields."""
        assert "nonexistent" not in sample_row

    def test_to_dict_returns_raw_data(self, sample_row: PipelineRow) -> None:
        """to_dict() returns raw data with normalized keys."""
        d = sample_row.to_dict()
        assert d == {"amount_usd": 100, "customer_id": "C123"}
        assert isinstance(d, dict)

    def test_contract_property(self, sample_row: PipelineRow) -> None:
        """contract property provides access to schema."""
        assert sample_row.contract.mode == "FLEXIBLE"
        assert len(sample_row.contract.fields) == 2


class TestPipelineRowCheckpoint:
    """Test PipelineRow checkpoint serialization."""

    def test_to_checkpoint_format(self) -> None:
        """to_checkpoint_format() returns dict with data and contract ref."""
        contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("id", "ID", int, True, "declared"),),
            locked=True,
        )
        row = PipelineRow({"id": 42}, contract)
        checkpoint = row.to_checkpoint_format()

        assert checkpoint["data"] == {"id": 42}
        assert "contract_version" in checkpoint
        assert checkpoint["contract_version"] == contract.version_hash()

    def test_from_checkpoint_round_trip(self) -> None:
        """PipelineRow survives checkpoint round-trip."""
        contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("id", "ID", int, True, "declared"),),
            locked=True,
        )
        original = PipelineRow({"id": 42}, contract)

        # Serialize
        checkpoint = original.to_checkpoint_format()

        # Build registry (in real use, this comes from node checkpoints)
        registry = {contract.version_hash(): contract}

        # Restore
        restored = PipelineRow.from_checkpoint(checkpoint, registry)

        assert restored["id"] == 42
        assert restored.contract.version_hash() == contract.version_hash()

    def test_from_checkpoint_unknown_contract_raises(self) -> None:
        """from_checkpoint() raises if contract not in registry."""
        checkpoint = {
            "data": {"x": 1},
            "contract_version": "unknown_hash_123",
        }
        registry: dict[str, SchemaContract] = {}

        with pytest.raises(KeyError):
            PipelineRow.from_checkpoint(checkpoint, registry)


class TestPipelineRowSlots:
    """Test PipelineRow memory efficiency."""

    def test_uses_slots(self) -> None:
        """PipelineRow uses __slots__ for memory efficiency."""
        contract = SchemaContract(mode="OBSERVED", fields=(), locked=True)
        row = PipelineRow({}, contract)

        # __slots__ means no __dict__
        assert not hasattr(row, "__dict__")
        assert hasattr(row, "__slots__")

    def test_cannot_add_attributes(self) -> None:
        """Cannot add arbitrary attributes (slots restriction)."""
        contract = SchemaContract(mode="OBSERVED", fields=(), locked=True)
        row = PipelineRow({}, contract)

        with pytest.raises(AttributeError):
            row.new_attr = "value"  # type: ignore[attr-defined]


class TestPipelineRowImmutability:
    """Test PipelineRow data immutability for audit integrity."""

    def test_setitem_raises_typeerror(self) -> None:
        """Cannot mutate row via bracket notation (Tier 1 integrity)."""
        contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("amount", "Amount", int, True, "declared"),),
            locked=True,
        )
        row = PipelineRow({"amount": 100}, contract)

        with pytest.raises(TypeError, match=r"immutable.*audit"):
            row["amount"] = 200

    def test_original_dict_mutation_does_not_affect_row(self) -> None:
        """Mutating original dict does not affect PipelineRow (defensive copy)."""
        contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("amount", "Amount", int, True, "declared"),),
            locked=True,
        )
        original_data = {"amount": 100}
        row = PipelineRow(original_data, contract)

        # Mutate original dict
        original_data["amount"] = 999

        # Row should still have original value
        assert row["amount"] == 100

    def test_to_dict_mutation_does_not_affect_row(self) -> None:
        """Mutating to_dict() result does not affect PipelineRow."""
        contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("amount", "Amount", int, True, "declared"),),
            locked=True,
        )
        row = PipelineRow({"amount": 100}, contract)

        # Get dict and mutate it
        d = row.to_dict()
        d["amount"] = 999

        # Row should still have original value
        assert row["amount"] == 100
