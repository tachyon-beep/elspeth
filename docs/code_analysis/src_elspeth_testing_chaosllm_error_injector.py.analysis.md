# Analysis: src/elspeth/testing/chaosllm/error_injector.py

**Lines:** 488
**Role:** Error injection engine for ChaosLLM. Decides per-request whether to inject an error, what kind, and how (HTTP-level, connection-level, or malformed response). Includes a burst state machine that periodically elevates error rates.
**Key dependencies:** Imports `ErrorInjectionConfig` from `chaosllm.config`. Consumed by `chaosllm.server.ChaosLLMServer` which calls `decide()` on every request. `ErrorDecision` and exported constants (`HTTP_ERRORS`, `CONNECTION_ERRORS`, `MALFORMED_TYPES`) are used by server, tests, and response generators.
**Analysis depth:** FULL

## Summary

This file is well-structured with clean separation of concerns. The `ErrorDecision` frozen dataclass and `ErrorInjector` class are coherent and readable. However, there is one significant thread-safety issue in `decide()` where the RNG is used outside the lock, and a subtle statistical bias in the priority-mode evaluation chain. The weighted mode has a minor edge-case floating-point issue but is generally correct. Overall confidence is HIGH -- the code is solid for a testing tool.

## Critical Findings

### [262-293] RNG is not thread-safe despite documented thread-safety

**What:** The class docstring says "Thread-safe implementation" (line 151), and `_get_current_time()` correctly uses `self._lock` to protect `_start_time`. However, `self._rng` (a `random.Random` instance) is accessed without any locking throughout `decide()`, `_decide_priority()`, `_decide_weighted()`, and all `_pick_*` methods. `random.Random` is not thread-safe -- concurrent calls to `.random()`, `.randint()`, `.uniform()` on the same instance from multiple threads can corrupt its internal Mersenne Twister state, producing non-random output or raising exceptions.

**Why it matters:** The ChaosLLM server uses Starlette with uvicorn, which can be configured with multiple workers. Even with a single worker, Starlette's async handling with thread pool executors can invoke `decide()` from multiple threads concurrently. Corrupted RNG state could cause: (1) the injector to stop producing errors entirely, (2) deterministic test failures that are irreproducible, or (3) in pathological cases, infinite loops inside the Mersenne Twister.

**Evidence:** Lines 178-179 create `self._rng` as a bare `random.Random()` instance. Lines 262-273 (`_should_trigger`), 226-227 (`_pick_retry_after`), 230-232 (`_pick_timeout_delay`), etc. all call `self._rng.random()`, `self._rng.randint()`, `self._rng.uniform()` without holding `self._lock`. The lock on lines 187-191 only protects `self._start_time`, not the RNG.

## Warnings

### [295-395] Priority mode has inherent statistical bias from sequential evaluation

**What:** In `_decide_priority()`, errors are evaluated sequentially with early-return. Each `_should_trigger(pct)` call is an independent Bernoulli trial. This means the probability of reaching later checks is conditional on all earlier checks failing. For example, if `connection_failed_pct=5` and `connection_stall_pct=5`, the effective probability of connection_stall is not 5% but rather `0.95 * 0.05 = 4.75%`. With many error types configured, the effective rates for later error types will be significantly lower than their configured percentages.

**Why it matters:** Users configuring `rate_limit_pct=10` might expect ~10% of requests to get 429s, but if connection-level errors are also configured, the effective rate will be lower. This is partially documented by the docstring saying "first matching error wins" and "priority order", but the implication for effective rates is not explicitly called out. In chaos testing, predictable error distributions matter.

**Evidence:** The evaluation chain on lines 301-395 has 18 sequential `if self._should_trigger(...)` checks. Each is independent, but the early-return pattern means later ones only fire if all preceding ones did not. The `selection_mode="weighted"` alternative (line 291) exists to address this, but `"priority"` is the default.

### [397-477] Weighted mode: total weight exceeding 100% produces unintuitive behavior

**What:** In `_decide_weighted()`, `success_weight` is computed as `max(0.0, 100.0 - total_weight)` (line 466). When the sum of configured percentages exceeds 100, `success_weight` clamps to 0, meaning every request will produce an error. This is mathematically correct but potentially surprising -- a user could configure `rate_limit_pct=60` and `timeout_pct=60` (total 120) and get zero successful requests.

**Why it matters:** There is no validation in `ErrorInjectionConfig` that the sum of all percentages does not exceed 100, and the weighted mode silently absorbs the over-allocation. For a testing tool this is unlikely to cause production issues, but it could cause confusion during test configuration.

**Evidence:** Line 462 computes `total_weight = sum(weight for weight, _ in choices)`. Line 466 computes `success_weight = max(0.0, 100.0 - total_weight)`. No warning or validation is emitted when `total_weight > 100`.

### [193-210] Burst period calculation depends on interval being larger than duration

**What:** `_is_in_burst()` checks if `position_in_interval < duration` (line 210). If `duration_sec >= interval_sec`, the system is permanently in burst mode. The `BurstConfig` Pydantic model validates `interval_sec > 0` and `duration_sec > 0` but does not validate `duration_sec < interval_sec`.

**Why it matters:** A misconfiguration like `interval_sec=5, duration_sec=10` would silently cause permanent burst mode with no non-burst windows, which defeats the purpose of burst simulation. The modulo arithmetic would still work but the result would always be `True`.

**Evidence:** `BurstConfig` in config.py (lines 150-180) has no cross-field validation between `interval_sec` and `duration_sec`. The `_is_in_burst` method (lines 193-210) would return `True` for every call when `duration >= interval`.

## Observations

### [20-111] ErrorDecision is a well-designed frozen dataclass

The `ErrorDecision` class uses named constructors (`success()`, `http_error()`, `connection_error()`, `malformed_response()`) which provide clear, self-documenting instantiation. The `frozen=True, slots=True` pattern is correct and consistent with ELSPETH conventions. No issues found.

### [113-144] Exported constant sets provide good documentation of the error taxonomy

`HTTP_ERRORS`, `CONNECTION_ERRORS`, and `MALFORMED_TYPES` are clearly defined and well-commented as being for external consumers. These serve as the authoritative list of supported error types.

### [479-487] reset() and is_in_burst() are clean observability methods

Both methods are straightforward. `reset()` correctly acquires the lock to clear `_start_time`. `is_in_burst()` is read-only and suitable for health check endpoints.

### Thread-safety scope note

The `_get_current_time()` method (lines 185-191) acquires the lock to protect `_start_time` initialization. This is correct for its purpose. However, the broader `decide()` method calls `_get_current_time()` then proceeds to call `_is_in_burst()` and multiple `_should_trigger()` calls outside any lock. The time-related state is protected, but the RNG is not (noted as Critical above).

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Fix the RNG thread-safety issue. The simplest approach would be to either (a) use a `threading.Lock` around all RNG access in `decide()`, or (b) document that `decide()` is not thread-safe and must be called from a single thread. Optionally validate `duration_sec < interval_sec` in `BurstConfig`. The priority-mode statistical bias should be documented clearly for users.
**Confidence:** HIGH -- I have read the full file, its configuration model, and the server that consumes it. The thread-safety issue is concrete and verifiable from the code.
