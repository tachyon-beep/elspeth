# Bug Triage Report - 2026-01-31

## Summary

Triaged **122 generated bug reports** from `docs/bugs/generated/`. Results:

| Status | Count |
|--------|-------|
| **VALID** | 73 |
| **INVALID/EMPTY** | 46 |
| **DUPLICATE** | 3 |

## P1 Bugs Created (9 filed)

These critical bugs have been filed in `docs/bugs/open/`:

| Bug | Location | Issue |
|-----|----------|-------|
| P1-2026-01-31-recovery-missing-payload-hash-verification | core-checkpoint/ | Resume doesn't verify payload integrity |
| P1-2026-01-31-payload-store-path-traversal | core-payload/ | Path traversal via unvalidated content_hash |
| P1-2026-01-31-routing-reason-payload-not-persisted | core-landscape/ | Routing reason payloads never stored |
| P1-2026-01-31-sanitized-webhook-url-fragment-secrets | core-security/ | Fragment-based secrets not sanitized |
| P1-2026-01-31-sink-flush-failure-leaves-open-states | engine-executors/ | Sink flush failures leave OPEN states |
| P1-2026-01-31-multi-query-output-key-collisions | plugins-llm/ | Silent data loss from key collisions |
| P1-2026-01-31-settings-path-missing-silent-fallback | cli/ | Missing settings file silently falls back |
| P1-2026-01-31-row-reorder-buffer-deadlock | engine-pooling/ | Deadlock on non-head sequence eviction |
| P1-2026-01-31-azure-blob-sink-no-audit-calls | plugins-sinks/ | Azure Blob operations not audited |

## Remaining Valid Bugs (64 pending)

### Additional P1 Bugs (not yet filed)

| Area | Bug | Priority |
|------|-----|----------|
| core-landscape | fetchone multi-row silent truncation | P1 |
| core-landscape | compute_grade no determinism validation | P1 |
| core-landscape | json formatter nan coercion | P1 |
| core-landscape | nodestate repo missing invariant checks | P1 |
| core-landscape | token outcome repo is_terminal coercion | P1 |
| core-checkpoint | RUNNING status blocks resume | P1 |
| core-dag | Gate drops computed schema guarantees | P1 |
| engine-orchestrator | Quarantine outcome before durability | P1 |
| engine-expression-parser | Expression errors bubble as raw exceptions | P1 |
| plugins-context | record_call bypasses centralized call_index | P1 |
| plugins-batching | mixin UnboundLocalError on exception | P1 |
| plugins-clients | LLM response payload dropped on parse failure | P1 |
| plugins-clients | HTTP client records raw URLs with secrets | P1 |
| plugins-sources | Azure CSV bad lines skipped without quarantine | P1 |
| plugins-sources | Azure JSON array errors crash instead of quarantine | P1 |
| plugins-sources | Azure JSON accepts NaN/Infinity | P1 |

### P2 Bugs (not yet filed)

| Area | Count | Examples |
|------|-------|----------|
| CLI | 2 | Resume payload backend ignored, rate limit cleanup |
| Contracts | 4 | Schema compatibility, ArtifactDescriptor duck-typing, etc. |
| Engine | 4 | Config gate MissingEdgeError, trigger coercion, etc. |
| Core/Landscape | 4 | Token outcome non-canonical, schema dialect-specific, etc. |
| Core (other) | 9 | Sink names lowercased, mixed logging, rate limit issues, etc. |
| Plugins/LLM | 5 | Azure batch custom_id, missing call records, retry semantics, etc. |
| Plugins (misc) | 3 | Verifier error misclassification, Azure auth method, etc. |
| MCP | 2 | Missing run_id filter, wrong status literal |

### P3 Bugs (not yet filed)

| Area | Count | Examples |
|------|-------|----------|
| Contracts | 3 | RowResult legacy accessors, telemetry output_hash, routing action |
| Core | 2 | Payload store re-export, checkpoint ID truncation |
| Engine | 1 | Aggregation missing telemetry |
| Core/Landscape | 1 | Lineage formatter fabricated latency |
| Plugins | 2 | Batching examples signature, Azure docstring |

## Duplicates Found

1. `retry.py.md` Bug 1 → Already exists as `P3-2026-01-21-retry-on-retry-called-after-final-attempt.md`
2. `retry.py.md` Bug 2 → Already exists as `P3-2026-01-21-retry-attempt-index-mismatch.md`
3. `exporter.py.md` → Partial duplicate of `P2-2026-01-19-exporter-missing-config-in-export.md` (should expand existing)

## Invalid/Empty Reports

46 files contained "No concrete bug found" or were empty placeholders. These should be deleted:

- All `__init__.py.md` files (empty modules)
- Files explicitly stating "No bug identified"
- Empty template files in plugins/pooling/

## Next Steps

1. **Immediate**: Address filed P1 bugs (9 critical issues)
2. **This sprint**: File remaining P1 bugs (~16 more)
3. **Next sprint**: File P2 bugs (~33 issues)
4. **Backlog**: File P3 bugs (~9 issues)
5. **Cleanup**: Delete `docs/bugs/generated/` directory after all bugs filed

## Methodology

Triage performed by parallel Claude Code agents:
- Each agent verified bugs against actual source code line numbers
- Checked for duplicates against existing `docs/bugs/open/` bugs
- Validated priority assessments (some adjusted based on impact analysis)
- Invalid reports marked for deletion
