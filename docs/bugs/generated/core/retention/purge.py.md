## Summary

`find_expired_payload_refs()` can purge blobs still needed by old `INTERRUPTED` runs when those blobs are content-addressable and shared with an expired completed/failed run.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/core/retention/purge.py`
- Line(s): 164-179
- Function/Method: `find_expired_payload_refs`

## Evidence

`find_expired_payload_refs()` treats only `completed` and `failed` runs as purge-eligible:

```python
run_expired_condition = and_(
    runs_table.c.status.in_(("completed", "failed")),
    runs_table.c.completed_at.isnot(None),
    runs_table.c.completed_at < cutoff,
)
```

It then protects shared refs only if they appear in the “active” set:

```python
run_active_condition = or_(
    runs_table.c.completed_at >= cutoff,
    runs_table.c.completed_at.is_(None),
    runs_table.c.status == "running",
)
...
safe_to_delete = expired_refs - active_refs
```

Source: [/home/john/elspeth/src/elspeth/core/retention/purge.py:164](/home/john/elspeth/src/elspeth/core/retention/purge.py#L164), [/home/john/elspeth/src/elspeth/core/retention/purge.py:175](/home/john/elspeth/src/elspeth/core/retention/purge.py#L175), [/home/john/elspeth/src/elspeth/core/retention/purge.py:231](/home/john/elspeth/src/elspeth/core/retention/purge.py#L231)

Old `INTERRUPTED` runs match neither set:
- not purge-eligible, because status is not `completed`/`failed`
- not active, because old interrupted runs have `completed_at < cutoff`, `completed_at is not None`, and `status != "running"`

That matters because interrupted runs are resumable:

```python
if run.status == RunStatus.COMPLETED:
    return ResumeCheck(can_resume=False, reason="Run already completed successfully")

if run.status == RunStatus.RUNNING:
    return ResumeCheck(can_resume=False, reason="Run is still in progress")

# Any other status (FAILED, INTERRUPTED) is eligible for resume
```

Source: [/home/john/elspeth/src/elspeth/core/checkpoint/recovery.py:112](/home/john/elspeth/src/elspeth/core/checkpoint/recovery.py#L112)

Resume requires the original row payload blob. If that blob was purged, resume fails:

```python
if source_data_ref is None:
    raise AuditIntegrityError(...)

try:
    payload_bytes = payload_store.retrieve(source_data_ref)
except PayloadNotFoundError as exc:
    raise ValueError(
        f"Row {row_id} payload has been purged (hash={exc.content_hash}) - cannot resume"
    ) from exc
```

Source: [/home/john/elspeth/src/elspeth/core/checkpoint/recovery.py:257](/home/john/elspeth/src/elspeth/core/checkpoint/recovery.py#L257)

There is a regression test for unique interrupted-run refs not being returned, but no coverage for the shared-ref case:

Source: [/home/john/elspeth/tests/unit/core/retention/test_purge.py:698](/home/john/elspeth/tests/unit/core/retention/test_purge.py#L698)

What the code does:
- Deletes a ref if it appears in expired completed/failed runs and not in `active_refs`.

What it should do:
- Also keep any ref that is still referenced by resumable interrupted runs, even if those runs are older than the retention cutoff.

## Root Cause Hypothesis

The file correctly fixed the earlier bug “do not purge interrupted runs directly,” but the anti-join logic still models “protected runs” as only recent/incomplete/running runs. Because payloads are content-addressable and shared across runs, interrupted runs must also be part of the protected set. The implementation split “purge-eligible” and “protect shared refs” into different predicates, and only the first predicate was updated for interrupted runs.

## Suggested Fix

Include `INTERRUPTED` runs in the protected/shared-ref predicate. For example, treat them as active for anti-join purposes:

```python
run_active_condition = or_(
    runs_table.c.completed_at >= cutoff,
    runs_table.c.completed_at.is_(None),
    runs_table.c.status.in_(("running", "interrupted")),
)
```

A tighter version would explicitly model “protected runs” as:
- all `running`
- all `interrupted`
- any run within retention

Add a regression test where:
1. an old `COMPLETED` run references payload ref `X`
2. an old `INTERRUPTED` run also references payload ref `X`
3. `find_expired_payload_refs()` must not return `X`

## Impact

Purging can silently remove blobs still required for checkpoint resume of interrupted runs. That breaks resume with `PayloadNotFoundError`/`ValueError`, despite the interrupted run still being a valid recovery candidate. Operationally, this causes irreversible data loss for recovery paths; audit hashes remain, but the system loses the payloads needed to continue the run.
