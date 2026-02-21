## Summary

`Operation` contract accepts impossible lifecycle states (e.g., `status="completed"` with missing `completed_at`/`duration_ms`), so corrupted Tier-1 operation records can be read and exported without crashing.

## Severity

- Severity: minor
- Priority: P2 (downgraded from P1 — defense-in-depth hardening for Tier 1 DB corruption, not an active failure mode since lifecycle states are set by our own code paths)

## Location

- File: /home/john/elspeth-rapid/src/elspeth/contracts/audit.py
- Line(s): 642-649
- Function/Method: `Operation.__post_init__`

## Evidence

`Operation.__post_init__` currently validates only enum-like membership:

```python
if self.operation_type not in self._ALLOWED_OPERATION_TYPES: ...
if self.status not in self._ALLOWED_STATUSES: ...
```

There is no lifecycle invariant validation tying `status` to required fields (`completed_at`, `duration_ms`, `error_message`, output fields).

Integration paths read DB rows directly into this dataclass with no extra checks:

- `src/elspeth/core/landscape/_call_recording.py:425-439`
- `src/elspeth/core/landscape/_call_recording.py:466-480`

Schema also has no conditional `CHECK` constraints for these lifecycle invariants:

- `src/elspeth/core/landscape/schema.py:229-247`

By contrast, `NodeState` does strict status-dependent invariant validation in repository load:

- `src/elspeth/core/landscape/repositories.py:281-367`

So operation records are currently less protected than other Tier-1 audit records.

## Root Cause Hypothesis

Contract hardening was applied to node-state reads but not to operations; `Operation` remained with only allowed-value checks and missed status-dependent invariant enforcement.

## Suggested Fix

Strengthen `Operation.__post_init__` in `audit.py` with status-dependent checks, for example:

- `status == "open"`: require `completed_at is None`, `duration_ms is None`, no terminal output/error fields.
- `status in {"completed","failed","pending"}`: require `completed_at` and `duration_ms`.
- `status == "failed"`: require `error_message` present.
- `status == "completed"`: require `error_message is None`.
- `status == "pending"`: enforce the intended pending semantics (no output or explicit allowed subset).

## Impact

Audit integrity guarantee is weakened: inconsistent operation records can silently pass through read/export paths, producing misleading forensic output instead of failing fast on Tier-1 corruption.
