## Summary

`list_tokens()` scopes tokens by joining through `rows.run_id` instead of using `tokens.run_id`, so it can return cross-run-contaminated tokens if a token’s denormalized run ownership disagrees with its row.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/mcp/analyzers/queries.py
- Line(s): 168-177
- Function/Method: `list_tokens`

## Evidence

`tokens_table` carries its own `run_id` explicitly for “cross-run contamination prevention”:

```python
# /home/john/elspeth/src/elspeth/core/landscape/schema.py:138-141
Column("row_id", String(64), ForeignKey("rows.row_id"), nullable=False),
Column("run_id", String(64), ForeignKey("runs.run_id"), nullable=False),  # Run ownership for cross-run contamination prevention
```

But `list_tokens()` ignores that denormalized ownership and filters only through `rows.run_id`:

```python
# /home/john/elspeth/src/elspeth/mcp/analyzers/queries.py:168-177
query = (
    select(tokens_table)
    .join(rows_table, tokens_table.c.row_id == rows_table.c.row_id)
    .where(rows_table.c.run_id == run_id)
    .limit(limit)
)
if row_id is not None:
    query = query.where(tokens_table.c.row_id == row_id)
```

What it does:
- Returns any token attached to a row in the requested run.

What it should do:
- Return only tokens whose own `tokens.run_id` matches the requested run, because token ownership is recorded independently for audit integrity.

The surrounding codebase treats denormalized run ownership as the correct filter for audit entities. For example, `get_all_node_states_for_run()` filters directly on `node_states.run_id` rather than joining outward:

```python
# /home/john/elspeth/src/elspeth/core/landscape/query_repository.py:393-397
query = (
    select(node_states_table)
    .where(node_states_table.c.run_id == run_id)
```

## Root Cause Hypothesis

This query appears to have been written using the older “join back to the parent table for run scoping” pattern and never updated after `tokens.run_id` was added as an explicit audit-integrity field. That makes the MCP read path trust row ownership instead of token ownership.

## Suggested Fix

Filter on `tokens_table.c.run_id == run_id` directly, and keep the row join only if it is needed for some other column or integrity check. Also add a deterministic `order_by` while touching this query.

Example fix:

```python
query = (
    select(tokens_table)
    .where(tokens_table.c.run_id == run_id)
    .order_by(tokens_table.c.created_at, tokens_table.c.token_id)
    .limit(limit)
)
if row_id is not None:
    query = query.where(tokens_table.c.row_id == row_id)
```

## Impact

If the database ever contains a token whose `row_id` points at one run while `tokens.run_id` points at another, `list_tokens()` will surface that token under the wrong run. For an audit tool, that is a lineage integrity failure: analysts can select and explain a token that does not actually belong to the requested run.
---
## Summary

`query()` silently drops result columns when the SQL returns duplicate column names, which can erase audit evidence from ad-hoc analysis queries.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/mcp/analyzers/queries.py
- Line(s): 768-773
- Function/Method: `query`

## Evidence

The result rows are converted to dicts with raw column names as keys:

```python
# /home/john/elspeth/src/elspeth/mcp/analyzers/queries.py:768-773
with db.connection() as conn:
    result = conn.execute(text(sql), params or {})
    columns = result.keys()
    rows = result.fetchall()

return [dict(zip(columns, [_serialize_datetime(v) for v in row], strict=False)) for row in rows]
```

If a query returns duplicate labels, `dict(...)` overwrites the earlier value with the later one. I verified that behavior locally with SQLAlchemy:

```python
list(result.keys())  -> ['x', 'x']
tuple(row)           -> (1, 2)
dict(zip(...))       -> {'x': 2}
```

That means a perfectly normal audit query like `SELECT rows.run_id, tokens.run_id ...` or `SELECT *` across joined tables can silently lose one side of the result.

The use of `strict=False` is also bug-hiding: if keys and row values ever diverge, this path will truncate instead of failing loudly.

## Root Cause Hypothesis

The generic SQL tool was implemented with a convenience `dict(zip(...))` conversion, but ad-hoc audit SQL does not guarantee unique column labels. The code assumes a one-to-one mapping between column names and dict keys even though SQL joins routinely violate that assumption.

## Suggested Fix

Reject duplicate column labels before building dicts, or normalize them to unique names in a deterministic way. Also remove `strict=False` so structural mismatches fail loudly.

Example fix:

```python
columns = list(result.keys())
dupes = {name for name in columns if columns.count(name) > 1}
if dupes:
    raise ValueError(f"Query returned duplicate column names: {sorted(dupes)}. Alias columns explicitly.")

return [
    dict(zip(columns, [_serialize_datetime(v) for v in row], strict=True))
    for row in rows
]
```

## Impact

This is silent data loss in the MCP audit surface. An analyst can run a valid read-only SQL query and receive a response that omits one of the selected values without any error. That undermines trust in ad-hoc investigations and can hide cross-table discrepancies precisely when the tool is being used to prove lineage or diagnose audit anomalies.
