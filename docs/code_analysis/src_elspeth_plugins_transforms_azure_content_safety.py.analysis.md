# Analysis: src/elspeth/plugins/transforms/azure/content_safety.py

**Lines:** 526
**Role:** Azure Content Safety transform -- sends text content to Azure's Content Safety API for moderation across four categories (hate, violence, sexual, self-harm). Flags content when severity scores exceed configured thresholds. Uses BatchTransformMixin for concurrent row processing with FIFO output ordering and PooledExecutor for internal concurrency.
**Key dependencies:** `elspeth.plugins.base.BaseTransform`, `elspeth.plugins.batching.BatchTransformMixin` + `OutputPort`, `elspeth.plugins.pooling.PooledExecutor` + `CapacityError` + `is_capacity_error`, `elspeth.plugins.clients.http.AuditedHTTPClient`, `elspeth.plugins.config_base.TransformDataConfig`, `elspeth.plugins.context.PluginContext`, `httpx`
**Analysis depth:** FULL

## Summary

This file is well-structured and follows ELSPETH patterns correctly for the most part. The primary concern is a **fail-open security defect** in the response parsing: when the Azure API returns an unexpected category name, it silently maps to a severity of 0 (safe) in the result dict rather than failing closed. For a content moderation transform, failing open means dangerous content passes unchecked. There is also an unused `PooledExecutor` that is allocated but never wired into the processing path, wasting resources. The Tier 3 boundary handling for the API response is present but has gaps.

## Critical Findings

### [451-467] Fail-open on unknown Azure category names: dangerous content passes unchecked

**What:** The `_analyze_content` method initializes all four categories to severity 0 (safe) at line 457-462, then iterates over the Azure API response to update them. The category name mapping at line 464 uses a simple string replacement (`"selfharm"` -> `"self_harm"`), but if Azure returns an unexpected category name (e.g., `"SelfHarm"` with different casing, or a new category like `"Jailbreak"`), the `result[category]` assignment at line 465 silently creates a new key in the dict rather than updating the expected category. The four standard categories remain at their initialized value of 0 (safe).

**Why it matters:** This is a content safety transform. Failing open means harmful content passes through the pipeline unchecked. If Azure changes the API response format (e.g., `"Hate"` instead of `"hate"`, or introduces a v2 response format), all content will be classified as safe regardless of actual severity scores. The pipeline will produce incorrect safety assessments with full confidence -- a silent data integrity failure in a security-critical path.

**Evidence:**
```python
# Lines 457-465
result: dict[str, int] = {
    "hate": 0,
    "violence": 0,
    "sexual": 0,
    "self_harm": 0,
}
for item in data["categoriesAnalysis"]:
    category = item["category"].lower().replace("selfharm", "self_harm")
    result[category] = item["severity"]  # If category is unexpected, creates new key; originals stay 0
```

If Azure returns `{"category": "SelfHarm", "severity": 6}`, the code does:
1. `"SelfHarm".lower()` = `"selfharm"`
2. `"selfharm".replace("selfharm", "self_harm")` = `"self_harm"` -- this works
But if Azure returns `{"category": "Self-Harm", "severity": 6}`:
1. `"Self-Harm".lower()` = `"self-harm"`
2. `"self-harm".replace("selfharm", "self_harm")` = `"self-harm"` -- NOT matched
3. `result["self-harm"] = 6` -- new key, `result["self_harm"]` stays at 0

The transform should validate that `category` is one of the four expected keys and fail closed (reject the content or error) if it encounters an unexpected category.

### [330-335] Non-string fields silently skipped without audit trail

**What:** When `fields_to_scan` specifies a field that exists in the row but is not a string (line 335: `if not isinstance(value, str): continue`), the field is silently skipped. No audit event, no warning, no indication in the TransformResult that a configured field was not scanned.

**Why it matters:** If a data pipeline evolution changes a field type from string to dict/list (e.g., JSON parsing upstream), this transform will silently stop scanning that field. Content that should be moderated will pass through without any indication. In a high-stakes content safety system, silent scan omission is a critical gap -- the audit trail will show the row as "validated" even though the configured field was never checked.

**Evidence:**
```python
for field_name in fields_to_scan:
    if field_name not in row_dict:
        continue  # Skip fields not present in this row
    value = row_dict[field_name]
    if not isinstance(value, str):
        continue  # SILENT skip - no audit trail of unscanned field
```

## Warnings

### [196-199] PooledExecutor allocated but never used in processing path

**What:** The `__init__` method creates a `PooledExecutor` instance at line 197 when `pool_size > 1`, but this executor is never referenced in the processing path. The `_process_row` and `_process_single_with_state` methods do not use `self._executor`. The only reference is in `close()` at line 518 where it is shutdown.

**Why it matters:** This is dead code that allocates thread pool resources (threads, memory) for no purpose. The actual concurrency is provided by the `BatchTransformMixin`'s worker pool (initialized in `connect_output` -> `init_batch_processing`). Having two thread pools creates confusion about which one handles what, and wastes resources.

**Evidence:**
```python
# Line 196-199: Created but never used for processing
if cfg.pool_config is not None:
    self._executor: PooledExecutor | None = PooledExecutor(cfg.pool_config)
else:
    self._executor = None

# Line 307-308: Processing goes through _process_row -> _process_single_with_state
# Neither method references self._executor
```

### [265-268] Recorder fallback in accept() bypasses on_start() contract

**What:** The `accept` method at lines 265-266 has a fallback to capture the recorder from `ctx.landscape` if `self._recorder` is None. This means `on_start()` (which sets the recorder, run_id, telemetry, and limiter) can be skipped entirely -- `accept()` will still work, but `self._run_id`, `self._telemetry_emit`, and `self._limiter` will be at their default/empty values.

**Why it matters:** If `on_start()` is not called (due to engine bug or test setup), the transform will proceed but with: (1) empty `run_id` in audit trail, (2) no-op telemetry emission, (3) no rate limiting. The partial state capture in `accept()` creates a false sense of safety -- it grabs the recorder but not the other required context.

**Evidence:**
```python
# Line 265-266: Partial fallback
if self._recorder is None and ctx.landscape is not None:
    self._recorder = ctx.landscape
# run_id, telemetry_emit, limiter NOT set here
```

### [463-464] Category mapping relies on fragile string manipulation

**What:** The Azure API category-to-internal-name mapping uses a string `lower()` + `replace()` chain. This is fragile: it depends on Azure returning exactly `"Hate"`, `"Violence"`, `"Sexual"`, and `"SelfHarm"`.

**Why it matters:** Any change in Azure API response format (e.g., `"self_harm"`, `"Self-Harm"`, or a new API version) will cause silent miscategorization. A lookup table mapping known Azure category strings to internal names would be explicit and verifiable, and would allow detection of unknown categories.

**Evidence:**
```python
category = item["category"].lower().replace("selfharm", "self_harm")
```

This transforms `"SelfHarm"` -> `"selfharm"` -> `"self_harm"`, but also transforms any string containing `"selfharm"` as a substring (e.g., hypothetical `"NotSelfHarm"` -> `"Notself_harm"`).

### [469-472] Malformed response wrapped as httpx.RequestError

**What:** When the Azure API response is malformed (missing `categoriesAnalysis` key, wrong types), the exception is wrapped as `httpx.RequestError` at line 472. This is semantically incorrect -- the HTTP request succeeded; it's the response content that is malformed.

**Why it matters:** The caller at line 355 treats `httpx.RequestError` as a network error and returns `retryable=True`. A malformed API response is not retryable -- the same request will get the same malformed response. Retrying wastes API calls and delays failure detection.

**Evidence:**
```python
except (KeyError, TypeError, ValueError) as e:
    raise httpx.RequestError(f"Malformed API response: {e}") from e
# Caller:
except httpx.RequestError as e:
    return TransformResult.error({...}, retryable=True)  # Will retry malformed response!
```

### [383-390] _get_fields_to_scan returns list[str] for "all" but may include non-string-value fields

**What:** When `self._fields == "all"`, the method returns all keys whose values are strings. But when `self._fields` is a list, it returns the configured list without checking whether those fields exist or have string values. The caller handles this, but the asymmetry means the method's return value has different semantic guarantees depending on the code path.

**Why it matters:** Minor inconsistency. The caller at lines 330-335 handles both cases correctly (checks existence and type). This is a readability/maintenance concern rather than a bug.

## Observations

### [131] Dual inheritance pattern (BaseTransform + BatchTransformMixin) is clean

The combination of `BaseTransform` for plugin contracts and `BatchTransformMixin` for concurrent processing is well-structured. The `process()` method correctly raises `NotImplementedError` directing callers to `accept()`.

### [166] API_VERSION class constant

The `API_VERSION = "2024-09-01"` class constant is good practice for Azure API versioning. However, it is hardcoded and not configurable, meaning an API version upgrade requires a code change rather than a config change.

### [201-204] HTTP client cache with lock is correct

The per-state_id HTTP client caching with `_http_clients_lock` correctly ensures thread safety for the concurrent worker pool. The cleanup in `_process_row`'s `finally` block (line 311-312) and in `close()` (lines 521-524) prevents client leaks.

### [474-508] Threshold checking is straightforward and correct

The `_check_thresholds` method uses direct field access on the validated `analysis` dict, which is correct per Tier 2 trust (we validated it at the boundary in `_analyze_content`). The comparison uses `>` (strictly greater than threshold), meaning a severity equal to the threshold is considered safe -- this is a design decision that should be documented for operators.

### [510-526] Close sequence is well-ordered

The close method shuts down batch processing first, then the pooled executor, then HTTP clients. This prevents new work from being submitted while cleanup proceeds. The lock-protected client cleanup is correct.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Two issues require immediate attention: (1) The fail-open category mapping must be replaced with an explicit lookup table that rejects unknown categories (fail closed). For a content safety transform, silently classifying unknown content as safe is a security defect. (2) The malformed-response-as-RequestError wrapping should be changed to return a non-retryable `TransformResult.error()` directly, rather than wrapping in a retryable exception type. Secondary issues: remove the unused `PooledExecutor`, and add audit trail logging when configured fields are skipped due to non-string type.
**Confidence:** HIGH -- The fail-open behavior is deterministic and reproducible by examining the category mapping logic. The unused executor is confirmed by searching all method bodies for `self._executor` references in the processing path. The retryable-malformed-response issue is confirmed by tracing the exception handling chain.
