# Implementation Roadmap: Security Architecture Completion

**Status**: Sprint 1 & 2 Complete - Sprint 3 Ready
**Date**: 2025-10-27 (Last Updated)
**Branch**: feature/adr-002-security-enforcement

## Executive Summary

**MAJOR PROGRESS**: Sprint 1 (SecureDataFrame) and Sprint 2 (CentralPluginRegistry) are **COMPLETE**.

Only **VULN-004 (Registry Enforcement)** remains to complete the security architecture.

### Current State
- ✅ **1480 tests passing** (up from 1445, +35 tests)
- ✅ **SecureDataFrame trusted container model IMPLEMENTED** (Sprint 1 - ADR-002-A)
- ✅ **CentralPluginRegistry with auto-discovery IMPLEMENTED** (Sprint 2 - ADR-003)
- ✅ **All plugins inherit from BasePlugin** (security validation enforced)
- ✅ **Security levels hard-coded in plugin code** (immutable policies)

### Implementation Status

| Sprint | Vulnerability | Status | Commit | Tests |
|--------|---------------|--------|--------|-------|
| Sprint 0 | VULN-005/006 Hotfixes | ✅ **COMPLETE** | Historical | 1445/1445 |
| Sprint 1 | VULN-001/002: SecureDataFrame | ✅ **COMPLETE** | 5ef1110 | 1445/1445 |
| Sprint 2 | VULN-003: Central Registry | ✅ **COMPLETE** | 3344cd5-0f40f82 | 1480/1480 |
| Sprint 3 | VULN-004: Registry Enforcement | ⚠️ **READY TO START** | - | - |

### Remaining Work

| Priority | Vulnerability | Scope | Estimated Effort |
|----------|---------------|-------|------------------|
| P2 | VULN-004: Configuration Override Attack | Registry-level validation enforcement | 13-18 hours (1 week) |

**Total Remaining Effort**: 13-18 hours (Sprint 3 only)

---

## Implementation Strategy

### Methodology: Test-Driven Development (TDD)

**Why TDD, Not Refactoring Methodology:**
- Building NEW capabilities (greenfield), not reducing complexity of existing code
- Refactoring methodology (`docs/refactoring/`) is for breaking down monolithic functions (complexity ≥25)
- These tasks add NEW behavior, requiring RED-GREEN-REFACTOR cycle

**Superpowers Skills to Use:**
1. `superpowers:brainstorming` - Refine designs before coding
2. `superpowers:writing-plans` - Create detailed implementation plans
3. `superpowers:test-driven-development` - Execute with test-first approach
4. `superpowers:requesting-code-review` - Validate after each major milestone

### Sprint Planning

#### Sprint 0: ✅ COMPLETE (P0 Hotfixes)
- **Status**: ✅ COMPLETE
- **Duration**: 20 minutes
- **Deliverables**: VULN-005/006 fixed, all tests passing

#### Sprint 1: ✅ COMPLETE (SecureDataFrame - P0)
- **Status**: ✅ COMPLETE (Commit: 5ef1110)
- **Duration**: Completed 2025-10-27
- **Deliverables**: VULN-001/002 resolved, ADR-002-A fully implemented
- **Key Features**:
  - SecureDataFrame trusted container with immutable security levels
  - Constructor protection (datasource-only creation)
  - Automatic uplifting (prevents downgrade attacks)
  - Runtime clearance validation (Bell-LaPadula "no read up")
  - 179 lines of convenience layer (empty, shape, columns, head, tail, etc.)
- **Tests**: 1445/1445 passing
- **See**: [VULN-001-002-classified-dataframe.md](./VULN-001-002-classified-dataframe.md)

#### Sprint 2: ✅ COMPLETE (Central Plugin Registry - P1)
- **Status**: ✅ COMPLETE (Commits: 3344cd5-0f40f82)
- **Duration**: Completed 2025-10-27
- **Deliverables**: VULN-003 resolved, ADR-003 implemented (alternative approach)
- **Key Features**:
  - CentralPluginRegistry facade with unified access
  - Automatic plugin discovery via module scanning
  - Validation baseline (EXPECTED_PLUGINS)
  - Single enforcement point for all plugin operations
  - 12 registry types consolidated
- **Tests**: 1480/1480 passing (+35 tests)
- **See**: [VULN-003-central-plugin-registry.md](./VULN-003-central-plugin-registry.md)
- **Review**: [SPRINT_2_COMPLETION_REVIEW.md](./SPRINT_2_COMPLETION_REVIEW.md)

#### Sprint 3: ⚠️ READY TO START (Registry Enforcement - P2)
- **Status**: ⚠️ READY TO START (all dependencies satisfied)
- **Duration**: 1 week (estimated 13-18 hours)
- **Deliverables**: VULN-004 resolved, configuration override attack closed
- **Phases**:
  1. Schema enforcement (reject security_level in options)
  2. Registry sanitization (strip forbidden fields)
  3. Post-creation verification (plugin.security_level == declared)
  4. Documentation & YAML cleanup
- **See**: [VULN-004-registry-enforcement.md](./VULN-004-registry-enforcement.md)

#### Sprint 4: Class Renaming (P3 - Optional)
- Duration: 1 week
- Deliverables: FEAT-001 complete, classes renamed for generic orchestration model
- See: [FEAT-001-class-renaming-orchestration.md](./FEAT-001-class-renaming-orchestration.md)

---

## Detailed Implementation Plans

Each implementation task has a dedicated document with:
- Vulnerability description and security impact
- Current state analysis
- Design decisions and API contracts
- Implementation phases with TDD approach
- Test strategy and acceptance criteria
- Risk assessment and rollback plan

### Documents

1. **[VULN-001-002: SecureDataFrame Implementation](./VULN-001-002-classified-dataframe.md)**
   - Priority: P0 (CRITICAL)
   - Effort: 60-80 hours
   - Implements ADR-002-A trusted container model
   - Adds runtime validation of data classification

2. **[VULN-003: Central Plugin Registry](./VULN-003-central-plugin-registry.md)**
   - Priority: P1 (HIGH)
   - Effort: 10-15 hours
   - Consolidates 15+ scattered registries
   - Implements ADR-003 unified architecture

3. **[VULN-004: Registry Enforcement](./VULN-004-registry-enforcement.md)**
   - Priority: P2 (MEDIUM)
   - Effort: 12-16 hours
   - Prevents configuration override attacks
   - Enforces Phase 2 immutability at registry level

4. **[FEAT-001: Class Renaming for Generic Orchestration](./FEAT-001-class-renaming-orchestration.md)**
   - Priority: P3 (NICE-TO-HAVE)
   - Effort: 8-12 hours
   - Aligns class names with sense-decide-act model
   - Removes "experiment runner" framing for generic orchestration

---

## Success Criteria

### Sprint 1 Complete (SecureDataFrame) ✅ ACHIEVED
- [x] `SecureDataFrame` class implemented with Bell-LaPadula enforcement
- [x] All datasources return classified DataFrames
- [x] Runtime validation prevents misclassified data from reaching plugins
- [x] XFAIL tests reclassified as deferred future work (documented)
- [x] No new test failures introduced (1445/1445 passing)
- **Commit**: 5ef1110

### Sprint 2 Complete (Central Registry) ✅ ACHIEVED
- [x] `CentralPluginRegistry` consolidates all plugin types (12 types)
- [x] Backward compatibility maintained via get_registry() facade pattern
- [x] Migration complete (9 files updated)
- [x] All existing tests pass (1480/1480, +35 new tests)
- [x] Documentation complete (ADR-003, CLAUDE.md, AI summaries)
- **Commits**: 3344cd5-0f40f82

### Sprint 3 Complete (Registry Enforcement) ⚠️ PENDING
- [ ] Registry validates `declared_security_level` matches plugin code
- [ ] Configuration attempts to override security_level are REJECTED
- [ ] Schema validation prevents YAML overrides
- [ ] Attack surface documented and tested
- **Status**: Ready to start (all dependencies satisfied)

### Final Acceptance
- [x] VULN-001/002 resolved (SecureDataFrame - Sprint 1)
- [x] VULN-003 resolved (CentralPluginRegistry - Sprint 2)
- [x] VULN-005/006 resolved (P0 hotfixes - Sprint 0)
- [ ] VULN-004 resolved (Registry enforcement - Sprint 3)
- [ ] All security audit findings fully resolved
- [ ] IRAP compliance blockers cleared
- [ ] Production deployment approved

---

## Risk Management

### High-Risk Areas
1. **SecureDataFrame backward compatibility** - Existing code expects plain pd.DataFrame
2. **Registry consolidation** - 15+ registries used throughout codebase
3. **Configuration parser changes** - YAML validation could break existing configs

### Mitigation Strategies
1. **Incremental rollout** - Feature flags for SecureDataFrame validation
2. **Deprecation path** - Old registries work alongside new for 1 release
3. **Schema versioning** - Support legacy YAML format during transition

### Rollback Plan
- Each sprint creates a tagged release
- Feature flags allow disabling new validation
- Old registries remain functional during migration

---

## Contact and Escalation

**Security Lead**: Review required for all changes touching:
- `src/elspeth/core/security/`
- `src/elspeth/core/base/plugin.py`
- Registry enforcement logic

**Compliance Review**: Required before marking IRAP blockers as resolved

**Architecture Review**: Required for ADR-003 central registry design approval

---

## Appendices

### A. Security Audit Summary

**Original Findings**: 7 P0 vulnerabilities
**Resolved in Phase 2**: 2 (VULN-005, VULN-006 via hotfix)
**Remaining**: 5 (2 P0, 1 P1, 2 P2)

### B. Test Coverage Baseline

**Before Sprint 1**: 1445 tests passing, 2 skipped, 6 xfailed
**Target After Sprint 3**: 1445+ passing, 0-1 skipped, 0 xfailed

### C. Performance Impact

**Expected**: Minimal (<5% overhead from SecureDataFrame validation)
**Monitoring**: Benchmark suite tracks datasource load times

### D. Documentation Updates Required

- [ ] Update ADR-002 to mark Phase 2 complete
- [ ] Create ADR-014: SecureDataFrame Implementation
- [ ] Update `docs/architecture/security-controls.md`
- [ ] Migration guide for SecureDataFrame
- [ ] API documentation for CentralPluginRegistry
