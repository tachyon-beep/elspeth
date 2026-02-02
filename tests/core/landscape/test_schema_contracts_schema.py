# tests/core/landscape/test_schema_contracts_schema.py
"""Tests for schema contract columns in Landscape tables.

Phase 5 Unified Schema Contracts: These columns store schema contracts
in the audit trail for complete field mapping traceability.
"""

from sqlalchemy import create_engine, inspect


class TestRunsSchemaContractColumns:
    """Tests for schema contract columns in runs table."""

    def test_runs_table_has_schema_contract_json_column(self) -> None:
        """runs table should have schema_contract_json column for full contract storage."""
        from elspeth.core.landscape.schema import runs_table

        columns = {c.name for c in runs_table.columns}
        assert "schema_contract_json" in columns

    def test_runs_table_has_schema_contract_hash_column(self) -> None:
        """runs table should have schema_contract_hash column for integrity verification."""
        from elspeth.core.landscape.schema import runs_table

        columns = {c.name for c in runs_table.columns}
        assert "schema_contract_hash" in columns

    def test_schema_contract_json_is_nullable(self) -> None:
        """schema_contract_json should be nullable for backward compatibility."""
        from elspeth.core.landscape.schema import runs_table

        columns = {c.name: c for c in runs_table.columns}
        assert columns["schema_contract_json"].nullable is True

    def test_schema_contract_hash_is_nullable(self) -> None:
        """schema_contract_hash should be nullable for backward compatibility."""
        from elspeth.core.landscape.schema import runs_table

        columns = {c.name: c for c in runs_table.columns}
        assert columns["schema_contract_hash"].nullable is True

    def test_schema_contract_hash_length(self) -> None:
        """schema_contract_hash should be String(16) per design (truncated SHA256)."""
        from elspeth.core.landscape.schema import runs_table

        columns = {c.name: c for c in runs_table.columns}
        # String type has length attribute
        assert columns["schema_contract_hash"].type.length == 16


class TestNodesContractColumns:
    """Tests for schema contract columns in nodes table."""

    def test_nodes_table_has_input_contract_json_column(self) -> None:
        """nodes table should have input_contract_json column for input requirements."""
        from elspeth.core.landscape.schema import nodes_table

        columns = {c.name for c in nodes_table.columns}
        assert "input_contract_json" in columns

    def test_nodes_table_has_output_contract_json_column(self) -> None:
        """nodes table should have output_contract_json column for output guarantees."""
        from elspeth.core.landscape.schema import nodes_table

        columns = {c.name for c in nodes_table.columns}
        assert "output_contract_json" in columns

    def test_input_contract_json_is_nullable(self) -> None:
        """input_contract_json should be nullable for backward compatibility."""
        from elspeth.core.landscape.schema import nodes_table

        columns = {c.name: c for c in nodes_table.columns}
        assert columns["input_contract_json"].nullable is True

    def test_output_contract_json_is_nullable(self) -> None:
        """output_contract_json should be nullable for backward compatibility."""
        from elspeth.core.landscape.schema import nodes_table

        columns = {c.name: c for c in nodes_table.columns}
        assert columns["output_contract_json"].nullable is True


class TestValidationErrorsContractColumns:
    """Tests for schema contract columns in validation_errors table."""

    def test_validation_errors_has_violation_type_column(self) -> None:
        """validation_errors table should have violation_type column."""
        from elspeth.core.landscape.schema import validation_errors_table

        columns = {c.name for c in validation_errors_table.columns}
        assert "violation_type" in columns

    def test_validation_errors_has_original_field_name_column(self) -> None:
        """validation_errors table should have original_field_name column."""
        from elspeth.core.landscape.schema import validation_errors_table

        columns = {c.name for c in validation_errors_table.columns}
        assert "original_field_name" in columns

    def test_validation_errors_has_normalized_field_name_column(self) -> None:
        """validation_errors table should have normalized_field_name column."""
        from elspeth.core.landscape.schema import validation_errors_table

        columns = {c.name for c in validation_errors_table.columns}
        assert "normalized_field_name" in columns

    def test_validation_errors_has_expected_type_column(self) -> None:
        """validation_errors table should have expected_type column."""
        from elspeth.core.landscape.schema import validation_errors_table

        columns = {c.name for c in validation_errors_table.columns}
        assert "expected_type" in columns

    def test_validation_errors_has_actual_type_column(self) -> None:
        """validation_errors table should have actual_type column."""
        from elspeth.core.landscape.schema import validation_errors_table

        columns = {c.name for c in validation_errors_table.columns}
        assert "actual_type" in columns

    def test_violation_type_is_nullable(self) -> None:
        """violation_type should be nullable for backward compatibility."""
        from elspeth.core.landscape.schema import validation_errors_table

        columns = {c.name: c for c in validation_errors_table.columns}
        assert columns["violation_type"].nullable is True

    def test_violation_type_length(self) -> None:
        """violation_type should be String(32) per design."""
        from elspeth.core.landscape.schema import validation_errors_table

        columns = {c.name: c for c in validation_errors_table.columns}
        assert columns["violation_type"].type.length == 32

    def test_original_field_name_length(self) -> None:
        """original_field_name should be String(256) per design."""
        from elspeth.core.landscape.schema import validation_errors_table

        columns = {c.name: c for c in validation_errors_table.columns}
        assert columns["original_field_name"].type.length == 256

    def test_normalized_field_name_length(self) -> None:
        """normalized_field_name should be String(256) per design."""
        from elspeth.core.landscape.schema import validation_errors_table

        columns = {c.name: c for c in validation_errors_table.columns}
        assert columns["normalized_field_name"].type.length == 256

    def test_expected_type_length(self) -> None:
        """expected_type should be String(32) per design."""
        from elspeth.core.landscape.schema import validation_errors_table

        columns = {c.name: c for c in validation_errors_table.columns}
        assert columns["expected_type"].type.length == 32

    def test_actual_type_length(self) -> None:
        """actual_type should be String(32) per design."""
        from elspeth.core.landscape.schema import validation_errors_table

        columns = {c.name: c for c in validation_errors_table.columns}
        assert columns["actual_type"].type.length == 32


class TestSchemaContractColumnsInDatabase:
    """Integration tests for schema contract columns in a real database."""

    def test_create_tables_with_contract_columns(self, tmp_path) -> None:
        """Verify all tables with contract columns can be created in database."""
        from elspeth.core.landscape.schema import metadata

        db_path = tmp_path / "test_contracts.db"
        engine = create_engine(f"sqlite:///{db_path}")
        metadata.create_all(engine)

        inspector = inspect(engine)

        # Verify runs table columns
        runs_columns = {col["name"] for col in inspector.get_columns("runs")}
        assert "schema_contract_json" in runs_columns
        assert "schema_contract_hash" in runs_columns

        # Verify nodes table columns
        nodes_columns = {col["name"] for col in inspector.get_columns("nodes")}
        assert "input_contract_json" in nodes_columns
        assert "output_contract_json" in nodes_columns

        # Verify validation_errors table columns
        ve_columns = {col["name"] for col in inspector.get_columns("validation_errors")}
        assert "violation_type" in ve_columns
        assert "original_field_name" in ve_columns
        assert "normalized_field_name" in ve_columns
        assert "expected_type" in ve_columns
        assert "actual_type" in ve_columns
