"""Tests for DatabaseSink output target schema validation."""

from pathlib import Path

import pytest
from sqlalchemy import Column, MetaData, String, Table, create_engine

from elspeth.plugins.sinks.database_sink import DatabaseSink


@pytest.fixture
def sqlite_path(tmp_path: Path) -> str:
    """Return a SQLite database URL."""
    return f"sqlite:///{tmp_path / 'test.db'}"


def _create_table_with_columns(url: str, table_name: str, columns: list[str]) -> None:
    """Create a table with the given column names (all as String type)."""
    engine = create_engine(url)
    metadata = MetaData()
    Table(
        table_name,
        metadata,
        *[Column(col, String) for col in columns],
    )
    metadata.create_all(engine)
    engine.dispose()


class TestDatabaseSinkValidateOutputTarget:
    """Tests for DatabaseSink.validate_output_target()."""

    def test_validate_nonexistent_table_returns_success(self, sqlite_path: str):
        """When table doesn't exist, validation should pass (will create)."""
        sink = DatabaseSink(
            {
                "url": sqlite_path,
                "table": "output_data",
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True
        sink.close()

    def test_validate_dynamic_schema_skips_validation(self, sqlite_path: str):
        """Dynamic schema should always pass validation."""
        _create_table_with_columns(sqlite_path, "output_data", ["wrong", "columns"])
        sink = DatabaseSink(
            {
                "url": sqlite_path,
                "table": "output_data",
                "schema": {"fields": "dynamic"},
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True
        assert set(result.target_fields) == {"wrong", "columns"}
        sink.close()


class TestDatabaseSinkStrictModeValidation:
    """Tests for strict mode schema validation."""

    def test_validate_strict_mode_exact_match(self, sqlite_path: str):
        """Strict mode should pass when columns match exactly."""
        _create_table_with_columns(sqlite_path, "output_data", ["id", "name"])
        sink = DatabaseSink(
            {
                "url": sqlite_path,
                "table": "output_data",
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True
        sink.close()

    def test_validate_strict_mode_missing_column(self, sqlite_path: str):
        """Strict mode should fail when schema column is missing from table."""
        _create_table_with_columns(sqlite_path, "output_data", ["id"])  # Missing 'name'
        sink = DatabaseSink(
            {
                "url": sqlite_path,
                "table": "output_data",
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
            }
        )

        result = sink.validate_output_target()

        assert result.valid is False
        assert "strict mode" in result.error_message
        assert "name" in result.missing_fields
        sink.close()

    def test_validate_strict_mode_extra_column(self, sqlite_path: str):
        """Strict mode should fail when table has extra column."""
        _create_table_with_columns(sqlite_path, "output_data", ["id", "name", "extra"])
        sink = DatabaseSink(
            {
                "url": sqlite_path,
                "table": "output_data",
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
            }
        )

        result = sink.validate_output_target()

        assert result.valid is False
        assert "strict mode" in result.error_message
        assert "extra" in result.extra_fields
        sink.close()

    def test_validate_strict_mode_order_independent(self, sqlite_path: str):
        """Strict mode for databases is order-independent (set comparison)."""
        # Create with different order - should still pass for database
        _create_table_with_columns(sqlite_path, "output_data", ["name", "id"])
        sink = DatabaseSink(
            {
                "url": sqlite_path,
                "table": "output_data",
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
            }
        )

        result = sink.validate_output_target()

        # Database strict mode uses set comparison (unlike CSV)
        assert result.valid is True
        sink.close()


class TestDatabaseSinkFreeModeValidation:
    """Tests for free mode schema validation."""

    def test_validate_free_mode_exact_match(self, sqlite_path: str):
        """Free mode should pass when columns match exactly."""
        _create_table_with_columns(sqlite_path, "output_data", ["id", "name"])
        sink = DatabaseSink(
            {
                "url": sqlite_path,
                "table": "output_data",
                "schema": {"mode": "free", "fields": ["id: int", "name: str"]},
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True
        sink.close()

    def test_validate_free_mode_missing_column(self, sqlite_path: str):
        """Free mode should fail when required schema column is missing."""
        _create_table_with_columns(sqlite_path, "output_data", ["id"])  # Missing 'name'
        sink = DatabaseSink(
            {
                "url": sqlite_path,
                "table": "output_data",
                "schema": {"mode": "free", "fields": ["id: int", "name: str"]},
            }
        )

        result = sink.validate_output_target()

        assert result.valid is False
        assert "free mode" in result.error_message
        assert "name" in result.missing_fields
        sink.close()

    def test_validate_free_mode_extra_column_allowed(self, sqlite_path: str):
        """Free mode should pass when table has extra columns."""
        _create_table_with_columns(sqlite_path, "output_data", ["id", "name", "extra", "another"])
        sink = DatabaseSink(
            {
                "url": sqlite_path,
                "table": "output_data",
                "schema": {"mode": "free", "fields": ["id: int", "name: str"]},
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True
        sink.close()
