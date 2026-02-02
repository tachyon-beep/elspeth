# src/elspeth/plugins/sinks/csv_sink.py
"""CSV sink plugin for ELSPETH.

Writes rows to CSV files with content hashing for audit integrity.

IMPORTANT: Sinks use allow_coercion=False to enforce that transforms
output correct types. Wrong types = upstream bug = crash.
"""

from __future__ import annotations

import csv
import hashlib
import os
from collections.abc import Sequence
from typing import IO, TYPE_CHECKING, Any, Literal

from elspeth.contracts import ArtifactDescriptor, PluginSchema

if TYPE_CHECKING:
    from elspeth.contracts.schema_contract import SchemaContract
    from elspeth.contracts.sink import OutputValidationResult
from elspeth.contracts.header_modes import HeaderMode, resolve_headers
from elspeth.plugins.base import BaseSink
from elspeth.plugins.config_base import SinkPathConfig
from elspeth.plugins.context import PluginContext
from elspeth.plugins.schema_factory import create_schema_from_config


class CSVSinkConfig(SinkPathConfig):
    """Configuration for CSV sink plugin.

    Inherits from SinkPathConfig, which provides:
    - Path handling (from PathConfig)
    - Schema configuration (from DataPluginConfig)
    - Display header options (display_headers, restore_source_headers)
    """

    delimiter: str = ","
    encoding: str = "utf-8"
    validate_input: bool = False  # Optional runtime validation of incoming rows
    mode: Literal["write", "append"] = "write"


class CSVSink(BaseSink):
    """Write rows to a CSV file.

    Returns ArtifactDescriptor with SHA-256 content hash for audit integrity.

    Creates the CSV file on first write. When schema is explicit, headers are
    derived from schema field definitions. When schema is dynamic, headers are
    inferred from the first row's keys.

    Config options:
        path: Path to output CSV file (required)
        schema: Schema configuration (required, via PathConfig)
        delimiter: Field delimiter (default: ",")
        encoding: File encoding (default: "utf-8")
        validate_input: Validate incoming rows against schema (default: False)
        mode: "write" (truncate, default) or "append" (add to existing file)

    The schema can be (all use infer-and-lock pattern):
        - Strict: {"mode": "strict", "fields": [...]} - columns from config, extras rejected
        - Free: {"mode": "free", "fields": [...]} - declared + first-row extras, then locked
        - Dynamic: {"fields": "dynamic"} - columns from first row, then locked

    Append mode behavior:
        - If file exists: reads headers from it and appends rows without header
        - If file doesn't exist or is empty: creates file with header (like write mode)
    """

    name = "csv"
    plugin_version = "1.0.0"
    # determinism inherited from BaseSink (IO_WRITE)

    # Resume capability: CSV can append to existing files
    supports_resume: bool = True

    def configure_for_resume(self) -> None:
        """Configure CSV sink for resume mode.

        Switches from truncate mode to append mode so resume operations
        add to existing output instead of overwriting.
        """
        self._mode = "append"

    def validate_output_target(self) -> OutputValidationResult:
        """Validate existing CSV file headers against configured schema.

        Checks that:
        - Strict mode: Headers match schema fields exactly (including order)
        - Free mode: All schema fields present (extras allowed)
        - Dynamic mode: No validation (schema adapts to existing headers)

        When display headers are configured (display_headers or restore_source_headers),
        the existing file headers are display names, so we map expected schema fields
        to their display equivalents before comparison.

        Returns:
            OutputValidationResult indicating compatibility.
        """
        from elspeth.contracts.sink import OutputValidationResult

        # No file = valid (will create with correct headers)
        if not self._path.exists():
            return OutputValidationResult.success()

        # Read existing headers
        with open(self._path, encoding=self._encoding, newline="") as f:
            reader = csv.DictReader(f, delimiter=self._delimiter)
            existing = list(reader.fieldnames or [])

        # Empty file = valid (will write headers on first write)
        if not existing:
            return OutputValidationResult.success()

        # Dynamic schema = no validation needed
        if self._schema_config.is_dynamic:
            return OutputValidationResult.success(target_fields=existing)

        # Get expected fields from schema (guaranteed non-None when not dynamic)
        fields = self._schema_config.fields
        if fields is None:
            return OutputValidationResult.success(target_fields=existing)

        # Base expected fields are normalized schema names
        expected_normalized = [f.name for f in fields]

        # When display headers are configured, the file contains display names
        # Map expected fields to their display equivalents for comparison
        display_map = self._get_effective_display_headers()
        if display_map is not None:
            # Map normalized -> display for comparison against file headers
            expected = [display_map.get(f, f) for f in expected_normalized]
        else:
            expected = expected_normalized

        existing_set, expected_set = set(existing), set(expected)

        if self._schema_config.mode == "strict":
            # Strict: exact match including order
            if existing != expected:
                return OutputValidationResult.failure(
                    message="CSV headers do not match schema (strict mode)",
                    target_fields=existing,
                    schema_fields=expected,
                    missing_fields=sorted(expected_set - existing_set),
                    extra_fields=sorted(existing_set - expected_set),
                    order_mismatch=(existing_set == expected_set),
                )
        else:  # mode == "free"
            # Free: schema fields must exist (extras allowed)
            missing = expected_set - existing_set
            if missing:
                return OutputValidationResult.failure(
                    message="CSV missing required schema fields (free mode)",
                    target_fields=existing,
                    schema_fields=expected,
                    missing_fields=sorted(missing),
                )

        return OutputValidationResult.success(target_fields=existing)

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        cfg = CSVSinkConfig.from_dict(config)

        self._path = cfg.resolved_path()
        self._delimiter = cfg.delimiter
        self._encoding = cfg.encoding
        self._validate_input = cfg.validate_input
        self._mode = cfg.mode

        # Display header configuration (legacy options)
        self._display_headers = cfg.display_headers
        self._restore_source_headers = cfg.restore_source_headers
        # Populated lazily on first write if restore_source_headers=True
        # Must be lazy because field resolution is only recorded AFTER first source iteration,
        # which happens after on_start() is called.
        self._resolved_display_headers: dict[str, str] | None = None
        self._display_headers_resolved: bool = False  # Track if we've attempted resolution

        # New header mode configuration (takes precedence over legacy options)
        self._headers_mode: HeaderMode = cfg.headers_mode
        self._headers_custom_mapping: dict[str, str] | None = cfg.headers_mapping

        # Output contract for header resolution (set via set_output_contract)
        self._output_contract: SchemaContract | None = None

        # Store schema config for audit trail
        # PathConfig (via DataPluginConfig) ensures schema_config is not None
        self._schema_config = cfg.schema_config

        # CSV supports all schema modes via infer-and-lock:
        # - mode='strict': columns from config, extras rejected at write time
        # - mode='free': declared columns + extras from first row, then locked
        # - fields='dynamic': columns from first row, then locked
        #
        # DictWriter's default extrasaction='raise' enforces the lock - any row
        # with fields not in the established fieldnames will error.

        # CRITICAL: allow_coercion=False - wrong types are bugs, not data to fix
        # Sinks receive PIPELINE DATA (already validated by source)
        self._schema_class: type[PluginSchema] = create_schema_from_config(
            self._schema_config,
            "CSVRowSchema",
            allow_coercion=False,  # Sinks reject wrong types (upstream bug)
        )

        # Set input_schema for protocol compliance
        self.input_schema = self._schema_class

        self._file: IO[str] | None = None
        self._writer: csv.DictWriter[str] | None = None
        self._fieldnames: Sequence[str] | None = None

    def write(self, rows: list[dict[str, Any]], ctx: PluginContext) -> ArtifactDescriptor:
        """Write a batch of rows to the CSV file.

        Args:
            rows: List of row dicts to write
            ctx: Plugin context

        Returns:
            ArtifactDescriptor with content_hash (SHA-256) and size_bytes

        Raises:
            ValidationError: If validate_input=True and a row fails validation.
                This indicates a bug in an upstream transform.
        """
        if not rows:
            # Empty batch - return descriptor for empty content
            return ArtifactDescriptor.for_file(
                path=str(self._path),
                content_hash=hashlib.sha256(b"").hexdigest(),
                size_bytes=0,
            )

        # Optional input validation - crash on failure (upstream bug!)
        if self._validate_input and not self._schema_config.is_dynamic:
            for row in rows:
                # Raises ValidationError on failure - this is intentional
                self._schema_class.model_validate(row)

        # Lazy resolution of display headers from Landscape
        # Must happen AFTER source iteration begins (when field resolution is recorded)
        self._resolve_display_headers_if_needed(ctx)

        # Lazy initialization - open file on first write
        if self._file is None:
            self._open_file(rows)

        # Write all rows in batch
        # Invariant: _file and _writer are always set together (by _open_file above)
        file = self._file
        writer = self._writer
        if file is None or writer is None:
            raise RuntimeError("CSVSink writer not initialized - this is a bug")
        for row in rows:
            writer.writerow(row)

        # Flush to ensure content is on disk for hashing
        file.flush()

        # Compute content hash from file
        content_hash = self._compute_file_hash()
        size_bytes = self._path.stat().st_size

        return ArtifactDescriptor.for_file(
            path=str(self._path),
            content_hash=content_hash,
            size_bytes=size_bytes,
        )

    def _open_file(self, rows: list[dict[str, Any]]) -> None:
        """Open file for writing, handling append mode and display headers.

        In append mode:
        - If file exists with headers: read headers from it, open in append mode
        - If file doesn't exist or is empty: create with headers (like write mode)

        In write mode:
        - Always truncate and write headers

        When schema is explicit (not dynamic), fieldnames are derived from schema
        field definitions. This ensures all defined fields (including optional ones)
        are present in the CSV header.

        When schema is dynamic, fieldnames are inferred from the first row's keys.

        Display Headers:
        When display_headers or restore_source_headers is configured, the CSV header
        row uses display names but row data uses normalized field names. This is
        handled by writing the header manually and configuring the DictWriter with
        the original data field names.

        Args:
            rows: First batch of rows (used to determine fieldnames if dynamic schema)
        """
        if self._mode == "append" and self._path.exists():
            # Try to read existing headers from file
            with open(self._path, encoding=self._encoding, newline="") as f:
                reader = csv.DictReader(f, delimiter=self._delimiter)
                existing_fieldnames = reader.fieldnames

            if existing_fieldnames:
                # Validate headers against explicit schema before opening
                # Dynamic schema = no validation (file headers are authoritative)
                if not self._schema_config.is_dynamic:
                    validation = self.validate_output_target()
                    if not validation.valid:
                        # Build clear error message
                        msg_parts = [f"CSV schema mismatch: {validation.error_message}"]
                        if validation.missing_fields:
                            msg_parts.append(f"Missing fields: {list(validation.missing_fields)}")
                        if validation.extra_fields:
                            msg_parts.append(f"Extra fields: {list(validation.extra_fields)}")
                        if validation.order_mismatch:
                            msg_parts.append("Fields present but in wrong order (strict mode)")
                        raise ValueError(". ".join(msg_parts))

                # In append mode with display headers, we need to map existing file headers
                # back to data field names for the DictWriter
                display_map = self._get_effective_display_headers()
                if display_map is not None:
                    # Reverse the display map to get display_name -> data_field
                    reverse_map = {v: k for k, v in display_map.items()}
                    # Map existing headers (display names) back to data field names
                    self._fieldnames = [reverse_map.get(h, h) for h in existing_fieldnames]
                else:
                    self._fieldnames = list(existing_fieldnames)

                self._file = open(  # noqa: SIM115 - handle kept open for streaming writes, closed in close()
                    self._path, "a", encoding=self._encoding, newline=""
                )
                self._writer = csv.DictWriter(
                    self._file,
                    fieldnames=self._fieldnames,
                    delimiter=self._delimiter,
                )
                # No header write - already exists
                return

        # Write mode OR append to non-existent/empty file
        # Get data field names (for DictWriter row lookup) and display names (for header)
        data_fields, display_fields = self._get_field_names_and_display(rows[0])

        # Store data field names for DictWriter
        self._fieldnames = data_fields

        self._file = open(  # noqa: SIM115 - handle kept open for streaming writes, closed in close()
            self._path, "w", encoding=self._encoding, newline=""
        )
        self._writer = csv.DictWriter(
            self._file,
            fieldnames=self._fieldnames,
            delimiter=self._delimiter,
        )

        # Write header row using display names if configured
        if display_fields != data_fields:
            # Write display headers using csv.writer to handle quoting properly
            # Display names may contain delimiters, quotes, or newlines (e.g., "Amount, USD")
            header_writer = csv.writer(self._file, delimiter=self._delimiter)
            header_writer.writerow(display_fields)
        else:
            # No display mapping - use standard writeheader()
            self._writer.writeheader()

    def _get_field_names_and_display(self, row: dict[str, Any]) -> tuple[list[str], list[str]]:
        """Get data field names and display names for CSV output.

        When schema is explicit, field names come from schema definition.
        This ensures all defined fields (including optional ones) are present.

        When schema is dynamic, falls back to inferring from row keys.

        Returns:
            Tuple of (data_fields, display_fields):
            - data_fields: Field names matching row dict keys (for DictWriter)
            - display_fields: Display names for CSV header row
            When no display headers are configured, both lists are identical.
        """
        # Get base field names from schema or row
        if not self._schema_config.is_dynamic and self._schema_config.fields:
            # Explicit schema: use field names from schema definition
            data_fields = [field_def.name for field_def in self._schema_config.fields]
        else:
            # Dynamic schema: infer from row keys
            data_fields = list(row.keys())

        # Apply display header mapping if configured
        display_map = self._get_effective_display_headers()
        if display_map is None:
            return data_fields, data_fields

        # Map field names to display names, falling back to original if not mapped
        # This handles transform-added fields that have no original header
        display_fields = [display_map.get(field, field) for field in data_fields]
        return data_fields, display_fields

    def _get_effective_display_headers(self) -> dict[str, str] | None:
        """Get the effective display header mapping.

        Priority order:
        1. CUSTOM mode with custom mapping from 'headers' config
        2. ORIGINAL mode with contract - use resolve_headers()
        3. Legacy display_headers config (explicit mapping)
        4. Legacy restore_source_headers - resolved display headers
        5. None (no mapping - use normalized names)

        Returns:
            Dict mapping normalized field name -> display name, or None if no
            display headers are configured or if using NORMALIZED mode.
        """
        # NORMALIZED mode = no display mapping
        if self._headers_mode == HeaderMode.NORMALIZED:
            return None

        # CUSTOM mode - use custom mapping from config
        if self._headers_mode == HeaderMode.CUSTOM:
            if self._headers_custom_mapping is not None:
                return self._headers_custom_mapping
            # Fall through to legacy display_headers if custom mapping not set
            if self._display_headers is not None:
                return self._display_headers
            return None

        # ORIGINAL mode - use contract to resolve headers
        # (mypy knows this is the only remaining case since HeaderMode has exactly 3 values)
        if self._output_contract is not None:
            # Use resolve_headers() to build mapping from contract
            return resolve_headers(
                contract=self._output_contract,
                mode=HeaderMode.ORIGINAL,
                custom_mapping=None,
            )
        # Fall through to legacy resolved_display_headers if no contract
        if self._resolved_display_headers is not None:
            return self._resolved_display_headers
        # No contract and no legacy resolution - return None (fallback to normalized)
        return None

    # === Contract Support ===

    def set_output_contract(self, contract: SchemaContract) -> None:
        """Set output contract for header resolution.

        When headers mode is ORIGINAL, this contract is used to map
        normalized field names back to their original source header names.

        Args:
            contract: Schema contract with field metadata including original names
        """
        self._output_contract = contract

    def get_output_contract(self) -> SchemaContract | None:
        """Get the output contract.

        Returns:
            The SchemaContract if set, None otherwise
        """
        return self._output_contract

    def set_resume_field_resolution(self, resolution_mapping: dict[str, str]) -> None:
        """Set field resolution mapping for resume validation.

        Called by CLI during `elspeth resume` to provide the source field resolution
        mapping BEFORE calling validate_output_target(). This allows validation to
        correctly compare expected display names against existing file headers when
        restore_source_headers=True.

        Args:
            resolution_mapping: Dict mapping original header name -> normalized field name.
                This is the same format returned by Landscape.get_source_field_resolution().

        Note:
            This only has effect when restore_source_headers=True. For explicit
            display_headers, the mapping is already available from config.
        """
        if not self._restore_source_headers:
            return  # No-op if not using restore_source_headers

        # Build reverse mapping: normalized -> original (display name)
        self._resolved_display_headers = {v: k for k, v in resolution_mapping.items()}
        self._display_headers_resolved = True

    def _resolve_display_headers_if_needed(self, ctx: PluginContext) -> None:
        """Lazily resolve display headers from Landscape if restore_source_headers=True.

        Called on first write() to fetch field resolution mapping. This MUST be lazy
        because the orchestrator calls sink.on_start() BEFORE source.load() iterates,
        and record_source_field_resolution() only happens after the first source row.

        Args:
            ctx: Plugin context with Landscape access.

        Raises:
            ValueError: If Landscape is unavailable or source didn't record resolution.
        """
        if self._display_headers_resolved:
            return  # Already resolved (or not needed)

        self._display_headers_resolved = True

        if not self._restore_source_headers:
            return  # Nothing to resolve

        # Fetch source field resolution from Landscape
        if ctx.landscape is None:
            raise ValueError(
                "restore_source_headers=True requires Landscape to be available. "
                "This is a framework bug - context should have landscape set."
            )

        resolution_mapping = ctx.landscape.get_source_field_resolution(ctx.run_id)
        if resolution_mapping is None:
            raise ValueError(
                "restore_source_headers=True but source did not record field resolution. "
                "Ensure source uses normalize_fields: true to enable header restoration."
            )

        # Build reverse mapping: final (normalized) -> original
        self._resolved_display_headers = {v: k for k, v in resolution_mapping.items()}

    def _compute_file_hash(self) -> str:
        """Compute SHA-256 hash of the file contents."""
        sha256 = hashlib.sha256()
        with open(self._path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def flush(self) -> None:
        """Flush buffered data to disk with fsync for durability.

        CRITICAL: Ensures data survives process crash and power loss.
        Called by orchestrator BEFORE creating checkpoints.

        This guarantees:
        - OS buffer flushed to disk (file.flush())
        - Filesystem metadata persisted (os.fsync())
        - Data durable on storage device
        """
        if self._file is not None:
            self._file.flush()
            os.fsync(self._file.fileno())

    def close(self) -> None:
        """Close the file handle."""
        if self._file is not None:
            self._file.close()
            self._file = None
            self._writer = None

    # === Lifecycle Hooks ===

    def on_start(self, ctx: PluginContext) -> None:
        """Called before processing begins.

        Note: restore_source_headers resolution is done lazily in write() because
        the field resolution mapping is only recorded AFTER source iteration begins,
        which happens after on_start() is called.
        """
        pass

    def on_complete(self, ctx: PluginContext) -> None:
        """Called after processing completes."""
        pass
