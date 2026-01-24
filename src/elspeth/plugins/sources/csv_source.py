# src/elspeth/plugins/sources/csv_source.py
"""CSV source plugin for ELSPETH.

Loads rows from CSV files using csv.reader for proper multiline quoted field support.

IMPORTANT: Sources use allow_coercion=True to normalize external data.
This is the ONLY place in the pipeline where coercion is allowed.
"""

import csv
from collections.abc import Iterator
from typing import Any

from pydantic import ValidationError

from elspeth.contracts import PluginSchema, SourceRow
from elspeth.plugins.base import BaseSource
from elspeth.plugins.config_base import SourceDataConfig
from elspeth.plugins.context import PluginContext
from elspeth.plugins.schema_factory import create_schema_from_config


class CSVSourceConfig(SourceDataConfig):
    """Configuration for CSV source plugin.

    Inherits from SourceDataConfig, which requires schema and on_validation_failure.
    """

    delimiter: str = ","
    encoding: str = "utf-8"
    skip_rows: int = 0


class CSVSource(BaseSource):
    """Load rows from a CSV file.

    Config options:
        path: Path to CSV file (required)
        schema: Schema configuration (required, via SourceDataConfig)
        delimiter: Field delimiter (default: ",")
        encoding: File encoding (default: "utf-8")
        skip_rows: Number of header rows to skip (default: 0)

    The schema can be:
        - Dynamic: {"fields": "dynamic"} - accept any fields
        - Strict: {"mode": "strict", "fields": ["id: int", "name: str"]}
        - Free: {"mode": "free", "fields": ["id: int"]} - at least these fields
    """

    name = "csv"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        cfg = CSVSourceConfig.from_dict(config)

        self._path = cfg.resolved_path()
        self._delimiter = cfg.delimiter
        self._encoding = cfg.encoding
        self._skip_rows = cfg.skip_rows

        # Store schema config for audit trail
        # SourceDataConfig (via DataPluginConfig) ensures schema_config is not None
        assert cfg.schema_config is not None
        self._schema_config = cfg.schema_config

        # Store quarantine routing destination
        self._on_validation_failure = cfg.on_validation_failure

        # CRITICAL: allow_coercion=True for sources (external data boundary)
        # Sources are the ONLY place where type coercion is allowed
        self._schema_class: type[PluginSchema] = create_schema_from_config(
            self._schema_config,
            "CSVRowSchema",
            allow_coercion=True,
        )

        # Set output_schema for protocol compliance
        self.output_schema = self._schema_class

        # Validate self-consistency (PHASE 1)
        self._validate_self_consistency()

    def _validate_self_consistency(self) -> None:
        """Validate CSVSource schemas are self-consistent.

        CSVSource has no self-consistency constraints - only output_schema.
        """
        self._validation_called = True  # Mark validation as complete
        # No additional validation needed - CSVSource has only output schema

    def load(self, ctx: PluginContext) -> Iterator[SourceRow]:
        """Load rows from CSV file.

        Uses csv.reader directly on file handle to properly support
        multiline quoted fields (e.g., "field with\nembedded newline").

        Each row is validated against the configured schema:
        - Valid rows are yielded as SourceRow.valid()
        - Invalid rows are yielded as SourceRow.quarantined()

        Yields:
            SourceRow for each row (valid or quarantined).

        Raises:
            FileNotFoundError: If CSV file does not exist.
        """
        if not self._path.exists():
            raise FileNotFoundError(f"CSV file not found: {self._path}")

        # CRITICAL: newline='' required for proper embedded newline handling
        # See: https://docs.python.org/3/library/csv.html
        with open(self._path, encoding=self._encoding, newline="") as f:
            # Skip header rows as configured
            for _ in range(self._skip_rows):
                next(f, None)

            # Create csv.reader on file handle for multiline field support
            reader = csv.reader(f, delimiter=self._delimiter)

            # Read header row
            try:
                headers = next(reader)
            except StopIteration:
                return  # Empty file after skip_rows

            # Process data rows with manual iteration to catch csv.Error per row
            row_num = 0  # Logical row number (data rows only)
            while True:
                try:
                    # Try to read next row - csv.Error raised here for malformed rows
                    values = next(reader)
                except StopIteration:
                    break  # End of file
                except csv.Error as e:
                    # CSV parsing error (bad quoting, unmatched quotes, etc.)
                    # Quarantine this row instead of crashing the run
                    row_num += 1
                    physical_line = reader.line_num + self._skip_rows
                    raw_row = {
                        "__raw_line__": "(unparseable due to csv.Error)",
                        "__line_number__": physical_line,
                        "__row_number__": row_num,
                    }
                    error_msg = f"CSV parse error at line {physical_line}: {e}"

                    ctx.record_validation_error(
                        row=raw_row,
                        error=error_msg,
                        schema_mode="parse",
                        destination=self._on_validation_failure,
                    )

                    if self._on_validation_failure != "discard":
                        yield SourceRow.quarantined(
                            row=raw_row,
                            error=error_msg,
                            destination=self._on_validation_failure,
                        )
                    continue  # Skip to next row

                # Skip empty rows (blank lines in CSV)
                # csv.reader returns [] for blank lines, which would cause field count mismatch
                if not values:
                    continue

                row_num += 1
                # reader.line_num tracks physical line position (including multiline fields)
                # Add skip_rows to get true file position (reader counts from 1 after skipped lines)
                physical_line = reader.line_num + self._skip_rows

                # Check field count matches header
                if len(values) != len(headers):
                    # Malformed row - field count mismatch
                    # Use physical line number for audit trail
                    raw_row = {
                        "__raw_line__": self._delimiter.join(values),
                        "__line_number__": physical_line,
                        "__row_number__": row_num,
                    }
                    error_msg = f"CSV parse error at line {physical_line}: expected {len(headers)} fields, got {len(values)}"

                    ctx.record_validation_error(
                        row=raw_row,
                        error=error_msg,
                        schema_mode="parse",
                        destination=self._on_validation_failure,
                    )

                    if self._on_validation_failure != "discard":
                        yield SourceRow.quarantined(
                            row=raw_row,
                            error=error_msg,
                            destination=self._on_validation_failure,
                        )
                    continue

                # Build row dict
                row = dict(zip(headers, values, strict=False))

                # Validate row against schema
                try:
                    validated = self._schema_class.model_validate(row)
                    yield SourceRow.valid(validated.to_row())
                except ValidationError as e:
                    ctx.record_validation_error(
                        row=row,
                        error=str(e),
                        schema_mode=self._schema_config.mode or "dynamic",
                        destination=self._on_validation_failure,
                    )

                    if self._on_validation_failure != "discard":
                        yield SourceRow.quarantined(
                            row=row,
                            error=str(e),
                            destination=self._on_validation_failure,
                        )

    def close(self) -> None:
        """Release resources (no-op for CSV source)."""
        pass
