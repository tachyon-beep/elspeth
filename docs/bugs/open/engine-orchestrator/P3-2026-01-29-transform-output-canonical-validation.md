# Enhancement: Enforce canonical-safe contract at transform output boundaries

## Summary

Transform outputs should be validated to ensure they are canonical-safe (JSON-serializable per ELSPETH's canonical JSON contract). Currently, the system relies on defensive `deepcopy()` in `TokenManager` to handle potential issues, but this masks plugin bugs rather than surfacing them.

By validating at the transform executor boundary, we:
1. Catch plugin bugs earlier with clear error messages
2. Potentially eliminate the need for defensive deepcopy (validated data is safe to copy)
3. Enforce the existing canonical JSON contract

## Severity

- Severity: minor (architectural enhancement)
- Priority: P3

## Reporter

- Name or handle: Claude Code (review board follow-up)
- Date: 2026-01-29
- Related run/issue ID: P2-2026-01-21-expand-token-shared-row-data

## Context

From the 4-perspective review board:

**Python Engineering Review:**
> "The fix must validate at transform output boundaries that row_data is canonical-safe"
> "True fix is enforcing canonical-safe contract at executor boundaries, not defensive copying"

**Architecture Review:**
> "If performance becomes a concern, the architecture could evolve toward immutable row data"

## Current State

1. `canonical_json()` in `src/elspeth/core/canonical.py` correctly rejects NaN, Infinity, and non-serializable types
2. This validation happens at **recording time** (when data goes to audit trail)
3. There's NO validation at **transform output time**
4. `TokenManager.expand_token()` and `fork_token()` use `deepcopy()` defensively

## Proposed Work

Add validation in transform executors (`src/elspeth/engine/executors.py`):

```python
# In TransformExecutor.execute_transform() after getting result:

def _validate_transform_output(self, row_data: dict[str, Any], transform_name: str) -> None:
    """Ensure transform output is canonical-safe.

    Raises PluginContractViolation if data cannot be serialized.
    """
    try:
        canonical_json(row_data)  # Rejects NaN/Inf/non-serializable
    except (TypeError, ValueError) as e:
        raise PluginContractViolation(
            f"Transform '{transform_name}' emitted non-canonical data: {e}"
        ) from e
```

**Apply to:**
- `TransformExecutor.execute_transform()` - single row output
- `AggregationExecutor.execute_flush()` - batch output
- Any path that creates `TransformResult` with row data

## Architectural Considerations

**Option A: Validate and keep deepcopy**
- Safest approach - belt and suspenders
- Extra overhead (serialize + deepcopy)

**Option B: Validate and remove deepcopy**
- If data is canonical-safe, it's guaranteed copyable
- Reduces overhead but requires careful analysis
- Deferred to future optimization

**Recommended: Option A first, consider Option B after benchmarking.**

## Acceptance Criteria

- [ ] Transform outputs validated for canonical-safe before token creation
- [ ] Clear error message when transform emits non-serializable data
- [ ] Test coverage for validation (transform returning non-serializable type)

## Trade-offs

**Pros:**
- Catches plugin bugs at source, not downstream
- Clearer error messages ("Transform X emitted non-canonical data" vs "deepcopy failed")
- Opens path to removing defensive deepcopy

**Cons:**
- Additional overhead per transform (one extra serialization)
- May surface latent bugs in existing pipelines (arguably a pro)

## Notes

This is an architectural enhancement to surface bugs earlier. The current deepcopy approach is **correct** - this improves the developer experience and enforcement.

## Verification (2026-02-01)

**Status: STILL VALID**

- Transform execution still proceeds from `transform.process()` straight to audit field population without canonical JSON validation. (`src/elspeth/engine/executors.py:245-337`)
