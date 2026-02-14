# Plugins-Clients Bug Triage Notes (2026-02-14)

## Summary Table

| # | Bug | File | Original | Triaged | Verdict |
|---|-----|------|----------|---------|---------|
| 1 | CallReplayer.replay fabricates empty response for error calls missing hash | replayer.py | P1 | P2 | Downgraded |
| 2 | chat_completion catches all exceptions, misclassifies internal failures | llm.py | P1 | P1 | Confirmed |
| 3 | Failed redirect hop network errors not recorded as HTTP_REDIRECT calls | http.py | P1 | P1 | Confirmed |
| 4 | CallReplayer.replay suppresses malformed Tier-1 error_json values | replayer.py | P2 | P2 | Confirmed |
| 5 | CallVerifier.verify misclassifies successful calls with no response payload | verifier.py | P2 | P2 | Confirmed |
| 6 | Redirect hops in SSRF-safe mode bypass the configured rate limiter | http.py | P2 | P2 | Confirmed |
| 7 | Telemetry payloads/hashes emitted using mutable request objects | llm.py | P2 | P2 | Confirmed |

**Result:** 2 confirmed at P1, 1 downgraded (P1 to P2), 4 confirmed at P2.

## Detailed Assessments

### Bug 1: CallReplayer fabricates empty response for error calls (P1 -> P2)

The code path is real: when `response_hash` is `None` and `status == ERROR`, the check at line 215 evaluates `response_expected = False`, causing the fallback to `response_data = {}` at line 221 even if the call originally had a response. However, examining the production recording flow in `_call_recording.py`, when `response_data` is `None`, both `response_hash` and `response_ref` are `None` (lines 135, 145-147). The bug scenario requires `response_ref` to be set independently of `response_data`, which only happens when a caller explicitly passes `response_ref` as a kwarg -- no production caller does this. The standard flow ensures that if a response existed, `response_hash` is set (computed from `response_data` at line 135), which triggers the `response_expected` check correctly. This is a theoretical API-level gap, not a production path. The suggested fix (checking `response_ref` too) is correct defense-in-depth, but the scenario is unreachable through current code paths. Downgraded to P2.

### Bug 2: chat_completion catches all exceptions (P1 confirmed)

Genuine P1. The `try` block at line 318 spans the SDK call (line 319), response processing (lines 322-344), Landscape recording (lines 346-354), and telemetry emission (lines 358-387). The `except Exception` at line 397 catches everything and wraps it in `LLMClientError`. Downstream, non-retryable `LLMClientError` is converted to `TransformResult.error()` at `base.py:343`, which means internal bugs in response processing or audit recording get silently reclassified as "LLM call failed" row outcomes instead of crashing the pipeline. This directly violates the plugin ownership model: plugin bugs must crash, not be masked as external failures. Note that telemetry emission is already independently wrapped (lines 357-387), confirming the codebase recognizes this separation concern but didn't apply it to the main audit recording path.

### Bug 3: Failed redirect hop errors not recorded as HTTP_REDIRECT calls (P1 confirmed)

Genuine P1. In `_follow_redirects_safe()`, the `record_call` for each redirect hop (line 934) is placed after the `hop_client.get()` call (line 909). If the hop request raises (timeout, connection error, DNS failure), execution jumps to the outer `except` in `get_ssrf_safe()` (line 788), which records a `CallType.HTTP` error with the original request URL/IP -- not the redirect hop URL/IP. The actual outbound request to the redirect target is not recorded. This is a genuine audit completeness gap: a real network request was made but has no corresponding call record. For SSRF-safe mode specifically, this is particularly important because redirect hops may target different hosts/IPs.

### Bug 4: CallReplayer suppresses malformed Tier-1 error_json (P2 confirmed)

Confirmed P2. The truthiness check `if call.error_json:` at line 206 treats empty string `""` as falsey, silently skipping `json.loads()`. Per the project's trust model, `error_json` is Tier 1 data -- it is written by our own recorder as either canonical JSON or `None` (lines 150, 375 of `_call_recording.py`). An empty string would indicate data corruption and should crash per Tier 1 rules. The fix is changing to `if call.error_json is not None:`, which preserves the correct `None` check while letting `""` propagate to `json.loads()` where it will raise `JSONDecodeError` and surface the corruption.

### Bug 5: CallVerifier misclassifies SUCCESS calls with no response (P2 confirmed)

Confirmed P2. The verifier at line 223 uses `call.status == CallStatus.SUCCESS` as a signal that a response was expected, but production code explicitly allows successful calls with `response_data=None` (test at `test_context.py:913-925` verifies this). The `missing_payloads` counter is inflated by these legitimate no-response calls, producing false-positive drift signals. The fix should use `response_hash` and/or `response_ref` as evidence of expected response, not call status.

### Bug 6: Redirect hops bypass rate limiter (P2 confirmed)

Confirmed P2. Rate limiting is acquired once at the entry of `get_ssrf_safe()` (line 640), but each redirect hop in `_follow_redirects_safe()` makes an additional `hop_client.get()` call without acquiring the limiter. With `max_redirects` up to 10 (configurable), a single logical call could make 11 unthrottled requests. In practice, redirect chains longer than 2-3 hops are rare, and the default `max_redirects` is small, so the overshoot is bounded. Still a real gap for strict rate-limit compliance, particularly when targeting APIs that count redirects against quotas.

### Bug 7: Telemetry payloads emitted with mutable references (P2 confirmed)

Confirmed P2. In `chat_completion()`, `request_data` (built at line 295 with mutable `messages` list and `**kwargs`) and `response_data` (built at line 337) are passed directly into `ExternalCallCompleted` at lines 372-373 without deep-copy snapshotting. The telemetry event is queued for async export (confirmed via `manager.py` background thread at line 7). If any caller modifies `messages` or `kwargs` after `chat_completion()` returns (before async export processes the event), the exported data will differ from the computed hashes. The codebase already solved this exact problem in `PluginContext.record_call` (lines 333-335) using `copy.deepcopy()`, confirming this is a known risk class that was missed in `AuditedLLMClient`.

## Cross-Cutting Observations

### 1. Bugs 2 and 3 both stem from error-path audit gaps in external client wrappers

Bug 2 (LLM client) and Bug 3 (HTTP client) share a common pattern: the `except` block handles too broad a scope and doesn't distinguish between external failures and internal bugs. In Bug 2, the broad catch reclassifies internal errors. In Bug 3, the outer catch records the wrong call type/metadata. Both would benefit from narrower exception scopes that separate external call boundaries from internal processing.

### 2. Bugs 1 and 5 share the same root cause: inferring "response expected" from status

Both the replayer (Bug 1) and verifier (Bug 5) use `call.status == CallStatus.SUCCESS` as a proxy for "a response payload was expected." This heuristic is incorrect because successful calls can legitimately have no response payload. Both should use the actual payload indicators (`response_hash`, `response_ref`) instead of status.

### 3. Bug 7 follows a known pattern -- snapshot before async emission

The deep-copy fix applied in `PluginContext.record_call` was not propagated to `AuditedLLMClient.chat_completion()`. Any telemetry emission point that passes mutable dicts into async queues should snapshot at emission time. A systematic audit of all `telemetry_emit()` call sites would identify any other gaps.
