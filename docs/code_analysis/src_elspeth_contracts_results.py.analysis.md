# Analysis: src/elspeth/contracts/results.py

**Lines:** 572
**Role:** Transform and gate result types -- TransformResult, GateResult, RowResult, SourceRow, ArtifactDescriptor, FailureInfo, ExceptionResult. These are the return types from every plugin execution, carrying success/failure status, output data, and routing decisions. Every row processed through the pipeline flows through these types.
**Key dependencies:**
- Imports from: `contracts.url` (SanitizedDatabaseUrl, SanitizedWebhookUrl), `contracts.schema_contract` (PipelineRow, SchemaContract -- TYPE_CHECKING), `contracts.enums` (RowOutcome), `contracts.errors` (TransformErrorReason, TransformSuccessReason), `contracts.identity` (TokenInfo), `contracts.routing` (RoutingAction), `engine.retry` (MaxRetriesExceeded -- TYPE_CHECKING)
- Imported by: `contracts/__init__.py` (re-exported), `engine/executors.py`, `engine/processor.py`, all transform plugins, gate plugins, sink plugins. This module is the universal result contract for the plugin system.
**Analysis depth:** FULL

## Summary

The result types are well-designed with clear factory methods, proper invariant enforcement via `__post_init__`, and good separation of concerns (plugins set data, executors set audit fields). The file is sound overall. There are two warnings: (1) `TransformResult.__post_init__` validates `success_reason` but not output data presence, creating an invariant gap, and (2) `_extract_dict_from_row` accesses the private `_data` attribute of PipelineRow directly, creating coupling to an internal implementation detail. The stale docstring mentioning non-existent types is a minor housekeeping issue.

## Warnings

### [142-149] __post_init__ validates success_reason but not output data presence

**What:** `TransformResult.__post_init__` enforces that `status="success"` implies `success_reason is not None`. However, it does NOT enforce that success results have output data (`row is not None or rows is not None`). This means it's theoretically possible to construct a `TransformResult(status="success", row=None, rows=None, reason=None, success_reason={"action": "..."})` -- a success result with no data.

**Why it matters:** The factory methods `success()` and `success_multi()` correctly populate `row` or `rows`, so this invariant holds for well-behaved callers. But `TransformResult` is a plain dataclass, not frozen -- direct construction bypasses factories. The executor at `executors.py:375` catches this at runtime with a `has_output_data` check, but that's a remote defense. An invariant this critical (success implies data) should be enforced at construction, consistent with how `success_reason` is enforced.

**Evidence:**
```python
# Line 142-149: Validates success_reason but not output data
def __post_init__(self) -> None:
    if self.status == "success" and self.success_reason is None:
        raise ValueError(...)
    # Missing: no check for success + no output data

# executors.py:375 - Runtime check that should not be necessary
if not result.has_output_data:
    raise RuntimeError(f"Transform '{transform.name}' returned success but has no output data")
```

### [29-42] _extract_dict_from_row accesses PipelineRow._data directly

**What:** The helper function `_extract_dict_from_row` accesses `row._data` (a private attribute with leading underscore) on PipelineRow instances. This same pattern exists in `engine/processor.py:60`.

**Why it matters:** `PipelineRow._data` is a `MappingProxyType`. Accessing it directly bypasses the public API (`to_dict()` or `dict(row._data)`). The function does `dict(row._data)` which is semantically equivalent to `row.to_dict()`, but creates coupling to the internal representation. If `PipelineRow`'s storage ever changes (e.g., if `_data` is renamed or restructured), all direct `_data` accessors break. This violates encapsulation. The `to_dict()` method exists precisely for this purpose and is explicitly preferred per CLAUDE.md.

**Evidence:**
```python
# Line 40-41: Direct private attribute access
if isinstance(row, PR):
    return dict(row._data)

# PipelineRow already provides this via to_dict():
# Line 589-595 of schema_contract.py
def to_dict(self) -> dict[str, Any]:
    return dict(self._data)
```

The function should use `row.to_dict()` instead of `dict(row._data)`.

### [1-9] Docstring mentions non-existent types (AggregationResult, SinkResult)

**What:** The module docstring at lines 1-9 states: "Transform and gate result types -- TransformResult, GateResult, AggregationResult, SinkResult." However, `AggregationResult` and `SinkResult` do not exist in this file or anywhere in the codebase (verified via grep). The comment at line 355-357 explains that `AcceptResult` was deleted during aggregation structural cleanup, but the docstring was not updated.

**Why it matters:** Misleading documentation in a contracts module creates confusion for maintainers trying to understand the result type taxonomy. In a system where every operation outcome must be traceable, phantom type names in the docstring could lead someone to think these types exist elsewhere.

**Evidence:**
```python
# Lines 1-9: Module docstring
"""Operation outcomes and results.
...
- ArtifactDescriptor matches architecture schema...
"""
# AggregationResult and SinkResult mentioned in the purpose line but don't exist
```

## Observations

### [45-62] ExceptionResult correctly wraps worker thread exceptions

**What:** `ExceptionResult` wraps `BaseException` (not `Exception`) for async propagation. This is correct because it needs to handle `KeyboardInterrupt` and `SystemExit` in addition to regular exceptions. The pattern of wrapping exceptions in a container for cross-thread propagation is sound.

### [64-98] FailureInfo properly captures retry context

**What:** `FailureInfo` stores structured error information including retry metadata. The `from_max_retries_exceeded` factory correctly extracts all relevant fields from the `MaxRetriesExceeded` exception. Clean design.

### [382-476] ArtifactDescriptor enforces URL sanitization at the type level

**What:** `for_database()` and `for_webhook()` use `isinstance()` checks to enforce that URLs are pre-sanitized types rather than raw strings. This is a strong security pattern -- it makes accidental credential leakage into the audit trail a type error rather than a logic error. The explicit `isinstance` check here is legitimate per CLAUDE.md (framework boundary protection, not bug hiding).

### [480-572] SourceRow handles non-dict quarantined data

**What:** `SourceRow.row` is typed as `Any` rather than `dict[str, Any]` because quarantined rows from external data may not be dicts (e.g., JSON arrays containing primitives). The `.valid()` factory constrains `row` to `dict[str, Any]`, while `.quarantined()` accepts `Any`. This is a thoughtful design that handles Tier 3 (external data) gracefully without forcing dict shape on invalid data.

### [101-316] TransformResult factory methods properly separate concerns

**What:** The factory methods (`success`, `success_multi`, `error`) correctly set fields according to the result type. The `error()` factory explicitly sets `contract=None` (line 315), preventing error results from carrying stale contracts. The `success_multi()` factory validates non-empty rows (line 274). This is well-designed.

### [319-352] GateResult is simpler but lacks factory methods

**What:** Unlike `TransformResult`, `GateResult` is a plain dataclass without factory methods or `__post_init__` validation. There is no enforcement that `row` is non-None or that `action` is valid. The gate executor creates `GateResult` instances directly (e.g., `executors.py:959`). This is acceptable since gates are simpler (always have exactly one output row and one routing action), but the asymmetry with `TransformResult` is noteworthy.

### [360-379] RowResult carries PipelineRow but type hint allows dict

**What:** `RowResult.final_data` is typed as `dict[str, Any] | PipelineRow`. In practice, most callers pass `token.row_data` (a PipelineRow), while one callsite (processor.py:1010) explicitly calls `.to_dict()`. The union type is accurate but callers must handle both cases. Since `RowResult` appears to be consumed mainly within the processor itself (no external consumers found), this is low risk.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Add output data invariant validation to `TransformResult.__post_init__` to match the pattern already used for `success_reason`. (2) Replace `_extract_dict_from_row`'s direct `_data` access with `row.to_dict()`. (3) Update the module docstring to reflect the actual type inventory. All three are straightforward fixes.
**Confidence:** HIGH -- Full read of the file plus all key consumers (executors.py, processor.py), all dependencies (schema_contract.py, routing.py, errors.py), and the trust model documentation. Findings are concrete and verifiable.
