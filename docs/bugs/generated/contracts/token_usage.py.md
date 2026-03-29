## Summary

`TokenUsage.from_dict()` crashes on negative Tier 3 token counts, which can prevent completed LLM calls from being recorded at all.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/contracts/token_usage.py
- Line(s): 115-141
- Function/Method: TokenUsage.from_dict

## Evidence

`from_dict()` is documented as the only Tier 3 reconstruction path and is supposed to coerce malformed external values into `None`:

```python
133 raw_prompt = data.get("prompt_tokens")
134 raw_completion = data.get("completion_tokens")
138 prompt = raw_prompt if isinstance(raw_prompt, int) and not isinstance(raw_prompt, bool) else None
139 completion = raw_completion if isinstance(raw_completion, int) and not isinstance(raw_completion, bool) else None
141 return cls(prompt_tokens=prompt, completion_tokens=completion)
```

But `cls(...)` immediately runs `__post_init__`, which rejects negative ints via `require_int(..., min_value=0)` at `/home/john/elspeth/src/elspeth/contracts/token_usage.py:41-49`. So external input like `{"prompt_tokens": -1}` does not become “unknown”; it raises.

That matters because several success paths call `TokenUsage.from_dict()` before recording the completed call:

- `/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py:496-504`
- `/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py:506-527`
- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/azure_batch.py:1400-1414`
- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/openrouter_batch.py:717-723`
- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/providers/openrouter.py:266-275`

In the audited LLM client, usage parsing happens before `model_dump()` and before `record_call()` on the normal success path. A negative provider count therefore turns a completed external call into an uncaught local exception, skipping the audit write entirely.

The current tests cover non-int, bool, missing-key, and `total_tokens`-only inputs, but not negative Tier 3 values:
- `/home/john/elspeth/tests/unit/contracts/test_token_usage.py:145-190`

## Root Cause Hypothesis

`from_dict()` treats “Python int” as sufficient validity for external usage fields, but the contract’s own invariant is stricter: token counts must also be non-negative. Because the method forwards negative ints straight into the validating constructor, malformed Tier 3 data escapes the intended coercion path and becomes a hard exception.

## Suggested Fix

Make `from_dict()` validate semantic correctness at the Tier 3 boundary and coerce invalid counts to `None` before constructing `TokenUsage`.

Helpful shape:

```python
def _coerce_token_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0:
        return None
    return value
```

Then use that helper for both fields.

Add regression tests for:
- `{"prompt_tokens": -1, "completion_tokens": 5}` -> `prompt_tokens is None`
- `{"prompt_tokens": 5, "completion_tokens": -1}` -> `completion_tokens is None`
- verify the audited LLM client still records the call when usage contains negative counts

## Impact

A provider or SDK bug in usage metadata can create silent audit gaps: the LLM call happened, but no terminal call record is written because usage parsing crashes first. That violates the project’s “if it happened, it must be recorded” audit standard and can also abort otherwise recoverable batch/result processing.
---
## Summary

`TokenUsage.from_dict()` silently discards `total_tokens`-only provider usage, causing real usage data to disappear from `token_usage` telemetry and `*_usage` row fields.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/contracts/token_usage.py
- Line(s): 82-93, 115-141
- Function/Method: TokenUsage.to_dict / TokenUsage.from_dict

## Evidence

The contract only stores `prompt_tokens` and `completion_tokens`:

```python
38 prompt_tokens: int | None = None
39 completion_tokens: int | None = None
```

`from_dict()` ignores `total_tokens` entirely:
- `/home/john/elspeth/src/elspeth/contracts/token_usage.py:133-141`

The unit test explicitly locks that behavior in:
- `/home/john/elspeth/tests/unit/contracts/test_token_usage.py:176-178`

```python
usage = TokenUsage.from_dict({"total_tokens": 30})
assert usage == TokenUsage.unknown()
```

But real integration paths already encounter `total_tokens`-only payloads. Azure batch test fixtures feed responses like:

- `/home/john/elspeth/tests/unit/plugins/llm/test_azure_batch.py:1335-1336`

```json
{"usage": {"total_tokens": 10}}
```

Those responses are parsed through:

- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/azure_batch.py:1400-1414`

and row usage is populated via:

- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/__init__.py:131-134`

So provider-reported usage becomes `{}` in `llm_response_usage`, even though the provider did report a usable token count. The same loss affects `ExternalCallCompleted.token_usage`, since events serialize `TokenUsage.to_dict()`:
- `/home/john/elspeth/src/elspeth/contracts/events.py:427-428`

## Root Cause Hypothesis

The contract was designed around two counters and treated `total_tokens` as ignorable extra metadata. That assumption no longer matches integration reality: some providers/batch APIs report only aggregate totals. Because the contract cannot represent that shape, the parser collapses “known total only” into “unknown.”

## Suggested Fix

Extend `TokenUsage` to preserve aggregate-only usage instead of dropping it. The cleanest fix is to add an optional `total_tokens` field with invariants similar to the other counters.

Behavior should then be:

- `from_dict({"total_tokens": 30})` preserves `total_tokens=30`
- `to_dict()` emits `{"total_tokens": 30}` when only the total is known
- `total_tokens` property returns the explicit field when present, otherwise computes `prompt + completion` when both components are known

Add regression tests for `total_tokens`-only round-trips and for Azure batch responses that currently lose usage.

## Impact

Budget tracking, cost routing, and telemetry lose valid provider-reported usage in integrations that only emit aggregate totals. The raw response payload still contains the original data, so this is not a full audit-trail loss, but operational usage data becomes falsely “unknown” at the contract boundary.
