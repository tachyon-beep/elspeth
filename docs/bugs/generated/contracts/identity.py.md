## Summary

No concrete bug found in /home/john/elspeth/src/elspeth/contracts/identity.py

## Severity

- Severity: trivial
- Priority: P3

## Location

- File: /home/john/elspeth/src/elspeth/contracts/identity.py
- Line(s): 13-64
- Function/Method: TokenInfo; TokenInfo.__post_init__; TokenInfo.with_updated_data

## Evidence

`TokenInfo` is a small L0 contract that carries `row_id`, `token_id`, `row_data`, and fork/join metadata, with two explicit invariants enforced in `__post_init__`: non-empty `row_id` and `token_id` ([identity.py](/home/john/elspeth/src/elspeth/contracts/identity.py#L13)). `with_updated_data()` uses `dataclasses.replace()` to preserve lineage fields while swapping `row_data` ([identity.py](/home/john/elspeth/src/elspeth/contracts/identity.py#L48)).

I checked the main production construction paths:
- Initial source tokens are created from validated `SourceRow.to_pipeline_row()` before wrapping in `TokenInfo` ([tokens.py](/home/john/elspeth/src/elspeth/engine/tokens.py#L93)).
- Checkpoint restore for coalesce reconstructs `PipelineRow` first, then rebuilds `TokenInfo` with restored lineage fields ([coalesce_executor.py](/home/john/elspeth/src/elspeth/engine/coalesce_executor.py#L272)).

I also checked the direct unit coverage for this file:
- Creation, branch metadata, empty-ID rejection, frozen behavior, and lineage preservation through `with_updated_data()` are all tested in [test_identity.py](/home/john/elspeth/tests/unit/contracts/test_identity.py#L18).

I did not find a verified mismatch where the primary fix belongs in `identity.py`.

## Root Cause Hypothesis

No bug identified.

## Suggested Fix

Unknown.

## Impact

No confirmed breakage from `src/elspeth/contracts/identity.py` based on the audited code paths and tests.
