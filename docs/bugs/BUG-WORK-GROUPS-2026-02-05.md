# Bug Work Groups - 2026-02-05

This document organizes the 140 validated bugs into strategic work groups for parallel assignment to agents or humans. Groups are designed to:
- Minimize context switching (related bugs together)
- Enable parallel work (independent subsystems)
- Group by common root cause (apply same fix pattern)

**Total: 51 P1, 76 P2, 13 P3 = 140 bugs**

---

## Group 1: Tier-1 Audit Trail Integrity (HIGHEST PRIORITY)

**Focus:** Core-landscape repository code violating "crash on corruption" principle
**Priority:** 10 P1 bugs
**Owner:** Core systems engineer
**Estimated effort:** 2-3 days

### Root Cause
Repository code uses defensive patterns (`.get()`, coercion, silent defaults) on Tier-1 audit data instead of crashing on anomalies.

### Bugs
1. `core-landscape/P1-2026-02-05-compute-grade-accepts-invalid-determinism-val.md`
2. `core-landscape/P1-2026-02-05-databaseops-write-helpers-ignore-affected-row.md`
3. `core-landscape/P1-2026-02-05-explain-allows-missing-parent-relationships.md`
4. `core-landscape/P1-2026-02-05-filesystempayloadstore-store-skips-integrity.md`
5. `core-landscape/P1-2026-02-05-io-read-io-write-nodes-misclassified-as-full.md`
6. `core-landscape/P1-2026-02-05-nodestaterepository-allows-invalid-open-pendi.md`
7. `core-landscape/P1-2026-02-05-operation-status-recorded-as-completed-on-bas.md`
8. `core-landscape/P1-2026-02-05-routing-reason-payloads-are-never-persisted.md`
9. `core-landscape/P1-2026-02-05-sqlite-schema-validation-misses-newly-added-a.md`
10. `core-landscape/P1-2026-02-05-audit-export-drops-nodestate-context-error-an.md`

### Fix Pattern
- Remove `.get()` calls on audit database reads
- Replace `or default` with strict checks
- Add type assertions before processing
- Let exceptions propagate (Tier-1 crash-on-corruption)

### Testing Strategy
- Add property tests that inject corrupted audit data
- Verify crashes occur (not silent recovery)
- Test via `tests/core/landscape/`

---

## Group 2: PipelineRow Migration Completion (HIGH PRIORITY)

**Focus:** Transforms/LLMs not fully migrated to PipelineRow dual-name access
**Priority:** 6 P1 + 3 P2 = 9 bugs
**Owner:** Plugin engineer
**Estimated effort:** 2 days

### Root Cause
PipelineRow has `original_name` + `normalized_name` fields, but some plugins still assume single-name access.

### P1 Bugs
1. `plugins-transforms/P1-2026-02-05-fieldmapper-renames-drop-original-field-names.md`
2. `plugins-transforms/P1-2026-02-05-keywordfilter-ignores-pipelinerow-dual-name-r.md`
3. `plugins-llm/P1-2026-02-05-azure-multi-query-drops-pipelinerow-dual-name.md`
4. `plugins-transforms/P1-2026-02-05-get-nested-field-hides-type-mismatches-as-mi.md`
5. `plugins-azure/P1-2026-02-05-csv-malformed-lines-are-silently-dropped-due.md`
6. `plugins-sources/P1-2026-02-05-duplicate-raw-headers-are-not-detected-when.md`

### P2 Bugs
7. `plugins-llm/P2-2026-02-05-azure-llm-template-rendering-ignores-pipeline.md`
8. `plugins-llm/P2-2026-02-05-openrouter-llm-template-rendering-ignores-sch.md`
9. `contracts/P2-2026-02-05-pipelinerow-contains-misreports-extras.md`

### Fix Pattern
- Use `row.get_field(name)` for dual-name resolution
- Update template rendering to handle both names
- Check `PipelineRow.contains()` instead of `dict` membership
- Review all `row["field"]` access in transforms

### Testing Strategy
- Add tests with field renames via normalization
- Verify original names preserved
- Test via `tests/plugins/transforms/`, `tests/plugins/llm/`

---

## Group 3: Contract Propagation Gaps (HIGH PRIORITY)

**Focus:** Transform executors not preserving input contracts properly
**Priority:** 2 P1 + 5 P2 = 7 bugs
**Owner:** Engine engineer
**Estimated effort:** 1-2 days

### Root Cause
Transform executors create new contracts instead of propagating input contracts with modifications.

### P1 Bugs
1. `engine-executors/P1-2026-02-05-transformexecutor-drops-input-contract-when-t.md`
2. `core-dag/P1-2026-02-05-pass-through-nodes-drop-computed-schema-contr.md`

### P2 Bugs
3. `engine-executors/P2-2026-02-05-sinkexecutor-leaves-ctx-contract-stale-for-si.md`
4. `contracts/P2-2026-02-05-contract-propagation-drops-complex-type-outpu.md`
5. `contracts/P2-2026-02-05-resolve-headers-masks-contract-corruption-in.md`
6. `plugins-transforms/P2-2026-02-05-jsonexplode-drops-output-field-from-contrac.md`
7. `plugins-transforms/P2-2026-02-05-batch-aware-transform-contract-mismatch-base.md`

### Fix Pattern
- Use `contract.merge()` instead of creating new contract
- Preserve input contract metadata in transform output
- Update `ctx.contract` after transform completes
- Reference migration plan at `executors.py:771`

### Testing Strategy
- Test contract preservation through transform chains
- Verify metadata (guaranteed fields, computed fields) survives
- Test via `tests/engine/test_executors.py`, `tests/contracts/`

---

## Group 4: External Call Secret Leakage (HIGH PRIORITY - SECURITY)

**Focus:** HTTP clients recording raw URLs with secrets in audit trail
**Priority:** 2 P1 + 1 P2 = 3 bugs
**Owner:** Security/plugins engineer
**Estimated effort:** 1 day

### Root Cause
`AuditedHTTPClient` records full URL before sanitization; fragments bypass sanitizer.

### Bugs
1. `contracts/P1-2026-02-05-sanitizedwebhookurl-leaves-fragment-tokens-un.md`
2. `core-security/P1-2026-02-05-key-vault-secrets-load-without-fingerprint-ke.md`
3. `plugins-llm/P1-2026-02-05-non-finite-json-values-in-http-responses-brea.md`

### Fix Pattern
- Sanitize URLs *before* audit recording
- Strip fragments from `SanitizedWebhookUrl`
- Require `ELSPETH_FINGERPRINT_KEY` for Key Vault loads
- Record HMAC fingerprints, never raw secrets

### Testing Strategy
- Test URLs with query params, fragments
- Verify audit trail contains sanitized versions only
- Test via `tests/core/security/`, `tests/plugins/llm/`

---

## Group 5: Resume/Checkpoint Integrity (HIGH PRIORITY)

**Focus:** Resume path has multiple data integrity issues
**Priority:** 5 P1 + 2 P2 = 7 bugs
**Owner:** Core recovery engineer
**Estimated effort:** 2 days

### Root Cause
Resume path: (1) missing validation, (2) reprocesses buffered rows, (3) can't serialize aggregation state, (4) infers missing contracts.

### P1 Bugs
1. `core-checkpoint/P1-2026-02-05-checkpointmanager-cannot-serialize-aggregatio.md`
2. `core-checkpoint/P1-2026-02-05-resume-reprocesses-buffered-rows-already-capt.md`
3. `engine-orchestrator/P1-2026-02-05-resume-fails-for-observed-schemas-due-to-empt.md`
4. `engine-orchestrator/P1-2026-02-05-resume-silently-infers-missing-run-contract.md`
5. `core-config/P1-2026-02-05-gate-route-labels-are-lowercased-during-confi.md`

### P2 Bugs
6. `contracts/P2-2026-02-05-resumepoint-allows-non-dict-aggregation-state.md`
7. `plugins-sources/P2-2026-02-05-nullsourceschema-treated-as-explicit-schema.md`

### Fix Pattern
- Validate all resume state fields (fail fast on corruption)
- Track which buffered rows already have states
- Make aggregation state JSON-serializable
- Crash if run contract missing (don't infer)

### Testing Strategy
- Test resume after aggregation triggers
- Test resume with various source schemas
- Test via `tests/core/checkpoint/`, `tests/engine/test_orchestrator_recovery.py`

---

## Group 6: Validation Boundary Enforcement (MEDIUM PRIORITY)

**Focus:** Contract/enum validators missing type checks
**Priority:** 5 P1 + 8 P2 = 13 bugs
**Owner:** Contracts engineer
**Estimated effort:** 1-2 days

### Root Cause
Validators check invariants but not types; accept non-enum strings, non-dict objects.

### P1 Bugs
1. `contracts/P1-2026-02-05-batch-trigger-type-bypasses-triggertype-e.md`
2. `contracts/P1-2026-02-05-flexible-contracts-are-locked-at-creation-bl.md`
3. `contracts/P1-2026-02-05-missing-value-sentinels-pd-na-np-datetime64.md`
4. `contracts/P1-2026-02-05-routingaction-accepts-non-enum-mode-causin.md`
5. `engine-triggers/P1-2026-02-05-condition-trigger-not-latched-once-fired.md`

### P2 Bugs (selected)
6. `contracts/P2-2026-02-05-observed-schema-silently-accepts-non-list-fi.md`
7. `contracts/P2-2026-02-05-operation-status-type-not-validated-in-audit.md`
8. `contracts/P2-2026-02-05-optional-float-fields-lose-type-enforcement-i.md`
9. `contracts/P2-2026-02-05-retry-policy-accepts-non-finite-floats-enabl.md`
10. `core-config/P2-2026-02-05-trigger-condition-validation-allows-unsupport.md`

### Fix Pattern
- Add `isinstance()` checks before invariant validation
- Reject non-enum types at construction
- Validate NaN/Infinity forbidden in canonicalization
- Make sentinel detection exhaustive (pd.NA, np.datetime64('NaT'))

### Testing Strategy
- Property tests with wrong types
- Test via `tests/contracts/`

---

## Group 7: Azure Plugin Error Handling (MEDIUM PRIORITY)

**Focus:** Azure sources/sinks crash instead of quarantine, skip audit calls
**Priority:** 3 P1 + 3 P2 = 6 bugs
**Owner:** Azure plugin maintainer
**Estimated effort:** 1 day

### Root Cause
Azure plugins don't follow standard error patterns: crash instead of quarantine, skip audit recording.

### P1 Bugs
1. `plugins-azure/P1-2026-02-05-azureblobsink-overwrites-prior-batches-on-rep.md`
2. `plugins-azure/P1-2026-02-05-json-array-parse-structure-errors-crash-inste.md`
3. `plugins-sinks/P1-2026-02-05-json-array-mode-silently-ignores-mode-append.md`

### P2 Bugs
4. `plugins-azure/P2-2026-02-05-azureblobsink-skips-audit-call-when-overwrite.md`
5. `plugins-azure/P2-2026-02-05-json-jsonl-accepts-nan-infinity-violating-ca.md`
6. `plugins-azure/P2-2026-02-05-partial-service-principal-fields-are-ignored.md`

### Fix Pattern
- Wrap JSON parsing in try/except → quarantine
- Record all blob operations via `AuditedAzureClient`
- Reject NaN/Infinity at boundary
- Validate all required auth fields present

### Testing Strategy
- Test malformed JSON, auth failures
- Verify audit calls recorded
- Test via `tests/plugins/azure/`

---

## Group 8: LLM Transform Audit Completeness (MEDIUM PRIORITY)

**Focus:** LLM transforms missing call recording, hash verification
**Priority:** 2 P1 + 9 P2 = 11 bugs
**Owner:** LLM plugin engineer
**Estimated effort:** 2 days

### Root Cause
LLM transforms: (1) skip hash verification when payload present, (2) missing audit calls, (3) silent failures.

### P1 Bugs
1. `plugins-llm/P1-2026-02-05-callverifier-skips-hash-verification-when-pay.md`
2. `plugins-llm/P1-2026-02-05-openrouter-multi-query-allows-output-key-coll.md`

### P2 Bugs (selected)
3. `plugins-llm/P2-2026-02-05-basellmtransform-output-contract-omits-usag.md`
4. `plugins-llm/P2-2026-02-05-duplicate-output-mapping-suffixes-silently.md`
5. `plugins-llm/P2-2026-02-05-llm-transforms-can-return-errors-without-mand.md`
6. `plugins-llm/P2-2026-02-05-lookup-data-mutability-produces-stale-lookup.md`
7. `plugins-llm/P2-2026-02-05-openrouter-batch-drops-api-v1-from-base-ur.md`
8. `plugins-llm/P2-2026-02-05-unknown-tracing-provider-is-silently-accepted.md`

### Fix Pattern
- Always verify hash (even when payload present)
- Record all LLM calls via `AuditedLLMClient`
- Include usage tokens in output contract
- Detect output key collisions at config time

### Testing Strategy
- Test with/without replay mode
- Verify all calls have audit records
- Test via `tests/plugins/llm/`

---

## Group 9: Transform Config Validation (MEDIUM PRIORITY)

**Focus:** Transforms silently drop config, accept malformed options
**Priority:** 1 P1 + 6 P2 = 7 bugs
**Owner:** Transform plugin engineer
**Estimated effort:** 1 day

### Root Cause
Transform config validation happens at execution time, not pipeline construction.

### P1 Bugs
1. `plugins-transforms/P1-2026-02-05-batchstats-silently-drops-configured-group-b.md`

### P2 Bugs
2. `plugins-transforms/P2-2026-02-05-batchstats-emits-mean-for-empty-batches-eve.md`
3. `plugins-transforms/P2-2026-02-05-configured-fields-are-silently-skipped-when-m.md`
4. `plugins-transforms/P2-2026-02-05-discovery-silently-skips-plugins-missing-nam.md`
5. `plugins-transforms/P2-2026-02-05-fieldmapper-strict-mode-can-emit-errors-witho.md`
6. `plugins-transforms/P2-2026-02-05-pluginconfigvalidator-rejects-openrouter-batc.md`
7. `plugins-transforms/P2-2026-02-05-schema-config-errors-escape-validator-as-exce.md`

### Fix Pattern
- Validate all transform configs at pipeline construction
- Fail fast before execution starts
- Standardize config validation across all transforms
- Add to preflight validation path

### Testing Strategy
- Test invalid configs block run start
- Test via `tests/plugins/transforms/`

---

## Group 10: Sink Data Integrity (MEDIUM PRIORITY)

**Focus:** Sinks write blank values, fail after validation
**Priority:** 3 P1 + 0 P2 = 3 bugs
**Owner:** Sink plugin engineer
**Estimated effort:** 0.5 day

### Root Cause
Sinks: (1) CSV writes blanks when required fields missing, (2) DatabaseSink fails after validation target set.

### P1 Bugs
1. `plugins-sinks/P1-2026-02-05-csvsink-silently-writes-blank-values-when-req.md`
2. `plugins-sinks/P1-2026-02-05-databasesink-fails-after-validate-output-tar.md`
3. `plugins-sinks/P1-2026-02-05-json-array-mode-silently-ignores-mode-append.md`

### Fix Pattern
- Validate required fields before write
- Fail atomically (all-or-nothing for batch)
- Respect append mode in JSON array sinks

### Testing Strategy
- Test missing required fields
- Test validation failures
- Test via `tests/plugins/sinks/`

---

## Group 11: Pooling/Batching State Management (MEDIUM PRIORITY)

**Focus:** Pool stats corruption, deadlocks, mutable context sharing
**Priority:** 1 P1 + 3 P2 + 2 P3 = 6 bugs
**Owner:** Pooling infrastructure engineer
**Estimated effort:** 1 day

### Root Cause
Pooling system: (1) shares mutable state, (2) stats persist across batches, (3) eviction can deadlock.

### P1 Bugs
1. `engine-pooling/P1-2026-02-05-batchtransformmixin-shares-mutable-plugincont.md`

### P2 Bugs
2. `engine-pooling/P2-2026-02-05-evicting-a-non-head-entry-can-permanently-sta.md`
3. `engine-pooling/P2-2026-02-05-global-dispatch-gate-ignores-aimd-current-de.md`
4. `engine-pooling/P2-2026-02-05-pool-stats-persist-across-batches-corrupting.md`

### P3 Bugs
5. `engine-pooling/P3-2026-02-05-timeout-0-treated-as-infinite-wait-in-submit.md`
6. `engine-pooling/P3-2026-02-05-transformoutputadapter-example-omits-state-i.md`

### Fix Pattern
- Deep copy `PluginContext` per batch
- Reset pool stats between batches
- Fix eviction algorithm (allow non-head eviction)

### Testing Strategy
- Test concurrent batch processing
- Test via `tests/plugins/batching/`, `tests/engine/test_processor_batch.py`

---

## Group 12: Telemetry Correctness (LOW PRIORITY)

**Focus:** Telemetry missing fields, wrong event types
**Priority:** 0 P1 + 7 P2 + 3 P3 = 10 bugs
**Owner:** Observability engineer
**Estimated effort:** 1 day

### P2 Bugs
1. `engine-spans/P2-2026-02-05-datadog-exporter-ignores-api-key-so-agentl.md`
2. `engine-spans/P2-2026-02-05-drop-backpressure-drops-newest-event-instead.md`
3. `engine-spans/P2-2026-02-05-externalcallcompleted-telemetry-lacks-token-i.md`
4. `engine-spans/P2-2026-02-05-fieldresolutionapplied-bypasses-granularity-f.md`
5. `engine-spans/P2-2026-02-05-otlp-exporter-accepts-invalid-config-types-an.md`
6. `engine-spans/P2-2026-02-05-span-id-derivation-ignores-utc-normalization.md`
7. `engine-spans/P2-2026-02-05-telemetry-exporter-discovery-ignores-pluggy-h.md`

### P3 Bugs
8. `engine-spans/P3-2026-02-05-aggregate-drop-logging-uses-shared-counter-wi.md`
9. `engine-spans/P3-2026-02-05-azure-monitor-flush-drops-no-events-acknowl.md`
10. `engine-spans/P3-2026-02-05-pop-batch-accepts-negative-max-count-and-sile.md`

### Fix Pattern
- Add missing token_id to telemetry events
- Validate exporter configs at startup
- Fix backpressure to drop oldest (not newest)

### Testing Strategy
- Test telemetry emission at each granularity level
- Test via `tests/telemetry/`

---

## Group 13: Miscellaneous P1s (VARIOUS PRIORITIES)

**Focus:** Remaining P1 bugs not fitting above groups
**Priority:** 9 P1 bugs
**Owner:** Various
**Estimated effort:** 2-3 days

### Bugs
1. `core-retention/P1-2026-02-05-operation-input-output-payloads-are-never-pur.md` (retention)
2. `engine-coalesce/P1-2026-02-05-late-arrival-coalesce-failures-miss-immediate.md` (coalesce)
3. `engine-executors/P1-2026-02-05-gateexecutor-stable-hash-failure-leaves-node.md` (gate executor)
4. `engine-orchestrator/P1-2026-02-05-condition-based-aggregation-triggers-ignored.md` (aggregation)
5. `engine-orchestrator/P1-2026-02-05-quarantined-row-telemetry-hash-can-crash-on-m.md` (quarantine)
6. `engine-processor/P1-2026-02-05-deaggregation-path-crashes-when-transformresu.md` (deaggregation)
7. `mcp/P1-2026-02-05-query-read-only-guard-allows-non-select-o.md` (MCP SQL injection)
8. `plugins-llm/P1-2026-02-05-azure-batch-llm-crashes-on-aggregation-flush.md` (Azure batch LLM)
9. `plugins-llm/P1-2026-02-05-llm-json-validator-accepts-nan-infinity-insid.md` (JSON validation)

### Fix Pattern
Varies by bug - each requires individual analysis.

---

## Group 14: Legacy Code Violations (MEDIUM PRIORITY)

**Focus:** Code violating "No Legacy Code Policy"
**Priority:** 0 P1 + 3 P2 = 3 bugs
**Owner:** Cleanup team
**Estimated effort:** 0.5 day

### P2 Bugs
1. `plugins-transforms/P2-2026-02-05-legacy-sink-header-options-violate-no-legacy.md`
2. `plugins-transforms/P2-2026-02-05-gate-hook-spec-still-advertised-after-gate-pl.md`
3. `plugins-transforms/P3-2026-02-05-basegate-uses-defensive-get-for-fork-to.md`

### Fix Pattern
- Remove all legacy compatibility code
- Update all call sites to new API
- Delete deprecated functions/options completely

---

## Group 15: Remaining P2/P3 Bugs (LOW PRIORITY)

**Focus:** Quality, UX, edge cases
**Priority:** ~40 P2 + 6 P3 bugs
**Owner:** Various
**Estimated effort:** 3-4 days

### Categories
- Source plugin edge cases (CSV/JSON parsing)
- Transform output validation
- CLI error messages
- MCP diagnostic false positives
- Rate limiting edge cases
- Expression parser security hardening

See individual bug files for details.

---

## Recommended Fix Order

### Sprint 1 (This Week) - P1 Critical Path
1. **Group 1**: Tier-1 Audit Trail (10 P1s) - **MUST FIX**
2. **Group 4**: Secret Leakage (2 P1s) - **SECURITY**
3. **Group 5**: Resume/Checkpoint (5 P1s) - **DATA INTEGRITY**

### Sprint 2 (Next Week) - P1 Completion
4. **Group 2**: PipelineRow Migration (6 P1s)
5. **Group 3**: Contract Propagation (2 P1s)
6. **Group 6**: Validation Boundaries (5 P1s)
7. **Group 13**: Misc P1s (9 P1s)

### Sprint 3 (Following Week) - P2 High Value
8. **Group 7**: Azure Plugin Errors (6 bugs)
9. **Group 8**: LLM Audit Completeness (11 bugs)
10. **Group 9**: Transform Config Validation (7 bugs)
11. **Group 10**: Sink Data Integrity (3 bugs)

### Sprint 4+ - P2/P3 Cleanup
12. **Group 11**: Pooling/Batching (6 bugs)
13. **Group 12**: Telemetry (10 bugs)
14. **Group 14**: Legacy Code (3 bugs)
15. **Group 15**: Remaining P2/P3 (~46 bugs)

---

## Parallel Work Opportunities

These groups can be worked **simultaneously** without conflicts:

- **Core work**: Groups 1, 5, 6 (landscape, checkpoint, contracts)
- **Plugin work**: Groups 2, 7, 8, 9, 10 (transforms, Azure, LLM, sinks)
- **Engine work**: Groups 3, 11 (executors, pooling)
- **Observability**: Group 12 (telemetry)

Assign to separate agents/humans for maximum throughput.
