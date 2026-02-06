# Analysis: src/elspeth/plugins/clients/llm.py

**Lines:** 457
**Role:** Audited LLM client wrapping OpenAI-compatible SDK. Records every LLM call (prompt, response, token usage, latency) to the Landscape audit trail. Provides structured error classification (rate limit, network, server, content policy, context length) with retryability signals.
**Key dependencies:** structlog, elspeth.contracts (CallStatus, CallType), elspeth.core.canonical (stable_hash), base.py (AuditedClientBase, TelemetryEmitCallback), telemetry.events (ExternalCallCompleted). Imported by: plugins/llm/azure.py, azure_multi_query.py, openrouter.py, llm/base.py, engine/processor.py, plugins/pooling/executor.py
**Analysis depth:** FULL

## Summary

The LLM client is well-structured with thorough error classification and proper audit trail discipline. The telemetry-after-landscape pattern is consistently followed. However, there is a critical issue with string-based error classification that can produce false positives/negatives, a potential data integrity issue where `**kwargs` can silently override critical request parameters, and the `raw_response` from `model_dump()` may contain non-serializable types. The error hierarchy is well-designed. Confidence is high.

## Critical Findings

### [148-194, 440-456] String-based error classification is fragile and can misclassify errors
**What:** The `_is_retryable_error` function and the error re-raise block (lines 440-456) both classify errors by searching for substrings in the stringified exception message. For example, `"429" in error_str` checks if "429" appears anywhere in the error string, and `"rate" in error_str` matches any error containing "rate".
**Why it matters:** This produces false positives and false negatives in production:
1. **False positive (retries non-retryable errors):** An error message like `"Invalid configuration for model gpt-4-0429"` contains "429" and would be classified as a rate limit error, causing infinite retries on a permanent configuration error. A model named `"rate-limited-v2"` would also trigger the rate limit match.
2. **False negative (fails to retry retryable errors):** LLM providers can return rate limit errors with different phrasing (e.g., Azure returns `"Requests to the Embeddings_Create Operation under Azure OpenAI API version 2024-02-01 have been throttled"` which contains neither "rate" nor "429").
3. **Server error overlap:** The string "500" appears in legitimate data (e.g., `"Processing batch of 500 items failed"`), and would be classified as a server error.
4. **Ordering dependency:** In `_is_retryable_error`, the check for "500" in `server_error_codes` (line 157) runs before client error codes like "400" (line 177). An error message containing both (e.g., `"Error 400: batch size 500 too large"`) would be classified as retryable when it should not be.
**Evidence:** `llm.py:151`: `if "rate" in error_str or "429" in error_str: return True` -- "429" can appear in model names, version strings, dates. `llm.py:157`: `if any(code in error_str for code in server_error_codes)` -- "500" is a common number that appears in non-error contexts.

### [289-291] `**kwargs` can silently override critical request parameters
**What:** Both `request_data` and `sdk_kwargs` are constructed with `**kwargs` spread after named parameters: `request_data = {"model": model, "messages": messages, "temperature": temperature, "provider": self._provider, **kwargs}`. If `kwargs` contains keys like `"model"`, `"messages"`, or `"temperature"`, the named parameters are silently overwritten.
**Why it matters:** This creates a split-brain condition where the audit trail records different parameters than what was actually sent to the LLM:
1. Caller passes `model="gpt-4"` and `kwargs={"model": "gpt-3.5-turbo"}`.
2. `request_data` would have `model="gpt-3.5-turbo"` (kwargs wins).
3. `sdk_kwargs` would also have `model="gpt-3.5-turbo"` (kwargs wins).
4. The audit trail records `model="gpt-3.5-turbo"` but the function signature suggested `model="gpt-4"`.
This is particularly dangerous for audit integrity -- the system claims to use one model but the audit trail shows another, with no warning.
**Evidence:** `llm.py:289`: `**kwargs` at end of dict literal overwrites any earlier key with the same name. Python dict literal semantics: last key wins.

## Warnings

### [312] Accessing `response.choices[0]` without bounds check
**What:** After a successful API call, the code accesses `response.choices[0].message.content` without checking that `choices` is non-empty.
**Why it matters:** While the OpenAI SDK normally returns at least one choice, edge cases exist:
1. Some providers return empty choices for content-filtered responses.
2. Azure OpenAI may return zero choices when the response is filtered by content safety.
3. A provider-side bug could return an empty list.
The result would be an `IndexError` that is caught by the generic `except Exception` block and classified as a non-retryable client error, when it may actually be a retryable content-filter transient issue. The error would be recorded in the audit trail but with misleading classification.
**Evidence:** `llm.py:312`: `content = response.choices[0].message.content or ""` -- `IndexError` if choices is empty.

### [325] `model_dump()` may produce non-serializable types
**What:** `raw_response = response.model_dump()` converts the Pydantic model to a dict. The resulting dict is passed as part of `response_data` to `record_call()`, which calls `canonical_json()` on it. If `model_dump()` produces types not handled by the canonical normalizer (e.g., `datetime` objects, custom Pydantic types, or nested models that serialize to non-standard types), canonicalization would raise a `TypeError`.
**Why it matters:** If canonicalization fails during `record_call()`, the exception propagates up to `chat_completion()`. Because `record_call()` is called inside the `try` block (line 336), the exception would be caught by the generic `except Exception` handler (line 386), which would then try to record an error call *without* the response. The LLM call succeeded but the response is lost from the audit trail. The caller gets an `LLMClientError` instead of the `LLMResponse` they expected.
**Evidence:** `llm.py:325`: `raw_response = response.model_dump()`. The OpenAI SDK's `model_dump()` typically returns JSON-safe types, but this is not contractually guaranteed across SDK versions. A SDK upgrade could introduce new field types.

### [52] `LLMResponse.total_tokens` uses `.get()` on `usage` dict
**What:** The `total_tokens` property uses `self.usage.get("prompt_tokens", 0) + self.usage.get("completion_tokens", 0)`. The usage dict is populated from the OpenAI response at line 315-318, using direct attribute access (`response.usage.prompt_tokens`).
**Why it matters:** There is an asymmetry: the usage dict is populated with direct access (trusting the SDK response at Tier 3 boundary), but consumed with `.get()` (defensive access). Per the project's anti-pattern rules, if the dict was correctly populated upstream, `.get()` should not be needed. If it was not correctly populated, the upstream code should be fixed. However, since `usage` can also be an empty dict (line 320: `usage = {}` when `response.usage is None`), the `.get()` pattern is actually correct here -- it handles both the "has usage" and "empty dict" cases gracefully. This is a legitimate use of `.get()` since the dict's contents are conditionally populated.
**Evidence:** `llm.py:52`: `self.usage.get("prompt_tokens", 0)` -- appears defensive but is actually correct given empty-dict case.

### [24] LLMResponse dataclass is not frozen
**What:** `LLMResponse` is a regular `@dataclass`, not `@dataclass(frozen=True)`. This means callers can mutate the response after it's returned.
**Why it matters:** If a caller modifies `response.content` or `response.usage` after recording to the audit trail, the in-memory state diverges from the audit record. Since the response is also used by the transform that called `chat_completion()`, any mutation would create a discrepancy between "what the transform processed" and "what the audit trail says was returned." Making it frozen would prevent this class of bugs.

## Observations

### [132-194] `_is_retryable_error` is a module-level function, not a method
**What:** This function is defined at module scope rather than as a static/class method of `AuditedLLMClient`. It is only used by `AuditedLLMClient.chat_completion()`.
**Why it matters:** Minor organization issue. As a module-level function, it is accessible to anyone who imports the module, but it's tightly coupled to the OpenAI SDK's error message format. Making it a static method would better signal its scope.

### [260] Only `chat_completion` is implemented
**What:** The LLM client only supports chat completion. No support for embeddings, images, audio, or other modalities.
**Why it matters:** This is fine for current use (all LLM transforms use chat completion), but future modality support would require additional methods with the same audit recording pattern. Similar to the HTTP client's post/get duplication, this could benefit from a shared internal audit wrapper.

### [233] `underlying_client` typed as `Any`
**What:** The OpenAI client parameter is typed as `Any` with a comment noting it should be `openai.OpenAI` or `openai.AzureOpenAI`.
**Why it matters:** No type checking on the SDK client. If the wrong type is passed, the error only surfaces at runtime when `self._client.chat.completions.create()` is called. This is a pragmatic choice to avoid importing `openai` as a hard dependency, but it means incorrect client types are not caught until execution.

## Verdict
**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Replace string-based error classification with structured error inspection (check for `status_code` attribute on OpenAI exceptions, or use `isinstance` checks against `openai.RateLimitError`, `openai.APIStatusError`, etc.). (2) Validate that `**kwargs` does not contain keys that would override named parameters, or use a separate `extra_params` dict. (3) Add a bounds check on `response.choices` before accessing index 0. (4) Make `LLMResponse` a frozen dataclass.
**Confidence:** HIGH -- Full read of all 457 lines, all callers and importers inspected, OpenAI SDK behavior considered.
