"""Tests for CSVSource schema contract integration."""

from pathlib import Path
from textwrap import dedent

import pytest

from elspeth.contracts.plugin_context import PluginContext
from elspeth.contracts.schema_contract import PipelineRow
from elspeth.plugins.sources.csv_source import CSVSource


@pytest.fixture
def temp_csv(tmp_path: Path) -> Path:
    """Create a temporary CSV file."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        dedent("""\
        id,name,score
        1,Alice,95.5
        2,Bob,87.0
    """)
    )
    return csv_file


@pytest.fixture
def mock_context() -> PluginContext:
    """Create a mock plugin context."""

    class MockContext:
        def record_validation_error(self, **kwargs: object) -> None:
            pass

    return MockContext()  # type: ignore[return-value]


class TestCSVSourceContract:
    """Test CSVSource schema contract integration."""

    def test_dynamic_schema_creates_observed_contract(self, temp_csv: Path, mock_context: PluginContext) -> None:
        """Dynamic schema creates OBSERVED mode contract."""
        source = CSVSource(
            {
                "path": str(temp_csv),
                "schema": {"mode": "observed"},
                "on_validation_failure": "quarantine",
                "on_success": "output",
            }
        )

        # Consume iterator to populate contract
        list(source.load(mock_context))

        contract = source.get_schema_contract()
        assert contract is not None
        assert contract.mode == "OBSERVED"
        assert contract.locked is True

    def test_strict_schema_creates_fixed_contract(self, temp_csv: Path, mock_context: PluginContext) -> None:
        """Strict schema creates FIXED mode contract."""
        source = CSVSource(
            {
                "path": str(temp_csv),
                "schema": {
                    "mode": "fixed",
                    "fields": ["id: int", "name: str", "score: float"],
                },
                "on_validation_failure": "quarantine",
                "on_success": "output",
            }
        )

        # Consume iterator to populate contract
        list(source.load(mock_context))

        contract = source.get_schema_contract()
        assert contract is not None
        assert contract.mode == "FIXED"

    def test_source_row_has_contract(self, temp_csv: Path, mock_context: PluginContext) -> None:
        """Valid SourceRows include contract reference."""
        source = CSVSource(
            {
                "path": str(temp_csv),
                "schema": {"mode": "observed"},
                "on_validation_failure": "quarantine",
                "on_success": "output",
            }
        )

        rows = list(source.load(mock_context))

        for row in rows:
            if not row.is_quarantined:
                assert row.contract is not None
                assert row.contract.locked is True

    def test_source_row_converts_to_pipeline_row(self, temp_csv: Path, mock_context: PluginContext) -> None:
        """SourceRow can convert to PipelineRow."""
        source = CSVSource(
            {
                "path": str(temp_csv),
                "schema": {"mode": "observed"},
                "on_validation_failure": "quarantine",
                "on_success": "output",
            }
        )

        rows = list(source.load(mock_context))
        source_row = rows[0]

        pipeline_row = source_row.to_pipeline_row()

        assert isinstance(pipeline_row, PipelineRow)
        # CSV values are strings unless schema coerces them
        assert pipeline_row["id"] == "1"
        assert pipeline_row["name"] == "Alice"

    def test_contract_includes_field_resolution(self, tmp_path: Path, mock_context: PluginContext) -> None:
        """Contract original_name populated from field resolution."""
        csv_file = tmp_path / "messy.csv"
        csv_file.write_text(
            dedent("""\
            'Amount USD',Customer ID
            100,C001
        """)
        )

        source = CSVSource(
            {
                "path": str(csv_file),
                "schema": {"mode": "observed"},
                "on_validation_failure": "quarantine",
                "on_success": "output",
                "normalize_fields": True,
            }
        )

        # Consume iterator to populate contract
        list(source.load(mock_context))
        contract = source.get_schema_contract()

        # Find the amount field
        assert contract is not None
        amount_field = next(f for f in contract.fields if f.normalized_name == "amount_usd")
        assert amount_field.original_name == "'Amount USD'"

    def test_inferred_types_from_first_row(self, temp_csv: Path, mock_context: PluginContext) -> None:
        """OBSERVED mode infers types from first row values."""
        source = CSVSource(
            {
                "path": str(temp_csv),
                "schema": {"mode": "observed"},
                "on_validation_failure": "quarantine",
                "on_success": "output",
            }
        )

        # Consume iterator to populate contract
        list(source.load(mock_context))
        contract = source.get_schema_contract()

        assert contract is not None
        type_map = {f.normalized_name: f.python_type for f in contract.fields}

        # With dynamic schema, all CSV values are strings (no coercion)
        assert "id" in type_map
        assert "name" in type_map
        assert "score" in type_map

    def test_empty_source_locks_contract(self, tmp_path: Path, mock_context: PluginContext) -> None:
        """Contract is locked even if all rows are quarantined."""
        csv_file = tmp_path / "all_bad.csv"
        csv_file.write_text(
            dedent("""\
            id,amount
            not_int,100
            also_not_int,200
        """)
        )

        source = CSVSource(
            {
                "path": str(csv_file),
                "schema": {
                    "mode": "fixed",
                    "fields": ["id: int", "amount: int"],
                },
                "on_validation_failure": "quarantine",
                "on_success": "output",
            }
        )

        rows = list(source.load(mock_context))

        # All rows should be quarantined (id field not coercible to int)
        assert all(r.is_quarantined for r in rows)

        # Contract should still be locked
        contract = source.get_schema_contract()
        assert contract is not None
        assert contract.locked is True
