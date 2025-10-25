# Integrated Migration Roadmap: Secure Data Containers

**Total Duration**: 35-47 hours (5-6 days)
**Phases**: 7 (Phase 0: Rename + Phases 1-6: Adoption + Phase 1.5: BasePlugin Inheritance)
**Status**: Planning Complete - Ready for Execution (UPDATED with ADR-004 "Security Bones")

---

## Migration Overview

This roadmap integrates **two migrations** into a single cohesive plan:

1. **Phase 0: Terminology Rename** (12-16 hours) - "Classified" → "Secure" for universal applicability
2. **Phases 1-6: Container Adoption** (23-31 hours) - Universal adoption of secure containers across all plugins
   - **NEW: Phase 1.5** (3-5 hours) - BasePlugin inheritance migration (CRITICAL for ADR-002 validation, uses "Security Bones" design from ADR-004)

**Why This Sequence**: Rename FIRST ensures ADR-003/004 implementation uses correct terminology from day one, avoiding double-work.

---

## Complete Timeline

```
┌─────────────────────────────────────────────────────────────────────┐
│  PRELIMINARY: Merge ADR-002-A Branch                                │
│  Branch: feature/adr-002-security-enforcement                       │
│  Action: Merge to main (ClassifiedDataFrame implementation ready)  │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 0: TERMINOLOGY RENAME (12-16 hours, 1.5-2 days)             │
│  Branch: refactor/terminology-secure-data                          │
├─────────────────────────────────────────────────────────────────────┤
│  Sub-Phase 0.1: Core Code Rename (4-5 hours)                       │
│    - Module: classified_data.py → secure_data.py                   │
│    - Class: ClassifiedDataFrame → SecureDataFrame                  │
│    - Field: .classification → .security_level                      │
│    - Methods: with_uplifted_classification() →                     │
│               with_uplifted_security_level()                        │
│    - Middleware: classified_material → sensitive_material           │
│    - Update all imports across 14 source files                     │
│    Exit: MyPy clean, Ruff clean (tests failing - expected)         │
├─────────────────────────────────────────────────────────────────────┤
│  Sub-Phase 0.2: Test Rename (3-4 hours)                            │
│    - Update 14 test files, 307 occurrences                         │
│    - Rename test data files (classification_bypass.yaml, etc.)     │
│    - Update variable names (classified_df → secure_df)             │
│    Exit: All 800+ tests passing (100%)                             │
├─────────────────────────────────────────────────────────────────────┤
│  Sub-Phase 0.3: Documentation Update (4-6 hours)                   │
│    - Update plugin development guide (69 occurrences)              │
│    - Update architecture docs (~200 occurrences)                   │
│    - Update examples & guides (~100 occurrences)                   │
│    - Add editorial notes to ADRs (preserve historical context)     │
│    - Update migration planning docs (~300 occurrences)             │
│    Exit: All current documentation uses "secure data" terminology  │
├─────────────────────────────────────────────────────────────────────┤
│  PHASE 0 DELIVERABLES:                                             │
│    ✅ SecureDataFrame class with all methods                       │
│    ✅ .security_level field (aligned with codebase)                │
│    ✅ SensitiveMaterialMiddleware (content detection)              │
│    ✅ All documentation updated                                    │
│    ✅ All tests passing, MyPy clean, Ruff clean                    │
│    ❌ NO backward compatibility shims (Pre-1.0 clean cut-over)    │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│  CHECKPOINT: Merge Phase 0                                          │
│  Action: Merge refactor/terminology-secure-data → main             │
│  Verify: SecureDataFrame exists, all references updated            │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│  PHASES 1-6: CONTAINER ADOPTION (24-32 hours, 3-4 days)            │
│  Branch: feature/adr-003-004-secure-containers                     │
├─────────────────────────────────────────────────────────────────────┤
│  PHASE 1: Infrastructure (2-3 hours)                               │
│    - Create SecureData[T] generic wrapper                          │
│    - Add utility functions (unwrap, safe factory)                  │
│    - Write invariant tests (5+ core properties)                    │
│    Exit: All new tests passing, MyPy clean                         │
├─────────────────────────────────────────────────────────────────────┤
│  PHASE 1.5: BasePlugin Inheritance Migration (3-5 hours) 🚨 NEW    │
│    - Step 0: Create BasePlugin ABC + Remove old Protocol (FIRST!)  │
│    - Step 0: Update all imports (protocols → plugin module)        │
│    - Step 1-4: Add BasePlugin to 26 plugin inheritance chains      │
│    - Step 1-4: Update __init__ to call super().__init__(...)       │
│    - CRITICAL: Enables ADR-002 validation (nominal typing)         │
│    - "Security Bones" design: inherit methods, don't implement     │
│    Exit: Protocol removed, validation runs, isinstance uses ABC    │
├─────────────────────────────────────────────────────────────────────┤
│  PHASE 2: Datasource Migration (2 hours)                           │
│    - 4 datasources return SecureDataFrame                          │
│    - Update DataSource protocol signature                          │
│    - Migrate datasource tests                                      │
│    Exit: All datasource tests passing, constructor protection OK   │
├─────────────────────────────────────────────────────────────────────┤
│  PHASE 3: Orchestrator & Runner Core (3-4 hours)                   │
│    - Orchestrator accepts SecureDataFrame                          │
│    - Runner processes SecureDataFrame.data                         │
│    - Suite runner passes SecureDataFrame between experiments       │
│    Exit: Integration tests passing, security level uplifts         │
├─────────────────────────────────────────────────────────────────────┤
│  PHASE 4: Middleware Integration (3-4 hours)                       │
│    - Wrap row context dicts in SecureData[dict]                    │
│    - Update middleware protocol to accept SecureData[dict]         │
│    - 6 middleware plugins: unwrap → process → wrap with uplifting  │
│    Exit: All middleware tests passing, uplifting preserves high    │
│          water mark                                                 │
├─────────────────────────────────────────────────────────────────────┤
│  PHASE 5: Row Plugins & Aggregators (2-3 hours)                    │
│    - Update row plugin signatures (if needed)                      │
│    - Verify aggregator compatibility                               │
│    - Test baseline plugins with SecureDataFrame                    │
│    Exit: All plugins compatible, tests passing                     │
├─────────────────────────────────────────────────────────────────────┤
│  PHASE 6: Verification & Documentation (1-2 hours)                 │
│    - Run full test suite (800+ tests)                              │
│    - Sample suite with security level debug logging                │
│    - Update plugin development guide                               │
│    - Create ADR-003 and ADR-004 documents                          │
│    Exit: Zero regressions, MyPy clean, Ruff clean, docs complete   │
├─────────────────────────────────────────────────────────────────────┤
│  PHASES 1-6 DELIVERABLES:                                          │
│    ✅ SecureData[T] generic wrapper for any data type              │
│    ✅ All datasources return SecureDataFrame                       │
│    ✅ Security level propagates through entire pipeline            │
│    ✅ Middleware integrates SecureData[dict]                       │
│    ✅ All plugins compatible with secure containers                │
│    ✅ ADR-003 and ADR-004 created                                  │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│  FINAL: Merge Phases 1-6                                            │
│  Action: Merge feature/adr-003-004-secure-containers → main        │
│  Verify: All success criteria met, zero regressions                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Effort Breakdown

| Phase | Sub-Phases | Hours | Complexity | Risk | Cumulative |
|-------|------------|-------|------------|------|------------|
| **Phase 0** | **Terminology Rename** | **12-16** | **LOW** | **LOW** | **12-16** |
| 0.1 | Core Code | 4-5 | LOW | LOW | 4-5 |
| 0.2 | Tests | 3-4 | LOW | LOW | 7-9 |
| 0.3 | Documentation | 4-6 | MEDIUM | LOW | 11-15 |
| **Checkpoint** | **Merge Phase 0** | **-** | **-** | **-** | **-** |
| **Phase 1** | **Infrastructure** | **2-3** | **MEDIUM** | **MEDIUM** | **14-19** |
| **Phase 1.5** | **BasePlugin Inheritance** | **3-5** | **MEDIUM** | **HIGH** | **17-24** |
| **Phase 2** | **Datasources** | **2** | **LOW** | **LOW** | **19-26** |
| **Phase 3** | **Core Engine** | **3-4** | **HIGH** | **MEDIUM** | **22-30** |
| **Phase 4** | **Middleware** | **3-4** | **HIGH** | **MEDIUM** | **25-34** |
| **Phase 5** | **Plugins** | **2-3** | **MEDIUM** | **LOW** | **27-37** |
| **Phase 6** | **Verification** | **1-2** | **LOW** | **LOW** | **28-39** |
| **Total** | **7 Phases** | **35-47** | **MEDIUM** | **MEDIUM** | **35-47** |

**Conservative Timeline**: 5-6 days with rigorous testing at each phase

---

## Success Criteria by Phase

### Phase 0: Terminology Rename
- ✅ All source code uses `SecureDataFrame` / `SecureData[T]`
- ✅ All field names use `.security_level`
- ✅ All 800+ tests passing (100%)
- ✅ MyPy clean, Ruff clean
- ✅ All current documentation updated
- ✅ **No backward compatibility** (Pre-1.0 clean cut-over)

### Phases 1-6: Container Adoption
- ✅ All 4 datasources return `SecureDataFrame`
- ✅ Security level uplifts at each boundary
- ✅ All 800+ tests passing (zero regressions after Phase 0)
- ✅ Middleware integrates `SecureData[dict]`
- ✅ All plugins compatible
- ✅ ADR-003 and ADR-004 created

---

## Risk Matrix

| Phase | Risk Type | Impact | Probability | Mitigation | Fallback |
|-------|-----------|--------|-------------|------------|----------|
| **Phase 0** | Config breaking | MEDIUM | MEDIUM | Update all in-tree configs, fail-fast errors | Clear error messages in CHANGELOG |
| **Phase 1** | Type complexity | MEDIUM | MEDIUM | Comprehensive typing, examples | Use typing.cast, fix incrementally |
| **Phase 3** | Core integration | HIGH | MEDIUM | Thorough testing, incremental changes | Rollback, defer |
| **Phase 4** | Middleware protocol | HIGH | MEDIUM | Direct migration, no unwrap shims | Defer Phase 4, Phases 0-3 deliver value |

---

## Branch Strategy

```
main
 │
 ├─ feature/adr-002-security-enforcement (MERGE FIRST)
 │   └─ ClassifiedDataFrame implementation (ADR-002-A complete)
 │
 ├─ refactor/terminology-secure-data (Phase 0)
 │   ├─ Sub-phase 0.1: Core code rename
 │   ├─ Sub-phase 0.2: Test rename
 │   ├─ Sub-phase 0.3: Documentation update
 │   └─ MERGE → main
 │
 └─ feature/adr-003-004-secure-containers (Phases 1-6)
     ├─ Phase 1: Infrastructure
     ├─ Phase 2: Datasources
     ├─ Phase 3: Core engine
     ├─ Phase 4: Middleware
     ├─ Phase 5: Plugins
     ├─ Phase 6: Verification
     └─ MERGE → main
```

---

## Documentation Index

### Phase 0: Terminology Rename
- **Primary**: `RENAMING_ASSESSMENT.md` (full rename plan)
- **Why "Secure"**: Universal applicability, semantic alignment (529 uses of `security_level` vs 118 uses of `classification`)

### Phases 1-6: Container Adoption
- **Primary**: `MIGRATION_COMPLEXITY_ASSESSMENT.md` (adoption plan)
- **Technical**: `plugin_migration_analysis.md` (70-plugin inventory)
- **Visual**: `DATA_FLOW_DIAGRAM.txt` (data flow architecture)
- **Summary**: `MIGRATION_SUMMARY.txt` (quick reference)

### Master Plan
- **This Document**: `INTEGRATED_ROADMAP.md` (complete timeline)
- **Entry Point**: `README.md` (overview, quick start, approvals)

---

## Decision Log

**Decision 1: Rename BEFORE Adoption** (Option A)
- **Rationale**: ADR-003/004 uses correct terminology from day one, avoid double-work
- **Impact**: Clean separation, 2 branches instead of 1 combined
- **Alternative Rejected**: Rename DURING or AFTER adoption (more complex, docs updated twice)

**Decision 2: Terminology "Secure" vs "Classified"**
- **Rationale**: Universal applicability (healthcare, finance, enterprise), semantic alignment with existing codebase
- **Impact**: 86 files, 1,450 occurrences, 12-16 hours
- **Benefit**: "Secure data" works globally, not just government contexts

**Decision 3: Phase 0 as Separate Branch**
- **Rationale**: Mechanical rename can merge independently, provides checkpoint before functional migration
- **Impact**: Clear rollback point, simpler code review
- **Benefit**: If blocked at Phase 4, Phases 0-3 still deliver value

---

## Next Actions

### Before Starting
1. ✅ Planning complete (all documentation finalized)
2. ⭕ Team review and approval (terminology change + container adoption)
3. ⭕ Merge ADR-002-A (`feature/adr-002-security-enforcement`)

### Execute Phase 0 (12-16 hours)
4. ⭕ Create branch `refactor/terminology-secure-data`
5. ⭕ Sub-phase 0.1: Core code (4-5 hours)
6. ⭕ Sub-phase 0.2: Tests (3-4 hours)
7. ⭕ Sub-phase 0.3: Documentation (4-6 hours)
8. ⭕ Merge Phase 0 → main

### Execute Phases 1-6 (18-24 hours)
9. ⭕ Create branch `feature/adr-003-004-secure-containers`
10. ⭕ Phase 1: Infrastructure (2-3 hours)
11. ⭕ Phase 2: Datasources (2 hours)
12. ⭕ Phase 3: Core engine (3-4 hours)
13. ⭕ Phase 4: Middleware (3-4 hours)
14. ⭕ Phase 5: Plugins (2-3 hours)
15. ⭕ Phase 6: Verification (1-2 hours)
16. ⭕ Merge Phases 1-6 → main

### Post-Migration
17. ⭕ Create ADR-003 and ADR-004 documents
18. ⭕ Update CHANGELOG (document breaking changes)

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

**Roadmap Version**: 1.0
**Last Updated**: 2025-10-25
**Total Scope**: 6 phases, 30-40 hours, 4-5 days
**Confidence**: HIGH (comprehensive planning, proven methodology)
