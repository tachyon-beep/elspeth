# Analysis: src/elspeth/plugins/sources/csv_source.py

**Lines:** 305
**Role:** CSV source plugin -- reads CSV files and yields rows into the pipeline. Handles encoding detection, header parsing, field normalization, schema validation, quarantine routing, and schema contract lifecycle.
**Key dependencies:** `csv` (stdlib), `pydantic.ValidationError`, `elspeth.contracts.PluginSchema`, `elspeth.contracts.SourceRow`, `elspeth.contracts.contract_builder.ContractBuilder`, `elspeth.contracts.schema_contract_factory.create_contract_from_config`, `elspeth.plugins.base.BaseSource`, `elspeth.plugins.config_base.TabularSourceDataConfig`, `elspeth.plugins.context.PluginContext`, `elspeth.plugins.schema_factory.create_schema_from_config`, `elspeth.plugins.sources.field_normalization.FieldResolution`, `elspeth.plugins.sources.field_normalization.resolve_field_names`. Imported by: `elspeth.plugins.validation`, `elspeth.plugins.azure.blob_source` (indirectly via shared patterns).
**Analysis depth:** FULL

## Summary

CSVSource is a well-structured source plugin that correctly implements the Tier 3 trust boundary pattern. The quarantine-or-yield flow for malformed rows is thorough and consistent. There is one critical finding around `zip(strict=False)` that is unreachable dead code due to an earlier guard but signals fragile intent. There are a few moderate warnings around resource handling and missing contract locking in edge paths. Overall, this file is sound with minor attention needed.

## Critical Findings

*None identified.*

## Warnings

### [243] `zip(headers, values, strict=False)` is redundant and misleading

**What:** Line 243 uses `dict(zip(headers, values, strict=False))` to build the row dict. However, the column-count check on line 219 (`if len(values) != expected_count`) already ensures that `headers` and `values` have equal length before this line is reached. The `strict=False` parameter is therefore unreachable in its "allow uneven" behavior -- but its presence implies to future readers that uneven lengths are expected and tolerated.

**Why it matters:** If the column-count guard on line 219 is ever refactored or moved (e.g., to support a "lenient" mode), the `strict=False` would silently truncate data rather than raising an error. In an audit-critical system, silently dropping trailing fields would be data integrity corruption. The `strict=True` parameter would be the correct safety-net, since it would crash if the guard were ever removed, surfacing the issue immediately rather than silently.

**Evidence:**
```python
# Line 219: Guard ensures equal length
if len(values) != expected_count:
    # ... quarantine and continue

# Line 243: strict=False is unreachable in its "truncate" behavior
row = dict(zip(headers, values, strict=False))
```

### [132] File handle opened but no protection against mid-iteration exceptions

**What:** The `with open(...)` context manager on line 132 correctly closes the file when the `with` block exits. However, `load()` is a generator (uses `yield`). The `with` block's `__exit__` is only called when the generator is garbage-collected or explicitly closed. If the caller does not exhaust the generator and does not call `.close()` on it, the file handle may remain open until GC runs.

**Why it matters:** In production with many pipelines running concurrently, leaked file handles could accumulate. Python's garbage collector typically handles this promptly for CPython (reference counting), but under PyPy or in edge cases with reference cycles, file handles could leak. This is a latent issue rather than an immediate production risk on CPython, but it violates resource safety best practices.

**Evidence:**
```python
def load(self, ctx: PluginContext) -> Iterator[SourceRow]:
    # ...
    with open(self._path, encoding=self._encoding, newline="") as f:
        # ... yield statements inside with block
        yield SourceRow.valid(...)
        yield SourceRow.quarantined(...)
```

### [184] Physical line number calculation after csv.Error may be imprecise

**What:** When a `csv.Error` is caught (line 180), the code computes `physical_line = reader.line_num + self._skip_rows`. However, `csv.reader.line_num` reports the last line read by the reader, which for a multiline quoted field would be the last line of that field. After a `csv.Error`, the `line_num` value may not correspond to the start of the problematic row -- it points to where the reader stopped, which could be in the middle of a multiline field or at the end of an unterminated quote.

**Why it matters:** The quarantined row's `__line_number__` metadata is used for audit trail investigation. If the line number is off, an auditor investigating a quarantined row would be directed to the wrong location in the source file. This is an audit accuracy issue, not a data integrity issue.

**Evidence:**
```python
except csv.Error as e:
    row_num += 1
    physical_line = reader.line_num + self._skip_rows  # May be imprecise
```

### [No line] JSON source has empty-source contract locking but CSV source pattern divergence risk

**What:** Lines 278-282 of CSVSource correctly handle the case where all rows are quarantined or the file has no data rows, by locking the contract. This is good. However, the JSON source (analyzed separately) is missing this pattern entirely. While this is not a bug in CSVSource itself, the asymmetry increases the risk that one source will diverge from the expected engine contract when the downstream consumer expects a locked contract.

**Why it matters:** If JSON source is used with an observed schema and all rows fail validation, the contract builder's contract would remain unlocked, potentially causing inconsistencies downstream.

**Evidence:**
```python
# CSV (correct)
if not first_valid_row_processed and self._contract_builder is not None:
    self.set_schema_contract(self._contract_builder.contract.with_locked())

# JSON source: this pattern is absent
```

## Observations

### [66-98] Constructor is well-structured

The constructor properly validates config through Pydantic (`CSVSourceConfig.from_dict`), creates the schema with `allow_coercion=True` (correct for Tier 3 boundary), and defers contract building until `load()` when headers are known. This is clean separation of concerns.

### [199/234/271] Consistent quarantine gating on `_on_validation_failure`

All three quarantine paths (csv.Error, column-count mismatch, validation error) consistently check `if self._on_validation_failure != "discard"` before yielding. This pattern is correct and consistent.

### [207-210] Empty row handling

Blank lines in CSV files return `[]` from `csv.reader`. The code correctly skips these with `if not values: continue` and does not increment `row_num`, which is the right behavior since blank lines are not data rows.

### [288-305] `get_field_resolution()` method

This is a clean read-only accessor for the audit trail. The `None` return when `load()` hasn't been called is documented and expected.

### [26-37] CSVSourceConfig inherits validation properly

The config class inherits from `TabularSourceDataConfig` which provides field normalization validation (mutual exclusion of `columns` and `normalize_fields`, etc.). This is correct delegation.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Change `strict=False` to `strict=True` on line 243 as a defense-in-depth measure. The remaining warnings are low-severity and can be tracked as backlog items. The generator-file-handle issue is inherent to Python generator patterns and may not warrant change unless production metrics show handle leakage.
**Confidence:** HIGH -- The file was read completely, all control flow paths were traced, and dependencies were examined for contract correctness.
