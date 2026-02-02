"""Tests for sink display header functionality.

Tests the display_headers and restore_source_headers configuration options
for CSV and JSON sinks that allow restoring original header names in output.
"""

import csv
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from elspeth.plugins.config_base import PluginConfigError, SinkPathConfig
from elspeth.plugins.context import PluginContext


class TestSinkPathConfigValidation:
    """Tests for SinkPathConfig display header validation."""

    def test_display_headers_and_restore_mutually_exclusive(self) -> None:
        """Cannot use both display_headers and restore_source_headers."""
        with pytest.raises(PluginConfigError, match="Cannot use both"):
            SinkPathConfig.from_dict(
                {
                    "path": "output.csv",
                    "schema": {"fields": "dynamic"},
                    "display_headers": {"user_id": "User ID"},
                    "restore_source_headers": True,
                }
            )

    def test_display_headers_only_is_valid(self) -> None:
        """display_headers alone is valid."""
        cfg = SinkPathConfig.from_dict(
            {
                "path": "output.csv",
                "schema": {"fields": "dynamic"},
                "display_headers": {"user_id": "User ID", "amount": "Transaction Amount"},
            }
        )
        assert cfg.display_headers == {"user_id": "User ID", "amount": "Transaction Amount"}
        assert cfg.restore_source_headers is False

    def test_restore_source_headers_only_is_valid(self) -> None:
        """restore_source_headers alone is valid."""
        cfg = SinkPathConfig.from_dict(
            {
                "path": "output.csv",
                "schema": {"fields": "dynamic"},
                "restore_source_headers": True,
            }
        )
        assert cfg.display_headers is None
        assert cfg.restore_source_headers is True

    def test_neither_display_option_is_valid(self) -> None:
        """Both display options omitted is valid (default behavior)."""
        cfg = SinkPathConfig.from_dict(
            {
                "path": "output.csv",
                "schema": {"fields": "dynamic"},
            }
        )
        assert cfg.display_headers is None
        assert cfg.restore_source_headers is False


class TestCSVSinkDisplayHeaders:
    """Tests for CSVSink display header functionality."""

    @pytest.fixture
    def ctx(self) -> PluginContext:
        """Create a minimal plugin context."""
        return PluginContext(run_id="test-run", config={})

    def test_explicit_display_headers(self, tmp_path: Path, ctx: PluginContext) -> None:
        """display_headers maps normalized names to display names in CSV header."""
        from elspeth.plugins.sinks.csv_sink import CSVSink

        output_file = tmp_path / "output.csv"
        sink = CSVSink(
            {
                "path": str(output_file),
                "schema": {"mode": "strict", "fields": ["user_id: str", "amount: float"]},
                "display_headers": {"user_id": "User ID", "amount": "Transaction Amount"},
            }
        )

        # Write with normalized field names
        sink.write(
            [
                {"user_id": "u1", "amount": 100.0},
                {"user_id": "u2", "amount": 200.0},
            ],
            ctx,
        )
        sink.flush()
        sink.close()

        # Verify CSV header uses display names
        with open(output_file) as f:
            reader = csv.reader(f)
            header = next(reader)
            assert header == ["User ID", "Transaction Amount"]

            # Verify data rows are correct
            rows = list(reader)
            assert len(rows) == 2
            assert rows[0] == ["u1", "100.0"]
            assert rows[1] == ["u2", "200.0"]

    def test_partial_display_headers(self, tmp_path: Path, ctx: PluginContext) -> None:
        """Unmapped fields keep their normalized names."""
        from elspeth.plugins.sinks.csv_sink import CSVSink

        output_file = tmp_path / "output.csv"
        sink = CSVSink(
            {
                "path": str(output_file),
                "schema": {"mode": "strict", "fields": ["user_id: str", "amount: float", "status: str"]},
                "display_headers": {"user_id": "User ID"},  # Only user_id is mapped
            }
        )

        sink.write([{"user_id": "u1", "amount": 100.0, "status": "active"}], ctx)
        sink.flush()
        sink.close()

        with open(output_file) as f:
            reader = csv.reader(f)
            header = next(reader)
            # user_id mapped, others keep normalized names
            assert header == ["User ID", "amount", "status"]

    def test_restore_source_headers(self, tmp_path: Path) -> None:
        """restore_source_headers fetches mapping from Landscape."""
        from elspeth.plugins.sinks.csv_sink import CSVSink

        output_file = tmp_path / "output.csv"
        sink = CSVSink(
            {
                "path": str(output_file),
                "schema": {"mode": "strict", "fields": ["user_id: str", "case_study_1: str"]},
                "restore_source_headers": True,
            }
        )

        # Mock Landscape with field resolution
        mock_landscape = MagicMock()
        mock_landscape.get_source_field_resolution.return_value = {
            "User ID": "user_id",
            "case StUdY --- 1!!": "case_study_1",
        }

        ctx = PluginContext(
            run_id="test-run",
            config={},
            landscape=mock_landscape,
        )

        # on_start fetches the mapping
        sink.on_start(ctx)

        # Write with normalized field names
        sink.write([{"user_id": "u1", "case_study_1": "value"}], ctx)
        sink.flush()
        sink.close()

        # Verify CSV header uses original (pre-normalization) names
        with open(output_file) as f:
            reader = csv.reader(f)
            header = next(reader)
            assert header == ["User ID", "case StUdY --- 1!!"]

    def test_restore_source_headers_requires_landscape(self, tmp_path: Path) -> None:
        """restore_source_headers fails if Landscape is not available.

        Note: Error occurs on first write(), not on_start(), because field resolution
        is only available after source iteration begins (lazy resolution).
        """
        from elspeth.plugins.sinks.csv_sink import CSVSink

        output_file = tmp_path / "output.csv"
        sink = CSVSink(
            {
                "path": str(output_file),
                "schema": {"mode": "strict", "fields": ["id: str"]},
                "restore_source_headers": True,
            }
        )

        ctx = PluginContext(run_id="test-run", config={}, landscape=None)

        # on_start is now a no-op for restore_source_headers (lazy resolution)
        sink.on_start(ctx)

        # Error occurs on first write when resolution is attempted
        with pytest.raises(ValueError, match="requires Landscape"):
            sink.write([{"id": "test"}], ctx)

    def test_restore_source_headers_requires_field_resolution(self, tmp_path: Path) -> None:
        """restore_source_headers fails if source didn't record resolution.

        Note: Error occurs on first write(), not on_start(), because field resolution
        is only available after source iteration begins (lazy resolution).
        """
        from elspeth.plugins.sinks.csv_sink import CSVSink

        output_file = tmp_path / "output.csv"
        sink = CSVSink(
            {
                "path": str(output_file),
                "schema": {"mode": "strict", "fields": ["id: str"]},
                "restore_source_headers": True,
            }
        )

        mock_landscape = MagicMock()
        mock_landscape.get_source_field_resolution.return_value = None

        ctx = PluginContext(run_id="test-run", config={}, landscape=mock_landscape)

        # on_start is now a no-op for restore_source_headers (lazy resolution)
        sink.on_start(ctx)

        # Error occurs on first write when resolution is attempted
        with pytest.raises(ValueError, match="did not record field resolution"):
            sink.write([{"id": "test"}], ctx)

    def test_transform_added_fields_use_normalized_names(self, tmp_path: Path) -> None:
        """Fields added by transforms use their normalized names (no original exists)."""
        from elspeth.plugins.sinks.csv_sink import CSVSink

        output_file = tmp_path / "output.csv"
        sink = CSVSink(
            {
                "path": str(output_file),
                "schema": {"mode": "strict", "fields": ["user_id: str", "computed_score: float"]},
                "restore_source_headers": True,
            }
        )

        mock_landscape = MagicMock()
        # Source only had user_id, computed_score was added by transform
        mock_landscape.get_source_field_resolution.return_value = {
            "User ID": "user_id",
        }

        ctx = PluginContext(run_id="test-run", config={}, landscape=mock_landscape)
        sink.on_start(ctx)

        sink.write([{"user_id": "u1", "computed_score": 0.95}], ctx)
        sink.flush()
        sink.close()

        with open(output_file) as f:
            reader = csv.reader(f)
            header = next(reader)
            # user_id restored, computed_score keeps normalized name
            assert header == ["User ID", "computed_score"]

    def test_no_display_headers_uses_normalized(self, tmp_path: Path, ctx: PluginContext) -> None:
        """Without display options, headers are normalized field names."""
        from elspeth.plugins.sinks.csv_sink import CSVSink

        output_file = tmp_path / "output.csv"
        sink = CSVSink(
            {
                "path": str(output_file),
                "schema": {"mode": "strict", "fields": ["user_id: str", "amount: float"]},
            }
        )

        sink.write([{"user_id": "u1", "amount": 100.0}], ctx)
        sink.flush()
        sink.close()

        with open(output_file) as f:
            reader = csv.reader(f)
            header = next(reader)
            assert header == ["user_id", "amount"]


class TestJSONSinkDisplayHeaders:
    """Tests for JSONSink display header functionality."""

    @pytest.fixture
    def ctx(self) -> PluginContext:
        """Create a minimal plugin context."""
        return PluginContext(run_id="test-run", config={})

    def test_explicit_display_headers_jsonl(self, tmp_path: Path, ctx: PluginContext) -> None:
        """display_headers maps normalized names to display names in JSONL keys."""
        from elspeth.plugins.sinks.json_sink import JSONSink

        output_file = tmp_path / "output.jsonl"
        sink = JSONSink(
            {
                "path": str(output_file),
                "schema": {"fields": "dynamic"},
                "display_headers": {"user_id": "User ID", "amount": "Transaction Amount"},
            }
        )

        sink.write(
            [
                {"user_id": "u1", "amount": 100.0},
                {"user_id": "u2", "amount": 200.0},
            ],
            ctx,
        )
        sink.flush()
        sink.close()

        # Verify JSONL uses display names as keys
        with open(output_file) as f:
            lines = f.readlines()
            assert len(lines) == 2

            row1 = json.loads(lines[0])
            assert row1 == {"User ID": "u1", "Transaction Amount": 100.0}

            row2 = json.loads(lines[1])
            assert row2 == {"User ID": "u2", "Transaction Amount": 200.0}

    def test_explicit_display_headers_json_array(self, tmp_path: Path, ctx: PluginContext) -> None:
        """display_headers works with JSON array format."""
        from elspeth.plugins.sinks.json_sink import JSONSink

        output_file = tmp_path / "output.json"
        sink = JSONSink(
            {
                "path": str(output_file),
                "format": "json",
                "schema": {"fields": "dynamic"},
                "display_headers": {"user_id": "User ID"},
            }
        )

        sink.write([{"user_id": "u1", "status": "active"}], ctx)
        sink.flush()
        sink.close()

        with open(output_file) as f:
            data = json.load(f)
            assert len(data) == 1
            assert data[0] == {"User ID": "u1", "status": "active"}

    def test_restore_source_headers_jsonl(self, tmp_path: Path) -> None:
        """restore_source_headers fetches mapping from Landscape for JSONL."""
        from elspeth.plugins.sinks.json_sink import JSONSink

        output_file = tmp_path / "output.jsonl"
        sink = JSONSink(
            {
                "path": str(output_file),
                "schema": {"fields": "dynamic"},
                "restore_source_headers": True,
            }
        )

        mock_landscape = MagicMock()
        mock_landscape.get_source_field_resolution.return_value = {
            "User ID": "user_id",
            "Amount (USD)": "amount_usd",
        }

        ctx = PluginContext(run_id="test-run", config={}, landscape=mock_landscape)
        sink.on_start(ctx)

        sink.write([{"user_id": "u1", "amount_usd": 99.99}], ctx)
        sink.flush()
        sink.close()

        with open(output_file) as f:
            row = json.loads(f.readline())
            assert row == {"User ID": "u1", "Amount (USD)": 99.99}

    def test_no_display_headers_uses_normalized(self, tmp_path: Path, ctx: PluginContext) -> None:
        """Without display options, JSONL uses normalized field names."""
        from elspeth.plugins.sinks.json_sink import JSONSink

        output_file = tmp_path / "output.jsonl"
        sink = JSONSink(
            {
                "path": str(output_file),
                "schema": {"fields": "dynamic"},
            }
        )

        sink.write([{"user_id": "u1", "amount": 100.0}], ctx)
        sink.flush()
        sink.close()

        with open(output_file) as f:
            row = json.loads(f.readline())
            assert row == {"user_id": "u1", "amount": 100.0}


class TestFieldResolutionReverseMapping:
    """Tests for FieldResolution.reverse_mapping property."""

    def test_reverse_mapping(self) -> None:
        """reverse_mapping inverts resolution_mapping."""
        from elspeth.plugins.sources.field_normalization import FieldResolution

        resolution = FieldResolution(
            final_headers=["user_id", "case_study_1"],
            resolution_mapping={
                "User ID": "user_id",
                "case StUdY --- 1!!": "case_study_1",
            },
            normalization_version="1.0.0",
        )

        reverse = resolution.reverse_mapping
        assert reverse == {
            "user_id": "User ID",
            "case_study_1": "case StUdY --- 1!!",
        }

    def test_reverse_mapping_empty(self) -> None:
        """reverse_mapping handles empty mapping."""
        from elspeth.plugins.sources.field_normalization import FieldResolution

        resolution = FieldResolution(
            final_headers=[],
            resolution_mapping={},
            normalization_version=None,
        )

        assert resolution.reverse_mapping == {}

    def test_reverse_mapping_passthrough(self) -> None:
        """reverse_mapping handles identity mapping (no normalization)."""
        from elspeth.plugins.sources.field_normalization import FieldResolution

        resolution = FieldResolution(
            final_headers=["id", "name"],
            resolution_mapping={"id": "id", "name": "name"},
            normalization_version=None,
        )

        reverse = resolution.reverse_mapping
        assert reverse == {"id": "id", "name": "name"}


class TestCSVDisplayHeadersAppendMode:
    """Tests for CSV append mode with display headers."""

    @pytest.fixture
    def ctx(self) -> PluginContext:
        """Create a minimal plugin context."""
        return PluginContext(run_id="test-run", config={})

    def test_append_with_explicit_display_headers(self, tmp_path: Path, ctx: PluginContext) -> None:
        """Append mode correctly validates and appends when display headers match."""
        from elspeth.plugins.sinks.csv_sink import CSVSink

        output_file = tmp_path / "output.csv"

        # First write with display headers
        sink1 = CSVSink(
            {
                "path": str(output_file),
                "schema": {"mode": "strict", "fields": ["user_id: str", "amount: float"]},
                "display_headers": {"user_id": "User ID", "amount": "Amount"},
            }
        )
        sink1.write([{"user_id": "u1", "amount": 100.0}], ctx)
        sink1.flush()
        sink1.close()

        # Append with same display headers
        sink2 = CSVSink(
            {
                "path": str(output_file),
                "schema": {"mode": "strict", "fields": ["user_id: str", "amount: float"]},
                "display_headers": {"user_id": "User ID", "amount": "Amount"},
                "mode": "append",
            }
        )
        sink2.write([{"user_id": "u2", "amount": 200.0}], ctx)
        sink2.flush()
        sink2.close()

        # Verify both rows present with correct headers
        with open(output_file) as f:
            reader = csv.reader(f)
            header = next(reader)
            assert header == ["User ID", "Amount"]
            rows = list(reader)
            assert len(rows) == 2
            assert rows[0] == ["u1", "100.0"]
            assert rows[1] == ["u2", "200.0"]


class TestCSVDisplayHeadersSpecialCharacters:
    """Tests for CSV display headers containing special characters."""

    @pytest.fixture
    def ctx(self) -> PluginContext:
        """Create a minimal plugin context."""
        return PluginContext(run_id="test-run", config={})

    def test_display_header_with_comma(self, tmp_path: Path, ctx: PluginContext) -> None:
        """Display headers containing commas are properly quoted in CSV."""
        from elspeth.plugins.sinks.csv_sink import CSVSink

        output_file = tmp_path / "output.csv"
        sink = CSVSink(
            {
                "path": str(output_file),
                "schema": {"mode": "strict", "fields": ["amount: float", "currency: str"]},
                "display_headers": {"amount": "Amount, USD", "currency": "Currency"},
            }
        )

        sink.write([{"amount": 100.0, "currency": "USD"}], ctx)
        sink.flush()
        sink.close()

        # Read raw file to verify quoting
        with open(output_file) as f:
            content = f.read()
            # Header should be quoted because it contains comma
            assert '"Amount, USD"' in content or "'Amount, USD'" in content

        # Verify it parses correctly with csv module
        with open(output_file) as f:
            reader = csv.reader(f)
            header = next(reader)
            assert header == ["Amount, USD", "Currency"]
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0] == ["100.0", "USD"]

    def test_display_header_with_quotes(self, tmp_path: Path, ctx: PluginContext) -> None:
        """Display headers containing quotes are properly escaped in CSV."""
        from elspeth.plugins.sinks.csv_sink import CSVSink

        output_file = tmp_path / "output.csv"
        sink = CSVSink(
            {
                "path": str(output_file),
                "schema": {"mode": "strict", "fields": ["value: str"]},
                "display_headers": {"value": 'Value "quoted"'},
            }
        )

        sink.write([{"value": "test"}], ctx)
        sink.flush()
        sink.close()

        # Verify it parses correctly with csv module
        with open(output_file) as f:
            reader = csv.reader(f)
            header = next(reader)
            assert header == ['Value "quoted"']

    def test_display_header_with_newline(self, tmp_path: Path, ctx: PluginContext) -> None:
        """Display headers containing newlines are properly quoted in CSV."""
        from elspeth.plugins.sinks.csv_sink import CSVSink

        output_file = tmp_path / "output.csv"
        sink = CSVSink(
            {
                "path": str(output_file),
                "schema": {"mode": "strict", "fields": ["description: str"]},
                "display_headers": {"description": "Description\n(multi-line)"},
            }
        )

        sink.write([{"description": "test"}], ctx)
        sink.flush()
        sink.close()

        # Verify it parses correctly with csv module
        with open(output_file) as f:
            reader = csv.reader(f)
            header = next(reader)
            assert header == ["Description\n(multi-line)"]


class TestJSONLDisplayHeadersAppendMode:
    """Tests for JSONL append/resume mode with display headers."""

    @pytest.fixture
    def ctx(self) -> PluginContext:
        """Create a minimal plugin context."""
        return PluginContext(run_id="test-run", config={})

    def test_append_with_explicit_display_headers(self, tmp_path: Path, ctx: PluginContext) -> None:
        """Append mode correctly validates and appends when display headers match."""
        from elspeth.plugins.sinks.json_sink import JSONSink

        output_file = tmp_path / "output.jsonl"

        # First write with display headers
        sink1 = JSONSink(
            {
                "path": str(output_file),
                "schema": {"mode": "strict", "fields": ["user_id: str", "amount: float"]},
                "display_headers": {"user_id": "User ID", "amount": "Amount"},
            }
        )
        sink1.write([{"user_id": "u1", "amount": 100.0}], ctx)
        sink1.flush()
        sink1.close()

        # Append with same display headers
        sink2 = JSONSink(
            {
                "path": str(output_file),
                "schema": {"mode": "strict", "fields": ["user_id: str", "amount: float"]},
                "display_headers": {"user_id": "User ID", "amount": "Amount"},
                "mode": "append",
            }
        )
        sink2.write([{"user_id": "u2", "amount": 200.0}], ctx)
        sink2.flush()
        sink2.close()

        # Verify both rows present with display names as keys
        with open(output_file) as f:
            lines = f.readlines()
            assert len(lines) == 2
            row1 = json.loads(lines[0])
            row2 = json.loads(lines[1])
            assert row1 == {"User ID": "u1", "Amount": 100.0}
            assert row2 == {"User ID": "u2", "Amount": 200.0}

    def test_resume_validation_with_display_headers(self, tmp_path: Path, ctx: PluginContext) -> None:
        """Resume validation succeeds when existing file uses display names."""
        from elspeth.plugins.sinks.json_sink import JSONSink

        output_file = tmp_path / "output.jsonl"

        # Pre-create file with display headers
        with open(output_file, "w") as f:
            f.write(json.dumps({"User ID": "u1", "Amount": 100.0}) + "\n")

        # Open in append mode with matching display headers - should validate successfully
        sink = JSONSink(
            {
                "path": str(output_file),
                "schema": {"mode": "strict", "fields": ["user_id: str", "amount: float"]},
                "display_headers": {"user_id": "User ID", "amount": "Amount"},
                "mode": "append",
            }
        )

        # Validation happens lazily, trigger it by calling validate_output_target
        result = sink.validate_output_target()
        assert result.valid, f"Validation failed: {result.error_message}"
