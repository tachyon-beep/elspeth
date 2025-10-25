# ADR-003 + ADR-004 Migration: Secure Data Container Adoption

**Migration Type**: Terminology + Architecture Enhancement - Secure Container Adoption
**Status**: Planning Complete - Ready for Execution
**Target ADRs**:
- **Terminology Rename** (Phase 0): "Classified" → "Secure" for universal applicability
- **ADR-003** (Phases 1-5): SecureDataFrame adoption across all plugins
- **ADR-004** (Phases 1-5): SecureData[T] generic wrapper for dicts/metadata

**Total Estimated Effort**: 30-40 hours (4-5 days)
- Terminology Rename (Phase 0): 12-16 hours (1.5-2 days, no deprecation shims needed)
- Container Adoption (Phases 1-6): 18-24 hours (2.5-3 days, clean migration)

**Risk Level**: MEDIUM (ADR-003/004), LOW (Rename)
**Confidence**: HIGH
**Approach**: Pre-1.0 fix-on-fail (no backward compatibility, breaking changes acceptable)

---

## Overview

This migration implements **universal adoption** of the ADR-002-A Trusted Container Model across the entire Elspeth codebase, with **terminology standardization** for broader industry applicability.

### Two-Phase Approach (INTEGRATED)

**Phase 0: Terminology Rename** (12-16 hours, 1.5-2 days)
- Rename `ClassifiedDataFrame` → `SecureDataFrame`
- Rename `.classification` → `.security_level` (aligns with existing 529 uses of `security_level`)
- Update all documentation for universal applicability (removes government-specific connotations)
- **Pre-1.0 Approach**: Clean cut-over, no deprecation shims (fix-on-fail)
- **Why First**: ADR-003/004 implementation uses correct terminology from day one

**Phases 1-6: Container Adoption** (18-24 hours, 2.5-3 days)
- Migrate all datasources, orchestrators, runners to use `SecureDataFrame`
- Create generic `SecureData[T]` wrapper for dicts, metadata, middleware integration
- **Pre-1.0 Approach**: Direct migration, breaking changes acceptable
- **Why After Rename**: Clean implementation without terminology churn

### What We're Doing

**Terminology Rename** (Phase 0):
- `ClassifiedDataFrame` → `SecureDataFrame` (universal terminology)
- `.classification` field → `.security_level` field (semantic alignment with codebase)
- `classified_material` middleware → `sensitive_material` middleware (content detection clarity)

**ADR-003** (Phases 1-5): Migrate all datasources, orchestrators, and runners to use `SecureDataFrame`

**ADR-004** (Phases 1-5): Create generic `SecureData[T]` wrapper for dicts, metadata, and middleware integration

### Why This Sequencing

1. **ADR-002-A is complete** - 72 passing tests, CVE fixed, performance validated
2. **Terminology first** - Clean slate, no renaming during functional migration
3. **Semantic alignment** - Codebase already uses `security_level` 529 times vs. `classification` 118 times
4. **Universal applicability** - "Secure data" works for healthcare, finance, enterprise, research (not just government)
5. **Type safety** - Prevent security level laundering at compile time

---

## Documentation Structure

This folder contains all planning artifacts for the ADR-003+004 migration:

### 📋 Planning & Assessment

**`RENAMING_ASSESSMENT.md`** (PHASE 0 - READ FIRST FOR TERMINOLOGY)
- Why "Secure" vs "Classified" (universal applicability)
- Complete renaming map (86 files, 1,450 occurrences)
- 3-phase rename strategy (Code → Tests → Documentation)
- Effort: 12-16 hours, LOW complexity, VERY HIGH confidence
- Breaking changes and deprecation strategy
- Sequencing rationale: Rename BEFORE ADR-003/004

**`MIGRATION_COMPLEXITY_ASSESSMENT.md`** (PHASES 1-5 - ADR-003/004 PLAN)
- Executive summary with effort estimates (18-24 hours)
- Current state analysis (what's done, what's not)
- Complete migration scope (critical/medium/low impact files)
- 5-phase migration strategy (Infrastructure → Datasources → Core → Middleware → Plugins → Verification)
- Risk assessment with mitigation strategies
- Success criteria and exit conditions
- **Note**: References `SecureDataFrame` (assumes Phase 0 complete)

**`README_MIGRATION_ANALYSIS.md`** (QUICK REFERENCE)
- Overview and quick facts
- Document guide (which to read when)
- Key decisions with recommendations
- Code examples (before/after)
- Testing strategy
- 5-phase migration summary

**`MIGRATION_SUMMARY.txt`** (AT-A-GLANCE VIEW)
- All 70 plugins inventoried
- 5 critical data flow paths
- New infrastructure needed
- Interface changes required
- Effort/risk assessment table
- Decision points with recommendations

### 🔍 Technical Deep Dives

**`plugin_migration_analysis.md`** (DETAILED TECHNICAL SPEC - 600+ lines)
- Complete plugin inventory with file paths and line numbers
- Current vs target behavior specifications
- Data passing patterns (6-tier architecture)
- Interface changes before/after
- Design decisions with rationale
- Testing requirements per component

**`DATA_FLOW_DIAGRAM.txt`** (VISUAL REFERENCE)
- Tier-by-tier architecture diagrams (Tier 0-3)
- Data structure transformations at each boundary
- Middleware unwrap/wrap options
- Classification uplifting flow (high water mark principle)
- Detailed row processing steps

---

## Quick Start Guide

### For Implementers (Starting the Migration)

**Phase 0: Terminology Rename** (12-16 hours)
1. **Read**: `RENAMING_ASSESSMENT.md` (terminology change rationale and plan)
2. **Execute**: Follow 3-phase rename strategy (Code → Tests → Docs)
3. **Verify**: All tests passing, MyPy clean, documentation updated
4. **Checkpoint**: `SecureDataFrame` exists, all references updated

**Phases 1-5: Container Adoption** (18-24 hours)
1. **Read**: `MIGRATION_COMPLEXITY_ASSESSMENT.md` (full migration plan)
2. **Reference**: `plugin_migration_analysis.md` (technical specs)
3. **Visualize**: `DATA_FLOW_DIAGRAM.txt` (see data flow)
4. **Execute**: Follow 5-phase strategy (Infrastructure → Datasources → Core → Middleware → Plugins → Verification)
5. **Track**: Use TodoWrite tool to track progress through phases

### For Reviewers (Code Review)

**Phase 0 Review** (Terminology):
1. **Rationale**: `RENAMING_ASSESSMENT.md` (why "Secure" vs "Classified")
2. **Scope**: 86 files, 1,450 occurrences
3. **Verify**: Deprecation shims in place, configs updated, tests passing

**Phases 1-5 Review** (Container Adoption):
1. **Context**: `README_MIGRATION_ANALYSIS.md` (quick overview)
2. **Scope**: `MIGRATION_SUMMARY.txt` (what's changing)
3. **Details**: `MIGRATION_COMPLEXITY_ASSESSMENT.md` (risk assessment, success criteria)
4. **Verify**: Each phase's exit criteria (100% tests passing, MyPy clean, etc.)

### For Approvers (Management/Architecture Review)

1. **Executive Summary**: This README (Overview + Timeline sections)
2. **Terminology Rationale**: `RENAMING_ASSESSMENT.md` (universal applicability)
3. **Container Migration**: `MIGRATION_COMPLEXITY_ASSESSMENT.md` (effort, risk, success criteria)
4. **Total Effort Estimate**: 30-40 hours (4-5 days), MEDIUM complexity, HIGH confidence
4. **Dependencies**: ADR-002-A complete (ready to merge), no external blockers

---

## Integrated Migration Timeline

### Complete Migration: 6 Phases (30-40 hours, 4-5 days)

```
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 0: Terminology Rename (12-16 hours, 1.5-2 days)          │
│   Sub-phases: Core Code → Tests → Documentation                │
│   Output: SecureDataFrame, .security_level, sensitive_material │
│   Branch: refactor/terminology-secure-data                     │
├─────────────────────────────────────────────────────────────────┤
│ Checkpoint: Merge Phase 0, create ADR-003/004 branch           │
├─────────────────────────────────────────────────────────────────┤
│ PHASE 1: Infrastructure (2-3 hours)                            │
│   Output: SecureData[T] generic wrapper                        │
├─────────────────────────────────────────────────────────────────┤
│ PHASE 2: Datasource Migration (2 hours)                        │
│   Output: 4 datasources return SecureDataFrame                 │
├─────────────────────────────────────────────────────────────────┤
│ PHASE 3: Orchestrator & Runner Core (3-4 hours)                │
│   Output: SecureDataFrame propagates through pipeline          │
├─────────────────────────────────────────────────────────────────┤
│ PHASE 4: Middleware Integration (3-4 hours)                    │
│   Output: Middleware handles SecureData[dict]                  │
├─────────────────────────────────────────────────────────────────┤
│ PHASE 5: Row Plugins & Aggregators (2-3 hours)                 │
│   Output: All plugins compatible with secure containers        │
├─────────────────────────────────────────────────────────────────┤
│ PHASE 6: Verification & Documentation (1-2 hours)              │
│   Output: ADR-003, ADR-004, updated guides, zero regressions   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase-by-Phase Breakdown

### Phase 0: Terminology Rename (12-16 hours) 🔄

**Objective**: Standardize terminology for universal applicability

**Branch**: `refactor/terminology-secure-data`

**Sub-Phase 0.1: Core Code** (4-5 hours)
- Rename module: `classified_data.py` → `secure_data.py`
- Rename class: `ClassifiedDataFrame` → `SecureDataFrame`
- Rename field: `.classification` → `.security_level`
- Rename methods: `with_uplifted_classification()` → `with_uplifted_security_level()`
- Rename middleware: `classified_material` → `sensitive_material`
- Update all imports across codebase
- **Exit Criteria**: MyPy clean, Ruff clean (tests will fail - expected)

**Sub-Phase 0.2: Tests** (3-4 hours)
- Update 14 test files, 307 occurrences
- Rename test data files
- Update variable names (`classified_df` → `secure_df`)
- **Exit Criteria**: All 800+ tests passing (100%)

**Sub-Phase 0.3: Documentation** (4-6 hours)
- Update plugin development guide (69 occurrences)
- Update architecture docs (~200 occurrences)
- Update examples & guides (~100 occurrences)
- Add editorial notes to ADRs (preserve historical context)
- **Exit Criteria**: All current docs use "secure data" terminology

**Deliverables**:
- ✅ `SecureDataFrame` class with all methods
- ✅ `.security_level` field (aligned with codebase standard)
- ✅ `SensitiveMaterialMiddleware` (content detection)
- ✅ All documentation updated
- ✅ All config files updated (`classified_material` → `sensitive_material`)

**Pre-1.0 Note**: No deprecation shims - clean breaking change (fix-on-fail approach)

**See**: `RENAMING_ASSESSMENT.md` for full details

---

### Phase 1: Infrastructure (2-3 hours) 🏗️

**Objective**: Build `SecureData[T]` generic wrapper and utilities

**Branch**: `feature/adr-003-004-secure-containers`

- Create `SecureData[T]` generic class (mirrors `SecureDataFrame` for any type T)
- Add utility functions: `unwrap(secure: SecureData[T]) -> T` (public, safe extraction)
- Add `SecureDataFrame.create_secure_dict(data: dict) -> SecureData[dict]` factory method
- **NO public `wrap()` helper** - would allow classification laundering (CVE-ADR-002-A-003)
- Write invariant tests (5+ core properties: immutability, uplifting, factory safety)
- **Exit Criteria**: All new tests passing, MyPy clean, no wrap() in public API

---

### Phase 2: Datasource Migration (2 hours) 📊

**Objective**: Datasources return `SecureDataFrame`

- 4 datasources: `_csv_base.py`, `csv_local.py`, `csv_blob.py`, `blob.py`
- Change: `return df` → `return SecureDataFrame.create_from_datasource(df, self.security_level)`
- Update `DataSource` protocol signature
- Migrate datasource tests
- **Exit Criteria**: All datasource tests passing, constructor protection verified

---

### Phase 3: Orchestrator & Runner Core (3-4 hours) ⚙️

**Objective**: Propagate `SecureDataFrame` through execution pipeline

- Orchestrator accepts `SecureDataFrame` from datasources
- Runner processes `SecureDataFrame.data` for row iteration
- Suite runner passes `SecureDataFrame` between experiments
- **Exit Criteria**: Integration tests passing, security level uplifts correctly

---

### Phase 4: Middleware Integration (3-4 hours) 🔌

**Objective**: Middleware handles `SecureData[dict]`

- Wrap row context dicts in `SecureData[dict]`
- Update middleware protocol to accept `SecureData[dict]`
- 6 middleware plugins: unwrap → process → wrap with uplifting
- **Exit Criteria**: All middleware tests passing, uplifting preserves high water mark

---

### Phase 5: Row Plugins & Aggregators (2-3 hours) 🧩

**Objective**: All plugins compatible with secure containers

- Update row plugin signatures (if needed)
- Verify aggregator compatibility
- Test baseline plugins with `SecureDataFrame`
- **Exit Criteria**: All plugins compatible, tests passing

---

### Phase 6: Verification & Documentation (1-2 hours) ✅

**Objective**: Confirm end-to-end security level propagation

- Run full test suite (800+ tests)
- Sample suite with security level debug logging
- Update plugin development guide
- Create ADR-003 and ADR-004 documents
- **Exit Criteria**: Zero regressions, MyPy clean, Ruff clean, docs complete

---

## Critical Files Inventory

### Phase 0: Terminology Rename (86 files, 1,450 occurrences)

| Category | Files | Examples | Change |
|----------|-------|----------|--------|
| **Core Module** | 1 | `classified_data.py` | → `secure_data.py` |
| **Core Class** | 14 source + 14 test | `ClassifiedDataFrame` | → `SecureDataFrame` |
| **Field Name** | 14 source + 14 test | `.classification` | → `.security_level` |
| **Middleware** | 1 + tests | `classified_material.py` | → `sensitive_material.py` |
| **Documentation** | 50 files | "classified data" | → "secure data" |

### Phases 1-6: Container Adoption

#### Critical Path (MUST CHANGE)

| File | Current State | Target State | Phase |
|------|---------------|--------------|-------|
| `src/elspeth/core/security/secure_data.py` | `SecureDataFrame` only | Add `SecureData[T]` generic | Phase 1 |
| `src/elspeth/plugins/nodes/sources/_csv_base.py` | Returns `pd.DataFrame` | Returns `SecureDataFrame` | Phase 2 |
| `src/elspeth/plugins/nodes/sources/blob.py` | Returns `pd.DataFrame` | Returns `SecureDataFrame` | Phase 2 |
| `src/elspeth/core/orchestrator.py` | Accepts `pd.DataFrame` | Accepts `SecureDataFrame` | Phase 3 |
| `src/elspeth/core/experiments/runner.py` | Accepts `pd.DataFrame` | Accepts `SecureDataFrame` | Phase 3 |
| `src/elspeth/core/experiments/suite_runner.py` | Passes plain DataFrames | Passes `SecureDataFrame` | Phase 3 |

#### Medium Impact (SHOULD CHANGE)

| Component | Files | Change | Phase |
|-----------|-------|--------|-------|
| Generic Wrapper | `secure_data.py` | Add `SecureData[T]` class | Phase 1 |
| LLM Middleware | 6 files in `transforms/llm/middleware/` | Unwrap/wrap `SecureData[dict]` | Phase 4 |
| Row Plugins | ~10 files in `plugins/experiments/row/` | Accept `SecureData[dict]` | Phase 5 |

#### Low Impact (VERIFY COMPATIBILITY)

| Component | Files | Action | Phase |
|-----------|-------|--------|-------|
| Sinks | 16 sink implementations | Verify compatibility | Phase 6 |
| Aggregators | 6 aggregator plugins | Test with secure data | Phase 5 |
| Baseline Plugins | 9 baseline comparison plugins | Verify no changes needed | Phase 5 |

---

## Key Design Decisions

### ✅ Decision 1: Rename "Classified" → "Secure" First (Phase 0)

**Rationale**: Terminology change BEFORE functional migration

**Benefits**:
- ADR-003/004 implementation uses correct terminology from day one
- Clean separation: terminology change (mechanical) vs. functional migration (architectural)
- Semantic alignment: Codebase already uses `security_level` 529 times vs. `classification` 118 times
- Universal applicability: "Secure data" works for healthcare, finance, enterprise, not just government

**Impact**: 86 files, 1,450 occurrences, 12-16 hours

**See**: `RENAMING_ASSESSMENT.md` for full rationale

---

### ✅ Decision 2: Create SecureData[T] Generic (Phase 1)

**Rationale**: `SecureDataFrame` only handles DataFrames, but we need security level propagation for dicts (row context, metadata, aggregation results).

**Pattern**:
```python
@dataclass(frozen=True)
class SecureData[T]:
    data: T
    security_level: SecurityLevel

    def with_uplifted_security_level(self, new_level: SecurityLevel) -> SecureData[T]:
        return SecureData(data=self.data, security_level=max(self.security_level, new_level))
```

**Benefits**: Type-safe security level propagation for ANY data type, not just DataFrames.

---

### ✅ Decision 3: Direct Middleware Migration (Pre-1.0 Clean Break - Phase 4)

**Rationale**: Pre-1.0 allows clean migration without backward compatibility. Migrate middleware directly to `SecureData[dict]` protocol.

**Pattern**:
```python
# Direct migration (pre-1.0):
secure_context = SecureData.wrap(context, security_level)
secure_response = middleware_chain(secure_context)  # Middleware handles SecureData directly
```

**Benefits**: Simpler code (no unwrap/wrap shims), cleaner architecture, faster execution.

---

### ✅ Decision 4: In-Place DataFrame Mutation Allowed

**Rationale**: `SecureDataFrame.data` is mutable (pandas DataFrame), enabling in-place transformations without copying large datasets.

**Pattern**:
```python
# Plugin can mutate .data in-place:
secure_df.data['processed'] = transform(secure_df.data['input'])

# Then uplift security level:
result = secure_df.with_uplifted_security_level(plugin.get_security_level())
```

**Security**: Security level is immutable (frozen dataclass), only data mutations allowed.

**Benefits**: Performance (no DataFrame copies), ergonomic plugin API.

---

## Success Criteria

### Phase 0: Terminology Rename (Must-Have)
- ✅ All source code uses `SecureDataFrame` / `SecureData[T]`
- ✅ All field names use `.security_level`
- ✅ All method names updated (`with_uplifted_security_level`)
- ✅ All 800+ tests passing (100%)
- ✅ MyPy clean, Ruff clean
- ✅ **No "ClassifiedDataFrame" references anywhere** (clean cut-over, pre-1.0)
- ✅ All current documentation updated
- ✅ All config files updated (`classified_material` → `sensitive_material`)
- ✅ Sample suite runs with new terminology

### Phases 1-6: Container Adoption (Must-Have)
- ✅ All 4 datasources return `SecureDataFrame`
- ✅ Orchestrator and runner propagate `SecureDataFrame`
- ✅ Security level uplifts at each boundary (datasource → runner → middleware)
- ✅ All 800+ tests passing (zero regressions after rename)
- ✅ MyPy clean, Ruff clean
- ✅ End-to-end suite test with security level logging

### Should-Have (Quality)
- ✅ Middleware integrates `SecureData[dict]` (direct migration, no unwrap shims)
- ✅ Row plugins compatible
- ✅ Performance validation (<0.1ms overhead per suite)
- ✅ Plugin development guide updated (uses `SecureDataFrame` examples)
- ✅ ADR-003 and ADR-004 created in `docs/architecture/decisions/`

### Nice-to-Have (Future)
- ⭕ Aggregators explicitly use `SecureData[dict]`
- ⭕ Baseline plugins handle security levels
- ⭕ Security level audit logging (track uplifts across pipeline)

---

## Risk Mitigation

### Critical Risk 1: Breaking Middleware Configurations (Phase 0)

**Impact**: Configs referencing `classified_material` middleware will fail
**Probability**: HIGH (pre-1.0, no auto-mapping)

**Mitigation**:
1. **Update all in-tree configs**: `config/sample_suite/**/*.yaml`
2. **Search codebase**: `grep -r "classified_material" config/` to find all references
3. **Documentation**: Breaking change in CHANGELOG
4. **Pre-1.0 Approach**: Fail fast with clear error message if old name used

**Fallback**: Fix on fail - update configs when errors occur (acceptable pre-1.0)

---

### Critical Risk 2: Breaking Middleware Protocol (Phase 4)

**Impact**: All 6 middleware plugins fail
**Probability**: MEDIUM (protocol changes are risky)

**Mitigation**:
1. **Direct migration**: Update all 6 middleware plugins to accept `SecureData[dict]`
2. **Test after each**: Update middleware one at a time, run tests immediately
3. **Pre-1.0 Approach**: No unwrap shims, cleaner code

**Fallback**: Revert Phase 4 if tests fail, Phases 0-3 still deliver value

**Test Coverage**: Each middleware has integration tests, full suite test validates end-to-end.

---

### Critical Risk 3: Type System Complexity (Phase 1)

**Impact**: MyPy errors with `SecureData[T]` generics
**Probability**: MEDIUM (Python generics can be tricky)

**Mitigation**:
1. **Comprehensive annotations**: All `SecureData[T]` methods fully typed
2. **Test type checker**: Run `mypy --strict` on new code before integration
3. **Incremental typing**: Use `typing.cast` where needed, fix incrementally
4. **Examples**: Provide clear usage examples in docstrings

**Test Coverage**: MyPy clean is exit criteria for every phase.

---

## Testing Strategy

### Phase 0: Rename Testing
- **After code rename**: Tests will fail (expected) - 14 test files need updating
- **After test rename**: All 800+ tests must pass (100%)
- **Verification**: MyPy clean, Ruff clean, no "ClassifiedDataFrame" references

### Phase 1: Invariant Tests (SecureData[T])
- **5+ core properties**: Constructor protection, uplifting, immutability, unwrap/wrap round-trip
- **Pattern**: Test-first (RED → GREEN → REFACTOR)
- **Coverage**: Minimum 90% on new `SecureData[T]` code

### Phases 2-5: Integration Tests
- **Datasource → Orchestrator → Runner**: End-to-end with `SecureDataFrame`
- **Middleware chain**: Security level propagates correctly
- **Suite runner**: Security level uplifts between experiments
- **Pattern**: Modify existing integration tests to verify security level propagation

### Phase 6: Regression Tests
- **Full suite**: All 800+ tests must pass (zero regressions)
- **Sample suite**: Run with security level debug logging enabled
- **Performance**: <0.1ms overhead per suite (ADR-002-A benchmark baseline)

---

## Dependencies & Prerequisites

### ✅ Ready (Unblocked)
- ADR-002-A Trusted Container Model complete (72 passing tests)
- `ClassifiedDataFrame` fully implemented with constructor protection
- Comprehensive test suite exists (800+ tests)
- Clear migration path documented (rename + adoption)

### ⭕ Before Starting Phase 0
- Merge current branch (`feature/adr-002-security-enforcement`)
- Create rename branch (`refactor/terminology-secure-data`)
- Team approval of terminology change

### ⭕ Before Starting Phases 1-6
- Phase 0 complete (`SecureDataFrame` exists, all tests passing)
- Merge rename branch
- Create ADR-003/004 branch (`feature/adr-003-004-secure-containers`)

### ❌ No External Dependencies
All work is internal to Elspeth codebase.

---

## Timeline & Effort

**Total Estimated Effort**: 25-35 hours (3-4 days) - **Reduced from 30-40 hours** (pre-1.0, no backward compatibility)

**Breakdown by Migration**:
- **Phase 0: Terminology Rename**: 10-14 hours (1-2 days, no deprecation shims)
- **Phases 1-6: Container Adoption**: 15-21 hours (2 days, clean migration)

**Detailed Phase Breakdown**:
| Phase | Hours | Complexity | Risk | Notes |
|-------|-------|------------|------|-------|
| **Phase 0: Rename** | **10-14** | **LOW** | **LOW** | **No shims, clean cut-over** |
| - Sub-phase 0.1: Core Code | 3-4 | LOW | LOW | No deprecation shims needed |
| - Sub-phase 0.2: Tests | 3-4 | LOW | LOW | Clean rename, no compat tests |
| - Sub-phase 0.3: Docs + Configs | 3-5 | MEDIUM | LOW | Update configs directly |
| **Checkpoint: Merge Phase 0** | - | - | - | - |
| **Phase 1: Infrastructure** | **2-3** | **MEDIUM** | **MEDIUM** | SecureData[T] generic |
| **Phase 2: Datasources** | **1-2** | **LOW** | **LOW** | 4 files, simple change |
| **Phase 3: Core Engine** | **2-3** | **HIGH** | **MEDIUM** | Orchestrator/runner |
| **Phase 4: Middleware** | **2-3** | **HIGH** | **MEDIUM** | **Direct migration, no unwrap shims** |
| **Phase 5: Plugins** | **2-3** | **MEDIUM** | **LOW** | Row/aggregator/baseline |
| **Phase 6: Verification** | **1-2** | **LOW** | **LOW** | Tests/docs/ADRs |

**Pre-1.0 Simplifications**:
- ✅ No deprecation warnings to write/test
- ✅ No backward compatibility shims to maintain
- ✅ No unwrap/rewrap compatibility layers
- ✅ Simpler, cleaner code
- ✅ Faster execution (less code to write)

---

## Next Steps

### Immediate (Pre-Migration)

1. ✅ **Planning complete** - All documentation in place (rename + adoption)
2. ⭕ **Review with team** - Approve integrated migration plan (6 phases, 30-40 hours)
3. ⭕ **Approve terminology change** - "Secure" vs "Classified" for universal applicability
4. ⭕ **Merge ADR-002-A** - Current branch (`feature/adr-002-security-enforcement`) ready

### Phase 0: Terminology Rename (12-16 hours, 1.5-2 days)

5. ⭕ **Create rename branch** - `refactor/terminology-secure-data`
6. ⭕ **Execute Sub-phase 0.1** - Core code (4-5 hours)
7. ⭕ **Execute Sub-phase 0.2** - Tests (3-4 hours)
8. ⭕ **Execute Sub-phase 0.3** - Documentation (4-6 hours)
9. ⭕ **Merge rename branch** - All tests passing, `SecureDataFrame` exists

**Checkpoint**: `SecureDataFrame` available, `.security_level` field, all docs updated

### Phases 1-6: Container Adoption (18-24 hours, 2-3 days)

10. ⭕ **Create ADR-003/004 branch** - `feature/adr-003-004-secure-containers`
11. ⭕ **Execute Phase 1** - Infrastructure (`SecureData[T]` generic, 2-3 hours)
12. ⭕ **Execute Phase 2** - Datasources (4 files, 2 hours)
13. ⭕ **Execute Phase 3** - Core engine (orchestrator/runner, 3-4 hours)
14. ⭕ **Execute Phase 4** - Middleware (6 plugins, 3-4 hours)
15. ⭕ **Execute Phase 5** - Plugins (row/aggregator/baseline, 2-3 hours)
16. ⭕ **Execute Phase 6** - Verification (tests/docs/ADRs, 1-2 hours)
17. ⭕ **Merge ADR-003/004 branch** - Zero regressions, all success criteria met

### Post-Migration

18. ⭕ **Create ADRs** - ADR-003 and ADR-004 in `docs/architecture/decisions/`
19. ⭕ **Update CHANGELOG** - Breaking changes, deprecation warnings
20. ⭕ **Deprecation timeline** - Plan for removing shims (next major version)

---

## References

### Internal Documentation
- **ADR-002**: Multi-Level Security Enforcement (`docs/architecture/decisions/002-security-architecture.md`)
- **ADR-002-A**: Trusted Container Model (`docs/architecture/decisions/002-a-trusted-container-model.md`)
- **Plugin Development Guide**: ADR-002-A patterns (`docs/guides/plugin-development-adr002a.md`)
- **Threat Model**: ADR-002 security controls (`docs/security/adr-002-threat-model.md`)

### Migration Documentation
- **Terminology Rename**: `RENAMING_ASSESSMENT.md` (this folder)
- **Container Adoption**: `MIGRATION_COMPLEXITY_ASSESSMENT.md` (this folder)
- **Technical Analysis**: `plugin_migration_analysis.md` (this folder)
- **Visual Reference**: `DATA_FLOW_DIAGRAM.txt` (this folder)
- **Quick Summary**: `MIGRATION_SUMMARY.txt` (this folder)

### Code References (After Phase 0)
- **SecureDataFrame**: `src/elspeth/core/security/secure_data.py` (renamed from `classified_data.py`)
- **Datasources**: `src/elspeth/plugins/nodes/sources/_csv_base.py`
- **Orchestrator**: `src/elspeth/core/orchestrator.py`
- **Runner**: `src/elspeth/core/experiments/runner.py`
- **Suite Runner**: `src/elspeth/core/experiments/suite_runner.py`
- **Middleware**: `src/elspeth/plugins/nodes/transforms/llm/middleware/sensitive_material.py` (renamed)

---

## Confidence & Approval

**Confidence Level**: **HIGH** (based on comprehensive codebase exploration)

**Why High Confidence**:
1. ✅ Similar pattern to ADR-002-A (successful implementation, zero regressions)
2. ✅ Clear migration path with 5 phases
3. ✅ Comprehensive safety net (800+ tests)
4. ✅ Well-defined interfaces (DataSource protocol, runner signatures)
5. ✅ Risk mitigation strategies in place

**Approval Required From**:
- [ ] Technical Lead (architecture approval)
- [ ] Security Team (ADR-003+004 alignment with ADR-002)
- [ ] Development Team (effort estimate, timeline)

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

**Migration Prepared By**: Claude Code
**Planning Date**: 2025-10-25
**Status**: Ready for Execution
**Version**: 1.0
