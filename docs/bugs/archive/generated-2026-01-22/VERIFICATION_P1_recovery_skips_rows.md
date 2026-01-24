# Bug Verification Report: Recovery Skips Rows for Sinks Written Later

## Status: FALSE POSITIVE

**Bug ID:** P1-2026-01-22-recovery-skips-rows
**Claimed Location:** `src/elspeth/core/checkpoint/recovery.py` (Bug #1 in CATALOG.md)
**Verification Date:** 2026-01-22
**Verifier:** Claude Code

---

## Summary of Bug Claim

The bug report claims that `RecoveryManager.get_unprocessed_rows()` uses row_index from the latest checkpoint as a single boundary, but checkpoint order doesn't align with row_index across multiple sinks, causing resume to skip rows routed to a later/failed sink.

## Code Analysis

### Checkpoint Creation (orchestrator.py:929-950)

```python
# From orchestrator.py:929-950
def checkpoint_after_sink(sink_node_id: str) -> Callable[[TokenInfo], None]:
    def callback(token: TokenInfo) -> None:
        self._maybe_checkpoint(
            run_id=run_id,
            token_id=token.token_id,
            node_id=sink_node_id,
        )
    return callback

for sink_name, tokens in pending_tokens.items():
    if tokens and sink_name in config.sinks:
        sink = config.sinks[sink_name]
        sink_node_id = sink_id_map[sink_name]
        sink_executor.write(
            sink=sink,
            tokens=tokens,
            ctx=ctx,
            step_in_pipeline=step,
            on_token_written=checkpoint_after_sink(sink_node_id),
        )
```

### get_unprocessed_rows (recovery.py:206-258)

```python
# From recovery.py:206-258
def get_unprocessed_rows(self, run_id: str) -> list[str]:
    """Get row IDs that were not processed before the run failed.

    Derives the row boundary from token lineage:
    checkpoint.token_id -> tokens.row_id -> rows.row_index
    """
    checkpoint = self._checkpoint_manager.get_latest_checkpoint(run_id)
    if checkpoint is None:
        return []

    with self._db.engine.connect() as conn:
        # Step 1: Find the row_index of the checkpointed token's source row
        # Join: checkpoint.token_id -> tokens.row_id -> rows.row_index
        checkpointed_row_index_query = (
            select(rows_table.c.row_index)
            .select_from(
                tokens_table.join(
                    rows_table,
                    tokens_table.c.row_id == rows_table.c.row_id,
                )
            )
            .where(tokens_table.c.token_id == checkpoint.token_id)
        )
        # ...
        checkpointed_row_index = checkpointed_row_result.row_index

        # Step 2: Find all rows with row_index > checkpointed_row_index
        result = conn.execute(
            select(rows_table.c.row_id)
            .where(rows_table.c.run_id == run_id)
            .where(rows_table.c.row_index > checkpointed_row_index)
            .order_by(rows_table.c.row_index)
        ).fetchall()

    return [row.row_id for row in result]
```

### Critical Observation: Sink Write Order

Looking at `orchestrator.py:939`:
```python
for sink_name, tokens in pending_tokens.items():
```

This iterates over sinks in dict order (Python 3.7+ maintains insertion order). For each sink, ALL tokens are written, and a checkpoint is created for EACH token after successful write.

### The Key Insight

The bug claim misunderstands the execution model:

1. **Rows are processed in order**: Row 0, then Row 1, then Row 2, etc.
2. **Sink writes happen AFTER all row processing**: Tokens are buffered in `pending_tokens` during row processing
3. **All tokens for ALL sinks are collected before ANY sink write**
4. **Checkpoints record token completion, deriving row_index from the token's source row**

### Scenario Analysis: Two Sinks, sink_b Fails

Let's trace through the claimed bug scenario:

**Setup:**
- Pipeline with sink_a (default) and sink_b (via gate routing)
- 5 rows: Row 0, 1, 2 -> sink_a; Row 3, 4 -> sink_b
- Checkpoint frequency: every_row

**Execution Flow:**

1. **Row Processing Phase:**
   - Rows 0-4 are processed through transforms
   - Tokens are routed and buffered in `pending_tokens`:
     - `pending_tokens["sink_a"] = [tok-0, tok-1, tok-2]`
     - `pending_tokens["sink_b"] = [tok-3, tok-4]`

2. **Sink Write Phase (orchestrator.py:939-950):**
   - sink_a.write([tok-0, tok-1, tok-2]) - SUCCESS
   - Checkpoints created: tok-0 (row_index=0), tok-1 (row_index=1), tok-2 (row_index=2)
   - sink_b.write([tok-3, tok-4]) - FAILS
   - Run marked as failed

3. **Latest Checkpoint:**
   - The latest checkpoint is for tok-2, with row_index=2

4. **Recovery:**
   - `get_unprocessed_rows()` finds row_index=2 from tok-2
   - Returns rows with row_index > 2: Row 3, Row 4
   - This is CORRECT - exactly the rows that weren't written

### Why the Bug Claim is Wrong

The bug claim states:
> "checkpoint order doesn't align with row_index across multiple sinks"

This is incorrect because:

1. **Checkpoints are created by row_index order**: Rows are processed sequentially (0, 1, 2, 3, 4)
2. **Sink writes happen in batches, but maintain row order**: Tokens for sink_a (rows 0,1,2) are written first, then tokens for sink_b (rows 3,4)
3. **If sink_b fails, the latest successful checkpoint is from sink_a's last token**: The token with the highest row_index that was successfully written to any sink

The recovery correctly identifies rows 3, 4 as unprocessed because:
- Latest checkpoint's token (tok-2) maps to row_index=2
- Rows with row_index > 2 are returned: rows 3, 4
- These are exactly the rows that weren't written before the crash

### Edge Case: Interleaved Row Processing

What if rows were interleaved (e.g., row 0 -> sink_a, row 1 -> sink_b, row 2 -> sink_a)?

**Buffering Phase:**
- `pending_tokens["sink_a"] = [tok-0, tok-2]`
- `pending_tokens["sink_b"] = [tok-1]`

**Sink Write Phase:**
- sink_a writes tok-0 (row 0), tok-2 (row 2) - checkpoints at row_index=0, row_index=2
- sink_b writes tok-1 (row 1) - fails before checkpoint

**Latest Checkpoint:** row_index=2 (from tok-2)

**Recovery:** Returns rows with row_index > 2 = none

**Is this wrong?** YES, this WOULD be a bug - row 1 was never successfully written but won't be recovered.

HOWEVER, looking at the checkpoint callback more carefully:

```python
on_token_written=checkpoint_after_sink(sink_node_id),
```

Each token gets a checkpoint AFTER it's written. If sink_b fails, it fails on `sink.write()` which is a batch write. The `on_token_written` callback is only called AFTER successful write per the SinkExecutor code (executors.py:1338-1340):

```python
# Call checkpoint callback for each token after successful write
if on_token_written is not None:
    for token in tokens:
        on_token_written(token)
```

So in the interleaved case:
- sink_a succeeds: checkpoints tok-0 (row 0), tok-2 (row 2)
- sink_b fails during write(): NO checkpoints for tok-1

Latest checkpoint: tok-2 with row_index=2
Recovery returns: rows with row_index > 2 = none

This IS a valid bug in the interleaved scenario!

### Re-Analysis: Is the Bug Valid?

Upon closer inspection, the bug IS valid but the description was misleading. Let me trace through a more accurate scenario:

**Scenario: Interleaved Routing**
- Row 0 -> sink_a
- Row 1 -> sink_b
- Row 2 -> sink_a

**Sink write order:**
1. sink_a.write([row 0, row 2]) - SUCCESS, checkpoints at row_index=0, row_index=2
2. sink_b.write([row 1]) - FAILS

**Recovery:**
- Latest checkpoint: row_index=2
- get_unprocessed_rows returns: rows with row_index > 2 = []
- Row 1 is LOST

This confirms the bug, but only in interleaved routing scenarios.

### However: Testing Evidence

Looking at the existing tests in `test_recovery.py`, there are tests for fork scenarios that pass:

```python
def test_fork_scenario_does_not_skip_unprocessed_rows(...)
    """Fork: Row 0 -> 3 tokens. Resume must process rows 1-4, not skip them."""
```

This test passes, which suggests the recovery logic works for the fork case. But the interleaved routing case is different.

### Final Assessment

Let me reconsider the claim more carefully:

The bug report says:
> "checkpoint order doesn't align with row_index across multiple sinks, causing resume to skip rows routed to a later/failed sink"

This describes a specific scenario where:
1. Rows are processed in order (0, 1, 2, 3, 4)
2. Some rows go to sink_a, some to sink_b
3. sink_a is written first, sink_b fails
4. If sink_b gets later rows AND sink_a gets earlier rows, the checkpoint boundary is correct
5. But if rows are interleaved between sinks, the bug manifests

Looking at the orchestrator code path for sink writing (orchestrator.py:939):

```python
for sink_name, tokens in pending_tokens.items():
```

The sink iteration order is arbitrary (dict iteration). If sink_a contains tokens [tok-0, tok-2] and sink_b contains [tok-1], and sink_a is written first:
- Checkpoint progression: tok-0 (row 0), tok-2 (row 2)
- Latest checkpoint: row_index=2
- sink_b fails on tok-1 (row 1)
- Recovery: rows > 2 = none
- Row 1 IS LOST

BUT wait - let me check if there's any ordering guarantee. The dict `pending_tokens` is created as:
```python
pending_tokens: dict[str, list[TokenInfo]] = {name: [] for name in config.sinks}
```

This iterates over config.sinks in insertion order. However, the token routing adds tokens to different sinks based on gate decisions, not in any guaranteed order within each sink's list.

### Actual Bug Location

The bug IS real but the description is slightly misleading. The actual issue is:

1. Tokens are written to sinks in SINK order (iterating over pending_tokens dict)
2. Within each sink, tokens are written in the order they were appended during row processing
3. Checkpoints are created after successful sink writes
4. The checkpoint boundary uses row_index from the token
5. If sink_a contains tokens from non-contiguous rows (e.g., rows 0 and 2) and sink_b contains row 1, and sink_b fails, row 1 is lost

## Revised Status: VERIFIED (Partial)

After deeper analysis, the bug IS valid but only manifests under specific conditions:

**Bug Condition:** Rows routed to different sinks in interleaved order (not contiguous blocks per sink)

**Example that triggers the bug:**
- Row 0 -> sink_a
- Row 1 -> sink_b
- Row 2 -> sink_a
- sink_a writes first, checkpoint at row_index=2
- sink_b fails
- Recovery skips row 1

**Example that does NOT trigger the bug:**
- Rows 0,1,2 -> sink_a
- Rows 3,4 -> sink_b
- sink_a writes first, checkpoint at row_index=2
- sink_b fails
- Recovery correctly processes rows 3,4

## Impact Assessment

| Factor | Assessment |
|--------|------------|
| Frequency | Low - requires interleaved sink routing |
| Severity | Critical when triggered - causes data loss |
| Detection | Hard to detect - run completes without error |
| Workaround | None without code fix |

## Recommended Fix

The proposed fix in the bug report is correct:
> "compute unprocessed rows by identifying tokens lacking a completed sink node_state"

Instead of using row_index boundary, query for rows whose tokens don't have completed sink node_states.

## Test Case to Add

```python
def test_interleaved_sink_routing_recovery():
    """Verify recovery handles interleaved sink routing.

    Scenario:
    - Row 0 -> sink_a
    - Row 1 -> sink_b
    - Row 2 -> sink_a
    - sink_a succeeds (rows 0, 2)
    - sink_b fails (row 1)

    Recovery must include row 1.
    """
    # Setup interleaved routing scenario
    # Force sink_b.write() to fail
    # Verify get_unprocessed_rows() returns row 1
```

---

## Final Verdict

| Aspect | Finding |
|--------|---------|
| **Bug Status** | **VERIFIED** (with clarification) |
| **Bug Description Accuracy** | Partially accurate - the issue is real but the specific scenario is interleaved routing, not just "later sink" |
| **Severity** | P1 is appropriate given potential data loss |
| **Priority** | High - auditability guarantee is violated |

The bug claim is **VERIFIED** with the clarification that it only manifests when rows are routed to different sinks in interleaved (non-contiguous) order. The current row_index boundary approach assumes sink writes preserve row ordering, which is violated when sinks receive non-contiguous subsets of rows.
