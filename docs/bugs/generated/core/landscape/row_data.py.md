## Summary

No concrete bug found in /home/john/elspeth/src/elspeth/core/landscape/row_data.py

## Severity

- Severity: trivial
- Priority: P3

## Location

- File: /home/john/elspeth/src/elspeth/core/landscape/row_data.py
- Line(s): 1-150
- Function/Method: RowDataResult.__post_init__; CallDataResult.__post_init__

## Evidence

`row_data.py` enforces the advertised discriminated-union invariants: data-bearing states require non-`None` mapping payloads, non-data states require `None`, and payloads are deep-frozen for immutability ([row_data.py](/home/john/elspeth/src/elspeth/core/landscape/row_data.py#L48), [row_data.py](/home/john/elspeth/src/elspeth/core/landscape/row_data.py#L107)).

Those invariants match the runtime producers:
- `QueryRepository.get_row_data()` only constructs `ROW_NOT_FOUND`, `NEVER_STORED`, `STORE_NOT_CONFIGURED`, `PURGED`, `AVAILABLE`, and `REPR_FALLBACK` in combinations accepted by `RowDataResult` ([query_repository.py](/home/john/elspeth/src/elspeth/core/landscape/query_repository.py#L186)).
- `ExecutionRepository.get_call_response_data()` only constructs `CALL_NOT_FOUND`, `HASH_ONLY`, `NEVER_STORED`, `STORE_NOT_CONFIGURED`, `PURGED`, and `AVAILABLE` in combinations accepted by `CallDataResult` ([execution_repository.py](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L974)).

Consumers handle the explicit states rather than assuming raw `None` semantics:
- replay path ([replayer.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/replayer.py#L218))
- verification path ([verifier.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/verifier.py#L324))

Tests cover the target file’s core contract and integration behavior:
- direct invariant/unit tests ([test_row_data.py](/home/john/elspeth/tests/unit/core/landscape/test_row_data.py#L13))
- property tests over all state/data combinations ([test_row_data_properties.py](/home/john/elspeth/tests/property/core/test_row_data_properties.py#L86))
- integration tests for recorder/query behavior and Tier 1 corruption handling ([test_recorder_row_data.py](/home/john/elspeth/tests/integration/audit/test_recorder_row_data.py#L19))

## Root Cause Hypothesis

No bug identified

## Suggested Fix

No code change recommended in /home/john/elspeth/src/elspeth/core/landscape/row_data.py based on this audit.

## Impact

No verified breakage found in the target file. The explicit-state API, immutability guard, and producer/consumer integration all appear consistent with the repository’s audit-trail and Tier 1 integrity requirements.
