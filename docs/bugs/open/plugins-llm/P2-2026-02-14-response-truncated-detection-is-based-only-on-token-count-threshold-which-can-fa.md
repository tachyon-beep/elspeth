## Summary

`response_truncated` detection is based only on token-count threshold, which can falsely mark complete responses as truncated.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/azure_multi_query.py`
- Line(s): 268-285
- Function/Method: `_process_single_query`

## Evidence

Current logic flags truncation when:

- `completion_tokens >= effective_max_tokens`
- without checking model `finish_reason`

Code:

- `src/elspeth/plugins/llm/azure_multi_query.py:269-285`

But the response object already carries raw provider payload (`raw_response`) where `finish_reason` is available:

- `src/elspeth/plugins/clients/llm.py:44-49`
- `src/elspeth/plugins/clients/llm.py:335`
- `src/elspeth/plugins/clients/llm.py:389-395`

Tests verify `finish_reason` is present in captured raw responses (including `"length"`):

- `tests/unit/plugins/clients/test_audited_llm_client.py:538`
- `tests/unit/plugins/clients/test_audited_llm_client.py:608`

So this method has enough data to distinguish true truncation (`finish_reason == "length"`) from responses that merely used exactly `max_tokens`.

## Root Cause Hypothesis

Truncation detection was implemented as a heuristic on token counts and did not consume the available canonical truncation signal (`finish_reason`) from the raw response payload.

## Suggested Fix

In this file, use `response.raw_response` to inspect first-choice `finish_reason`; treat `"length"` as authoritative truncation signal. Keep token-count heuristic only as fallback when finish reason is unavailable.

## Impact

Valid responses can be incorrectly turned into `TransformResult.error(reason="response_truncated")`, causing avoidable row failures/quarantine, lower throughput, and misleading audit/error metrics.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/azure_multi_query.py.md`
- Finding index in source report: 2
- Beads: pending
