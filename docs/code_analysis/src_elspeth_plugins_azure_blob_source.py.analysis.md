# Analysis: src/elspeth/plugins/azure/blob_source.py

**Lines:** 735
**Role:** Azure Blob Storage source plugin -- downloads blobs (CSV, JSON, JSONL) from Azure containers and feeds them into the pipeline as validated/quarantined rows. This is a Tier 3 trust boundary: blob content is external data with zero trust.
**Key dependencies:** Imports `AzureAuthConfig` (auth.py), `BaseSource` (base.py), `DataPluginConfig` (config_base.py), `PluginContext` (context.py), `PluginSchema`/`SourceRow`/`CallStatus`/`CallType` (contracts), `create_schema_from_config` (schema_factory.py), `FieldResolution`/`resolve_field_names` (field_normalization.py), `ContractBuilder`/`create_contract_from_config` (contracts). Imported by engine orchestrator (core.py) and test_blob_source.py.
**Analysis depth:** FULL

## Summary
This file is well-structured and generally follows the Three-Tier Trust Model correctly. The biggest concern is that the entire blob is loaded into memory with `readall()`, creating an unbounded memory allocation risk in production with large blobs. There are also asymmetric error-handling patterns between JSON and CSV formats (JSON parse failures crash the pipeline while JSONL parse failures quarantine gracefully), and a re-raise pattern on line 441 that can mangle Azure SDK exception types. Overall the file is sound in its audit trail integration and schema validation, but needs attention on the memory and error-handling fronts.

## Critical Findings

### [403] Unbounded memory allocation via readall()
**What:** `blob_client.download_blob().readall()` loads the entire blob into memory as a single `bytes` object. There is no size limit, streaming, or chunking.
**Why it matters:** In production, an Azure blob can be arbitrarily large (up to 190.7 TiB for block blobs). A misconfigured `blob_path` pointing at a multi-gigabyte file, or a malicious actor uploading a large blob, will cause the process to exhaust memory and be OOM-killed. For an emergency dispatch system, this is a denial-of-service vector against the entire pipeline.
**Evidence:**
```python
blob_data = blob_client.download_blob().readall()
```
No preceding size check (e.g., `blob_client.get_blob_properties().size`) and no streaming reader. The Azure SDK's `download_blob()` supports chunked reads via `readinto()` or iteration, but none of those are used. The `pd.read_csv` call on line 499 could also accept a stream directly rather than requiring the full blob in memory.

### [441] Exception re-raise pattern may mangle Azure SDK exception constructors
**What:** The error re-raise on line 441 uses `type(e)(f"Failed to download blob...") from e`, which calls the constructor of the original exception class with a single string argument.
**Why it matters:** Azure SDK exceptions (e.g., `ResourceNotFoundError`, `ClientAuthenticationError`, `HttpResponseError`) have complex constructors that accept `message` and other keyword arguments. Calling `type(e)(string)` may not produce a valid exception of the same type -- it could raise a `TypeError` during the re-raise itself, hiding the original Azure error. This would manifest as an inscrutable `TypeError` in production logs instead of the actual blob download failure.
**Evidence:**
```python
raise type(e)(f"Failed to download blob '{self._blob_path}' from container '{self._container}': {e}") from e
```
Azure's `HttpResponseError.__init__` signature is `__init__(self, message=None, response=None, **kwargs)`. While passing a single string works for that particular class, `ResourceExistsError` and others have varying constructor signatures. A safer pattern would be `raise RuntimeError(f"Failed to download blob...") from e` or wrapping in a known exception type.

## Warnings

### [574-607] Asymmetric error handling between JSON array and JSONL formats
**What:** `_load_json_array()` raises `ValueError` on invalid JSON (line 598) and on non-array top-level types (line 607), crashing the pipeline. In contrast, `_load_jsonl()` quarantines individual malformed lines gracefully (lines 647-666). CSV also has a quarantine path for catastrophic parse failures (lines 508-527).
**Why it matters:** A malformed JSON blob (e.g., truncated download, encoding issue partway through) will crash the entire pipeline instead of being quarantined. This is inconsistent with the quarantine-on-external-data-failure principle that CSV and JSONL correctly implement. For an emergency dispatch system, one malformed blob should not halt all processing.
**Evidence:**
```python
# JSON array - crashes
except json.JSONDecodeError as e:
    raise ValueError(f"Invalid JSON in blob: {e}") from e
```
vs.
```python
# JSONL - quarantines
except json.JSONDecodeError as e:
    raw_row = {"__raw_line__": line, "__line_number__": line_num}
    error_msg = f"JSON parse error at line {line_num}: {e}"
    ctx.record_validation_error(...)
    if self._on_validation_failure != "discard":
        yield SourceRow.quarantined(...)
    continue
```

### [397] Instance variable `_first_valid_row_processed` set outside __init__
**What:** `self._first_valid_row_processed = False` is set at the top of `load()` rather than in `__init__()`. This means accessing it before `load()` is called would raise `AttributeError`.
**Why it matters:** While the current flow always calls `load()` before anything accesses this attribute, this is fragile. If the source is used in a different lifecycle (e.g., dry-run validation, schema introspection), the missing attribute could cause a confusing error. Per the codebase's "no defensive programming" policy, attributes should be properly initialized in `__init__`.
**Evidence:**
```python
def load(self, ctx: PluginContext) -> Iterator[SourceRow]:
    # Track first valid row for OBSERVED mode type inference
    self._first_valid_row_processed = False
```
This should be `self._first_valid_row_processed = False` in `__init__` with a re-assignment in `load()`.

### [170-188] AzureAuthConfig is constructed twice during validation
**What:** `validate_auth_config()` creates an `AzureAuthConfig` instance to validate auth fields, but discards it. Then `get_auth_config()` creates another one during `__init__`. This means the full auth validation logic runs twice with identical inputs.
**Why it matters:** Minor performance waste and potential for divergence if the two construction sites ever get different arguments. More importantly, this creates a maintenance hazard: someone could add a field to `get_auth_config()` but forget to add it to `validate_auth_config()`, causing validation to pass but runtime to use different parameters.
**Evidence:**
```python
# First construction (validate_auth_config, line 179)
AzureAuthConfig(
    connection_string=self.connection_string,
    sas_token=self.sas_token,
    ...
)

# Second construction (get_auth_config, line 224)
return AzureAuthConfig(
    connection_string=self.connection_string,
    sas_token=self.sas_token,
    ...
)
```

### [506] CSV on_bad_lines="warn" silently drops malformed rows
**What:** `pd.read_csv(..., on_bad_lines="warn")` will skip rows with incorrect column counts and print a warning to stderr, but the skipped rows are not quarantined or recorded in the audit trail.
**Why it matters:** For an auditable pipeline, every row must have a terminal state. Rows silently dropped by pandas have no audit trail entry -- they vanish without a trace. The audit trail will show N rows processed, but the blob might have had N+M rows. This violates the "no silent drops" principle.
**Evidence:**
```python
df = pd.read_csv(
    io.StringIO(text_data),
    ...
    on_bad_lines="warn",  # Warn but skip bad lines instead of crashing
)
```
There is no mechanism to capture which lines were skipped by pandas, no quarantine SourceRow for those lines, and no audit record of the data loss.

## Observations

### [355] Incomplete Phase 1 comment
**What:** Line 355 has the comment `# PHASE 1: Validate self-consistency` but there is no code after it in `__init__`. The comment appears to be a leftover placeholder.
**Why it matters:** Dead comments reduce readability and imply unfinished work.

### [570-572] DataFrame iteration allocates N dicts
**What:** `df.to_dict(orient="records")` materializes all rows as a list of dicts at once, then iterates through them. Combined with the full blob already in memory, this means the data exists in memory three times: raw bytes, DataFrame, and list of dicts.
**Why it matters:** For a 500MB CSV, this could mean 1.5GB+ peak memory usage. Not critical for typical use but compounds the `readall()` concern.

### [338-350] Conditional contract creation is fragile
**What:** The contract builder initialization has three paths (CSV deferred, JSON/JSONL locked, JSON/JSONL observed) with `None` sentinel values to track state across methods. The `_contract_builder` field is `None` for two different reasons (locked contract vs. CSV deferred), creating an ambiguous state.
**Why it matters:** Future changes to contract initialization could easily introduce bugs by misunderstanding which `None` state they're in. A dedicated enum or state class would be clearer.

### Config duplication with CSVSource
**What:** `AzureBlobSourceConfig` duplicates many fields and validators from `TabularSourceDataConfig` (the base class used by CSVSource/JSONSource), including `normalize_fields`, `columns`, `field_mapping`, `on_validation_failure`, and their validators.
**Why it matters:** The blob source cannot inherit from `TabularSourceDataConfig` because it extends `PathConfig` (local file path). This means any changes to field normalization validation must be replicated in two places. Consider extracting a mixin or shared validator.

## Verdict
**Status:** NEEDS_ATTENTION
**Recommended action:** Address the unbounded memory allocation (critical for production safety), fix the exception re-raise pattern to avoid constructor mismatches, and make JSON array error handling consistent with JSONL/CSV quarantine patterns. The `on_bad_lines="warn"` audit gap should also be resolved -- either use `on_bad_lines="error"` with a try/except quarantine wrapper, or capture skipped lines via a custom bad_line handler.
**Confidence:** HIGH -- All findings are based on direct code reading with clear reproduction paths. The memory concern is straightforward Azure SDK behavior. The exception constructor issue is documented in Azure SDK source.
