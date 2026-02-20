## Summary

Coalesce and aggregation timeout checks only fire when the next token arrives, not during genuine idle periods. This means aggregation buffers won't flush until a new row arrives or source completes, and coalesce pending groups won't timeout until the next token reaches the coalesce point.

## Severity

- Severity: low
- Priority: P3
- Type: bug
- Status: open
- Bead ID: elspeth-rapid-xys7

## Details

For streaming sources that may have long idle periods, this can cause unbounded delays. Documented in `system-operations.md` (lines 593, 769).

**Current workaround:** Combine timeouts with source-level heartbeat rows.

**Proper fix:** Background timer thread or asyncio task that periodically checks pending timeouts.

## Blocked By

- `w2q7` — ELSPETH-NEXT (deferred to post-RC3)

## Affected Subsystems

- `engine/coalesce_executor.py`
- `engine/triggers.py`
- `engine/orchestrator/`
