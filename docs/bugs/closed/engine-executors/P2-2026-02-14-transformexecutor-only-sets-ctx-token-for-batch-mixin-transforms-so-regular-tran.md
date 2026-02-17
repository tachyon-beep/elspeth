## Summary

`TransformExecutor` only sets `ctx.token` for batch-mixin transforms, so regular transforms that use audited clients lose `token_id` telemetry correlation.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/engine/executors/transform.py`
- Line(s): `214-229`, `250-252`
- Function/Method: `TransformExecutor.execute_transform`

## Evidence

In executor:

- `ctx.token` is set only inside batch branch (`transform.py:226`).
- Regular branch calls `transform.process(...)` without setting `ctx.token` (`transform.py:250-252`).

A regular transform (`WebScrapeTransform`) passes token telemetry as optional:

- `src/elspeth/plugins/transforms/web_scrape.py:293` uses `ctx.token.token_id if ctx.token is not None else None`.

Audited HTTP telemetry uses that token directly:

- `src/elspeth/plugins/clients/http.py:388-401` emits `ExternalCallCompleted(... token_id=effective_token_id ...)` with no fallback lookup from `state_id`.

Project contract states telemetry correlation should include token IDs:

- `CLAUDE.md:526` (“Telemetry events include `run_id` and `token_id`.”)

## Root Cause Hypothesis

Executor context wiring treats token identity as batch-only state, but non-batch transforms also rely on `ctx.token` for telemetry correlation when using audited clients.

## Suggested Fix

Set `ctx.token = token` before both execution modes (batch and regular), not only in the batch branch. Keep batch behavior unchanged otherwise.

Add/extend tests to assert:

1. Regular transform receives non-`None` `ctx.token`.
2. External-call telemetry from a regular transform includes the active token ID.

## Impact

- External-call telemetry from regular transforms can emit `token_id=None`.
- Weakens cross-correlation between operational telemetry and Landscape lineage for affected plugins.

## Triage

- Status: open
- Source report: `docs/bugs/generated/engine/executors/transform.py.md`
- Finding index in source report: 2
- Beads: pending
