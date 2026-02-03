# src/elspeth/plugins/sinks/json_sink.py
"""JSON sink plugin for ELSPETH.

Writes rows to JSON files. Supports JSON array and JSONL formats.

IMPORTANT: Sinks use allow_coercion=False to enforce that transforms
output correct types. Wrong types = upstream bug = crash.
"""

import hashlib
import json
import os
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


class JSONSinkConfig(SinkPathConfig):
    """Configuration for JSON sink plugin.

    Inherits from SinkPathConfig, which provides:
    - Path handling (from PathConfig)
    - Schema configuration (from DataPluginConfig)
    - Display header options (display_headers, restore_source_headers)
    """

    format: Literal["json", "jsonl"] | None = None
    indent: int | None = None
    encoding: str = "utf-8"
    validate_input: bool = False  # Optional runtime validation of incoming rows
    mode: Literal["write", "append"] = "write"  # "write" (truncate) or "append"


class JSONSink(BaseSink):
    """Write rows to a JSON file.

    Returns ArtifactDescriptor with SHA-256 content hash for audit integrity.

    Config options:
        path: Path to output JSON file (required)
        schema: Schema configuration (required, via PathConfig)
        format: "json" (array) or "jsonl" (lines). Auto-detected from extension.
        indent: Indentation for pretty-printing (default: None for compact)
        encoding: File encoding (default: "utf-8")
        validate_input: Validate incoming rows against schema (default: False)

    The schema can be:
        - Observed: {"mode": "observed"} - accept any fields
        - Fixed: {"mode": "fixed", "fields": ["id: int", "name: str"]}
        - Flexible: {"mode": "flexible", "fields": ["id: int"]} - at least these fields
    """

    name = "json"
    plugin_version = "1.0.0"
    # determinism inherited from BaseSink (IO_WRITE)

    # Note: supports_resume is set per-instance in __init__ based on format.
    # JSONL format supports resume (append), JSON array does not.
    # JSON array format rewrites the entire file on each write (seek(0) + truncate),
    # so it cannot append to existing output. JSONL writes line-by-line and can
    # append to existing files.

    def configure_for_resume(self) -> None:
        """Configure JSON sink for resume mode.

        Only JSONL format supports resume. JSON array format rewrites the
        entire file on each write and cannot append.

        Raises:
            NotImplementedError: If format is JSON array (not JSONL).
        """
        if self._format != "jsonl":
            raise NotImplementedError(
                f"JSONSink with format='{self._format}' does not support resume. "
                f"JSON array format rewrites the entire file and cannot append. "
                f"Use format='jsonl' for resumable JSON output."
            )
        self._mode = "append"

    def validate_output_target(self) -> "OutputValidationResult":
        """Validate existing JSONL file structure against configured schema.

        Reads the first line of the JSONL file to check field structure.

        Checks that:
        - Strict mode: Record fields match schema fields exactly (set comparison)
        - Free mode: All schema fields present (extras allowed)
        - Dynamic mode: No validation (schema adapts to existing structure)

        When display headers are configured (display_headers or restore_source_headers),
        the existing file keys are display names, so we map expected schema fields
        to their display equivalents before comparison.

        Note: Only JSONL format supports resume. JSON array returns valid=True
        (it will overwrite anyway).

        Returns:
            OutputValidationResult indicating compatibility.
        """
        from elspeth.contracts.sink import OutputValidationResult

        # Only JSONL supports resume - JSON array rewrites entirely
        if self._format != "jsonl":
            return OutputValidationResult.success()

        # No file or empty file = valid (will create on first write)
        if not self._path.exists() or self._path.stat().st_size == 0:
            return OutputValidationResult.success()

        # Read first line to check structure
        with open(self._path, encoding=self._encoding) as f:
            first_line = f.readline().strip()
            if not first_line:
                return OutputValidationResult.success()
            try:
                first_record = json.loads(first_line)
            except json.JSONDecodeError:
                return OutputValidationResult.failure(message="Existing JSONL file contains invalid JSON")

            # Ensure first record is a dict (JSONL should contain objects)
            if not isinstance(first_record, dict):
                return OutputValidationResult.failure(message="Existing JSONL file contains non-object records")

            existing = list(first_record.keys())

        # Dynamic schema = no validation needed
        if self._schema_config.is_observed:
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
            # Map normalized -> display for comparison against file keys
            expected = [display_map.get(f, f) for f in expected_normalized]
        else:
            expected = expected_normalized

        existing_set, expected_set = set(existing), set(expected)

        if self._schema_config.mode == "fixed":
            # Fixed: exact field match (set comparison)
            if existing_set != expected_set:
                return OutputValidationResult.failure(
                    message="JSONL record fields do not match schema (fixed mode)",
                    target_fields=existing,
                    schema_fields=expected,
                    missing_fields=sorted(expected_set - existing_set),
                    extra_fields=sorted(existing_set - expected_set),
                )
        else:  # mode == "flexible"
            # Flexible: schema fields must exist (extras allowed)
            missing = expected_set - existing_set
            if missing:
                return OutputValidationResult.failure(
                    message="JSONL record missing required schema fields (flexible mode)",
                    target_fields=existing,
                    schema_fields=expected,
                    missing_fields=sorted(missing),
                )

        return OutputValidationResult.success(target_fields=existing)

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        cfg = JSONSinkConfig.from_dict(config)

        self._path = cfg.resolved_path()
        self._encoding = cfg.encoding
        self._indent = cfg.indent
        self._validate_input = cfg.validate_input

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

        # Auto-detect format from extension if not specified
        fmt = cfg.format
        if fmt is None:
            fmt = "jsonl" if self._path.suffix == ".jsonl" else "json"
        self._format = fmt
        self._mode = cfg.mode

        # Set resume capability based on format
        # JSONL can append; JSON array rewrites entirely and cannot resume
        self.supports_resume = fmt == "jsonl"

        # Store schema config for audit trail
        # PathConfig (via DataPluginConfig) ensures schema_config is not None
        self._schema_config = cfg.schema_config

        # CRITICAL: allow_coercion=False - wrong types are bugs, not data to fix
        # Sinks receive PIPELINE DATA (already validated by source)
        self._schema_class: type[PluginSchema] = create_schema_from_config(
            self._schema_config,
            "JSONRowSchema",
            allow_coercion=False,  # Sinks reject wrong types (upstream bug)
        )

        # Set input_schema for protocol compliance
        self.input_schema = self._schema_class

        self._file: IO[str] | None = None
        self._rows: list[dict[str, Any]] = []  # Buffer for json array format

    def write(self, rows: list[dict[str, Any]], ctx: PluginContext) -> ArtifactDescriptor:
        """Write a batch of rows to the JSON file.

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
        if self._validate_input and not self._schema_config.is_observed:
            for row in rows:
                # Raises ValidationError on failure - this is intentional
                self._schema_class.model_validate(row)

        # Lazy resolution of display headers from Landscape
        # Must happen AFTER source iteration begins (when field resolution is recorded)
        self._resolve_display_headers_if_needed(ctx)

        # Lazy resolution of contract from context for headers: original mode
        # ctx.contract is set by orchestrator after first valid source row
        self._resolve_contract_from_context_if_needed(ctx)

        # Apply display header mapping to row keys if configured
        output_rows = self._apply_display_headers(rows)

        if self._format == "jsonl":
            self._write_jsonl_batch(output_rows)
        else:
            # Buffer rows for JSON array format
            self._rows.extend(output_rows)
            # Write immediately (file is rewritten on each write for JSON format)
            self._write_json_array()

        # Flush to ensure content is on disk for hashing
        if self._file is not None:
            self._file.flush()

        # Compute content hash from file
        content_hash = self._compute_file_hash()
        size_bytes = self._path.stat().st_size

        return ArtifactDescriptor.for_file(
            path=str(self._path),
            content_hash=content_hash,
            size_bytes=size_bytes,
        )

    def _write_jsonl_batch(self, rows: list[dict[str, Any]]) -> None:
        """Write rows as JSONL.

        Uses write mode (truncate) or append mode based on self._mode.
        Append mode is used during resume to add to existing output.
        """
        if self._file is None:
            file_mode = "a" if self._mode == "append" else "w"
            self._file = open(self._path, file_mode, encoding=self._encoding)  # noqa: SIM115

        for row in rows:
            json.dump(row, self._file)
            self._file.write("\n")

    def _write_json_array(self) -> None:
        """Write buffered rows as JSON array (rewrite mode)."""
        if self._file is None:
            # Handle kept open for streaming writes, closed in close()
            self._file = open(self._path, "w", encoding=self._encoding)  # noqa: SIM115
        self._file.seek(0)
        self._file.truncate()
        json.dump(self._rows, self._file, indent=self._indent)

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
            self._rows = []

    # === Display Header Support ===

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

    def set_resume_field_resolution(self, resolution_mapping: dict[str, str]) -> None:
        """Set field resolution mapping for resume validation.

        Called by CLI during `elspeth resume` to provide the source field resolution
        mapping BEFORE calling validate_output_target(). This allows validation to
        correctly compare expected display names against existing file keys when
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

    # === Contract Support ===

    def set_output_contract(self, contract: "SchemaContract") -> None:
        """Set output contract for header resolution.

        When headers mode is ORIGINAL, this contract is used to map
        normalized field names back to their original source header names.

        Args:
            contract: Schema contract with field metadata including original names
        """
        self._output_contract = contract

    def get_output_contract(self) -> "SchemaContract | None":
        """Get the output contract.

        Returns:
            The SchemaContract if set, None otherwise
        """
        return self._output_contract

    def _resolve_contract_from_context_if_needed(self, ctx: PluginContext) -> None:
        """Lazily resolve output contract from context for headers: original mode.

        Called on first write() to capture ctx.contract if _output_contract is not
        already set. This allows the new headers: original mode to work without
        explicit orchestrator wiring of set_output_contract().

        The orchestrator sets ctx.contract after the first valid source row is
        processed (see orchestrator/core.py line ~1164). By the time write() is
        called, the contract is available.

        Note:
            This only has effect when:
            1. headers mode is ORIGINAL
            2. _output_contract is not already set (via set_output_contract)
            3. ctx.contract is available

        Args:
            ctx: Plugin context with potential contract from orchestrator
        """
        # Only resolve if:
        # 1. We're in ORIGINAL mode (otherwise contract is irrelevant)
        # 2. Contract isn't already set (explicit set_output_contract takes precedence)
        # 3. Context has a contract to provide
        if self._headers_mode != HeaderMode.ORIGINAL:
            return
        if self._output_contract is not None:
            return  # Already set explicitly
        if ctx.contract is not None:
            self._output_contract = ctx.contract

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

    def _apply_display_headers(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply display header mapping to row keys.

        Args:
            rows: List of row dicts with normalized field names

        Returns:
            List of row dicts with display names as keys. If no display headers
            are configured, returns the original rows unchanged.
        """
        display_map = self._get_effective_display_headers()
        if display_map is None:
            return rows

        # Transform each row's keys to display names
        # Fields not in the mapping keep their original names (transform-added fields)
        return [{display_map.get(k, k): v for k, v in row.items()} for row in rows]

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
