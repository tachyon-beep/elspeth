# Implementation Roadmap: Post-Phase 2 Security Enhancements

**Status**: Phase 2 Migration Complete (40→0 test failures), P0 hotfixes deployed
**Date**: 2025-10-27
**Branch**: feature/adr-002-security-enforcement

## Executive Summary

After completing ADR-002-B Phase 2 migration (immutable security policies) and deploying P0 hotfixes for incomplete plugin migrations, three major implementation tasks remain to fully realize the security architecture defined in ADR-002 and ADR-003.

### Current State
- ✅ **1445 tests passing** (0 failures)
- ✅ **All plugins inherit from BasePlugin** (security validation no longer bypassed)
- ✅ **Security levels hard-coded in plugin code** (not configurable via YAML)
- ✅ **P0 hotfixes deployed**: VULN-005 (PromptVariantsAggregator) + VULN-006 (3 validation plugins)

### Remaining Implementation Tasks

| Priority | Vulnerability | Scope | Estimated Effort |
|----------|---------------|-------|------------------|
| P0 | VULN-001/002: SecureDataFrame Not Implemented | Implement ADR-002-A trusted container model | 48-64 hours |
| P1 | VULN-003: Central Plugin Registry Missing | Consolidate 15+ scattered registries per ADR-003 | 9.5-13 hours |
| P2 | VULN-004: Configuration Override Attack | Implement registry-level validation enforcement | 13-18 hours |

**Total Estimated Effort**: 70.5-95 hours (2-3 sprints)

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
- Duration: 20 minutes
- Deliverables: VULN-005/006 fixed, all tests passing

#### Sprint 1: SecureDataFrame Implementation (P0)
- Duration: 2-3 weeks
- Deliverables: VULN-001/002 resolved, ADR-002-A fully implemented
- See: [VULN-001-002-classified-dataframe.md](./VULN-001-002-classified-dataframe.md)

#### Sprint 2: Central Plugin Registry (P1)
- Duration: 1 week
- Deliverables: VULN-003 resolved, ADR-003 implemented
- See: [VULN-003-central-plugin-registry.md](./VULN-003-central-plugin-registry.md)

#### Sprint 3: Registry Enforcement (P2)
- Duration: 1-2 weeks
- Deliverables: VULN-004 resolved, immutability guaranteed at registry level
- See: [VULN-004-registry-enforcement.md](./VULN-004-registry-enforcement.md)

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

### Sprint 1 Complete (SecureDataFrame)
- [ ] `SecureDataFrame` class implemented with Bell-LaPadula enforcement
- [ ] All datasources return classified DataFrames
- [ ] Runtime validation prevents misclassified data from reaching plugins
- [ ] XFAIL tests in `test_adr002_baseplugin_compliance.py` now PASS
- [ ] No new test failures introduced

### Sprint 2 Complete (Central Registry)
- [ ] `CentralPluginRegistry` consolidates all plugin types
- [ ] Backward compatibility maintained (old registries deprecated but functional)
- [ ] Migration guide published
- [ ] All existing tests pass without modification

### Sprint 3 Complete (Registry Enforcement)
- [ ] Registry validates `declared_security_level` matches plugin code
- [ ] Configuration attempts to override security_level are REJECTED
- [ ] Schema validation prevents YAML overrides
- [ ] Attack surface documented and tested

### Final Acceptance
- [ ] All XFAIL tests converted to PASS
- [ ] Security audit findings VULN-001 through VULN-006 fully resolved
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
