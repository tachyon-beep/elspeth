"""Tests for CSVSink output target schema validation."""

import csv
from pathlib import Path

import pytest

from elspeth.plugins.sinks.csv_sink import CSVSink


@pytest.fixture
def tmp_csv_path(tmp_path: Path) -> Path:
    """Return a temporary CSV file path."""
    return tmp_path / "output.csv"


def _create_csv_with_headers(path: Path, headers: list[str]) -> None:
    """Create a CSV file with the given headers and no data rows."""
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()


class TestCSVSinkValidateOutputTarget:
    """Tests for CSVSink.validate_output_target()."""

    def test_validate_nonexistent_file_returns_success(self, tmp_csv_path: Path):
        """When file doesn't exist, validation should pass (will create)."""
        sink = CSVSink(
            {
                "path": str(tmp_csv_path),
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True

    def test_validate_empty_file_returns_success(self, tmp_csv_path: Path):
        """When file exists but is empty, validation should pass."""
        tmp_csv_path.write_text("")
        sink = CSVSink(
            {
                "path": str(tmp_csv_path),
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True

    def test_validate_dynamic_schema_skips_validation(self, tmp_csv_path: Path):
        """Dynamic schema should always pass validation."""
        _create_csv_with_headers(tmp_csv_path, ["wrong", "headers", "entirely"])
        sink = CSVSink(
            {
                "path": str(tmp_csv_path),
                "schema": {"fields": "dynamic"},
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True
        assert list(result.target_fields) == ["wrong", "headers", "entirely"]


class TestCSVSinkStrictModeValidation:
    """Tests for strict mode schema validation."""

    def test_validate_strict_mode_exact_match(self, tmp_csv_path: Path):
        """Strict mode should pass when headers match exactly."""
        _create_csv_with_headers(tmp_csv_path, ["id", "name"])
        sink = CSVSink(
            {
                "path": str(tmp_csv_path),
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True
        assert list(result.target_fields) == ["id", "name"]

    def test_validate_strict_mode_missing_field(self, tmp_csv_path: Path):
        """Strict mode should fail when schema field is missing from file."""
        _create_csv_with_headers(tmp_csv_path, ["id"])  # Missing 'name'
        sink = CSVSink(
            {
                "path": str(tmp_csv_path),
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
            }
        )

        result = sink.validate_output_target()

        assert result.valid is False
        assert "strict mode" in result.error_message
        assert "name" in result.missing_fields
        assert result.order_mismatch is False

    def test_validate_strict_mode_extra_field(self, tmp_csv_path: Path):
        """Strict mode should fail when file has extra field."""
        _create_csv_with_headers(tmp_csv_path, ["id", "name", "extra"])
        sink = CSVSink(
            {
                "path": str(tmp_csv_path),
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
            }
        )

        result = sink.validate_output_target()

        assert result.valid is False
        assert "strict mode" in result.error_message
        assert "extra" in result.extra_fields

    def test_validate_strict_mode_order_mismatch(self, tmp_csv_path: Path):
        """Strict mode should fail when same fields but different order."""
        _create_csv_with_headers(tmp_csv_path, ["name", "id"])  # Reversed order
        sink = CSVSink(
            {
                "path": str(tmp_csv_path),
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
            }
        )

        result = sink.validate_output_target()

        assert result.valid is False
        assert "strict mode" in result.error_message
        assert result.order_mismatch is True
        # No missing or extra fields - just order wrong
        assert len(result.missing_fields) == 0
        assert len(result.extra_fields) == 0


class TestCSVSinkFreeModeValidation:
    """Tests for free mode schema validation."""

    def test_validate_free_mode_exact_match(self, tmp_csv_path: Path):
        """Free mode should pass when headers match exactly."""
        _create_csv_with_headers(tmp_csv_path, ["id", "name"])
        sink = CSVSink(
            {
                "path": str(tmp_csv_path),
                "schema": {"mode": "free", "fields": ["id: int", "name: str"]},
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True

    def test_validate_free_mode_missing_field(self, tmp_csv_path: Path):
        """Free mode should fail when required schema field is missing."""
        _create_csv_with_headers(tmp_csv_path, ["id"])  # Missing 'name'
        sink = CSVSink(
            {
                "path": str(tmp_csv_path),
                "schema": {"mode": "free", "fields": ["id: int", "name: str"]},
            }
        )

        result = sink.validate_output_target()

        assert result.valid is False
        assert "free mode" in result.error_message
        assert "name" in result.missing_fields

    def test_validate_free_mode_extra_field_allowed(self, tmp_csv_path: Path):
        """Free mode should pass when file has extra fields."""
        _create_csv_with_headers(tmp_csv_path, ["id", "name", "extra", "another"])
        sink = CSVSink(
            {
                "path": str(tmp_csv_path),
                "schema": {"mode": "free", "fields": ["id: int", "name: str"]},
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True
        assert list(result.target_fields) == ["id", "name", "extra", "another"]

    def test_validate_free_mode_order_independent(self, tmp_csv_path: Path):
        """Free mode should pass regardless of column order."""
        _create_csv_with_headers(tmp_csv_path, ["name", "id"])  # Reversed order
        sink = CSVSink(
            {
                "path": str(tmp_csv_path),
                "schema": {"mode": "free", "fields": ["id: int", "name: str"]},
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True


class TestCSVSinkValidationWithDelimiter:
    """Tests for validation with non-default delimiter."""

    def test_validate_with_custom_delimiter(self, tmp_csv_path: Path):
        """Validation should respect custom delimiter."""
        # Create CSV with tab delimiter
        with open(tmp_csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "name"], delimiter="\t")
            writer.writeheader()

        sink = CSVSink(
            {
                "path": str(tmp_csv_path),
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
                "delimiter": "\t",
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True
