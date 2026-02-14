# Plugins-LLM Bug Triage Notes (2026-02-14)

## Summary Table

| # | Bug | File | Original | Triaged | Verdict |
|---|-----|------|----------|---------|---------|
| 1 | Azure multi-query unhandled missing-field KeyError crashes pipeline | azure_multi_query.py | P1 | P1 | Confirmed |
| 2 | Azure _process_row uses mutable ctx.state_id in cleanup (wrong cache eviction) | azure.py | P1 | P2 | Downgraded |
| 3 | BaseLLMTransform adds fields but does not set transforms_adds_fields=True | base.py | P1 | P1 | Confirmed |
| 4 | BaseLLMTransform output_schema diverges from output_schema_config guaranteed_fields | base.py | P1 | P2 | Downgraded |
| 5 | enable_content_recording accepted/logged but never applied in Azure Monitor setup | azure.py | P1 | P2 | Downgraded |
| 6 | __init__.py allows invalid contract field bases (hyphens, spaces, leading digits) | __init__.py | P1 | P2 | Downgraded |
| 7 | Malformed Azure batch response body (not dict) crashes instead of row error | azure_batch.py | P1 | P1 | Confirmed |
| 8 | Multi-query cross-product output_prefix collisions from delimiter ambiguity | multi_query.py | P1 | P2 | Downgraded |
| 9 | OpenRouter batch HTTP clients cached by state_id, never evicted per batch | openrouter_batch.py | P1 | P2 | Downgraded |
| 10 | OpenRouter batch successful rows misclassified when input has "error" field | openrouter_batch.py | P1 | P1 | Confirmed |
| 11 | OpenRouter multi-query JSON parsing allows NaN/Infinity, crashes canonical hashing | openrouter_multi_query.py | P1 | P1 | Confirmed (related to known P0) |
| 12 | OpenRouter multi-query malformed response shapes trigger uncaught exceptions | openrouter_multi_query.py | P1 | P1 | Confirmed |
| 13 | OpenRouter reparses JSON permissively, does not validate usage finiteness | openrouter.py | P1 | P1 | Confirmed (related to known P0) |
| 14 | PromptTemplate allows in-template mutation of shared lookup and raw row | templates.py | P1 | P1 | Confirmed |
| 15 | Terminal batch failures clear checkpoint without per-row LLM call recording | azure_batch.py | P1 | P2 | Downgraded |
| 16 | _validate_field_type accepts non-finite floats for number outputs | base_multi_query.py | P1 | P1 | Confirmed (related to known P0) |
| 17 | validate_tracing_config crashes with TypeError on unhashable provider value | tracing.py | P1 | P2 | Downgraded |
| 18 | validate_tracing_config only checks None; empty strings and wrong types pass | tracing.py | P1 | P2 | Downgraded |
| 19 | _init_multi_query computes enriched output_schema_config but sets output_schema to input | base_multi_query.py | P2 | P2 | Confirmed |
| 20 | Response truncated detection based only on token-count threshold | azure_multi_query.py | P2 | P2 | Confirmed |

**Result:** 11 confirmed at original priority (9 P1, 2 P2), 9 downgraded (all P1 -> P2), 0 closed.

## Detailed Assessments

### Bug 1: Azure multi-query unhandled missing-field KeyError (P1 confirmed)

Genuine P1. `_process_single_query` at line 188 calls `spec.build_template_context(row)` outside any try/except. The `build_template_context` method at `multi_query.py:113-114` explicitly raises `KeyError` when `field_name not in row`. The source comment says "missing field is a config error, should crash" but this conflicts with the Three-Tier Trust Model: row data is Tier 2 post-source, and missing fields are a data-quality issue that should produce a row-level error (quarantine), not crash the pipeline. The `try/except` around template rendering starts at line 191, AFTER the context build.

### Bug 2: Azure _process_row mutable ctx.state_id in cleanup (P1 -> P2)

The race condition is theoretically real. `AzureLLMTransform` uses `BatchTransformMixin` (worker threads), and `_process_row` reads `ctx.state_id` at line 447 for client creation, then uses it again at line 519 in the `finally` block for cache eviction. If a timeout causes the executor to set a new `ctx.state_id` for a retry while the prior worker is still finishing, the `finally` block would pop the wrong cache entry. However, this requires a very specific timing sequence (timeout race with worker completion) and the practical impact is a resource leak (wrong client evicted), not data corruption or audit integrity loss. The fix (snapshot `state_id` at function entry) is a one-liner. Downgraded to P2 because the blast radius is limited to resource management under stress, not correctness.

### Bug 3: BaseLLMTransform does not set transforms_adds_fields=True (P1 confirmed)

Genuine P1. `BaseLLMTransform` adds `response_field`, `_model`, `_usage`, and audit fields at lines 350-360, and internally calls `propagate_contract(transform_adds_fields=True)` at line 366. But the class attribute `transforms_adds_fields` is inherited as `False` from `BaseTransform` (base.py:154). The executor at `transform.py:335` uses `transform.transforms_adds_fields` to decide whether to persist the evolved output contract. So the contract is computed internally but never persisted to the audit trail. The `BaseMultiQueryTransform` correctly sets `transforms_adds_fields = True` (base_multi_query.py:61), confirming this is an oversight in `BaseLLMTransform`. This is an audit trail completeness gap -- node schema evolution is silently absent.

### Bug 4: BaseLLMTransform output_schema diverges from output_schema_config (P1 -> P2)

The divergence is real: `output_schema` is set equal to `input_schema` (line 247), while `_output_schema_config` includes LLM-added guaranteed fields (lines 257-263). DAG validation uses both: `output_schema_config` for guaranteed-field contract checks and `output_schema` for type compatibility. However, the practical impact is limited to explicit-schema pipelines where a downstream transform requires LLM-added fields in its `required_input_fields`. In the much more common `dynamic` schema mode, this divergence has no effect because dynamic schemas accept any fields. Additionally, the `_output_schema_config` guaranteed fields DO correctly declare what the transform emits, so DAG validation at the contract level works. The type-level schema mismatch only surfaces in uncommon explicit configurations. Downgraded to P2.

### Bug 5: enable_content_recording dead config field (P1 -> P2)

Confirmed: `enable_content_recording` is accepted in config (tracing.py:77, 135), logged as active (azure.py:320), but never passed to `configure_azure_monitor()` (azure.py:764-767). The Azure Monitor SDK does not have this parameter at all (SDK signature is `**kwargs` with no `enable_content_recording` documented). This is a dead config field that misleads operators. However, this is a config-to-runtime orphaning issue with no data corruption or audit integrity risk -- it's a misleading UX problem, not a correctness bug. Downgraded to P2.

### Bug 6: __init__.py allows invalid contract field bases (P1 -> P2)

The validation gap is real: `get_llm_guaranteed_fields` only rejects empty/whitespace strings, not non-identifier strings. A `response_field` like `"bad-field"` would produce field names like `"bad-field_usage"` that violate `SchemaConfig` identifier rules. However, `response_field` is a Pydantic `Field` with default `"llm_response"` and no validator allows arbitrary strings. The practical attack surface requires a user to deliberately configure `response_field` with invalid characters in their YAML, which is an unusual configuration error. The Pydantic layer accepts it (no validator), but this is a config validation gap, not a runtime data corruption risk. The fix (add `isidentifier()` check) is straightforward. Downgraded to P2 because the blast radius is limited to misconfigured pipelines, not silent data loss.

### Bug 7: Malformed Azure batch response body (not dict) crashes (P1 confirmed)

Genuine P1. The Tier 3 boundary validation at lines 1024-1032 checks that `response` is a dict and contains `"body"`, but does NOT check that `response["body"]` is a dict. Later at line 1164, `body.get("choices")` is called on the unvalidated `body`, which would crash with `AttributeError` if `body` is a list or other non-dict type. This is an incomplete boundary validation gap: the code validates one level but not the next. A single malformed external response line can crash the entire batch processing. The fix (add `isinstance(response["body"], dict)` check) is straightforward.

### Bug 8: Multi-query cross-product output_prefix collisions (P1 -> P2)

The collision detection gap is real: `validate_multi_query_key_collisions` checks for duplicate case_study names, duplicate criterion names, duplicate output_mapping suffixes, and reserved suffix conflicts -- but not the generated cross-product prefix `f"{case_study.name}_{criterion.name}"`. So `(a_b, c)` and `(a, b_c)` both generate prefix `a_b_c` and silently overwrite each other. However, this requires a deliberately adversarial naming convention with embedded underscores that create ambiguity. In practice, case study and criterion names are semantic labels (e.g., "toxicity", "relevance"), making collisions unlikely without deliberate intent. The fix is straightforward (add prefix uniqueness check). Downgraded to P2 because the collision requires unlikely naming patterns.

### Bug 9: OpenRouter batch HTTP clients never evicted per batch (P1 -> P2)

The resource leak is real: `_http_clients` grows with each new `state_id` (one per batch flush) and is only cleaned up in `close()`. For long-running jobs with many aggregation flushes, this accumulates clients. However, each `AuditedHTTPClient` is lightweight (wraps `httpx.Client`), and the leak is bounded by the number of batches processed. The clients ARE eventually cleaned up at `close()`. This is a resource management concern, not a correctness or audit integrity issue. For typical runs (tens to hundreds of batches), the impact is negligible. Only extremely long-running streaming jobs with thousands of batches would see material impact. Downgraded to P2.

### Bug 10: OpenRouter batch successful rows misclassified when input has "error" field (P1 confirmed)

Genuine P1. The sentinel check at line 510 (`"error" in result`) uses key-presence in a dict that includes all of `row.to_dict()`. If the input row has a field named `"error"` (perfectly valid user data), successful results are misclassified as failures: `llm_response` is overwritten to `None`, and the actual LLM output is silently dropped. This is silent data loss triggered by user data shape -- exactly the kind of Tier 2 data variance that should be handled correctly. The fix requires using a collision-proof internal result type instead of key-presence detection.

### Bug 11: OpenRouter multi-query JSON parsing allows NaN/Infinity (P1 confirmed, related to known P0)

Genuine P1. `openrouter_multi_query.py:350` uses plain `json.loads(content_str)` which accepts `NaN` and `Infinity`. By contrast, `azure_multi_query.py:297` uses `validate_json_object_response()` which calls `json.loads` with `parse_constant=_reject_nonfinite_constant`. So the Azure path is protected but the OpenRouter path is not. Non-finite floats pass `_validate_field_type` (Bug 16) and reach `stable_hash()` which crashes with `ValueError`. This is directly related to the known P0 "NaN/Infinity accepted in float validation undermines RFC 8785" but describes the specific OpenRouter multi-query attack vector. The `validation.py` module exists with the correct pattern but is not used here.

### Bug 12: OpenRouter multi-query malformed response shapes trigger uncaught exceptions (P1 confirmed)

Genuine P1. `_process_single_query` at line 290 extracts `content = choices[0]["message"]["content"]` inside a try/except that catches `KeyError, IndexError, TypeError`. But `content` is then used at line 339 as `content.strip()` OUTSIDE that try/except. If content is a dict or list (not None, not str), `.strip()` raises `AttributeError` which is uncaught and crashes the transform. Similarly, `usage = data.get("usage") or {}` at line 316 does not validate that `usage` is a dict before calling `.get()` on it. If `usage` is a list (truthy, not coerced to `{}`), `.get()` raises `AttributeError`. These are incomplete Tier 3 boundary validations on external response fields.

### Bug 13: OpenRouter reparses JSON permissively, does not validate usage finiteness (P1 confirmed, related to known P0)

Genuine P1. `openrouter.py:593` uses `response.json()` (httpx's permissive parser) which accepts NaN/Infinity. The `usage` dict at line 652 is written directly to output without finiteness validation. Later, `stable_hash(result.row)` at `transform.py:292` crashes with `ValueError` on non-finite floats. This is the same NaN/Infinity P0 vector but in the single-row OpenRouter path. The `response.json()` call should use strict parsing (or the validated `response.text` with `json.loads` + `parse_constant`).

### Bug 14: PromptTemplate allows in-template mutation of shared lookup and raw row (P1 confirmed)

Genuine P1. I reproduced this directly: `SandboxedEnvironment` permits `dict.update()` calls in templates, so a template like `{% set _ = lookup.update({'k': 'changed'}) %}` mutates the shared `self._lookup_data` object. Subsequent renders see the mutated state. The audit `lookup_hash` is computed once at init and never updated, creating hash/content divergence. `ImmutableSandboxedEnvironment` (available in jinja2, verified present) correctly blocks this. The row mutation vector is also confirmed: when `contract is None`, raw dict is passed through, and template-side mutation affects the `variables_hash` computation. Thread-safety amplifies this for pooled transforms.

### Bug 15: Terminal batch failures clear checkpoint without per-row LLM call recording (P1 -> P2)

The gap is real: on terminal non-completed batch statuses (failed, cancelled, expired, timeout), per-row `CallType.LLM` records are never emitted before `_clear_checkpoint(ctx)` erases the request context. Only the completed path at `_download_results:1230-1262` records per-row calls. However, the batch-level failure IS recorded (as `TransformResult.error`), and the batch job IS recorded in Langfuse. The missing per-row records are a completeness gap in audit granularity, not a data corruption or silent failure. Operators can still determine that the batch failed and why, just not the per-row decomposition. Downgraded to P2 because the failure is visible at batch level.

### Bug 16: _validate_field_type accepts non-finite floats for number outputs (P1 confirmed, related to known P0)

Genuine P1. `_validate_field_type` at `base_multi_query.py:521-525` checks `isinstance(value, (int, float))` for `NUMBER` type but does not reject `math.isnan(value)` or `math.isinf(value)`. The `INTEGER` path at line 516 has the same issue: `isinstance(value, float) and value.is_integer()` accepts `float('inf')` (which passes `is_integer()` -> no, actually `float('inf').is_integer()` returns False in Python). But `float('nan').is_integer()` also returns False. So the INTEGER path is actually safe. The NUMBER path IS vulnerable: `float('nan')` passes `isinstance(value, float)` and enters output. This is the validation-layer component of the known P0.

### Bug 17: validate_tracing_config crashes with TypeError on unhashable provider (P1 -> P2)

The crash is real: `config.provider not in SUPPORTED_TRACING_PROVIDERS` raises `TypeError` if `provider` is a dict or list (unhashable). However, `parse_tracing_config` at line 129-146 uses `provider` in a `match` statement. In Python, `match provider:` with `case "azure_ai"` / `case "langfuse"` / `case _` handles all cases: a dict value falls through to the default case and creates `TracingConfig(provider={"bad": "type"})`. So the crash only occurs if someone passes a dict/list as the provider value in their config YAML. This is a config trust-boundary issue, but the YAML would need to be `provider: {bad: type}` which is unusual. Downgraded to P2 because the trigger requires unusual YAML configuration.

### Bug 18: validate_tracing_config only checks None (P1 -> P2)

The gap is real: validation only rejects `None` for credentials (lines 165-172), not empty strings or wrong types. `connection_string=""`, `public_key=123`, etc. all pass validation. The SDK constructors then receive these invalid values and may fail with poor diagnostics. However, the practical risk is limited: tracing is optional and only affects observability, not pipeline correctness or audit integrity. Bad tracing config causes SDK initialization failures that are caught by the `except ImportError` blocks and logged as warnings. Downgraded to P2 because impact is limited to observability setup, not data integrity.

### Bug 19: _init_multi_query output_schema diverges from output_schema_config (P2 confirmed)

Same pattern as Bug 4 but for multi-query transforms. `output_schema` is set to `input_schema` (line 131), while `_output_schema_config` includes all generated multi-query fields (lines 116-122). However, `BaseMultiQueryTransform` correctly sets `transforms_adds_fields = True` (line 61), so the evolved contract IS persisted -- unlike Bug 3. The divergence affects DAG type-level validation in explicit-schema mode only. Confirmed at P2.

### Bug 20: Response truncated detection based only on token-count threshold (P2 confirmed)

The heuristic is suboptimal: `completion_tokens >= effective_max_tokens` can flag complete responses as truncated (e.g., when a response naturally uses exactly `max_tokens` tokens). The `finish_reason` field is available in the raw response and would give a definitive truncation signal. However, false positives here mean a valid response is retried or errored -- the audit trail remains correct (the error reason is recorded). No silent data corruption. Confirmed at P2.

## Cross-Cutting Observations

### 1. NaN/Infinity (Bugs 11, 13, 16) form a coherent cluster related to known P0

Three bugs describe the same root cause from different angles: non-finite floats entering pipeline data from LLM responses. Bug 16 is the validation layer gap, Bug 11 is the OpenRouter multi-query JSON parsing gap, Bug 13 is the OpenRouter single-row JSON parsing gap. Azure multi-query is protected by `validate_json_object_response()` but Azure single-row (`azure.py`) goes through `AuditedLLMClient` which uses `litellm`, making it a different vector. The fix should be coordinated: add `math.isfinite` check in `_validate_field_type`, use `parse_constant` rejection in all `json.loads` calls, and validate `usage` values for finiteness.

### 2. Schema divergence (Bugs 3, 4, 19) share a systemic pattern

All three LLM base classes have the same issue: `output_schema` is set equal to `input_schema`, but the transform actually emits additional fields. `BaseMultiQueryTransform` at least sets `transforms_adds_fields = True` (Bug 3 fix is not applied to `BaseLLMTransform`). The `_output_schema_config` enrichment is computed but `output_schema` is not updated to match. A systematic fix should align both schema representations in all LLM base classes.

### 3. Tracing validation (Bugs 5, 17, 18) affect observability setup, not data integrity

All three tracing bugs affect the optional tracing subsystem. The impact is limited to misleading configuration, poor diagnostics, or SDK initialization crashes -- none affect pipeline correctness or audit trail integrity. They are all appropriately P2.

### 4. Template mutation (Bug 14) is the most immediately dangerous

The template mutation vulnerability is easily triggered by any template using `lookup.update(...)` and breaks both audit hash integrity and cross-row isolation. The fix (`ImmutableSandboxedEnvironment`) is a one-line change with high impact. This should be fixed first.
