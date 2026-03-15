# Architecture Analysis: Testing Infrastructure (Chaos Servers)

**Date:** 2026-02-22
**Branch:** RC3.3-architectural-remediation
**Analyst:** Claude Sonnet 4.6
**Scope:** 20 files across chaosengine/, chaosllm/, chaosllm_mcp/, chaosweb/

---

## File-by-File Analysis

### chaosengine/cli.py

**Purpose:** Unified CLI aggregator. Mounts `chaosllm` and `chaosweb` Typer apps as sub-commands under the `chaosengine` command. Thin wrapper only.

**Key classes/functions:**
- `app` — top-level Typer app with `llm` and `web` sub-commands
- `main()` — entry point for `chaosengine` CLI

**Dependencies:** `chaosllm.cli`, `chaosweb.cli`, `typer`

**Concerns:** None. Correct use of Typer's `add_typer`. No logic.

---

### chaosengine/config_loader.py

**Purpose:** Shared generic configuration loading with 3-level precedence: preset < config file < CLI overrides. Used by both `chaosllm` and `chaosweb` as their config-loading backend.

**Key classes/functions:**
- `deep_merge(base, override)` — recursive dict merge, non-mutating
- `list_presets(presets_dir)` — lists YAML presets by directory
- `load_preset(presets_dir, preset_name)` — loads a single YAML preset
- `load_config[ConfigT: BaseModel](...)` — generic loader that merges layers, validates through Pydantic

**Dependencies:** `yaml`, `pydantic`, `pathlib`

**Concerns:**
- The generic `load_config` function uses Python 3.12 type parameter syntax (`[ConfigT: BaseModel]`). This is correct modern Python but worth noting.
- `yaml.safe_load` is used — safe.
- Empty config file emits a `UserWarning` — appropriate.
- One subtle issue: `config_dict["preset_name"] = preset` is injected unconditionally (line 141). If `ChaosLLMConfig` or `ChaosWebConfig` adds a field named `preset_name` that conflicts with this injection, it silently clobbers the field. Currently both top-level configs do have `preset_name`, and it works, but this is fragile: the loader assumes knowledge of the concrete config type's schema.

---

### chaosengine/injection_engine.py

**Purpose:** Domain-agnostic burst state machine and error-selection algorithm. Composes into domain-specific injectors (LLM, Web); knows nothing about HTTP codes, content types, or any domain specifics. Operates only on `ErrorSpec` lists with tags and weights.

**Key classes/functions:**
- `InjectionEngine` — core class with:
  - `is_in_burst()` — checks periodic burst window state
  - `should_trigger(percentage)` — random roll against a percentage
  - `select(specs)` — dispatches to priority or weighted selection
  - `_select_priority(specs)` — first spec to trigger wins
  - `_select_weighted(specs)` — proportional selection accounting for success probability
  - `reset()` — clears burst timing state

**Dependencies:** `chaosengine.types` (BurstConfig, ErrorSpec), `random`, `threading`, `time`

**Concerns:**
- Thread-safe for `_start_time` initialization via `threading.Lock`. No other shared mutable state.
- `_select_weighted`: The success probability is `max(0, 100 - total_weight)`. If weights sum to more than 100, success probability is 0 and all weight is proportionally split. This is mathematically correct but could surprise users who configure weights summing beyond 100.
- `should_trigger(percentage)` is called in priority mode to test each spec independently. This means in priority mode, multiple errors could theoretically fire but only the first one is returned. The independence is correct for a "random chance of this error" model, but it means actual error rates in priority mode are not purely additive — a spec with weight 20 is evaluated independently regardless of prior specs.
- No concerns with correctness. This is well-designed: injectable `rng` and `time_func` enable full determinism in tests.

---

### chaosengine/latency.py

**Purpose:** Stateless latency simulation. Computes artificial delay durations for `asyncio.sleep()` calls in servers.

**Key classes/functions:**
- `LatencySimulator` — computes `(base_ms + uniform_jitter) / 1000.0`
  - `simulate()` — normal per-request latency
  - `simulate_slow_response(min_sec, max_sec)` — extended delay for slow-response injection

**Dependencies:** `chaosengine.types` (LatencyConfig), `random`

**Concerns:** None. Stateless, injectable RNG, correct clamping to 0. Simple and correct.

---

### chaosengine/metrics_store.py

**Purpose:** Thread-safe SQLite metrics storage, shared by all chaos plugins. Schema-driven DDL generation, WAL mode, thread-local connections, timeseries bucket management.

**Key classes/functions:**
- `_generate_ddl(schema)` — generates CREATE TABLE and CREATE INDEX from `MetricsSchema`
- `_get_bucket_utc(timestamp_utc, bucket_sec)` — truncates a timestamp to a bucket boundary
- `MetricsStore` — central class providing:
  - Thread-local SQLite connections with WAL (or MEMORY) mode
  - `record(**kwargs)` — schema-validated INSERT into requests table
  - `update_timeseries(bucket, **counters)` — UPSERT with ON CONFLICT increment
  - `update_bucket_latency(bucket, latency_ms)` — recalculates avg/p99 latency for a bucket
  - `rebuild_timeseries(classify)` — full rebuild from raw request data using caller-supplied classifier
  - `get_stats()` — schema-aware summary statistics (uses column presence checks to avoid hardcoding)
  - `export_data()` — raw dump of both tables
  - `reset()` — clears tables, generates new run_id
  - `close()` — closes all thread connections

**Dependencies:** `chaosengine.types` (MetricsConfig, MetricsSchema), `sqlite3`, `threading`, `uuid`, `datetime`, `pathlib`

**Concerns:**
- SQL injection: Column names in `record()` and `update_timeseries()` come from `kwargs` keys, which are used directly in f-string SQL. The `unknown = set(kwargs) - set(self._request_col_names)` check validates keys against the schema, preventing arbitrary column injection. This is safe.
- The `rebuild_timeseries` method uses column names from schema in SQL but only implicitly via the caller-supplied `classify` callback. The callback's return dict keys are used in `totals.get(col, 0)` — only explicitly declared columns are written to the DB. Safe.
- `_cleanup_stale_connections()` is called before every new connection. It uses `threading.enumerate()` to find live threads. This is a known pattern but has a minor race: a thread can exit between `enumerate()` and connection access. The `contextlib.suppress(sqlite3.ProgrammingError)` handles this correctly.
- The `update_bucket_latency` method recomputes avg/p99 from a range query on every insert. For high-throughput scenarios this is O(n) per insert per bucket. Acceptable for test tooling; would not scale to production metrics.
- The `get_stats()` and `export_data()` return `dict[str, Any]` — not typed/frozen. These are chaos server metrics, not audit data, so this is acceptable. The data never touches the Landscape audit trail.

---

### chaosengine/types.py

**Purpose:** Shared frozen dataclasses and Pydantic models used across all chaos plugins.

**Key classes/functions:**
- `ServerConfig` — host, port, workers (Pydantic, frozen, extra=forbid)
- `MetricsConfig` — database URI, timeseries bucket size (Pydantic, frozen, extra=forbid)
- `LatencyConfig` — base_ms, jitter_ms (Pydantic, frozen, extra=forbid)
- `ErrorSpec` — frozen dataclass: tag + weight, validated in `__post_init__`
- `BurstConfig` — frozen dataclass: enabled, interval_sec, duration_sec, with invariant checks
- `ColumnDef` — frozen dataclass: column name, SQL type, nullable, default, primary_key
- `MetricsSchema` — frozen dataclass: tuple of ColumnDef for request and timeseries tables, plus index definitions

**Dependencies:** `pydantic`, `dataclasses`, `math`

**Concerns:**
- All Pydantic models have `frozen=True` and `extra="forbid"` — correct.
- `ErrorSpec.__post_init__` checks `math.isfinite(weight)` — correctly rejects NaN/Infinity.
- `BurstConfig.__post_init__` validates `duration_sec < interval_sec` when enabled — correct invariant.
- No concerns.

---

### chaosengine/vocabulary.py

**Purpose:** Shared static word banks used by both ChaosLLM and ChaosWeb for random text generation.

**Key contents:**
- `ENGLISH_VOCABULARY` — 110 high-frequency English words + some technical terms, as a tuple
- `LOREM_VOCABULARY` — Lorem Ipsum words, deduplicated, sorted, as a tuple

**Dependencies:** None

**Concerns:** None. Deterministic (sorted), immutable tuples. The use of a `set` intermediate (`_LOREM_SET`) then `tuple(sorted(...))` ensures the ordering is deterministic across Python versions.

---

### chaosllm/cli.py

**Purpose:** CLI for the ChaosLLM server with `serve`, `presets`, and `show_config` commands. Also contains the `chaosllm-mcp` entry point.

**Key classes/functions:**
- `serve(...)` — builds CLI override dict, loads config, starts uvicorn with `create_app`
- `presets()` — lists available presets
- `show_config(...)` — displays merged config in JSON or YAML
- `mcp_main(...)` — entry point for `chaosllm-mcp` (searches for or accepts a database path, imports and runs the MCP server module)

**Dependencies:** `chaosllm.config`, `chaosllm.server`, `chaosllm_mcp.server`, `typer`, `pydantic`, `yaml`, `uvicorn` (optional)

**Concerns:**
- The `mcp_main` function imports `elspeth.testing.chaosllm_mcp.server` with `# type: ignore[import-not-found]`. The comment says "module may not be built yet," but the module does exist (`chaosllm_mcp/server.py`). The ignore annotations should be removed now that the module exists.
- The `show_config` command has a bare `except Exception` catch (line 453). This is acceptable for a CLI display command but slightly broader than the rest of the error handling.
- The `mcp_app` is defined in `cli.py` but is not added to the main `app`. It is a separate entry point (`mcp_main_entry`). This is correct design — they're separate commands.

---

### chaosllm/config.py

**Purpose:** Full configuration schema for the ChaosLLM server. Pydantic models for response generation, error injection (HTTP, connection-level, malformed responses), bursts, and top-level config.

**Key classes/functions:**
- `RandomResponseConfig` — min/max words, vocabulary choice
- `TemplateResponseConfig` — single `body` Jinja2 template string
- `PresetResponseConfig` — JSONL file path, random/sequential selection
- `ResponseConfig` — aggregates the above + mode + header override settings
- `BurstConfig` — burst interval, duration, elevated error percentages
- `ErrorInjectionConfig` — all error types with percentages (HTTP: 429, 529, 503, 502, 504, 500, 403, 404; connection: timeout, stall, failed, reset, slow; malformed: invalid_json, truncated, empty_body, missing_fields, wrong_content_type). Also range validation for `[min, max]` tuple fields.
- `ChaosLLMConfig` — top-level with host-binding safety validation (blocks 0.0.0.0 unless `allow_external_bind=True`)

**Dependencies:** `chaosengine.config_loader`, `chaosengine.types`, `pydantic`

**Concerns:**
- All models have `frozen=True, extra="forbid"` — correct.
- The `allow_external_bind` safety check is good. ChaosLLM is test-only and should not be network-exposed.
- `BurstConfig` here is a Pydantic model (different from `chaosengine.types.BurstConfig` which is a frozen dataclass). Two types named `BurstConfig` in different modules, both used within `error_injector.py` (imported as `EngineBurstConfig` to disambiguate). This naming overlap is confusing but managed correctly via aliasing.

---

### chaosllm/error_injector.py

**Purpose:** LLM-domain error injection decision-making. Composes `InjectionEngine` for burst/selection logic while owning LLM-specific error types and `ErrorDecision` construction.

**Key classes/functions:**
- `ErrorCategory` — enum: HTTP, CONNECTION, MALFORMED
- `ErrorDecision` — frozen dataclass with rich `__post_init__` validation of field invariants per category. Factory classmethods: `success()`, `http_error()`, `connection_error()`, `malformed_response()`
- `HTTP_ERRORS`, `CONNECTION_ERRORS`, `MALFORMED_TYPES` — exported lookup sets
- `ErrorInjector` — composes `InjectionEngine`, builds `ErrorSpec` list with burst-adjusted weights, maps selected tag to `ErrorDecision`

**Dependencies:** `chaosengine.injection_engine`, `chaosengine.types`, `chaosllm.config`

**Concerns:**
- `ErrorDecision.__post_init__` is thorough and enforces category-field invariants. Good defensive use of dataclass validation (this is system-owned code defending against bugs in the builder, which is appropriate).
- The `_build_timeout_decision()` uses `self._engine.should_trigger(50.0)` to decide 50/50 between 504 and connection drop. This is correct but means the decision borrows from `InjectionEngine`'s RNG for a non-injection-rate purpose. Minor: cleaner to use `self._rng.random() < 0.5` directly.
- No issues with the composition pattern.

---

### chaosllm/metrics.py

**Purpose:** LLM-specific metrics recording layer. Wraps `MetricsStore` with typed methods and outcome classification for LLM request data.

**Key classes/functions:**
- `LLM_METRICS_SCHEMA` — `MetricsSchema` constant defining requests and timeseries columns for LLM use case
- `RequestRecord` — frozen dataclass representing one request record (not actually used for DB insertion; the recorder method takes raw kwargs instead)
- `OutcomeClassification` — NamedTuple for timeseries classification
- `_classify_outcome(outcome, status_code, error_type)` — maps to `OutcomeClassification`
- `_classify_row(row)` — adapter for `MetricsStore.rebuild_timeseries()`
- `MetricsRecorder` — composes `MetricsStore`, adds `record_request()`, `update_timeseries()`, pass-through methods

**Dependencies:** `chaosengine.metrics_store`, `chaosengine.types`, `sqlite3`, `dataclasses`

**Concerns:**
- `RequestRecord` is defined but never used for actual DB insertion — `record_request()` takes keyword arguments matching the schema columns directly. `RequestRecord` appears to be documentation or a future-facing DTO that was not wired up. This is dead code. Either use it as the insertion type or remove it.
- The `_classify_outcome` function treats `status_code=None` plus error_type in a specific set as `is_connection_error`. If a new connection error type is added to `ErrorInjector` but not to this set, it silently misclassifies. The set could be derived from `CONNECTION_ERRORS` in `error_injector.py` to avoid drift.
- `update_timeseries()` method on `MetricsRecorder` is named confusingly — it rebuilds ALL timeseries from scratch (delegates to `store.rebuild_timeseries`), not incremental updates. The name suggests incremental.

---

### chaosllm/response_generator.py

**Purpose:** Fake LLM response generation in OpenAI-compatible format. Supports random text, Jinja2 template, echo, and preset-bank modes.

**Key classes/functions:**
- `OpenAIResponse` — frozen dataclass with `to_dict()` producing OpenAI-format JSON
- `PresetBank` — manages JSONL-loaded canned responses with random/sequential selection
- `ResponseGenerator` — main generator with:
  - `_create_jinja_env()` — creates `jinja2.sandbox.SandboxedEnvironment`
  - Template helpers: `random_choice`, `random_float`, `random_int`, `random_words`, `timestamp`
  - `generate(request, mode_override, template_override)` — dispatches to appropriate mode

**Dependencies:** `chaosengine.vocabulary`, `chaosllm.config`, `jinja2`, `jinja2.sandbox`, `structlog`, `random`, `uuid`

**Concerns:**
- **Jinja2 sandbox:** `_create_jinja_env` uses `jinja2.sandbox.SandboxedEnvironment` with `autoescape=False`. This is correct for LLM response generation (not HTML context). The sandbox prevents arbitrary Python execution. This addresses the MEMORY.md concern about "unsandboxed Jinja2."
- **Template override from headers:** The `X-Fake-Template` header can inject a template string up to `max_template_length` (default 10,000 chars). The SandboxedEnvironment renders this template with access to `random_choice`, `random_float`, `random_int`, `random_words`, `timestamp`. None of these helpers expose filesystem, network, or env access, and SandboxedEnvironment blocks attribute access to internals. The risk is low, but any client who can reach the ChaosLLM server (which defaults to localhost-only) can control template rendering. Since the server is localhost-only and the helpers are bounded, this is acceptable for a test tool.
- **TemplateError handling in `generate()`:** Template rendering errors return a string like `"Template rendering error: TemplateError"`. This means a malformed template override still produces a 200 response with a string body, not an exception. The server treats this as a successful generation, which is correct — the chaos server should not crash on bad templates.
- `_generate_echo_response` does not HTML-escape the echoed content (it just `f"Echo: {last_content}"`). This is a JSON response body, not HTML, so XSS is not a concern here. Fine.
- `_estimate_tokens` is a rough 4-chars-per-token approximation with `max(1, ...)`. Correct for fake usage.

---

### chaosllm/server.py

**Purpose:** Starlette ASGI application for ChaosLLM. Routes HTTP requests to error injection or successful response handlers, records metrics, supports runtime config update via `/admin/config`.

**Key classes/functions:**
- `ChaosLLMServer` — central server class:
  - Composes `ErrorInjector`, `ResponseGenerator`, `LatencySimulator`, `MetricsRecorder`
  - `update_config(updates)` — thread-safe runtime config swap under `_config_lock`
  - Route handlers: `/health`, `/v1/chat/completions`, `/openai/deployments/{deployment}/chat/completions`, `/admin/*`
  - `_handle_completion_request(...)` — main dispatch with error injection
  - `_handle_connection_error(...)` — raises `ConnectionResetError` for disconnect simulation
  - `_handle_http_error(...)` — returns `JSONResponse` with appropriate error body
  - `_handle_malformed_response(...)` — returns 200 with intentionally bad content
  - `_handle_success_response(...)` — generates response, applies latency, records metrics
  - `_record_request(...)` — best-effort metrics recording with exception suppression
- `create_app(config)` — factory function

**Dependencies:** `chaosllm.config`, `chaosllm.error_injector`, `chaosllm.metrics`, `chaosllm.response_generator`, `chaosengine.config_loader`, `chaosengine.latency`, `chaosengine.types`, `starlette`, `structlog`

**Concerns:**
- **Thread safety in `update_config`:** Components are built outside the lock, then swapped atomically. This is correct — validation may be expensive. However, `update_config` is called from the async `_admin_config_endpoint` which runs in the server's event loop. Uvicorn with multiple workers means each worker has its own process and its own `ChaosLLMServer` instance; config updates only affect the worker that received the `/admin/config` POST. This is a multi-process limitation, not a bug, but it is non-obvious and unmentioned in the docstring.
- **Metrics recording is best-effort:** `_record_request` catches all exceptions and logs a warning. This is explicitly documented and intentional — a metrics failure must not corrupt a chaos response. This is correct design for test infrastructure.
- **`_handle_connection_error` raises `ConnectionResetError`:** Starlette/uvicorn will catch unhandled exceptions from route handlers and return 500. But `ConnectionResetError` is not a standard HTTP exception — uvicorn treats it as a disconnect signal. The actual behavior at the ASGI level depends on the server: with `uvicorn`, raising `ConnectionResetError` in an ASGI app body causes the response to be dropped, simulating a disconnect. This works but is fragile — it relies on uvicorn's specific behavior. A more explicit approach would use Starlette streaming responses.
- **No authentication on `/admin/` endpoints:** The server defaults to localhost-only binding, so this is acceptable. The `allow_external_bind: true` override would expose unauthenticated admin endpoints. The docstring should warn about this.
- **`_ERROR_TYPE_MAPPING` and `_ERROR_MESSAGE_MAPPING`:** Direct dict lookup with `error_type` as key (no `.get()`). If `error_type` is not in the mapping, this raises `KeyError`. In `_handle_http_error`, `error_type` comes from `decision.error_type`, which comes from `_build_decision` in `ErrorInjector`. The set of possible tags is controlled by `_build_specs()`, and all HTTP tags are keys in both mappings. But there is no compile-time guarantee — if someone adds a new HTTP error type to `ErrorInjector` without updating the server mappings, this crashes at runtime. A defensive `.get(error_type, "server_error")` fallback would be more robust. Alternatively, add a test that covers all HTTP_ERRORS tags.

---

### chaosllm_mcp/server.py

**Purpose:** MCP server for analyzing ChaosLLM metrics data. Provides Claude-optimized analysis tools over the SQLite metrics database from a `chaosllm serve` run. Read-only access only.

**Key classes/functions:**
- `ChaosLLMAnalyzer` — analysis class with:
  - `diagnose()` — summary: total requests, success rate, top error types, patterns, AIMD assessment
  - `analyze_aimd_behavior()` — burst detection, recovery times, throughput degradation, backoff ratio
  - `analyze_errors()` — error breakdown by type and status code with sample timestamps
  - `analyze_latency()` — p50/p95/p99 with slow-request detection and error correlation
  - `find_anomalies()` — unexpected status codes, throughput cliffs, error clustering, zero-success periods
  - `get_burst_events()` — per-burst before/during/after statistics
  - `get_error_samples(error_type, limit)` — sample request records for a specific error type
  - `get_time_window(start_sec, end_sec)` — stats for a Unix timestamp range
  - `query(sql)` — read-only SQL with SELECT enforcement and dangerous keyword rejection
  - `describe_schema()` — static schema description
- `create_server(database_path)` — creates MCP `Server` instance with all tools registered
- `run_server(database_path)` — async entry point using stdio transport
- `_find_metrics_databases(search_dir, max_depth)` — auto-discovery of metrics databases
- `main()` — CLI entry point via argparse

**Dependencies:** `mcp.server`, `mcp.server.stdio`, `mcp.types`, `sqlite3`, `json`, `re`, `pathlib`

**Concerns:**
- **Read-only SQL enforcement:** `query()` checks that the SQL starts with `SELECT` and uses `re.search(rf"\b{keyword}\b", sql_normalized)` for dangerous keywords. The word-boundary approach is better than a simple `in` check (the comment even notes why — `created_at` would otherwise match `CREATE`). This is reasonable for a test tool. However, SQLite allows some tricks like `WITH ... AS (SELECT ...) UPDATE` (CTEs with writes). The CTE case would pass the SELECT check but could be a write if it included a write statement in the CTE. Mitigating factor: this is a test tool on a metrics DB, not a production system. If stricter enforcement is needed, use `sqlite3` in read-only mode (`uri=True` with `?mode=ro`).
- **Single connection (not thread-local):** `_get_connection()` uses a single `self._conn`, not thread-local connections. The MCP server runs async (asyncio), not multi-threaded, so this is acceptable — all calls serialize through the event loop.
- **Error handling in `call_tool`:** Bare `except Exception as e` returns `TextContent(type="text", text=f"Error: {e!s}")`. For an MCP analysis tool this is correct — errors should surface as text to Claude, not crash the server.
- **`_find_metrics_databases` uses `rglob("*.db")`:** This searches all `.db` files in the directory tree up to `max_depth`. It prioritizes by filename pattern (chaosllm-metrics wins) then by modification time. Simple and effective for test tooling.
- **No MCP equivalent to Landscape MCP's extensive tooling:** ChaosLLM MCP has 9 tools vs Landscape MCP's much larger set. This is appropriate — chaos metrics are simpler than audit data.

---

### chaosweb/cli.py

**Purpose:** CLI for the ChaosWeb server. Structurally identical to `chaosllm/cli.py` — `serve`, `presets`, `show_config` commands. No MCP entry point.

**Key classes/functions:** Same structure as `chaosllm/cli.py`.

**Dependencies:** `chaosweb.config`, `chaosweb.server`, `typer`, `pydantic`, `yaml`, `uvicorn`

**Concerns:**
- Structural duplication with `chaosllm/cli.py` is high. The `serve` and `show_config` commands follow the exact same pattern. See "Shared Patterns / Duplication" section below.
- Same bare `except Exception` in `show_config` as ChaosLLM — acceptable.

---

### chaosweb/config.py

**Purpose:** Configuration schema for the ChaosWeb server. Mirrors `chaosllm/config.py` structure but with web-domain error types and HTML content generation modes.

**Key classes/functions:**
- `RandomContentConfig` — min/max words, vocabulary choice (mirrors `RandomResponseConfig`)
- `TemplateContentConfig` — Jinja2 template body (mirrors `TemplateResponseConfig`)
- `PresetContentConfig` — JSONL file, selection mode
- `WebContentConfig` — aggregates above + mode, header override, template length cap, default content type
- `WebBurstConfig` — elevated rate_limit and forbidden percentages during burst (mirrors `BurstConfig` in chaosllm)
- `WebErrorInjectionConfig` — all web error types: HTTP (429, 403, 404, 410, 402, 451, 503, 502, 504, 500), connection-level (timeout, reset, stall, slow, incomplete), content malformations (wrong_content_type, encoding_mismatch, truncated_html, invalid_encoding, charset_confusion, malformed_meta), redirect injection (redirect_loop, ssrf_redirect)
- `ChaosWebConfig` — top-level with same `allow_external_bind` safety as ChaosLLM

**Dependencies:** `chaosengine.config_loader`, `chaosengine.types`, `pydantic`

**Concerns:**
- All models have `frozen=True, extra="forbid"` — correct.
- The comment in `ChaosWebConfig` reads "Uses ServerConfig, MetricsConfig, and LatencyConfig from ChaosLLM (identical types, future chaos_base extraction candidates)." These types actually live in `chaosengine.types`, not `chaosllm`. The comment is slightly misleading.
- Two `BurstConfig` types in the ecosystem: `chaosengine.types.BurstConfig` (frozen dataclass), `chaosllm.config.BurstConfig` (Pydantic model), and now `WebBurstConfig` (Pydantic model). The dataclass lives at the engine layer; the Pydantic versions are config-layer equivalents. They have different fields (`WebBurstConfig` has `forbidden_pct` while `chaosllm.config.BurstConfig` has `rate_limit_pct` and `capacity_pct`). The naming is slightly confusing — `WebBurstConfig` vs `BurstConfig` is fine, but the `chaosengine.types.BurstConfig` dataclass being separate from the Pydantic models is an architectural seam worth noting.

---

### chaosweb/content_generator.py

**Purpose:** HTML content generation for ChaosWeb. Mirrors `chaosllm/response_generator.py` pattern but generates HTML pages instead of JSON LLM responses. Also contains standalone content-corruption helper functions.

**Key classes/functions:**
- `WebResponse` — frozen dataclass: content (str or bytes), content_type, status_code, headers, encoding
- `PresetBank` — manages JSONL HTML page snapshots (mirrors chaosllm PresetBank but stores dicts instead of strings)
- `ContentGenerator` — generates HTML via random, template, echo, or preset modes:
  - `_create_jinja_env()` — `SandboxedEnvironment` with `autoescape=True` (HTML context)
  - `_generate_random_html()` — syntactically valid HTML5 with random structural elements, HTML-escaped content
  - `_generate_template_html(path, headers)` — Jinja2 template with error handling
  - `_generate_echo_html(path, headers)` — all reflected content HTML-escaped
  - `_generate_preset_html()` — from PresetBank
- Standalone corruption helpers: `truncate_html`, `inject_encoding_mismatch`, `inject_charset_confusion`, `inject_invalid_encoding`, `inject_malformed_meta`, `generate_wrong_content_type`

**Dependencies:** `chaosengine.vocabulary`, `chaosweb.config`, `jinja2`, `jinja2.sandbox`, `structlog`, `html`, `random`

**Concerns:**
- **Jinja2 sandbox:** Uses `jinja2.sandbox.SandboxedEnvironment` with `autoescape=True` (HTML context). This is correct. The `autoescape=True` means Jinja2 auto-escapes all template variables, preventing XSS in generated HTML. This addresses the MEMORY.md concern about "unsandboxed Jinja2 in blob_sink and chaosllm server/generator." The chaos servers use sandboxed environments; the concern in MEMORY.md appears to refer to `blob_sink` specifically, not these files.
- **Echo mode:** `_generate_echo_html` manually HTML-escapes path and header values with `html.escape()`. This is correct and explicit.
- **`inject_malformed_meta` injects `javascript:void(0)` in a meta refresh:** This is intentional to simulate malformed websites. Safe in test context.
- **`PresetBank` in chaosweb and chaosllm are near-identical:** The web version stores `dict[str, str]` (with url/content/content_type fields) while the LLM version stores `str`. Both have the same `__init__`, `next()`, `reset()`, and `from_jsonl()` interface. This is significant duplication.
- **`generate_wrong_content_type` creates a new `random.Random()` if no rng is passed:** Minor: this means it uses a non-deterministic RNG even in tests that inject an RNG into `ContentGenerator`, since the corruption helper is called from `server.py` independently. Not a correctness issue, but testing is less deterministic than it appears.

---

### chaosweb/error_injector.py

**Purpose:** Web-domain error injection. Mirrors `chaosllm/error_injector.py` structure but with web-specific error types including redirect injection (redirect loops, SSRF redirects to private IPs).

**Key classes/functions:**
- `WebErrorCategory` — enum: HTTP, CONNECTION, MALFORMED, REDIRECT (extends LLM's 3 categories with REDIRECT)
- `WEB_HTTP_ERRORS`, `WEB_CONNECTION_ERRORS`, `WEB_MALFORMED_TYPES`, `WEB_REDIRECT_TYPES` — exported constants
- `SSRF_TARGETS` — hardcoded list of SSRF redirect targets (cloud metadata, RFC 1918, loopback, CGNAT, IPv6, encoding tricks)
- `WebErrorDecision` — frozen dataclass similar to LLM's `ErrorDecision` but with extra fields: `redirect_target`, `redirect_hops`, `incomplete_bytes`, `encoding_actual`. Rich `__post_init__` validation.
- `WebErrorInjector` — composes `InjectionEngine`, manages web-specific spec building and decision mapping

**Dependencies:** `chaosengine.injection_engine`, `chaosengine.types`, `chaosweb.config`

**Concerns:**
- `WebErrorDecision` and `ErrorDecision` (chaosllm) are structurally very similar. Both are frozen dataclasses with `error_type`, `status_code`, `retry_after_sec`, `delay_sec`, `start_delay_sec`, `category`, `malformed_type`, and rich `__post_init__` validation. The web version adds 4 extra fields. These could share a base frozen dataclass, but frozen dataclass inheritance is tricky in Python (parent must also be frozen). Given the domain difference, the duplication is somewhat justified.
- `SSRF_TARGETS` includes all major SSRF vectors. This is used for testing that ELSPETH's web clients correctly reject SSRF redirects — the server deliberately redirects to these targets to test the client's `validate_url_for_ssrf` defense.
- The decimal IP trick (`http://2852039166/` = 169.254.169.254) is noted as a "bypass vector." This is a realistic SSRF test case.

---

### chaosweb/metrics.py

**Purpose:** Web-specific metrics recording. Mirrors `chaosllm/metrics.py` but with web-domain classification (forbidden, not_found, redirect instead of capacity_error, client_error).

**Key classes/functions:**
- `WebOutcomeClassification` — NamedTuple with web-specific fields
- `WEB_METRICS_SCHEMA` — schema constant for web requests/timeseries tables
- `_classify_web_outcome(outcome, status_code, error_type)` — web outcome classifier
- `WebMetricsRecorder` — composes `MetricsStore`, adds `record_request()` with web fields

**Dependencies:** `chaosengine.metrics_store`, `chaosengine.types`

**Concerns:**
- Similar to `chaosllm/metrics.py`: no unused `RequestRecord` equivalent — the web recorder uses keyword arguments directly.
- `_classify_web_outcome` has the same potential drift issue: `connection_error` is classified by a hardcoded set `("timeout", "connection_reset", "connection_stall", "incomplete_response")`. `"slow_response"` is absent — slow responses are recorded as "success" with `injection_type="slow_response"`. This appears intentional (slow responses eventually succeed), but the set should be derived from `WEB_CONNECTION_ERRORS` minus `"slow_response"`.

---

### chaosweb/server.py

**Purpose:** Starlette ASGI server for ChaosWeb. Mirrors `chaosllm/server.py` structure with web-specific handlers including redirect injection, content malformation, and the `_StreamingDisconnect` response class for incomplete responses.

**Key classes/functions:**
- `ChaosWebServer` — main server class with same structure as `ChaosLLMServer`:
  - Routes: `/health`, `/admin/*`, `/redirect` (redirect loop handler), `/{path:path}` (catch-all)
  - `_handle_redirect(...)` — SSRF redirect and redirect loop entry
  - `_redirect_hop_endpoint(...)` — stateless query-parameter hop counter with termination
  - `_handle_connection_error(...)` — timeout (504 response), reset, stall (both via `_StreamingDisconnect`), incomplete
  - `_handle_http_error(...)` — HTML body errors
  - `_handle_malformed_content(...)` — all 6 malformation types
  - `_handle_success(...)` — normal HTML page generation
  - `_record_request(...)` — best-effort metrics recording with exception suppression
- `_StreamingDisconnect` — custom `Response` subclass that streams partial body then raises `ConnectionResetError`
- `create_app(config)` — factory function

**Dependencies:** `chaosengine.config_loader`, `chaosengine.latency`, `chaosengine.types`, `chaosweb.config`, `chaosweb.content_generator`, `chaosweb.error_injector`, `chaosweb.metrics`, `starlette`, `structlog`

**Concerns:**
- **`update_config` in ChaosWeb is NOT thread-safe:** Unlike `ChaosLLMServer` which uses `self._config_lock`, `ChaosWebServer.update_config()` swaps components without a lock. In a multi-worker uvicorn setup each worker is a separate process, so this isn't a cross-process issue. Within a single worker (single asyncio event loop) concurrent requests could theoretically see a partial swap during the three consecutive assignments. Since asyncio is cooperative, a swap across three assignments without `await` is atomic from the event loop's perspective. However, this is inconsistent with ChaosLLM's approach and may confuse readers. LOW SEVERITY.
- **`_redirect_hop_endpoint`:** Uses `int(request.query_params.get("hop", "1"))` without validation — a non-integer value would raise `ValueError` and return a 500. This is test infrastructure so it is not critical, but a try/except would be more robust.
- **`_StreamingDisconnect`:** The class directly sets `self.body_iterator`, `self.status_code`, `self.media_type`, and `self.background` without calling `super().__init__()`. This bypasses Starlette's `Response.__init__()`, which could break if Starlette adds new required initialization in a future version. Technically works now.
- **No `_config_lock` equivalent:** See above — inconsistency with ChaosLLMServer.
- `_WEB_ERROR_MESSAGES` uses `_WEB_ERROR_MESSAGES.get(error_type, f"{status_code} Error")` (defensive `.get`) while `chaosllm/server.py` uses direct dict lookup. ChaosWeb is more robust here. ChaosLLM should be fixed to match.

---

## Overall Analysis

### 1. ChaosEngine — What Does It Inject? How Is It Configured?

ChaosEngine is the shared utility layer, not a standalone chaos server. It provides:

- **`InjectionEngine`**: Burst state machine + priority/weighted error selection. Domain-agnostic — operates on `ErrorSpec(tag, weight)` lists. Callers build the spec list; the engine selects; callers interpret the result.
- **`LatencySimulator`**: Base + jitter delay computation.
- **`MetricsStore`**: Thread-safe SQLite backend for request and timeseries recording.
- **`config_loader`**: Generic 4-level precedence config loading (defaults < preset < file < CLI).
- **`types`**: Shared frozen models: `ServerConfig`, `MetricsConfig`, `LatencyConfig`, `ErrorSpec`, `BurstConfig`, `ColumnDef`, `MetricsSchema`.
- **`vocabulary`**: Static word banks for content generation.

The chaosengine CLI itself is just a Typer aggregator that mounts chaosllm and chaosweb as sub-commands.

**Configuration:** YAML presets in each plugin's `presets/` directory, layered by the generic `load_config` utility. Controlled at CLI level via `--preset`, `--config`, and individual override flags.

### 2. ChaosLLM — How Does It Work?

ChaosLLM is a fake OpenAI/Azure OpenAI compatible server for testing LLM client code:

1. **Starts** as a Starlette ASGI server (`uvicorn`) on configurable port (default 8000, localhost-only).
2. **Per-request:** `ErrorInjector.decide()` selects one of 18 error types or success. Priority order: connection errors > HTTP errors > malformed responses.
3. **On error:** Returns appropriate HTTP error (429, 503, etc.), simulates connection drop (`ConnectionResetError`), or returns 200 with intentionally bad content (invalid JSON, truncated, empty, missing fields, wrong content type).
4. **On success:** `ResponseGenerator.generate()` produces an OpenAI-format response in one of four modes: random text, Jinja2 template (sandboxed), echo of last user message, or preset JSONL bank. `LatencySimulator` adds artificial delay.
5. **Metrics:** Every request is recorded to SQLite (best-effort). `MetricsRecorder` tracks outcome, status codes, latency, injection type, token counts.
6. **Burst mode:** `InjectionEngine` tracks elapsed time; during burst windows, `rate_limit_pct` and `capacity_529_pct` are elevated to simulate provider stress.
7. **Admin endpoints:** `/admin/config` (GET/POST), `/admin/stats`, `/admin/reset`, `/admin/export` allow runtime control.
8. **Response header overrides:** `X-Fake-Response-Mode` and `X-Fake-Template` headers allow per-request override of response generation (if `allow_header_overrides=True`).

### 3. ChaosWeb — How Does It Work?

ChaosWeb is a fake web server for testing HTML scraping pipelines:

1. **Same structure as ChaosLLM** with domain-specific differences.
2. **Error types include web-specific scenarios**: redirect loops (stateless query-parameter hop counter), SSRF redirect injection (redirects to cloud metadata, private IPs, IPv6 variants), HTTP errors specific to web (403, 404, 410, 402, 451), and HTML content malformations (encoding mismatch, charset confusion, malformed meta refresh, invalid encoding, truncated HTML).
3. **Content generation**: HTML pages instead of JSON. `ContentGenerator` produces valid HTML5 (random structural elements), template (Jinja2 sandboxed with autoescape=True), echo (HTML-escaped), or preset JSONL pages.
4. **SSRF testing**: The `SSRF_TARGETS` list covers all major SSRF vector categories (cloud metadata, RFC 1918, loopback, CGNAT, IPv4-mapped IPv6, decimal IP encoding). The server redirects to these targets to test client-side SSRF defenses.
5. **Incomplete responses**: `_StreamingDisconnect` response class sends partial body then raises `ConnectionResetError` to simulate mid-transfer disconnections.

### 4. Shared Patterns — Is There Duplication?

Yes, significant and consistent duplication across chaosllm and chaosweb:

| Component | ChaosLLM | ChaosWeb | Notes |
|-----------|----------|----------|-------|
| CLI structure | cli.py | cli.py | Identical pattern: serve/presets/show_config |
| Config schema | ChaosLLMConfig | ChaosWebConfig | Same outer structure, different inner error types |
| Error decision type | ErrorDecision | WebErrorDecision | ~70% identical fields + web adds 4 fields |
| Error injector | ErrorInjector | WebErrorInjector | Identical composition pattern |
| Outcome classifier | OutcomeClassification | WebOutcomeClassification | Same NamedTuple pattern, different fields |
| Metrics recorder | MetricsRecorder | WebMetricsRecorder | Identical delegation pattern |
| Schema constant | LLM_METRICS_SCHEMA | WEB_METRICS_SCHEMA | Different columns, same structure |
| Content generator | ResponseGenerator | ContentGenerator | Parallel design, different domain |
| Preset bank | PresetBank (str) | PresetBank (dict) | Near-identical code, different element type |
| Server class | ChaosLLMServer | ChaosWebServer | Same lifecycle, different handlers |
| Admin endpoints | /admin/* | /admin/* | Identical |
| Burst config (Pydantic) | BurstConfig | WebBurstConfig | Different elevated-rate fields |

The duplication is intentional and well-structured — the shared code lives in `chaosengine/`, and each plugin owns its domain-specific layer. The architectural pattern (compose engine utilities, own domain decisions) is consistent. However, several pieces could be further extracted:

- `PresetBank` is duplicated almost exactly. A generic `PresetBank[T]` would eliminate both.
- The CLI `serve` command pattern (build overrides dict, load config, start uvicorn) is identical and could be a shared utility accepting a config-loader function and app-factory function.
- `ErrorDecision` and `WebErrorDecision` share significant structure. A common base could reduce duplication.
- The server `_record_request` + best-effort metrics suppression pattern is identical in both servers.

### 5. ChaosLLM MCP — What Is It For?

`chaosllm_mcp/server.py` is an MCP (Model Context Protocol) server that provides Claude with read-only analysis tools over a ChaosLLM metrics database. It is intended for post-run analysis: after running a test with `chaosllm serve`, the metrics SQLite database can be inspected via `chaosllm-mcp --database ...`.

The 9 tools cover: diagnosis, AIMD behavior analysis (backoff effectiveness, recovery times), error distribution, latency percentiles, anomaly detection, burst event inspection, error samples, time window queries, and raw SQL access (SELECT only).

This parallels the Landscape MCP server's function for audit data — it provides a structured, Claude-optimized interface to a specialized SQLite database.

**Key distinction from Landscape MCP:** ChaosLLM MCP analyzes chaos server metrics (a testing artifact), not production audit data. It has no equivalent of the audit integrity requirements.

### 6. Security Concerns

**Jinja2 (MEMORY.md concern):**
- `chaosllm/response_generator.py`: Uses `jinja2.sandbox.SandboxedEnvironment` with `autoescape=False` (JSON context). SANDBOXED. The MEMORY.md concern is addressed here.
- `chaosweb/content_generator.py`: Uses `jinja2.sandbox.SandboxedEnvironment` with `autoescape=True` (HTML context). SANDBOXED.
- The MEMORY.md concern about "unsandboxed Jinja2" in `blob_sink` and `chaosllm server/generator` appears to be outdated for the chaos servers — they are properly sandboxed. The `blob_sink` concern should be verified separately.

**X-Fake-Template header injection:**
- ChaosLLM server allows arbitrary Jinja2 templates via the `X-Fake-Template` header (bounded by `max_template_length`).
- The SandboxedEnvironment prevents Python attribute access and module imports. The exposed helpers (`random_choice`, `random_float`, etc.) have no filesystem or network access.
- Risk: LOW (localhost-only by default; sandbox is restrictive).

**SSRF redirects:**
- ChaosWeb deliberately redirects to private IP ranges to test client defenses. The `allow_external_bind` check prevents the server from being network-accessible by default.
- Risk: LOW if deployed correctly (localhost-only). If `allow_external_bind=True` is set and the server is reachable from the internet, it becomes an open SSRF redirect server. This is documented but there is no second layer of protection.

**Admin endpoints without authentication:**
- Both servers expose `/admin/config` (allows runtime error rate modification), `/admin/reset`, and `/admin/export` without authentication.
- Protected only by localhost binding. Same risk as above for external bind.

**Read-only SQL enforcement in ChaosLLM MCP:**
- Uses keyword-boundary regex matching plus SELECT prefix check. Does not use SQLite read-only connection mode. A CTE with a write statement (e.g., `WITH x AS (SELECT ...) INSERT ...`) might bypass the check. Low risk for test tooling; could be improved by using `uri=True` with `?mode=ro`.

### 7. Cross-Cutting Dependencies — What Do These Import from the Main Codebase?

The chaos testing infrastructure is largely self-contained. Main codebase imports are minimal:

- `chaosllm/cli.py`: Imports `from elspeth import __version__` for version display. This is a soft dependency (wrapped in try/except ImportError).
- `chaosweb/cli.py`: Same version import.
- `chaosllm_mcp/server.py`: No import from main elspeth codebase — only standard library and `mcp` package.
- All other chaos modules: Import only from `chaosengine.*` (sibling) or standard library/third-party (jinja2, starlette, pydantic, yaml, structlog, uvicorn, mcp).

This is good isolation. The chaos testing servers do NOT import from `elspeth.core`, `elspeth.engine`, `elspeth.plugins`, or `elspeth.contracts`. They are usable independently of the main pipeline.

The reverse is also true: main elspeth code does not import from `elspeth.testing.*`. The testing infrastructure is a one-way dependency: testing depends on nothing from main, and main depends on nothing from testing.

**Third-party dependencies used:**
- `starlette` — ASGI web framework (both servers)
- `uvicorn` — ASGI runner (CLI, optional import)
- `jinja2` + `jinja2.sandbox` — templating (both generators)
- `pydantic` — config validation (all config modules)
- `yaml` — preset loading (config_loader)
- `structlog` — logging (server, generators)
- `mcp` — MCP protocol (chaosllm_mcp)

---

## Concerns and Recommendations

### HIGH PRIORITY

**H1: `update_config` thread safety inconsistency (chaosweb/server.py)**
`ChaosLLMServer.update_config()` uses `threading.Lock` for atomic config swap; `ChaosWebServer.update_config()` does not. Under asyncio this is safe (cooperative multitasking), but the inconsistency is confusing and could become a real bug if the server is ever run with a threaded executor. Recommendation: Add `_config_lock` to `ChaosWebServer` and use it in `update_config` and `_get_current_config`, matching `ChaosLLMServer`.

**H2: `_ERROR_TYPE_MAPPING` KeyError risk (chaosllm/server.py)**
`_handle_http_error` accesses `_ERROR_TYPE_MAPPING[error_type]` without `.get()`. If a new HTTP error type is added to `ErrorInjector` without updating the server mappings, this raises `KeyError` at runtime on the first request injecting that error. `ChaosWebServer._handle_http_error` correctly uses `.get(error_type, f"{status_code} Error")`. Align ChaosLLM to use the same defensive access pattern. A test that exercises every error type in `HTTP_ERRORS` would also catch this.

**H3: Dead code — `RequestRecord` in chaosllm/metrics.py**
`RequestRecord` frozen dataclass is defined but never used for insertion. `MetricsRecorder.record_request()` takes raw keyword arguments. Either wire up `RequestRecord` as the insertion type (pass it to `record_request` and unpack internally, providing type safety) or remove it. Currently it is documentation that can drift from the actual schema.

### MEDIUM PRIORITY

**M1: Stale `# type: ignore` annotations in chaosllm/cli.py**
`import elspeth.testing.chaosllm_mcp.server as mcp_server  # type: ignore[import-not-found]` — the module exists. The second ignore `# type: ignore[attr-defined]` on `mcp_server.serve(database)` is because the MCP server's `main()` function is the correct entry point (not `serve(database)`). The chaosllm CLI calls `mcp_server.serve(database)` but the MCP server exports `main()` and `run_server(database_path)`. Either `serve()` does not exist (which would be a bug) or it needs to be added. On investigation: `chaosllm_mcp/server.py` has `run_server(database_path: str)` (async) and `main()` (CLI entry). There is no `serve()` function. The `# type: ignore[attr-defined]` suppresses the error about this missing function. This is a real bug: `mcp_server.serve(database)` will raise `AttributeError` at runtime. The CLI should call `asyncio.run(mcp_server.run_server(database))` instead.

**M2: Preset name injection into config dict (chaosengine/config_loader.py)**
`config_dict["preset_name"] = preset` is injected unconditionally into the merged config dict before Pydantic validation. This works because both `ChaosLLMConfig` and `ChaosWebConfig` have a `preset_name` field with `extra="forbid"`. Any new Pydantic config class that does NOT have `preset_name` but uses `load_config` will fail at validation. This is a hidden coupling. Recommendation: Only inject `preset_name` if the target config type has that field, or document the requirement that all chaos config classes must have `preset_name`.

**M3: Connection error set drift (chaosllm/metrics.py, chaosweb/metrics.py)**
Both `_classify_outcome` and `_classify_web_outcome` use hardcoded sets of connection error type strings for classification. These sets must stay in sync with the error injectors. Recommendation: Derive the sets from `CONNECTION_ERRORS` and `WEB_CONNECTION_ERRORS` constants (already exported from the respective `error_injector.py` modules) rather than repeating the strings.

**M4: `PresetBank` duplication**
Two near-identical `PresetBank` classes exist in `chaosllm/response_generator.py` and `chaosweb/content_generator.py`. They differ only in the return type of `next()` (`str` vs `dict[str, str]`). Recommendation: Extract a generic `PresetBank[T]` to `chaosengine/` with a JSONL-loading classmethod that takes a row-extraction callable. Both plugins could then instantiate `PresetBank[str]` and `PresetBank[dict[str, str]]`.

**M5: `_StreamingDisconnect` bypasses `Response.__init__` (chaosweb/server.py)**
Sets instance attributes directly without calling `super().__init__()`. Fragile against Starlette upgrades. Recommendation: Call `super().__init__(content=b"", status_code=status_code, media_type=media_type)` and then override the `body_iterator` attribute, or use Starlette's `StreamingResponse` correctly.

**M6: `redirect_loop_terminated` outcome string (chaosweb/server.py line 264)**
The `_redirect_hop_endpoint` records `outcome="redirect_loop_terminated"` which is not in the classification set in `_classify_web_outcome`. This means redirect loop terminations are not counted in any timeseries bucket — they appear in raw requests but not in aggregate stats. Recommendation: Add `redirect_loop_terminated` to `_classify_web_outcome` or record it as `outcome="success"` (since the loop did terminate as designed).

### LOW PRIORITY

**L1: Multi-worker config isolation undocumented (both servers)**
When run with `workers > 1`, each uvicorn worker has its own server instance. A `POST /admin/config` update only affects the worker that receives the request. This is a significant usability issue for multi-worker testing: stats from `/admin/stats` will only show that worker's requests. Document this limitation prominently in the CLI output when `workers > 1`.

**L2: ChaosLLM MCP SQL enforcement could use SQLite read-only mode**
`query()` uses regex keyword-matching for write prevention. More robust: open the connection as `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)`. This prevents writes at the SQLite level, not just at the application level.

**L3: `BurstConfig` naming proliferation**
Three types named `BurstConfig` (or `WebBurstConfig`): the chaosengine frozen dataclass, the ChaosLLM Pydantic model, and the ChaosWeb Pydantic model. The engine-layer dataclass is imported as `EngineBurstConfig` in both injectors to disambiguate. Rename the Pydantic models to `LLMBurstSettings` / `WebBurstSettings` to match the `*Settings` convention and avoid confusion with the engine-layer type.

**L4: `update_timeseries` method name on MetricsRecorder is misleading**
`MetricsRecorder.update_timeseries()` rebuilds the entire timeseries from scratch (calls `rebuild_timeseries`). The name suggests an incremental update. Rename to `rebuild_timeseries()` to match the underlying method name.

**L5: `generate_wrong_content_type` ignores passed RNG in some call sites**
In `chaosweb/server.py`, `generate_wrong_content_type()` is called without passing `self._content_generator._rng` (and indeed cannot, as the content generator's RNG is private). This creates a separate non-seeded RNG instance for wrong-content-type selection. Minor issue for testing determinism.

---

## Confidence Assessment

**Overall confidence: HIGH**

- All 20 files were read in full.
- The architecture is clear and well-organized: shared utilities in `chaosengine/`, domain-specific code in `chaosllm/` and `chaosweb/`, MCP analysis in `chaosllm_mcp/`.
- The duplication patterns are consistent and intentional.
- The security properties (Jinja2 sandboxing, localhost binding, read-only SQL) are understood.
- The one confirmed bug (M3: `mcp_server.serve()` does not exist) is unambiguous.
- The thread-safety inconsistency (H1) is real but low-risk under asyncio.
- No external code was left unread; no uncertainty about file contents.

**Known limits:**
- Preset YAML files were not read — cannot verify preset content correctness.
- Tests for the chaos infrastructure were not reviewed — cannot confirm test coverage.
- The actual `validate_url_for_ssrf` behavior in the main codebase was not checked against the `SSRF_TARGETS` list — cannot confirm all vectors are blocked.
- `blob_sink.py` was not reviewed — the MEMORY.md concern about unsandboxed Jinja2 in blob_sink remains unresolved by this analysis.
