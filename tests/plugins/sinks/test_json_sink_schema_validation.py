"""Tests for JSONSink output target schema validation."""

import json
from pathlib import Path

import pytest

from elspeth.plugins.sinks.json_sink import JSONSink


@pytest.fixture
def tmp_jsonl_path(tmp_path: Path) -> Path:
    """Return a temporary JSONL file path."""
    return tmp_path / "output.jsonl"


@pytest.fixture
def tmp_json_path(tmp_path: Path) -> Path:
    """Return a temporary JSON file path."""
    return tmp_path / "output.json"


def _create_jsonl_with_record(path: Path, record: dict) -> None:
    """Create a JSONL file with a single record."""
    with open(path, "w") as f:
        f.write(json.dumps(record) + "\n")


class TestJSONSinkValidateOutputTarget:
    """Tests for JSONSink.validate_output_target()."""

    def test_validate_nonexistent_file_returns_success(self, tmp_jsonl_path: Path):
        """When file doesn't exist, validation should pass (will create)."""
        sink = JSONSink(
            {
                "path": str(tmp_jsonl_path),
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
                "format": "jsonl",
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True

    def test_validate_empty_file_returns_success(self, tmp_jsonl_path: Path):
        """When file exists but is empty, validation should pass."""
        tmp_jsonl_path.write_text("")
        sink = JSONSink(
            {
                "path": str(tmp_jsonl_path),
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
                "format": "jsonl",
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True

    def test_validate_json_array_format_skips_validation(self, tmp_json_path: Path):
        """JSON array format always passes validation (it rewrites entirely)."""
        # Create a JSON array file with wrong structure
        with open(tmp_json_path, "w") as f:
            json.dump([{"wrong": "fields"}], f)

        sink = JSONSink(
            {
                "path": str(tmp_json_path),
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
                "format": "json",
            }
        )

        result = sink.validate_output_target()

        # JSON array format doesn't need validation - it overwrites
        assert result.valid is True

    def test_validate_dynamic_schema_skips_validation(self, tmp_jsonl_path: Path):
        """Dynamic schema should always pass validation."""
        _create_jsonl_with_record(tmp_jsonl_path, {"wrong": 1, "fields": 2})
        sink = JSONSink(
            {
                "path": str(tmp_jsonl_path),
                "schema": {"fields": "dynamic"},
                "format": "jsonl",
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True
        assert set(result.target_fields) == {"wrong", "fields"}

    def test_validate_invalid_json_returns_failure(self, tmp_jsonl_path: Path):
        """Invalid JSON in file should return failure."""
        tmp_jsonl_path.write_text("not valid json\n")
        sink = JSONSink(
            {
                "path": str(tmp_jsonl_path),
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
                "format": "jsonl",
            }
        )

        result = sink.validate_output_target()

        assert result.valid is False
        assert "invalid JSON" in result.error_message

    def test_validate_non_object_record_returns_failure(self, tmp_jsonl_path: Path):
        """JSONL with non-object records should return failure."""
        tmp_jsonl_path.write_text("[1, 2, 3]\n")  # Array instead of object
        sink = JSONSink(
            {
                "path": str(tmp_jsonl_path),
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
                "format": "jsonl",
            }
        )

        result = sink.validate_output_target()

        assert result.valid is False
        assert "non-object" in result.error_message


class TestJSONSinkStrictModeValidation:
    """Tests for strict mode schema validation."""

    def test_validate_strict_mode_exact_match(self, tmp_jsonl_path: Path):
        """Strict mode should pass when fields match exactly."""
        _create_jsonl_with_record(tmp_jsonl_path, {"id": 1, "name": "test"})
        sink = JSONSink(
            {
                "path": str(tmp_jsonl_path),
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
                "format": "jsonl",
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True

    def test_validate_strict_mode_missing_field(self, tmp_jsonl_path: Path):
        """Strict mode should fail when schema field is missing."""
        _create_jsonl_with_record(tmp_jsonl_path, {"id": 1})  # Missing 'name'
        sink = JSONSink(
            {
                "path": str(tmp_jsonl_path),
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
                "format": "jsonl",
            }
        )

        result = sink.validate_output_target()

        assert result.valid is False
        assert "strict mode" in result.error_message
        assert "name" in result.missing_fields

    def test_validate_strict_mode_extra_field(self, tmp_jsonl_path: Path):
        """Strict mode should fail when record has extra field."""
        _create_jsonl_with_record(tmp_jsonl_path, {"id": 1, "name": "test", "extra": 99})
        sink = JSONSink(
            {
                "path": str(tmp_jsonl_path),
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
                "format": "jsonl",
            }
        )

        result = sink.validate_output_target()

        assert result.valid is False
        assert "strict mode" in result.error_message
        assert "extra" in result.extra_fields


class TestJSONSinkFreeModeValidation:
    """Tests for free mode schema validation."""

    def test_validate_free_mode_exact_match(self, tmp_jsonl_path: Path):
        """Free mode should pass when fields match exactly."""
        _create_jsonl_with_record(tmp_jsonl_path, {"id": 1, "name": "test"})
        sink = JSONSink(
            {
                "path": str(tmp_jsonl_path),
                "schema": {"mode": "free", "fields": ["id: int", "name: str"]},
                "format": "jsonl",
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True

    def test_validate_free_mode_missing_field(self, tmp_jsonl_path: Path):
        """Free mode should fail when required schema field is missing."""
        _create_jsonl_with_record(tmp_jsonl_path, {"id": 1})  # Missing 'name'
        sink = JSONSink(
            {
                "path": str(tmp_jsonl_path),
                "schema": {"mode": "free", "fields": ["id: int", "name: str"]},
                "format": "jsonl",
            }
        )

        result = sink.validate_output_target()

        assert result.valid is False
        assert "free mode" in result.error_message
        assert "name" in result.missing_fields

    def test_validate_free_mode_extra_field_allowed(self, tmp_jsonl_path: Path):
        """Free mode should pass when record has extra fields."""
        _create_jsonl_with_record(tmp_jsonl_path, {"id": 1, "name": "test", "extra": 99, "another": "value"})
        sink = JSONSink(
            {
                "path": str(tmp_jsonl_path),
                "schema": {"mode": "free", "fields": ["id: int", "name: str"]},
                "format": "jsonl",
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True


class TestJSONSinkAutoDetectFormat:
    """Tests for format auto-detection."""

    def test_validate_auto_detected_jsonl_format(self, tmp_path: Path):
        """Auto-detected JSONL format should validate correctly."""
        jsonl_path = tmp_path / "output.jsonl"
        _create_jsonl_with_record(jsonl_path, {"id": 1, "name": "test"})

        sink = JSONSink(
            {
                "path": str(jsonl_path),
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
                # format not specified - auto-detect from extension
            }
        )

        result = sink.validate_output_target()

        assert result.valid is True

    def test_validate_auto_detected_json_format_skips(self, tmp_path: Path):
        """Auto-detected JSON format should skip validation."""
        json_path = tmp_path / "output.json"
        with open(json_path, "w") as f:
            json.dump([{"wrong": "structure"}], f)

        sink = JSONSink(
            {
                "path": str(json_path),
                "schema": {"mode": "strict", "fields": ["id: int", "name: str"]},
                # format not specified - auto-detect from extension
            }
        )

        result = sink.validate_output_target()

        # JSON array format doesn't validate (it rewrites)
        assert result.valid is True
