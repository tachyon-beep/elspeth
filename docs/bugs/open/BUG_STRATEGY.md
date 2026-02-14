# Bug Fix Strategy

**Created:** 2026-02-14
**Branch:** `RC3.1-bug-hunt`
**Inventory:** 178 open bugs (64 P1, 89 P2, 25 P3), 18 closed

## Principles

1. **Root causes before symptoms.** Fixing a boundary validator eliminates 8 downstream bugs.
2. **Cluster by file, not by folder.** Bugs in the same file should be fixed in one commit.
3. **Silent success is worse than a crash.** Prioritize fail-open bugs over crash bugs.
4. **Parallel agents per cluster.** Independent clusters can be fixed simultaneously.
5. **Each fix includes its regression test.** No fix merges without a test that would have caught it.

## Phase 0: Quick Wins

**Goal:** Clear trivially-fixable P1s that have documented one-liner fixes. Build momentum.
**Effort:** ~1 session. **Bugs closed:** ~12

These are isolated, independent fixes with no design decisions and no risk of regression cascades.

| Bug | File | Fix |
|-----|------|-----|
| Template mutation | `plugins/llm/__init__.py` | `SandboxedEnvironment` → `ImmutableSandboxedEnvironment` |
| GraphValidationError suppressed | `core/dag/graph.py:1088-1092` | Delete the try/except block |
| MCP eager import | `mcp/__init__.py` | Lazy import behind function |
| Journal circuit-breaker dead | `core/landscape/journal.py` | Restructure hook to not short-circuit before recovery check |
| Interrupted run purge | `core/retention/purge.py:145-149` | `status != "running"` → `status.in_(("completed", "failed"))` |
| Resume leaves RUNNING | `engine/orchestrator/core.py` | Add except clause mirroring `run()` |
| Plugin cleanup skipped | `engine/orchestrator/core.py` | Move cleanup outside try block |
| Gate executor open states | `engine/executors/gate.py` | Widen except block to include dispatch errors |
| PoolConfig zero-delay | `plugins/pooling/config.py` | Pydantic validator: `min_delay > 0 or recovery_step > 0` |
| MCP Mermaid non-unique IDs | `mcp/analyzers/reports.py` | Use full node_id or hash-based short IDs |
| Purge unbounded IN | `core/retention/purge.py:352-403` | Apply existing `_METADATA_CHUNK_SIZE` chunking pattern |
| `base_llm` adds_fields | `plugins/llm/base.py` | Set `transforms_adds_fields = True` |

## Phase 1: NaN/Infinity Root Cause

**Goal:** Fix the systemic NaN/Infinity boundary gap. Single root cause, ~8 downstream bugs neutralized.
**Effort:** ~1 session. **Bugs closed:** 5-8 directly + reduces risk on ~4 P2s
**Depends on:** Nothing

### Root cause
Pydantic float validation accepts `float("nan")` and `float("inf")` — these pass schema validation at the source boundary, flow into the pipeline, and crash `canonical_json()` (RFC 8785 rejects them).

### Fix sequence
1. **Boundary fix** — `plugins/schema_factory.py`: Add `math.isfinite()` guard to float validation for explicit schemas
2. **Defense-in-depth** — `plugins/llm/validate_field_type`: Add `math.isfinite()` for NUMBER outputs
3. **LLM response parsing** — `plugins/llm/openrouter_multi_query.py`: Use `parse_constant` kwarg to reject NaN in `json.loads`
4. **LLM response parsing** — `plugins/llm/openrouter.py`: Same pattern for re-parsed responses
5. **Canonical guard** — `core/canonical.py`: `np.datetime64` rejection (related non-standard type issue)

### Downstream bugs neutralized
After the boundary fix, these become defense-in-depth (their risk drops from P1 to "already blocked"):
- `core-rate-limit/P2-nan-timeout`
- `core/P2-sanitize-for-canonical`

## Phase 2: Fail-Open Security

**Goal:** Fix all security transforms that silently report "clean" on malformed/empty input.
**Effort:** ~1 session. **Bugs closed:** 5
**Depends on:** Nothing (independent of Phase 1)

These are the highest-risk bugs in the inventory — they don't crash, they silently succeed, and the audit trail looks correct. An auditor would see "content validated" when nothing was actually checked.

| Bug | File | Pattern |
|-----|------|---------|
| Content severity accepts bool/negative | `plugins/transforms/azure_content_safety.py` | Validate severity is int, 0-7 range |
| Empty documents analysis = clean | `plugins/transforms/azure_content_safety.py` | Reject len(analyses) != len(documents) |
| Prompt shield empty fields = validated | `plugins/transforms/azure_prompt_shield.py` | Reject `fields=[]` at config validation |
| Keyword filter empty fields = no-op | `plugins/transforms/keyword_filter.py` | Reject `fields=[]` at config validation |
| Content safety retry race | `plugins/transforms/azure_content_safety.py` | Capture state_id before try block |

All 5 bugs are in 3 files. One agent can fix all of them in a single pass.

## Phase 3: Silent Data Loss — Field Collisions

**Goal:** Fix all field-overwrite and sentinel-collision bugs.
**Effort:** ~1 session. **Bugs closed:** 6-8
**Depends on:** Nothing

Pattern: A dict comprehension or field assignment silently overwrites when names collide. The audit trail records both fields, but the artifact/output has only one — a divergence that breaks traceability.

| Bug | File | Fix pattern |
|-----|------|-------------|
| FieldMapper target collisions | `plugins/transforms/field_mapper.py` | Validate no duplicate targets at config time |
| GroupBy aggregate overwrite | `plugins/transforms/group_by.py` | Check aggregate field name not in row keys |
| JsonExplode output_field collision | `plugins/transforms/json_explode.py` | Error if output_field already exists in row |
| JsonSink header mapping collision | `plugins/sinks/json_sink.py` | Detect collision in dict comprehension |
| SinkPathConfig header collision | `plugins/config_base.py` | Validate no duplicate values in header_mapping |
| OpenRouter error sentinel | `plugins/llm/openrouter_batch.py` | Use typed discriminated union instead of `"error" in result` |

These are all in separate files. Fully parallelizable.

## Phase 4: Tier 3 Boundary Hardening

**Goal:** Fix external-response handling in LLM and Azure plugins.
**Effort:** ~1 session. **Bugs closed:** 7-9
**Depends on:** Nothing

Pattern: External API responses are used without type/shape validation, violating the Tier 3 trust model.

### LLM plugins (same file cluster)
| Bug | File | Fix |
|-----|------|-----|
| Azure multi-query KeyError | `plugins/llm/azure_multi_query.py` | Wrap template context building in try/except |
| Azure batch non-dict body | `plugins/llm/azure_batch.py` | Validate `isinstance(body, dict)` before `.get()` |
| OpenRouter malformed shapes | `plugins/llm/openrouter_multi_query.py` | Validate content is str, usage is dict |

### Azure plugins
| Bug | File | Fix |
|-----|------|-----|
| Blob source type(e) rewrap | `plugins/azure/blob_source.py` | Use `RuntimeError(str(e)) from e` instead of `type(e)(...)` |
| JSONL decode ValueError | `plugins/azure/blob_source.py` | Catch ValueError, quarantine row |

### Audit gap
| Bug | File | Fix |
|-----|------|-----|
| Chat completion broad catch | `plugins/clients/chat_completion.py` | Narrow try block to SDK call only |
| Redirect hop not recorded | `plugins/clients/http.py` | Record HTTP_REDIRECT before attempting hop |

## Phase 5: Engine Correctness

**Goal:** Fix fork/coalesce routing and node-state terminality.
**Effort:** ~1 session. **Bugs closed:** 5-6
**Depends on:** Nothing, but test carefully (engine is the riskiest subsystem)

These bugs affect the DAG execution model and are interconnected. Fix them together and run the full integration + E2E suite after.

| Bug | File | Issue |
|-----|------|-------|
| Fork-to-sink skips coalesce notify | `engine/processor.py` | Call `_notify_coalesce_of_lost_branch()` on gate sink routing |
| DAGNavigator misroutes continuations | `engine/dag_navigator.py` | Fix `create_continuation_work_item` to not jump backward |
| AggregationExecutor non-terminal | `engine/executors/aggregation.py` | Widen try/except to include post-process hash |
| TransformExecutor terminality | `engine/executors/transform.py` | Same pattern as aggregation |
| Reconstruct Optional[Decimal] | `engine/orchestrator/export.py` | Handle 3-branch anyOf in `_json_schema_to_python_type` |

## Phase 6: Contracts Hardening

**Goal:** Fix the 10 P1s in the contracts subsystem.
**Effort:** ~1 session. **Bugs closed:** 10
**Depends on:** Nothing

All in `src/elspeth/contracts/`. Parallelizable per-file.

| Bug | File | Pattern |
|-----|------|---------|
| check_compatibility rejects float→Optional[float] | `schema_contract.py` | Fix compatibility check to handle nullable numeric widening |
| ContractAuditRecord invalid enum | `audit.py` | Validate contract value against known enum members |
| ContractBuilder crashes on dict/list | `builder.py` | Handle nested JSON in first-row processing |
| create_contract_from_config inconsistent | `factory.py` | Reject FIXED mode with unlocked flag |
| PipelineRow coerces non-dict | `pipeline_row.py` | Crash on non-dict input (Tier 1) |
| propagate/narrow drops fields on TypeError | `schema_contract.py` | Re-raise TypeError instead of silently dropping |
| SchemaConfig coerces non-bool required | `schema.py` | Use `type(v) is bool` instead of `bool(v)` |
| TransformResult error invariants | `results.py` | Validate error+success_reason mutual exclusion |
| TypeMismatchViolation serializes raw | `violations.py` | Sanitize offending values before serialization |
| update_checkpoint stale path | `checkpoint.py` | Actually update the active checkpoint path |

## Phase 7: Core Infrastructure

**Goal:** Fix remaining core P1s.
**Effort:** ~1 session. **Bugs closed:** 6-8
**Depends on:** Phase 1 (NaN fix) should land first to simplify canonical.py work

| Bug | File | Fix |
|-----|------|-----|
| Checkpoint datetime collision | `core/checkpoint/serialization.py` | Collision-safe envelope with escaping |
| Config drops unknown keys | `core/config.py` | Replace allowlist with Dynaconf blocklist |
| Landscape exporter missing table | `core/landscape/exporter.py` | Add `token_outcomes` to `_iter_records` |
| Run contract ignores hash column | `core/landscape/_run_recording.py` | Cross-check `schema_contract_hash` DB column |
| Record transform error crashes | `core/landscape/_error_recording.py` | Apply `repr_hash` fallback pattern from sibling method |
| web.py DNS timeout | `core/security/web.py` | `shutdown(wait=False, cancel_futures=True)` |
| web.py port parsing | `core/security/web.py` | try/except + `is not None` + port 0 rejection |
| PayloadStore race | `core/payload_store.py` | Atomic write with temp file + rename |
| Lowercase schema keys | `core/config.py` | Don't lowercase coalesce branch keys |

## Phase 8: P2 Sweeps

**Goal:** Systematically clear P2 bugs using thematic sweeps.
**Effort:** 2-3 sessions. **Bugs closed:** ~50
**Depends on:** Phases 0-7 (P1s should be clear first)

### Sweep A: Truthiness → `is not None` (~12 bugs)
Pattern: `if x:` where `x` can be `0`, `0.0`, `""`, or `False` and those are valid values.
Single `grep` + systematic replacement across all flagged locations.

### Sweep B: Resume/Run Parity (~4 bugs)
Extract shared finalization path from `run()` and `resume()` in orchestrator/core.py.
One refactoring commit that closes multiple bugs.

### Sweep C: Export Determinism (~3 bugs)
Add `ORDER BY` to `get_artifacts`, `get_nodes`, and fix CSV flatten collision.
Same signing pipeline, fix together.

### Sweep D: Validation Guards (~15 bugs)
Config validation gaps across plugins: empty lists, impossible enum combinations, type coercion.
Embarrassingly parallel — each is one Pydantic validator or `__post_init__` check.

### Sweep E: Remaining Audit/Telemetry (~8 bugs)
Mutable dict snapshots, wrong token_id in telemetry, missing DDL instrumentation.
Independent per-file fixes.

### Sweep F: Tier 1 Defense-in-Depth (~8 bugs)
Landscape hardening: complete-batch/run status validation, schema cross-run FK, etc.
Low urgency but clean fixes.

## Phase 9: P3 Backlog

**Goal:** Clear remaining P3 items as convenient.
**Effort:** As available. **Bugs closed:** ~25
**Depends on:** Nothing blocking

These are all real bugs with no practical impact today. Fix when touching adjacent code,
or batch into a single cleanup session. Not worth dedicated scheduling.

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

### Parallelism map

```
Phase 0 (quick wins)          ─── can start immediately
Phase 1 (NaN root cause)      ─── can start immediately
Phase 2 (fail-open security)  ─── can start immediately
Phase 3 (field collisions)    ─── can start immediately
Phase 4 (Tier 3 boundaries)   ─── can start immediately
Phase 5 (engine correctness)  ─── can start immediately (but test carefully)
Phase 6 (contracts)           ─── can start immediately
Phase 7 (core infrastructure) ─── after Phase 1 (NaN fix simplifies canonical.py work)
Phase 8 (P2 sweeps)           ─── after Phases 0-7
Phase 9 (P3 backlog)          ─── whenever convenient
```

Phases 0-6 are fully independent and can run in parallel across sessions.
Phase 7 has a soft dependency on Phase 1.
Phases 8-9 are mop-up.

## Metrics

After each phase, update the counts:

| Phase | Target | P1 closed | P2 closed | P3 closed |
|-------|--------|-----------|-----------|-----------|
| 0 | Quick wins | ~12 | — | — |
| 1 | NaN root cause | 5 | 2 | — |
| 2 | Fail-open security | 5 | — | — |
| 3 | Field collisions | 6 | — | — |
| 4 | Tier 3 boundaries | 7 | — | — |
| 5 | Engine correctness | 5 | — | — |
| 6 | Contracts | 10 | — | — |
| 7 | Core infrastructure | 8 | — | — |
| 8 | P2 sweeps | — | ~50 | — |
| 9 | P3 backlog | — | — | ~25 |
| **Total** | | **~58** | **~52** | **~25** |

Remaining ~43 P2s from Phases 0-7 are absorbed into Phase 8 sweeps or closed as
side effects of P1 fixes in the same file.
