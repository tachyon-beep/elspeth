# Analysis: src/elspeth/core/landscape/exporter.py

**Lines:** 537
**Role:** Exports complete audit trail data for a run as flat dict records suitable for JSON/CSV/Parquet output. Supports HMAC signing for tamper-evident export packages. This is the compliance export path -- the data produced here may be submitted to legal or regulatory review.
**Key dependencies:** Imports `LandscapeDB`, `LandscapeRecorder`, `canonical_json`, and audit contract types (`NodeStateOpen`, `NodeStatePending`, `NodeStateCompleted`). Consumed by `engine/orchestrator/export.py` and accessible via `core/landscape/__init__.py`.
**Analysis depth:** FULL

## Summary

The exporter is well-structured and has already been refactored to fix the N+1 query problem (Bug 76r). The batch-query pre-loading pattern is sound. However, there are two concerns worth attention: (1) an N+1 query pattern remains in the batch/batch_member section that was not addressed by the Bug 76r fix, and (2) memory consumption for large runs is unbounded since all row-level data is loaded into dictionaries before iteration begins. The signing chain implementation is correct in design but has a subtle robustness issue around partial consumption of the generator.

## Warnings

### [468-491] Residual N+1 query pattern in batch members export

**What:** The Bug 76r fix pre-loaded tokens, token_parents, node_states, routing_events, and calls into batch queries. However, the batches section on lines 468-491 still performs per-batch queries for `get_batch_members(batch.batch_id)` inside a loop over all batches. This is the same N+1 pattern that was fixed elsewhere in the same method.

**Why it matters:** For pipelines that use aggregation heavily, a run could have hundreds or thousands of batches. Each batch triggers a separate database query for its members. While aggregation-heavy runs are less common than row-heavy runs, this is an inconsistency with the stated fix strategy and will cause performance degradation proportional to batch count.

**Evidence:**
```python
for batch in self._recorder.get_batches(run_id):
    yield { ... }
    # N+1 query - one per batch
    for member in self._recorder.get_batch_members(batch.batch_id):
        yield { ... }
```

The same `_iter_records` method has a prominent comment (line 156-157): "Bug 76r fix: Uses batch queries to pre-load all data, avoiding N+1 pattern." But batch members were not included in this fix.

### [272-306] Unbounded memory consumption from pre-loaded batch data

**What:** Lines 272-306 load ALL tokens, token_parents, node_states, routing_events, and calls for the entire run into in-memory dictionaries before yielding any row records. For large runs (hundreds of thousands of rows with multiple transform states each), this could consume significant memory.

**Why it matters:** The exporter is designed as a generator (`Iterator[dict]`) which suggests streaming intent, but the pre-loading defeats streaming for the row-level data. A run with 100K rows, each with 5 node states, 2 calls per state, and routing events would create dictionaries with hundreds of thousands of entries. This is a trade-off made intentionally (N+1 fix vs memory), but it is worth noting because the docstring and generator interface suggest streaming behavior.

**Evidence:**
```python
# These all load full result sets into memory
all_tokens = self._recorder.get_all_tokens_for_run(run_id)
all_parents = self._recorder.get_all_token_parents_for_run(run_id)
all_states = self._recorder.get_all_node_states_for_run(run_id)
all_routing_events = self._recorder.get_all_routing_events_for_run(run_id)
all_calls = self._recorder.get_all_calls_for_run(run_id)
```

### [130-151] Signing chain integrity depends on full generator consumption

**What:** The `export_run` method yields records with signatures and accumulates a running hash. The final manifest record (with `final_hash` and `record_count`) is only emitted at the end of iteration. If a consumer partially consumes the generator (e.g., stops after N records, encounters an error mid-stream, or breaks out of the loop), the manifest is never emitted and the signing chain is incomplete.

**Why it matters:** An incomplete signing chain without a manifest could be mistaken for a complete export by a downstream system that does not verify the manifest exists. The `record_count` in the manifest is the only way to verify completeness. A partial export file without a manifest looks like a valid JSONL file with signed records but no integrity envelope.

**Evidence:**
```python
for record in self._iter_records(run_id):
    if sign:
        record["signature"] = self._sign_record(record)
        running_hash.update(record["signature"].encode())
    record_count += 1
    yield record  # Consumer may stop here

# This only runs if generator is fully consumed
if sign:
    manifest = { ... "record_count": record_count, "final_hash": running_hash.hexdigest() ... }
    yield manifest
```

### [233-270] Operation-level calls fetched inside operation loop (residual N+1)

**What:** The operations section (lines 233-270) iterates over all operations for a run and for each operation calls `get_operation_calls(operation.operation_id)`. This is another N+1 query pattern not addressed by the Bug 76r fix. The Bug 76r fix explicitly notes it only covers "state-parented calls" (`get_all_calls_for_run`), but operation-parented calls still use per-operation queries.

**Why it matters:** Source and sink operations can make many external calls (e.g., a source loading from a paginated API). Each operation triggers a separate query.

**Evidence:**
```python
for operation in self._recorder.get_operations_for_run(run_id):
    yield { ... }
    # N+1 query per operation
    for call in self._recorder.get_operation_calls(operation.operation_id):
        yield { ... }
```

## Observations

### [344-428] Large repetitive code blocks for NodeState discriminated union

**What:** The four NodeState variant branches (lines 344-428) each construct a record dict with nearly identical field sets, differing only in which fields are set to `None`. This is approximately 85 lines of repetitive code.

**Why it matters:** Maintainability concern. If a new field is added to node states, it must be added in four places. The fact that BUG #9 comments appear in all four branches suggests this has already required coordinated multi-location edits.

### [507-537] `export_run_grouped` materializes entire export in memory

**What:** `export_run_grouped` calls `self.export_run(run_id, sign=sign)` and groups all records by type into a dict of lists. This materializes the entire export in memory, doubling the memory impact of the already-in-memory pre-loaded data.

**Why it matters:** For large runs this could cause memory pressure. The method is documented as useful for CSV export, which is a valid use case, but callers should be aware of the memory implications.

### [94-100] Canonical JSON for signing uses UTF-8 encoding assumption

**What:** The `_sign_record` method calls `canonical_json(record)` and then `.encode("utf-8")` on the result. This is correct -- RFC 8785 produces UTF-8 output -- but there is no explicit assertion that `canonical_json` always returns a string (as opposed to bytes). The dependency is implicit.

**Why it matters:** Minor robustness concern. If `canonical_json` ever changes to return bytes, the `.encode()` call would fail. This is low risk given the stable interface.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Address the residual N+1 query patterns in batch members (lines 468-491) and operation calls (lines 233-270) to bring them in line with the Bug 76r fix. Consider documenting the memory trade-off of the pre-loading strategy or adding a streaming alternative for very large runs. The signing chain incompleteness on partial consumption should be documented in the method's docstring at minimum.
**Confidence:** HIGH -- The code is well-documented, the patterns are clear, and the Bug 76r fix is explicitly commented. The residual N+1 patterns and memory implications are straightforward to verify.
