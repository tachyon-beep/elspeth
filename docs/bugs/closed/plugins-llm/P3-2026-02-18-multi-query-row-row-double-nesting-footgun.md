## Summary

The multi-query template context creates a confusing double-nesting of `row`. `build_template_context()` sets `context["row"] = original_row`, then `PromptTemplate.render()` wraps the entire synthetic dict under `context["row"]`. Result: `{{ row }}` = synthetic dict, `{{ row.row }}` = original row. This naming collision is a footgun that has already caused real user-facing template errors.

## Severity

- Severity: minor (design smell)
- Priority: P3

## Location

- File: `src/elspeth/plugins/llm/multi_query.py`
- Line(s): `124`
- Function/Method: `QuerySpec.build_template_context()`
- Related: `src/elspeth/plugins/llm/templates.py:174` (`render()` context construction)

## Evidence

`build_template_context` at line 124:

```python
context["row"] = row  # original PipelineRow
```

`render()` at line 174:

```python
context: dict[str, Any] = {
    "row": row_context,  # row_context = the synthetic dict containing "row" key
    "lookup": self._lookup_data,
}
```

Template access patterns become:
- `{{ row }}` → synthetic dict (not the actual row)
- `{{ row.row }}` → original source row
- `{{ row.input_1 }}` → positional value
- `{{ row.case_study }}` → case study metadata

A template author unfamiliar with this nesting will naturally write `{{ row.field_name }}` expecting source data and get synthetic context instead, or `{{ row.case_study.input_1 }}` conflating metadata with positional data.

## Root Cause Hypothesis

`build_template_context` was designed to build a self-contained context dict with everything a template might need, including the original row under the key `"row"`. But `PromptTemplate.render()` independently wraps whatever it receives under its own `"row"` key. Neither was designed with awareness of the other's naming choice.

## Suggested Fix

Rename the original row key in `build_template_context` to avoid collision:

```python
# multi_query.py:124
context["source_row"] = row  # was: context["row"] = row
```

Template authors then use:
- `{{ row.input_1 }}` — positional data (unchanged)
- `{{ row.source_row.field_name }}` — original source data (clear intent)
- `{{ row.criterion }}` — criterion metadata (unchanged)
- `{{ row.case_study }}` — case study metadata (unchanged)

This eliminates the `row.row` confusion while keeping all data accessible. Requires updating any existing templates that use `{{ row.row }}`.
