## Summary

When `input_contract` is not None, `PromptTemplate.render()` wraps the multi-query synthetic dict in `PipelineRow(synthetic_dict, source_contract)`. The source contract knows about source columns (`case_study_1`, `service_summary`, etc.) but has no knowledge of synthetic keys (`input_1`, `input_2`, `criterion`, `case_study`). In FIXED schema mode, `resolve_name("input_1")` raises `KeyError` and the FIXED-mode fallback refuses raw data access, making all positional template variables inaccessible. FLEXIBLE/OBSERVED modes survive via raw data fallback but the contract mismatch is still semantically wrong.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `src/elspeth/plugins/llm/templates.py`
- Line(s): `168-169`
- Function/Method: `PromptTemplate.render()`
- Related: `src/elspeth/plugins/llm/multi_query.py:97-126` (`build_template_context`)

## Evidence

In `render()`:

```python
elif contract is not None:
    row_context = PipelineRow(row, contract)  # row = synthetic dict, contract = source schema
```

The synthetic dict from `build_template_context` contains:

```python
{"input_1": v1, "input_2": v2, ..., "criterion": {...}, "case_study": {...}, "row": original_row}
```

The source schema contract contains fields like `case_study_1`, `service_summary`, etc. — none of the synthetic keys.

`PipelineRow.__getitem__` resolution path for `input_1`:
1. `resolve_name("input_1")` → not in `_by_normalized`, not in `_by_original` → `KeyError`
2. Fallback: `if mode in ("FLEXIBLE", "OBSERVED") and key in self._data` → works in FLEXIBLE/OBSERVED
3. In FIXED mode: re-raises `KeyError` → `AttributeError` → Jinja2 `UndefinedError`

## Root Cause Hypothesis

`PromptTemplate.render()` was designed for regular rows where the contract describes the row's actual fields. The multi-query system creates a synthetic dict with a different structure than the source schema, but passes the source's contract anyway. The contract/data mismatch is papered over by the FLEXIBLE/OBSERVED fallback but breaks in FIXED mode.

## Suggested Fix

Two options:

**Option A (minimal):** Don't pass the source contract when rendering synthetic dicts. In `azure_multi_query.py` and `openrouter_multi_query.py`, pass `contract=None` to `render_with_metadata()` for synthetic rows, so the dict is used directly without PipelineRow wrapping.

**Option B (proper):** Build a synthetic `SchemaContract` that describes the actual synthetic dict structure (`input_1`, `input_2`, ..., `criterion`, `case_study`, `row`), and pass that instead. This preserves contract-aware rendering while accurately describing the data.

Option A is simpler and sufficient since the synthetic dict's structure is well-defined by `build_template_context`.
