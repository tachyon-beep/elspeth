# Core Retention Triage Notes

**Triaged:** 2026-02-14
**Scope:** `docs/bugs/open/core-retention/` (2 findings)

## Summary

| # | File | Original | Triaged | Verdict |
|---|------|----------|---------|---------|
| 1 | `P1-...-find-affected-run-ids-can-fail-with-sqlite-too-many-sql-variables.md` | P1 | **P1 confirmed** | Real — crash after partial purge leaves inconsistent state |
| 2 | `P2-...-expiration-logic-purges-interrupted-runs.md` | P2 | **P1 upgrade** | Silent irreversible data loss breaking resume |

## Detailed Assessment

### Finding 1: `_find_affected_run_ids` unbounded IN — CONFIRMED P1

**Verdict: Confirmed P1.**

The code at `purge.py:352-403` builds 8 separate queries each using `refs_set` directly in
`.in_()` clauses with no chunking. SQLite's `SQLITE_MAX_VARIABLE_NUMBER` defaults to 999.

The critical ordering problem: `purge_payloads()` deletes blobs FIRST, then calls
`_find_affected_run_ids()` to determine which runs need grade updates. If the IN clause
crashes on a large `refs_set`, the blobs are already deleted but grades remain stale —
runs still claim "reproducible" when their payloads are gone.

The codebase already has the chunking pattern (`recovery.py:32-34`, `_METADATA_CHUNK_SIZE = 500`).
The fix is to apply the same pattern here.

### Finding 2: Expiration purges interrupted runs — UPGRADED to P1

**Verdict: Upgraded from P2 to P1. Silent irreversible data loss.**

The purge filter at `purge.py:145-149` uses `status != "running"` — a negative predicate that
catches INTERRUPTED alongside COMPLETED and FAILED. The code's own comments (lines 89-90, 143-144)
say "completed and failed runs are eligible" but the implementation is broader.

**Why P1:**
1. `INTERRUPTED` runs are explicitly resumable — `orchestrator/core.py:869-871` and `:1953-1955`
   set `RunStatus.INTERRUPTED` with the comment "resumable via `elspeth resume`"
2. Resume requires payloads — `recovery.py:243` raises ValueError "payload has been purged"
3. Purging is **irreversible** — once blobs are deleted, there's no recovery
4. **No warning** — the user's interrupted run silently becomes non-resumable
5. The code **contradicts its own documentation** — comments say "completed and failed only"

**Temporal exposure:** Requires `retention_days` to elapse while the run stays INTERRUPTED.
Short retention + delayed resume = silent data loss. This is plausible in production.

**Fix:** Replace the negative predicate with an explicit allowlist:
```python
_PURGE_ELIGIBLE_STATUSES = ("completed", "failed")
runs_table.c.status.in_(_PURGE_ELIGIBLE_STATUSES)
```
