# Analysis: src/elspeth/plugins/transforms/batch_stats.py

**Lines:** 208
**Role:** Batch-aware aggregation transform that computes statistical summaries (count, sum, mean) over batches of rows. Receives buffered rows when an aggregation trigger fires and emits a single summary row per batch.
**Key dependencies:** BaseTransform, TransformDataConfig, SchemaConfig, SchemaContract, FieldContract, PipelineRow, TransformResult, create_schema_from_config
**Analysis depth:** FULL

## Summary

BatchStats is structurally sound with correct trust model enforcement for type violations. However, there are two significant issues: (1) floating-point overflow/precision in the `sum()` call that can silently produce `inf` or lose precision on large batches, and (2) the `group_by` logic takes the value from only the first row, which is misleading if the batch contains mixed groups. The `_on_error` field is stored but never used, matching the same pattern as batch_replicate.

## Critical Findings

### [162] sum() on float values can silently produce inf -- bypasses RFC 8785 canonicalization

**What:** `total = sum(values)` where `values` is `list[float]` can produce `float('inf')` on sufficiently large batches of large values. The `FiniteFloat` constraint at the source only rejects NaN/Infinity in the INPUT; it does not prevent arithmetic within transforms from producing Infinity as an intermediate result.

**Why it matters:** If `total` is `float('inf')`, it will propagate into the result dict as `"sum": inf`. When the engine attempts to canonicalize this for the audit trail hash (via `rfc8785`), it will crash because RFC 8785 rejects NaN and Infinity. The pipeline fails with a cryptic canonicalization error deep in the audit system, far from the actual cause. This will only manifest with specific data distributions (many large positive floats) making it a latent production issue.

**Evidence:**
```python
values.append(float(raw_value))
# ...
total = sum(values) if values else 0
# ...
result["sum"] = total  # Could be inf
```
The source validates that individual values are finite, but no check is performed on the aggregate. Similarly, `mean = total / count` will be `inf` if `total` is `inf`.

### [175-177] group_by value taken from first row only -- misleading for mixed batches

**What:** When `group_by` is configured, the code takes the group value from `rows[0]` only:
```python
if self._group_by and rows and self._group_by in rows[0]:
    result[self._group_by] = rows[0][self._group_by]
```

**Why it matters:** Aggregation triggers are count-based or time-based, not group-based. A batch of 100 rows triggered by `count: 100` may contain rows from multiple groups (e.g., categories "A", "B", "C"). The summary will report the group as whatever was in row 0 (e.g., "A"), but the sum/count/mean are computed across ALL groups. The audit trail records that "category A had sum=X" when actually X includes categories B and C. This is silent data corruption in the audit trail -- the exact scenario CLAUDE.md warns about.

**Evidence:** The docstring says `group_by: Optional. Field to include in output for context` -- the word "context" suggests it's informational. But in practice, any consumer of this data will interpret the group_by field as identifying what was aggregated, creating false audit attributions.

## Warnings

### [159] float() conversion of int values loses precision for large integers

**What:** `values.append(float(raw_value))` converts all values to float, including integers.

**Why it matters:** Python integers have arbitrary precision, but float64 has 53 bits of mantissa. Integer values above 2^53 (9,007,199,254,740,992) will lose precision when converted to float. For financial or ID-based aggregation, this could produce wrong sums. The sum of `[9007199254740993, 1]` as floats gives `9007199254740994.0` instead of the correct `9007199254740994`.

### [116-141] Empty batch handling returns result with `mean: None`

**What:** Empty batch returns `{"count": 0, "sum": 0, "mean": None, "batch_empty": True}`.

**Why it matters:** The output schema has `mean` typed as `object` in the contract, but the value is `None`. Downstream transforms or sinks that expect numeric `mean` will get `None`. This is documented as "should not happen in normal operation" but if it does occur, the None value may cause TypeErrors in downstream arithmetic. Additionally, the `batch_size` field is missing from the empty batch result (present in non-empty results at line 168), creating schema inconsistency.

### [79] _on_error stored but never used

**What:** `self._on_error = cfg.on_error` is stored from TransformDataConfig but never referenced.

**Why it matters:** The transform raises TypeError/KeyError for upstream bugs (correct per trust model) but has no error path for row-level failures. If in the future someone expects on_error to work (because it is configurable), it silently does nothing.

### [192] python_type=object for all fields loses type fidelity

**What:** Same issue as batch_replicate -- all output contract fields use `python_type=object`.

**Why it matters:** The output has well-known types: `count` is always `int`, `sum` is always `float`, `mean` is `float | None`. These could be declared with actual types for better audit trail quality. Using `object` means contract validation at downstream nodes is effectively disabled for these fields.

## Observations

### [146-157] Correct Tier 2 enforcement for type violations

The isinstance check for numeric types and the direct `row[self._value_field]` access (which will raise KeyError if missing) correctly follow the trust model. Wrong types or missing fields in Tier 2 data are upstream bugs and should crash.

### [167] batch_size vs count distinction

The code distinguishes `count` (number of values) from `batch_size` (total rows). In the current implementation these are always equal since every row must have the value_field (KeyError if missing). This distinction would only matter if the code were changed to skip rows with missing values rather than crashing.

### [186-198] Contract creation pattern is clean

The OBSERVED contract creation from result keys is consistent with the pattern used in batch_replicate and follows the schema_contract module's conventions.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Add overflow protection for `sum()` -- check if `total` is finite after computation. (2) Re-evaluate the `group_by` design: either validate that all rows in the batch have the same group_by value, or include a list of distinct group values, or remove the feature. The current behavior produces misleading audit data. (3) Add `batch_size` to the empty-batch result for schema consistency.
**Confidence:** HIGH -- The group_by issue is a clear audit integrity concern. The overflow issue is mathematically provable for specific inputs.
