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
