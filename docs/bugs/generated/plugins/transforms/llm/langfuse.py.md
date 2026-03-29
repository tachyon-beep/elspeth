## Summary

Partial token-usage data is silently dropped from Langfuse traces whenever a provider reports only one of `prompt_tokens` or `completion_tokens`.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/plugins/transforms/llm/langfuse.py
- Line(s): 121-124
- Function/Method: `ActiveLangfuseTracer.record_success`

## Evidence

`record_success()` only forwards usage to Langfuse when `usage.is_known` is true:

```python
if usage is not None and usage.is_known:
    update_kwargs["usage_details"] = {
        "input": usage.prompt_tokens,
        "output": usage.completion_tokens,
    }
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/llm/langfuse.py:121-124`

But ELSPETH’s `TokenUsage` contract explicitly preserves partial usage and says it is still valuable signal:

```python
@property
def has_data(self) -> bool:
    """True when at least one token count was reported."""
```

Source: `/home/john/elspeth/src/elspeth/contracts/token_usage.py:68-76`

Its serializer also preserves whichever fields are known instead of requiring both:

```python
if self.prompt_tokens is not None:
    result["prompt_tokens"] = self.prompt_tokens
if self.completion_tokens is not None:
    result["completion_tokens"] = self.completion_tokens
```

Source: `/home/john/elspeth/src/elspeth/contracts/token_usage.py:88-93`

The rest of the system already treats partial usage as worth emitting. `record_call()` sends telemetry when `tu.has_data`, not only when both counters are known:

```python
tu = TokenUsage.from_dict(raw_usage)
token_usage = tu if tu.has_data else None
```

Source: `/home/john/elspeth/src/elspeth/contracts/plugin_context.py:334-337`

And LLM plugins explicitly acknowledge usage may be omitted or partial at the provider boundary:

```python
# Note: "usage" and "model" are optional in OpenAI/OpenRouter API responses
usage = TokenUsage.from_dict(data.get("usage"))
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/llm/openrouter_batch.py:717-719`

What the code does: drops all usage unless both counters are present.

What it should do: preserve whichever token counters were actually reported, the same way the rest of ELSPETH preserves partial usage.

## Root Cause Hypothesis

`langfuse.py` predates or diverged from the newer `TokenUsage` contract and still treats usage as an all-or-nothing payload. That conflicts with the current repository-wide rule that partial token data must be retained rather than erased.

## Suggested Fix

Use `usage.has_data` instead of `usage.is_known`, and include only the keys that are present.

Example shape:

```python
if usage is not None and usage.has_data:
    usage_details: dict[str, int] = {}
    if usage.prompt_tokens is not None:
        usage_details["input"] = usage.prompt_tokens
    if usage.completion_tokens is not None:
        usage_details["output"] = usage.completion_tokens
    update_kwargs["usage_details"] = usage_details
```

## Impact

Langfuse traces under-report LLM usage for providers that return incomplete usage blocks. That loses cost/throughput observability and makes Langfuse disagree with ELSPETH’s own token-usage handling, even though the underlying provider did return some usage data.
---
## Summary

Langfuse traces record only the user prompt and omit the system prompt, so the traced request can differ from the actual LLM call ELSPETH sent.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/plugins/transforms/llm/langfuse.py
- Line(s): 141, 183
- Function/Method: `ActiveLangfuseTracer.record_success`, `ActiveLangfuseTracer.record_error`

## Evidence

Both tracing paths hard-code the Langfuse generation input to a single user message:

```python
input=[{"role": "user", "content": prompt}]
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/llm/langfuse.py:141`
Source: `/home/john/elspeth/src/elspeth/plugins/transforms/llm/langfuse.py:183`

But the real LLM request assembled by callers includes an optional system prompt before the user message:

```python
messages: list[dict[str, str]] = []
if self.system_prompt:
    messages.append({"role": "system", "content": self.system_prompt})
messages.append({"role": "user", "content": rendered.prompt})
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py:258-261`
Source: `/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py:512-515`
Source: `/home/john/elspeth/src/elspeth/plugins/transforms/llm/openrouter_batch.py:590-598`

So when `system_prompt` is configured, the external provider receives two messages, but Langfuse stores only one. The existing tests reinforce the narrowed behavior by asserting only a user message is traced:

```python
assert gen_kwargs["input"] == [{"role": "user", "content": "Hello world"}]
```

Source: `/home/john/elspeth/tests/unit/plugins/llm/test_tracing_integration.py:162-166`

What the code does: traces a simplified request.

What it should do: trace the actual message list sent to the provider.

## Root Cause Hypothesis

The tracer protocol was defined around a single `prompt: str` instead of the real `messages` payload. Once optional system prompts were added to LLM transforms, `langfuse.py` was not updated to capture the full request shape.

## Suggested Fix

Change the tracer contract in `langfuse.py` to accept the exact message list, or at minimum both `system_prompt` and `prompt`, then pass that through unchanged to Langfuse.

Example direction:

```python
def record_success(..., messages: list[dict[str, str]], ...):
    ...
    self.client.start_as_current_observation(
        as_type="generation",
        name="llm_call",
        model=model,
        input=messages,
    )
```

Then update callers in the LLM transform modules to pass the already-built `messages` list instead of only `rendered.prompt`.

## Impact

Langfuse prompt analytics, debugging, and incident review operate on an incomplete request. When a system prompt changes model behavior, investigators looking only at Langfuse will see a different prompt than the one actually sent to the external LLM.
