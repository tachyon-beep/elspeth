## Summary

`get_error_analysis()` silently masks broken node references by outer-joining error rows to `nodes` and then emitting `None` plugin buckets instead of treating the missing join as Tier 1 audit corruption.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/mcp/analyzers/reports.py
- Line(s): 360-409
- Function/Method: `get_error_analysis`

## Evidence

`get_error_analysis()` builds both summaries with `outerjoin(...)` and groups only on `nodes_table.c.plugin_name`:

```python
val_by_node = (
    select(
        nodes_table.c.plugin_name,
        validation_errors_table.c.schema_mode,
        func.count(validation_errors_table.c.error_id).label("count"),
    )
    .outerjoin(
        nodes_table,
        (validation_errors_table.c.node_id == nodes_table.c.node_id)
        & (validation_errors_table.c.run_id == nodes_table.c.run_id),
    )
    .group_by(nodes_table.c.plugin_name, validation_errors_table.c.schema_mode)
)

trans_by_node = (
    select(
        nodes_table.c.plugin_name,
        func.count(transform_errors_table.c.error_id).label("count"),
    )
    .outerjoin(
        nodes_table,
        (transform_errors_table.c.transform_id == nodes_table.c.node_id)
        & (transform_errors_table.c.run_id == nodes_table.c.run_id),
    )
    .group_by(nodes_table.c.plugin_name)
)
```

Then it returns those grouped rows directly as required string fields:

```python
{"source_plugin": row.plugin_name, ...}
{"transform_plugin": row.plugin_name, ...}
```

Source evidence that this is wrong:

- [`transform_errors_table`]( /home/john/elspeth/src/elspeth/core/landscape/schema.py#L443 ) enforces `transform_id` as `nullable=False` plus a composite FK to `nodes` at [`schema.py:461-466`]( /home/john/elspeth/src/elspeth/core/landscape/schema.py#L461 ). If `plugin_name` comes back `None`, that is not a valid “missing plugin”; it is audit corruption.
- Validation errors legitimately allow `node_id=None` at [`schema.py:416`]( /home/john/elspeth/src/elspeth/core/landscape/schema.py#L416 ) and tests confirm that path is supported at [`test_contract_audit.py:290-298`]( /home/john/elspeth/tests/integration/audit/test_contract_audit.py#L290 ) and [`test_model_loaders.py:1182-1197`]( /home/john/elspeth/tests/unit/core/landscape/test_model_loaders.py#L1182 ).
- Another analyzer already handles this correctly: [`diagnostics.py:331-337`]( /home/john/elspeth/src/elspeth/mcp/analyzers/diagnostics.py#L331 ) raises when `validation_errors.node_id` is set but the node join fails.

What the code does now:
- Broken `transform_errors -> nodes` joins are silently reported as `{"transform_plugin": None, ...}`.
- Broken `validation_errors -> nodes` joins are silently merged into the same `source_plugin=None` bucket as legitimate `node_id=None` validation errors.

What it should do:
- Treat unmatched `transform_errors` joins as a hard failure.
- Distinguish legitimate `validation_errors.node_id is None` from corrupted `node_id set but no node row`, and raise on the corrupted case.

## Root Cause Hypothesis

The function was written as a convenience aggregate and used permissive SQL outer joins, but it forgot that Landscape reads are Tier 1 reads. That made sense for optional validation `node_id`, but the implementation grouped away the evidence needed to tell “legitimate unattributed validation error” from “missing node row,” and it applied the same permissive pattern to `transform_errors`, where missing nodes are never valid.

## Suggested Fix

Keep the grouping logic in `reports.py`, but first fetch enough identity to validate joins before aggregating.

For example:
- Include `validation_errors_table.c.node_id` in the validation query.
- Include `transform_errors_table.c.transform_id` in the transform query.
- Before building summaries:
  - if `transform_id` is non-null and `plugin_name` is `None`, raise `RuntimeError`/`AuditIntegrityError`.
  - if `validation node_id` is non-null and `plugin_name` is `None`, raise.
- Aggregate in Python after validation so legitimate `node_id=None` validation errors can be represented intentionally instead of being merged with corruption.

## Impact

This hides audit-database corruption in an analysis endpoint whose purpose is to explain failures. An operator can receive a plausible report with `None` plugin buckets instead of an immediate integrity failure, which breaks the project’s “bad data in the audit trail = crash immediately” rule and can misattribute or de-attribute the source of failures during investigation.
---
## Summary

`get_llm_usage_report()` only returns its documented “empty” response when a run has no external calls at all, so runs with HTTP/SQL calls but zero LLM calls get a misleading zeroed LLM summary instead of the no-LLM case.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/mcp/analyzers/reports.py
- Line(s): 501-565
- Function/Method: `get_llm_usage_report`

## Evidence

The report type explicitly documents a special case for “no LLM calls”:

- [`types.py:268-281`]( /home/john/elspeth/src/elspeth/mcp/types.py#L268 )

```python
class LLMUsageReport(TypedDict, total=False):
    # Present when there are LLM calls
    call_types: dict[str, int]
    llm_summary: LLMSummary
    by_plugin: dict[str, LLMPluginStats]
    # Present when there are NO LLM calls
    message: str
```

But the implementation only uses that case when *both* `llm_rows` and `call_type_rows` are empty:

```python
if not llm_rows and not call_type_rows:
    return {
        "run_id": run_id,
        "message": "No external calls found in this run",
        "call_types": {},
    }
```

That means a run with non-LLM calls only will return:

- `call_types` populated, e.g. `{"http": 3}`
- `llm_summary = {"total_calls": 0, ...}`
- `by_plugin = {}`

instead of the documented no-LLM message path.

This scenario is real, not hypothetical:
- sources record HTTP calls during operations, e.g. [`dataverse.py:512-519`]( /home/john/elspeth/src/elspeth/plugins/sources/dataverse.py#L512 ) calls `ctx.record_call(call_type=CallType.HTTP, ...)`.

What the code does now:
- Treats “HTTP-only run” as if it were an LLM run with zero usage.

What it should do:
- Return the no-LLM-case whenever `llm_rows` is empty, regardless of whether other external call types exist.

## Root Cause Hypothesis

The function conflates two different states:
1. no external calls at all
2. external calls exist, but none are LLM calls

Because it gates the special case on `call_type_rows` as well as `llm_rows`, it only handles the first state.

## Suggested Fix

Change the empty-path condition to branch on `llm_rows` alone.

For example:
- if `not llm_rows`:
  - return `run_id`
  - return `call_types` summarizing other calls if desired
  - return `message` like `"No LLM calls found in this run"`
  - omit `llm_summary` and `by_plugin`

That keeps the function aligned with its own return contract while preserving useful context about other call types.

## Impact

MCP consumers cannot reliably distinguish “this run never used an LLM” from “this report has an actual LLM summary.” UI or automation built against the documented contract may render misleading zero-usage LLM stats for HTTP-only pipelines instead of the intended no-LLM result.
