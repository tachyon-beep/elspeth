"""Tests for ContractAwareRow - enables dual-name access in Jinja2 templates."""

import pytest

from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.plugins.llm.contract_aware_row import ContractAwareRow


class TestContractAwareRow:
    """Test dual-name access via ContractAwareRow."""

    @pytest.fixture
    def contract(self) -> SchemaContract:
        """Contract with original name mappings."""
        return SchemaContract(
            mode="FLEXIBLE",
            fields=(
                FieldContract("amount_usd", "'Amount USD'", int, True, "declared"),
                FieldContract("customer_id", "Customer ID", str, True, "declared"),
                FieldContract("simple", "simple", str, True, "declared"),
            ),
            locked=True,
        )

    @pytest.fixture
    def data(self) -> dict[str, object]:
        """Row data with normalized keys."""
        return {
            "amount_usd": 100,
            "customer_id": "C001",
            "simple": "value",
        }

    def test_access_by_normalized_name(self, data: dict[str, object], contract: SchemaContract) -> None:
        """Access by normalized name works."""
        row = ContractAwareRow(data, contract)

        assert row["amount_usd"] == 100
        assert row["customer_id"] == "C001"

    def test_access_by_original_name(self, data: dict[str, object], contract: SchemaContract) -> None:
        """Access by original name works."""
        row = ContractAwareRow(data, contract)

        assert row["'Amount USD'"] == 100
        assert row["Customer ID"] == "C001"

    def test_access_by_attribute(self, data: dict[str, object], contract: SchemaContract) -> None:
        """Dot notation access works for normalized names."""
        row = ContractAwareRow(data, contract)

        assert row.amount_usd == 100
        assert row.customer_id == "C001"

    def test_contains_normalized(self, data: dict[str, object], contract: SchemaContract) -> None:
        """'in' operator works with normalized names."""
        row = ContractAwareRow(data, contract)

        assert "amount_usd" in row
        assert "customer_id" in row
        assert "nonexistent" not in row

    def test_contains_original(self, data: dict[str, object], contract: SchemaContract) -> None:
        """'in' operator works with original names."""
        row = ContractAwareRow(data, contract)

        assert "'Amount USD'" in row
        assert "Customer ID" in row

    def test_keys_returns_normalized(self, data: dict[str, object], contract: SchemaContract) -> None:
        """keys() returns normalized names for iteration."""
        row = ContractAwareRow(data, contract)

        keys = list(row.keys())

        assert "amount_usd" in keys
        assert "'Amount USD'" not in keys  # Normalized only

    def test_missing_field_raises_keyerror(self, data: dict[str, object], contract: SchemaContract) -> None:
        """Unknown field raises KeyError."""
        row = ContractAwareRow(data, contract)

        with pytest.raises(KeyError, match="nonexistent"):
            _ = row["nonexistent"]

    def test_missing_attr_raises_attributeerror(self, data: dict[str, object], contract: SchemaContract) -> None:
        """Unknown attribute raises AttributeError."""
        row = ContractAwareRow(data, contract)

        with pytest.raises(AttributeError, match="nonexistent"):
            _ = row.nonexistent

    def test_private_attr_raises_attributeerror(self, data: dict[str, object], contract: SchemaContract) -> None:
        """Private attributes raise AttributeError (not delegated)."""
        row = ContractAwareRow(data, contract)

        with pytest.raises(AttributeError):
            _ = row._private

    def test_get_with_default(self, data: dict[str, object], contract: SchemaContract) -> None:
        """get() method supports default values."""
        row = ContractAwareRow(data, contract)

        assert row.get("amount_usd") == 100
        assert row.get("'Amount USD'") == 100
        assert row.get("nonexistent", "default") == "default"
        assert row.get("nonexistent") is None

    def test_iteration_yields_normalized_keys(self, data: dict[str, object], contract: SchemaContract) -> None:
        """Iteration yields normalized keys."""
        row = ContractAwareRow(data, contract)

        keys = list(row)

        assert set(keys) == {"amount_usd", "customer_id", "simple"}


class TestContractAwareRowContainsMembership:
    """Test __contains__ reflects actual data presence, not just contract.

    P2 bug: __contains__ was checking the contract, not the actual data.
    This broke template conditionals like {% if "optional" in row %}.
    """

    @pytest.fixture
    def contract_with_optional(self) -> SchemaContract:
        """Contract with both required and optional fields."""
        return SchemaContract(
            mode="FLEXIBLE",
            fields=(
                FieldContract("id", "ID", int, True, "declared"),  # required
                FieldContract("name", "Name", str, True, "declared"),  # required
                FieldContract("notes", "Notes", str, False, "declared"),  # optional
            ),
            locked=True,
        )

    def test_contains_returns_true_when_data_present(self, contract_with_optional: SchemaContract) -> None:
        """__contains__ returns True when field exists in actual data."""
        data = {"id": 1, "name": "Alice", "notes": "Some notes"}
        row = ContractAwareRow(data, contract_with_optional)

        assert "id" in row
        assert "name" in row
        assert "notes" in row

    def test_contains_returns_false_when_data_missing(self, contract_with_optional: SchemaContract) -> None:
        """__contains__ returns False when field is in contract but not in data.

        This is the P2 bug: __contains__ was returning True because "notes"
        exists in the contract, even though the actual data doesn't have it.
        """
        data = {"id": 1, "name": "Alice"}  # notes is MISSING from data
        row = ContractAwareRow(data, contract_with_optional)

        assert "id" in row  # Present in data
        assert "name" in row  # Present in data
        assert "notes" not in row  # NOT in data, even though in contract

    def test_contains_works_with_original_names(self, contract_with_optional: SchemaContract) -> None:
        """__contains__ works with original names when data present."""
        data = {"id": 1, "name": "Alice", "notes": "Some notes"}
        row = ContractAwareRow(data, contract_with_optional)

        assert "ID" in row  # Original name, data present
        assert "Name" in row
        assert "Notes" in row

    def test_contains_with_original_names_returns_false_when_data_missing(self, contract_with_optional: SchemaContract) -> None:
        """__contains__ returns False for original names when data missing."""
        data = {"id": 1, "name": "Alice"}  # notes missing
        row = ContractAwareRow(data, contract_with_optional)

        assert "Notes" not in row  # Original name, data missing

    def test_template_conditional_pattern(self, contract_with_optional: SchemaContract) -> None:
        """Template pattern {% if "field" in row %} works correctly.

        This is the exact use case that was broken by the P2 bug.
        """
        data_with_notes = {"id": 1, "name": "Alice", "notes": "Some notes"}
        data_without_notes = {"id": 1, "name": "Alice"}

        row_with = ContractAwareRow(data_with_notes, contract_with_optional)
        row_without = ContractAwareRow(data_without_notes, contract_with_optional)

        # With notes: should be able to access
        if "notes" in row_with:
            value = row_with["notes"]
            assert value == "Some notes"

        # Without notes: membership check should prevent access
        if "notes" in row_without:
            # This block should NOT execute
            pytest.fail("Should not enter this block when data is missing")
