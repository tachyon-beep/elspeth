# src/elspeth/plugins/sources/csv_source.py
"""CSV source plugin for ELSPETH.

Loads rows from CSV files using line-by-line parsing for graceful malformed row handling.

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

    def load(self, ctx: PluginContext) -> Iterator[SourceRow]:
        """Load rows from CSV file.

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

        with open(self._path, encoding=self._encoding) as f:
            # Skip header rows as configured
            for _ in range(self._skip_rows):
                next(f, None)

            # Read header line
            header_line = f.readline()
            if not header_line:
                return  # Empty file after skip_rows

            # Parse header using csv module
            reader = csv.reader([header_line], delimiter=self._delimiter)
            headers = next(reader)

            # Process each data line
            line_num = self._skip_rows + 2  # +1 for header, +1 for first data line
            for line in f:
                line = line.rstrip("\n\r")
                if not line:
                    line_num += 1
                    continue

                # Parse CSV line - catch malformed rows
                try:
                    reader = csv.reader([line], delimiter=self._delimiter)
                    values = next(reader)

                    # Check field count matches header
                    if len(values) != len(headers):
                        # Malformed row - field count mismatch
                        raw_row = {"__raw_line__": line, "__line_number__": line_num}
                        error_msg = f"CSV parse error at line {line_num}: expected {len(headers)} fields, got {len(values)}"

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
                        line_num += 1
                        continue

                    # Build row dict
                    row = dict(zip(headers, values, strict=False))

                except csv.Error as e:
                    # Catch CSV parsing errors (e.g., bad quoting, delimiter issues)
                    raw_row = {"__raw_line__": line, "__line_number__": line_num}
                    error_msg = f"CSV parse error at line {line_num}: {e}"

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
                    line_num += 1
                    continue

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

                line_num += 1

    def close(self) -> None:
        """Release resources (no-op for CSV source)."""
        pass
