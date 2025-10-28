# ADR-002-A Implementation Plan: Trusted Container Model

**Status**: Planning
**Started**: 2025-10-25
**Estimated Effort**: 8-10 hours (proper planning + execution)
**Approach**: Test-first security development (RED → GREEN → REFACTOR)

---

## Quick Summary

**What**: Add constructor protection to `SecureDataFrame` preventing plugins from creating arbitrary classifications.

**Why**: Moves T4 (Classification Mislabeling) defense from certification (human review) to technical control (framework enforcement).

**How**: Use `__post_init__` validation + factory methods to restrict frame creation to datasources only.

**Security Property**: Only trusted sources (datasources) can create initial classifications. Plugins can only uplift, never relabel.

---

## Success Criteria

### Must-Have (MVP)
- [ ] All 5 security invariant tests PASS
- [ ] Plugins blocked from creating frames directly
- [ ] Datasources can create frames via factory method
- [ ] All existing tests still pass (no regressions)
- [ ] All datasources migrated to factory method
- [ ] MyPy clean, Ruff clean

### Should-Have (Quality)
- [ ] Performance validation (<0.1ms overhead per suite)
- [ ] Plugin development guide updated
- [ ] THREAT_MODEL.md T4 section updated
- [ ] Clear error messages for violations

### Nice-to-Have (Future)
- [ ] Feature flag for gradual rollout (if deploying to production)
- [ ] Metrics/logging for constructor violations
- [ ] Integration tests covering classification laundering scenarios

---

## Phase 0: Security Invariants (RED) - 2 hours

**Objective**: Define security properties as executable tests BEFORE implementation.

### 0.1 Create Security Invariant Tests

**File**: `tests/test_adr002a_invariants.py`

**Tests to Write** (5 core invariants):

1. **`test_invariant_plugin_cannot_create_frame_directly`**
   - Property: Plugins calling `SecureDataFrame(data, level)` → SecurityValidationError
   - Attack prevented: Classification laundering

2. **`test_invariant_datasource_can_create_frame`**
   - Property: Datasources calling `create_from_datasource()` → Success
   - Functionality preserved: Trusted sources work

3. **`test_invariant_with_uplifted_security_level_bypasses_check`**
   - Property: Internal uplifting method doesn't trigger validation
   - Functionality preserved: Uplifting still works

4. **`test_invariant_with_new_data_preserves_classification`**
   - Property: `with_new_data()` carries forward existing classification
   - Functionality preserved: LLM/aggregation patterns work

5. **`test_invariant_malicious_classification_laundering_blocked`**
   - Property: SECRET → transform → "fresh OFFICIAL" → BLOCKED
   - Attack prevented: Full attack scenario blocked

**Expected State**: All 5 tests FAIL (RED) - implementation doesn't exist yet.

**Checklist**:
- [ ] Create `tests/test_adr002a_invariants.py`
- [ ] Write all 5 test cases with clear Given/When/Then
- [ ] Run tests - verify all FAIL with clear error messages
- [ ] Document which security property each test validates

---

## Phase 1: Core Implementation (GREEN) - 3-4 hours

**Objective**: Implement minimal code to make security tests pass.

### 1.1 Update SecureDataFrame

**File**: `src/elspeth/core/security/secure_data.py`

**Changes**:

1. **Add `_created_by_datasource` field** (line ~20)
   ```python
   _created_by_datasource: bool = False
   ```

2. **Add `__post_init__` validation** (after dataclass definition)
   ```python
   def __post_init__(self):
       """Enforce datasource-only creation (ADR-002-A)."""
       import inspect

       # Skip validation for internal methods
       caller = inspect.currentframe().f_back
       if caller and caller.f_code.co_name in (
           'with_uplifted_security_level',
           'with_new_data',
           'create_from_datasource'
       ):
           return

       # Allow datasource factory
       if object.__getattribute__(self, '_created_by_datasource'):
           return

       # Block all other attempts
       raise SecurityValidationError(
           "SecureDataFrame can only be created by datasources using "
           "create_from_datasource(). Plugins must use with_uplifted_security_level() "
           "or mutate .data directly. See ADR-002-A for details."
       )
   ```

3. **Add `create_from_datasource()` class method** (after `__post_init__`)
   ```python
   @classmethod
   def create_from_datasource(
       cls,
       data: pd.DataFrame,
       classification: SecurityLevel
   ) -> "SecureDataFrame":
       """Create initial classified frame (datasources only).

       This is the ONLY way to create a SecureDataFrame from scratch.
       Plugins must use with_uplifted_security_level() or mutate .data.

       Args:
           data: The DataFrame to wrap
           classification: Initial classification level

       Returns:
           SecureDataFrame with datasource creation flag set

       Example:
           >>> df = pd.DataFrame({'col': [1, 2, 3]})
           >>> frame = SecureDataFrame.create_from_datasource(
           ...     df, SecurityLevel.SECRET
           ... )
       """
       instance = cls.__new__(cls)
       object.__setattr__(instance, 'data', data)
       object.__setattr__(instance, 'classification', classification)
       object.__setattr__(instance, '_created_by_datasource', True)
       return instance
   ```

4. **Add `with_new_data()` method** (after `with_uplifted_security_level`)
   ```python
   def with_new_data(self, new_data: pd.DataFrame) -> "SecureDataFrame":
       """Create frame with different data, preserving current classification.

       Use this when generating entirely new DataFrames (LLM responses,
       aggregations, etc.) that derive from classified input.

       IMPORTANT: Still call with_uplifted_security_level() afterwards to
       account for the transformation's security level.

       Args:
           new_data: The new DataFrame (different structure/content)

       Returns:
           SecureDataFrame with same classification, new data

       Example:
           >>> llm_output = generate_responses(input_frame.data)
           >>> output_frame = input_frame.with_new_data(llm_output)
           >>> output_frame = output_frame.with_uplifted_security_level(
           ...     self.get_security_level()
           ... )
       """
       instance = SecureDataFrame.__new__(SecureDataFrame)
       object.__setattr__(instance, 'data', new_data)
       object.__setattr__(instance, 'classification', self.classification)
       object.__setattr__(instance, '_created_by_datasource', False)
       return instance
   ```

**Checklist**:
- [ ] Add all 4 changes to `secure_data.py`
- [ ] Update `__all__` exports if needed
- [ ] Run MyPy - verify type safety
- [ ] Run Ruff - verify style
- [ ] Run Phase 0 tests - should see progress toward GREEN

### 1.2 Verify Tests Pass

**Objective**: All 5 security invariant tests should now PASS (GREEN).

**Checklist**:
- [ ] `pytest tests/test_adr002a_invariants.py -v`
- [ ] All 5/5 tests PASSING
- [ ] Review test output for any warnings

---

## Phase 2: Datasource Migration - 1-2 hours

**Objective**: Update all datasources to use `create_from_datasource()`.

### 2.1 Find All Datasource Usages

**Search Pattern**:
```bash
grep -r "SecureDataFrame(" src/elspeth/plugins/nodes/datasources/ --include="*.py"
```

**Expected Files** (~5-10):
- CSV datasources
- Azure Blob datasources
- Mock datasources for testing
- Any other datasources

### 2.2 Migration Pattern

**Before**:
```python
return SecureDataFrame(df, self.security_level)
```

**After**:
```python
return SecureDataFrame.create_from_datasource(df, self.security_level)
```

**Checklist**:
- [ ] Identify all datasource files
- [ ] Update each one to use factory method
- [ ] Run MyPy - verify no type errors
- [ ] Run Ruff - verify style
- [ ] Search for remaining direct constructor calls (should be none in datasources)

### 2.3 Update Test Fixtures

**Search Pattern**:
```bash
grep -r "SecureDataFrame(" tests/ --include="*.py" | grep -v "test_adr002a"
```

**Action**: Update any test fixtures that create `SecureDataFrame` for testing datasources.

**Checklist**:
- [ ] Find test fixtures using direct constructor
- [ ] Update to use `create_from_datasource()`
- [ ] Run affected tests - verify still passing

---

## Phase 3: Integration & Regression Testing - 1-2 hours

**Objective**: Verify no regressions, all existing functionality works.

### 3.1 Run Full Test Suite

**Tests to Run**:
```bash
# ADR-002 Phase 0-2 tests (should still pass)
pytest tests/test_adr002_invariants.py -v
pytest tests/test_adr002_validation.py -v
pytest tests/test_adr002_suite_integration.py -v

# ADR-002-A tests (should pass)
pytest tests/test_adr002a_invariants.py -v

# Suite runner characterization (should still pass)
pytest tests/test_suite_runner_characterization.py -v

# Full suite (if time permits)
pytest tests/ -k "not slow" --tb=short
```

**Expected Results**:
- ✅ All ADR-002 tests: PASSING (no regressions)
- ✅ All ADR-002-A tests: PASSING (new functionality)
- ✅ Characterization tests: PASSING (no regressions)

**Checklist**:
- [ ] ADR-002 invariants: 14/14 passing
- [ ] ADR-002 validation: 5/5 passing
- [ ] ADR-002 integration: 4/4 passing
- [ ] ADR-002-A invariants: 5/5 passing
- [ ] Suite runner characterization: 6/6 passing
- [ ] MyPy clean across entire codebase
- [ ] Ruff clean across entire codebase

### 3.2 Performance Validation

**Objective**: Verify `__post_init__` overhead is negligible.

**Test**:
```python
import timeit

setup = """
from elspeth.core.security.classified_data import SecureDataFrame
from elspeth.core.base.types import SecurityLevel
import pandas as pd

df = pd.DataFrame({'col': [1, 2, 3]})
"""

# Measure factory method creation time
result = timeit.timeit(
    "SecureDataFrame.create_from_datasource(df, SecurityLevel.SECRET)",
    setup=setup,
    number=1000
)
print(f"Average creation time: {result/1000*1000:.3f} μs")
```

**Success Criteria**: < 10μs per creation (target: 1-5μs)

**Checklist**:
- [ ] Run performance benchmark
- [ ] Creation time < 10μs per frame
- [ ] Document results in commit message

---

## Phase 4: Documentation - 1-2 hours

**Objective**: Update all relevant documentation.

### 4.1 Update SecureDataFrame Docstring

**File**: `src/elspeth/core/security/secure_data.py`

**Add to module docstring**:
```python
"""SecureDataFrame: Trusted container for classified data (ADR-002 & ADR-002-A).

Lifecycle:
1. Datasources create initial frames via create_from_datasource()
2. Plugins transform data via mutation or with_new_data()
3. Plugins uplift classification via with_uplifted_security_level()
4. Runtime validation via validate_compatible_with() before access

Security Properties (ADR-002-A):
- Only datasources can create frames (constructor protected)
- Plugins can only uplift, never relabel (no direct constructor access)
- Classification uplifting is automatic (max() operation)
- Data mutations are explicit (.data attribute is mutable)

Plugin Patterns:
    # Pattern 1: In-place mutation (recommended)
    def process(self, frame: SecureDataFrame) -> SecureDataFrame:
        frame.data['processed'] = transform(frame.data['input'])
        return frame.with_uplifted_security_level(self.get_security_level())

    # Pattern 2: New data generation
    def process(self, frame: SecureDataFrame) -> SecureDataFrame:
        new_df = self.llm.generate(...)
        return frame.with_new_data(new_df).with_uplifted_security_level(
            self.get_security_level()
        )
"""
```

### 4.2 Update THREAT_MODEL.md

**File**: `ADR002_IMPLEMENTATION/THREAT_MODEL.md`

**Update T4 section** (around line 150):
```markdown
### T4: Classification Mislabeling

**Defense Layers**:
- **Primary (Constructor Protection - ADR-002-A)**: ✅ TECHNICAL CONTROL
  - SecureDataFrame.__post_init__() blocks plugin creation
  - Only datasources can create frames via create_from_datasource()
  - Plugins MUST use with_uplifted_security_level() (no alternative)
  - Enforced by constructor validation

- **Secondary (Automatic Uplifting)**: ✅ TECHNICAL CONTROL
  - SecureDataFrame.with_uplifted_security_level() uses max()
  - Classification can only increase, never decrease
  - Immutable via frozen dataclass

- **Certification (Reduced Scope)**: ⚠️ HUMAN REVIEW
  - Verify get_security_level() honesty only
  - No longer need to review every transformation
```

### 4.3 Update Plugin Development Guide

**File**: `docs/development/plugin-development-guide.md` (or create if doesn't exist)

**Add section**:
```markdown
## Working with SecureDataFrame

### Creating Classified Frames

**Datasources** (trusted sources):
```python
# ✅ CORRECT - Use factory method
frame = SecureDataFrame.create_from_datasource(
    data=df,
    security_level=SecurityLevel.SECRET
)
```

**Plugins** (transformations):
```python
# ❌ WRONG - Direct constructor blocked
frame = SecureDataFrame(df, SecurityLevel.OFFICIAL)  # SecurityValidationError!

# ✅ CORRECT - Mutate existing frame
def process(self, frame: SecureDataFrame) -> SecureDataFrame:
    frame.data['new_col'] = transform(frame.data['input'])
    return frame.with_uplifted_security_level(self.get_security_level())

# ✅ CORRECT - Generate new data
def process(self, frame: SecureDataFrame) -> SecureDataFrame:
    new_df = self.generate(frame.data)
    return frame.with_new_data(new_df).with_uplifted_security_level(
        self.get_security_level()
    )
```

**Checklist**:
- [ ] Update `secure_data.py` module docstring
- [ ] Update `THREAT_MODEL.md` T4 section
- [ ] Create/update plugin development guide
- [ ] Add examples to all new methods
- [ ] Review documentation for clarity

---

## Phase 5: Commit & Review - 30 minutes

**Objective**: Clean commit with comprehensive documentation.

### 5.1 Pre-Commit Checklist

- [ ] All tests passing (ADR-002 + ADR-002-A)
- [ ] MyPy clean
- [ ] Ruff clean
- [ ] Performance validated (<10μs overhead)
- [ ] Documentation complete
- [ ] No debug code or TODOs
- [ ] Git status clean (no untracked changes)

### 5.2 Commit Message Template

```
Feat: ADR-002-A - Trusted Container Model for SecureDataFrame

**What**: Constructor protection preventing plugins from creating arbitrary classifications.

**Why**: Moves T4 (Classification Mislabeling) defense from certification to technical control.

**How**:
- Added __post_init__ validation with frame inspection (~15 lines)
- Added create_from_datasource() factory method for datasources
- Added with_new_data() for plugins generating new DataFrames
- Migrated X datasources to use factory method

**Security Properties**:
- ✅ Prevents classification laundering (SECRET → "fresh OFFICIAL")
- ✅ Only datasources can create initial classifications
- ✅ Plugins can only uplift, never relabel
- ✅ Reduces certification burden (no transformation review needed)

**Tests** (5/5 passing):
- test_invariant_plugin_cannot_create_frame_directly
- test_invariant_datasource_can_create_frame
- test_invariant_with_uplifted_security_level_bypasses_check
- test_invariant_with_new_data_preserves_classification
- test_invariant_malicious_classification_laundering_blocked

**Performance**: <Xμs creation overhead (target: <10μs)

**Regression Testing**:
- ✅ ADR-002 invariants: 14/14 passing
- ✅ ADR-002 validation: 5/5 passing
- ✅ ADR-002 integration: 4/4 passing
- ✅ Suite runner characterization: 6/6 passing

**Documentation**:
- Updated SecureDataFrame module docstring
- Updated THREAT_MODEL.md T4 section
- Added plugin development guide section

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Risk Mitigation

### Risk 1: Frame Inspection Edge Cases

**Risk**: `inspect.currentframe()` might fail in async, decorators, or unusual call stacks.

**Mitigation**:
- Add comprehensive test cases for edge cases
- Consider feature flag: `ADR_002A_ENFORCE=true/false`
- Document known limitations if any found

### Risk 2: Migration Mistakes

**Risk**: Missing a datasource during migration could cause runtime errors.

**Mitigation**:
- Use grep to verify no remaining direct constructor calls in datasources
- Run full test suite (catches test fixtures)
- Code review before merge

### Risk 3: Performance Overhead

**Risk**: Frame inspection might be slow.

**Mitigation**:
- Benchmark before committing
- If overhead > 10μs, add caching or feature flag
- Document performance characteristics

---

## Timeline Estimate

| Phase | Duration | Complexity |
|-------|----------|-----------|
| Phase 0: Security Invariants | 2h | Simple - Test writing |
| Phase 1: Core Implementation | 3-4h | Moderate - Frame inspection |
| Phase 2: Datasource Migration | 1-2h | Simple - Find/replace |
| Phase 3: Integration Testing | 1-2h | Simple - Run tests |
| Phase 4: Documentation | 1-2h | Simple - Update docs |
| Phase 5: Commit & Review | 0.5h | Simple - Git workflow |
| **Total** | **8.5-11.5h** | **~1.5 work days** |

**Buffer**: +20% for unexpected issues = **10-14 hours total**

---

## Success Metrics

### Technical
- [ ] 5/5 security invariant tests passing
- [ ] 0 regressions (all existing tests pass)
- [ ] <10μs creation overhead
- [ ] MyPy clean, Ruff clean

### Security
- [ ] Classification laundering attack blocked
- [ ] T4 defense moved from certification to technical
- [ ] Attack surface reduced (no direct constructor)

### Quality
- [ ] Clear error messages for violations
- [ ] Comprehensive documentation
- [ ] Plugin patterns documented with examples

---

## Next Actions

1. ✅ Read this plan
2. ⏸️ Start Phase 0 (create security invariant tests)
3. ⏸️ Execute phases sequentially with clear gates
4. ⏸️ Update this document as we discover issues

---

**Remember**: Security implementation is like surgery - sterile technique matters more than speed. Take time to get it right.
