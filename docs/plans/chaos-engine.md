 ChaosEngine: Unified Chaos Testing Platform

 Context

 ChaosLLM (~2,466 lines) and ChaosWeb (~2,564 lines) are parallel implementations of fault-injection test servers with ~80% structural overlap. Both follow the same 5-layer architecture (config, error injector, content generator,
 metrics, server) but were built independently. The user wants to extract shared infrastructure into a chaosengine core package, making both systems thin plugins, and enabling future plugins: ChaosFile (virtual filesystem),
 ChaosSQL (fake database), ChaosSocket (raw TCP), ChaosMail (SMTP).

 The critical architectural insight: not all plugins are HTTP servers. ChaosFile and ChaosSQL are in-process. ChaosSocket is TCP. ChaosMail is SMTP. The base abstraction must be transport-agnostic.

 Package Structure

 src/elspeth/testing/
     chaosengine/                    # NEW: Core shared infrastructure
         __init__.py                 # Public API
         config.py                   # ServerConfig, MetricsConfig, LatencyConfig, BurstConfigBase
         error_injector.py           # BaseErrorInjector, ErrorSpec, ErrorDecision
         latency.py                  # LatencySimulator (moved from chaosllm)
         metrics.py                  # BaseMetricsRecorder, MetricsSchema, ColumnDef
         preset.py                   # deep_merge, load_config, list_presets, load_preset
         vocabulary.py               # ENGLISH_VOCABULARY, LOREM_VOCABULARY
         server.py                   # BaseChaosServer (optional, HTTP-only mixin)
         fixture.py                  # BaseChaosFixture (shared pytest patterns)
         cli.py                      # Unified CLI root + shared helpers
     chaosllm/                       # REFACTORED: LLM plugin
         (same files, now imports from chaosengine)
     chaosweb/                       # REFACTORED: Web plugin
         (same files, now imports from chaosengine)
     chaosllm_mcp/                   # UNCHANGED initially

 Phase 1: Extract chaosengine Core Types

 Create chaosengine/ with types currently defined in chaosllm/config.py and imported by chaosweb/config.py.

 1a. chaosengine/config.py

 Move from chaosllm/config.py:

- ServerConfig (lines 18-37) — unchanged
- MetricsConfig (lines 40-53) — unchanged, no default DB (plugins set their own)
- LatencyConfig (lines 145-159) — unchanged

 New:

- BurstConfigBase — base burst pattern fields (enabled, interval_sec, duration_sec); plugins extend with protocol-specific elevated rates

 1b. chaosengine/latency.py

 Move LatencySimulator from chaosllm/latency_simulator.py (79 lines). Change import of LatencyConfig to chaosengine.config. Identical behavior.

 1c. chaosengine/vocabulary.py

 Move ENGLISH_VOCABULARY and LOREM_VOCABULARY from chaosllm/response_generator.py. Both ChaosLLM and ChaosWeb already use these.

 1d. chaosengine/preset.py

 Extract from chaosllm/config.py:

- deep_merge() (rename from_deep_merge, now public)
- Generic load_config(config_class, presets_dir, *, preset, config_file, cli_overrides)
- Generic list_presets(presets_dir) and load_preset(presets_dir, name)

 Both ChaosLLM and ChaosWeb have identical implementations of these — only the config class and presets directory differ.

 1e. Update imports

- chaosllm/config.py — delete ServerConfig, MetricsConfig, LatencyConfig, _deep_merge, load_config, list_presets, load_preset; import from chaosengine
- chaosweb/config.py — change imports from chaosllm.config to chaosengine.config and chaosengine.preset
- chaosllm/latency_simulator.py — delete file; chaosllm/__init__.py re-exports from chaosengine.latency
- chaosllm/response_generator.py — import vocabularies from chaosengine.vocabulary
- chaosweb/content_generator.py — import vocabularies from chaosengine.vocabulary

 1f. Verification

- All 8,200+ existing tests pass
- mypy src/ clean
- ruff check src/ clean
- Zero behavioral change — pure extraction

 ---
 Phase 2: Extract BaseErrorInjector

 The error injectors are the largest duplication (~490 lines each, ~80% algorithmic overlap). The shared algorithm: threading, burst state machine, priority/weighted selection, _should_trigger(). The difference: which error types
 exist and how decisions are built.

 2a. chaosengine/error_injector.py

 ErrorDecision — unified base decision type (frozen dataclass):
 @dataclass(frozen=True, slots=True)
 class ErrorDecision:
     error_type: str | None
     status_code: int | None = None
     category: str | None = None          # String, not enum — plugins define their own
     retry_after_sec: int | None = None
     delay_sec: float | None = None
     start_delay_sec: float | None = None
     malformed_type: str | None = None

 Key design: category is str | None, not an enum. Plugins define category constants (LLM uses "http"/"connection"/"malformed", Web adds "redirect", File would use "filesystem", SQL would use "deadlock"). This avoids a fragile enum
  hierarchy across unrelated plugins.

 Properties: should_inject, is_connection_level (checks category == "connection"), is_malformed (checks category == "malformed").

 Class methods: success(), http_error(), connection_error(), malformed_response().

 WebErrorDecision(ErrorDecision) — extends with web-specific typed fields:
 @dataclass(frozen=True, slots=True)
 class WebErrorDecision(ErrorDecision):
     redirect_target: str | None = None
     redirect_hops: int | None = None
     incomplete_bytes: int | None = None
     encoding_actual: str | None = None

 Additional class methods: redirect(), malformed_content().
 Additional property: is_redirect.

 This uses frozen dataclass inheritance (Python 3.10+ with slots). The base engine works with ErrorDecision; web-specific code uses WebErrorDecision.

 ErrorSpec — declarative error type specification:
 @dataclass(frozen=True, slots=True)
 class ErrorSpec:
     name: str
     get_pct: Callable[[], float]
     build: Callable[[], ErrorDecision]
     priority: int

 Each injectable error is described by: a name, a callable returning the current percentage (may be burst-adjusted), a callable building the decision, and a priority (lower = checked first in priority mode).

 BaseErrorInjector — generic engine with pluggable specs:

- Constructor: selection_mode, burst_enabled, burst_interval_sec, burst_duration_sec, time_func, rng
- Shared methods (moved here): _get_current_time(),_is_in_burst(), _should_trigger(), is_in_burst(), reset()
- decide() → calls _build_specs(elapsed) then routes to _decide_priority(specs) or _decide_weighted(specs)
- _decide_priority(specs) — iterate specs sorted by priority, first trigger wins
- _decide_weighted(specs) — weight-proportional random selection
- Abstract method: _build_specs(elapsed: float) -> list[ErrorSpec] — plugins implement this

 2b. Refactor chaosllm/error_injector.py

- ErrorCategory enum stays (for LLM-specific categorization in string form)
- ErrorDecision class deleted — import from chaosengine
- ErrorInjector → LLMErrorInjector(BaseErrorInjector):
  - Constructor calls super().__init__() with burst/selection params from config
  - Implements _build_specs(elapsed) returning LLM-specific ErrorSpec list
  - Keeps LLM-specific pickers: _pick_retry_after(),_pick_timeout_delay(), _build_timeout_decision(), etc.

 2c. Refactor chaosweb/error_injector.py

- WebErrorCategory enum stays (string constants)
- WebErrorDecision stays but inherits from chaosengine.ErrorDecision
- WebErrorInjector → WebErrorInjector(BaseErrorInjector):
  - Same pattern as LLM
  - Implements _build_specs(elapsed) returning web-specific specs
  - Keeps web-specific pickers: _pick_ssrf_target(),_pick_incomplete_bytes(), _pick_redirect_hops()

 2d. Verification

- Property tests for error injection pass (same probabilistic behavior)
- Unit tests pass with updated imports
- HTTP_ERRORS, CONNECTION_ERRORS, MALFORMED_TYPES constants stay in their plugin modules

 ---
 Phase 3: Extract BaseMetricsRecorder

 The metrics recorders are ~85% identical. Shared: thread-local SQLite connections, WAL mode, time-series bucketing, percentile computation, get_stats(), export_data(), reset(), save_run_info(). Different: request table columns,
 timeseries bucket columns, outcome classifier.

 3a. chaosengine/metrics.py

 ColumnDef — SQL column definition:
 @dataclass(frozen=True, slots=True)
 class ColumnDef:
     name: str
     sql_type: str          # "TEXT", "INTEGER", "REAL"
     nullable: bool = True

 MetricsSchema — plugin-provided schema extension:
 @dataclass(frozen=True, slots=True)
 class MetricsSchema:
     request_columns: tuple[ColumnDef, ...]
     timeseries_columns: tuple[ColumnDef, ...]
     request_indexes: tuple[str, ...] = ()   # Additional index column names

 BaseMetricsRecorder:

- Base request columns (always present): request_id, timestamp_utc, outcome, status_code, error_type, injection_type, latency_ms, injected_delay_ms
- Base timeseries columns: bucket_utc, requests_total, requests_success, avg_latency_ms, p99_latency_ms
- run_info table: identical across all plugins
- Constructor takes MetricsConfig + MetricsSchema, generates DDL from schema
- All shared methods move here: _get_connection(), _init_schema(), record_request(**kwargs),_update_timeseries(),_update_bucket_latency_stats(), reset(), get_stats(), export_data(), save_run_info(), get_requests(),
 get_timeseries(), close()
- Abstract method: _classify_outcome(outcome, status_code, error_type) -> dict[str, int] — returns column_name → 0/1 for timeseries update

 3b. Refactor plugin metrics

- chaosllm/metrics.py — LLMMetricsRecorder(BaseMetricsRecorder): defines LLM schema + classifier, typed record_request() wrapper
- chaosweb/metrics.py — WebMetricsRecorder(BaseMetricsRecorder): defines web schema + classifier, typed record_request() wrapper

 3c. Verification

- Metrics recording tests pass identically
- Time-series aggregation tests pass
- Stats output format unchanged

 ---
 Phase 4: Extract Server Base + Fixture Base

 4a. chaosengine/server.py — BaseChaosServer

 For HTTP-server plugins only. Provides:

- Constructor pattern: init error_injector, latency_simulator, metrics_recorder, content_generator, record_run_info, create_app
- Lifecycle methods: reset(), export_metrics(), update_config(), get_stats(),_get_current_config(), _record_run_info()
- Admin endpoint handlers: _health_endpoint(), _admin_config_endpoint(),_admin_stats_endpoint(), _admin_reset_endpoint(),_admin_export_endpoint()
- Properties: app, run_id
- Abstract methods: _create_routes() (plugin adds protocol-specific routes), _create_content_generator(),_create_error_injector(), _create_metrics_recorder()

 ChaosLLMServer(BaseChaosServer) and ChaosWebServer(BaseChaosServer) implement the abstract methods and add their protocol-specific request handlers.

 4b. chaosengine/fixture.py — BaseChaosFixture

 Shared fixture infrastructure:

- Config-from-marker builder pattern
- get_stats(), export_metrics(), update_config(), reset(), wait_for_requests()
- Properties: admin_url, run_id, metrics_db
- HTTP-specific: TestClient integration (for server-based plugins)

 ChaosLLMFixture(BaseChaosFixture) adds post_completion(), post_azure_completion().
 ChaosWebFixture(BaseChaosFixture) adds fetch_page().

 4c. Verification

- All existing fixture-based tests pass
- Admin endpoint behavior identical

 ---
 Phase 5: Unified CLI

 5a. chaosengine/cli.py

 Unified Typer CLI with plugin subcommands:
 chaosengine llm serve --preset=stress_aimd
 chaosengine web serve --port=8200
 chaosengine llm presets
 chaosengine web show-config
 chaosengine plugins                  # List available plugins

 Each plugin registers a Typer sub-app. The shared CLI base provides version callback, preset listing, and show-config patterns.

 5b. Entry points in pyproject.toml

 [project.scripts]
 chaosengine = "elspeth.testing.chaosengine.cli:main"
 chaosllm = "elspeth.testing.chaosllm.cli:main"        # Preserved
 chaosweb = "elspeth.testing.chaosweb.cli:main"         # New
 chaosllm-mcp = "elspeth.testing.chaosllm.cli:mcp_main_entry"  # Preserved

 5c. Verification

- chaosengine llm serve works identically to chaosllm serve
- chaosengine web serve works identically to chaosweb serve
- Old entry points still work

 ---
 Phase 6: Tests

 Update test imports and structure:

- Unit tests for chaosengine/ core (error injection algorithm, metrics schema generation, preset loading, latency simulation)
- Property tests for BaseErrorInjector probabilistic behavior
- Existing ChaosLLM/ChaosWeb tests updated with new imports
- Fixture tests exercise the BaseChaosFixture pattern

 ---
 Future Plugin Sketches (Validates Architecture)

 These are NOT implemented in this refactoring. They demonstrate the architecture supports non-HTTP plugins.

 ChaosFile (in-process virtual filesystem)

 chaosfile/
     config.py      — ChaosFileConfig (MetricsConfig + LatencyConfig + FileErrorConfig, NO ServerConfig)
     error_injector.py — FileErrorInjector(BaseErrorInjector) with specs: permission_denied, file_not_found,
                         disk_full, corrupted_content, encoding_error, slow_read
     filesystem.py  — VirtualFilesystem: open(), read(), write(), listdir() with fault injection
     metrics.py     — FileMetricsRecorder(BaseMetricsRecorder) with columns: file_path, operation, bytes

 ChaosSQL (in-process fault-injecting DB wrapper)

 chaossql/
     config.py      — ChaosSQLConfig (MetricsConfig + LatencyConfig + SQLErrorConfig, NO ServerConfig)
     error_injector.py — SQLErrorInjector(BaseErrorInjector) with specs: deadlock, lock_timeout,
                         connection_error, corrupted_result, slow_query, constraint_violation
     engine.py      — ChaosDBEngine: wraps real SQLite, intercepts execute() to inject faults
     metrics.py     — SQLMetricsRecorder(BaseMetricsRecorder) with columns: query_type, table_name

 ChaosSocket (raw TCP server)

 chaossocket/
     config.py      — ChaosSocketConfig (ServerConfig + MetricsConfig + LatencyConfig + SocketErrorConfig)
     error_injector.py — SocketErrorInjector(BaseErrorInjector) with specs: connection_reset, partial_data,
                         slow_read, corrupted_bytes, connection_refused
     server.py      — ChaosSocketServer: asyncio TCP server (NOT Starlette/HTTP)
     metrics.py     — SocketMetricsRecorder(BaseMetricsRecorder) with columns: bytes_sent, bytes_received

 ChaosMail (SMTP server)

 chaosmail/
     config.py      — ChaosMailConfig (ServerConfig + MetricsConfig + LatencyConfig + MailErrorConfig)
     error_injector.py — MailErrorInjector(BaseErrorInjector) with specs: connection_refused, bounce,
                         slow_delivery, malformed_headers, encoding_error, spam_reject
     server.py      — ChaosMailServer: aiosmtpd-based SMTP server
     metrics.py     — MailMetricsRecorder(BaseMetricsRecorder) with columns: sender, recipient, message_size

 ---
 Key Design Decisions
 ┌─────────────────────────────────────────────────────┬──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
 │                      Decision                       │                                                                    Rationale                                                                     │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ category is str, not enum                           │ Plugins define their own categories (LLM: 3, Web: 4, File: different). Enum hierarchy would be fragile across unrelated plugins.                 │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ ErrorSpec list replaces if-chains                   │ The 100-line _decide_priority() methods are pure data. Declarative specs eliminate duplication and make selection testable independently.        │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ Per-plugin ErrorDecision subclasses, not extra dict │ Typed fields over untyped dicts. WebErrorDecision(ErrorDecision) adds redirect_target etc. Keeps ELSPETH's "no defensive programming" principle. │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ Per-plugin MCP servers                              │ Domain-specific analysis (AIMD for LLM, redirect chains for Web). Unified MCP would need runtime schema discovery for no clear benefit.          │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ No pluggy for chaos plugins                         │ Closed set of system-owned plugins. No dynamic discovery needed. Explicit wiring is simpler and matches ELSPETH's plugin ownership model.        │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ Schema-driven metrics SQL generation                │ 85% of metrics code is identical. The 15% difference is column definitions. Generated DDL eliminates duplication while keeping SQL explicit.     │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ Phased migration                                    │ 8,200+ tests, 40+ files with imports. Each phase independently verifiable with zero behavioral change until the extraction is complete.          │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ ServerConfig is optional per plugin                 │ ChaosFile/ChaosSQL are in-process — they don't bind to ports. Server config is composed by plugins that need it, not inherited from a base.      │
 └─────────────────────────────────────────────────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
 Critical Files
 ┌────────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────┐
 │                        File                        │                      Role in Refactoring                       │
 ├────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
 │ src/elspeth/testing/chaosllm/config.py             │ Source of truth for shared types to extract                    │
 ├────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
 │ src/elspeth/testing/chaosllm/error_injector.py     │ Core algorithm (~350 lines) becomes BaseErrorInjector          │
 ├────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
 │ src/elspeth/testing/chaosllm/metrics.py            │ Infrastructure (~600 lines) becomes BaseMetricsRecorder        │
 ├────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
 │ src/elspeth/testing/chaosllm/latency_simulator.py  │ Moves to chaosengine/latency.py unchanged                      │
 ├────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
 │ src/elspeth/testing/chaosllm/response_generator.py │ Vocabularies move to chaosengine/vocabulary.py                 │
 ├────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
 │ src/elspeth/testing/chaosweb/error_injector.py     │ Validates BaseErrorInjector abstraction handles Web too        │
 ├────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
 │ src/elspeth/testing/chaosweb/config.py             │ Currently imports from chaosllm — will import from chaosengine │
 ├────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
 │ tests/fixtures/chaosllm.py                         │ Fixture pattern to extract into BaseChaosFixture               │
 ├────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
 │ tests/fixtures/chaosweb.py                         │ Second fixture validating the base pattern                     │
 ├────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
 │ pyproject.toml                                     │ Entry points for CLI commands                                  │
 └────────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────┘
 Verification Plan

 After each phase:

 1. .venv/bin/python -m pytest tests/ — all tests pass
 2. .venv/bin/python -m mypy src/ — type checking clean
 3. .venv/bin/python -m ruff check src/ — linting clean
 4. Manually verify: chaosllm serve --preset=gentle starts correctly
 5. Manually verify: chaosweb serve --preset=gentle starts correctly
