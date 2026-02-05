# Analysis: src/elspeth/engine/orchestrator/export.py

**Lines:** 346
**Role:** Post-run export orchestration and schema reconstruction. Handles exporting the Landscape audit trail to JSON or CSV format after run completion. Also contains `reconstruct_schema_from_json` for restoring Pydantic schemas during pipeline resume from checkpoint.
**Key dependencies:** Imports `PluginContext` (runtime), `LandscapeExporter` and `CSVFormatter` (deferred), `create_model` and `PluginSchema` from Pydantic/contracts (deferred). Called by `orchestrator.core.Orchestrator` during the EXPORT phase and by resume logic.
**Analysis depth:** FULL

## Summary

The module has two distinct responsibilities: audit export and schema reconstruction. The export functionality has a few concerns around resource cleanup and path handling. The schema reconstruction logic is thorough and correctly handles the major Pydantic JSON schema patterns. One notable issue is the `PluginContext` construction with `landscape=None` during export, which could cause problems if sinks try to record audit data. Overall the module is well-structured with clear error handling.

## Warnings

### [84] PluginContext constructed with landscape=None during export

**What:** The export function creates a `PluginContext(run_id=run_id, config={}, landscape=None)` for sink operations. If the export sink's `write()`, `flush()`, or `close()` methods attempt to record anything to the Landscape (via `ctx.landscape`), they will silently skip recording (since `PluginContext.record_call` returns `None` when landscape is None) or log warnings.

**Why it matters:** Export is itself an auditable operation (the orchestrator records EXPORT phase status). If the export sink makes external calls (e.g., writing to Azure Blob, calling an API), those calls will not be recorded in the audit trail. For a system where "if it's not recorded, it didn't happen," this is a gap. The sink's `write()` call is expected to return an `ArtifactDescriptor` (line 105), but the descriptor is captured into `_artifact_descriptor` with a leading underscore and a "future use" comment, suggesting it is currently unused.

**Evidence:**
```python
ctx = PluginContext(run_id=run_id, config={}, landscape=None)
```

### [100-107] JSON export: sink.flush() and sink.close() called even when no records exist

**What:** When `export_config.format` is not "csv" (i.e., JSON), the code calls `list(exporter.export_run(...))` and only writes if `records` is non-empty. However, `sink.flush()` and `sink.close()` are called unconditionally regardless of whether any records were written or even whether the sink was opened for writing.

**Why it matters:** If the sink has not been opened or initialized (because no `write()` was called), calling `flush()` and `close()` on it may fail or produce empty artifacts. While sinks should handle this gracefully, it is an implicit contract assumption.

**Evidence:**
```python
records = list(exporter.export_run(run_id, sign=export_config.sign))
if records:
    _artifact_descriptor = sink.write(records, ctx)
sink.flush()   # Called even if records was empty
sink.close()   # Called even if records was empty
```

### [100-107] JSON export: no try/finally for sink cleanup

**What:** If `sink.write()` raises an exception, `sink.flush()` and `sink.close()` will never be called. This could leave the sink in an open state with leaked file handles or database connections.

**Why it matters:** Resource leak on export failure. The caller in `orchestrator.core` (line 520-529) catches the export exception and records export failure status, but the sink is not closed. If the same sink object is reused or if the process continues after export failure, the leaked resource could cause issues.

**Evidence:**
```python
# No try/finally wrapping
_artifact_descriptor = sink.write(records, ctx)
sink.flush()
sink.close()
```

### [131-134] CSV export: artifact_path suffix stripping could produce unexpected directory names

**What:** The code strips the file suffix from `artifact_path` to create a directory: `export_dir = Path(artifact_path)` then `export_dir = export_dir.with_suffix("")` if it has a suffix. For a path like `/output/data.csv`, this creates `/output/data/`. For a path with multiple dots like `/output/my.pipeline.csv`, `with_suffix("")` only strips the last suffix, producing `/output/my.pipeline/`.

**Why it matters:** This is a minor naming concern but could be surprising to users. The behavior is correct per Python's `Path.with_suffix()` semantics, but the intent (strip extension to get directory name) may not match expectations for paths with dots in the base name.

**Evidence:**
```python
export_dir = Path(artifact_path)
if export_dir.suffix:
    export_dir = export_dir.with_suffix("")
export_dir.mkdir(parents=True, exist_ok=True)
```

### [147] CSV record_type used directly in filename without sanitization

**What:** The `record_type` value from exported records is used directly to construct the CSV filename: `csv_path = export_dir / f"{record_type}.csv"`. The `record_type` values come from `LandscapeExporter.export_run_grouped()`, which returns hardcoded string keys like "run", "node", "edge", etc. (our data, Tier 1).

**Why it matters:** Since record_type is our data (generated by the exporter from hardcoded strings), path traversal is not a realistic concern here. However, if the exporter were ever changed to include record types derived from user input, this could become a path traversal vector. This is informational only.

**Evidence:**
```python
csv_path = export_dir / f"{record_type}.csv"
```

### [267-290] anyOf pattern matching for Decimal relies on specific Pydantic output format

**What:** The Decimal type detection checks for `{"number", "string"}.issubset(type_strs)` without `"null"`. This correctly matches Pydantic's Decimal representation but would also match other union types that happen to include both number and string (e.g., a hypothetical `int | str` field). Since this is our schema data (reconstructed from our own `model_json_schema()` output), false positives are unlikely but possible if custom validators or complex union types are used.

**Why it matters:** If a custom Pydantic schema emitted a non-Decimal anyOf with both number and string types, it would be incorrectly reconstructed as Decimal. Low probability given the current codebase.

**Evidence:**
```python
type_strs = {item.get("type") for item in any_of_items if "type" in item}
if {"number", "string"}.issubset(type_strs) and "null" not in type_strs:
    return Decimal
```

## Observations

### [165-234] reconstruct_schema_from_json is well-structured

The function correctly handles: empty properties with `additionalProperties=true` (dynamic schemas), required vs optional fields, and delegates to `_json_schema_to_python_type` for type mapping. Error messages are clear and actionable.

### [318-321] Array type loses item type information

`_json_schema_to_python_type` returns bare `list` for array types, losing the items schema. The comment acknowledges this: "For now, return list (Pydantic will validate items at parse time)." This is acceptable for resume purposes where the primary goal is type fidelity for the container, but means `list[int]` would be reconstructed as `list[Any]`.

### [324-326] Object type loses property structure

Similarly, nested object types return bare `dict` rather than reconstructing a nested model. This is a known simplification for the resume use case.

### [86-98] CSV export bypasses sink protocol

The CSV multi-file export writes directly to files instead of going through the sink's `write()` method. This is documented ("CSV export writes files directly, not via sink.write") and is necessary because the sink protocol expects homogeneous batches while CSV export writes multiple file types. However, this means the sink's `ArtifactDescriptor` (content_hash, size_bytes) is not produced for CSV exports, creating an audit gap.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Add try/finally around sink operations in JSON export to ensure cleanup on failure. (2) Consider whether export sinks should receive a landscape-connected PluginContext for full auditability. (3) The array/object type simplification in schema reconstruction should be documented as a known limitation for the resume feature.
**Confidence:** HIGH -- The module is straightforward and the concerns are clearly visible. The schema reconstruction logic is sound for its documented scope.
