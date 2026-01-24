# Validation Subsystem Migration - Phased Rollout

## Overview

This document describes the 3-phase rollout strategy for migrating validation
from plugin `__init__` methods to separate PluginConfigValidator subsystem.

Each phase is independently deployable and testable.

---

## Phase 1: Discovery (Tasks 0.1-0.4) ✅

**Status:** COMPLETE (you are here)

**Deliverables:**
- Instantiation audit: Know what needs updating
- Config model inventory: Verify all plugins compatible
- Integration tests: Completion criteria defined
- This document: Rollout strategy documented

**Safety:** Read-only phase, no production changes

**Discovery Results (Actual):**
- **Production instantiation sites:** 9 (2 files: cli.py, cli_helpers.py)
- **Total plugins:** 21 (20 with config classes, 1 without - NullSource)
- **Test instantiation sites:** 224
- **Azure plugin pack:** 7 additional plugins (blob source/sink, 5 Azure transforms)

**Discovery Artifacts:**
- `docs/plans/instantiation-audit.md` - Production site audit
- `docs/plans/config-model-audit.md` - Config class inventory
- `tests/plugins/test_validation_integration.py` - Integration tests (xfail)
- `docs/plans/validation-migration-phases.md` - This document

---

## Phase 2: Manager Integration (Tasks 1-4)

**Goal:** Add PluginConfigValidator and integrate with PluginManager

**Deployment Strategy:**
1. Add validator module (Task 1)
2. Extend validator for all types (Task 2)
3. Add schema validation (Task 3)
4. Add create_* methods to manager (Task 4)

**Safety Gates:**
- Integration tests start passing (remove xfail markers)
- NullSource edge case handled (resume-only source with no config class)
- Old instantiation pattern STILL WORKS (backward compatible)
- Validation happens in BOTH places (manager + __init__)

**Rollback:** Revert manager changes, old enforcement still active

**Deployment Order:**
```
1. Deploy validator module (no-op, not used yet)
2. Deploy manager with create_* methods
3. Gradually migrate callsites to use manager
4. Verify dual validation doesn't break anything
```

**Success Criteria:**
- All integration tests pass
- Production can create plugins via manager.create_*()
- Old direct instantiation still works
- No test failures introduced

---

## Phase 3: Cleanup (Tasks 5-8)

**Goal:** Remove old enforcement mechanism, update test fixtures

**Deployment Strategy:**
1. Update test fixture docs (Task 5)
2. Add optional self-consistency checks (Task 6)
3. Remove enforcement from base classes (Task 7)
4. Verify all tests pass (Task 8)

**Safety Gates:**
- Manager validation proven working in Phase 2
- All production callsites migrated to manager
- Test fixtures documented to use direct instantiation

**Rollback:** Re-add enforcement mechanism if needed

**Deployment Order:**
```
1. Remove __init_subclass__ hook from base classes
2. Remove _validate_self_consistency() calls from plugins
3. Remove R2 allowlist entries
4. Deploy and verify 86 failing tests now pass
```

**Success Criteria:**
- All 3,305 tests pass (100% pass rate)
- No RuntimeError from enforcement
- Plugins are simpler (no validation in __init__)
- Test fixtures work without changes

---

## Rollback Procedures

### Phase 2 Rollback
If manager integration causes issues:
1. Revert manager.py changes
2. Production continues using direct instantiation
3. Old enforcement mechanism still works

### Phase 3 Rollback
If removing enforcement causes issues:
1. Re-add __init_subclass__ hook to base classes
2. Re-add _validate_self_consistency() calls
3. Re-add R2 allowlist entries
4. Production uses manager, tests use old pattern

---

## Risk Mitigation

### Risk: Manager methods break production
**Mitigation:** Phase 2 keeps old pattern working (backward compatible)
**Detection:** Integration tests fail
**Response:** Fix manager methods before Phase 3

### Risk: Removing enforcement breaks tests
**Mitigation:** Phase 2 proves manager validation works first
**Detection:** 86 tests fail in Phase 3
**Response:** Keep enforcement until manager proven stable

### Risk: Scope undercount (missed instantiation sites)
**Mitigation:** Task 0.1 audit finds ALL sites
**Detection:** Grep verification before Phase 3
**Response:** Update missing sites before removing enforcement

---

## Timeline

**Phase 1 (Discovery):** 4 tasks × 10 min = 40 minutes
**Phase 2 (Integration):** 4 tasks × 15 min = 60 minutes
**Phase 3 (Cleanup):** 4 tasks × 15 min = 60 minutes

**Total estimated time:** 2.5 hours (includes buffer for debugging)

---

## Success Metrics

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Test pass rate | 96.5% (3,219/3,305) | 100% (3,305/3,305) | +3.5% |
| Test failures | 86 | 0 | -86 |
| Enforcement complexity | __init_subclass__ hooks | None | Simplified |
| Validation location | Plugin __init__ | PluginManager | Centralized |
| Test fixture updates | 95+ classes | 0 | No burden |
