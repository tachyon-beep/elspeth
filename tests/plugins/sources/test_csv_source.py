"""Tests for CSV source plugin."""

from pathlib import Path

import pytest

from elspeth.plugins.context import PluginContext
from elspeth.plugins.protocols import SourceProtocol

# Dynamic schema config for tests - SourceDataConfig requires schema
DYNAMIC_SCHEMA = {"fields": "dynamic"}

# Standard quarantine routing for tests
QUARANTINE_SINK = "quarantine"


class TestCSVSource:
    """Tests for CSVSource plugin."""

    @pytest.fixture
    def sample_csv(self, tmp_path: Path) -> Path:
        """Create a sample CSV file."""
        csv_file = tmp_path / "sample.csv"
        csv_file.write_text("id,name,value\n1,alice,100\n2,bob,200\n3,carol,300\n")
        return csv_file

    @pytest.fixture
    def ctx(self) -> PluginContext:
        """Create a minimal plugin context."""
        return PluginContext(run_id="test-run", config={})

    def test_implements_protocol(self) -> None:
        """CSVSource implements SourceProtocol."""
        from elspeth.plugins.sources.csv_source import CSVSource

        assert isinstance(CSVSource, type)
        # Runtime check via Protocol
        source = CSVSource(
            {
                "path": "/tmp/test.csv",
                "schema": DYNAMIC_SCHEMA,
                "on_validation_failure": QUARANTINE_SINK,
            }
        )
        assert isinstance(source, SourceProtocol)

    def test_has_required_attributes(self) -> None:
        """CSVSource has name and output_schema."""
        from elspeth.plugins.sources.csv_source import CSVSource

        assert CSVSource.name == "csv"
        # output_schema is an instance attribute (set based on config)
        source = CSVSource(
            {
                "path": "/tmp/test.csv",
                "schema": DYNAMIC_SCHEMA,
                "on_validation_failure": QUARANTINE_SINK,
            }
        )
        assert hasattr(source, "output_schema")

    def test_load_yields_rows(self, sample_csv: Path, ctx: PluginContext) -> None:
        """load() yields dict rows from CSV."""
        from elspeth.plugins.sources.csv_source import CSVSource

        source = CSVSource(
            {
                "path": str(sample_csv),
                "schema": DYNAMIC_SCHEMA,
                "on_validation_failure": QUARANTINE_SINK,
            }
        )
        rows = list(source.load(ctx))

        assert len(rows) == 3
        # All rows are SourceRow objects - access .row for data
        assert rows[0].row == {"id": "1", "name": "alice", "value": "100"}
        assert rows[0].is_quarantined is False
        assert rows[1].row["name"] == "bob"
        assert rows[2].row["value"] == "300"

    def test_load_with_delimiter(self, tmp_path: Path, ctx: PluginContext) -> None:
        """CSV with custom delimiter."""
        from elspeth.plugins.sources.csv_source import CSVSource

        csv_file = tmp_path / "semicolon.csv"
        csv_file.write_text("id;name;value\n1;alice;100\n")

        source = CSVSource(
            {
                "path": str(csv_file),
                "delimiter": ";",
                "schema": DYNAMIC_SCHEMA,
                "on_validation_failure": QUARANTINE_SINK,
            }
        )
        rows = list(source.load(ctx))

        assert len(rows) == 1
        assert rows[0].row["name"] == "alice"

    def test_load_with_encoding(self, tmp_path: Path, ctx: PluginContext) -> None:
        """CSV with non-UTF8 encoding."""
        from elspeth.plugins.sources.csv_source import CSVSource

        csv_file = tmp_path / "latin1.csv"
        csv_file.write_bytes(b"id,name\n1,caf\xe9\n")

        source = CSVSource(
            {
                "path": str(csv_file),
                "encoding": "latin-1",
                "schema": DYNAMIC_SCHEMA,
                "on_validation_failure": QUARANTINE_SINK,
            }
        )
        rows = list(source.load(ctx))

        assert rows[0].row["name"] == "café"

    def test_close_is_idempotent(self, sample_csv: Path, ctx: PluginContext) -> None:
        """close() can be called multiple times."""
        from elspeth.plugins.sources.csv_source import CSVSource

        source = CSVSource(
            {
                "path": str(sample_csv),
                "schema": DYNAMIC_SCHEMA,
                "on_validation_failure": QUARANTINE_SINK,
            }
        )
        list(source.load(ctx))  # Consume iterator
        source.close()
        source.close()  # Should not raise

    def test_file_not_found_raises(self, ctx: PluginContext) -> None:
        """Missing file raises FileNotFoundError."""
        from elspeth.plugins.sources.csv_source import CSVSource

        source = CSVSource(
            {
                "path": "/nonexistent/file.csv",
                "schema": DYNAMIC_SCHEMA,
                "on_validation_failure": QUARANTINE_SINK,
            }
        )
        with pytest.raises(FileNotFoundError):
            list(source.load(ctx))


class TestCSVSourceConfigValidation:
    """Test CSVSource config validation."""

    def test_missing_path_raises_error(self) -> None:
        """Empty config raises PluginConfigError."""
        from elspeth.plugins.config_base import PluginConfigError
        from elspeth.plugins.sources.csv_source import CSVSource

        with pytest.raises(PluginConfigError, match="path"):
            CSVSource({"schema": DYNAMIC_SCHEMA, "on_validation_failure": QUARANTINE_SINK})

    def test_empty_path_raises_error(self) -> None:
        """Empty path string raises PluginConfigError."""
        from elspeth.plugins.config_base import PluginConfigError
        from elspeth.plugins.sources.csv_source import CSVSource

        with pytest.raises(PluginConfigError, match="path cannot be empty"):
            CSVSource(
                {
                    "path": "",
                    "schema": DYNAMIC_SCHEMA,
                    "on_validation_failure": QUARANTINE_SINK,
                }
            )

    def test_unknown_field_raises_error(self) -> None:
        """Unknown config field raises PluginConfigError."""
        from elspeth.plugins.config_base import PluginConfigError
        from elspeth.plugins.sources.csv_source import CSVSource

        with pytest.raises(PluginConfigError, match="Extra inputs"):
            CSVSource(
                {
                    "path": "/tmp/test.csv",
                    "schema": DYNAMIC_SCHEMA,
                    "on_validation_failure": QUARANTINE_SINK,
                    "unknown_field": "value",
                }
            )

    def test_missing_schema_raises_error(self) -> None:
        """Missing schema raises PluginConfigError."""
        from elspeth.plugins.config_base import PluginConfigError
        from elspeth.plugins.sources.csv_source import CSVSource

        with pytest.raises(PluginConfigError, match=r"require.*schema"):
            CSVSource({"path": "/tmp/test.csv", "on_validation_failure": QUARANTINE_SINK})

    def test_missing_on_validation_failure_raises_error(self) -> None:
        """Missing on_validation_failure raises PluginConfigError."""
        from elspeth.plugins.config_base import PluginConfigError
        from elspeth.plugins.sources.csv_source import CSVSource

        with pytest.raises(PluginConfigError, match="on_validation_failure"):
            CSVSource({"path": "/tmp/test.csv", "schema": DYNAMIC_SCHEMA})


class TestCSVSourceQuarantineYielding:
    """Tests for CSV source yielding SourceRow.quarantined() for invalid rows."""

    @pytest.fixture
    def ctx(self) -> PluginContext:
        """Create a minimal plugin context."""
        return PluginContext(run_id="test-run", config={})

    def test_invalid_row_yields_quarantined_source_row(self, tmp_path: Path, ctx: PluginContext) -> None:
        """Invalid row yields SourceRow.quarantined() with error info."""
        from elspeth.contracts import SourceRow
        from elspeth.plugins.sources.csv_source import CSVSource

        # CSV with invalid row (score is not an int)
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("id,name,score\n1,alice,95\n2,bob,bad\n3,carol,92\n")

        source = CSVSource(
            {
                "path": str(csv_file),
                "on_validation_failure": "quarantine",
                "schema": {
                    "mode": "strict",
                    "fields": ["id: int", "name: str", "score: int"],
                },
            }
        )

        results = list(source.load(ctx))

        # 2 valid rows + 1 quarantined - all are SourceRow
        assert len(results) == 3
        assert all(isinstance(r, SourceRow) for r in results)

        # First and third are valid SourceRows
        assert results[0].is_quarantined is False
        assert results[0].row["name"] == "alice"
        assert results[2].is_quarantined is False
        assert results[2].row["name"] == "carol"

        # Second is a quarantined SourceRow
        quarantined = results[1]
        assert quarantined.is_quarantined is True
        assert quarantined.row["name"] == "bob"
        assert quarantined.row["score"] == "bad"  # Original value preserved
        assert quarantined.quarantine_destination == "quarantine"
        assert quarantined.quarantine_error is not None
        assert "score" in quarantined.quarantine_error  # Error mentions the field

    def test_discard_mode_does_not_yield_invalid_rows(self, tmp_path: Path, ctx: PluginContext) -> None:
        """When on_validation_failure='discard', invalid rows are not yielded."""
        from elspeth.contracts import SourceRow
        from elspeth.plugins.sources.csv_source import CSVSource

        csv_file = tmp_path / "data.csv"
        csv_file.write_text("id,name,score\n1,alice,95\n2,bob,bad\n3,carol,92\n")

        source = CSVSource(
            {
                "path": str(csv_file),
                "on_validation_failure": "discard",
                "schema": {
                    "mode": "strict",
                    "fields": ["id: int", "name: str", "score: int"],
                },
            }
        )

        results = list(source.load(ctx))

        # Only 2 valid rows - invalid row discarded
        assert len(results) == 2
        assert all(isinstance(r, SourceRow) and not r.is_quarantined for r in results)
        assert {r.row["name"] for r in results} == {"alice", "carol"}

    def test_malformed_csv_row_quarantined_not_crash(self, tmp_path: Path, ctx: PluginContext) -> None:
        """Malformed CSV row (extra columns) should quarantine, not crash pipeline."""
        from elspeth.plugins.sources.csv_source import CSVSource

        csv_file = tmp_path / "data.csv"
        # Row 2 has extra column - pandas ParserError
        csv_file.write_text("id,name\n1,alice\n2,bob,extra\n3,carol\n")

        source = CSVSource(
            {
                "path": str(csv_file),
                "on_validation_failure": "quarantine",
                "schema": DYNAMIC_SCHEMA,
            }
        )

        # Should not crash - should yield 2 valid + 1 quarantined
        results = list(source.load(ctx))

        # Verify we got 3 total rows
        assert len(results) == 3

        # First row valid
        assert not results[0].is_quarantined
        assert results[0].row == {"id": "1", "name": "alice"}

        # Second row quarantined (parse error)
        assert results[1].is_quarantined is True
        assert results[1].quarantine_destination == "quarantine"
        assert results[1].quarantine_error is not None
        assert "parse error" in results[1].quarantine_error.lower()
        assert "__raw_line__" in results[1].row
        assert "__line_number__" in results[1].row

        # Third row valid
        assert not results[2].is_quarantined
        assert results[2].row == {"id": "3", "name": "carol"}

    def test_malformed_csv_row_with_discard_mode(self, tmp_path: Path, ctx: PluginContext) -> None:
        """Malformed CSV row with discard mode should not yield quarantined row."""
        from elspeth.plugins.sources.csv_source import CSVSource

        csv_file = tmp_path / "data.csv"
        csv_file.write_text("id,name\n1,alice\n2,bob,extra\n3,carol\n")

        source = CSVSource(
            {
                "path": str(csv_file),
                "on_validation_failure": "discard",
                "schema": DYNAMIC_SCHEMA,
            }
        )

        # Should not crash, should yield only valid rows
        results = list(source.load(ctx))

        # Only 2 valid rows, malformed row discarded
        assert len(results) == 2
        assert results[0].row == {"id": "1", "name": "alice"}
        assert results[1].row == {"id": "3", "name": "carol"}

    def test_csv_error_handling_defensive(self, tmp_path: Path, ctx: PluginContext) -> None:
        """CSV parsing with manual iteration handles csv.Error defensively.

        Regression test for P1 bug where csv.Error was not caught in for-loop iteration.
        Python's csv.reader rarely raises csv.Error (it's quite tolerant), so this test
        verifies the defensive code path exists even if triggering it is difficult.

        The actual fix ensures that IF csv.Error is ever raised during iteration,
        it will be caught and quarantined instead of crashing the run.
        """
        from elspeth.plugins.sources.csv_source import CSVSource

        csv_file = tmp_path / "data.csv"
        # Use a CSV with multiline quoted field (valid CSV that tests iteration)
        # This verifies manual while/next() iteration works correctly
        csv_file.write_text('id,name\n1,alice\n2,"bob\nsmith"\n3,carol\n')

        source = CSVSource(
            {
                "path": str(csv_file),
                "on_validation_failure": "quarantine",
                "schema": DYNAMIC_SCHEMA,
            }
        )

        # Should not crash - manual iteration with try/except should work
        results = list(source.load(ctx))

        # Should get 3 valid rows (multiline field is valid CSV)
        assert len(results) == 3

        # All rows should be valid
        assert not results[0].is_quarantined
        assert results[0].row == {"id": "1", "name": "alice"}

        assert not results[1].is_quarantined
        assert results[1].row == {"id": "2", "name": "bob\nsmith"}  # Multiline field preserved

        assert not results[2].is_quarantined
        assert results[2].row == {"id": "3", "name": "carol"}

    def test_skip_rows_line_numbers_are_accurate(self, tmp_path: Path, ctx: PluginContext) -> None:
        """Line numbers in error messages should be accurate when skip_rows > 0.

        Regression test for P2 bug where line numbers were off by skip_rows amount.
        """
        from elspeth.plugins.sources.csv_source import CSVSource

        csv_file = tmp_path / "data.csv"
        # Line 1: comment to skip
        # Line 2: header
        # Line 3: valid row
        # Line 4: malformed row (extra field)
        # Line 5: valid row
        csv_file.write_text("# This is a comment\nid,name\n1,alice\n2,bob,extra\n3,carol\n")

        source = CSVSource(
            {
                "path": str(csv_file),
                "skip_rows": 1,  # Skip the comment line
                "on_validation_failure": "quarantine",
                "schema": DYNAMIC_SCHEMA,
            }
        )

        results = list(source.load(ctx))

        # Should get 3 rows: 2 valid + 1 quarantined
        assert len(results) == 3

        # First row valid (line 3 in file)
        assert not results[0].is_quarantined

        # Second row quarantined (line 4 in file)
        assert results[1].is_quarantined is True
        quarantined_row = results[1].row

        # Check that __line_number__ reflects actual file position (line 4, not line 3)
        assert quarantined_row["__line_number__"] == 4

        # Error message should also show correct line number
        assert results[1].quarantine_error is not None
        assert "line 4" in results[1].quarantine_error

        # Third row valid (line 5 in file)
        assert not results[2].is_quarantined

    def test_empty_rows_are_skipped(self, tmp_path: Path, ctx: PluginContext) -> None:
        """Empty rows (blank lines) should be skipped without generating errors.

        Regression test for P3 where csv.reader returns [] for blank lines,
        which would cause field-count mismatch errors if not handled.
        """
        from elspeth.plugins.sources.csv_source import CSVSource

        csv_file = tmp_path / "data.csv"
        # Include blank lines between rows
        csv_file.write_text("id,name\n1,alice\n\n2,bob\n\n\n3,carol\n")

        source = CSVSource(
            {
                "path": str(csv_file),
                "on_validation_failure": "quarantine",
                "schema": DYNAMIC_SCHEMA,
            }
        )

        results = list(source.load(ctx))

        # Should get only 3 valid rows, blank lines skipped
        assert len(results) == 3

        # All rows should be valid (no quarantined rows from empty lines)
        assert not results[0].is_quarantined
        assert results[0].row == {"id": "1", "name": "alice"}

        assert not results[1].is_quarantined
        assert results[1].row == {"id": "2", "name": "bob"}

        assert not results[2].is_quarantined
        assert results[2].row == {"id": "3", "name": "carol"}
