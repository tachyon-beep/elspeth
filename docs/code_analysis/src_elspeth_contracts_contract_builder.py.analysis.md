# Analysis: src/elspeth/contracts/contract_builder.py

**Lines:** 100
**Role:** Fluent builder for constructing schema contracts during first-row inference. Manages the "infer-and-lock" lifecycle: takes an initial contract (possibly unlocked), processes the first row to infer field types, and returns a locked contract. Used by source plugins (CSV, JSON, Azure Blob) during data ingestion.
**Key dependencies:** Imports `SchemaContract` from `schema_contract`. Consumed by `plugins/sources/csv_source.py`, `json_source.py`, `azure/blob_source.py`, and test files.
**Analysis depth:** FULL

## Summary

This is a small, focused class with clear responsibilities. The code is well-documented with appropriate docstrings and follows the immutable pattern (creating new SchemaContract instances via `with_field()` and `with_locked()` rather than mutating state). There are no critical issues. The main observation is a subtle edge case in the `normalized_to_original` mapping construction that could produce incorrect behavior when multiple original names map to the same normalized name.

## Critical Findings

None.

## Warnings

### [Line 76] Reverse mapping collision: multiple original names mapping to same normalized name

**What:** The reverse mapping `normalized_to_original = {v: k for k, v in field_resolution.items()}` assumes the normalization is injective (no two original names produce the same normalized name). If two different original names normalize to the same value, the dict comprehension silently keeps only the last one. The line 93 lookup `original_name = normalized_to_original[normalized_name]` would then use the wrong original name.

**Why it matters:** If two CSV columns like `"Customer ID"` and `"customer id"` both normalize to `"customer_id"`, the reverse mapping would only retain one. The `FieldContract` would then record an incorrect `original_name`, which is an audit integrity issue -- the audit trail would attribute a field to the wrong source column.

**Evidence:**
```python
# Line 76: Reverse mapping may lose entries on collision
normalized_to_original = {v: k for k, v in field_resolution.items()}
# If field_resolution = {"Customer ID": "customer_id", "customer id": "customer_id"}
# Then normalized_to_original = {"customer_id": "customer id"} -- first entry lost

# Line 93: Would use the wrong original name
original_name = normalized_to_original[normalized_name]
```

**Mitigation:** The header normalization in source plugins likely prevents this (duplicate detection should catch two headers normalizing to the same name), but this code does not defend against it. If the upstream guarantee fails, the error is silent data corruption in the audit trail rather than a crash.

### [Lines 85-93] Fields already declared are silently skipped without type validation

**What:** When a field name appears in both the existing contract (from config) and the first row, the code skips it at line 87-88 with "Field already declared - skip (type from config takes precedence)". This means if the declared type is `int` but the first row contains a `str` value for that field, the mismatch is silently ignored during contract building.

**Why it matters:** The type mismatch would only be caught later during row validation (via `SchemaContract.validate()`). During the contract building phase, there is no early warning that the source data disagrees with the declared schema. For FLEXIBLE mode schemas with declared fields, this could lead to every row failing validation if the source data consistently has a different type.

**Evidence:**
```python
for normalized_name, value in row.items():
    if normalized_name in declared_names:
        # Field already declared - skip (type from config takes precedence)
        continue  # No type check between declared type and actual value
```

## Observations

### [Lines 33-39] Constructor is simple and clean

The constructor takes a `SchemaContract` and stores it. No unnecessary complexity. The `_contract` prefix indicates private state, and the public `contract` property provides read access.

### [Lines 71-73] Early return for already-locked contracts is correct

The check at line 72 `if self._contract.locked: return self._contract` correctly handles FIXED mode contracts where all fields are declared and the contract is already locked from construction. This prevents double-processing.

### [Lines 92-94] KeyError on missing normalization is intentional

The comment at lines 91-92 explicitly states that `KeyError` from `normalized_to_original[normalized_name]` is intentional per CLAUDE.md: if a field exists in the row but not in the resolution mapping, that's a bug in the source plugin. This is the correct approach per the trust model.

### [Line 94] Delegates type inference to SchemaContract.with_field

The actual type inference is delegated to `SchemaContract.with_field()`, which calls `normalize_type_for_contract(value)`. This means `ValueError` for NaN/Infinity values will propagate up from `process_first_row()`, which is documented in the docstring at line 69.

### Class is mutable despite working with immutable contracts

The `ContractBuilder` class itself is mutable (line 98: `self._contract = updated`), even though the `SchemaContract` instances it works with are immutable. This is the builder pattern -- the builder accumulates state and the final product is immutable. However, `process_first_row` is not idempotent: calling it twice would attempt to add fields again on a locked contract. The lock check at line 72 prevents actual damage on a second call, but the method semantics imply single-use.

### No thread safety

The builder stores mutable state (`self._contract`) and has no locking. If two threads called `process_first_row` concurrently (unlikely in current usage, since source processing is single-threaded), the state could be corrupted. This is acceptable given the current architecture.

## Verdict

**Status:** SOUND
**Recommended action:** Consider adding a debug log or assertion when the reverse mapping in line 76 would produce collisions (len(field_resolution) != len(normalized_to_original)). The type-skip behavior at line 87 is a design choice that could benefit from a debug log noting the declared type vs actual type discrepancy for observability.
**Confidence:** HIGH -- the code is small and straightforward with well-defined semantics. The identified issues are edge cases that depend on upstream behavior.
