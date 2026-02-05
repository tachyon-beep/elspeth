# Analysis: src/elspeth/plugins/sources/json_source.py

**Lines:** 335
**Role:** JSON/JSONL source plugin -- reads JSON array or JSONL files and yields rows into the pipeline. Handles format auto-detection, nested data extraction via `data_key`, schema validation with coercion, quarantine routing, and schema contract lifecycle for observed mode.
**Key dependencies:** `json` (stdlib), `pydantic.ValidationError`, `elspeth.contracts.PluginSchema`, `elspeth.contracts.SourceRow`, `elspeth.contracts.contract_builder.ContractBuilder`, `elspeth.contracts.schema_contract_factory.create_contract_from_config`, `elspeth.plugins.base.BaseSource`, `elspeth.plugins.config_base.SourceDataConfig`, `elspeth.plugins.context.PluginContext`, `elspeth.plugins.schema_factory.create_schema_from_config`. Imported by: `elspeth.plugins.validation`.
**Analysis depth:** FULL

## Summary

JSONSource is a competent source plugin that handles multiple JSON formats, correctly rejects NaN/Infinity at parse time, and properly quarantines malformed external data. However, it has one critical gap: the missing empty-source contract locking that CSVSource implements. It also has a moderate issue where the entire JSON array file is loaded into memory at once, creating a resource exhaustion risk for large files. The code is well-organized but has a few asymmetries with its CSV sibling that should be harmonized.

## Critical Findings

### [125-151 / 287-331] Missing empty-source contract locking for OBSERVED schemas

**What:** When all rows are quarantined or the source file contains an empty array, `_first_valid_row_processed` remains `False` and `_contract_builder` is never finalized. The `load()` method returns without ever locking the contract. Compare with CSVSource lines 278-282 which explicitly handles this case:

```python
# CSVSource (correct):
if not first_valid_row_processed and self._contract_builder is not None:
    self.set_schema_contract(self._contract_builder.contract.with_locked())
```

JSONSource has no equivalent code path.

**Why it matters:** If a JSON source with an observed schema produces zero valid rows (all quarantined, or empty array), the engine's downstream consumers may receive a `None` schema contract from `get_schema_contract()`. Depending on how the engine handles this, it could cause a `NoneType` error when attempting to create `PipelineRow` instances, or it could silently propagate `None` as the contract, breaking the contract chain for audit trail recording. This is a data integrity risk for the audit trail.

**Evidence:**
```python
def load(self, ctx: PluginContext) -> Iterator[SourceRow]:
    # ...
    self._first_valid_row_processed = False
    if self._format == "jsonl":
        yield from self._load_jsonl(ctx)
    else:
        yield from self._load_json_array(ctx)
    # NO empty-source contract locking here!
```

### [193-222] Entire JSON file loaded into memory

**What:** `_load_json_array` reads the entire file into memory with `json.load(f)` on line 198. For JSON array files, this means the complete parsed data structure (potentially millions of rows) is held in memory simultaneously.

**Why it matters:** In production, a JSON source file could be gigabytes in size. Loading the entire file into a Python data structure multiplies memory usage (raw JSON string + parsed Python objects). A 2GB JSON file could consume 6-8GB of memory when fully parsed. This is a resource exhaustion vector, especially in environments with constrained memory (containers, serverless). The JSONL format does not have this issue since it processes line-by-line. However, users may not understand the performance implications of choosing `format: json` vs `format: jsonl`.

**Evidence:**
```python
def _load_json_array(self, ctx: PluginContext) -> Iterator[SourceRow]:
    with open(self._path, encoding=self._encoding) as f:
        data = json.load(f)  # Entire file in memory
```

## Warnings

### [146] `_first_valid_row_processed` is an instance attribute set in `load()`, not `__init__()`

**What:** The `_first_valid_row_processed` flag is set on `self` during `load()` (line 146) but is not initialized in `__init__()`. If `_validate_and_yield` were somehow called before `load()` (e.g., during testing or future refactoring), it would raise `AttributeError`. The CSVSource uses a local variable `first_valid_row_processed` which avoids this issue.

**Why it matters:** This is a latent bug. If `load()` is called multiple times (e.g., during retry after a partial failure), the flag from the previous invocation would carry over. Setting it in `load()` at line 146 resets it for each call, which is correct for the current single-call pattern. But if `_validate_and_yield` were extracted or called independently, the missing initialization in `__init__` would surface.

**Evidence:**
```python
def load(self, ctx: PluginContext) -> Iterator[SourceRow]:
    # ...
    self._first_valid_row_processed = False  # Set here, not in __init__
```

### [287-331] `_validate_and_yield` does not validate that `row` is a dict before `model_validate`

**What:** The `_validate_and_yield` method's type annotation says `row: dict[str, Any]`, but in `_load_json_array`, the items come from iterating over `data` (line 284: `for row in data`). If the JSON array contains non-dict items (e.g., `[1, "hello", null, {"valid": "row"}]`), these are passed directly to `_validate_and_yield`. Pydantic's `model_validate` does reject non-dict input with a `ValidationError`, so these items will be quarantined rather than crashing. However, the type annotation is incorrect (the runtime type could be `int`, `str`, `None`, `list`, etc.) and the quarantine error message will be the Pydantic internal message rather than a user-friendly "expected JSON object, got int".

**Why it matters:** The system handles this correctly due to Pydantic's validation, so this is a robustness observation rather than a bug. However, the type annotation mismatch (`dict[str, Any]` vs actual `Any`) could confuse static analysis tools and future maintainers. A pre-check `if not isinstance(row, dict)` with a clear quarantine message would improve audit trail readability.

**Evidence:**
```python
def _validate_and_yield(self, row: dict[str, Any], ctx: PluginContext) -> Iterator[SourceRow]:
    # row could actually be int, str, None, list from JSON array iteration
    try:
        validated = self._schema_class.model_validate(row)  # Pydantic catches non-dict
```

### [109-123] Contract initialization in `__init__` differs from CSV pattern

**What:** JSON source creates and potentially locks the contract in `__init__()` (lines 113-123), while CSV defers contract creation entirely to `load()`. For FIXED/FLEXIBLE schemas, JSON locks the contract immediately. For OBSERVED schemas, it creates a `ContractBuilder` but does not set a schema contract on `self`. This means that between `__init__()` and `load()`, `get_schema_contract()` returns `None` for observed schemas.

**Why it matters:** If any code between construction and `load()` calls `get_schema_contract()` expecting a non-None value (e.g., DAG validation, plugin introspection), it would get `None`. This is likely safe given the engine's lifecycle, but the asymmetry with CSV source could cause confusion when maintaining both sources.

**Evidence:**
```python
# JSON __init__ - sets contract immediately for FIXED/FLEXIBLE
if initial_contract.locked:
    self.set_schema_contract(initial_contract)
    self._contract_builder = None
else:
    self._contract_builder = ContractBuilder(initial_contract)
    # Contract will be set after processing first valid row in load()
```

### [No line] No field normalization support

**What:** JSONSource inherits from `SourceDataConfig` (not `TabularSourceDataConfig`), so it does not support `normalize_fields`, `field_mapping`, or `columns`. JSON field names are used as-is.

**Why it matters:** This is likely intentional since JSON keys are typically already well-formed identifiers (unlike CSV headers which can have spaces, special characters, etc.). However, if a JSON source has keys like `"Customer Name"` or `"Date-Of-Birth"`, users have no way to normalize them at the source boundary. They would need a downstream transform, which violates the principle that normalization should happen at the trust boundary. This is a feature gap rather than a bug.

## Observations

### [26-42] `_reject_nonfinite_constant` is clean and correct

The function correctly rejects NaN, Infinity, and -Infinity at parse time by hooking into `json.loads`/`json.load` via `parse_constant`. This is the right approach per RFC 8259 compliance and canonical JSON policy.

### [153-191] JSONL parsing is well-implemented

Line-by-line processing with per-line error handling is correct. Each malformed line is quarantined independently without affecting subsequent lines. The empty-line skip is appropriate.

### [230-282] `data_key` extraction with structural validation

The three-stage validation (root must be dict, key must exist, extracted value must be list) is thorough and correctly quarantines at each failure point rather than raising exceptions. This properly implements the Tier 3 trust model.

### [86-89] Format auto-detection is simplistic but adequate

Auto-detecting format from file extension (`.jsonl` -> jsonl, else -> json) is reasonable. Users can override with explicit `format` config.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Add empty-source contract locking after the yield-from calls in `load()`, mirroring CSVSource lines 278-282. This is the highest priority fix. (2) Consider adding a pre-check in `_validate_and_yield` for non-dict items with a clear quarantine message. (3) Document the memory implications of JSON array format in the docstring or config validation.
**Confidence:** HIGH -- Complete file analysis with all control paths traced, dependency contracts verified, and comparison with sibling CSV source completed.
