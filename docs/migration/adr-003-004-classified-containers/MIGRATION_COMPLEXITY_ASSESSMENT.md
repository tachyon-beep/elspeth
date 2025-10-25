# Secure Data Container Migration - Complexity Assessment (Phases 1-6)

**Date**: 2025-10-25
**Branch**: feature/adr-003-004-secure-containers (after Phase 0 complete)
**Status**: Planning - Ready to Execute After Terminology Rename
**Assessed By**: Claude Code

> **IMPORTANT**: This document describes **Phases 1-6** of the integrated migration (container adoption).
> **Phase 0** (Terminology Rename: "Classified" → "Secure") is documented in `RENAMING_ASSESSMENT.md`.
>
> **Assumption**: All references below use `SecureDataFrame` / `SecureData[T]` terminology,
> assuming Phase 0 is complete. If executing before Phase 0, mentally substitute
> `SecureDataFrame` ↔ `ClassifiedDataFrame` and `.security_level` ↔ `.classification`.

---

## Executive Summary

**Current State**: ADR-002-A Trusted Container Model is **COMPLETE** and ready to merge. Container classes exist with full constructor protection, uplifting, and validation.

**Gap**: **ZERO plugins/engines** currently use secure containers. All datasources return plain `pd.DataFrame` with security level in `.attrs`.

**Scope**: Migrate **4 critical files** + **~16 medium-impact files** to use classified containers throughout the data pipeline.

**Complexity**: **MEDIUM** (18-24 hours) - Well-defined interfaces, comprehensive test safety net exists, clear migration path.

---

## Current State Analysis

### ✅ What's DONE (ADR-002-A Complete)

1. **ClassifiedDataFrame** - Fully implemented in `src/elspeth/core/security/classified_data.py`:
   - ✅ Constructor protection (datasource-only creation)
   - ✅ Immutable classification (frozen dataclass)
   - ✅ Automatic uplifting (high water mark)
   - ✅ Access validation (runtime failsafe)
   - ✅ CVE-ADR-002-A-001 fixed (frame equality bypass)
   - ✅ 72 passing tests (invariants, performance, integration)

2. **Security Infrastructure**:
   - ✅ SecurityLevel enum and comparison
   - ✅ Suite-level minimum envelope validation
   - ✅ Plugin clearance enforcement at start-time
   - ✅ Comprehensive threat model documented

### ❌ What's NOT DONE (Migration Needed)

1. **No datasources use ClassifiedDataFrame** - All 4 return plain `pd.DataFrame`:
   ```python
   # Current (line 108 of _csv_base.py):
   df.attrs["security_level"] = self.security_level
   return df

   # Target:
   return ClassifiedDataFrame.create_from_datasource(df, self.security_level)
   ```

2. **No engines/runners use ClassifiedDataFrame** - Accept plain DataFrame:
   ```python
   # Current (orchestrator.py:152):
   df = datasource.load()  # Returns pd.DataFrame
   runner.run(df)          # Accepts pd.DataFrame

   # Target:
   classified_df = datasource.load()  # Returns ClassifiedDataFrame
   runner.run(classified_df)           # Accepts ClassifiedDataFrame
   ```

3. **No generic ClassifiedData[T] wrapper** - Need for dict/metadata propagation

4. **No middleware unwrap/wrap** - Middleware sees plain dicts, no classification

---

## Migration Scope

### Critical Path (BLOCKING - 8-10 hours)

| File | Current Signature | Target Signature | Impact |
|------|------------------|------------------|--------|
| **4 Datasources** | `load() -> pd.DataFrame` | `load() -> ClassifiedDataFrame` | HIGH |
| `src/elspeth/plugins/nodes/sources/_csv_base.py` (line 93) | Return `df` | Return `ClassifiedDataFrame.create_from_datasource(df, self.security_level)` | CRITICAL |
| `src/elspeth/plugins/nodes/sources/blob.py` (line 46) | Same as above | Same as above | CRITICAL |
| `src/elspeth/core/orchestrator.py` (line 152) | `df = datasource.load()` | `classified_df = datasource.load()` | HIGH |
| `src/elspeth/core/experiments/runner.py` (line ~159) | `def run(self, df: pd.DataFrame)` | `def run(self, df: ClassifiedDataFrame)` | CRITICAL |

**Deliverables**:
- ClassifiedDataFrame propagates from datasource → orchestrator → runner
- All 4 datasources use factory method
- Runner extracts `.data` when needed for row iteration
- Suite runner updated for ClassifiedDataFrame handoff

---

### Medium Impact (ENHANCEMENT - 5-7 hours)

| Component | Files | Change Needed | Priority |
|-----------|-------|---------------|----------|
| **Generic Wrapper** | NEW: `classified_data.py` | Create `ClassifiedData[T]` for dicts/metadata | P1 |
| **LLM Middleware** | 6 files in `transforms/llm/middleware/` | Unwrap/wrap `ClassifiedData[dict]` in request metadata | P2 |
| **Row Plugins** | ~10 files in `plugins/experiments/row/` | Accept `ClassifiedData[dict]` for row context | P2 |
| **Suite Runner** | `core/experiments/suite_runner.py` | Pass ClassifiedDataFrame between experiments | P1 |

**Deliverables**:
- `ClassifiedData[T]` generic wrapper (similar to ClassifiedDataFrame but for any type)
- Middleware integration pattern (unwrap before processing, wrap after)
- Row plugin signature updates
- Uplifting at each transformation boundary

---

### Low Impact (OPTIONAL - 3-4 hours)

| Component | Files | Change Needed | Risk |
|-----------|-------|---------------|------|
| **Sinks** | 16 sink implementations | Already use `metadata.security_level`, minimal changes | LOW |
| **Aggregators** | 6 aggregator plugins | May need unwrap/wrap, or no change (dict-based) | LOW |
| **Baseline Plugins** | 9 baseline comparison plugins | Verify no changes needed (dict-based) | VERY LOW |

**Deliverables**:
- Verify sinks work with ClassifiedDataFrame in payload
- Test aggregators with classified data
- Baseline plugins compatibility check

---

## Infrastructure Needed

### New Infrastructure (2-3 hours)

1. **`ClassifiedData[T]` Generic Wrapper**
   ```python
   @dataclass(frozen=True)
   class ClassifiedData[T]:
       """Generic wrapper for classified data of any type."""
       data: T
       classification: SecurityLevel

       @classmethod
       def create_from_datasource(cls, data: T, classification: SecurityLevel) -> ClassifiedData[T]:
           """Only datasources/trusted sources can create."""
           ...

       def with_uplifted_classification(self, new_level: SecurityLevel) -> ClassifiedData[T]:
           """Uplift (max operation, no downgrades)."""
           ...
   ```

2. **Utilities** (add to `classified_data.py`):
   - `unwrap(classified: ClassifiedData[T]) -> T` - Extract data (public, safe)
   - **NO public `wrap()` helper** - would allow untrusted downgrading (CVE-ADR-002-A-003)
   - Instead: Use `with_new_data()` pattern from existing `ClassifiedData` instance

   **SECURITY**: Public `wrap()` would allow classification laundering:
   ```python
   # ❌ ATTACK if wrap() were public:
   secret_data = input_frame.data
   downgraded = ClassifiedData.wrap(secret_data, SecurityLevel.UNOFFICIAL)  # BYPASS!
   ```

   **Safe Pattern**: Only uplift from existing containers:
   ```python
   # ✓ SAFE: Create from existing container
   secure_context = existing_frame.with_new_data(context_dict)
   uplifted = secure_context.with_uplifted_classification(plugin.get_security_level())
   ```

3. **ClassifiedDataFrame Extensions**:
   - **`.create_classified_dict(data: dict) -> ClassifiedData[dict]`** - Safe factory for dict wrapping
     - Creates `ClassifiedData[dict]` with same classification as frame
     - ONLY way to create `ClassifiedData` from dict without datasource
     - Prevents classification laundering (no public `wrap()` helper)
   - `.head(n)` support for CLI preview (unwrap, show, rewrap)
   - `.unwrap()` convenience method
   - Better repr for debugging

   **Security Pattern**:
   ```python
   # ✓ SAFE: Create ClassifiedData[dict] from existing frame
   classified_frame: ClassifiedDataFrame = datasource.load()
   context_dict = {"row_id": 1, "data": "..."}

   # Factory method uses frame's classification
   classified_context = classified_frame.create_classified_dict(context_dict)
   # classification == classified_frame.classification

   # Then uplift as needed
   uplifted = classified_context.with_uplifted_classification(plugin_level)
   ```

---

## Data Flow After Migration

```
┌─────────────────────────────────────────────────────────────────┐
│ Tier 0: Datasource Load                                        │
│   CSVDataSource.load() -> ClassifiedDataFrame                  │
│   └─ create_from_datasource(df, SecurityLevel.OFFICIAL)        │
└─────────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ Tier 1: Orchestrator Handoff                                   │
│   classified_df = datasource.load()                            │
│   runner.run(classified_df)  # ClassifiedDataFrame             │
└─────────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ Tier 2: Runner Row Processing                                  │
│   for idx, row in classified_df.data.iterrows():               │
│       context = prepare_prompt_context(row, ...)               │
│       # SAFE: Create ClassifiedData[dict] from existing frame  │
│       # Uses frame's classification as starting point          │
│       classified_context = classified_df.create_classified_dict(context)  │
│       # Then uplift to runner's security level                 │
│       uplifted_context = classified_context.with_uplifted_classification( │
│           runner.security_level                                │
│       )                                                         │
│       # Middleware sees ClassifiedData[dict]                   │
│       response = middleware_chain(uplifted_context)            │
└─────────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ Tier 3: Aggregation & Sink Dispatch                            │
│   payload = {"results": ..., "metadata": ...}                  │
│   # SAFE: Create from existing classified frame               │
│   classified_payload = classified_df.create_classified_dict(payload) │
│   # Uplift to final classification (highest level in pipeline) │
│   final_payload = classified_payload.with_uplifted_classification( │
│       final_classification                                      │
│   )                                                             │
│   artifact_pipeline.execute(final_payload, sinks)              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Complexity Analysis

### High Complexity Areas (6-8 hours)

1. **Runner Row Iteration** (runner.py:767-850):
   - Currently: `for idx, row in df.iterrows():`
   - Target: `for idx, row in classified_df.data.iterrows():`
   - Need: Uplift row dict → ClassifiedData → middleware → aggregation
   - **Risk**: Row dict schema changes, middleware integration points

2. **Middleware Integration** (6 files):
   - Current: `before_request(request: LLMRequest)` where `request.metadata: dict`
   - Target: `request.metadata: ClassifiedData[dict]`
   - Need: Unwrap before processing, wrap after, preserve classification
   - **Risk**: Breaking changes to middleware protocol

3. **Suite Runner Experiment Chain** (suite_runner.py:86-210):
   - Current: Pass plain DataFrames between experiments
   - Target: Pass ClassifiedDataFrame, uplift between experiments
   - Need: Baseline comparison with classified data
   - **Risk**: Baseline payload uplifting logic

### Medium Complexity Areas (4-6 hours)

4. **Generic ClassifiedData[T] Implementation**:
   - Pattern: Copy ClassifiedDataFrame, make generic
   - Risk: Type system complexity (TypeVar, Generic)
   - Testing: Need similar invariant tests

5. **Datasource Migration** (4 files):
   - Pattern: Replace `return df` with `return ClassifiedDataFrame.create_from_datasource(df, level)`
   - Risk: LOW (single-line changes, factory method exists)
   - Testing: Existing tests + new ClassifiedDataFrame validation

### Low Complexity Areas (2-3 hours)

6. **Orchestrator Update**:
   - Pattern: Accept ClassifiedDataFrame, pass through
   - Risk: VERY LOW (type annotation change)

7. **Sink Compatibility**:
   - Pattern: Extract classification from metadata (already done)
   - Risk: VERY LOW (sinks already handle security_level)

---

## Migration Strategy (5 Phases)

### Phase 0: Infrastructure (2-3 hours)

**Objective**: Build foundation without breaking existing code.

1. Create `ClassifiedData[T]` generic wrapper
2. Add utility functions (unwrap, wrap, uplift_dict)
3. Extend ClassifiedDataFrame with convenience methods
4. Write invariant tests for ClassifiedData[T]

**Exit Criteria**:
- ✅ All new tests passing
- ✅ No changes to existing code yet
- ✅ MyPy clean

---

### Phase 1: Datasource Migration (2 hours)

**Objective**: Datasources return ClassifiedDataFrame.

**Changes**:
1. `_csv_base.py` line 93: `load() -> ClassifiedDataFrame`
2. `blob.py` line 46: Same
3. Update DataSource protocol signature
4. Update all datasource tests

**Testing**:
- Verify datasources create ClassifiedDataFrame
- Verify constructor protection blocks plugins
- Verify schema attachment still works

**Exit Criteria**:
- ✅ 4 datasources migrated
- ✅ All datasource tests passing
- ✅ No orchestrator changes yet (type mismatch expected)

---

### Phase 2: Orchestrator & Runner Core (3-4 hours)

**Objective**: Propagate ClassifiedDataFrame through execution core.

**Changes**:
1. `orchestrator.py` line 152: Accept ClassifiedDataFrame
2. `runner.py` line ~159: `def run(self, df: ClassifiedDataFrame)`
3. `runner.py` line 767-850: Extract `.data` for row iteration
4. `suite_runner.py`: Pass ClassifiedDataFrame between experiments

**Testing**:
- End-to-end suite test with ClassifiedDataFrame
- Verify classification uplifting between experiments
- Verify baseline comparison still works

**Exit Criteria**:
- ✅ Orchestrator accepts ClassifiedDataFrame
- ✅ Runner processes rows from ClassifiedDataFrame.data
- ✅ All integration tests passing
- ✅ Middleware sees plain dicts (no breaking changes yet)

---

### Phase 3: Middleware Integration (3-4 hours)

**Objective**: Middleware sees and propagates classification.

**Changes**:
1. Wrap row context dicts in ClassifiedData[dict]
2. Update middleware protocol to accept ClassifiedData[dict]
3. Middleware unwraps, processes, wraps with uplifting
4. 6 middleware files updated

**Testing**:
- Test each middleware with classified data
- Verify uplifting preserves high water mark
- Verify unwrap/wrap round-trip

**Exit Criteria**:
- ✅ Middleware integrates ClassifiedData[dict]
- ✅ All middleware tests passing
- ✅ Classification propagates correctly

---

### Phase 4: Row Plugins & Aggregators (2-3 hours)

**Objective**: Row/aggregation plugins handle classified data.

**Changes**:
1. Update row plugin signatures (optional - may not need)
2. Verify aggregators work with classified payloads
3. Test baseline plugins with ClassifiedDataFrame

**Testing**:
- Row plugin execution with classified context
- Aggregator execution with classified results
- Baseline comparison with classified data

**Exit Criteria**:
- ✅ All row plugins compatible
- ✅ All aggregators compatible
- ✅ All baseline plugins compatible

---

### Phase 5: Verification & Documentation (1-2 hours)

**Objective**: Confirm end-to-end classification propagation.

**Activities**:
1. Run full test suite (all 800+ tests)
2. Run sample suite with classification logging
3. Verify classification uplifts at each boundary
4. Update plugin development guide
5. Create migration ADR

**Exit Criteria**:
- ✅ All tests passing (100%)
- ✅ Zero behavioral changes
- ✅ MyPy clean, Ruff clean
- ✅ Documentation updated
- ✅ ADR created

---

## Estimated Effort

| Phase | Hours | Complexity | Risk |
|-------|-------|------------|------|
| **Phase 0: Infrastructure** | 2-3 | MEDIUM | LOW |
| **Phase 1: Datasources** | 2 | LOW | VERY LOW |
| **Phase 2: Core Engine** | 3-4 | HIGH | MEDIUM |
| **Phase 3: Middleware** | 3-4 | HIGH | MEDIUM |
| **Phase 4: Plugins** | 2-3 | MEDIUM | LOW |
| **Phase 5: Verification** | 1-2 | LOW | VERY LOW |
| **TOTAL** | **13-18 hours** | **MEDIUM** | **MEDIUM** |

**Conservative Estimate**: 18-24 hours (accounting for testing, edge cases, documentation)

**Parallel Work Opportunities**:
- Phase 0 + Phase 1 can be done in parallel (infrastructure + datasources)
- Phase 4 (plugins) can be done in parallel with Phase 5 (docs)

---

## Risk Assessment

### Critical Risks (Mitigation Required)

1. **Breaking Middleware Protocol** (MEDIUM RISK)
   - **Impact**: All 6 middleware plugins fail
   - **Mitigation**: Provide backward-compatible unwrap in runner, migrate middleware incrementally
   - **Fallback**: Runner unwraps ClassifiedData before middleware (defer middleware migration)

2. **Row Iteration Performance** (LOW RISK)
   - **Impact**: Unwrap/wrap overhead on every row
   - **Mitigation**: Batch uplifting, lazy evaluation, performance tests (ADR-002-A already has benchmarks showing <0.1ms overhead)
   - **Fallback**: Optimize hot path with caching

3. **Type System Complexity** (MEDIUM RISK)
   - **Impact**: MyPy errors with ClassifiedData[T] generics
   - **Mitigation**: Comprehensive type annotations, test type checker, use typing.cast where needed
   - **Fallback**: Use Any temporarily, fix incrementally

### Minor Risks (Monitor)

4. **Test Maintenance** (LOW RISK)
   - **Impact**: Many tests need ClassifiedDataFrame fixtures
   - **Mitigation**: Create test factory functions, update conftest.py
   - **Effort**: 1-2 hours

5. **Baseline Comparison** (LOW RISK)
   - **Impact**: Baseline payload uplifting logic
   - **Mitigation**: Existing tests cover baseline flow, add classification checks
   - **Effort**: 30 minutes

---

## Success Criteria

### Must-Have (MVP)

- ✅ All datasources return ClassifiedDataFrame
- ✅ Orchestrator and runner propagate ClassifiedDataFrame
- ✅ Classification uplifts at each boundary (datasource → runner → middleware)
- ✅ All 800+ tests passing (zero regressions)
- ✅ MyPy clean, Ruff clean
- ✅ End-to-end suite test with classification logging

### Should-Have (Quality)

- ✅ Middleware integrates ClassifiedData[dict]
- ✅ Row plugins compatible
- ✅ Performance validation (<0.1ms overhead per suite, as per ADR-002-A benchmarks)
- ✅ Plugin development guide updated
- ✅ Migration ADR created

### Nice-to-Have (Future)

- ⭕ Aggregators use ClassifiedData[dict]
- ⭕ Baseline plugins explicitly handle classification
- ⭕ Classification audit logging (track uplifts)
- ⭕ Feature flag for gradual rollout

---

## Dependencies & Blockers

### Unblocked (Ready to Start)

- ✅ ADR-002-A Trusted Container Model complete
- ✅ ClassifiedDataFrame fully implemented and tested
- ✅ Comprehensive test suite exists (800+ tests)
- ✅ Clear migration path documented

### Prerequisites (Before Starting)

- ⭕ Merge current branch (feature/adr-002-security-enforcement)
- ⭕ Create new branch (feature/classified-data-migration)
- ⭕ Review/approve migration plan with team

### External Dependencies

- **NONE** - All work internal to Elspeth codebase

---

## Recommendation

**Assessment**: **MEDIUM COMPLEXITY** - Well-defined scope, clear interfaces, comprehensive safety net.

**Approach**: Follow the **5-phase migration strategy** using the complexity reduction methodology:
1. **Phase 0 as "Safety Net"** - Build infrastructure, write tests BEFORE touching plugins
2. **Incremental migration** - One phase at a time, test after each
3. **Commit frequently** - After each phase minimum
4. **Zero behavioral changes** - Refactoring only (structure changes, not behavior)

**Timeline**: **2-3 days** (18-24 hours) with rigorous testing and documentation.

**Confidence**: **HIGH** - Similar pattern to ADR-002-A implementation which was successful (100% tests passing, zero regressions).

---

## Next Steps

1. **Review this assessment** with team
2. **Approve migration plan** (5-phase strategy)
3. **Merge current branch** (ADR-002-A complete)
4. **Create migration branch** (feature/classified-data-migration)
5. **Start Phase 0** (infrastructure + tests)

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

**Assessed By**: Claude Code
**Review Date**: 2025-10-25
**Confidence**: HIGH (based on comprehensive codebase exploration)
