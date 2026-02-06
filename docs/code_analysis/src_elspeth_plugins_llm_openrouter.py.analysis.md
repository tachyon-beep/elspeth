# Analysis: src/elspeth/plugins/llm/openrouter.py

**Lines:** 719
**Role:** OpenRouter single-query LLM transform. Same pattern as Azure but targeting OpenRouter's API via raw HTTP (httpx) instead of the OpenAI SDK. Sends one prompt per row, parses the JSON response, extracts content, and adds classification fields to the row. Includes Langfuse tracing support (Azure AI tracing is correctly rejected since OpenRouter uses HTTP directly, not the OpenAI SDK).
**Key dependencies:** Imports `LLMConfig` from `base.py`, `AuditedHTTPClient` from `plugins.clients.http`, `BatchTransformMixin`/`OutputPort` from `plugins.batching`, `PromptTemplate`/`TemplateError` from `plugins.llm.templates`, Langfuse tracing types from `plugins.llm.tracing`, `httpx` for HTTP error types, LLM error types (`NetworkError`, `RateLimitError`, `ServerError`) from `plugins.clients.llm`. Imported by the plugin manager for registration.
**Analysis depth:** FULL

## Summary

The file closely mirrors `azure.py` structurally but with important differences in the HTTP boundary handling. OpenRouter uses raw HTTP via `AuditedHTTPClient` instead of the OpenAI SDK, which means the transform must manually parse JSON responses and extract content -- creating a Tier 3 boundary within the transform itself. This boundary handling is done correctly with proper error wrapping. However, there are several findings: a critical issue with HTTP client creation lacking thread safety, a warning about the response body being parsed twice (once by the transform, once by the audited client), and an important behavioral difference where OpenRouter silently absorbs `max_tokens=0` (falsy value).

## Critical Findings

### [C1: LINE 663-689] HTTP client creation creates new httpx.Client for every request

**What:** The `_get_http_client()` method creates `AuditedHTTPClient` instances which are cached per `state_id`. However, each `AuditedHTTPClient` creates a new `httpx.Client()` (with `with httpx.Client(...)` context manager) for every `post()` call (see http.py line 304). This means connection pooling is not utilized -- every LLM request opens a new TCP connection (potentially including TLS handshake) to OpenRouter.

**Why it matters:** For high-throughput pipelines processing thousands of rows with concurrent workers, this creates:
1. **Latency overhead:** TLS handshake per request adds 50-200ms each.
2. **Resource exhaustion:** Many short-lived connections can exhaust ephemeral ports or trigger rate limiting at the OS/network level.
3. **No HTTP/2 multiplexing:** The OpenRouter API likely supports HTTP/2, but creating a new client per request prevents multiplexing benefits.

**Evidence:**
```python
# http.py line 304 - new Client per request
try:
    with httpx.Client(timeout=effective_timeout) as client:
        response = client.post(full_url, json=json, headers=merged_headers)
```

This is technically an issue in `AuditedHTTPClient` rather than OpenRouter specifically, but OpenRouter is the primary consumer of this HTTP path for LLM calls. The Azure transform avoids this because the OpenAI SDK manages its own connection pooling internally.

**Note:** This is the same pattern used by Azure's `AuditedHTTPClient` calls, so it is a shared concern. However, OpenRouter is the first LLM transform to make raw HTTP calls, making it the primary place this matters in practice. Filed here rather than in a separate HTTP client analysis because the impact is most visible in the OpenRouter LLM workflow.

### [C2: LINE 527] max_tokens=0 is treated as falsy, silently omitted from request

**What:** The request body construction uses `if self._max_tokens:` to conditionally add `max_tokens`. Since `0` is falsy in Python, a `max_tokens` of `0` would be silently omitted from the request.

**Why it matters:** While `max_tokens=0` is nonsensical for a chat completion request, the Pydantic config field has `gt=0` validation (from `LLMConfig.max_tokens`, line 80 in base.py), so the value `0` would be rejected at config time. However, this truthiness check is a fragile pattern. If the Pydantic validator were ever relaxed (e.g., to allow `0` to mean "use model default"), this check would silently eat the value. The Azure transform does not have this issue because it passes `max_tokens` to `llm_client.chat_completion()` which uses `if max_tokens is not None` (a proper None check).

**Evidence:**
```python
# openrouter.py line 527 - truthiness check
if self._max_tokens:
    request_body["max_tokens"] = self._max_tokens

# Compare with azure.py -> llm.py line 292-293 - proper None check
if max_tokens is not None:
    request_data["max_tokens"] = max_tokens
```

While currently safe due to Pydantic validation, this is a latent bug that violates the principle of defensive correctness.

## Warnings

### [W1: LINE 505] Template rendering does not pass schema contract for dual-name resolution

**What:** Same issue as Azure (azure.py W1). The `_process_row()` method calls `self._template.render_with_metadata(row_data)` without passing `contract=row.contract`.

**Why it matters:** Templates using original header names (`{{ row["Amount USD"] }}`) will fail with `TemplateError` at runtime. See base.py analysis W1 for full details.

**Evidence:**
```python
# openrouter.py line 505
rendered = self._template.render_with_metadata(row_data)  # No contract!
```

### [W2: LINE 586-597] JSON parse error returns raw body preview in error reason

**What:** When the response body is not valid JSON, the error reason includes `body_preview` with the first 500 characters of the response text (line 596). This preview is stored in the audit trail via `TransformResult.error()`.

**Why it matters:** If the OpenRouter response contains sensitive information (error messages with API keys, internal server paths, etc.), this data will be stored in the audit trail. The 500-character truncation limits exposure, but the pattern should be noted for security review. The Azure transform does not have this issue because JSON parsing happens inside the OpenAI SDK.

**Evidence:**
```python
# Line 594-596
error_reason_json: TransformErrorReason = {
    "reason": "invalid_json_response",
    "error": f"Response is not valid JSON: {e}",
    "content_type": response.headers.get("content-type", "unknown"),
}
if response.text:
    error_reason_json["body_preview"] = response.text[:500]
```

### [W3: LINE 620] Usage data coerced with `or {}` for null/missing cases

**What:** `usage = data.get("usage") or {}` handles both missing and null usage fields from OpenRouter. The comment explains this is intentional ("OpenRouter can return `{"usage": null}` or omit usage entirely").

**Why it matters:** While correct for OpenRouter's API behavior, this deviates from the ELSPETH pattern where transforms should NOT coerce. However, this is at a Tier 3 boundary (external API response), so coercion is explicitly allowed per CLAUDE.md. The comment makes the intent clear. The usage dict is then passed to output row building and Langfuse tracing.

The subtle issue is that the empty dict `{}` will be stored as `{response_field}_usage: {}` in the output row, which downstream transforms may interpret differently than `None`. If a downstream transform checks `if usage:` to decide whether to compute cost, an empty dict is truthy, potentially leading to a "cost = 0" record where "cost = unknown" is more accurate.

**Evidence:**
```python
# Line 620
usage = data.get("usage") or {}
# Line 637 - stored in output
output[f"{self._response_field}_usage"] = usage  # {} when missing/null
```

### [W4: LINE 629] Model name from response uses .get() with fallback to configured model

**What:** `data.get("model", self._model)` extracts the model name from the response. This is Tier 3 data, so `.get()` with a fallback is appropriate. However, the fallback means that if OpenRouter changes its response format and stops including the `model` field, the audit trail will record the configured model rather than "unknown," which could mislead auditors.

**Why it matters:** The audit trail should record what actually happened, not what was requested. If the API doesn't tell us which model processed the request, recording the requested model as the actual model is an assumption that could be false (OpenRouter routes to fallback models). This is a minor point but relevant for audit integrity.

**Evidence:**
```python
# Line 629 - response model with fallback
model=data.get("model", self._model),
# Line 644 - same pattern for output row
output[f"{self._response_field}_model"] = data.get("model", self._model)
```

### [W5: LINE 658-661] Client cleanup in finally block same pattern as Azure

**What:** Same `finally` cleanup pattern as Azure (azure.py W3), removing the cached HTTP client after each `_process_row()` call.

**Why it matters:** See azure.py analysis W3 for details. The "cache" is effectively per-call, making the caching infrastructure overhead without benefit. Same analysis applies.

## Observations

### [O1: LINE 117-193] __init__ duplicates significant logic from BaseLLMTransform

**What:** Same duplication pattern as Azure (azure.py O1). Config parsing, template creation, schema creation, and output schema config building are all duplicated from `BaseLLMTransform.__init__()`.

### [O2: LINE 540] Token ID fallback to "unknown" is dead code

**What:** Same as Azure (azure.py O4). `token_id = ctx.token.token_id if ctx.token else "unknown"` -- the "unknown" path is unreachable because `BatchTransformMixin.accept_row()` validates `ctx.token is not None`.

### [O3: LINE 599-616] Tier 3 boundary handling for response parsing is well-done

**What:** The response parsing at lines 599-616 correctly handles multiple failure modes:
- `data["choices"]` missing: `KeyError` caught
- `choices` is empty: explicit check with descriptive error
- `choices[0]["message"]["content"]` malformed: `KeyError`, `IndexError`, `TypeError` caught
- Response keys included in error for debugging

This is correct Tier 3 boundary handling. The error reasons include `response_keys` (line 613) which helps debugging without exposing the full response body.

### [O4: LINE 264-271] Azure AI tracing correctly rejected for OpenRouter

**What:** The `_setup_tracing()` method explicitly rejects `azure_ai` tracing with a clear warning message explaining that Azure AI auto-instruments the OpenAI SDK but OpenRouter uses HTTP directly. This is correct and well-documented.

### [O5: LINE 676-688] HTTP client includes HTTP-Referer header as required by OpenRouter

**What:** The `AuditedHTTPClient` is created with an `HTTP-Referer` header pointing to the elspeth-rapid GitHub URL. This is an OpenRouter API requirement.

**Why it matters:** The referer URL (`https://github.com/elspeth-rapid`) is hardcoded. If the project moves or is renamed, this header becomes incorrect. This is low severity since OpenRouter uses this for analytics/attribution rather than authentication, but it should be noted for release hygiene.

### [O6: LINE 550-584] Error classification correctly maps HTTP status codes to retry behavior

**What:** HTTP status code mapping is correct:
- 429 -> `RateLimitError` (retryable)
- 500+ -> `ServerError` (retryable)
- Other 4xx -> `TransformResult.error()` (not retryable)
- `httpx.RequestError` (network) -> `NetworkError` (retryable)

This matches the Azure transform's behavior through `LLMClientError` subclasses, ensuring consistent retry semantics across providers.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** The `max_tokens` truthiness check (C2) should be changed to `if self._max_tokens is not None` for correctness parity with Azure. The HTTP client creation pattern (C1) is a deeper architectural issue in `AuditedHTTPClient` that would benefit from connection reuse, but this requires changes to the HTTP client module rather than OpenRouter itself. The contract passthrough gap (W1) should be addressed consistently with Azure (see base.py analysis). The usage coercion pattern (W3) is correct per Tier 3 rules but downstream consumers should be documented about the empty dict vs None semantics.
**Confidence:** HIGH -- Full read of file plus all dependencies. Cross-referenced with Azure transform and HTTP client implementation. The truthiness bug is clearly evidenced by comparing with the Azure/LLM client None check pattern.
