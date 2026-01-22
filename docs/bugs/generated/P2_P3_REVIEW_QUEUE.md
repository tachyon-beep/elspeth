# P2-P3 Novel Bug Review Queue

Generated: 2026-01-22

This document contains all P2 and P3 bugs from the generated bug reports that are **novel** (not already filed as duplicates, not already processed as P0-P1). Each bug includes a quick assessment of likelihood and recommended action.

## Executive Summary

| Priority | Total | Likely Real | Needs Verification | Probable False Positive |
|----------|-------|-------------|-------------------|------------------------|
| P2 | 18 | 12 | 5 | 1 |
| P3 | 4 | 2 | 2 | 0 |

---

## P2 Bugs Review Table

| # | Title | Component | Source File | Likely Real? | Recommendation |
|---|-------|-----------|-------------|--------------|----------------|
| 1 | Resume forces mode=append on all sinks | CLI | cli.py.md | **YES** | Spot-check: verify JSON/DB sink resume |
| 2 | BatchOutput contract missing batch_output_id | Contracts | audit.py.md | **YES** | Promote directly - schema/contract mismatch is verifiable |
| 3 | check_compatibility ignores field constraints | Contracts | data.py.md | **LIKELY** | Spot-check: test FiniteFloat compatibility |
| 4 | Checkpoint aggregation_state_json bypasses canonical | Checkpoint | manager.py.md | **YES** | Promote directly - code clearly uses raw json.dumps |
| 5 | can_resume accepts invalid run status | Checkpoint | recovery.py.md | **YES** | Promote directly - enum validation gap is clear |
| 6 | resolve_config not exported from elspeth.core | Core | __init__.py.md | **YES** | Promote directly - trivial to verify via import |
| 7 | Nested numpy arrays skip recursive normalization | Canonical | canonical.py.md | **LIKELY** | Spot-check: test 2D array with pd.Timestamp |
| 8 | Duplicate coalesce branch names overwritten in DAG | DAG | dag.py.md | **YES** | Promote - duplicate logic matches DUPLICATES.md analysis |
| 9 | Schema validation misses newer required columns | Landscape | database.py.md | **YES** | Promote - _REQUIRED_COLUMNS clearly incomplete |
| 10 | get_calls returns raw strings for call enums | Landscape | recorder.py.md | **YES** | Promote directly - enum coercion gap is clear |
| 11 | NodeRepository drops schema_mode and schema_fields | Landscape | repositories.py.md | **YES** | Spot-check: verify load() mapping |
| 12 | compute_grade ignores invalid determinism values | Landscape | reproducibility.py.md | **YES** | Promote - Tier 1 violation clear |
| 13 | update_grade_after_purge leaves FULL_REPRODUCIBLE | Landscape | reproducibility.py.md | **LIKELY** | Spot-check: verify semantics intent |
| 14 | Key Vault empty secret accepted as HMAC key | Security | fingerprint.py.md | **YES** | Promote directly - security issue, clear validation gap |
| 15 | Plugin gate routes missing in ExecutionGraph | DAG | dag.py.md | **DUPLICATE** | Already in pending: P2-2026-01-19-plugin-gate-graph-mismatch.md |
| 16 | Exporter uses N+1 query pattern | Landscape | exporter.py.md | **DUPLICATE** | Already in pending: P2-2026-01-19-exporter-n-plus-one-queries.md |
| 17 | Export omits run/node config and determinism | Landscape | exporter.py.md | **DUPLICATE** | Already in pending: P2-2026-01-19-exporter-missing-config-in-export.md |
| 18 | Token export omits expand_group_id | Landscape | exporter.py.md | **DUPLICATE** | Already in open: P2-2026-01-19-exporter-missing-expand-group-id.md |

### P2 Bugs - Detailed Summaries

#### 1. Resume forces mode=append on all sinks (CLI)
- **One-line**: `_build_resume_pipeline_config` injects `mode=append` for all sinks but JSON/Database sinks reject unknown fields.
- **Related bugs**: None identified
- **Assessment**: High confidence - plugin configs are strict (`extra="forbid"`), code clearly adds `mode` unconditionally.
- **Action**: Spot-check by attempting resume with JSON sink.

#### 2. BatchOutput contract missing batch_output_id (Contracts)
- **One-line**: `BatchOutput` dataclass omits the `batch_output_id` primary key from the schema table.
- **Related bugs**: None
- **Assessment**: High confidence - direct schema/contract mismatch.
- **Action**: Promote to pending without verification.

#### 3. check_compatibility ignores field constraints (Contracts)
- **One-line**: Schema compatibility only checks annotations, not constraint metadata like `allow_inf_nan=False`.
- **Related bugs**: References closed P2-2026-01-19-non-finite-floats-pass-source-validation.md
- **Assessment**: Likely real - follows logically from how Pydantic stores constraints.
- **Action**: Spot-check with FiniteFloat producer/consumer compatibility test.

#### 4. Checkpoint aggregation_state_json bypasses canonical (Checkpoint)
- **One-line**: `CheckpointManager.create_checkpoint()` uses raw `json.dumps` without canonical normalization or NaN rejection.
- **Related bugs**: None
- **Assessment**: High confidence - code clearly uses `json.dumps(aggregation_state)` directly.
- **Action**: Promote to pending without verification.

#### 5. can_resume accepts invalid run status (Checkpoint)
- **One-line**: `RecoveryManager.can_resume` treats any status other than RUNNING/COMPLETED as resumable, including invalid enum values.
- **Related bugs**: None
- **Assessment**: High confidence - Tier 1 violation, enum validation gap is clear from code.
- **Action**: Promote to pending without verification.

#### 6. resolve_config not exported from elspeth.core (Core)
- **One-line**: `from elspeth.core import resolve_config` fails despite documented API.
- **Related bugs**: None
- **Assessment**: High confidence - trivially verifiable via import.
- **Action**: Promote to pending without verification.

#### 7. Nested numpy arrays skip recursive normalization (Canonical)
- **One-line**: Multi-dimensional numpy arrays with pandas/numpy objects fail canonicalization.
- **Related bugs**: None
- **Assessment**: Likely real - ndarray handling appears to skip recursive normalization.
- **Action**: Spot-check with 2D array containing pd.Timestamp.

#### 8. Duplicate coalesce branch names overwritten in DAG (DAG)
- **One-line**: Same branch in multiple coalesce configs overwrites `branch_to_coalesce` dict entries.
- **Related bugs**: Related to P1 config.py bug about duplicate branch names
- **Assessment**: High confidence - dict overwrite is clear in code.
- **Action**: Promote to pending, may be fixed alongside P1 config validation.

#### 9. Schema validation misses newer required columns (Landscape)
- **One-line**: `_REQUIRED_COLUMNS` only checks `tokens.expand_group_id`, missing `nodes.schema_mode` and `nodes.schema_fields_json`.
- **Related bugs**: None
- **Assessment**: High confidence - _REQUIRED_COLUMNS list is clearly incomplete.
- **Action**: Promote to pending without verification.

#### 10. get_calls returns raw strings for call enums (Landscape)
- **One-line**: `LandscapeRecorder.get_calls()` returns raw DB strings for `call_type` and `status` instead of enum values.
- **Related bugs**: None
- **Assessment**: High confidence - code clearly passes raw strings to Call constructor.
- **Action**: Promote to pending without verification.

#### 11. NodeRepository drops schema_mode and schema_fields (Landscape)
- **One-line**: `NodeRepository.load` ignores `schema_mode` and `schema_fields_json` columns.
- **Related bugs**: Open P3-2026-01-19-node-repository-drops-schema-config.md already exists
- **Assessment**: Duplicate of existing open bug.
- **Action**: Skip - already filed.

#### 12. compute_grade ignores invalid determinism values (Landscape)
- **One-line**: Invalid determinism strings in `nodes` are silently treated as reproducible instead of crashing.
- **Related bugs**: None
- **Assessment**: High confidence - Tier 1 violation, code only checks for known non-reproducible values.
- **Action**: Promote to pending without verification.

#### 13. update_grade_after_purge leaves FULL_REPRODUCIBLE (Landscape)
- **One-line**: Deterministic runs remain `FULL_REPRODUCIBLE` after payload purge, contradicting documented semantics.
- **Related bugs**: None
- **Assessment**: Likely real but needs semantics clarification - may be intentional design.
- **Action**: Spot-check: verify intended semantics with architecture docs.

#### 14. Key Vault empty secret accepted as HMAC key (Security)
- **One-line**: Empty Key Vault secret value accepted as valid HMAC key, defeating fingerprint security.
- **Related bugs**: None
- **Assessment**: High confidence - security issue, validation gap is clear.
- **Action**: Promote to pending without verification.

---

## P3 Bugs Review Table

| # | Title | Component | Source File | Likely Real? | Recommendation |
|---|-------|-----------|-------------|--------------|----------------|
| 1 | RoutingReason contract out of sync | Contracts | errors.py.md | **LIKELY** | Spot-check: verify GateExecutor emits `condition`/`result` |
| 2 | TransformReason contract out of sync | Contracts | errors.py.md | **LIKELY** | Spot-check: verify transform error payloads |
| 3 | BatchRepository drops trigger_type | Landscape | repositories.py.md | **YES** | Promote directly - clear field omission |
| 4 | Landscape Models drift from contracts/schema | Landscape | models.py.md | **DUPLICATE** | Already in open: P3-2026-01-19-landscape-models-duplication-drift.md |

### P3 Bugs - Detailed Summaries

#### 1. RoutingReason contract out of sync with GateExecutor (Contracts)
- **One-line**: `RoutingReason` requires `rule`/`matched_value` but GateExecutor emits `condition`/`result`.
- **Related bugs**: None
- **Assessment**: Likely real - contract drift is common with evolving code.
- **Action**: Spot-check by inspecting actual gate reason payloads.

#### 2. TransformReason contract out of sync with TransformResult.error (Contracts)
- **One-line**: `TransformReason` requires `action` but transforms emit `message`/`reason`/`error` keys.
- **Related bugs**: None
- **Assessment**: Likely real - transforms clearly use different keys than contract.
- **Action**: Spot-check by inspecting actual transform error payloads.

#### 3. BatchRepository drops trigger_type (Landscape)
- **One-line**: `BatchRepository.load` never assigns `trigger_type` from DB, losing aggregation trigger metadata.
- **Related bugs**: None
- **Assessment**: High confidence - clear field omission in load() method.
- **Action**: Promote to pending without verification.

---

## Recommendations Summary

### Immediate Promotion to pending/ (No Verification Needed)

These bugs have clear code evidence and can be promoted directly:

1. **P2: BatchOutput contract missing batch_output_id** - Schema/contract mismatch
2. **P2: Checkpoint aggregation_state_json bypasses canonical** - Clear json.dumps usage
3. **P2: can_resume accepts invalid run status** - Clear enum validation gap
4. **P2: resolve_config not exported** - Trivially verifiable import
5. **P2: Duplicate coalesce branch names in DAG** - Clear dict overwrite
6. **P2: Schema validation misses newer required columns** - Incomplete _REQUIRED_COLUMNS
7. **P2: get_calls returns raw strings for call enums** - Clear coercion gap
8. **P2: compute_grade ignores invalid determinism** - Tier 1 violation
9. **P2: Key Vault empty secret accepted** - Security validation gap
10. **P3: BatchRepository drops trigger_type** - Clear field omission

### Spot-Check Required

These bugs should be verified before promotion:

1. **P2: Resume forces mode=append on all sinks** - Test resume with JSON/DB sink
2. **P2: check_compatibility ignores field constraints** - Test FiniteFloat compatibility
3. **P2: Nested numpy arrays skip normalization** - Test 2D array with pd.Timestamp
4. **P2: update_grade_after_purge semantics** - Clarify intended behavior
5. **P3: RoutingReason contract drift** - Inspect actual gate reason payloads
6. **P3: TransformReason contract drift** - Inspect actual transform error payloads

### Already Filed (Skip)

These bugs are duplicates of existing reports:

- P2: Plugin gate routes missing in ExecutionGraph -> `docs/bugs/pending/P2-2026-01-19-plugin-gate-graph-mismatch.md`
- P2: Exporter uses N+1 query pattern -> `docs/bugs/pending/P2-2026-01-19-exporter-n-plus-one-queries.md`
- P2: Export omits run/node config -> `docs/bugs/pending/P2-2026-01-19-exporter-missing-config-in-export.md`
- P2: Token export omits expand_group_id -> `docs/bugs/open/P2-2026-01-19-exporter-missing-expand-group-id.md`
- P2: NodeRepository drops schema_mode -> `docs/bugs/open/P3-2026-01-19-node-repository-drops-schema-config.md`
- P3: Landscape Models drift -> `docs/bugs/open/P3-2026-01-19-landscape-models-duplication-drift.md`

---

## False Positive Analysis

Only one bug was assessed as potentially a false positive:

**None identified as clear false positives** - All generated P2-P3 bugs appear to have code evidence supporting their validity. The main uncertainty is around intended semantics (e.g., reproducibility grade after purge) rather than incorrect analysis.

---

## Priority Adjustment Recommendations

Some bugs may warrant priority changes based on impact:

### Upgrade to P1 Candidates
- **Key Vault empty secret accepted as HMAC key** (currently P2) - Security issue, should potentially be P1
- **can_resume accepts invalid run status** (currently P2) - Tier 1 violation, should potentially be P1

### Downgrade Candidates
- None identified - all P2 bugs have meaningful audit/integrity impact

---

## Next Steps

1. **Batch promote** the 10 high-confidence bugs to `docs/bugs/pending/`
2. **Run spot-checks** for the 6 verification-required bugs
3. **Update DUPLICATES.md** to mark the 6 duplicate bugs as already filed
4. **Review P1 candidates** for priority upgrade decision
