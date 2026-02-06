# Analysis: src/elspeth/core/landscape/lineage.py

**Lines:** 217
**Role:** Implements the `explain()` function that composes query results from the `LandscapeRecorder` into a complete `LineageResult` for a token or row. This powers the `elspeth explain` command -- the primary user-facing tool for tracing decisions back to their source data. The `LineageResult` dataclass aggregates token identity, source row, node states, routing events, external calls, parent tokens, errors, and outcome into a single object.
**Key dependencies:** Imports audit contract types from `elspeth.contracts`. Takes a `LandscapeRecorder` as its primary dependency (TYPE_CHECKING import). Consumed by `mcp/server.py`, `core/landscape/__init__.py` (re-exported), and the TUI lineage screens.
**Analysis depth:** FULL

## Summary

The lineage module is the most audit-critical query path in the system -- it answers the question "what happened to this row?" The implementation is correct and follows Tier 1 trust principles rigorously, with explicit integrity validation for parent token relationships. There is one N+1 query pattern that impacts performance for tokens with many node states, and one edge case in row-based lookup that could produce misleading results.

## Warnings

### [157-166] N+1 query pattern for routing events and external calls

**What:** Lines 157-166 iterate over `node_states` and for each state call `recorder.get_routing_events(state.state_id)` and `recorder.get_calls(state.state_id)`. These are per-state queries inside a loop. For a token that traversed many nodes (e.g., a DAG with 10+ transforms, or multiple retry attempts), this produces 2*N queries where N is the number of node states.

**Why it matters:** The `explain()` function is called interactively (from the CLI `explain` command and the MCP server). Users expect near-instant responses. For a token with 20 node states (reasonable for a deep pipeline with retries), this produces 40 additional queries beyond the base queries. Each query has SQLAlchemy overhead (connection acquisition, SQL generation, result set processing).

The exporter solved this same problem with batch queries (`get_all_routing_events_for_run`, `get_all_calls_for_run`) but the lineage module still uses per-entity queries. The lineage case is different (single token, not entire run), but the pattern could be improved with a batch query that fetches all routing events and calls for a set of state_ids in a single query using an IN clause.

**Evidence:**
```python
# N+1: one query per state for routing events
routing_events: list[RoutingEvent] = []
for state in node_states:
    events = recorder.get_routing_events(state.state_id)
    routing_events.extend(events)

# N+1: one query per state for calls
calls: list[Call] = []
for state in node_states:
    state_calls = recorder.get_calls(state.state_id)
    calls.extend(state_calls)
```

### [96-136] Row-based lookup returns `None` for rows with only non-terminal tokens

**What:** When looking up by `row_id` (lines 96-136), the function filters outcomes to terminal-only. If all tokens for a row are in non-terminal states (e.g., `BUFFERED` in an aggregation), the function returns `None` (line 106). This is documented and intentional, but the caller receives the same `None` as for "row not found" (line 99), making it impossible to distinguish the two cases.

**Why it matters:** From the user's perspective, `explain(run_id=X, row_id=Y)` returning `None` could mean: (a) the row does not exist, (b) the row is buffered and awaiting aggregation, or (c) processing has not started. These are very different situations for debugging. The `LineageTextFormatter` renders all three as "No lineage found. Token or row may not exist, or processing is incomplete." This could mislead an operator investigating a stuck pipeline.

**Evidence:**
```python
outcomes = recorder.get_token_outcomes_for_row(run_id, row_id)
if not outcomes:
    return None  # Case: row not found OR no outcomes recorded

terminal_outcomes = [o for o in outcomes if o.is_terminal]
if not terminal_outcomes:
    return None  # Case: all tokens non-terminal (BUFFERED)
```

A more informative approach would be to return a distinct signal (e.g., a different return type or a `LineageResult` with a status field) for "in progress" vs "not found."

### [175-183] Tier 1 integrity check for group_id-without-parents has a false positive edge case

**What:** Lines 175-183 validate that tokens with `fork_group_id`, `join_group_id`, or `expand_group_id` must have parent records in the `token_parents` table. This raises a `ValueError` (audit integrity violation) if a group ID is present but no parents exist.

**Why it matters:** The truthiness check `has_group_id = token.fork_group_id or token.join_group_id or token.expand_group_id` uses Python's truthiness. If a group_id is set to an empty string `""` (which is falsy), the check would pass (no validation) even though the token has a group_id. Per Tier 1 trust, an empty string group_id is itself an integrity violation that should be caught, but this check would silently skip it.

This is a minor edge case -- UUIDs are used for group_ids, so empty strings should not appear in practice. But per the Data Manifesto, "if it's not recorded, it didn't happen" -- a check that silently passes on edge cases is weaker than the Tier 1 standard demands.

**Evidence:**
```python
has_group_id = token.fork_group_id or token.join_group_id or token.expand_group_id
if has_group_id and not parents:
    # This validation is skipped if group_id is "" (empty string, which is falsy)
```

### [185-196] N+1 query pattern for parent token resolution

**What:** For each parent in `parents` list, the function calls `recorder.get_token(parent.parent_token_id)` individually (line 186). If a token was created by a coalesce (join) of many branches, it could have many parents, each requiring a separate query.

**Why it matters:** Similar to the routing events/calls N+1 pattern, but less severe because most tokens have 0-2 parents. Coalesce operations merging many branches are the exception, but when they occur (e.g., 10-way fan-in), this produces 10 queries.

**Evidence:**
```python
for parent in parents:
    parent_token = recorder.get_token(parent.parent_token_id)
    if parent_token is None:
        raise ValueError(...)  # Audit integrity violation
    parent_tokens.append(parent_token)
```

## Observations

### [186-195] Excellent audit integrity defense-in-depth for dangling parent references

**What:** If `recorder.get_token(parent.parent_token_id)` returns `None`, the function raises a `ValueError` with a detailed message explaining that this indicates database corruption. The comment on lines 188-190 notes that foreign key constraints should make this impossible, but the check exists as defense-in-depth.

**Why it matters:** This is correct Tier 1 behavior. The detailed error message aids debugging and explicitly names the violation type.

### [90-91] Correct fail-fast on missing arguments

**What:** The function raises `ValueError` immediately if neither `token_id` nor `row_id` is provided. This prevents the function from proceeding with undefined behavior.

### [138-140] Cast usage for type narrowing is correct

**What:** Line 140 uses `cast(str, token_id)` to narrow the type from `str | None` to `str` after the control flow guarantees it is set. This is the correct way to handle this pattern -- the control flow analysis on lines 94-136 ensures `token_id` is assigned before reaching this point.

### [198-199] Validation errors looked up by hash, not by row_id

**What:** `get_validation_errors_for_row` takes `source_data_hash` rather than `row_id` as the lookup key. This is because validation errors are recorded at the source level before rows are assigned IDs -- they are keyed by the hash of the source data. This is correct for the data model.

### [63-68] Clean function signature with clear disambiguation options

**What:** The `explain()` function accepts `token_id` (precise, for DAGs with forks), `row_id` (convenient, for simple pipelines), and `sink` (for disambiguation). The parameter hierarchy and validation logic are well-documented in the docstring.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) The N+1 query pattern for routing events and calls (lines 157-166) should be optimized with batch queries using an IN clause over the set of state_ids, especially since this is a user-facing interactive path. (2) Consider returning a richer result type from `explain()` that distinguishes "not found" from "in progress" when looking up by row_id. (3) The group_id truthiness check (line 175) should use explicit `is not None` comparisons instead of Python truthiness to catch empty string edge cases.
**Confidence:** HIGH -- The code is concise and well-structured. The N+1 patterns are verifiable by examining the recorder methods called in loops. The truthiness edge case is a minor but real gap in the Tier 1 validation.
