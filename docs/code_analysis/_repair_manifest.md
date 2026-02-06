# ELSPETH Repair Manifest

**Generated:** 2026-02-06
**Source:** 153 code analysis documents in `docs/code_analysis/`
**Scope:** Full `src/elspeth/` codebase -- core, engine, plugins, contracts, telemetry, TUI, testing

---

## Executive Summary

The ELSPETH codebase is architecturally sound with a well-designed audit backbone, clean contract system, and correct trust model enforcement in the majority of files. Of 153 files analyzed:

- **2 CRITICAL** -- Security vulnerability and data loss risk requiring immediate fixes
- **3 NEEDS_REFACTOR** -- Structural problems requiring significant rework
- **98 NEEDS_ATTENTION** -- Localized issues with specific remediation paths
- **50 SOUND** -- No issues beyond minor observations

The most concerning cross-cutting patterns are: (1) SSRF/TOCTOU vulnerabilities in web-facing code, (2) non-atomic file writes in sinks that risk data loss on crash, (3) security transforms that fail open instead of closed, (4) ~2,000 lines of dead or duplicated code in the CLI, and (5) NaN/Infinity acceptance in float validation that undermines RFC 8785 canonical JSON integrity.

No evidence of systemic architectural rot. The issues cluster in specific subsystems (LLM plugins, CLI, sinks) rather than being distributed uniformly, indicating the core framework is stable.

---

## P0: Fix Before Next Deploy

These issues represent active security vulnerabilities, data loss risks, or correctness bugs that could produce wrong audit results in production.

### P0-01: DNS Rebinding TOCTOU in SSRF Prevention

**File:** `src/elspeth/core/security/web.py` (84 lines)
**Lines:** 51-84 + `web_scrape.py:150-170`
**Verdict:** CRITICAL

`validate_ip()` resolves a hostname via `socket.gethostbyname()`, validates the IP against blocked ranges, but the caller discards the resolved IP. The HTTP client (`httpx`) performs its own DNS resolution when connecting. Between the two resolutions, an attacker-controlled DNS server can change the A record from a safe public IP to a blocked internal IP (e.g., `169.254.169.254` for cloud metadata service).

Additionally, `socket.gethostbyname()` only resolves IPv4. If `httpx` resolves and connects via IPv6, the validated IP is irrelevant. Missing blocked ranges include `0.0.0.0/8`, `100.64.0.0/10` (CGNAT), `fe80::/10` (link-local IPv6), and `::ffff:0:0/96` (IPv4-mapped IPv6).

**Remediation:**
1. Return the resolved IP from `validate_ip()` and pass it to the HTTP client so it connects to the validated address, not a re-resolved one.
2. Use `socket.getaddrinfo()` instead of `gethostbyname()` to resolve both A and AAAA records.
3. Add missing blocked ranges: `0.0.0.0/8`, `100.64.0.0/10`, `fe80::/10`, `::ffff:0:0/96`.
4. Consider using `httpx` transport hooks to validate the connection IP at connect time.

**Affected components:** `web_scrape` transform, any future HTTP-fetching transform.

---

### P0-02: JSON Sink Data Loss on Crash (Non-Atomic Write)

**File:** `src/elspeth/plugins/sinks/json_sink.py` (537 lines)
**Lines:** 310-317
**Verdict:** CRITICAL

In JSON array mode, `_write_json_array()` performs `seek(0)`, `truncate()`, then `json.dump()`. After `truncate()`, the file is empty. If the process crashes, is killed, or `json.dump()` raises (e.g., non-serializable value), ALL previously written data is destroyed. The file is left empty or partially written.

Secondary issue: `self._rows` grows without bound in JSON array mode (all rows held in memory for the entire run), creating OOM risk for large datasets.

**Remediation:**
1. Write to a temporary file, then atomically rename (`os.replace()`) to the target path. This ensures the original file is intact until the new write completes.
2. For memory: consider streaming JSON array output (write opening bracket, append rows with commas, write closing bracket on close) instead of rewriting the entire array on each batch.

**Affected components:** Any pipeline using JSON array output format.

---

### P0-03: Content Safety Transform Fails Open on Unknown Categories

**File:** `src/elspeth/plugins/transforms/azure/content_safety.py` (526 lines)
**Lines:** 451-467
**Verdict:** NEEDS_ATTENTION (elevated to P0 due to security impact)

When Azure Content Safety returns an unknown category name, the category mapping falls through silently. The content is treated as safe. For a content safety transform, this means dangerous content passes through unchecked when Azure updates their category taxonomy.

**Remediation:**
1. Replace the string-manipulation category mapping with an explicit lookup table.
2. Reject unknown categories -- fail closed, not open. Return `TransformResult.error()` with `retryable=False` for unrecognized categories.
3. Log the unknown category name at WARNING level so operators are alerted.

---

### P0-04: Prompt Shield Transform Fails Open on Malformed Response

**File:** `src/elspeth/plugins/transforms/azure/prompt_shield.py` (459 lines)
**Lines:** 427-441
**Verdict:** NEEDS_ATTENTION (elevated to P0 due to security impact)

When the Azure Prompt Shield API returns a malformed response (missing `attackDetected` field, wrong type, etc.), the transform passes the content through as safe. The comment says "fail closed" but the implementation fails open. No type validation is performed on `attackDetected` values (Tier 3 boundary violation).

**Remediation:**
1. Validate the response structure immediately at the Tier 3 boundary: check `attackDetected` exists, is a dict, and contains expected keys.
2. On any validation failure, return `TransformResult.error()` with `retryable=True` (API anomaly, retry might get clean response).
3. Fix the secondary issue: user content is sent as both `userPrompt` AND `documents`, which is semantically wrong and wastes API resources.

---

### P0-05: NoneType Crash on Content-Filtered LLM Responses

**File:** `src/elspeth/plugins/llm/openrouter_multi_query.py` (1,253 lines)
**Lines:** 846
**Verdict:** NEEDS_REFACTOR (P0 component)

When OpenRouter returns `null` content (content filtering, provider error), `content.strip()` at line 846 throws `AttributeError: 'NoneType' object has no attribute 'strip'`. This crashes the entire pipeline rather than quarantining the affected row.

**Remediation:**
1. Check `if content is None` before `.strip()` and return `TransformResult.error()` with reason `"content_filtered"`.
2. Also add this check to the single-query OpenRouter transform for consistency.

---

### P0-06: NaN/Infinity Acceptance in Float Validation

**File:** `src/elspeth/contracts/config/runtime.py` (598 lines)
**Lines:** 74-75
**Also:** `src/elspeth/plugins/llm/validation.py` (74 lines)
**Verdict:** NEEDS_ATTENTION (elevated to P0 due to audit integrity impact)

`_validate_float_field()` does not reject `NaN` or `Infinity`. These values pass through to runtime config, potentially reaching the canonical JSON layer which strictly rejects them (causing a crash during audit recording, not during validation). The LLM validation module has the same gap.

**Remediation:**
1. Add `math.isfinite()` check in `_validate_float_field()`.
2. Add the same check in LLM validation's float acceptance.
3. This aligns with the existing RFC 8785 rejection of NaN/Infinity in canonical.py.

---

## P1: Fix This Sprint

These issues represent correctness problems, code quality violations of CLAUDE.md policy, or reliability risks that should be addressed before RC-2 stabilization.

### P1-01: Dead Code -- 311-line `_execute_pipeline` Function

**File:** `src/elspeth/cli.py` (2,417 lines)
**Lines:** 675-985
**Verdict:** NEEDS_REFACTOR

A 311-line function annotated as "deprecated" that is never called. Directly violates the No Legacy Code Policy. Delete entirely.

---

### P1-02: Plaintext Secrets Persist in Memory

**Files:** `src/elspeth/core/security/config_secrets.py` (183 lines), `src/elspeth/cli.py`
**Lines:** config_secrets.py:152, cli.py:257

Secret resolution records contain `"secret_value"` keys with plaintext values that persist through the entire pipeline startup phase. These records are passed through multiple function calls and stored in lists.

**Remediation:** Clear `secret_value` from resolution records immediately after fingerprinting. Mutate the records in `record_secret_resolutions()` to delete the key, or restructure to separate the fingerprint record from the resolution record.

---

### P1-03: Datadog Exporter Mutates Global Environment

**File:** `src/elspeth/telemetry/exporters/datadog.py` (333 lines)
**Lines:** 147-148, 150
**Verdict:** NEEDS_REFACTOR

`configure()` sets `os.environ["DD_AGENT_HOST"]` and `os.environ["DD_TRACE_AGENT_PORT"]` as process-global side effects that persist after `close()`. The `ddtrace.tracer` singleton's `shutdown()` kills tracing for the entire process, including other libraries.

**Remediation:**
1. Save original env var values in `configure()`, restore in `close()`.
2. Use `ddtrace` API that accepts agent configuration directly rather than via env vars, if available.
3. Document that the Datadog exporter is process-exclusive (cannot coexist with other ddtrace users).

---

### P1-04: Missing `extra="forbid"` on Pydantic Settings Models

**File:** `src/elspeth/core/config.py` (1,598 lines)
**Lines:** 861 (ElspethSettings) and most sub-models
**Verdict:** NEEDS_ATTENTION

Most Settings models (including `ElspethSettings`, `SourceSettings`, `TransformSettings`) do not set `extra="forbid"`. Typos in `settings.yaml` are silently ignored. A user configuring `max_retries` instead of `max_attempts` would get default behavior with no warning.

**Remediation:** Add `model_config = ConfigDict(extra="forbid")` to all Settings models that represent user-facing configuration. Some models already have it (e.g., `RetrySettings`); the others need it for consistency.

---

### P1-05: Defensive hasattr/getattr Patterns in Engine Executors

**File:** `src/elspeth/engine/executors.py` (2,235 lines)
**Lines:** 168, 175, 258, 306
**Verdict:** NEEDS_ATTENTION

Multiple uses of `hasattr(transform, "is_batch_aware")` and `getattr(transform, "batch_adapter", None)` to check for plugin capabilities. Per CLAUDE.md, these defensive patterns hide bugs. The `is_batch_aware` attribute is part of the transform protocol; use direct access.

**Remediation:** Replace `hasattr`/`getattr` with direct attribute access. If `is_batch_aware` is a required protocol attribute, access it directly. The batch adapter storage should use a proper typed attribute, not monkey-patching.

---

### P1-06: CLI Event Formatter Duplication (~600 lines)

**File:** `src/elspeth/cli.py` (2,417 lines)
**Lines:** 807-935, 1091-1219, 1780-1830
**Verdict:** NEEDS_REFACTOR

The same set of event formatters is defined three times in the CLI module. This is ~600 lines of duplicated code that must be kept in sync.

**Remediation:** Extract formatters into a shared factory or registry function. Call it once from each command that needs event formatting.

---

### P1-07: Orchestrator Run/Resume Code Duplication (~800 lines)

**File:** `src/elspeth/engine/orchestrator/core.py` (2,319 lines)
**Lines:** run() and resume() paths
**Verdict:** NEEDS_ATTENTION

The `run()` and `resume()` methods share ~800 lines of nearly identical outcome-handling and finalization logic. Missing `rows_succeeded` increments in the resume path is a direct consequence of this duplication.

**Remediation:** Extract shared finalization logic into a private method. Both `run()` and `resume()` should call it.

---

### P1-08: Silent JSONDecodeError Swallow in Landscape Recorder

**File:** `src/elspeth/core/landscape/recorder.py` (3,233 lines)
**Lines:** 2662
**Verdict:** NEEDS_ATTENTION

`explain_row()` catches `json.JSONDecodeError` silently when parsing audit data. Per the Three-Tier Trust Model, audit database data is Tier 1 (full trust). JSON parse failures on our own data indicate corruption and should crash immediately, not be silently swallowed.

**Remediation:** Remove the `JSONDecodeError` catch or convert it to a crash with an `AuditIntegrityError`.

---

### P1-09: OpenRouter Multi-Query Missing Output Key Collision Validation

**File:** `src/elspeth/plugins/llm/openrouter_multi_query.py` (1,253 lines)
**Lines:** 57-193
**Verdict:** NEEDS_REFACTOR

The Azure multi-query variant has `validate_no_output_key_collisions` (checks for duplicate names, reserved suffix collisions). The OpenRouter variant lacks this entirely. Combined with `output.update(result.row)` merge semantics, duplicate output keys silently overwrite each other, corrupting pipeline data.

**Remediation:** Either share the validator via a mixin/base class, or copy it to the OpenRouter config class. This is a data integrity issue.

---

### P1-10: SSRF TOCTOU in Web Scrape Transform

**File:** `src/elspeth/plugins/transforms/web_scrape.py` (293 lines)
**Lines:** 150-166
**Verdict:** NEEDS_ATTENTION

Same DNS rebinding vulnerability as P0-01, but in the web scrape transform specifically. The transform calls `validate_ip()`, discards the result, then passes the original hostname URL to the HTTP client.

**Remediation:** Same fix as P0-01 -- pass resolved IP to HTTP client. This is the same underlying issue; fixing web.py alone is insufficient if the caller doesn't use the resolved IP.

---

### P1-11: Non-Atomic File Writes in Payload Store

**File:** `src/elspeth/core/payload_store.py` (145 lines)
**Lines:** 103-106
**Verdict:** NEEDS_ATTENTION

`store()` writes directly to the target path with `open(path, "wb")`. If the process crashes mid-write, the file is left in a corrupted state. The hash-verified deduplication would catch this on next read, but the corrupted file persists.

**Remediation:** Write to a temp file in the same directory, then `os.replace()` to the target path.

---

### P1-12: SQLite Missing busy_timeout PRAGMA

**File:** `src/elspeth/core/landscape/database.py` (327 lines)
**Verdict:** NEEDS_ATTENTION

No `PRAGMA busy_timeout` is set on SQLite connections. Under concurrent access (e.g., pipeline writing + TUI reading), SQLite returns `SQLITE_BUSY` immediately instead of waiting. This causes spurious database errors.

**Remediation:** Add `PRAGMA busy_timeout=5000` to `_configure_sqlite()`.

---

### P1-13: ReDoS Vulnerability in Keyword Filter

**File:** `src/elspeth/plugins/transforms/keyword_filter.py` (176 lines)
**Lines:** 83
**Verdict:** NEEDS_ATTENTION

User-configured regex patterns are compiled without timeout or backtracking protection. A crafted pattern like `(a+)+$` on certain inputs causes exponential backtracking. Since patterns come from pipeline config (system-owned), this is lower severity than if they came from row data, but config errors should not hang the pipeline.

**Remediation:** Use `re.compile()` with a timeout wrapper, or pre-screen patterns for backtracking risk. Document the risk if no runtime protection is added.

---

### P1-14: batch_members Table Lacks Primary Key

**File:** `src/elspeth/core/landscape/schema.py` (506 lines)
**Lines:** 353-361
**Verdict:** NEEDS_ATTENTION

The `batch_members` table has a `UniqueConstraint("batch_id", "token_id")` but no primary key. This is unusual for relational databases and may cause issues with some ORMs, migration tools, or database backends.

**Remediation:** Convert the UniqueConstraint to a `PrimaryKeyConstraint("batch_id", "token_id")`.

---

### P1-15: Jinja2 SSTI Surface in Blob Sink and ChaosLLM

**Files:**
- `src/elspeth/plugins/azure/blob_sink.py` (637 lines) -- line 350
- `src/elspeth/testing/chaosllm/server.py` (747 lines) -- line 282
- `src/elspeth/testing/chaosllm/response_generator.py` (603 lines) -- lines 415-417

`jinja2.Environment` (unsandboxed) is used for template rendering. In blob_sink, the template source is pipeline config (system-owned, lower risk). In ChaosLLM, the template comes from the `X-Fake-Template` HTTP header (user-controlled, higher risk).

**Remediation:** Replace `jinja2.Environment` with `jinja2.SandboxedEnvironment` in all cases. This is defense-in-depth and costs nothing.

---

### P1-16: Per-Criterion max_tokens Silently Ignored (OpenRouter Multi-Query)

**File:** `src/elspeth/plugins/llm/openrouter_multi_query.py` (1,253 lines)
**Lines:** 169-189
**Verdict:** NEEDS_REFACTOR

`expand_queries()` does not pass `max_tokens=criterion.max_tokens` to `QuerySpec`. Users who configure per-criterion token limits get no effect. The Azure variant correctly passes this field.

**Remediation:** Add `max_tokens=criterion.max_tokens` to the `QuerySpec` construction in `expand_queries()`.

---

### P1-17: Sequential Path Does Not Catch Retryable LLMClientError

**File:** `src/elspeth/plugins/llm/azure_multi_query.py` (1,089 lines)
**Lines:** 842-854
**Verdict:** NEEDS_ATTENTION

In `_execute_queries_sequential()`, retryable `LLMClientError` (NetworkError, ServerError) is not caught. The error propagates as an unhandled exception, crashing the row instead of marking it retryable.

**Remediation:** Add `except LLMClientError` to the sequential path's exception handling, matching the concurrent path's behavior.

---

### P1-18: Truthiness-Based Filtering Loses Falsy Values in Recorder

**File:** `src/elspeth/core/landscape/recorder.py` (3,233 lines)
**Lines:** 1690-1694
**Verdict:** NEEDS_ATTENTION

`update_batch_status()` filters update values using truthiness checks. This silently drops legitimate falsy values like `0`, `0.0`, `""`, and `False`. Use `is not None` checks instead.

---

## P2: Technical Debt

These issues are correctness or quality problems that should be tracked but do not require immediate action.

### P2-01: Recorder God Class (3,233 lines)

**File:** `src/elspeth/core/landscape/recorder.py`

The `LandscapeRecorder` class is 3,233 lines with 80+ methods. It handles row management, node state, calls, batches, operations, routing, outcomes, checkpoints, and lineage. Extract cohesive method groups into focused modules.

---

### P2-02: N+1 Query Patterns in Landscape Layer

**Files:**
- `src/elspeth/core/landscape/lineage.py` -- routing events and calls per node state
- `src/elspeth/core/landscape/exporter.py` -- batch members, operation calls
- `src/elspeth/core/checkpoint/recovery.py` -- `get_unprocessed_row_data`
- `src/elspeth/mcp/server.py` -- `get_recent_activity()`

Multiple locations fetch related data inside loops instead of batch-fetching with IN clauses. Performance impact is proportional to pipeline size.

---

### P2-03: Processor Work Queue Duplication (~4 near-identical loops)

**File:** `src/elspeth/engine/processor.py` (2,004 lines)
**Lines:** 381-437, 1309-1387, 1389-1459, 1461-1511

Four near-identical work queue processing loops with minor variations. Extract a parameterized loop function.

---

### P2-04: LLM Plugin Code Duplication (Azure vs OpenRouter)

**Files:**
- `openrouter_multi_query.py` (1,253 lines) vs `azure_multi_query.py` (1,089 lines)
- `openrouter.py` (719 lines) vs `azure.py` (759 lines)
- `openrouter_batch.py` (783 lines) vs `azure_batch.py` (1,261 lines)

Significant duplication across Azure and OpenRouter variants: config classes, JSON schema building, output mapping, response parsing, Langfuse tracing. Extract shared logic into base classes or utilities.

---

### P2-05: Expression Parser Mutable Operator Allowlists

**File:** `src/elspeth/engine/expression_parser.py` (583 lines)
**Lines:** 48-83
**Known bug:** P2-2026-02-05

Operator allowlists are mutable sets at module level. Runtime code could theoretically modify them. Make them `frozenset`.

---

### P2-06: Thread Pool Executor P2 Bugs (3 confirmed)

**File:** `src/elspeth/plugins/pooling/executor.py` (479 lines)

1. AIMD throttle stats accumulate across batches without reset (lines 144-148, 178)
2. Dispatch gate uses `min_dispatch_delay_ms` instead of AIMD `current_delay_ms` (lines 306-356)
3. `_shutdown` flag read/written without synchronization (lines 116-125)

---

### P2-07: Template File Path Traversal

**File:** `src/elspeth/core/config.py` (1,598 lines)
**Lines:** 1407-1415, 1422-1438

Template file loading (`_expand_config_templates`) does not prevent path traversal. A settings.yaml with `template: "../../../etc/passwd"` would read arbitrary files. Since config is system-owned, this is low severity but should be hardened.

---

### P2-08: CSV Sink Append Mode Hash Semantics

**File:** `src/elspeth/plugins/sinks/csv_sink.py` (617 lines)
**Lines:** 266-271

Content hash in append mode represents the cumulative file state (re-reads entire file after each write), not the batch written. This is O(N^2) over the run and the semantic meaning is ambiguous for audit purposes.

---

### P2-09: Coalesce Executor Union Merge Overwrites

**File:** `src/elspeth/engine/coalesce_executor.py` (903 lines)
**Lines:** 543-550

Union merge strategy silently overwrites fields from earlier branches with later branches when field names collide. Iteration order depends on `settings.branches`, not arrival order.

---

### P2-10: Journal Silent Self-Disabling

**File:** `src/elspeth/core/landscape/journal.py` (215 lines)
**Lines:** 111-115

On write failure, the journal permanently disables itself (`self._disabled = True`). All subsequent journal entries are silently dropped. No periodic reminder or shutdown report.

---

### P2-11: MCP Server SQL Keyword Blocklist False Positives

**File:** `src/elspeth/mcp/server.py` (2,355 lines)
**Lines:** 619-627

The SQL injection protection uses a substring check that blocks legitimate queries referencing columns like `created_at` (blocked because it contains "CREATE"). Use word-boundary-aware regex.

**Also affects:** `src/elspeth/testing/chaosllm_mcp/server.py` (lines 721-737)

---

### P2-12: ChaosLLM Metrics Thread Connection Leak

**File:** `src/elspeth/testing/chaosllm/metrics.py` (848 lines)
**Lines:** 837-848

`close()` only closes the calling thread's SQLite connection, leaking connections from all worker threads. Requires a thread-safe connection registry.

---

### P2-13: Race Condition in `_get_underlying_client()` (Azure LLM)

**File:** `src/elspeth/plugins/llm/azure.py` (759 lines)
**Lines:** 519-533

`_get_underlying_client()` is not protected by the same lock as `_get_llm_client()`. Under concurrent access (thread pool), multiple clients could be created.

---

### P2-14: Resume Command Instantiates Plugins 4 Times

**File:** `src/elspeth/cli.py` (2,417 lines)
**Lines:** 2112-2133

Source, transform, and sink plugins are each constructed 3-4 times during resume. Wasteful but not incorrect.

---

### P2-15: Direct `_data` Private Attribute Access

**Files:**
- `src/elspeth/engine/processor.py` lines 51-61
- `src/elspeth/engine/executors.py` lines 389-390, 1433-1434
- `src/elspeth/contracts/results.py`

Multiple files access `PipelineRow._data` directly instead of using `row.to_dict()`. This couples to the internal representation.

---

### P2-16: Reproducibility Read-Modify-Write Race

**File:** `src/elspeth/core/landscape/reproducibility.py` (155 lines)
**Lines:** 126-154

`update_grade_after_purge` reads current grade, computes new grade, writes back. Under concurrent purge operations, the last writer wins.

---

### P2-17: HTTP Client Per-Request Creation

**Files:**
- `src/elspeth/plugins/clients/http.py` (683 lines) -- lines 304, 519
- `src/elspeth/plugins/llm/openrouter.py` (719 lines) -- line 663

New `httpx.Client` created and destroyed per request. Connection pooling and TCP reuse are lost.

---

### P2-18: Dead Code in OpenRouter Multi-Query

**File:** `src/elspeth/plugins/llm/openrouter_multi_query.py` (1,253 lines)
**Lines:** 556-608

`_record_langfuse_trace_for_error` is defined but never called. Delete per No Legacy Code Policy.

---

### P2-19: AzureResourceNotFoundError Fallback Catches All Exceptions

**File:** `src/elspeth/core/security/secret_loader.py` (301 lines)
**Lines:** 191

When `azure.core.exceptions.ResourceNotFoundError` cannot be imported, the fallback catches all exceptions, not just resource-not-found errors.

---

### P2-20: Checkpoint Recovery Defensive .get() on Tier 1 Data

**File:** `src/elspeth/core/checkpoint/recovery.py` (472 lines)
**Lines:** 286-296

Uses `.get()` with defaults on aggregation state from the audit database. Per Tier 1 trust model, this should use direct key access (crash on corruption).

---

## P3: Improvements

These are enhancements, cleanup, and hardening opportunities that improve code quality but have no functional impact.

### P3-01: Use `Required[]` Annotations on TUI TypedDicts

**File:** `src/elspeth/tui/types.py` -- `NodeStateInfo` uses `total=False` but documents some fields as "required". Use Python 3.11+ `Required[]` annotations.

### P3-02: TUI Lineage Tree Assumes Linear Topology

**File:** `src/elspeth/tui/widgets/lineage_tree.py` -- Transform chain is rendered as linear even for DAG pipelines with forks. Document as known limitation or implement DAG display.

### P3-03: TUI Explain Screen Drops Gate/Aggregation/Coalesce Nodes

**File:** `src/elspeth/tui/screens/explain_screen.py` -- Only SOURCE, TRANSFORM, SINK node types are displayed. GATE, AGGREGATION, COALESCE are silently omitted.

### P3-04: Consolidate Type Maps Across Contract Modules

**Files:** `contracts/contract_records.py` (TYPE_MAP), `contracts/schema_contract.py` (VALID_FIELD_TYPES), `contracts/type_normalization.py` (ALLOWED_CONTRACT_TYPES), `contracts/transform_contract.py` (_TYPE_MAP) -- Four near-identical type mapping dicts. Consolidate into a single source of truth.

### P3-05: Add `datetime` to `_TYPE_MAP` in Transform Contract

**File:** `src/elspeth/contracts/transform_contract.py` -- Missing `datetime` type means transform schemas with datetime fields get wrong types.

### P3-06: TokenInfo Should Be Frozen Dataclass

**File:** `src/elspeth/contracts/identity.py` -- `TokenInfo` is mutable despite `with_updated_data` already returning new instances. Make it `frozen=True`.

### P3-07: SchemaContract `version_hash` Truncated to 64 Bits

**File:** `src/elspeth/contracts/schema_contract.py` -- SHA-256 truncated to 16 hex chars (64 bits). Birthday attack threshold is 2^32 for collision. Lengthen to 128+ bits.

### P3-08: BoundedBuffer Dead Code in Telemetry

**File:** `src/elspeth/telemetry/buffer.py` -- `BoundedBuffer` is defined but never imported or used anywhere. Delete per No Legacy Code Policy.

### P3-09: Remove Gate Dead Code from Plugin Manager

**File:** `src/elspeth/plugins/manager.py` -- `get_gates`, `get_gate_by_name`, `create_gate` methods and gate iteration in `_refresh_caches` are dead code.

### P3-10: Legacy `display_headers`/`restore_source_headers` in Sink Config

**File:** `src/elspeth/plugins/config_base.py` -- Deprecated fields should be removed per No Legacy Code Policy. Migrate all sinks to unified `headers` field.

### P3-11: `route_to_sink()` Stub in PluginContext

**File:** `src/elspeth/plugins/context.py` -- Phase 2 stub that raises `NotImplementedError`. Either implement or delete to avoid misleading API surface.

### P3-12: Missing Transform Configs in Plugin Validation

**File:** `src/elspeth/plugins/validation.py` -- `_get_transform_config_model()` is missing entries for `openrouter_batch_llm`, `openrouter_multi_query_llm`, `web_scrape`.

### P3-13: ChaosLLM Admin Endpoints Lack Authentication

**File:** `src/elspeth/testing/chaosllm/server.py` -- `/admin/config`, `/admin/reset`, `/admin/presets` endpoints have no auth. Low risk since ChaosLLM is a test tool, but should be documented.

### P3-14: Telemetry Filtering Fail-Open Default

**File:** `src/elspeth/telemetry/filtering.py` -- Unknown event types pass through the filter unconditionally. Consider fail-closed for audit-focused system.

### P3-15: Redundant Condition `path and len(path) > 0`

**File:** `src/elspeth/tui/widgets/lineage_tree.py` line 115 -- `if path` already handles empty lists.

---

## Cross-Cutting Patterns

These patterns appear across multiple files and represent systemic issues worth addressing holistically.

### CCP-01: Non-Atomic File Writes

**Affected files:** json_sink.py, payload_store.py, csv_sink.py, journal.py
**Pattern:** `open(path, "w") + write()` instead of write-to-temp-then-rename.
**Impact:** Data loss or corruption on crash.
**Fix:** Adopt a shared `atomic_write()` utility that writes to a temp file in the same directory and calls `os.replace()`.

### CCP-02: SSRF/TOCTOU in DNS Resolution

**Affected files:** web.py, web_scrape.py
**Pattern:** Hostname validated by resolving DNS, but HTTP client independently resolves, creating a window for DNS rebinding.
**Fix:** Pass resolved IP to HTTP client or use transport-level IP validation hooks.

### CCP-03: Truthiness vs Explicit None Checks

**Affected files:** recorder.py, executors.py, expression_parser.py, openrouter.py, multiple others
**Pattern:** `if value:` instead of `if value is not None:`, silently treating `0`, `""`, `False`, `0.0` as absent.
**Fix:** Audit all truthiness checks on values that could legitimately be falsy. Replace with `is not None`.

### CCP-04: Code Duplication in LLM Plugins

**Affected files:** All 6 LLM plugin files (azure/openrouter x single/multi/batch)
**Pattern:** Config classes, JSON schema builders, response parsers, Langfuse tracing, error classification are duplicated between Azure and OpenRouter variants.
**Fix:** Extract shared logic into `plugins/llm/multi_query.py` base utilities. Use composition or mixins.

### CCP-05: Code Duplication in CLI

**Affected files:** cli.py
**Pattern:** Event formatters defined 3 times (~600 lines). Run/resume finalization duplicated (~800 lines). Dead function retained (311 lines).
**Fix:** Extract formatters to shared factory. Extract finalization to shared method. Delete dead code.

### CCP-06: Defensive Programming Violations

**Affected files:** executors.py, cli_helpers.py, processor.py, recovery.py
**Pattern:** `hasattr()`, `getattr(obj, attr, default)`, `.get()` used on system-owned objects to suppress potential attribute errors.
**Fix:** Replace with direct attribute access per CLAUDE.md policy. If access fails, that's a bug to fix.

### CCP-07: Security Transforms Failing Open

**Affected files:** content_safety.py, prompt_shield.py
**Pattern:** Unknown categories or malformed responses result in content being passed through as safe.
**Fix:** Fail closed. Unknown inputs should block content, not pass it through.

### CCP-08: Direct Private Attribute Access (`_data`, `_on_error`, `_config`)

**Affected files:** processor.py, executors.py, contracts/results.py, chaosllm/server.py
**Pattern:** Accessing `row._data`, `transform._on_error`, `generator._config` instead of using public API.
**Fix:** Add public accessors where needed, or refactor to eliminate the dependency on internal structure.

### CCP-09: Unsandboxed Jinja2 Templates

**Affected files:** blob_sink.py, chaosllm/server.py, chaosllm/response_generator.py
**Pattern:** `jinja2.Environment()` used where `jinja2.SandboxedEnvironment()` should be used for defense-in-depth.
**Fix:** Global find-and-replace of `jinja2.Environment` with `jinja2.SandboxedEnvironment` where templates process external or configurable content.

### CCP-10: Missing Pydantic `extra="forbid"`

**Affected files:** config.py (most Settings models)
**Pattern:** Settings models silently accept unknown fields, meaning config typos are never reported.
**Fix:** Add `model_config = ConfigDict(extra="forbid")` to all user-facing Settings models.
