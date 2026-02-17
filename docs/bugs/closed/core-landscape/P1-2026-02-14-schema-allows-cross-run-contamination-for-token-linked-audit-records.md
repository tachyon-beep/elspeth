## Summary

`schema.py` allows cross-run contamination for token-linked audit records because it does not enforce that `token_id` and `run_id` belong to the same run in `token_outcomes` and `transform_errors`.

## Severity

- Severity: major
- Priority: P3 (downgraded from P1 — theoretical; tokens.run_id column missing but all callers maintain consistency)

## Location

- File: /home/john/elspeth-rapid/src/elspeth/core/landscape/schema.py
- Line(s): 131-142, 146-153, 434-450
- Function/Method: module-level table definitions (`tokens_table`, `token_outcomes_table`, `transform_errors_table`)

## Evidence

`tokens` has no `run_id` column (`schema.py:131-142`), so downstream tables cannot enforce token↔run ownership.

`token_outcomes` stores both `run_id` and `token_id`, but they are independent FKs (`schema.py:151-153`) rather than a coupled FK proving token ownership for that run.

`transform_errors` has the same issue: independent FK to `runs` plus FK to `tokens` (`schema.py:438-439`), with no token↔run coupling (`schema.py:447-450` only couples transform node to run).

Writers trust caller-supplied IDs:
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_token_recording.py:562-566`
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_error_recording.py:163-165`

Verified in-memory repro (current code):
- Recording `tok-A` (created in `run-A`) as outcome in `run-B` succeeds.
- `get_token_outcomes_for_row('run-A','row-A')` returns `[]`, while `get_token_outcomes_for_row('run-B','row-A')` returns `[('run-B','tok-A','completed')]`.
- Recording transform error with `run_id='run-B'`, `token_id='tok-A'` succeeds, and `get_transform_errors_for_token('tok-A')` returns the `run-B` error.

Run-scoped recovery logic depends on `token_outcomes.run_id` filtering (`/home/john/elspeth-rapid/src/elspeth/core/checkpoint/recovery.py:342-370`), so this misattributes completion state.

## Root Cause Hypothesis

The schema denormalizes `run_id` into token-linked tables but does not provide a relational invariant that ties those rows back to the token's true run. Because `tokens` lacks `run_id`, SQL constraints cannot currently enforce token/run consistency.

## Suggested Fix

Introduce schema-level run ownership for tokens, then enforce composite FKs from token-linked tables:

- Add `run_id` to `tokens_table` and enforce token-row consistency (e.g., composite FK to `rows` with matching run).
- Add a composite uniqueness target for tokens (e.g., `(token_id, run_id)`).
- Change `token_outcomes` to use composite FK `(["token_id", "run_id"] -> ["tokens.token_id", "tokens.run_id"])`.
- Change `transform_errors` similarly for token ownership.
- Add migration/backfill for existing rows (derive token `run_id` via `tokens.row_id -> rows.run_id`).

## Impact

Audit integrity can be silently corrupted across runs:
- terminal outcomes can be recorded under the wrong run,
- transform errors can appear in lineage for the wrong run/token context,
- run-scoped recovery and explain workflows can make incorrect decisions from contaminated records.

## Triage

Triage: Downgraded P1→P3. Same root cause as record-transform-error-wrong-run and token-lifecycle bugs. Schema migration to add tokens.run_id is a large change for a theoretical issue. Track as single schema-hardening item.
