# Architecture Analysis: Source and Sink Plugins

**Date:** 2026-02-22
**Branch:** RC3.3-architectural-remediation
**Scope:** `src/elspeth/plugins/sources/` and `src/elspeth/plugins/sinks/`
**Confidence:** High

---

## Per-File Analysis

### 1. `csv_source.py` — CSVSource

#### Purpose
Loads rows from CSV files and yields them as `SourceRow` instances (valid or quarantined). Handles multi-line quoted fields, encoding detection failures, configurable skip rows, column normalization, and schema validation at the Tier 3 trust boundary.

#### Key Classes/Functions
- `CSVSourceConfig(TabularSourceDataConfig)` — Pydantic config with delimiter, encoding, skip_rows
- `CSVSource(BaseSource)` — Main plugin class with `load()` and `_load_from_file()` methods
- `load()` — Opens file, handles UnicodeDecodeError at open() time, delegates to `_load_from_file()`
- `_load_from_file()` — Inner loop: skip rows, read header, resolve fields, validate each row
- `get_field_resolution()` — Returns audit trail data for original→normalized field mapping

#### Dependencies
- `elspeth.contracts`: `PluginSchema`, `SourceRow`
- `elspeth.contracts.contract_builder`: `ContractBuilder`
- `elspeth.contracts.schema_contract_factory`: `create_contract_from_config`
- `elspeth.plugins.base`: `BaseSource`
- `elspeth.plugins.config_base`: `TabularSourceDataConfig`
- `elspeth.plugins.schema_factory`: `create_schema_from_config`
- `elspeth.plugins.sources.field_normalization`: `FieldResolution`, `resolve_field_names`
- Standard library: `csv`, `collections.abc`, `pydantic`

#### Trust Boundary Handling
Correct and thorough. The file explicitly annotates `allow_coercion=True` as source-only. Error handling covers:
- `UnicodeDecodeError` at `open()` — quarantined with file-level metadata
- `UnicodeDecodeError` during row reading — quarantined with line number
- `csv.Error` during `skip_rows` — record and stop (corrupted parser state)
- `csv.Error` at header read — quarantine/discard, return
- `csv.Error` per data row — quarantine the row, continue processing
- Column count mismatch — quarantine row with raw content
- Pydantic `ValidationError` — quarantine row with error string
- Contract violation (type drift after first row) — quarantine row

The `_load_from_file()` split from `load()` is intentional: the `UnicodeDecodeError` during iteration must be caught at the `load()` level because Python generators don't propagate errors through the outer context correctly otherwise.

#### Error Handling
Comprehensive. Every failure mode yields a `SourceRow.quarantined()` (unless `on_validation_failure == "discard"`) and calls `ctx.record_validation_error()` for audit trail completeness. The "record even when discarding" pattern is correct — absence of a record would mean we could not distinguish "file had no data" from "file had bad data that was silently dropped."

#### Concerns
1. **MINOR — `strict=False` in `zip(headers, values)`**: Line 398 uses `zip(headers, values, strict=False)`. This is intentional (column count mismatch is already validated above), but the comment that explains why is absent at the call site. The column count guard at line 374 makes this safe, but future maintainers may question it.
2. **MINOR — `_field_resolution` is `None` before `load()`**: `get_field_resolution()` returns `None` if called before `load()` or for headerless files with no normalization. Callers must handle this `None` case. This is documented but could silently produce no audit data if a caller forgets to check.
3. **MINOR — Empty row skip silently**: Blank lines (empty `values`) are skipped at line 365 with no audit record. Per the data manifesto, absent data should be recorded. Blank lines in a CSV are a known-to-be-harmless edge case, but the audit trail will not show that blank lines existed.

---

### 2. `json_source.py` — JSONSource

#### Purpose
Loads rows from JSON array or JSONL files. Handles NaN/Infinity rejection, encoding errors (including surrogateescape sequences for broken multibyte encodings), nested data extraction via `data_key`, and schema validation. Auto-detects format from file extension.

#### Key Classes/Functions
- `JSONSourceConfig(SourceDataConfig)` — Pydantic config with format, data_key, encoding
- `_reject_nonfinite_constant(value)` — Hook passed to `json.loads(parse_constant=...)` to reject NaN/Infinity at parse time
- `_contains_surrogateescape_chars(value)` — Detects low-surrogate code points from failed decode
- `_surrogateescape_line_to_bytes(value, encoding)` — Re-encodes for quarantine hex storage
- `JSONSource(BaseSource)` — Main plugin class
- `load()` — Dispatcher to `_load_jsonl()` or `_load_json_array()`
- `_load_jsonl()` — Line-by-line with per-line quarantine
- `_load_json_array()` — Full-file load with structure validation
- `_validate_and_yield()` — Shared schema validation logic
- `_record_parse_error()` — DRY helper for parse error recording

#### Dependencies
Same pattern as CSVSource but without `field_normalization` (JSON has no CSV headers to normalize). Imports `ContractBuilder` lazily inside `__init__` (inside the method body), which is unusual but not incorrect.

#### Trust Boundary Handling
Strong. The `parse_constant=_reject_nonfinite_constant` hook addresses a known Python `json` module defect where `NaN`, `Infinity`, and `-Infinity` are accepted despite being non-standard JSON. This directly addresses the known P0 concern about NaN/Infinity acceptance. The JSONL path handles surrogateescape-encoded bytes gracefully, preserving them as hex in the quarantine record rather than crashing or silently losing them.

Structure validation for JSON array mode is layered:
1. Parse failure → quarantine/discard file
2. `data_key` on non-dict root → quarantine
3. `data_key` not found → quarantine with available keys listed
4. Extracted value is not a list → quarantine
5. Per-row Pydantic validation → quarantine
6. Contract violation (type drift) → quarantine

#### Error Handling
Well-structured. `_record_parse_error()` DRY helper correctly captures the "record always, yield only if not discard" pattern. The `_validate_and_yield()` helper is shared between array and JSONL paths, ensuring consistent contract-lock behavior.

#### Concerns
1. **MODERATE — Late import in `__init__`**: Lines 130-131 do `from elspeth.contracts.contract_builder import ContractBuilder` and `from elspeth.contracts.schema_contract_factory import create_contract_from_config` inside `__init__`. This is inconsistent with the module-level imports in `csv_source.py` and all other files. It avoids no circular import (these are contract modules, not plugins). Should be moved to module level.
2. **MINOR — `_first_valid_row_processed` as instance attribute set in `load()`**: The attribute `self._first_valid_row_processed` is initialized in `load()` (line 165), not in `__init__()`. If `_validate_and_yield()` were ever called outside `load()` (e.g., in a test), this would raise `AttributeError`. In practice it cannot happen, but the pattern is fragile.
3. **MINOR — `_load_json_array` opens file inside nested `try`**: The outer `try`/`except UnicodeDecodeError` wraps the entire file processing, but the inner `try`/`except (json.JSONDecodeError, ValueError)` only covers `json.load()`. The structure is correct but the nesting is somewhat unusual. A reader could mistake the outer `try` for being broader than it is.
4. **MINOR — Inconsistent contract behavior for FIXED vs FLEXIBLE/OBSERVED in `__init__`**: For FIXED schemas, the contract is locked and set immediately. For FLEXIBLE/OBSERVED, `_contract_builder` is created and the contract is set after the first row. The CSVSource always defers to `load()` time (because it needs `field_resolution`). The JSON path tries to optimize by locking FIXED schemas early. This divergence works correctly but adds conceptual overhead.

---

### 3. `null_source.py` — NullSource

#### Purpose
A no-op source that yields zero rows. Used during resume operations where rows come from the payload store, not from a live data source. Satisfies `SourceProtocol.output_schema` typing and DAG validation requirements.

#### Key Classes/Functions
- `NullSourceSchema(PluginSchema)` — Empty observed schema with `extra="allow"` to satisfy DAG validator's observed-schema detection
- `NullSource(BaseSource)` — Yields `iter([])`

#### Dependencies
- `elspeth.contracts`: `Determinism`, `PluginSchema`, `SourceRow`
- `elspeth.contracts.plugin_context`: `PluginContext`
- `elspeth.plugins.base`: `BaseSource`
- `pydantic`: `ConfigDict`

#### Trust Boundary Handling
Not applicable — no external data is ingested.

#### Error Handling
None needed — it never yields rows.

#### Concerns
1. **MINOR — Config defaulting in `__init__`**: If `"schema"` is absent from `config`, `NullSource.__init__` silently injects `{"mode": "observed"}`. This is a defensive pattern (`if "schema" not in config_copy`) applied to Tier 1 system config. Per the data manifesto and CLAUDE.md prohibition on defensive programming, system-owned config should crash if malformed, not be silently corrected. The comment says "NullSource requires no other specific config," which is correct, but the fix should be to document that `BaseSource` requires a `schema` key and provide the default at the YAML/config-loading level, not inside the plugin.
2. **INFO — `_on_validation_failure = "discard"` as class attribute**: Setting this as a class-level string (not from config) is correct for NullSource. No concern.

---

### 4. `field_normalization.py` — Field Name Normalization

#### Purpose
Normalizes messy external CSV headers (e.g., `"CaSE Study1 !!!! xx!"`) to valid Python identifiers (`"case_study1_xx"`) at the Tier 3 source boundary. Provides versioned, auditable field resolution with collision detection.

#### Key Classes/Functions
- `NORMALIZATION_ALGORITHM_VERSION = "1.0.0"` — Frozen version for audit trail
- `normalize_field_name(raw)` — 9-step normalization pipeline producing a valid Python identifier
- `check_normalization_collisions(raw_headers, normalized_headers)` — Raises on collision with full detail
- `check_mapping_collisions(pre_mapping, post_mapping, field_mapping)` — Raises on user-mapping collision
- `check_duplicate_raw_headers(raw_headers)` — Raises on ambiguous raw duplicates
- `FieldResolution` — Frozen dataclass: `final_headers`, `resolution_mapping`, `normalization_version`
- `resolve_field_names(...)` — Orchestrates the full resolution pipeline

#### Dependencies
- Standard library: `re`, `unicodedata`, `keyword`, `dataclasses`
- No ELSPETH internal imports — pure utility module

#### Trust Boundary Handling
This module IS the trust boundary mechanism for field names. It correctly raises `ValueError` on ambiguous or invalid inputs (collision, empty normalization result). The `ValueError` propagates up to `CSVSource._load_from_file()` which intentionally does not catch it (a collision is a configuration error, not a per-row data error).

#### Error Handling
- Collision detection raises with full detail (which columns, their positions, and their names)
- Defense-in-depth: `normalized.isidentifier()` check after normalization confirms the algorithm is correct — a failure here indicates a bug in normalization, not user data
- Empty normalization result raises `ValueError` with the original raw value

#### Concerns
1. **MINOR — `FieldResolution.final_headers` is `list[str]`, not `tuple[str, ...]`**: The `FieldResolution` dataclass is `frozen=True`, but `final_headers` and `resolution_mapping` are mutable types (`list`, `dict`). `frozen=True` only prevents reassignment of the field, not mutation of the contained object. A caller could do `resolution.final_headers.append("injected")` and corrupt the audit-trail mapping. Should be `tuple[str, ...]` and `types.MappingProxyType` respectively (or at minimum the fields should be documented as "do not mutate").
2. **MINOR — `noqa: SIM401` comment on line 267**: The comment suppresses a Ruff suggestion to use `.get()`, citing the no-bug-hiding policy. This is correct and desirable. The suppression comment is itself documentation of intent. No action needed, but worth noting in code review.

---

### 5. `csv_sink.py` — CSVSink

#### Purpose
Writes pipeline rows to a CSV file with SHA-256 content hashing for audit integrity. Supports write and append modes (for resume), custom display headers (normalized/original/custom mapping), incremental content hashing, and atomic batch staging (all rows staged in memory before writing).

#### Key Classes/Functions
- `CSVSinkConfig(SinkPathConfig)` — Config with delimiter, encoding, validate_input, mode
- `CSVSink(BaseSink)` — Main plugin
- `write(rows, ctx)` — Batch write with memory staging and incremental hashing
- `_open_file(rows)` — Lazy file initialization with append-mode header compatibility check
- `_get_field_names_and_display(row)` — Schema-mode-aware field name selection
- `_get_effective_display_headers()` — Priority-ordered display header resolution
- `validate_output_target()` — Pre-append schema compatibility check
- `configure_for_resume()` — Switches to append mode
- `flush()` — `file.flush()` + `os.fsync()` for crash safety
- `set_output_contract()`, `_resolve_contract_from_context_if_needed()`, `_resolve_display_headers_if_needed()` — Header resolution wiring

#### Dependencies
- `elspeth.contracts`: `ArtifactDescriptor`, `PluginSchema`
- `elspeth.contracts.header_modes`: `HeaderMode`, `resolve_headers`
- `elspeth.contracts.plugin_context`: `PluginContext`
- `elspeth.plugins.base`: `BaseSink`
- `elspeth.plugins.config_base`: `SinkPathConfig`
- `elspeth.plugins.schema_factory`: `create_schema_from_config`
- Standard library: `csv`, `hashlib`, `io`, `os`

#### Trust Boundary Handling
Correct. `allow_coercion=False` is set. The sink expects Tier 2 pipeline data and does not attempt to coerce. Wrong types are bugs, not data quality issues.

The batch staging via `io.StringIO` (lines 268-278) is a notable correctness improvement: if any row fails DictWriter serialization (e.g., extra fields in fixed mode), no rows are written. This prevents audit divergence where CSV has partial writes that the Landscape marked as FAILED.

#### Error Handling
- `validate_output_target()` checks schema compatibility before appending
- Append-mode mismatch raises `ValueError` before opening file
- DictWriter with default `extrasaction='raise'` enforces schema lock at write time
- Empty batch returns a descriptor for empty content (no file write)

#### Concerns
1. **MODERATE — Incremental hashing reads newly-written bytes from disk (lines 290-294)**: After each batch write, the hasher reads back the newly-written bytes from disk via `bf.seek(pre_write_size)`. This is a correctness issue if the OS write buffer is not flushed before the read: the `file.flush()` on line 286 flushes the Python buffer, but `os.fsync()` is only called in `flush()` (the lifecycle hook), not during `write()`. On most OS/hardware combinations the `file.flush()` is sufficient to make the data visible to a subsequent `open()` + `read()`, but there is a theoretical race where the hasher reads stale data if the OS has not committed the buffer. This is distinct from the durability concern (power loss); it is a correctness concern within a single run.
2. **MINOR — `pre_write_size` uses `stat().st_size` before `file.flush()` (line 281 precedes line 284/286)**: The size is read before the write happens, which is correct — it marks the start of the new content. But if the file is opened without buffering or if an earlier batch partially flushed, the `st_size` might not reflect what `bf.seek()` will find. This appears safe in practice because the file is opened with standard Python buffering (not direct I/O), but the sequencing should be documented.
3. **MINOR — `_display_headers_resolved` flag set to `True` before the actual resolution attempt (lines 571-573 in `_resolve_display_headers_if_needed`)**: The flag is set to `True` unconditionally at the start of the method to prevent re-entry. If the Landscape call raises (lines 583-593), the flag remains `True`, meaning subsequent calls will not retry. For `headers: original` mode, a transient Landscape failure would silently fall back to no display headers (because `_resolved_display_headers` remains `None` and `_get_effective_display_headers()` returns `None`). However the `ValueError` at line 584 would propagate to the caller and abort the write, so in practice this is not a silent failure — but the flag pattern deserves a comment explaining why early-set is safe.
4. **MINOR — Duplicate `_resolve_contract_from_context_if_needed` and `_resolve_display_headers_if_needed` logic**: These two methods are verbatim duplicated between `csv_sink.py` and `json_sink.py` (see also item 2 in json_sink.py concerns). This is a DRY violation in shared sink behavior that could be extracted to a mixin or base class.

---

### 6. `json_sink.py` — JSONSink

#### Purpose
Writes pipeline rows to JSON array or JSONL files. For JSON array format, uses atomic temp-file-write + `os.replace()` to prevent data loss on crash (addressing the known P0). JSONL format uses a persistent file handle with append/write mode. Supports display header key remapping.

#### Key Classes/Functions
- `JSONSinkConfig(SinkPathConfig)` — Config with format, indent, encoding, validate_input, mode. Has a `@model_validator` that rejects `format='json'` + `mode='append'`
- `JSONSink(BaseSink)` — Main plugin
- `write(rows, ctx)` — Dispatcher
- `_write_jsonl_batch(rows)` — Persistent file handle, appends line by line
- `_write_json_array()` — Atomic write: temp file → fsync → `os.replace()` → dir fsync
- `_compute_file_hash()` — Full-file SHA-256 scan after each write
- `configure_for_resume()` — JSONL only; raises `NotImplementedError` for JSON array
- `validate_output_target()` — JSONL resume compatibility check (reads first line)
- `_apply_display_headers(rows)` — Key-remapping for JSON output
- Display header resolution: same lazy pattern as CSVSink

#### Dependencies
Same as CSVSink but without `csv` module; adds `json`.

#### Trust Boundary Handling
Correct. `allow_coercion=False`. No coercion of incoming pipeline data.

#### Error Handling
- `@model_validator` rejects `format='json'` + `mode='append'` at construction time (config-level enforcement)
- `_write_json_array()` cleans up the temp file on any `BaseException`, including `KeyboardInterrupt` and `SystemExit`
- JSONL append validates schema compatibility before opening the file
- `_apply_display_headers()` raises `ValueError` on header collision (prevents silent data corruption from two fields mapping to the same output key)

#### Concerns — The Known P0 is RESOLVED in This Code
The `_write_json_array()` implementation correctly uses atomic write: write to `.tmp` → fsync → `os.replace()` → dir fsync. The old truncate-then-write is gone. **The known P0 (JSON sink data loss) is fixed in the current codebase.** This should be updated in the project memory.

#### Remaining Concerns
1. **MODERATE — Full-file hash on every `write()` call**: `_compute_file_hash()` (lines 373-379) reads the entire file from the beginning on every `write()` call. For JSON array format, this is unavoidable because the file is rewritten each time (and is bounded by the total data written so far). For JSONL format, however, this is O(total file size) per batch — each subsequent batch reads the entire file. CSVSink avoids this with incremental hashing (`_hasher` that only reads the newly-written bytes). JSONSink should use the same pattern for JSONL mode.
2. **MODERATE — Duplicate display header resolution code**: `_resolve_contract_from_context_if_needed()`, `_resolve_display_headers_if_needed()`, `_get_effective_display_headers()`, and `set_resume_field_resolution()` are verbatim duplicates of the same methods in `csv_sink.py`. Any fix in one must be manually applied to the other. This should be extracted to a shared mixin (`DisplayHeaderMixin`) or moved to the `BaseSink` class.
3. **MINOR — `_rows` accumulates in memory for JSON array format**: `self._rows` buffers all rows written during the run for JSON array format (line 247, extended at line 287). This is necessary because the JSON array format requires knowing all rows at write time. For large runs this is an unbounded memory accumulation. There is no configurable limit or streaming alternative. This is an inherent architectural tradeoff of the JSON array format, but it should be documented.
4. **MINOR — `close()` clears `self._rows = []` (line 400)**: If `close()` is called before the final `write()`, buffered rows would be lost. The orchestrator lifecycle should prevent this, but there is no guard. If `close()` is called (e.g., on exception during run), the JSON array file will have the content from the last successful `write()`, which is the last rewrite — consistent. The `_rows = []` in `close()` prevents memory leaks but would cause silent data loss if `write()` were called after `close()` (it would succeed writing an empty file).
5. **MINOR — `_write_jsonl_batch` uses bare `open()` without `newline=""` parameter** (line 332): For JSONL output, each row ends with `\n`. On Windows, without `newline=""`, Python would translate `\n` to `\r\n`, producing non-standard JSONL with double line endings when read back on POSIX. This is a Windows portability bug. The CSVSink correctly uses `newline=""` throughout.

---

### 7. `database_sink.py` — DatabaseSink

#### Purpose
Writes pipeline rows to a database table via SQLAlchemy Core. Infers table schema from Pydantic field definitions or first-row keys. Hashes the canonical JSON payload BEFORE insert (proving intent — the database may transform data post-insert). Records all DDL and DML operations in the audit trail.

#### Key Classes/Functions
- `DatabaseSinkConfig(DataPluginConfig)` — Config with url, table, if_exists, validate_input
- `DatabaseSink(BaseSink)` — Main plugin
- `write(rows, ctx)` — Canonical hash pre-insert, then batch INSERT with `ctx.record_call`
- `_ensure_table(row, ctx)` — Lazy table creation with `if_exists` handling
- `_drop_table_if_exists(ctx)` — Instrumented DDL for audit trail
- `_create_columns_from_schema_or_row(row)` — Maps schema field types to SQLAlchemy types
- `_serialize_any_typed_fields(rows)` — Converts dict/list values to JSON strings for TEXT columns
- `_compute_any_typed_fields()` — Identifies `any`-typed fields from schema
- `validate_output_target()` — SQLAlchemy inspector-based column compatibility check
- `configure_for_resume()` — Sets `if_exists = "append"`
- `_ensure_engine_and_metadata_initialized()` — Invariant: engine and metadata always set together

#### Dependencies
- `sqlalchemy`: `Column`, `Table`, `MetaData`, `create_engine`, `insert`, type columns
- `elspeth.contracts`: `ArtifactDescriptor`, `CallStatus`, `CallType`, `PluginSchema`
- `elspeth.contracts.plugin_context`: `PluginContext`
- `elspeth.contracts.url`: `SanitizedDatabaseUrl`
- `elspeth.core.canonical`: `canonical_json`
- `elspeth.plugins.base`: `BaseSink`

#### Trust Boundary Handling
Correct at the pipeline data level. No coercion of incoming rows. The `_serialize_any_typed_fields()` method converts Python dicts/lists to JSON strings — this is necessary serialization (Python objects cannot go directly into SQL TEXT columns), not type coercion in the ELSPETH sense. Canonical JSON hashing before insert is architecturally sound: it records what ELSPETH intended to write, not what the database ultimately stored.

The `SanitizedDatabaseUrl` usage is correct: raw URL is used for the actual connection, sanitized (credentials-stripped) URL goes to the audit trail.

#### Error Handling
- CREATE TABLE and DROP TABLE are both wrapped in `try/except` that records the error via `ctx.record_call` before re-raising
- INSERT is wrapped in `try/except` that records the error via `ctx.record_call` before re-raising
- Extra fields (keys in row not in table schema) raise `ValueError` before INSERT — prevents SQLAlchemy's silent column dropping behavior
- `_ensure_engine_and_metadata_initialized()` guards against `None` state with `RuntimeError` (correct: this is a framework bug, not user data error)

#### Concerns
1. **MODERATE — `_serialize_any_typed_fields` uses `isinstance(value, (dict, list))`**: This is Tier 1 system-owned data (pipeline rows) being checked defensively. Per CLAUDE.md, transforms have a contractual obligation to produce the correct types. An `any`-typed field that contains a `dict` should be expected — it is the declared contract for that field type. The serialization itself is necessary (SQL cannot store Python dicts), but the use of `isinstance` on pipeline data to branch behavior is a form of defensive pattern that may mask upstream transform bugs. If a `float`-typed field somehow contained a `dict`, this code would silently leave it as-is (since it only checks `any`-typed fields), letting SQLAlchemy fail with an opaque error rather than a clear contract violation.
2. **MODERATE — No transaction isolation: each `write()` is auto-committed**: Each `write()` call uses `engine.begin()` which commits immediately on exit. If a run processes 1000 rows in 10 batches of 100, and batch 7 fails, batches 1-6 are permanently committed. There is no rollback capability at the batch level. For `if_exists='replace'`, the DROP TABLE happened at the start, so a mid-run failure leaves the table in a partial state (neither the original data nor the new data). The `flush()` docstring acknowledges "Future enhancement: Hold transaction open between write() and flush()" — but the current state should be explicitly documented in the class docstring as a limitation.
3. **MINOR — `observed` mode serializes ALL field values (not just dict/list) via the wrong code path**: In `_serialize_any_typed_fields()`, when `self._schema_config.is_observed`, `fields_to_check` becomes `set(row.keys())` (all fields). Only `dict` and `list` values are then JSON-serialized. For observed mode, any field could be a dict/list (since no schema declared them), so this is the correct behavior. The logic is sound but the `observed` and `any_typed_fields` paths share a loop body that could be clearer.
4. **MINOR — `SCHEMA_TYPE_TO_SQLALCHEMY` maps `"any"` to `Text`**: When a field is declared `any` in the schema, it becomes a `TEXT` column. The `_serialize_any_typed_fields()` pre-insert serialization handles the dict/list case. However, if an `any`-typed field contains a numpy array or other non-JSON-serializable type, `json.dumps()` will raise at insert time. The error will propagate through `ctx.record_call` and re-raise, so it is recorded. But the error message will be from `json.dumps()` (e.g., "Object of type ndarray is not JSON serializable"), not from ELSPETH's validation layer.
5. **MINOR — `flush()` is a no-op with a comment**: The `flush()` method (lines 521-533) does nothing but has a detailed docstring explaining why. This is correct and well-documented. No concern about the behavior itself, but callers relying on `flush()` for crash safety with the database sink get no additional guarantees beyond auto-commit.

---

## Overall Analysis

### 1. Source Architecture

Sources use a **streaming iterator pattern**: `load()` is a generator that yields `SourceRow` instances one at a time. The orchestrator iterates these. This is correct for memory efficiency with large files.

The architecture is:
1. Open file handle
2. Resolve field names (headers/normalization)
3. Lock schema contract after first valid row
4. Per-row: validate → yield valid or quarantined
5. Close file handle in `finally`

CSVSource and JSONSource both implement the "lock after first valid row" pattern via `ContractBuilder`. This ensures type inference from observed schemas is deterministic and the contract is applied consistently to all subsequent rows.

### 2. Field Normalization

Field normalization is well-architected:
- **Versioned** (`NORMALIZATION_ALGORITHM_VERSION`) — algorithm changes produce auditable diffs
- **Auditable** (`FieldResolution.resolution_mapping`) — original→final mapping stored in Landscape
- **Collision-safe** — all three collision scenarios (normalization, mapping, raw duplicates) are detected with full diagnostic output
- **Defense-in-depth** — `isidentifier()` post-check catches algorithm bugs
- **Immutability concern** (see Concern 1 under `field_normalization.py`) — `list` and `dict` in frozen dataclass are not truly immutable

### 3. Sink Architecture

Sinks use a **batch write pattern**: the orchestrator collects rows and calls `write(batch, ctx)`. Sinks lazily initialize their file handles / database connections on first write.

Write safety varies by sink:
- **CSVSink**: Streams to a persistent file handle. Atomic at the batch level (all rows staged in memory before write). Durable via `flush()` → `os.fsync()`. Not atomic across the entire run (partial writes are possible if the process crashes between batches).
- **JSONSink (JSONL)**: Same pattern as CSVSink — persistent file handle, append per-line. O(N) hash cost per write (regression vs CSVSink's O(batch)).
- **JSONSink (JSON array)**: Fully atomic via temp-file + `os.replace()`. Each `write()` rewrites the entire accumulated set. Memory-intensive (all rows buffered). O(N) hash cost is acceptable since file is always rewritten.
- **DatabaseSink**: Auto-commit per batch. No batch-level atomicity. DDL and DML both instrumented.

### 4. Trust Tier Compliance

**Sources (Tier 3 handling):** Compliant. All three sources use `allow_coercion=True`, quarantine invalid rows rather than crashing, record all validation errors in the audit trail, and handle parse errors as external data failures. The NaN/Infinity rejection in `json_source.py` directly addresses the known P0 for float validation at the boundary.

**Sinks (Tier 2 handling):** Compliant. All three sinks use `allow_coercion=False`. Sinks do not attempt to coerce incoming data. Wrong types would crash (per policy) rather than being silently fixed.

### 5. Known Issue Status

| Issue | Status in Current Code |
|-------|------------------------|
| JSON sink data loss (truncate-then-write) | **RESOLVED** — `_write_json_array()` now uses atomic temp-file + `os.replace()` pattern |
| NaN/Infinity accepted in float validation | **RESOLVED at source boundary** — `_reject_nonfinite_constant` hook rejects at parse time. Status at transform/sink level not covered by this analysis. |

### 6. Cross-Cutting Patterns

**Shared patterns (good):**
- `allow_coercion=True/False` consistently set in all sources/sinks
- `ContractBuilder` for infer-and-lock schema contracts
- `SourceRow.valid()` / `SourceRow.quarantined()` for typed row states
- `ArtifactDescriptor` for typed audit output from sinks
- `ctx.record_validation_error()` and `ctx.record_call()` for audit trail recording
- `on_start()` / `on_complete()` lifecycle hooks (all currently no-op but present)
- `flush()` + `os.fsync()` for crash safety (CSV and JSONL)

**DRY violations (bad):**
- `_resolve_contract_from_context_if_needed()` — duplicated verbatim between `csv_sink.py` and `json_sink.py`
- `_resolve_display_headers_if_needed()` — duplicated verbatim between `csv_sink.py` and `json_sink.py`
- `_get_effective_display_headers()` — duplicated verbatim between `csv_sink.py` and `json_sink.py`
- `set_resume_field_resolution()` — duplicated verbatim between `csv_sink.py` and `json_sink.py`

**Divergence (worth documenting):**
- CSVSink uses **incremental hashing** (O(batch) per write); JSONSink uses **full-file hashing** (O(total) per write). This is a performance regression in JSONSink that should be aligned.
- CSVSource defers contract creation to `load()` (needs field resolution); JSONSource partially initializes in `__init__()` (FIXED schemas locked early). Both are correct but conceptually divergent.

---

## Concerns and Recommendations (Ranked by Severity)

### P1 — High (Fix Before RC3.3)

**P1-1: DRY violation in sink display header logic (4 methods × 2 sinks)**
- **Files:** `csv_sink.py` lines 507-596, `json_sink.py` lines 476-546
- **Issue:** Four methods are verbatim duplicates. A bug fix in one must be manually applied to the other. This has already created one known divergence (the incremental vs full-file hash difference that could indicate copy-paste divergence).
- **Recommendation:** Extract `DisplayHeaderMixin` with the four shared methods and apply to both sinks. Alternatively, move them to `BaseSink` if all sinks will eventually support display headers.

**P1-2: JSONL sink full-file hash on every write (O(N) per batch)**
- **File:** `json_sink.py` lines 373-379 (`_compute_file_hash`)
- **Issue:** For JSONL format, every `write()` call scans the entire file from byte 0. For a 1 GB output file being written in 1000 batches, the total hash overhead is O(N²/batch_size) — quadratic in file size. CSVSink avoids this with the incremental `_hasher`.
- **Recommendation:** Add an incremental `_hasher: hashlib._Hash` to JSONSink for JSONL mode, seeded with existing file content on append-mode open (same as CSVSink `_open_file`).

**P1-3: JSONL sink missing `newline=""` on file open (Windows portability)**
- **File:** `json_sink.py` line 332
- **Issue:** `open(self._path, file_mode, encoding=self._encoding)` without `newline=""`. On Windows, `\n` becomes `\r\n`. A JSONL file written on Windows and read on POSIX (or vice versa) may have line-ending issues that break `json.loads()` per-line parsing.
- **Recommendation:** Add `newline=""` to all `open()` calls in JSONL write paths, matching CSVSink's pattern.

### P2 — Medium (Address in RC3.3 or immediately after)

**P2-1: `FieldResolution` mutable fields in frozen dataclass**
- **File:** `field_normalization.py` lines 184-212
- **Issue:** `final_headers: list[str]` and `resolution_mapping: dict[str, str]` are mutable despite `frozen=True`. Callers can mutate the audit trail mapping data.
- **Recommendation:** Change `final_headers` to `tuple[str, ...]` and wrap `resolution_mapping` in `types.MappingProxyType`. Update `CSVSource` where these are accessed (only reads, so no behavior change needed).

**P2-2: JSONSink `_rows` memory accumulation for JSON array format**
- **File:** `json_sink.py` line 247, 287
- **Issue:** All rows written to a JSON array sink are buffered in `self._rows` for the life of the run. No limit. Inherent to the format but undocumented.
- **Recommendation:** Add a note to the class docstring warning that JSON array format buffers all output rows in memory. Consider raising a `ValueError` if the run exceeds a configurable `max_rows_in_memory` threshold.

**P2-3: DatabaseSink no batch-level transaction isolation**
- **File:** `database_sink.py` lines 476-511
- **Issue:** Each `write()` auto-commits. A mid-run crash leaves partially committed data. Combined with `if_exists='replace'`, this can destroy existing data and leave a partial replacement.
- **Recommendation:** Document this limitation explicitly in the class docstring. For `if_exists='replace'`, consider staging to a temp table and renaming atomically after all batches succeed (more complex but correct). At minimum, document that database sink does not support atomic run-level rollback.

**P2-4: JSONSource late imports in `__init__`**
- **File:** `json_source.py` lines 130-131
- **Issue:** `ContractBuilder` and `create_contract_from_config` are imported inside `__init__()` rather than at module level. Inconsistent with all other files.
- **Recommendation:** Move to module-level imports.

**P2-5: `NullSource` defensive schema injection**
- **File:** `null_source.py` lines 67-70
- **Issue:** `if "schema" not in config_copy: config_copy["schema"] = {"mode": "observed"}` is defensive programming on system-owned config. If `BaseSource` requires a schema key, that requirement should be enforced at the config loading layer, not silently corrected inside the plugin.
- **Recommendation:** Either (a) make `BaseSource.__init__` handle the schema-required-for-protocol issue, or (b) have the caller (resume path in `cli.py`) always provide a schema key for NullSource. Remove the in-plugin default injection.

### P3 — Low (Quality improvements)

**P3-1: CSVSink incremental hash reads without `os.fsync` before read**
- **File:** `csv_sink.py` lines 281-294
- **Issue:** `file.flush()` is called but `os.fsync()` is not before the incremental hash read. Theoretically the OS could return stale data. Practically safe on POSIX.
- **Recommendation:** Add `os.fsync(self._file.fileno())` between `file.flush()` and the hash read in `write()`, or add a comment documenting why `flush()` is sufficient.

**P3-2: CSV sink `_display_headers_resolved` early-set pattern needs comment**
- **File:** `csv_sink.py` lines 571-573, `json_sink.py` lines 521-523
- **Issue:** Flag is set `True` before the resolution attempt to prevent re-entry, but if `ValueError` is raised by the Landscape call, the flag remains `True`. Correct behavior (the ValueError propagates), but confusing pattern.
- **Recommendation:** Add an inline comment explaining the early-set is safe because the `ValueError` aborts the write path.

**P3-3: CSVSource blank-line skip with no audit record**
- **File:** `csv_source.py` line 365-366
- **Issue:** `if not values: continue` silently skips blank lines with no audit trail entry. The audit trail will not show that blank lines existed.
- **Recommendation:** Add a `ctx.record_validation_error()` call (or a dedicated `ctx.record_info()` if that exists) for blank lines, or document that blank lines are intentionally unaudited as they are non-content.

**P3-4: JSONSource `_first_valid_row_processed` not initialized in `__init__`**
- **File:** `json_source.py` line 165
- **Issue:** Attribute initialized in `load()`, not `__init__()`. Would cause `AttributeError` if `_validate_and_yield()` were called before `load()`.
- **Recommendation:** Initialize `self._first_valid_row_processed = False` in `__init__()`.

**P3-5: `zip(headers, values, strict=False)` missing explanatory comment**
- **File:** `csv_source.py` line 398
- **Issue:** `strict=False` is intentional (column count already validated), but a reader may flag it.
- **Recommendation:** Add inline comment: `# strict=False: column count already validated at line 374`.

---

## Confidence

**High.** All 7 files were read in full. Analysis is based on direct code examination. The trust tier compliance, error handling patterns, and architectural concerns are grounded in specific line numbers and code constructs. The "JSON sink P0 resolved" finding is directly verifiable from `_write_json_array()` implementation at lines 338-371 of `json_sink.py`.
