## Summary

`get_failure_context()` can silently drop failed node-state records when the corresponding `nodes` row is missing, under-reporting failures instead of crashing on Tier 1 audit corruption.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/mcp/analyzers/diagnostics.py
- Line(s): 250-270, 307-360
- Function/Method: `get_failure_context`

## Evidence

`failed_states` is loaded with an inner join to `nodes`:

```python
failed_states = conn.execute(
    select(...)
    .join(
        nodes_table,
        (node_states_table.c.node_id == nodes_table.c.node_id) & (node_states_table.c.run_id == nodes_table.c.run_id),
    )
    .where(node_states_table.c.run_id == run_id)
    .where(node_states_table.c.status == "failed")
    .order_by(node_states_table.c.started_at.desc())
    .limit(limit)
).fetchall()
```

Then the report’s counts and patterns are derived only from the joined rows:

```python
failed_state_list = [{...} for s in failed_states]
...
"failure_count": len(failed_state_list),
```

But `node_states` is audit-owned Tier 1 data with a composite FK to `nodes`:

- `/home/john/elspeth/src/elspeth/core/landscape/schema.py:207-230`

So if the audit DB is corrupted or partially imported and a `node_states` row no longer has a matching `nodes` row, this analyzer will not raise. The inner join simply removes the failed state from the result set, causing silent data loss in the incident report.

The same function already treats this class of mismatch as corruption for validation errors:

```python
if e.node_id is not None and e.plugin_name is None:
    raise RuntimeError(...)
```

- `/home/john/elspeth/src/elspeth/mcp/analyzers/diagnostics.py:331-337`

What the code does: silently omits unmatched failed states.

What it should do: detect the missing `nodes` row and crash with a Tier 1 corruption error.

## Root Cause Hypothesis

The query was written to enrich failed states with plugin metadata, but it uses an inner join as if missing `nodes` rows were impossible. In analyzer code, that assumption is unsafe: the MCP server is specifically for diagnosing broken audit databases, so corruption must be surfaced explicitly rather than filtered out by SQL join semantics.

## Suggested Fix

Change the failed-state query to `outerjoin(...)` and add an explicit corruption check before building the report, mirroring the validation-error path.

Example shape:

```python
failed_states = conn.execute(
    select(...)
    .outerjoin(
        nodes_table,
        (node_states_table.c.node_id == nodes_table.c.node_id)
        & (node_states_table.c.run_id == nodes_table.c.run_id),
    )
    ...
).fetchall()

for s in failed_states:
    if s.node_id is not None and s.plugin_name is None:
        raise RuntimeError(
            f"Tier-1 corruption: node_states row has node_id={s.node_id!r} "
            f"but no matching node in nodes table for run_id={run_id!r}"
        )
```

Add a regression test that injects a failed `node_states` row whose node metadata is missing and asserts `get_failure_context()` raises.

## Impact

Failure investigations can report too few failed states, too low a `failure_count`, and an incomplete `plugins_failing` list. That violates the auditability requirement that “I don’t know what happened” is never acceptable and breaks the expectation that Tier 1 anomalies crash immediately instead of producing a plausible but false report.
---
## Summary

`get_failure_context()` treats missing `nodes` metadata for transform errors as `plugin=None`, masking Tier 1 audit corruption instead of surfacing it.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/mcp/analyzers/diagnostics.py
- Line(s): 273-288, 320-327
- Function/Method: `get_failure_context`

## Evidence

Transform errors are joined to `nodes` with an outer join:

```python
transform_errors = conn.execute(
    select(...)
    .outerjoin(
        nodes_table,
        (transform_errors_table.c.transform_id == nodes_table.c.node_id)
        & (transform_errors_table.c.run_id == nodes_table.c.run_id),
    )
    .where(transform_errors_table.c.run_id == run_id)
    ...
).fetchall()
```

But the result builder does not validate the join outcome:

```python
transform_error_list = [
    {
        "token_id": e.token_id,
        "plugin": e.plugin_name,
        "details": json.loads(e.error_details_json) if e.error_details_json else None,
    }
    for e in transform_errors
]
```

- `/home/john/elspeth/src/elspeth/mcp/analyzers/diagnostics.py:273-327`

`transform_errors` has a composite FK to `nodes`:

- `/home/john/elspeth/src/elspeth/core/landscape/schema.py:443-466`

So a row with `plugin_name is None` is not “unknown plugin”; it is corrupted audit state. The function already follows that rule for validation errors, raising when `node_id` exists but the join finds no node:

- `/home/john/elspeth/src/elspeth/mcp/analyzers/diagnostics.py:331-337`

What the code does: returns a transform error entry with `"plugin": None`.

What it should do: raise immediately because our audit data is inconsistent.

## Root Cause Hypothesis

The transform-error path uses `outerjoin()` to avoid losing records, but it never added the follow-up corruption assertion that the validation-error path has. That leaves a silent “unknown plugin” fallback in Tier 1 analysis code, which conflicts with the project’s crash-on-anomaly rule for audit-owned data.

## Suggested Fix

Add an explicit corruption guard after fetching `transform_errors`, analogous to the validation-error handling.

Example shape:

```python
for e in transform_errors:
    if e.transform_id is not None and e.plugin_name is None:
        raise RuntimeError(
            f"Tier-1 corruption: transform_errors row has transform_id={e.transform_id!r} "
            f"but no matching node in nodes table for run_id={run_id!r}"
        )
```

Then build `transform_error_list` only after the integrity check passes. Add a regression test for a transform error whose node metadata is missing.

## Impact

Incident responders can receive a degraded failure report that looks valid but omits which transform failed. That erodes audit traceability for row-level failures and violates the Tier 1 rule that analyzer code must crash on corrupted internal records rather than silently fabricating an “unknown” answer.
