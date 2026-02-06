# Analysis: src/elspeth/contracts/sink.py

**Lines:** 85
**Role:** Defines `OutputValidationResult`, a frozen dataclass used by sinks to report whether an existing output target (CSV file, database table, etc.) is compatible with the configured schema. Used for append/resume operations to detect schema drift before writing data.
**Key dependencies:**
- Imports: `dataclasses` (stdlib only -- no project dependencies)
- Imported by: `plugins/base.py` (BaseSink default), `plugins/protocols.py` (SinkProtocol), `plugins/sinks/csv_sink.py`, `plugins/sinks/json_sink.py`, `plugins/sinks/database_sink.py`, `contracts/__init__.py`
**Analysis depth:** FULL

## Summary

This is a clean, well-designed value object with no external dependencies. The frozen dataclass pattern is appropriate for an immutable validation result. Factory methods (`success()` and `failure()`) provide clean construction. No critical findings. Two minor observations about API design. This file is among the soundest in the contracts package.

## Critical Findings

None.

## Warnings

None.

## Observations

### [39-51] `success()` factory does not populate `schema_fields`

**What:** The `success()` factory method accepts `target_fields` but does not accept or populate `schema_fields`. This means a successful validation result can tell you what fields exist in the target, but not what fields were expected by the schema.

**Why it matters:** Very low severity. For successful validation, the schema_fields are implicitly "compatible" so they are not strictly needed. However, for diagnostic logging or audit purposes, having both `target_fields` and `schema_fields` on successful results could be useful for confirming what was validated. Callers can always construct the dataclass directly if they need all fields populated.

### [31-35] Default factory for tuples uses `tuple` not `lambda: ()`

**What:** The `default_factory=tuple` pattern creates an empty tuple via `tuple()`. This is idiomatic and correct. It avoids the mutable default argument pitfall (not that tuples are mutable, but the pattern is consistent).

**Why it matters:** No concern. This is a correct pattern noted for completeness.

### [77-85] `failure()` factory converts `None` lists to empty tuples via conditional expression

**What:** Each list parameter is converted with `tuple(x) if x else ()`. This means both `None` and empty lists `[]` produce `()`. While functionally correct, this means a caller cannot distinguish "no information about missing fields" from "explicitly zero missing fields."

**Why it matters:** Very low severity. In practice, callers construct failures with explicit field lists (e.g., `missing_fields=["col_a"]`) when they have diagnostic info, and omit them when they do not. The distinction between "unknown" and "empty" is not needed by current consumers.

### [10] Frozen dataclass is the correct choice

**What:** The dataclass is `frozen=True`, making instances immutable after creation. This is appropriate for a validation result that should not be modified after construction.

**Why it matters:** Positive observation. This aligns with the codebase's pattern of using frozen dataclasses for value objects and prevents accidental mutation of validation results between creation and consumption.

### No `__eq__` or `__hash__` considerations

**What:** Frozen dataclasses auto-generate `__eq__` and `__hash__` based on all fields. The default tuple fields use `compare=True` and `hash=True` (the defaults). This means two `OutputValidationResult` instances with the same field values are equal and hashable.

**Why it matters:** This is correct behavior. Validation results are value objects and should compare by value.

## Verdict

**Status:** SOUND
**Recommended action:** No changes needed. This file is clean, minimal, and well-tested through its consumers (csv_sink, json_sink, database_sink all extensively use both factory methods). The one potential enhancement (accepting `schema_fields` in `success()`) is a nice-to-have, not a need.
**Confidence:** HIGH -- the file has zero external dependencies, simple logic, and is thoroughly exercised by sink tests.
