# Bug Fix Strategy

**Created:** 2026-02-14
**Updated:** 2026-02-17
**Branch:** `RC3.1-bug-hunt`
**Original inventory:** 178 open bugs (64 P1, 89 P2, 25 P3), 18 closed
**Current:** 77 open (33 P1, 39 P2, 5 P3), 118 closed — **60% resolved**

## Principles

1. **Root causes before symptoms.** Fixing a boundary validator eliminates 8 downstream bugs.
2. **Cluster by file, not by folder.** Bugs in the same file should be fixed in one commit.
3. **Silent success is worse than a crash.** Prioritize fail-open bugs over crash bugs.
4. **Parallel agents per cluster.** Independent clusters can be fixed simultaneously.
5. **Each fix includes its regression test.** No fix merges without a test that would have caught it.

## Phase 0: Quick Wins — COMPLETE

**Commit:** `c4ce8cda`
**Bugs closed:** 12 P1

| Bug | File | Status |
|-----|------|--------|
| Template mutation | `plugins/llm/__init__.py` | CLOSED |
| GraphValidationError suppressed | `core/dag/graph.py` | CLOSED |
| MCP eager import | `mcp/__init__.py` | CLOSED |
| Journal circuit-breaker dead | `core/landscape/journal.py` | CLOSED |
| Interrupted run purge | `core/retention/purge.py` | CLOSED |
| Resume leaves RUNNING | `engine/orchestrator/core.py` | CLOSED |
| Plugin cleanup skipped | `engine/orchestrator/core.py` | CLOSED |
| Gate executor open states | `engine/executors/gate.py` | CLOSED |
| PoolConfig zero-delay | `plugins/pooling/config.py` | CLOSED |
| MCP Mermaid non-unique IDs | `mcp/analyzers/reports.py` | CLOSED |
| Purge unbounded IN | `core/retention/purge.py` | CLOSED |
| `base_llm` adds_fields | `plugins/llm/base.py` | CLOSED |

## Phase 1: NaN/Infinity Root Cause — COMPLETE

**Commit:** `6ea152e8`
**Bugs closed:** 5 P1 + 1 P2

All NaN/Infinity boundary fixes landed. The `np.datetime64` canonical hashing issue (originally listed here) is the sole remaining item — see Remaining Work below.

### Fix sequence (all delivered)
1. Boundary fix — `plugins/schema_factory.py`: `math.isfinite()` guard on float validation
2. Defense-in-depth — `plugins/llm/validate_field_type`: `math.isfinite()` for NUMBER outputs
3. LLM response parsing — `plugins/llm/openrouter_multi_query.py`: `parse_constant` kwarg
4. LLM response parsing — `plugins/llm/openrouter.py`: Same pattern
5. Canonical guard — `core/canonical.py`: non-standard type rejection

### Downstream bugs neutralized
- `core-rate-limit/P2-nan-timeout` — CLOSED
- `core/P2-sanitize-for-canonical` — CLOSED

## Phase 2: Fail-Open Security — COMPLETE

**Commit:** `6ef7b55e`
**Bugs closed:** 5 P1 + 1 P2

| Bug | File | Status |
|-----|------|--------|
| Content severity accepts bool/negative | `plugins/transforms/azure/content_safety.py` | CLOSED |
| Empty documents analysis = clean | `plugins/transforms/azure/content_safety.py` | CLOSED |
| Prompt shield empty fields = validated | `plugins/transforms/azure/prompt_shield.py` | CLOSED |
| Keyword filter empty fields = no-op | `plugins/transforms/keyword_filter.py` | CLOSED |
| Content safety retry race | `plugins/transforms/azure/content_safety.py` | CLOSED |

## Phase 3: Silent Data Loss — Field Collisions — COMPLETE

**Commits:** `abc6aace` through `dec2b95a`, `9542218f`, `d2932c84`
**Bugs closed:** 7

Implemented centralized `detect_field_collisions()` utility and deployed it across all transforms. Also centralized collision detection in `TransformExecutor` as defense-in-depth.

| Bug | File | Status |
|-----|------|--------|
| GroupBy aggregate overwrite | `plugins/transforms/group_by.py` | CLOSED |
| JsonExplode output_field collision | `plugins/transforms/json_explode.py` | CLOSED |
| JsonSink header mapping collision | `plugins/sinks/json_sink.py` | CLOSED |
| SinkPathConfig header collision | `plugins/config_base.py` | CLOSED |
| OpenRouter error sentinel | `plugins/llm/openrouter_batch.py` | CLOSED |
| LLM/multi-query/batch collisions | Multiple LLM files | CLOSED |
| TransformExecutor centralized guard | `engine/executors/transform.py` | CLOSED |

**Still open:** FieldMapper target collisions (`plugins/transforms/field_mapper.py`) — see Remaining Work.

## Phase 4: Tier 3 Boundary Hardening — COMPLETE

**Commit:** `eb0e8ba7`
**Bugs closed:** 10 P1

| Bug | File | Status |
|-----|------|--------|
| Azure multi-query KeyError | `plugins/llm/azure_multi_query.py` | CLOSED |
| Azure batch non-dict body | `plugins/llm/azure_batch.py` | CLOSED |
| OpenRouter malformed shapes | `plugins/llm/openrouter_multi_query.py` | CLOSED |
| Blob source type(e) rewrap | `plugins/azure/blob_source.py` | CLOSED |
| JSONL decode ValueError | `plugins/azure/blob_source.py` | CLOSED |
| Chat completion broad catch | `plugins/clients/chat_completion.py` | CLOSED |
| Redirect hop not recorded | `plugins/clients/http.py` | CLOSED |

## Phase 5: Engine Correctness — COMPLETE

**Commits:** `5557573b`, `c624e546`, `7fa16b4c`, `3947f7c7`
**Bugs closed:** 12 P1 (exceeded target of 5-6)

| Bug | File | Status |
|-----|------|--------|
| Fork-to-sink skips coalesce notify | `engine/processor.py` | CLOSED |
| DAGNavigator misroutes continuations | `engine/dag_navigator.py` | CLOSED |
| AggregationExecutor non-terminal | `engine/executors/aggregation.py` | CLOSED |
| TransformExecutor terminality | `engine/executors/transform.py` | CLOSED |
| Reconstruct Optional[Decimal] | `engine/orchestrator/export.py` | CLOSED |
| Batch adapter crash-on-None | `engine/batch_adapter.py` | CLOSED |
| + 6 additional engine bugs found during fixing | Various | CLOSED |

## Phase 6: Contracts Hardening — COMPLETE

**Commit:** `bf5dc956`
**Bugs closed:** 10 P1

| Bug | File | Status |
|-----|------|--------|
| check_compatibility nullable widening | `schema_contract.py` | CLOSED |
| ContractAuditRecord invalid enum | `audit.py` | CLOSED |
| ContractBuilder crashes on dict/list | `builder.py` | CLOSED |
| create_contract_from_config inconsistent | `factory.py` | CLOSED |
| PipelineRow coerces non-dict | `pipeline_row.py` | CLOSED |
| propagate/narrow drops fields on TypeError | `schema_contract.py` | CLOSED |
| SchemaConfig coerces non-bool required | `schema.py` | CLOSED |
| TransformResult error invariants | `results.py` | CLOSED |
| TypeMismatchViolation serializes raw | `violations.py` | CLOSED |
| update_checkpoint stale path | `checkpoint.py` | CLOSED |

## Phase 7: Core Infrastructure — COMPLETE

**Commit:** `d7f9fd40`
**Bugs closed:** 8

| Bug | File | Status |
|-----|------|--------|
| Checkpoint datetime collision | `core/checkpoint/serialization.py` | CLOSED |
| Config drops unknown keys | `core/config.py` | CLOSED |
| Landscape exporter missing table | `core/landscape/exporter.py` | CLOSED |
| Run contract ignores hash column | `core/landscape/_run_recording.py` | CLOSED |
| Record transform error crashes | `core/landscape/_error_recording.py` | CLOSED |
| web.py DNS timeout | `core/security/web.py` | CLOSED |
| web.py port parsing | `core/security/web.py` | CLOSED |
| PayloadStore race | `core/payload_store.py` | CLOSED |
| Lowercase schema keys | `core/config.py` | CLOSED |

## Phase 8: P2 Sweeps — PARTIAL

**Sweep A:** Truthiness → `is not None` — COMPLETE (`a6df77a9`, 4 locations)
**Sweep D:** Validation guards — COMPLETE (`96e34280`, 11 boundaries)
**Sweeps B, C, E, F:** Not yet started

Additional hardening commits outside the sweep structure:
- `f0a897b4`: 11 core-landscape Tier 1 strictness fixes
- `49336165`: 6-step plugin/executor enforcement centralization
- `6eece8b5`: Telemetry test repair (on_error=None, missing protocol attrs)
- `76c3894f`: Nullable field contract audit round-trip
- `5f7b939d`: Unsupported types, nullable unions, SchemaConfig validation
- `2f4d89de`: Deterministic ordering, type validation, orphan prevention
- `16b57e94`: Terminal status invariants in landscape completion

## Phase 9: P3 Backlog — MOSTLY COMPLETE

20 of 25 original P3s closed (absorbed as side effects of P1/P2 fixes).
5 remaining — see Remaining Work.

## Emergent Bugs

Bugs discovered during execution that were NOT in the original 178-bug inventory:

| Commit | Bug | How found |
|--------|-----|-----------|
| `a15e1c24` | AzurePromptShield missing `super().on_start()` — lifecycle guard regression | Code review |
| `ae38a115` | BatchReplicate `max_copies` not enforced on `default_copies` fallback | Code review |
| `e7708954` | DNS resolver thread leak on validation timeout | Code review |
| `e7708954` | Config validation regression from Phase 7 changes | Code review |
| `e2a23cee` | state_id=None errors hang batch waiters instead of propagating | Phase 5 debugging |
| `ea5445fc` | Pending batch state lost on post-submission failure | Phase 5 debugging |
| `2b3dd92a` | Unbounded IN clause in checkpoint recovery buffered-token filter | Phase 5 debugging |
| `d2932c84` | Field collision detection missing from TransformExecutor (defense-in-depth) | Phase 3 design |
| `f207964a` | Env var config regression, resume DB validation gap | Integration testing |
| `6eece8b5` | Pre-existing telemetry test failures (on_error=None) | Test suite repair |
| `76c3894f` | Nullable field lost through contract audit round-trip | Phase 6 follow-up |

**Lesson:** ~15% of fixes came from bugs discovered during execution, not from the original inventory. Bug-hunting generates bugs.

## Remaining Work — 77 Open Bugs

### P1 (33 remaining) — by subsystem

**Plugins — LLM (6):**
- `base-llm-transform-output-schema-diverges-from-output-schema-config-guaranteed-fields`
- `multi-query-cross-product-output-prefix-collisions-from-delimiter-ambiguity`
- `openrouter-batch-http-clients-cached-by-state-id-never-evicted-per-batch`
- `terminal-batch-failures-clear-checkpoint-without-per-row-llm-call-recording`
- `azure-process-row-uses-mutable-ctx-state-id-in-cleanup-wrong-cache-eviction`
- `np-datetime64-values-can-pass-schema-validation-but-crash-canonical-hashing`

**Plugins — Sinks (4):**
- `azure-blob-sink-misses-required-field-validation`
- `csvsink-write-can-partially-write-a-batch-before-raising-causing-sink-output-to`
- `databasesink-silently-accepts-schema-invalid-rows-by-default-validate-input-fal`
- `jsonsink-in-mode-append-can-append-to-an-existing-jsonl-file-without-validating`

**Plugins — Transforms (3):**
- `fieldmapper-allows-target-name-collisions-that-silently-overwrite-fields-and-co`
- `jsonexplode-infers-output-field-type-from-only-the-first-exploded-row-so-hetero`
- `batchreplicate-accepts-bool-in-copies-field-as-a-valid-integer-copy-count-silen`

**Plugins — Other (4):**
- `callreplayer-replay-fabricates-empty-response-for-error-calls-missing-hash`
- `pluginmanager-register-leaves-pluggy-polluted-on-duplicate-name`
- `pooledexecutor-shutdown-race-leaves-reserved-buffer-slots-stranded`
- `shutdown-batch-processing-can-silently-drop-in-flight-rows`

**Plugins — Sources (2):**
- `jsonsource-crashes-on-invalid-byte-sequences-in-json-array-mode-instead-of-quar`
- `skip-rows-can-silently-drop-all-remaining-csv-data-without-any-quarantine-audi`

**Engine (4):**
- `check-aggregation-timeouts-flushes-batches-but-never-triggers-checkpoint-callba`
- `coalesce-timeout-flush-silently-ignores-invalid-coalesceoutcome-states`
- `release-loop-can-fail-to-propagate-real-error-with-stale-token-state-id`
- `build-execution-graph-shares-mutable-schema-dicts-across-nodes`

**Core/Landscape (4):**
- `record-transform-error-can-write-under-a-run-id-that-does-not-own-the-token-id`
- `schema-allows-cross-run-contamination-for-token-linked-audit-records`
- `schema-type-any-is-mapped-to-sql-text-without-serialization-so-valid-any-values`
- `token-lifecycle-methods-accept-caller-supplied-run-id-row-id-without-validating`

**MCP (3):**
- `call-tool-returns-success-for-invalid-args-or-unknown-tools`
- `get-outcome-analysis-returns-is-terminal-as-db-integer-instead-of-bool`
- `get-performance-report-truncates-node-id-into-a-non-canonical-display`

**Other (3):**
- `console-run-summary-formatter-crashes-on-legitimate`
- `explain-field-can-return-the-wrong-field-when-lookup-key-matches`
- `enable-content-recording-accepted-logged-but-never-applied-in-azure-monitor-setup`

### P2 (39 remaining) — by theme

**Contracts/Schema (10):** Schema validation, type misclassification, immutability violations
**MCP/Analyzers (5):** Query ordering, null handling, tool schema gaps
**Security (3):** SSRF redirect bypass, secret validation, webhook fingerprints
**Engine (4):** Mutable flush results, branch-lost dedup, executor ctx gaps
**Telemetry/Audit (5):** Mutable payloads, wrong token_id, missing instrumentation
**Config/Checkpoint (3):** Stale examples, error wrapping, secret race
**Plugins (9):** Response truncation, verifier false positives, Unicode, type normalization

### P3 (5 remaining)

- `eventbus-emit-iterates-live-subscriber-list`
- `resolve-database-url-rejects-valid-prefixed-settings-path`
- `skip-rows-accepts-negative-values`
- `tokeninfos-pipelinerow-annotations-not-runtime-resolvable`
- `validate-field-names-attributeerror-for-non-string-entries`

## Execution Model

### Session structure
Each phase should be executed as a single session with parallel subagents:
- **Read** the bug files and source code
- **Fix** the bugs (one commit per cluster, not per bug)
- **Test** with `pytest` after each cluster
- **Close** the bug files (move to `docs/bugs/closed/`)

### Commit granularity
- One commit per phase or per cluster within a phase
- Commit message references all bug files closed
- Run full test suite before each commit

### Risk ordering within each phase
1. Fix the bug
2. Write the regression test
3. Run the targeted test file
4. Run the full suite
5. Move bug file to closed

## Metrics

| Phase | Target | Status | P1 closed | P2 closed | P3 closed |
|-------|--------|--------|-----------|-----------|-----------|
| 0 | Quick wins | COMPLETE | 12 | — | — |
| 1 | NaN root cause | COMPLETE | 5 | 1 | — |
| 2 | Fail-open security | COMPLETE | 5 | 1 | — |
| 3 | Field collisions | COMPLETE | 6 | 1 | — |
| 4 | Tier 3 boundaries | COMPLETE | 10 | — | — |
| 5 | Engine correctness | COMPLETE | 12 | — | — |
| 6 | Contracts | COMPLETE | 10 | — | — |
| 7 | Core infrastructure | COMPLETE | 8 | 1 | — |
| 8 | P2 sweeps | PARTIAL | — | 15 | — |
| 9 | P3 backlog | MOSTLY DONE | — | — | 20 |
| Emergent | Found during fixing | ONGOING | ~5 | ~5 | — |
| Cross-phase | Landscape/telemetry | DONE | 15 | — | — |
| **Actual total** | | | **~88** | **~24** | **~20** |
| **Remaining** | | | **33** | **39** | **5** |
