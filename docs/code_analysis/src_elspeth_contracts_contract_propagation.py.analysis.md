# Analysis: src/elspeth/contracts/contract_propagation.py

**Lines:** 209
**Role:** Contract propagation through the DAG. Determines how schema contracts evolve as data flows through transforms -- handling field addition (propagate), field removal/renaming (narrow), and merge with output schema declarations.
**Key dependencies:** Imports `FieldContract`, `SchemaContract` from `schema_contract`, `normalize_type_for_contract` from `type_normalization`, `structlog`. Consumed by `engine/executors.py` (propagate_contract), `plugins/transforms/field_mapper.py`, `json_explode.py`, `web_scrape.py` (narrow_contract_to_output), and test files.
**Analysis depth:** FULL

## Summary

The file contains three clean, well-documented functions for contract evolution. The code is structurally sound with one notable design limitation: `propagate_contract` and `narrow_contract_to_output` have ~90% duplicated field inference logic (acknowledged in a TODO at line 98). There is one subtle semantic issue where `propagate_contract` catches only `TypeError` while `narrow_contract_to_output` catches both `TypeError` and `ValueError`, creating inconsistent error handling for the same field inference operation. The `merge_contract_with_output` function has a design behavior worth flagging: it only includes fields from the output schema, silently dropping input-only fields.

## Critical Findings

None.

## Warnings

### [Lines 52-57 vs 112-124] Inconsistent exception handling between propagate and narrow

**What:** `propagate_contract` catches only `TypeError` from `normalize_type_for_contract`, while `narrow_contract_to_output` catches both `TypeError` and `ValueError`. The `normalize_type_for_contract` function raises `ValueError` for NaN/Infinity values and `TypeError` for unsupported types. This means `propagate_contract` will crash with `ValueError` if a new field has a NaN value, while `narrow_contract_to_output` will gracefully skip it.

**Why it matters:** If a transform adds a field with value `float('nan')` (which can happen with LLM usage metadata or numeric computations), `propagate_contract` will raise an unhandled `ValueError`, crashing the pipeline. The same scenario in `narrow_contract_to_output` would just skip the field. Since both functions serve the same purpose (inferring field types for new fields), this inconsistency means the same data can cause a crash or graceful handling depending on which code path is taken.

**Evidence:**
```python
# propagate_contract (line 52-57) - only TypeError
try:
    python_type = normalize_type_for_contract(value)
except TypeError:
    continue

# narrow_contract_to_output (line 112-124) - TypeError AND ValueError
try:
    python_type = normalize_type_for_contract(value)
except (TypeError, ValueError) as e:
    skipped_fields.append(name)
    log.debug(...)
    continue
```

`normalize_type_for_contract` in `type_normalization.py` line 63-64:
```python
if isinstance(value, (float, np.floating)) and (math.isnan(value) or math.isinf(value)):
    raise ValueError(...)  # This would crash propagate_contract!
```

### [Lines 153-209] merge_contract_with_output silently drops input-only fields

**What:** The merge function iterates over `output_schema_contract.fields` only. Fields present in `input_contract` but absent from `output_schema_contract` are silently dropped. This is by design (the output schema defines what the transform guarantees), but there is no warning or logging when input fields are lost.

**Why it matters:** If a transform's output schema accidentally omits a field that existed in the input, the contract will silently narrow. Downstream transforms relying on that field would have no contract-level indication that it should exist. The error would only manifest at runtime when the downstream transform tries to access the field.

**Evidence:**
```python
# Line 176: Only iterates output_schema_contract.fields
for output_field in output_schema_contract.fields:
    # Input-only fields are never reached
```

### [Lines 39-41] propagate_contract returns identity for passthrough but does not verify field consistency

**What:** When `transform_adds_fields=False`, the function returns the input contract unchanged without verifying that the output row's fields match the contract. A transform that claims not to add fields but actually removes or renames fields would have its contract pass through unchanged, creating a mismatch between the contract and actual data.

**Why it matters:** The contract would claim fields exist that have actually been removed. Downstream validation against the contract would either fail unexpectedly or, worse, succeed because the validation only checks fields present in the row (not that all contract fields exist in the row for non-required fields).

**Evidence:**
```python
if not transform_adds_fields:
    # Passthrough - same contract
    return input_contract  # No validation that output_row matches input_contract
```

This is documented behavior (tests at lines 493-537 of the test file explicitly document that type mismatches are not caught at propagation time), but it is a gap in the contract enforcement chain.

## Observations

### [Line 98] Acknowledged code duplication between propagate and narrow

The TODO at line 98 states: "Extract shared field inference logic with propagate_contract() -- 90% overlap". Both functions independently iterate output row fields, check against existing names, call `normalize_type_for_contract`, and build `FieldContract` instances with identical parameters. Extracting a shared `_infer_new_fields` helper would reduce the 209-line file by ~30 lines and, critically, would eliminate the exception handling inconsistency identified in the Warning above.

### [Lines 194-203] Mode ordering uses dict lookup, not enum comparison

The mode ordering in `merge_contract_with_output` uses a plain dict `{"FIXED": 0, "FLEXIBLE": 1, "OBSERVED": 2}` instead of an enum or constant. The same pattern appears in `SchemaContract.merge()` at line 417 of `schema_contract.py`. This is duplicated logic that should ideally be centralized.

### [Line 77] propagate_contract always sets locked=True on new contracts

When new fields are found, the output contract is created with `locked=True` regardless of the input contract's locked state. This is correct behavior (if fields are being inferred from actual data, the contract should be locked) but is not documented as intentional.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Fix the inconsistent exception handling in `propagate_contract` (add `ValueError` to the except clause at line 54). Extract shared field inference logic to eliminate the duplication that caused this inconsistency. Consider adding debug logging to `propagate_contract` to match `narrow_contract_to_output`'s observability.
**Confidence:** HIGH -- the exception handling inconsistency is verifiable from the source of `normalize_type_for_contract` and the two catch blocks.
