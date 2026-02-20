## Summary

Add DIVERT+coalesce safety warning when branch-specific transforms ship. The dead `warn_divert_coalesce_interactions()` was deleted from `dag.py` because it could never fire — it searched continue-labeled edges, but fork-to-coalesce uses branch-labeled COPY edges. The current architecture has no intermediate transforms between fork gates and coalesces.

## Severity

- Severity: moderate
- Priority: P2
- Type: task
- Status: in_progress
- Bead ID: elspeth-rapid-xqdj

## Details

When branch-specific transforms (elspeth-rapid-ya3x) are implemented, this safety check must be reimplemented correctly: detect DIVERT transforms on branch paths that feed `require_all` coalesces. The new implementation must include positive test cases (the deleted version had zero).

The 4-perspective review board found the algorithm's directionality was wrong — transforms are upstream of fork, not between fork and coalesce.

## Depends On

- `ya3x` — Branch-specific inline transforms for fork/coalesce paths (P4 feature)

## Affected Subsystems

- `core/dag/`
