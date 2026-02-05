# Analysis: src/elspeth/core/landscape/row_data.py

**Lines:** 61
**Role:** Provides a discriminated union type (`RowDataResult`) for row data retrieval, replacing ambiguous `dict | None` returns with explicit state handling. Five states distinguish between data available, purged, never stored, store not configured, and row not found.
**Key dependencies:** Standard library only (`dataclasses`, `enum`, `typing`). Imported by `elspeth.core.landscape.recorder` (returns `RowDataResult` from `get_row_data()`) and re-exported from `elspeth.core.landscape.__init__`.
**Analysis depth:** FULL

## Summary

This is a well-designed, minimal module that solves a real problem (ambiguous None returns). The discriminated union pattern with `__post_init__` invariant enforcement is correct and robust. The frozen dataclass prevents mutation after construction. No critical issues found. This is one of the soundest files in the analysis set.

## Observations

### [56-60] Invariant enforcement is correct and complete

The `__post_init__` validates both directions of the state/data invariant:
- AVAILABLE requires non-None data
- All other states require None data

This is correctly implemented and prevents construction of invalid states. The frozen dataclass ensures the invariant can't be violated after construction.

### [54] data field type annotation allows broad dict

The `data` field is typed as `dict[str, Any] | None`. This is appropriate for the module's role as a transport container -- it doesn't know what fields the row contains. The actual type validation happens at the source plugin level (Tier 3 boundary).

### [21-31] RowDataState enum covers all retrieval outcomes

The five states provide complete coverage of row data retrieval scenarios:
1. `AVAILABLE` -- happy path
2. `PURGED` -- retention policy deleted the payload
3. `NEVER_STORED` -- source_data_ref was never set (e.g., NullSource)
4. `STORE_NOT_CONFIGURED` -- no PayloadStore available
5. `ROW_NOT_FOUND` -- row_id doesn't exist

This eliminates the guesswork that would be required with a plain `None` return. Callers can use structural pattern matching for exhaustive handling.

### [34] frozen=True is correct for immutable result type

A retrieval result should be immutable once constructed. The frozen dataclass enforces this at the Python level, preventing accidental mutation by callers.

### Potential enhancement: Missing `__repr__` or `__str__` override

The default dataclass `__repr__` will include the full `data` dict, which could be large. For logging/debugging, a truncated representation might be useful. This is very minor and doesn't affect correctness.

## Verdict

**Status:** SOUND
**Recommended action:** No changes needed. This module is well-designed, minimal, and correct.
**Confidence:** HIGH -- The module is 61 lines with a single clear purpose, complete invariant enforcement, and no external I/O or complex logic.
