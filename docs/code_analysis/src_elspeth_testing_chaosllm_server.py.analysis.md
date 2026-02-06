# Analysis: src/elspeth/testing/chaosllm/server.py

**Lines:** 747
**Role:** ChaosLLM mock server -- a Starlette ASGI application that simulates an LLM API endpoint with configurable chaos injection (errors, latency, malformed responses) for testing pipeline resilience. Provides OpenAI and Azure OpenAI compatible endpoints plus admin endpoints for runtime configuration, metrics, and reset.
**Key dependencies:** Imports `ChaosLLMConfig`, `ErrorInjectionConfig`, `LatencyConfig`, `ResponseConfig` from `config.py`; `ErrorDecision`, `ErrorInjector` from `error_injector.py`; `LatencySimulator` from `latency_simulator.py`; `MetricsRecorder` from `metrics.py`; `ResponseGenerator` from `response_generator.py`. Used by Starlette/uvicorn, the chaosllm CLI (`cli.py`), the pytest fixture (`tests/fixtures/chaosllm.py`), and `tests/stress/conftest.py`.
**Analysis depth:** FULL

## Summary

The server is well-designed with clean separation between error injection, latency simulation, response generation, and metrics recording. The request handling flow is clear and well-documented. However, there are significant security concerns: the admin endpoints have zero authentication (allowing arbitrary runtime reconfiguration and data export from any network client), and the Jinja2 template override header enables server-side template injection from any request. There is also a race condition in `update_config()` where component replacement is not atomic, and the `_handle_completion_request` method performs synchronous (blocking) SQLite writes inside async handlers. Confidence is HIGH.

## Critical Findings

### [282-283] Server-Side Template Injection (SSTI) via X-Fake-Template header

**What:** Any HTTP client can pass arbitrary Jinja2 templates via the `X-Fake-Template` request header. The server renders these templates using a Jinja2 environment that has `autoescape=False` (confirmed in `response_generator.py` line 415) and exposes custom helper functions including `random_int`, `random_float`, `random_words`, and `timestamp`. While the Jinja2 environment uses `StrictUndefined` (preventing access to undefined variables), the template rendering still has access to Python's string methods and could potentially be used for information disclosure.

**Why it matters:** ChaosLLM is described as "deployed as a real HTTP server that ELSPETH pipelines connect to during integration/chaos testing." If it's accessible on any network interface (the default `ServerConfig.host` is `127.0.0.1` but this can be overridden to `0.0.0.0`), any client that can reach the server can inject templates. While Jinja2's sandboxing without explicit `SandboxedEnvironment` is not a full sandbox, the risk is mitigated by the limited globals exposed. However, Jinja2 without `SandboxedEnvironment` allows access to `__class__`, `__subclasses__()`, etc., which can be leveraged for arbitrary code execution in classic SSTI attacks.

**Evidence:**
```python
# server.py line 282-283: Header directly used as template input
mode_override = request.headers.get("X-Fake-Response-Mode")
template_override = request.headers.get("X-Fake-Template")

# response_generator.py line 415: Not a SandboxedEnvironment
env = jinja2.Environment(
    autoescape=False,
    undefined=jinja2.StrictUndefined,
)

# response_generator.py line 568-573: Template rendered with request data
if template_override is not None:
    template = self._jinja_env.from_string(template_override)
    content = template.render(
        request=request,
        messages=request.get("messages", []),
        model=request.get("model", "unknown"),
    )
```

An attacker could send: `X-Fake-Template: {{ ''.__class__.__mro__[1].__subclasses__() }}` to enumerate Python classes, potentially escalating to code execution.

### [233-241, 247-250, 252-254] Admin endpoints have no authentication

**What:** The `/admin/config` (GET/POST), `/admin/stats` (GET), `/admin/reset` (POST), and `/admin/export` (GET) endpoints have no authentication, authorization, or access control of any kind. Any client that can reach the server can:
- Read the full server configuration including all error injection settings
- Modify error injection rates at runtime (e.g., set `rate_limit_pct=100.0` to make all requests fail)
- Reset metrics, destroying recorded data
- Export all raw request data

**Why it matters:** The assignment context states "this server receives network traffic" and "security and resource management matter." If the server is bound to a non-localhost interface (which is configurable), any network client can sabotage test runs by modifying error rates, destroy metrics by resetting the server, or exfiltrate request data via the export endpoint. Even on localhost, other processes on the same machine can interfere.

**Evidence:**
```python
# No auth check anywhere in any admin handler
async def _admin_config_endpoint(self, request: Request) -> JSONResponse:
    if request.method == "GET":
        return JSONResponse(self._get_current_config())
    body = await request.json()
    self.update_config(body)  # Arbitrary config changes from any client
    return JSONResponse({"status": "updated", "config": self._get_current_config()})

async def _admin_reset_endpoint(self, request: Request) -> JSONResponse:
    new_run_id = self.reset()  # Data destruction from any client
    return JSONResponse({"status": "reset", "new_run_id": new_run_id})
```

### [277] No request body validation on completion endpoints

**What:** The `_handle_completion_request` method calls `await request.json()` without any validation or error handling. If the request body is not valid JSON, Starlette will raise a `json.JSONDecodeError` which will result in an unhandled 500 Internal Server Error. This is external data at the Tier 3 boundary.

**Why it matters:** Any malformed request body crashes the handler with a 500 error that is NOT recorded in metrics. The `_record_request` call never executes because the exception happens before error injection decision. This means the metrics will not reflect actual request volume -- dropped requests due to malformed bodies are invisible to the metrics system.

**Evidence:**
```python
async def _handle_completion_request(self, request, endpoint, deployment=None):
    request_id = str(uuid.uuid4())
    start_time = time.monotonic()
    timestamp_utc = datetime.now(UTC).isoformat()

    body = await request.json()  # Unhandled -- crashes on malformed JSON
    model = body.get("model", "gpt-4")  # Never reached if above fails
    messages = body.get("messages", [])
```

## Warnings

### [159-182] update_config() replaces components non-atomically, creating race conditions

**What:** The `update_config()` method replaces `self._error_injector`, `self._response_generator`, and `self._latency_simulator` by assigning new instances to instance attributes. These assignments are not atomic and not protected by any lock. A concurrent request being handled in an async handler could read `self._error_injector` before the update but `self._latency_simulator` after the update, experiencing an inconsistent configuration state.

**Why it matters:** When a test dynamically reconfigures the server (a documented use case via `/admin/config`), in-flight requests may see a mix of old and new configuration. In most cases this is harmless (the chaos is already stochastic), but for deterministic test scenarios it could cause flaky test failures.

**Evidence:**
```python
def update_config(self, updates: dict[str, Any]) -> None:
    if "error_injection" in updates:
        # ... build new config ...
        self._error_injector = ErrorInjector(error_config)  # Assignment 1
    if "response" in updates:
        # ... build new config ...
        self._response_generator = ResponseGenerator(response_config)  # Assignment 2
    if "latency" in updates:
        # ... build new config ...
        self._latency_simulator = LatencySimulator(latency_config)  # Assignment 3
    # A concurrent request between assignments 1 and 3 sees mixed state
```

### [167, 173, 179, 187-189] Accessing private _config attributes of collaborator objects

**What:** `update_config()` and `_get_current_config()` directly access `self._error_injector._config`, `self._response_generator._config`, and `self._latency_simulator._config` -- private attributes of other classes. This creates tight coupling between the server and the internal implementation of these components.

**Why it matters:** If any of these classes rename or restructure their internal config storage, the server code breaks silently. The `_config` prefix convention signals "internal implementation detail" but the server treats it as a public API. Each of these classes should expose a public `config` property or a `get_config()` method.

**Evidence:**
```python
# Six occurrences of accessing private attributes:
current_error = self._error_injector._config.model_dump()       # line 167
current_response = self._response_generator._config.model_dump() # line 173
current_latency = self._latency_simulator._config.model_dump()   # line 179
"error_injection": self._error_injector._config.model_dump(),    # line 187
"response": self._response_generator._config.model_dump(),       # line 188
"latency": self._latency_simulator._config.model_dump(),         # line 189
```

### [686] Accessing private _config of response generator in request handler

**What:** Line 686 accesses `self._response_generator._config.mode` to record the response mode in metrics. This is another private attribute access, but in the hot path of request handling.

**Why it matters:** Same coupling concern as above, but with the additional concern that this is in the request-handling hot path rather than an admin endpoint. If `_config` access were to raise due to internal changes, it would crash the request handler after the response has already been generated and sent, but before metrics are recorded -- causing a silent metrics gap.

**Evidence:**
```python
response_mode=mode_override or self._response_generator._config.mode,
```

### [327-367, 692-728] Synchronous SQLite writes in async handlers

**What:** The `_record_request` method (called from all async endpoint handlers) performs synchronous SQLite writes via `self._metrics_recorder.record_request()`. SQLite writes involve disk I/O (for file-backed databases) and potentially WAL checkpointing. These synchronous operations block the async event loop.

**Why it matters:** Under high concurrency (the stated use case for ChaosLLM stress testing), synchronous database writes in async handlers will block the event loop, increasing latency for all concurrent requests and potentially causing connection timeouts. The SQLite 30-second timeout (set in `MetricsRecorder._get_connection`) means the event loop could block for up to 30 seconds waiting for a write lock.

**Evidence:**
```python
# All async handlers call synchronous _record_request:
async def _handle_success_response(self, ...):
    # ...
    self._record_request(...)  # Synchronous SQLite write blocks event loop
    return JSONResponse(response.to_dict())
```

### [401-515] Connection error handlers raise exceptions after recording metrics

**What:** The connection error handlers (`_handle_connection_error`) call `self._record_request(...)` and then raise `ConnectionResetError`. If the metrics recording fails (e.g., SQLite busy), the exception from SQLite would propagate instead of the intended `ConnectionResetError`, changing the behavior observed by the test client.

**Why it matters:** A failed metrics write would mask the intended connection error simulation, causing tests to see unexpected exceptions instead of the simulated connection failure behavior.

**Evidence:**
```python
# Lines 420-435:
self._record_request(
    request_id=request_id,
    # ... metrics data ...
)
raise ConnectionResetError("Connection failed after lead time")  # Never reached if above fails
```

### [542] _handle_http_error does a dict lookup without KeyError handling

**What:** Line 542 does `openai_error_type = _ERROR_TYPE_MAPPING[error_type]` and line 543 does `error_message = _ERROR_MESSAGE_MAPPING[error_type]`. If `ErrorInjector.decide()` returns an `error_type` that is not in these mappings, a `KeyError` will crash the handler with an unhandled 500 error.

**Why it matters:** This creates a coupling between the error types defined in `error_injector.py` and the mappings defined in `server.py`. If a new error type is added to the injector but not to the server's mapping tables, the server will crash on that error type. Since these are separate modules, this is a maintenance trap.

**Evidence:**
```python
# server.py line 542-543: Direct dict access, no .get() or try/except
openai_error_type = _ERROR_TYPE_MAPPING[error_type]  # KeyError if unknown
error_message = _ERROR_MESSAGE_MAPPING[error_type]    # KeyError if unknown

# error_injector.py defines HTTP_ERRORS dict -- these must stay in sync
HTTP_ERRORS: dict[str, int] = {
    "rate_limit": 429,
    "capacity_529": 529,
    # ... etc
}
```

Note: Per CLAUDE.md, this is system-owned code and crashing on unknown error types is correct behavior (it's a bug in our code if the mappings are out of sync). However, the crash would be a `KeyError` with no context about what went wrong, which is harder to debug than an explicit assertion.

## Observations

### [730-747] create_app attaches server to app.state but server already has the app

**What:** The `create_app()` function creates a `ChaosLLMServer`, then attaches the server instance to `server.app.state.server`. However, the server already has a reference to the app via `self._app`. This creates a circular reference: `app.state.server._app == app`.

**Why it matters:** The circular reference prevents garbage collection in some scenarios (though Python's cycle collector handles most cases). More importantly, the `app.state.server` is set by `create_app()` but NOT set when using `ChaosLLMServer` directly, creating an inconsistent API -- some code paths may expect `app.state.server` to exist and fail when using the class directly.

### [491] Unreachable elif after guaranteed if/elif chain

**What:** Line 511 has `elif error_type == "slow_response":` after an `if error_type == "timeout":` block that ends with a `raise`. The `slow_response` type should have been routed to `_handle_slow_response` by the caller (`_handle_error_injection`, line 289), so this branch is defensive dead code.

**Why it matters:** This is a correct safety net (raises `ValueError` if called with the wrong type), but the code comment "should be handled by _handle_slow_response" documents the contract that the caller is expected to route slow_response before reaching this method.

### [278-279] Default model from request body uses .get() appropriately

**What:** Line 278 uses `body.get("model", "gpt-4")` and line 279 uses `body.get("messages", [])`. These are correct uses of `.get()` because `body` is external user data (Tier 3 -- the request body from an HTTP client). The defaults ensure the server doesn't crash on minimal request bodies that omit optional fields.

**Why it matters:** No issue -- noting this as a correctly applied pattern per the Three-Tier Trust Model.

### General observation: No request size limit

**What:** The server accepts arbitrarily large request bodies. The `await request.json()` call will read the entire body into memory. There is no Content-Length limit enforced.

**Why it matters:** As a test server this is unlikely to be a real issue, but if deployed in a shared environment, a malicious or buggy client could exhaust server memory by sending very large request bodies. This is a standard concern for HTTP servers that accept JSON bodies.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** The highest priority items are (1) the SSTI vulnerability via X-Fake-Template header, which should use `jinja2.SandboxedEnvironment` instead of `jinja2.Environment`, and (2) adding basic authentication (even a shared secret via header) to admin endpoints if the server is ever bound to non-localhost interfaces. The request body validation gap should be addressed with a try/except around `request.json()` that returns a 400 and records the malformed request in metrics. The synchronous SQLite writes in async handlers should be moved to a background thread via `asyncio.to_thread()` or an executor to avoid blocking the event loop under load.
**Confidence:** HIGH -- all findings are based on direct code reading, Jinja2 security documentation, Starlette request handling semantics, and async/sync interaction patterns. The SSTI finding is well-documented in Jinja2 security literature.
