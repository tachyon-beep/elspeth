## Summary

`explain()` performs an incomplete/unsafe parent-lineage integrity check, so malformed token lineage states can pass silently instead of crashing.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1 — truthiness vs is-not-None; empty string scenario requires DB corruption)

## Location

- File: /home/john/elspeth-rapid/src/elspeth/core/landscape/lineage.py
- Line(s): 168-171
- Function/Method: explain

## Evidence

In `explain()`, parent consistency is validated with a truthy shortcut and only one direction:

```python
has_group_id = token.fork_group_id or token.join_group_id or token.expand_group_id
if has_group_id and not parents:
    ...
```

(`/home/john/elspeth-rapid/src/elspeth/core/landscape/lineage.py:168-171`)

What it does now:
- Only checks `group_id -> parents`.
- Treats empty string group IDs as "no group" (falsy), so corrupted values like `""` bypass the check.
- Does not validate inverse invariant (`parents -> group_id`) or invalid multi-group states.

Why this is reachable:
- Group-ID fields are nullable strings with no non-empty constraint in schema (`/home/john/elspeth-rapid/src/elspeth/core/landscape/schema.py:136-138`).
- Token/outcome writers validate `None` but not empty strings (`/home/john/elspeth-rapid/src/elspeth/core/landscape/_token_recording.py:144-146`, `/home/john/elspeth-rapid/src/elspeth/core/landscape/_token_recording.py:465-496`).

Expected behavior (Tier-1 audit data): malformed lineage metadata should crash explicitly, not be silently accepted.

## Root Cause Hypothesis

The integrity guard was implemented as a convenience truthiness check (`or` chain) instead of strict invariant validation of lineage metadata (None vs invalid value, bidirectional consistency, exclusivity of group IDs).

## Suggested Fix

In `explain()`:
- Replace truthy checks with explicit `is not None` checks.
- Reject empty-string group IDs as audit corruption.
- Enforce both directions:
  - if any group ID is set, parents must exist;
  - if parents exist, exactly one lineage group ID should be set.
- Raise `ValueError` (or `AuditIntegrityError`) on violations.

Example shape:

```python
group_ids = {
    "fork": token.fork_group_id,
    "join": token.join_group_id,
    "expand": token.expand_group_id,
}
set_groups = [k for k, v in group_ids.items() if v is not None]
if any(v == "" for v in group_ids.values() if v is not None):
    raise ValueError("Audit integrity violation: empty group_id")
if len(set_groups) > 1:
    raise ValueError("Audit integrity violation: multiple group_ids set")
if set_groups and not parents:
    raise ValueError("...group_id set but no token_parents...")
if parents and not set_groups:
    raise ValueError("...token_parents exist but no group_id...")
```

## Impact

Lineage corruption can be hidden:
- tokens with malformed group metadata may appear valid,
- parent-token lineage can be incomplete without a hard failure,
- audit guarantees ("crash on Tier-1 anomalies", complete lineage reconstructability) are weakened.

## Triage

Triage: Downgraded P1→P2. Write path sets group IDs from UUID-based engine code (never empty strings). Empty-string scenario requires direct DB manipulation. Fix is warranted for Tier 1 correctness but not urgent.
