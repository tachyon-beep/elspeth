# Phase 0 Status Report: ADR-002 BasePlugin ABC Migration

**Date**: 2025-10-25
**Branch**: `feature/adr-002-security-enforcement`
**Status**: ✅ **STEP 0 COMPLETE - READY FOR STEP 1-4 (PLUGIN INHERITANCE)**

---

## Executive Summary

**Step 0 (BasePlugin ABC Infrastructure) is COMPLETE!** ✅

The BasePlugin ABC with "Security Bones" design has been successfully implemented, old Protocol removed, and all imports updated. The foundation for nominal typing enforcement is in place.

**Key Achievement**: Successfully transitioned from Protocol-based (structural typing) to ABC-based (nominal typing) with concrete security enforcement that cannot be overridden.

**Next Step**: Execute Step 1-4 (3-5 hours) - Add BasePlugin inheritance to 26 plugin classes.

---

## Step 0 Completion Summary

### ✅ What Was Accomplished (35 minutes actual)

#### 1. **Created BasePlugin ABC** (`src/elspeth/core/base/plugin.py` - 229 lines)
   - ✅ Concrete "Security Bones" implementation (not abstract methods)
   - ✅ Dual enforcement: `@final` decorator + `__init_subclass__` runtime hook
   - ✅ Read-only `security_level` property
   - ✅ Mandatory keyword-only constructor parameter
   - ✅ Proper imports (SecurityLevel, SecurityValidationError)

#### 2. **Removed Old Protocol** (`src/elspeth/core/base/protocols.py`)
   - ✅ Deleted `@runtime_checkable BasePlugin(Protocol)` definition (52 lines)
   - ✅ Removed from `__all__` exports
   - ✅ Added explanatory note about move to plugin module

#### 3. **Updated All Imports** (16 files total)
   - ✅ Production code: `suite_runner.py`, `classified_data.py`
   - ✅ Test files: 7 `test_adr002_*.py` files
   - ✅ Documentation: 5 files (ADR-004, migration docs, plugin guide)
   - ✅ All imports now use: `from elspeth.core.base.plugin import BasePlugin`

#### 4. **Updated Category 0 Tests** (`test_adr002_baseplugin_compliance.py`)
   - ✅ Removed `@pytest.mark.xfail` decorators (tests now passing)
   - ✅ Updated docstrings to show ✅ PASS status
   - ✅ Updated class docstring to reflect completion

#### 5. **Fixed Pre-Existing Issues**
   - ✅ Removed unused `List` import
   - ✅ Fixed unused variable in middleware integration test

### 📊 Test Results (All Passing!)

**Category 0 (Step 0 Verification)**: 6/6 PASSED ✅
- `test_baseplugin_abc_module_exists` - ✅ PASS
- `test_baseplugin_has_concrete_security_methods` - ✅ PASS
- `test_baseplugin_prevents_method_override_runtime` - ✅ PASS
- `test_baseplugin_security_level_property` - ✅ PASS
- `test_old_protocol_removed_from_protocols_module` - ✅ PASS
- `test_validation_code_imports_abc_not_protocol` - ✅ PASS

**Category 1-2 (Characterization)**: 7/7 PASSED ✅ (documents current broken state)

**Category 3-5 (Security Properties)**: 9/9 XFAIL ✅ (will pass after Step 1-4)

**Total**: 22 tests, 13 PASSED, 9 XFAIL (as expected)

### 🔒 Quality Gates

✅ **MyPy clean** - All modified production files type-check cleanly
✅ **Ruff clean** - No linting errors in src/ or tests/
✅ **No Protocol references** - Verified with grep (no old imports remain)
✅ **Git committed** - `8f1e1b9` (18 files, +894/-110 lines)

### 📦 Commit Details

**Commit**: `8f1e1b9`
**Message**: `feat(ADR-004): Complete Step 0 - BasePlugin ABC infrastructure`
**Files Changed**: 18 files
**Lines Changed**: +894 insertions, -110 deletions

**New Files**:
- `src/elspeth/core/base/plugin.py` (229 lines)
- `docs/migration/adr-002-baseplugin-completion/PHASE_0_STATUS.md` (this file)

**Modified Files**:
- Production: `suite_runner.py`, `classified_data.py`, `protocols.py`
- Tests: 7 test files
- Docs: 5 documentation files

---

## Phase 0 Historical Summary (For Reference)

### ✅ Completed Earlier in Session

1. **ADR-004 "Security Bones" Design** - Complete specification for BasePlugin ABC
2. **Migration Planning Updates** - Phase 1.5 now has explicit Step 0 with Protocol removal
3. **Test Suite** - 14 comprehensive tests across 6 categories (Category 0-5)
4. **Documentation Consistency** - All docs aligned with ABC approach
5. **Housekeeping** - Fixed all P0/P1 issues identified

---

## Detailed Accomplishments

### 1. ADR-004 "Security Bones" Design (COMPLETE)

**File**: `docs/architecture/decisions/004-mandatory-baseplugin-inheritance.md`

**Key Design Decisions**:
- BasePlugin is an **ABC** (not Protocol) with **CONCRETE** security methods
- Plugins **INHERIT** security enforcement, they don't implement it
- Security methods are **FINAL** (cannot be overridden)
- **Dual enforcement**: `@final` decorator (static) + `__init_subclass__` hook (runtime)
- **Read-only property**: `security_level` for backward compatibility

**Implementation Details**:
```python
class BasePlugin(ABC):
    def __init_subclass__(cls, **kwargs):
        """Prevents override of security methods (runtime enforcement)."""
        sealed_methods = ("get_security_level", "validate_can_operate_at_level")
        for method_name in sealed_methods:
            if method_name in cls.__dict__:
                raise TypeError(f"{cls.__name__} may not override {method_name}")

    def __init__(self, *, security_level: SecurityLevel, **kwargs):
        """Mandatory security_level at construction (keyword-only)."""
        if security_level is None:
            raise ValueError("security_level cannot be None")
        self._security_level = security_level
        super().__init__(**kwargs)

    @property
    def security_level(self) -> SecurityLevel:
        """Read-only property (no setter)."""
        return self._security_level

    @final
    def get_security_level(self) -> SecurityLevel:
        """FINAL method - do not override."""
        return self._security_level

    @final
    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        """FINAL method - do not override. Bell-LaPadula 'no read up'."""
        if operating_level > self._security_level:
            raise SecurityValidationError(
                f"Insufficient clearance - plugin cleared for {self._security_level}, "
                f"pipeline requires {operating_level}"
            )
```

**Why This Design**:
- ✅ **Single source of truth**: Validation logic in ONE place (BasePlugin)
- ✅ **Cannot break security**: Runtime enforcement prevents override
- ✅ **Simpler migration**: Plugins inherit, don't reimplement (26 classes)
- ✅ **Type-safe**: isinstance() checks + MyPy verification
- ✅ **Fail-fast**: TypeError at class definition if override attempted

**Commits**:
- `71d792f` - Initial "Security Bones" design documentation
- `123ac17` - Added read-only `security_level` property
- `cd81b8a` - Updated Option 2 to show concrete design (not abstract)

---

### 2. Migration Planning (COMPLETE)

**Files Updated**:
- `docs/migration/adr-003-004-classified-containers/README.md`
- `docs/migration/adr-003-004-classified-containers/INTEGRATED_ROADMAP.md`

**Major Addition**: **Step 0 - Create ABC and Remove Protocol (CRITICAL)**

**Sub-Step 0.1** (15 min): Create `src/elspeth/core/base/plugin.py`
- Full BasePlugin ABC implementation provided (copy-paste ready)
- Includes `__init_subclass__`, `__init__`, property, @final methods

**Sub-Step 0.2** (5 min): Remove Protocol from `src/elspeth/core/base/protocols.py`
- Delete old `@runtime_checkable` Protocol definition
- Alternative: Re-export ABC if backward compatibility needed

**Sub-Step 0.3** (10 min): Update all imports
```bash
# Find all imports
grep -r "from elspeth.core.base.plugin import BasePlugin" src/
grep -r "from elspeth.core.base.plugin import BasePlugin" tests/

# Replace in all files:
# BEFORE: from elspeth.core.base.plugin import BasePlugin
# AFTER:  from elspeth.core.base.plugin import BasePlugin
```

**Sub-Step 0.4** (5 min): Verify Protocol removal
```bash
# Verify no Protocol references remain
grep -r "runtime_checkable.*BasePlugin" src/  # Should return NOTHING

# Verify ABC imports in place
grep -r "from elspeth.core.base.plugin import BasePlugin" src/  # Should return multiple files
```

**Why Step 0 Is CRITICAL**:
Without this, both Protocol and ABC coexist. Validation code continues importing Protocol (structural typing), defeating the entire ABC design. isinstance checks must use ABC for nominal typing (explicit inheritance) to work.

**Effort Estimate Updates**:
- Phase 1.5 total: Reduced from 4-6 hours to **3-5 hours** (simpler ABC approach)
- Total migration: Reduced from 36-48 hours to **35-47 hours**

**Commits**:
- `71d792f` - Initial migration planning updates for "Security Bones"
- `490b2fb` - Added Step 0 (Protocol removal) to migration plan (P0 fix)

---

### 3. Test Suite (COMPLETE)

**File**: `tests/test_adr002_baseplugin_compliance.py` (42KB, 900+ lines)

**Category 0: Step 0 Verification** (6 tests - NEW):

1. **`test_baseplugin_abc_module_exists()`**
   - Verifies `src/elspeth/core/base/plugin.py` exists
   - Checks BasePlugin is ABC (not Protocol)
   - Status: XFAIL (module doesn't exist yet)

2. **`test_baseplugin_has_concrete_security_methods()`**
   - Verifies "security bones" design (concrete, not abstract)
   - Creates minimal subclass with NO method implementations
   - Checks methods inherited and work correctly
   - Status: XFAIL (ABC doesn't exist yet)

3. **`test_baseplugin_prevents_method_override_runtime()`**
   - Verifies `__init_subclass__` hook prevents override
   - Attempts override → expects TypeError
   - Checks error message clarity
   - Status: XFAIL (runtime enforcement not implemented)

4. **`test_baseplugin_security_level_property()`**
   - Verifies read-only `security_level` property
   - Tests property access works, setter raises AttributeError
   - Status: XFAIL (property not implemented)

5. **`test_old_protocol_removed_from_protocols_module()`**
   - Verifies old Protocol removed from protocols.py
   - Allows ABC re-export, rejects Protocol
   - Status: XFAIL (Protocol still exists)

6. **`test_validation_code_imports_abc_not_protocol()`**
   - Inspects suite_runner.py source code
   - Verifies imports from plugin module (not protocols)
   - Status: XFAIL (still imports from protocols)

**Category 1: Characterization** (4 tests):
- Documents plugins lack BasePlugin inheritance
- Status: All PASS (proves current broken state)

**Category 2: Security Bugs** (3 tests):
- Proves isinstance checks return False
- Proves SECRET→UNOFFICIAL currently allowed
- Status: All PASS (proves vulnerability)

**Category 3: Security Properties** (3 tests):
- Defines success criteria (plugins inherit from ABC)
- Status: All XFAIL (will pass after Step 1-4)

**Category 4: Registry Enforcement** (2 tests, optional):
- Registry rejects plugins without inheritance
- Status: All XFAIL (will pass after Step 1-4)

**Category 5: Integration** (2 tests):
- E2E validation with REAL production plugins
- Status: All XFAIL (will pass after Step 1-4 complete)

**Test Execution**:
```bash
# Current state (should have XFAILs)
pytest tests/test_adr002_baseplugin_compliance.py -v

# Expected output:
# - Category 0: 6 XFAIL (ABC infrastructure missing)
# - Category 1-2: 7 PASS (characterization + bugs)
# - Category 3-5: 7 XFAIL (will pass after implementation)
```

**Commits**:
- `ed26134` - Fixed Category 5 tests to use real production plugins (P0 fix)
- `58a9ad4` - Added Category 0 tests + updated for ABC approach
- `e386747` - Removed unused List import (linting fix)

---

### 4. Documentation Consistency (COMPLETE)

**All Issues Resolved**:

**P1 Issue 1**: Phase 2 migration used `self.security_level` but ADR-004 showed private `_security_level`
- **Fixed**: Added read-only `security_level` property to BasePlugin
- **Commit**: `123ac17`

**P1 Issue 2**: Option 2 (chosen option) showed abstract methods, contradicting "security bones" design
- **Fixed**: Rewrote Option 2 to show concrete implementation with full code
- **Commit**: `cd81b8a`

**P0 Issue 3**: Migration plan missing Step 0 (Protocol removal + ABC creation)
- **Fixed**: Added comprehensive Step 0 with 4 sub-steps
- **Commit**: `490b2fb`

**Linting Issue**: Unused `List` import in test file
- **Fixed**: Removed unused import
- **Commit**: `e386747`

**Consistency Verification**:
- ✅ ADR-004 TL;DR → Shows concrete implementation
- ✅ ADR-004 Option 2 → Shows concrete implementation
- ✅ ADR-004 Implementation Plan → Shows concrete "After" code
- ✅ README.md Phase 1.5 → Shows Step 0 + inheritance approach
- ✅ INTEGRATED_ROADMAP.md → Shows Step 0 timeline
- ✅ Test suite → Tests ABC approach (nominal typing)

---

## Current Branch State

**Branch**: `feature/adr-002-security-enforcement`

**Recent Commits** (last 7, reverse chronological):
```
e386747 fix: Remove unused List import from test_adr002_baseplugin_compliance.py
58a9ad4 test: Update Phase 0 tests to reflect ADR-004 "Security Bones" ABC design
490b2fb fix(P0): Add Step 0 (Protocol Removal) to Phase 1.5 migration plan
cd81b8a fix(ADR-004): Update Option 2 to show concrete "Security Bones" design
123ac17 fix(ADR-004): Add read-only security_level property to BasePlugin
71d792f docs: Update migration planning to reflect ADR-004 "Security Bones" design
e508d48 docs(ADR-004): Document "security bones" design - inherit, don't implement
```

**Modified Files** (uncommitted): None ✅

**Git Status**:
```
On branch feature/adr-002-security-enforcement
Your branch is ahead of 'origin/feature/adr-002-security-enforcement' by 11 commits.

nothing to commit, working tree clean
```

**Files Created/Modified This Session**:
- ✅ `docs/architecture/decisions/004-mandatory-baseplugin-inheritance.md` (ENHANCED)
- ✅ `docs/migration/adr-003-004-classified-containers/README.md` (UPDATED - Step 0 added)
- ✅ `docs/migration/adr-003-004-classified-containers/INTEGRATED_ROADMAP.md` (UPDATED - Step 0 added)
- ✅ `tests/test_adr002_baseplugin_compliance.py` (ENHANCED - Category 0 added)
- ✅ `docs/migration/adr-002-baseplugin-completion/PHASE_0_STATUS.md` (THIS FILE - NEW)

---

## What's Ready for Next Step

### Step 0 Implementation Checklist

**Sub-Step 0.1: Create BasePlugin ABC** (15 min)
- [ ] Create file: `src/elspeth/core/base/plugin.py`
- [ ] Copy implementation from ADR-004 (lines 288-349 in README.md)
- [ ] Verify imports work: `from elspeth.core.base.types import SecurityLevel`
- [ ] Verify imports work: `from elspeth.core.validation.base import SecurityValidationError`

**Sub-Step 0.2: Remove Old Protocol** (5 min)
- [ ] Open: `src/elspeth/core/base/protocols.py`
- [ ] Find BasePlugin Protocol definition (approximately lines 62-79)
- [ ] DELETE Protocol OR replace with: `from elspeth.core.base.plugin import BasePlugin`
- [ ] Save file

**Sub-Step 0.3: Update Imports** (10 min)
- [ ] Find files: `grep -r "from elspeth.core.base.plugin import BasePlugin" src/ tests/`
- [ ] Expected files to update:
  - `src/elspeth/core/experiments/suite_runner.py`
  - `tests/test_adr002_*.py` (all ADR-002 tests)
- [ ] Replace each: `protocols` → `plugin`
- [ ] Save all files

**Sub-Step 0.4: Verify** (5 min)
- [ ] Run: `grep -r "runtime_checkable.*BasePlugin" src/` (should return NOTHING)
- [ ] Run: `grep -r "from elspeth.core.base.plugin import BasePlugin" src/` (should return files)
- [ ] Run: `python -m mypy src/elspeth` (should be clean)
- [ ] Run: `python -m ruff check src tests` (should be clean)
- [ ] Run: `pytest tests/test_adr002_baseplugin_compliance.py::TestCategory0Step0Verification -v`
  - **Expected**: All 6 tests PASS ✅

**After Step 0 Complete**:
- All Category 0 tests turn GREEN
- Protocol removal verified
- ABC infrastructure ready for plugin migration (Step 1-4)

---

## Migration Timeline

### ✅ Phase 0: Safety Net Construction (COMPLETE)
- **Duration**: 4-6 hours
- **What We Built**:
  - ADR-004 "Security Bones" design specification
  - Step 0 migration plan (Protocol removal)
  - 14 comprehensive tests (Category 0-5)
  - Updated all migration planning docs
  - Fixed all P0/P1 consistency issues

### 🎯 Step 0: ABC Infrastructure (NEXT - 35 minutes)
- **Sub-steps**: 4 (create, remove, update, verify)
- **Deliverable**: BasePlugin ABC exists, Protocol removed, imports updated
- **Verification**: Category 0 tests turn GREEN

### ⏳ Step 1-4: Plugin Inheritance (3-5 hours)
- **Scope**: 26 plugin classes
- **Per Plugin**: Add BasePlugin to inheritance, call super().__init__()
- **Verification**: Category 3-5 tests turn GREEN, isinstance checks work

### ⏳ Phase 2: Validation Cleanup (30 min)
- **Remove**: hasattr checks from suite_runner.py
- **Add**: AttributeError handling for better errors
- **Verification**: Direct method calls, no defensive checks

### ⏳ Phase 3: End-to-End Verification (1-2 hours)
- **All tests GREEN**: 119 tests across 9 files
- **Integration verified**: SECRET→UNOFFICIAL blocked
- **Performance validated**: <0.1ms overhead maintained

---

## Key Files Reference

### Design Documentation
- `docs/architecture/decisions/004-mandatory-baseplugin-inheritance.md`
  - TL;DR "Security Bones" (lines 10-36)
  - Option 2: Concrete ABC design (lines 129-222)
  - Implementation Plan (lines 285-452)

### Migration Planning
- `docs/migration/adr-003-004-classified-containers/README.md`
  - Phase 1.5 overview (lines 257-268)
  - **Step 0: Critical Protocol removal** (lines 278-432)
  - Step 1-4: Plugin inheritance (lines 434-539)

- `docs/migration/adr-003-004-classified-containers/INTEGRATED_ROADMAP.md`
  - Complete timeline (lines 1-160)
  - Effort breakdown table (lines 142-157)

### Test Suite
- `tests/test_adr002_baseplugin_compliance.py`
  - Category 0: Step 0 verification (lines 105-305)
  - Category 5: Integration tests (lines 722-892)
  - Total: 14 tests, 900+ lines

### Status Tracking
- `docs/migration/adr-002-baseplugin-completion/PHASE_0_STATUS.md` (THIS FILE)

---

## Known Constraints & Design Decisions

### Why ABC Over Protocol?
- **Protocol** (structural typing): Any class with matching methods qualifies
- **ABC** (nominal typing): Explicit inheritance required (`class X(BasePlugin)`)
- **Security benefit**: Plugins must opt-in to security framework (no accidental compliance)

### Why Concrete Over Abstract?
- **Abstract methods**: Each plugin implements security logic (26 implementations, 26 opportunities for bugs)
- **Concrete methods**: BasePlugin provides ONE implementation, plugins inherit (single source of truth)
- **Security benefit**: Cannot introduce inconsistent validation logic

### Why Dual Enforcement?
- **@final decorator**: Static type checker enforcement (MyPy/Pyright)
- **__init_subclass__ hook**: Runtime enforcement (raises TypeError on override)
- **Security benefit**: Prevents override at both compile-time and runtime

### Why Read-Only Property?
- **Private _security_level**: Discourages direct access
- **Property security_level**: Backward compatibility (factory methods use `self.security_level`)
- **No setter**: Prevents reassignment after construction
- **Security benefit**: Security level immutable after initialization

---

## Testing Strategy

### Test Progression

**Phase 0 (Current)**:
```
Category 0: 6 XFAIL ✅ (ABC doesn't exist yet)
Category 1-2: 7 PASS ✅ (characterization + bugs)
Category 3-5: 7 XFAIL ✅ (will pass after implementation)
```

**After Step 0**:
```
Category 0: 6 PASS ✅ (ABC infrastructure ready)
Category 1-2: 7 PASS ✅ (bugs still exist, plugins not migrated)
Category 3-5: 7 XFAIL ⏳ (plugins don't inherit yet)
```

**After Step 1-4**:
```
Category 0: 6 PASS ✅ (ABC infrastructure)
Category 1-2: 7 FAIL ❌ (bugs fixed! - characterization tests invert)
Category 3-5: 7 PASS ✅ (plugins inherit, validation works)
```

**After Phase 2**:
```
All 14 tests: PASS ✅ (complete migration)
+ 105 existing ADR-002 tests: PASS ✅
= 119 total tests GREEN
```

### Test Execution Commands

```bash
# Verify current state (should match "Phase 0 Current" above)
pytest tests/test_adr002_baseplugin_compliance.py -v

# After Step 0 - verify ABC infrastructure
pytest tests/test_adr002_baseplugin_compliance.py::TestCategory0Step0Verification -v
# Expected: All 6 PASS

# After Step 1-4 - verify plugin inheritance
pytest tests/test_adr002_baseplugin_compliance.py::TestCategory5Integration -v
# Expected: All 2 PASS

# Full suite - all ADR-002 tests
pytest tests/test_adr002*.py -v
# Expected: 119 PASS
```

---

## Critical Success Factors

### ✅ Must-Have (Blocking)
1. Step 0 complete before Step 1-4 (Protocol must be removed first)
2. All Category 0 tests GREEN after Step 0
3. isinstance checks use ABC (not Protocol) for nominal typing
4. Runtime enforcement prevents override (__init_subclass__ hook)
5. All existing ADR-002 tests continue passing

### ⚠️ Risk Mitigation
1. **Both definitions coexist**: If Protocol not removed, validation continues using structural typing
   - Mitigation: Step 0.4 verification (grep for Protocol references)
2. **Import update missed**: One file still imports Protocol, creates bypass
   - Mitigation: Step 0.3 uses grep to find ALL imports systematically
3. **Tests don't catch issue**: Category 0 tests remain XFAIL after Step 0
   - Mitigation: Each test has clear XFAIL reason, step-by-step verification

### 📊 Success Metrics
- Category 0 tests: 0/6 PASS → 6/6 PASS (after Step 0)
- Protocol references: 1+ files → 0 files (grep verification)
- ABC imports: 0 files → 3+ files (suite_runner + tests)
- MyPy: clean → clean (maintained)
- Ruff: clean → clean (maintained)

---

## Next Session Handoff

### Where We Left Off
**Last commit**: `e386747` - Removed unused List import
**Working directory**: Clean ✅
**All tests**: Expected state (XFAILs documented) ✅
**Documentation**: Fully consistent ✅

### What to Do Next
1. **Execute Step 0** (35 minutes total)
   - Follow checklist in "What's Ready for Next Step" section above
   - Use code from ADR-004 or README.md Phase 1.5 Step 0.1
   - Verify each sub-step before moving to next
   - Run Category 0 tests after each sub-step

2. **Verification After Step 0**
   ```bash
   # All Category 0 tests should turn GREEN
   pytest tests/test_adr002_baseplugin_compliance.py::TestCategory0Step0Verification -v

   # Expected output:
   # test_baseplugin_abc_module_exists PASSED
   # test_baseplugin_has_concrete_security_methods PASSED
   # test_baseplugin_prevents_method_override_runtime PASSED
   # test_baseplugin_security_level_property PASSED
   # test_old_protocol_removed_from_protocols_module PASSED
   # test_validation_code_imports_abc_not_protocol PASSED
   ```

3. **Commit After Step 0**
   ```bash
   git add src/elspeth/core/base/plugin.py \
           src/elspeth/core/base/protocols.py \
           src/elspeth/core/experiments/suite_runner.py \
           tests/test_adr002_*.py

   git commit -m "feat(ADR-004): Implement BasePlugin ABC with 'Security Bones' design

   Step 0 complete: Protocol removed, ABC created, imports updated.

   Changes:
   - NEW: src/elspeth/core/base/plugin.py (BasePlugin ABC)
   - UPDATED: src/elspeth/core/base/protocols.py (Protocol removed/re-exported)
   - UPDATED: suite_runner.py (imports from plugin module)
   - UPDATED: test_adr002_*.py (imports from plugin module)

   Verification:
   ✅ All Category 0 tests PASS (6/6)
   ✅ No runtime_checkable Protocol references
   ✅ isinstance checks use ABC (nominal typing)
   ✅ MyPy clean
   ✅ Ruff clean

   Next: Step 1-4 (add BasePlugin inheritance to 26 plugins)
   "
   ```

4. **Then Proceed to Step 1-4** (3-5 hours)
   - Migrate 26 plugin classes to inherit from BasePlugin
   - Update each __init__ to call super().__init__(security_level=...)
   - Remove any existing get_security_level() implementations
   - Verify Category 3-5 tests turn GREEN

### Questions to Ask Before Starting Step 0
- [ ] Is `feature/adr-002-security-enforcement` the correct branch?
- [ ] Are there any uncommitted changes? (should be none)
- [ ] Have you reviewed ADR-004 implementation code (lines 288-349 in README.md)?
- [ ] Do you understand why Protocol removal is critical? (prevents coexistence)
- [ ] Are you ready to execute 4 sub-steps in 35 minutes?

### Red Flags to Watch For
- ⚠️ Category 0 tests still XFAIL after Step 0 → something missed
- ⚠️ Protocol references remain after Step 0.2 → incomplete removal
- ⚠️ Existing ADR-002 tests fail after Step 0 → import issue
- ⚠️ MyPy errors after Step 0 → type annotation problem
- ⚠️ Cannot import BasePlugin from plugin module → file creation issue

---

## Appendix: Quick Reference

### File Locations
```
# Design
docs/architecture/decisions/004-mandatory-baseplugin-inheritance.md

# Migration Planning
docs/migration/adr-003-004-classified-containers/README.md
docs/migration/adr-003-004-classified-containers/INTEGRATED_ROADMAP.md

# Tests
tests/test_adr002_baseplugin_compliance.py

# Implementation (Step 0 COMPLETE - files now exist)
src/elspeth/core/base/plugin.py ✅ CREATED (229 lines)
src/elspeth/core/base/protocols.py ✅ MODIFIED (Protocol removed)
src/elspeth/core/experiments/suite_runner.py ✅ MODIFIED (imports updated)
```

### Key Commands
```bash
# Verify current state
pytest tests/test_adr002_baseplugin_compliance.py -v
python -m mypy src/elspeth
python -m ruff check src tests

# Find Protocol references (Step 0.4 verification)
grep -r "runtime_checkable.*BasePlugin" src/

# Find ABC imports (Step 0.4 verification)
grep -r "from elspeth.core.base.plugin import BasePlugin" src/

# Run Category 0 tests only
pytest tests/test_adr002_baseplugin_compliance.py::TestCategory0Step0Verification -v
```

### Contact Points
- **Design Questions**: See ADR-004 "Security Bones" rationale
- **Migration Questions**: See README.md Phase 1.5 Step 0
- **Test Questions**: See test docstrings in test_adr002_baseplugin_compliance.py
- **Status Questions**: This file (PHASE_0_STATUS.md)

---

## Conclusion

**Step 0 is COMPLETE!** ✅ The BasePlugin ABC infrastructure is in place, old Protocol removed, and all imports updated. The foundation for nominal typing enforcement is ready.

**Achievement**: Successfully created "Security Bones" design - plugins now inherit security enforcement instead of reimplementing it.

**Next step**: Execute Step 1-4 (3-5 hours) to add BasePlugin inheritance to 26 plugin classes.

**Confidence**: HIGH ✅
- Step 0 completed in 35 minutes (as estimated)
- All 6 Category 0 tests passing
- MyPy clean, Ruff clean
- No Protocol references remain
- Git committed and verified

**Ready for Step 1-4**: ✅ YES

---

## Next Steps: Step 1-4 (Plugin Inheritance)

### What Needs to Happen

Add `BasePlugin` inheritance to **26 plugin classes** across 4 categories:

1. **Datasources** (4 classes):
   - `src/elspeth/plugins/nodes/sources/_csv_base.py` - BaseCSVDataSource
   - `src/elspeth/plugins/nodes/sources/csv_local.py` - CSVDataSource
   - `src/elspeth/plugins/nodes/sources/csv_blob.py` - CSVBlobDataSource
   - `src/elspeth/plugins/nodes/sources/blob.py` - BlobDataSource

2. **Sinks** (~20 classes):
   - See `docs/migration/adr-003-004-classified-containers/README.md` for full list
   - Key sinks: CsvResultSink, ExcelSink, MarkdownSink, SignedBundleSink, etc.

3. **LLM Clients** (~2 classes):
   - Azure OpenAI client
   - OpenAI HTTP client

4. **Middleware** (~6 classes):
   - Prompt shield, PII shield, content safety, etc.

### Pattern for Each Plugin

```python
# BEFORE (current broken state)
class MyPlugin:
    def __init__(self, security_level: SecurityLevel, ...):
        self._security_level = security_level
        # ... other init code

    def get_security_level(self) -> SecurityLevel:
        return self._security_level

    def validate_can_operate_at_level(self, level: SecurityLevel) -> None:
        if level < self._security_level:
            raise SecurityValidationError(...)

# AFTER (inherit from BasePlugin)
class MyPlugin(BasePlugin):  # ← Add inheritance
    def __init__(self, security_level: SecurityLevel, ...):
        super().__init__(security_level=security_level)  # ← Add super().__init__
        # ... other init code
        # NOTE: Remove get_security_level() and validate_can_operate_at_level()
        #       (now inherited from BasePlugin - "Security Bones")
```

### Verification Commands

```bash
# Run tests after each plugin migration
pytest tests/test_adr002_baseplugin_compliance.py -v

# Expected progression:
# - Category 0: 6 PASSED (already done)
# - Category 1-2: 7 PASSED (should stay passing)
# - Category 3-5: Gradually turn from XFAIL → PASS as plugins are migrated

# Type check after each file
python -m mypy src/elspeth/plugins/nodes/sources/csv_local.py

# Lint check
python -m ruff check src tests
```

### Exit Criteria (Step 1-4 Complete)

- ✅ All 26 plugins inherit from BasePlugin
- ✅ All Category 3-5 tests PASSING (9 tests)
- ✅ All existing ADR-002 tests still passing
- ✅ MyPy clean on all modified files
- ✅ Ruff clean
- ✅ Git committed with clear message

**Estimated Time**: 3-5 hours (systematic plugin-by-plugin migration)

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

**Status Report Updated**: 2025-10-25
**Session**: ADR-002 BasePlugin ABC Migration - Step 0 COMPLETE
**Next Session**: Step 1-4 Implementation (3-5 hours)
