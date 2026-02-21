# Core Checkpoint Triage Notes

**Triaged:** 2026-02-14
**Scope:** `docs/bugs/open/core-checkpoint/` (3 findings from static analysis)
**Source code reviewed:** All 5 files in `src/elspeth/core/checkpoint/`

## Summary

| # | File | Original | Triaged | Verdict |
|---|------|----------|---------|---------|
| 1 | `P1-...-checkpoint-loads-corrupts-valid-user-data-by-treating-datetime-shaped-dicts.md` | P1 | **P1 confirmed** | Real bug, well-documented, data corruption risk |
| 2 | `P2-...-checkpoint-row-corruption-in-checkpointmanager-is-surfaced-as-a-generic-valueerr.md` | P2 | **P3 downgrade** | Valid but purely diagnostic — crash behavior is correct per trust model |
| 3 | `P2-...-get-unprocessed-row-data-promises-valueerror-on-schema-validation-failure-but-cu.md` | P2 | **CLOSE (false positive)** | `pydantic.ValidationError` inherits from `ValueError` — contract is NOT violated |

## Detailed Assessment

### Finding 1: `__datetime__` tag collision — CONFIRMED P1

**Verdict: Real bug. P1 confirmed.**

The static analysis correctly identified that `_restore_types()` in `serialization.py:124` uses
shape-based detection (`"__datetime__" in obj and len(obj) == 1 and isinstance(obj["__datetime__"], str)`)
which collides with user data in aggregation checkpoints.

**Validated claims:**
- `aggregation.py:627` stores `t.row_data.to_dict()` — user pipeline data flows into checkpoint state
- `checkpoint_dumps()` serializes this via `CheckpointEncoder` — no escaping of user dicts
- `checkpoint_loads()` → `_restore_types()` matches user data by shape alone
- Property tests at `test_checkpoint_serialization_properties.py:77` explicitly filter `__datetime__` keys
  from generated data, confirming the team was aware but suppressed the collision in tests rather than fixing it

**Impact confirmed:**
1. **Silent data corruption:** `{"__datetime__": "2024-01-01T00:00:00+00:00"}` in user data → restored as `datetime` object instead of dict
2. **Resume crash:** `{"__datetime__": "not-a-date"}` in user data → `ValueError` from `fromisoformat()`
3. Violates round-trip fidelity guarantee that checkpoints promise

**Fix approach (from bug report is sound):** Use collision-safe envelope, e.g. a reserved prefix
that gets escaped if it appears in user data. The simplest approach: during encode, scan user dicts
for the reserved key and escape them; during decode, reverse the escaping after type tag restoration.

### Finding 2: `CheckpointCorruptionError` not raised — DOWNGRADED to P3

**Verdict: Valid observation, but downgraded from P2 to P3.**

The analysis is technically correct — `Checkpoint.__post_init__` at `audit.py:408-411` raises bare
`ValueError` when `upstream_topology_hash` or `checkpoint_node_config_hash` are empty, and
`CheckpointManager.get_latest_checkpoint()` does not wrap this in `CheckpointCorruptionError`.

However, this is **correct behavior per CLAUDE.md's trust model:**

> "Bad data in the audit trail = crash immediately"

Checkpoint data is Tier 1 (our data). If the database contains empty hash fields, that IS corruption,
and crashing with `ValueError` is the right thing to do. The `CheckpointCorruptionError` exception
exists and would provide better diagnostic context (run_id, checkpoint_id attribution), but the
current crash-on-corruption behavior is not *wrong* — it's just less informative.

**Why not P2:**
- No data integrity risk (crash is the correct response)
- No behavioral difference (corruption still crashes the process)
- Only diagnostic quality improvement (better exception type + context)
- Edge case requiring actual database corruption to trigger

**Recommended fix (P3):** Simple try/except wrapping as the bug report suggests. Low effort, low risk.

### Finding 3: `get_unprocessed_row_data` leaks `ValidationError` — CLOSED (false positive)

**Verdict: False positive. The contract is NOT violated.**

The bug report claims the docstring promises `ValueError` but `pydantic.ValidationError` is raised
instead. This would be a contract violation IF `ValidationError` were a separate exception type.

**However, `pydantic.ValidationError` inherits from `ValueError`:**

```
ValidationError.__mro__ = (ValidationError, ValueError, Exception, BaseException, object)
```

This means:
- Any `except ValueError` handler WILL catch `ValidationError`
- The docstring's promise of `ValueError` is technically satisfied
- Callers relying on `ValueError` semantics are not broken

The missing `row_id` context in the error message is a minor improvement opportunity (P4 at best),
but the core claim of the bug report — that the exception contract is violated — is incorrect.

**Action: Close as false positive.** Updated description below.

## Actions Taken

1. **Finding 1:** Confirmed P1, no changes to bug file needed (analysis is thorough and accurate)
2. **Finding 2:** Downgraded from P2 → P3 (updated in bug file)
3. **Finding 3:** Closed as false positive (file to be removed from open/)
