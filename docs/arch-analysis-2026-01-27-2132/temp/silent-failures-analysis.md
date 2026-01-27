# ELSPETH Silent Failure Pattern Analysis

**Date:** 2026-01-27
**Auditor:** Claude Opus 4.5 (Error Handling Specialist)
**Scope:** /home/john/elspeth-rapid/src/elspeth/**/*.py (133 files)

## Executive Summary

This audit examined the ELSPETH codebase for silent failure patterns that could cause undetected issues during pipeline execution. The codebase demonstrates **generally strong error handling discipline** consistent with its CLAUDE.md manifesto. However, several patterns require attention.

**Key Finding:** Most `except Exception` blocks in the codebase properly re-raise after recording or convert to structured error results. The architecture enforces this through the Three-Tier Trust Model. However, there are specific instances where defensive patterns could mask bugs.

---

## Critical Findings

### 1. CRITICAL: Defensive `.get()` on LLM Response Data

**Location:** `/home/john/elspeth-rapid/src/elspeth/plugins/llm/azure_batch.py:768-774`

```python
# Success - extract response
response = result.get("response", {})
body = response.get("body", {})
choices = body.get("choices", [])

if choices:
    content = choices[0].get("message", {}).get("content", "")
    usage = body.get("usage", {})
```

**Why Dangerous:**
This chain of `.get()` calls with empty default fallbacks violates the CLAUDE.md Three-Tier Trust Model for external data. When external API data is malformed:

- Missing `response` key silently becomes `{}`
- Missing `body` silently becomes `{}`
- Missing `choices` silently becomes `[]`
- The code then proceeds to the "no choices" branch, reporting `no_choices_in_response`

**Hidden Errors:**
- API format changes (Azure changes their response schema)
- Network corruption producing partial JSON
- Proxy servers injecting error responses
- Rate limiting responses with different structure

**User Impact:** Users will see "no_choices_in_response" errors when the actual problem is malformed API response structure. Debugging requires examining audit trail payloads, not error messages.

**Severity:** CRITICAL

**Recommendation:** Validate structure at boundary per CLAUDE.md Section "External Call Boundaries in Transforms":

```python
# IMMEDIATELY validate at the boundary
if not isinstance(result, dict):
    return TransformResult.error({
        "reason": "invalid_response_type",
        "expected": "dict",
        "actual": type(result).__name__
    })

if "response" not in result:
    return TransformResult.error({
        "reason": "missing_response_key",
        "available_keys": list(result.keys())
    })

response = result["response"]
if not isinstance(response, dict) or "body" not in response:
    return TransformResult.error({
        "reason": "invalid_response_structure",
        "response_type": type(response).__name__
    })
# ... continue with validated data
```

---

### 2. HIGH: Silent JSON Parse Fallback in HTTP Client

**Location:** `/home/john/elspeth-rapid/src/elspeth/plugins/clients/http.py:164-169`

```python
if "application/json" in content_type:
    try:
        response_body = response.json()
    except Exception:
        # If JSON decode fails, store as text
        response_body = response.text
```

**Why Dangerous:**
- The `except Exception` is too broad - catches all errors, not just JSON decode errors
- Content-Type says JSON but body is not JSON - this is a protocol violation that should be surfaced
- Silent fallback to text means the audit trail records text when JSON was expected
- Downstream transforms may fail cryptically when expecting parsed JSON

**Hidden Errors:**
- `MemoryError` if response is huge
- `UnicodeDecodeError` in some edge cases
- Actual API returning HTML error pages with JSON content-type
- Proxy/CDN error pages

**User Impact:** Transforms expecting parsed JSON will receive raw text strings. The error message will be about type mismatches, not about the actual JSON parsing failure.

**Severity:** HIGH

**Recommendation:**
```python
if "application/json" in content_type:
    try:
        response_body = response.json()
    except json.JSONDecodeError as e:
        # Record the parse failure explicitly - don't silently fallback
        response_body = {
            "_json_parse_error": str(e),
            "_raw_preview": response.text[:500] if response.text else None
        }
        # Mark this in metadata so callers can detect
```

---

### 3. HIGH: Silent Git SHA Fallback in Health Check

**Location:** `/home/john/elspeth-rapid/src/elspeth/cli.py:1584-1585`

```python
except Exception:
    git_sha = "unknown"
```

**Why Dangerous:**
- Broad `except Exception` catches all errors including:
  - `FileNotFoundError` (git not installed)
  - `PermissionError` (git dir inaccessible)
  - `OSError` (filesystem issues)
- Health check silently reports "warn" status with no indication of WHY
- Audit trail reproducibility depends on knowing exact code version

**Hidden Errors:**
- Git not installed in production environment
- Running from a tarball (not git checkout)
- Insufficient permissions
- Subprocess timeout

**User Impact:** The health check will show `"status": "warn", "value": "unknown"` but users won't know if it's because git isn't installed, permissions are wrong, or the repo is corrupted.

**Severity:** HIGH

**Recommendation:**
```python
except FileNotFoundError:
    git_sha = "git_not_installed"
except subprocess.TimeoutExpired:
    git_sha = "git_timeout"
except Exception as e:
    git_sha = f"error:{type(e).__name__}"
```

---

### 4. HIGH: Swallowed Checkpoint Callback Exception

**Location:** `/home/john/elspeth-rapid/src/elspeth/engine/executors.py:1644-1656`

```python
try:
    on_token_written(token)
except Exception as e:
    # Sink write is durable, can't undo. Log error and continue.
    # Operator must manually clean up checkpoint inconsistency.
    logger.error(
        "Checkpoint failed after durable sink write for token %s. "
        "Sink artifact exists but no checkpoint record created. "
        "Resume will replay this row (duplicate write). "
        "Manual cleanup may be required. Error: %s",
        token.token_id,
        e,
        exc_info=True,
    )
    # Don't raise - we can't undo the sink write
```

**Why Dangerous:**
- While the logging is excellent, the exception is swallowed
- The pipeline continues with corrupted checkpoint state
- On resume, these rows will be replayed causing duplicates
- This violates the "every decision traceable" audit principle

**Hidden Errors:**
- Database connection failures during checkpoint write
- Landscape table corruption
- Disk full during checkpoint

**User Impact:** Data duplication on resume with no automated detection. The log message is there but if not monitored, duplicates appear silently.

**Severity:** HIGH (mitigated by logging, but still creates silent data corruption)

**Recommendation:** While the catch is necessary (can't undo sink write), consider:
1. Track failed checkpoint tokens in run metadata
2. Add a post-run validation check for checkpoint integrity
3. Consider a RunCompleted event with `checkpoint_failures: int` field

---

### 5. MEDIUM: Defensive getattr for Schema Extraction

**Location:** `/home/john/elspeth-rapid/src/elspeth/plugins/manager.py:94-95`

```python
# Schemas vary by plugin type: sources have only output_schema,
# sinks have only input_schema, transforms have both.
input_schema = getattr(plugin_cls, "input_schema", None)
output_schema = getattr(plugin_cls, "output_schema", None)
```

**Why Problematic:**
- This is defensively accessing schema attributes that SHOULD exist based on plugin type
- If a transform is missing its `input_schema`, this returns `None` silently
- Later code may fail cryptically when schema hash is computed from `None`

**Justification for Pattern (Legitimate Use):**
- Different plugin types have different schema requirements
- Sources only have `output_schema`, sinks only have `input_schema`
- This is polymorphism, not bug-hiding

**Recommendation:** While this is a legitimate use per CLAUDE.md (framework boundary), it should be accompanied by validation:

```python
# Extract schemas based on plugin type
if node_type == "transform":
    if not hasattr(plugin_cls, "input_schema"):
        raise TypeError(f"Transform {name} missing required input_schema")
    if not hasattr(plugin_cls, "output_schema"):
        raise TypeError(f"Transform {name} missing required output_schema")
# ...etc for other types
```

**Severity:** MEDIUM

---

### 6. MEDIUM: Defensive getattr for batch_id in Azure Batch

**Location:** `/home/john/elspeth-rapid/src/elspeth/plugins/llm/azure_batch.py:530`

```python
"output_file_id": getattr(batch, "output_file_id", None),
```

**Why Problematic:**
- If the Azure SDK changes and `output_file_id` is no longer present, this silently returns `None`
- The audit trail then lacks the file ID, making replay/verification impossible
- The SDK promises this field exists on completed batches

**Hidden Errors:**
- Azure SDK version mismatch
- Wrong batch status (checking file_id before batch completes)
- SDK breaking changes

**Justification:** This may be defensive against optional SDK fields.

**Recommendation:** Either trust the SDK contract and access directly, or explicitly handle the case:

```python
if hasattr(batch, "output_file_id"):
    output_file_id = batch.output_file_id
else:
    # Explicit handling for SDK versions that don't have this field
    logger.warning("Azure SDK batch missing output_file_id - may be incomplete batch")
    output_file_id = None
```

**Severity:** MEDIUM

---

### 7. MEDIUM: Usage Token Extraction with Defaults

**Location:** `/home/john/elspeth-rapid/src/elspeth/plugins/clients/llm.py:45`

```python
def total_tokens(self) -> int:
    """Total tokens used (prompt + completion)."""
    return self.usage.get("prompt_tokens", 0) + self.usage.get("completion_tokens", 0)
```

**Why Problematic:**
- If usage dict doesn't have these keys, we silently return 0
- This could be a malformed LLM response (external data boundary)
- Cost tracking and billing would be incorrect with 0 tokens

**Justification:** This is accessing external LLM response data, so some defense is warranted per Trust Model.

**Recommendation:** Validate at the point where `usage` dict is populated, not where it's accessed:

```python
# At population time:
if "prompt_tokens" not in usage or "completion_tokens" not in usage:
    logger.warning("LLM response missing usage tokens", usage_keys=list(usage.keys()))
```

**Severity:** MEDIUM

---

### 8. LOW: Empty pass in Lifecycle Hooks

**Location:** `/home/john/elspeth-rapid/src/elspeth/plugins/base.py:100, 110, 117, etc.`

```python
def close(self) -> None:  # noqa: B027 - optional override, not abstract
    """Clean up resources after pipeline completion."""
    pass

def on_start(self, ctx: PluginContext) -> None:  # noqa: B027 - optional hook
    """Called at the start of each run."""
    pass
```

**Why Not Problematic:**
- These are intentionally empty base class hooks
- The `noqa: B027` comments document intentionality
- Subclasses override these when needed
- This is standard Template Method pattern

**Severity:** LOW (not a bug, documented pattern)

---

### 9. LOW: config.get("fork_to") in Base Gate

**Location:** `/home/john/elspeth-rapid/src/elspeth/plugins/base.py:162-163`

```python
# fork_to is optional - None is valid (most gates don't fork)
fork_to = config.get("fork_to")
self.fork_to = list(fork_to) if fork_to is not None else None
```

**Why Not Problematic:**
- Documented as optional
- `fork_to` being absent means "no forking" which is valid
- Direct access (`config["fork_to"]`) would crash for non-forking gates

**Severity:** LOW (legitimate optional configuration)

---

## Patterns That Are CORRECT

The following patterns were examined and found to be correctly implemented:

### 1. Executor Exception Handling

**Location:** `/home/john/elspeth-rapid/src/elspeth/engine/executors.py:272-308`

```python
except Exception as e:
    duration_ms = (time.perf_counter() - start) * 1000
    # Record failure
    error: ExecutionError = {
        "exception": str(e),
        "type": type(e).__name__,
    }
    self._recorder.complete_node_state(
        state_id=state.state_id,
        status="failed",
        duration_ms=duration_ms,
        error=error,
    )
    # ... then re-raises
    raise
```

**Assessment:** CORRECT - Records failure in audit trail, then re-raises. Exception is never swallowed.

### 2. Orchestrator Phase Error Handling

**Location:** `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator.py:485-487`

```python
except Exception as e:
    self._events.emit(PhaseError(phase=PipelinePhase.DATABASE, error=e))
    raise  # CRITICAL: Always re-raise - database connection failure is fatal
```

**Assessment:** CORRECT - Emits event for observability, then re-raises. Explicit comment explains rationale.

### 3. External API Error Handling in Azure Batch

**Location:** `/home/john/elspeth-rapid/src/elspeth/plugins/llm/azure_batch.py:415-425`

```python
except Exception as e:
    # External API failure - record error and return structured result
    ctx.record_call(
        call_type=CallType.HTTP,
        request_data={"file_size": len(jsonl_content)},
        status=CallStatus.ERROR,
        error=str(e),
        latency_ms=(time.perf_counter() - start) * 1000,
    )
    return TransformResult.error({
        "reason": "upload_failed",
        "error": str(e),
    })
```

**Assessment:** CORRECT - External boundary exception converted to structured error result. This is proper Tier 3 handling per CLAUDE.md.

### 4. hasattr for Type Checking

**Location:** `/home/john/elspeth-rapid/src/elspeth/contracts/results.py:239-242`

```python
if not hasattr(url, "sanitized_url") or not hasattr(url, "fingerprint"):
    raise TypeError(
        "url must be a SanitizedDatabaseUrl instance..."
    )
```

**Assessment:** CORRECT - This is type enforcement at a contract boundary, not bug-hiding. It immediately raises if the wrong type is passed.

---

## Summary of Required Actions

| Priority | Count | Description |
|----------|-------|-------------|
| CRITICAL | 1 | LLM response `.get()` chain needs boundary validation |
| HIGH | 3 | JSON fallback, git fallback, checkpoint swallowing |
| MEDIUM | 3 | Schema extraction, Azure batch, usage tokens |
| LOW | 2 | Documented as intentional, no action needed |

## Recommendations

1. **Immediate:** Fix the azure_batch.py `.get()` chain (Finding #1) - this is the most likely to cause debugging nightmares

2. **Short-term:** Add explicit error types to the git health check (Finding #3)

3. **Medium-term:** Review all `.get()` usage on external API responses to ensure boundary validation happens BEFORE defensive access

4. **Documentation:** The codebase would benefit from a "Boundary Validation Patterns" section in CLAUDE.md showing correct vs incorrect patterns for each tier

---

*Generated by Claude Opus 4.5 Error Handling Audit Agent*
