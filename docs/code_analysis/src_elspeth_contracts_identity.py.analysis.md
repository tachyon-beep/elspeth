# Analysis: src/elspeth/contracts/identity.py

**Lines:** 55
**Role:** Defines `TokenInfo`, the identity and data carrier for tokens flowing through the DAG execution engine. Tracks row identity (row_id), token identity (token_id), row data (PipelineRow), and lineage metadata (branch_name, fork_group_id, join_group_id, expand_group_id).
**Key dependencies:**
- Imports: `dataclasses.dataclass`, `dataclasses.replace` (stdlib); `PipelineRow` (TYPE_CHECKING only, from `schema_contract.py`)
- Imported by: `engine/tokens.py` (TokenManager), `engine/processor.py`, `engine/executors.py`, `engine/orchestrator/core.py`, `engine/coalesce_executor.py`, `engine/batch_adapter.py`, `contracts/__init__.py`, `plugins/context.py`, `plugins/batching/mixin.py`, `contracts/results.py`
**Analysis depth:** FULL

## Summary

This is a deliberately mutable dataclass (not frozen) that serves as the primary token carrier in the DAG execution engine. The design is intentional -- mutability is needed because token metadata evolves as tokens flow through the pipeline. The `with_updated_data()` method correctly uses `dataclasses.replace()` for creating updated copies. The main concern is that `TokenInfo` being non-frozen creates a risk of accidental mutation of identity fields (`row_id`, `token_id`) after audit recording, which would violate audit integrity. The test suite explicitly tests and documents this mutability. One warning about the mutability risk, several observations.

## Critical Findings

None.

## Warnings

### [15] TokenInfo is a non-frozen dataclass -- row_id and token_id can be silently overwritten

**What:** `TokenInfo` is declared as `@dataclass` without `frozen=True`. This means all fields, including `row_id` and `token_id`, can be reassigned after construction:

```python
token.row_id = "different_row"  # No error
token.token_id = "different_token"  # No error
```

The test at `test_identity.py:87-98` explicitly verifies and documents this mutability:
```python
def test_token_info_not_frozen(self) -> None:
    token.row_id = "new_row_id"
    assert token.row_id == "new_row_id"
```

**Why it matters:** While the comment on line 28 explains mutability is needed for `row_data` updates, and `with_updated_data()` exists for the safe update path, nothing prevents engine code from accidentally overwriting `row_id` or `token_id`. These are identity fields that link tokens to audit trail records. If a bug in processor or executor code overwrites `token.row_id`, the token would reference the wrong row in the audit trail, and the mismatch would be silent -- no exception, no log, no detection.

The codebase appears disciplined about this (no `token.row_id = ` assignments found in engine code; `with_updated_data` is used for data updates), but the safety relies entirely on developer discipline rather than language enforcement.

**Evidence:** No direct `row_data =` mutations were found in engine code (grep confirms this), and `TokenManager.update_row_data()` correctly uses `with_updated_data()`. However, the dataclass being non-frozen means any future code change could introduce silent identity mutation without type checker or runtime warnings.

A partial mitigation would be to use `__setattr__` to protect `row_id` and `token_id` while allowing other fields to be set. Or, making `TokenInfo` frozen and removing the mutability entirely since `with_updated_data()` already returns new instances.

### [39-55] `with_updated_data` uses `replace()` which creates a shallow copy

**What:** `dataclasses.replace()` creates a new `TokenInfo` with all fields shallow-copied, then the specified field(s) overwritten. For `PipelineRow`, this means the new `TokenInfo` holds a reference to the provided `new_data`, not a deep copy.

**Why it matters:** This is actually correct behavior. `PipelineRow` is internally immutable (backed by `MappingProxyType`), so sharing references is safe. The `TokenManager.fork_token()` method in `tokens.py` correctly uses `copy.deepcopy()` when creating forked children where independent mutations are needed. The `with_updated_data()` method does not need deep copy because it is replacing the data entirely, not forking.

## Observations

### [30-37] Lineage fields default to None -- no validation of field combinations

**What:** All lineage fields (`branch_name`, `fork_group_id`, `join_group_id`, `expand_group_id`) default to `None`. There is no validation that certain combinations are logically consistent. For example, having `fork_group_id` set but `branch_name` as `None` would be logically inconsistent (a forked token must have a branch name).

**Why it matters:** Low severity. This validation is the responsibility of `TokenManager` and `LandscapeRecorder`, which construct `TokenInfo` instances with correct field combinations. The dataclass itself is a simple carrier, not a domain validator. Adding invariant checks here would couple the data structure to engine logic.

### [33] Comment "CHANGED from dict[str, Any]" is historical

**What:** Line 33 has a comment `# CHANGED from dict[str, Any]` documenting that `row_data` was previously typed as a plain dict and is now `PipelineRow`.

**Why it matters:** Very low severity. Under the no-legacy-code policy, historical comments about what something used to be add clutter without value. The comment could be removed since it documents a past migration that is now complete.

### [6-7] Import of `dataclasses.replace` is explicit and correct

**What:** Both `dataclass` and `replace` are imported directly from `dataclasses`. This avoids the common mistake of calling `dataclasses.replace()` on a non-dataclass.

### [12] PipelineRow import is TYPE_CHECKING only

**What:** `PipelineRow` is imported under `TYPE_CHECKING` to avoid circular imports. At runtime, the type annotation is a string reference resolved lazily by type checkers.

**Why it matters:** This is a correct pattern. `identity.py` and `schema_contract.py` have a potential circular dependency (identity references PipelineRow, which is defined in schema_contract). The TYPE_CHECKING guard breaks the cycle correctly.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** The mutability of `row_id` and `token_id` is a latent risk. Consider either (a) making `TokenInfo` a frozen dataclass (since `with_updated_data` already returns new instances and no code mutates fields in place), or (b) adding a `__setattr__` guard that prevents overwriting `row_id` and `token_id` after construction. Remove the historical "CHANGED from dict" comment per no-legacy-code policy.
**Confidence:** HIGH -- the file is small (55 lines), well-tested (two dedicated test files), and the mutability concern is clearly documented in tests. The risk is real but currently mitigated by code discipline.
