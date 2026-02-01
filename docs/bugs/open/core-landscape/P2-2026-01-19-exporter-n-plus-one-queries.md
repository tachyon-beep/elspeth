# Bug Report: LandscapeExporter uses N+1 query pattern (likely very slow for large runs)

## Summary

- `LandscapeExporter._iter_records()` performs nested per-entity queries:
  - for each row → query tokens
  - for each token → query token_parents + node_states
  - for each state → query routing_events + calls
- This can lead to extremely high query counts and poor performance on large runs, even on local SQLite.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: codex
- Date: 2026-01-19
- Related run/issue ID: N/A

## Environment

- Commit/branch: `main` @ `8ca061c9293db459c9a900f2f74b19b59a364a42`
- OS: Linux (Ubuntu kernel 6.8.0-90-generic)
- Python version: 3.13.1
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: deep dive subsystem 4 (Landscape) and create bug tickets
- Model/version: GPT-5.2 (Codex CLI)
- Tooling and permissions (sandbox/approvals): workspace-write, network restricted, approvals on-request
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code inspection (complexity analysis)

## Steps To Reproduce

1. Run a pipeline with thousands of rows and multiple node states per token.
2. Enable post-run export (`landscape.export.enabled: true`).
3. Observe export time grows superlinearly due to many small DB transactions/queries.

## Expected Behavior

- Export should execute a bounded number of queries per run (ideally one per table/record type), using joins or batch loads keyed by `run_id` and related IDs.

## Actual Behavior

- Export performs nested queries across row/token/state hierarchies.

## Evidence

- Nested query loops:
  - `src/elspeth/core/landscape/exporter.py:199-332`
- Each `LandscapeRecorder.get_*` call opens its own transaction/connection:
  - `src/elspeth/core/landscape/recorder.py` (multiple `with self._db.connection()` blocks)

## Impact

- User-facing impact: slow exports for realistic datasets; can make “post-run export” unusable at scale.
- Data integrity / security impact: low.
- Performance or cost impact: high DB overhead (many transactions) and potential lock contention on SQLite.

## Root Cause Hypothesis

- Exporter was implemented for correctness first and composes existing per-entity query methods without batching.

## Proposed Fix

- Code changes (modules/files):
  - Implement batched export queries:
    - prefetch all rows/tokens/states/events/calls with a small number of queries
    - assemble records in Python using maps keyed by IDs
  - Alternatively, add dedicated export query methods on recorder that return grouped results efficiently.
- Config or schema changes: none.
- Tests to add/update:
  - Add a performance/regression test (bounded query count) if feasible, or at least a benchmark harness.
- Risks or migration steps:
  - Ensure deterministic output ordering is preserved when switching to batch queries (important for signing).

## Architectural Deviations

- Spec or doc reference: `docs/design/requirements.md` (export feature expectations)
- Observed divergence: exporter likely scales poorly.
- Reason (if known): N+1 composition pattern.
- Alignment plan or decision needed: decide acceptable export performance targets (rows/sec, max run size).

## Acceptance Criteria

- Export for large runs performs a bounded number of queries and completes in reasonable time (define target).
- Output ordering remains deterministic for signed exports.

## Tests

- Suggested tests to run: `pytest tests/core/landscape/test_exporter.py`
- New tests required: optional (benchmark/harness)

## Notes / Links

- Related issues/PRs: N/A

## Verification (2026-01-25)

**Status: STILL VALID**

The N+1 query pattern remains present in the current codebase. No fixes have been applied since this bug was filed.

## Verification (2026-02-01)

**Status: STILL VALID**

- `_iter_records()` still performs nested per-row/per-token/per-state queries. (`src/elspeth/core/landscape/exporter.py:231-320`)

### Current State Analysis

**Code examination confirms the nested query structure:**

1. **Main export loop** (`exporter.py:199-366`):
   - `get_rows(run_id)` - one query per run
   - For each row → `get_tokens(row_id)` - one query per row
   - For each token → `get_token_parents(token_id)` - one query per token
   - For each token → `get_node_states_for_token(token_id)` - one query per token
   - For each state → `get_routing_events(state_id)` - one query per state
   - For each state → `get_calls(state_id)` - one query per state

2. **Query count formula for a typical run:**
   - Rows: 1 query
   - Tokens: R queries (R = number of rows)
   - Token parents: T queries (T = number of tokens)
   - Node states: T queries
   - Routing events: S queries (S = number of states)
   - External calls: S queries
   - Batches: 1 query
   - Batch members: B queries (B = number of batches)
   - Artifacts: 1 query

   **Total: ~5 + R + 2T + 2S + B queries minimum**

3. **Example scaling:**
   - 1,000 rows × 2 tokens/row × 5 states/token = 1,000 + 2,000 + 2,000 + 10,000 + 10,000 = **~25,000 queries**
   - Each query involves `with self._db.connection()` context manager (separate transaction)

### Evidence from Current Code

**Exporter (`src/elspeth/core/landscape/exporter.py:199-329`):**
```python
# Rows and their tokens/states
for row in self._recorder.get_rows(run_id):
    # ... yield row record ...

    # Tokens for this row
    for token in self._recorder.get_tokens(row.row_id):
        # ... yield token record ...

        # Token parents (for fork/join lineage)
        for parent in self._recorder.get_token_parents(token.token_id):
            # ... yield parent record ...

        # Node states for this token
        for state in self._recorder.get_node_states_for_token(token.token_id):
            # ... yield state record ...

            # Routing events for this state
            for event in self._recorder.get_routing_events(state.state_id):
                # ... yield event record ...

            # External calls for this state
            for call in self._recorder.get_calls(state.state_id):
                # ... yield call record ...
```

**Recorder query methods all open separate connections (`src/elspeth/core/landscape/recorder.py`):**
```python
def get_tokens(self, row_id: str) -> list[Token]:
    query = select(tokens_table).where(tokens_table.c.row_id == row_id)...
    with self._db.connection() as conn:  # Separate connection per call
        result = conn.execute(query)
```

### Git History Check

No commits addressing this issue found:
- Searched for keywords: "N+1", "exporter", "batch query", "query optimization"
- Only formatting and unrelated fixes since 2026-01-19
- Recent commits: RC-1 release (c786410), PENDING status addition (0f21ecb), explain() disambiguation (6ea21c4)

### Test Coverage Assessment

**Existing tests focus on correctness, NOT performance:**
- `tests/core/landscape/test_exporter.py` - functional correctness tests only
- `tests/integration/test_landscape_export.py` - end-to-end integration tests
- No tests measuring query count or performance scaling
- Determinism tests exist (critical for signed exports) but don't measure efficiency

**Test observation:**
The determinism test at `test_exporter.py:592-688` actually creates a complex run with multiple records and exports 5 times to verify hash stability. This test would execute thousands of queries per export but doesn't measure or assert on query count.

### Impact Severity

**Current assessment: P2 is appropriate**

Reasons:
1. **Not P1** - System is functional; this is a performance optimization, not a correctness bug
2. **Significant at scale** - For production workloads (10k+ rows), export could take minutes instead of seconds
3. **SQLite impact** - Transaction overhead is significant; each `connection()` context is a separate transaction
4. **No workarounds** - Users can't bypass this; export is all-or-nothing

### Recommendations

1. **Keep as P2** - Should be fixed before declaring exporter "production-ready" but not a blocker for RC-1
2. **Add performance test** - Benchmark query count on synthetic data (100 rows, 200 tokens, 1000 states)
3. **Fix approach**: Implement batch queries in recorder:
   ```python
   # NEW: Batch query methods for export
   def get_all_export_data(self, run_id: str) -> ExportData:
       """Fetch all export data in 8-10 queries total."""
       with self._db.connection() as conn:
           rows = conn.execute(select(rows_table).where(...))
           tokens = conn.execute(select(tokens_table).where(...))
           # ... join in Python using dicts
   ```
4. **Risk mitigation**: Preserve ORDER BY clauses for deterministic export signatures (critical!)

### Verified By

- Examiner: Claude Sonnet 4.5
- Date: 2026-01-25
- Method: Code inspection, git history review, test coverage analysis
- Commit hash: 7540e57 (current HEAD on `fix/rc1-bug-burndown-session-4`)
