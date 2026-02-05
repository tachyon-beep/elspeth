# Analysis: src/elspeth/engine/tokens.py

**Lines:** 382
**Role:** High-level token lifecycle management for the SDA engine. Provides operations for creating initial tokens from source rows, forking tokens to parallel DAG branches, coalescing tokens from joins, expanding tokens for deaggregation (1-to-N), and updating row data after transforms. Acts as a facade over LandscapeRecorder for token-related audit trail operations.
**Key dependencies:**
- Imports: `copy`, `LandscapeRecorder`, `SourceRow`, `TokenInfo`, `PipelineRow`, `SchemaContract`, `PayloadStore` (TYPE_CHECKING)
- Imported by: `engine/processor.py`, `engine/coalesce_executor.py`, `engine/orchestrator/core.py`, `engine/executors.py` (TYPE_CHECKING), `engine/__init__.py`
**Analysis depth:** FULL

## Summary

TokenManager is well-structured with clear separation of concerns. The most significant finding is a missing invariant assertion in `coalesce_tokens` where `parents[0].row_id` is used with only a comment ("they should all be the same") but no runtime validation. In an audit-critical system, this assumption must be verified. There is also a contract validation ordering issue in `expand_token` where the DB write occurs before the contract lock check, meaning a crash on unlocked contracts leaves orphaned audit records. Overall confidence is HIGH -- the file is well-written with good deepcopy discipline for fork/expand safety.

## Critical Findings

### [277-278] coalesce_tokens assumes all parent row_ids are identical without validation

**What:** The `coalesce_tokens` method takes `parents[0].row_id` with the comment "they should all be the same" but never validates this invariant. If parent tokens from different source rows are coalesced (due to a bug in the coalesce executor or a misconfigured DAG), the audit trail would silently record the wrong `row_id` for the merged token.

**Why it matters:** This is the audit trail backbone. If a coalesce operation merges tokens from different source rows under one `row_id`, the lineage for the merged token is corrupted. An auditor tracing a token back to its source row would get the wrong source data. Per the project's auditability standard: "I don't know what happened" is never acceptable, and silent corruption is worse than a crash.

**Evidence:**
```python
# Line 277-278
# Use first parent's row_id (they should all be the same)
row_id = parents[0].row_id
```
No assertion or guard verifies that `all(p.row_id == parents[0].row_id for p in parents)`. The recorder's `coalesce_tokens` also does not appear to validate this. If the CoalesceExecutor has a bug that presents tokens from different rows, the corruption propagates silently into the audit database.

Additionally, if `parents` is an empty list, `parents[0]` raises `IndexError`. While the caller (CoalesceExecutor) is expected to only call with non-empty lists, there is no guard here.

## Warnings

### [343-358] expand_token performs DB write before contract lock validation

**What:** In `expand_token`, the recorder's `expand_token` (which performs database inserts for child tokens and potentially records the parent EXPANDED outcome) is called at line 344 before the contract lock check at line 354. If the output contract is not locked, the `ValueError` at line 355 is raised after orphaned audit records have already been written to the database.

**Why it matters:** The DB operations in `recorder.expand_token` are described as ATOMIC (per the docstring), but the subsequent crash from the unlocked contract means the audit trail contains child tokens whose parent may or may not have the EXPANDED outcome recorded (depending on `record_parent_outcome`). These orphaned records could confuse the lineage chain.

**Evidence:**
```python
# Line 344-351: DB write happens first
db_children, expand_group_id = self._recorder.expand_token(
    parent_token_id=parent_token.token_id,
    row_id=parent_token.row_id,
    count=len(expanded_rows),
    run_id=run_id,
    step_in_pipeline=step_in_pipeline,
    record_parent_outcome=record_parent_outcome,
)

# Line 354-358: Contract check happens AFTER DB write
if not output_contract.locked:
    raise ValueError(
        f"Output contract must be locked before token expansion. "
        ...
    )
```
The validation should precede the database write.

### [204-256] fork_token deepcopy operates on potentially large row data

**What:** `fork_token` performs `copy.deepcopy(data)` for each branch (line 250). For wide rows with deeply nested structures or large blob references, this creates N full copies where N is the number of branches. There is no size guard or warning threshold.

**Why it matters:** In production with many-branch forks (e.g., 10+ paths) and wide row data, this could cause significant memory pressure. The same applies to `expand_token` (line 372) where the number of expanded rows could be much larger (aggregation output).

**Evidence:**
```python
# Line 246-255 - deepcopy per branch
child_infos = [
    TokenInfo(
        row_id=parent_token.row_id,
        token_id=child.token_id,
        row_data=copy.deepcopy(data),  # Full deep copy per branch
        ...
    )
    for child in children
]
```
The comment at line 243 correctly explains WHY deepcopy is needed (preventing cross-branch mutation leaks), but there's no bound on the size or count.

## Observations

### [113-176] create_quarantine_token has inline import of SchemaContract

**What:** Line 150 imports `SchemaContract` from `elspeth.contracts.schema_contract` despite it already being imported at line 19 at the module level.

**Why it matters:** This is a minor redundancy. The module-level import at line 19 already provides `SchemaContract`. The inline import is unnecessary and suggests the function may have been written or moved independently.

### [64-111] create_initial_token correctly guards against missing contracts

**What:** The guard at line 90-91 enforces that `source_row.contract is not None` before creating tokens. This is consistent with the trust model (source rows that pass validation must have contracts).

**Why it matters:** Positive observation -- this guard prevents uncontracted data from entering the pipeline, which would corrupt downstream schema propagation.

### [178-202] create_token_for_existing_row has no validation

**What:** This method creates a token for a pre-existing row during resume, but does not validate that the row_id actually exists in the database. If the checkpoint data is corrupted and references a nonexistent row_id, the token is created with a dangling reference.

**Why it matters:** During resume from checkpoint, corrupted state could lead to tokens referencing rows that don't exist. However, per the trust model, checkpoint data is "our data" (Tier 1), so corruption should crash. The lack of validation here means it won't crash -- it will silently create an orphaned token.

### [10] __all__ re-exports TokenInfo from contracts

**What:** Line 10 declares `__all__ = ["TokenInfo", "TokenManager"]` but `TokenInfo` is imported from `elspeth.contracts`. This re-export creates an alternate import path for `TokenInfo`.

**Why it matters:** Minimal impact, but consumers should import `TokenInfo` from `elspeth.contracts.identity` or `elspeth.contracts`, not from `elspeth.engine.tokens`. This re-export could lead to import confusion.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Add an assertion in `coalesce_tokens` validating that all parent row_ids match and that the parents list is non-empty. This is the highest priority as it directly protects audit trail integrity. (2) Move the contract lock check in `expand_token` to before the database write. (3) Consider whether `create_token_for_existing_row` should validate row existence against the recorder.
**Confidence:** HIGH -- All code paths were fully analyzed with cross-reference to callers in processor.py and coalesce_executor.py. The coalesce row_id assumption was verified to be unguarded in both TokenManager and its callers.
