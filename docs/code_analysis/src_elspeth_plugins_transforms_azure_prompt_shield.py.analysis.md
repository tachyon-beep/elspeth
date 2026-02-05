# Analysis: src/elspeth/plugins/transforms/azure/prompt_shield.py

**Lines:** 459
**Role:** Azure Prompt Shield transform -- detects prompt injection attacks (jailbreak attempts and document-embedded injection) by sending content to Azure's Prompt Shield API. Binary detection model: either an attack is detected or it is not. Uses BatchTransformMixin for concurrent row processing with FIFO output ordering.
**Key dependencies:** `elspeth.plugins.base.BaseTransform`, `elspeth.plugins.batching.BatchTransformMixin` + `OutputPort`, `elspeth.plugins.pooling.PooledExecutor` + `CapacityError` + `is_capacity_error`, `elspeth.plugins.clients.http.AuditedHTTPClient`, `elspeth.plugins.config_base.TransformDataConfig`, `elspeth.plugins.context.PluginContext`, `httpx`
**Analysis depth:** FULL

## Summary

This file closely mirrors the Content Safety transform in structure and shares several of its issues. The most critical finding is a **fail-open defect in the response parsing**: when the Azure API returns a malformed response, the error is wrapped as a retryable `httpx.RequestError`, which the caller treats as a network error. After retries are exhausted, a malformed API response would eventually be treated as retryable error rather than content being blocked -- meaning prompt injection attacks could pass through if the API returns unexpected data. The response validation is also missing type checks on the `attackDetected` boolean values, which are Tier 3 external data.

## Critical Findings

### [419-421] User content used as both userPrompt AND documents -- duplicate analysis is wasteful and semantically wrong

**What:** The API request at line 420 sends the same text as both the `userPrompt` field and as the sole entry in the `documents` array: `json={"userPrompt": text, "documents": [text]}`.

**Why it matters:** Azure Prompt Shield's two detection modes serve different purposes:
- `userPrompt` analysis: detects direct jailbreak attempts in user messages
- `documents` analysis: detects prompt injection hidden in documents/context that the LLM would read

By sending the same text to both, the transform is:
1. **Doubling API cost** -- two analyses of the same content per field per row.
2. **Semantically conflating user input with document context** -- the models are trained for different attack patterns. User prompt attacks are explicit ("ignore your instructions"), while document attacks are covert (hidden instructions in seemingly normal text). Applying the document attack model to a user prompt, or the user prompt model to a document, produces less accurate results.
3. **Making the document_attack result meaningless** -- since the "document" is identical to the user prompt, a `document_attack` detection is indistinguishable from a `user_prompt_attack` detection. The distinction in the error result at line 338-346 is illusory.

The correct pattern would be to classify each field as either a user prompt or a document, and send them to the appropriate analysis path. The current implementation should at minimum allow configuration of which fields are user prompts vs. documents.

### [427-441] Fail-open on malformed response: prompt injection passes through on API anomaly

**What:** When the Azure API returns a malformed response (missing keys, unexpected structure), the exception at line 441 wraps it as `httpx.RequestError`. The caller at line 327-335 treats `httpx.RequestError` as `retryable=True`. For a prompt injection detection transform, a malformed API response should fail **closed** (block the content), not open (allow it through after retries).

**Why it matters:** If the Azure API changes its response format, experiences a partial outage returning empty responses, or an intermediary proxy corrupts the response, the transform will:
1. Retry the request (same malformed response returned each time)
2. After max retries, the row will fail with a retryable error
3. Depending on engine retry exhaustion behavior, the content may either be quarantined or retried indefinitely

The comment at line 426 says "fail CLOSED on malformed response" but the implementation does the opposite -- it wraps as a retryable error rather than immediately returning `TransformResult.error()` with `retryable=False`.

**Evidence:**
```python
# Line 426: Comment says fail closed
# Security transform: fail CLOSED on malformed response
try:
    data = response.json()
    user_attack = data["userPromptAnalysis"]["attackDetected"]
    # ...
except (KeyError, TypeError) as e:
    # Line 441: But implementation wraps as retryable RequestError
    raise httpx.RequestError(f"Malformed Prompt Shield response: {e}") from e

# Caller (line 327-335):
except httpx.RequestError as e:
    return TransformResult.error({...}, retryable=True)  # ALLOWS RETRY, NOT FAIL-CLOSED
```

### [429-431] No type validation on attackDetected values -- Tier 3 boundary violation

**What:** The `user_attack` and `doc_attack` values at lines 429-431 are extracted from the Azure API response (Tier 3 external data) without validating that they are boolean values. The only types caught are `KeyError` and `TypeError`. If `attackDetected` is a string `"false"` instead of boolean `false`, the truthiness check at line 338 (`if analysis["user_prompt_attack"]`) would evaluate `"false"` as `True`, causing false positives. Conversely, if `attackDetected` is `0` instead of `False`, it would be falsy and allow content through.

**Why it matters:** Per the Three-Tier Trust Model, external API responses must be validated at the boundary. The `attackDetected` values are used directly in a boolean check at line 338 without confirming they are actually booleans. While Azure currently returns proper booleans, a JSON parsing edge case, API version change, or proxy interference could change the type.

**Evidence:**
```python
# Line 429: No isinstance(user_attack, bool) check
user_attack = data["userPromptAnalysis"]["attackDetected"]
documents_analysis = data["documentsAnalysis"]
doc_attack = any(doc["attackDetected"] for doc in documents_analysis)

# Line 338: Used in boolean context without type guarantee
if analysis["user_prompt_attack"] or analysis["document_attack"]:
```

## Warnings

### [172-176] PooledExecutor allocated but never used in processing path

**What:** Same issue as in content_safety.py. The `__init__` method creates a `PooledExecutor` when `pool_size > 1`, but neither `_process_row` nor `_process_single_with_state` reference `self._executor`. The only reference is in `close()` where it is shutdown.

**Why it matters:** Wastes thread pool resources (threads, memory) for no functional purpose. The actual concurrency comes from `BatchTransformMixin`'s worker pool initialized via `connect_output` -> `init_batch_processing`.

**Evidence:**
```python
# Line 172-176: Created but never used
if cfg.pool_config is not None:
    self._executor: PooledExecutor | None = PooledExecutor(cfg.pool_config)
# No method ever calls self._executor.submit() or similar
```

### [236-238] Recorder fallback in accept() bypasses on_start() contract

**What:** Same pattern as content_safety.py. The `accept()` method captures the recorder from `ctx.landscape` if `self._recorder` is None, but does not capture `run_id`, `telemetry_emit`, or `limiter`. This creates partial state if `on_start()` was not called.

**Why it matters:** If `on_start()` is skipped, audit records will have empty `run_id`, telemetry will be silently dropped, and rate limiting will be bypassed. The partial capture gives a false sense of initialization completeness.

**Evidence:**
```python
if self._recorder is None and ctx.landscape is not None:
    self._recorder = ctx.landscape
# self._run_id, self._telemetry_emit, self._limiter NOT captured
```

### [302-308] Non-string fields silently skipped without audit trail

**What:** Same pattern as content_safety.py. When configured fields exist in the row but are not strings, they are silently skipped with no logging or audit indication. The row passes as "validated" even though not all configured fields were actually analyzed.

**Why it matters:** For a prompt injection detection transform, silently skipping fields means injection attacks in non-string fields (e.g., a field that was converted from string to list by an upstream transform) pass through without detection. The audit trail records the row as safe when it may not have been fully analyzed.

**Evidence:**
```python
value = row_dict[field_name]
if not isinstance(value, str):
    continue  # Silent skip - no audit trail
```

### [438] Exception catch does not include ValueError

**What:** The exception handler at line 438 catches `(KeyError, TypeError)` but not `ValueError`. The `response.json()` call at line 428 can raise `ValueError` (or more specifically `json.JSONDecodeError`, a subclass of `ValueError`) if the response body is not valid JSON.

**Why it matters:** If the Azure API returns non-JSON content (e.g., an HTML error page from a load balancer, or a 200 response with empty body), `response.json()` will raise `ValueError`/`JSONDecodeError` which is not caught. This will propagate as an unhandled exception through the `httpx.HTTPStatusError` / `httpx.RequestError` handlers in the caller, or crash the worker thread.

**Evidence:**
```python
try:
    data = response.json()  # Can raise ValueError/JSONDecodeError
    user_attack = data["userPromptAnalysis"]["attackDetected"]
    # ...
except (KeyError, TypeError) as e:  # ValueError NOT caught
    raise httpx.RequestError(f"Malformed Prompt Shield response: {e}") from e
```

Note: `response.json()` uses httpx's internal JSON parser which raises `json.JSONDecodeError` (subclass of `ValueError`). This is distinct from `KeyError` and `TypeError`.

### [354-361] _get_fields_to_scan identical to content_safety -- potential for extraction

**What:** The `_get_fields_to_scan` method is character-for-character identical to the same method in content_safety.py. Both transforms share this logic for resolving `"all"` vs string vs list field specifications.

**Why it matters:** Code duplication in security-critical paths means a bug fix in one location may not be applied to the other. This is a maintenance hazard.

## Observations

### [100-131] Class structure mirrors content_safety.py closely

The class follows the same architecture pattern as AzureContentSafety: BaseTransform + BatchTransformMixin, connect_output/accept/process(raises), _process_row/_process_single_with_state. This consistency is good for maintainability.

### [138] API_VERSION matches content_safety

Both transforms use `API_VERSION = "2024-09-01"`. This is correct -- Prompt Shield is part of the Azure Content Safety service and shares the same API versioning.

### [348-352] Success result passes contract through correctly

The success path at lines 348-352 correctly passes `row.contract` through, maintaining schema contract integrity for downstream transforms.

### [443-459] Close sequence matches content_safety pattern

The shutdown order (batch processing -> pooled executor -> HTTP clients -> recorder reference) is correct and prevents resource leaks.

### [67-68] Config docstring says "Azure Content Safety" for API key

Minor documentation issue: the config field descriptions at lines 67-68 say "Azure Content Safety" rather than "Azure Prompt Shield". While both services share credentials, this is confusing for operators.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Three issues require immediate attention: (1) The API request structure should be redesigned to properly distinguish user prompt fields from document fields, rather than sending identical content to both analysis paths. This is a design defect that wastes API calls and produces meaningless document_attack results. (2) The malformed response handler must actually fail closed as the comment states -- return `TransformResult.error()` with `retryable=False`, not wrap as `httpx.RequestError`. The comment at line 426 and the implementation at line 441 directly contradict each other. (3) Add `ValueError` to the exception catch and add type validation on `attackDetected` boolean values at the Tier 3 boundary. Secondary: remove unused PooledExecutor, add audit logging for skipped fields, fix config docstrings.
**Confidence:** HIGH -- The fail-open behavior is confirmed by tracing the exception handling chain from `_analyze_prompt` through the caller's `except httpx.RequestError` handler. The duplicate content submission is visible in the API request construction. The missing ValueError catch is confirmed by checking httpx's `response.json()` behavior.
