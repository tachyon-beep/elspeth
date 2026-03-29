## Summary

`chat_completion()` drops real LLM calls on the floor when the provider returns an empty `choices` array: it raises `LLMClientError` before writing any `calls` row.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py`
- Line(s): 281, 390-394
- Function/Method: `AuditedLLMClient.chat_completion`

## Evidence

`call_index` is allocated up front, proving the client has already committed to recording a call:

```python
call_index = self._next_call_index()
```

But if the SDK returns `response.choices = []`, the code immediately raises:

```python
if not response.choices:
    raise LLMClientError(
        "LLM returned empty choices array — abnormal response",
        retryable=False,
    )
```

There is no preceding `self._recorder.record_call(...)` on this branch, unlike the nearby `model_dump()` and null-content branches, which explicitly record an `ERROR` call before raising ([llm.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py):406-454, [llm.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py):509-531). `record_call()` is the mechanism that persists the legal audit entry ([execution_repository.py](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py):560-639).

The current test only verifies the exception, not audit persistence ([test_audited_llm_client.py](/home/john/elspeth/tests/unit/plugins/clients/test_audited_llm_client.py):985-991).

## Root Cause Hypothesis

The success-path validation for malformed Tier 3 responses was moved outside the SDK `try/except`, but the empty-choices branch was not given the same “record before raise” treatment as other post-call failures. That leaves a path where a real external call consumed a `call_index` yet never reaches Landscape.

## Suggested Fix

Before raising on empty `choices`, serialize whatever response is available and record an `ERROR` call with `response_data` or at minimum an `LLMCallError`, mirroring the null-content/model-dump failure paths.

## Impact

A provider response with empty `choices` creates an unexplained audit gap: the LLM call happened, but Landscape cannot prove it. That violates the project’s “if it’s not recorded, it didn’t happen” rule and can break call-index lineage for the surrounding node state.
---
## Summary

`chat_completion()` fabricates `content=""` for `finish_reason=="tool_calls"` and records the call as `SUCCESS`, even though the Azure provider immediately treats that same response as an unsupported failure.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py`
- Line(s): 396-400, 533-549, 590-595
- Function/Method: `AuditedLLMClient.chat_completion`

## Evidence

The client explicitly rewrites `None` content to an empty string on tool-call responses:

```python
if content is None:
    if response.choices[0].finish_reason == "tool_calls":
        content = ""
```

That fabricated value is then recorded as a successful LLM response:

```python
response_dto = LLMCallResponse(content=content, ...)
self._recorder.record_call(... status=CallStatus.SUCCESS, response_data=response_dto, ...)
return LLMResponse(content=content, ...)
```

The Azure integration documents this as a known fabrication and has to compensate after the fact:

```python
# Empty/whitespace content — AuditedLLMClient converts None→""
# (known fabrication).
if not response.content or not response.content.strip():
    if finish_reason == FinishReason.TOOL_CALLS:
        raise LLMClientError("Azure returned tool_calls response (not supported by ELSPETH)", ...)
```

See [llm.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py):396-400, [llm.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py):533-549, [llm.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py):590-595, and [azure.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/providers/azure.py):193-204.

## Root Cause Hypothesis

The client tries to preserve backward compatibility for SDK tool-call responses by forcing them into the text-response contract instead of treating them as a distinct unsupported outcome at the Tier 3 boundary.

## Suggested Fix

Treat `finish_reason=="tool_calls"` as an error path in `AuditedLLMClient` itself: record an `ERROR` call with the raw response preserved, emit error telemetry, and raise `LLMClientError` instead of fabricating `content=""` and recording `SUCCESS`.

## Impact

Landscape records a false success with synthetic content while the higher-level provider rejects the call. That creates contradictory evidence: the audit trail says the LLM returned usable text, but runtime behavior says the call failed.
---
## Summary

`chat_completion()` never validates that `response.choices[0].message.content` is actually a string, so malformed provider payloads can be recorded as successful text responses and only fail later in integration code.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py`
- Line(s): 395, 533-548, 590-595
- Function/Method: `AuditedLLMClient.chat_completion`

## Evidence

The client trusts the external payload shape here:

```python
content = response.choices[0].message.content
```

There is no `str` check before `content` is written into `LLMCallResponse` and returned in `LLMResponse`, even though `LLMResponse.content` is declared as `str` ([llm.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py):33-58).

By contrast, the OpenRouter provider validates this boundary explicitly:

```python
if not isinstance(content, str):
    raise LLMClientError(
        f"Expected string content, got {type(content).__name__}",
        retryable=False,
    )
```

See [openrouter.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/providers/openrouter.py):245-250.

The Azure provider also assumes `response.content` is a string and calls `.strip()` on it:

```python
if not response.content or not response.content.strip():
```

See [azure.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/providers/azure.py):196-204.

## Root Cause Hypothesis

The client validates only presence (`None` vs non-`None`) but not type, so malformed Tier 3 SDK data is allowed to cross into the Tier 2 contract as if it were trusted text.

## Suggested Fix

Validate `content` immediately after extraction:
- `None` -> existing null-content/tool-call handling
- non-`str` -> record an `ERROR` call and raise `LLMClientError`
- `str` -> continue

That keeps the Tier 3 validation at the actual boundary instead of relying on downstream providers to explode on `.strip()`.

## Impact

A provider bug or schema drift can produce a `SUCCESS` audit entry containing non-text “content”, then crash later in provider code or downstream transforms. That violates the response contract and records malformed external data as if it were a valid text completion.
