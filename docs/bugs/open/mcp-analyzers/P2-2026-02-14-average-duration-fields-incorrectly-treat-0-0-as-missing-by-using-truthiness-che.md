## Summary

Average-duration fields incorrectly treat `0.0` as missing by using truthiness checks, causing real zero-latency values to be reported as `None`.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/mcp/analyzers/reports.py`
- Line(s): `158`, `304`
- Function/Method: `get_run_summary`, `get_performance_report`

## Evidence

Current logic:

```python
"avg_state_duration_ms": round(avg_duration, 2) if avg_duration else None
...
"avg_ms": round(row.avg_ms, 2) if row.avg_ms else None
```

The engine records legitimate `duration_ms=0` for source states (`engine/processor.py`, lines `1146-1160`, `1220-1224`), so averages can be exactly `0.0`. Those get converted to `None` incorrectly.

## Root Cause Hypothesis

Truthy/falsy checks were used for null handling, conflating `0.0` with `None`.

## Suggested Fix

Use explicit `is not None` checks:

```python
round(avg_duration, 2) if avg_duration is not None else None
round(row.avg_ms, 2) if row.avg_ms is not None else None
```

## Impact

Reports understate measured performance data by showing “missing” instead of zero, which can mislead latency and bottleneck analysis.

## Triage

- Status: open
- Source report: `docs/bugs/generated/mcp/analyzers/reports.py.md`
- Finding index in source report: 4
- Beads: pending
