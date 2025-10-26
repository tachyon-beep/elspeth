# ADR 002/003/004 Migration - Current State Assessment

**Assessment Date**: 2025-10-26
**Methodology**: Five-Phase Zero-Regression Refactoring (see `docs/refactoring/METHODOLOGY.md`)
**Status**: Phase 0 - Safety Net Construction (IN PROGRESS)

---

## Executive Summary

**Problem**: Plugins are inconsistent, not current, and need to be brought to spec. We discovered a critical security flaw (inverted Bell-LaPadula logic) mid-migration, which broke the previous migration work in half.

**Approach**: Restart migration from first principles using test-first methodology, bringing plugins to spec **one at a time**, with comprehensive test coverage proving correctness at each step.

**Critical Insight from User**: "all our plugins are inconsistent, not current and need to be brought up to spec, but we're doing it on a plugin by plugin basis, so our test structure is invaluable to get the proof we need"

---

## What We Know Works (Recent Implementations)

### ✅ BasePlugin ABC (ADR-004) - IMPLEMENTED 2025-10-26

**File**: `src/elspeth/core/base/plugin.py`

**Status**: ✅ Fully implemented with ADR-005 frozen plugin capability

**Key Features**:
- Abstract Base Class with **concrete security enforcement** (not Protocol)
- Mandatory `security_level` parameter (keyword-only)
- **Sealed methods** (@final + __init_subclass__ runtime enforcement):
  - `get_security_level()` - returns security clearance
  - `validate_can_operate_at_level()` - enforces Bell-LaPadula "no read up"
- **ADR-005 frozen plugin capability**: `allow_downgrade: bool = True` parameter
  - `allow_downgrade=True` (default): Trusted downgrade, can operate at lower levels
  - `allow_downgrade=False` (frozen): Must operate at exact declared level only
- Read-only properties: `security_level`, `allow_downgrade`
- Prevents override attempts at class definition time (TypeError)

**Validation Logic** (CORRECTED Bell-LaPadula):
```python
def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
    # Check 1: Insufficient clearance (Bell-LaPadula "no read up")
    if operating_level > self._security_level:
        raise SecurityValidationError(...)  # Plugin clearance TOO LOW

    # Check 2: Frozen plugin downgrade rejection (ADR-005)
    if operating_level < self._security_level and not self._allow_downgrade:
        raise SecurityValidationError(...)  # Frozen plugin, must match exactly
```

**Test Coverage**: 33/33 tests passing in `tests/test_baseplugin_frozen.py`

---

### ✅ SecureDataFrame (ADR-002-A) - IMPLEMENTED

**File**: `src/elspeth/core/security/secure_data.py`

**Status**: ✅ Fully implemented with constructor protection

**Key Features**:
- Frozen dataclass (immutable classification)
- **Constructor protection** via `__post_init__` stack inspection
- Datasource-only creation via `create_from_datasource()` factory
- Plugin-safe methods:
  - `with_uplifted_security_level()` - uplift to higher level (prevents downgrade)
  - `with_new_data()` - generate new data, preserve classification
- Fail-closed behavior when stack inspection unavailable
- Prevents classification laundering attacks (T4 threat)

**Current Name**: `SecureDataFrame` (NOT renamed to `SecureDataFrame` yet)
**Current Field**: `.classification` (NOT renamed to `.security_level` yet)

**Usage Status**: ❌ **NOT used by datasources** - they return plain `pd.DataFrame`

---

### ✅ Suite Runner Validation (ADR-002) - IMPLEMENTED

**File**: `src/elspeth/core/experiments/suite_runner.py` (lines 646-663)

**Status**: ✅ Validation logic implemented and CALLS plugin validation

```python
# Compute minimum clearance envelope (weakest-link principle)
operating_level = compute_minimum_clearance_envelope(plugins)

# Validate ALL plugins can operate at this level (fail-fast if any rejects)
for plugin in plugins:
    try:
        plugin.validate_can_operate_at_level(operating_level)
    except SecurityValidationError as e:
        raise SecurityValidationError(f"ADR-002 Start-Time Validation Failed...") from e
```

**Key Insight**: Validation code ASSUMES plugins have `validate_can_operate_at_level()` method.

**Risk**: If ANY plugin doesn't inherit from BasePlugin, this will raise `AttributeError` at runtime.

---

## What's Partially Done

### ⚠️ Datasource Plugins - PARTIAL COMPLIANCE

**Example**: `src/elspeth/plugins/nodes/sources/_csv_base.py`

**Status**: ✅ Inherits from BasePlugin, ❌ Returns plain DataFrame (not SecureDataFrame)

```python
class BaseCSVDataSource(BasePlugin, DataSource):
    """Base class for CSV datasources with common functionality.

    Inherits from BasePlugin to provide security enforcement (ADR-004).
    """

    def __init__(self, *, security_level: SecurityLevel, ...):
        # ✅ CORRECT: Calls BasePlugin.__init__()
        super().__init__(security_level=security_level)
        ...

    def load(self) -> pd.DataFrame:
        # ❌ WRONG: Returns plain DataFrame, not SecureDataFrame
        df = pd.read_csv(self.path, ...)
        df.attrs["security_level"] = self.security_level  # ← Metadata only, not container
        return df
```

**What Works**:
- ✅ Inherits from BasePlugin (nominal typing)
- ✅ Calls `super().__init__(security_level=security_level)`
- ✅ `get_security_level()` works (inherited from BasePlugin)
- ✅ `validate_can_operate_at_level()` works (inherited from BasePlugin)
- ✅ Security level validation will run in suite_runner

**What's Missing**:
- ❌ Doesn't use `SecureDataFrame.create_from_datasource()`
- ❌ Returns plain `pd.DataFrame` with `attrs` metadata (not secure container)
- ❌ No constructor protection on returned data
- ❌ No uplifting enforcement at data boundaries

**Known Datasources** (from archive docs):
1. `_csv_base.py` - BaseCSVDataSource (base class)
2. `csv_local.py` - CSVDataSource
3. `csv_blob.py` - CSVBlobDataSource
4. `blob.py` - BlobDataSource

**Compliance Status**: UNKNOWN - need to check each individually

---

### ⚠️ LLM Client Plugins - UNKNOWN COMPLIANCE

**Location**: `src/elspeth/plugins/nodes/transforms/llm/*.py`

**Known Clients** (from archive docs):
1. `azure_openai.py` - AzureOpenAIClient
2. `openai_http.py` - OpenAIHTTPClient
3. `mock_llm.py` - MockLLMClient
4. `static_llm.py` - StaticLLMClient
5. (Plus middleware wrappers)

**Status**: UNKNOWN - need to check if they:
- ✅ Inherit from BasePlugin?
- ✅ Call `super().__init__(security_level=...)`?
- ❓ Handle SecureDataFrame?
- ❓ Uplift security levels correctly?

---

### ⚠️ Sink Plugins - UNKNOWN COMPLIANCE

**Location**: `src/elspeth/plugins/nodes/sinks/*.py`

**Known Sinks** (from archive docs): 16 implementations
- CSV, Excel, JSON, Markdown, visual analytics, signed bundles, repositories, etc.

**Status**: UNKNOWN - need to check if they:
- ✅ Inherit from BasePlugin?
- ✅ Call `super().__init__(security_level=...)`?
- ❓ Accept SecureDataFrame?
- ❓ Validate security levels at write time?

---

## What's NOT Done

### ❌ Terminology Rename (SecureDataFrame → SecureDataFrame)

**Status**: NOT STARTED

**Scope** (from archive assessment):
- 86 files, 1,450 occurrences
- Rename: `SecureDataFrame` → `SecureDataFrame`
- Rename: `.classification` → `.security_level`
- Rename: `classified_material` middleware → `sensitive_material`

**Rationale**: "Secure data" is more universally applicable (healthcare, finance, enterprise) than "classified data" (government-specific)

**Blockers**: Should we do this FIRST or AFTER plugin migration?

---

### ❌ Secure Container Adoption (ADR-003)

**Status**: NOT STARTED

**Goal**: All datasources return `SecureDataFrame` (or `SecureDataFrame` after rename)

**Current**: Datasources return plain `pd.DataFrame` with `.attrs` metadata

**Required Changes**:
```python
# BEFORE (current)
def load(self) -> pd.DataFrame:
    df = pd.read_csv(self.path, ...)
    df.attrs["security_level"] = self.security_level
    return df

# AFTER (target)
def load(self) -> SecureDataFrame:
    df = pd.read_csv(self.path, ...)
    return SecureDataFrame.create_from_datasource(df, self.security_level)
```

**Downstream Impact**: Orchestrator, runner, suite_runner must accept SecureDataFrame

---

### ❌ Generic SecureData[T] Wrapper (ADR-004)

**Status**: NOT STARTED

**Goal**: Type-safe security level propagation for dicts, metadata, middleware context

**Current**: Only `SecureDataFrame` exists (DataFrame-specific)

**Need**: Generic wrapper for ANY data type:
```python
@dataclass(frozen=True)
class SecureData[T]:
    data: T
    security_level: SecurityLevel

    def with_uplifted_security_level(self, new_level: SecurityLevel) -> SecureData[T]:
        return SecureData(data=self.data, security_level=max(self.security_level, new_level))
```

**Use Cases**:
- Row context dicts (middleware processing)
- Aggregation results
- Metadata propagation
- Baseline comparison data

---

## Critical Questions for Phase 0

### Q1: Which Plugins Currently Inherit from BasePlugin?

**Need**: Inventory of ALL plugins with compliance status

**Method**:
1. Find all plugin classes
2. Check if they inherit from BasePlugin
3. Check if they call `super().__init__(security_level=...)`
4. Check if they override security methods (should raise TypeError)

**Output**: Compliance matrix (plugin × compliance checks)

---

### Q2: What Validation Logic Currently Runs?

**Need**: Understand what security checks are actually enforced vs. assumed

**Method**:
1. Trace validation calls in suite_runner
2. Check if hasattr() defensive checks exist (allow short-circuit)
3. Verify isinstance(plugin, BasePlugin) checks use ABC (not Protocol)
4. Test that AttributeError raised for non-compliant plugins

**Output**: Validation flow diagram (what runs, what's skipped, what fails)

---

### Q3: What Tests Currently Exist?

**Need**: Understand existing test coverage before building safety net

**Method**:
1. Find all ADR-002 tests (`tests/test_adr002*.py`)
2. Find all BasePlugin tests (`tests/test_baseplugin*.py`)
3. Find all datasource/sink/LLM tests
4. Measure coverage on validation code paths

**Output**: Test inventory with coverage metrics

---

### Q4: What Breaks with ADR-005 Changes?

**User Statement**: "we also added ADR-005 which likely broke ADR-002"

**Need**: Understand what ADR-005 (allow_downgrade) broke

**Hypothesis**: Old tests assumed **INVERTED** Bell-LaPadula logic:
- OLD (wrong): `operating_level < self.security_level` → REJECT
- NEW (correct): `operating_level > self.security_level` → REJECT

**Method**:
1. Run existing ADR-002 tests
2. Identify failures
3. Check if failures are due to inverted logic assumptions
4. Mark tests with warnings if based on wrong logic

**Output**: Test failure report with root cause analysis

---

## Proposed Phase 0 Plan (Safety Net Construction)

### Phase 0.1: Comprehensive Plugin Inventory (3-4 hours)

**Deliverable**: `01-PLUGIN_INVENTORY.md` with compliance matrix

**Tasks**:
1. Find all plugin classes (datasources, transforms, sinks, experiments)
2. Check BasePlugin inheritance (nominal typing)
3. Check `super().__init__(security_level=...)` calls
4. Check for override attempts (should raise TypeError)
5. Check return types (DataFrame vs. SecureDataFrame)

**Output Format**:
```markdown
| Plugin Class | Location | Inherits BasePlugin? | Calls super().__init__? | Returns Secure Container? | Compliance Status |
|--------------|----------|---------------------|------------------------|--------------------------|-------------------|
| BaseCSVDataSource | sources/_csv_base.py | ✅ YES | ✅ YES | ❌ NO (plain DataFrame) | PARTIAL |
| AzureOpenAIClient | transforms/llm/azure_openai.py | ❓ UNKNOWN | ❓ UNKNOWN | ❓ UNKNOWN | NEEDS CHECK |
...
```

---

### Phase 0.2: Validation Flow Analysis (2-3 hours)

**Deliverable**: `02-VALIDATION_FLOW.md` with call graph

**Tasks**:
1. Trace suite_runner validation logic
2. Identify all validation call sites
3. Check for defensive hasattr() checks (short-circuit risk)
4. Verify isinstance() uses BasePlugin ABC (not Protocol)
5. Test AttributeError for non-compliant plugins

**Output**: Validation call graph showing:
- What validation SHOULD run (ADR-002 design)
- What validation ACTUALLY runs (current code)
- What validation is SKIPPED (defensive checks)
- What validation FAILS (missing methods)

---

### Phase 0.3: Test Inventory & Coverage (2-3 hours)

**Deliverable**: `03-TEST_INVENTORY.md` with coverage metrics

**Tasks**:
1. List all existing security tests
2. Run tests, identify failures
3. Measure coverage on critical paths (validation, uplifting, container creation)
4. Identify gaps in test coverage

**Output**:
- Test count by category (BasePlugin, validation, containers, plugins)
- Coverage % on critical modules
- List of failing tests with root cause
- Gaps in coverage (untested scenarios)

---

### Phase 0.4: Characterization Tests (4-6 hours)

**Deliverable**: `tests/test_adr002_003_004_characterization.py` (NEW FILE)

**Purpose**: Document current behavior (both correct and broken)

**Test Categories**:
1. **Compliance Tests** - Which plugins inherit from BasePlugin?
2. **Validation Tests** - Does validation actually run?
3. **Container Tests** - Do datasources use SecureDataFrame?
4. **Security Tests** - Are security properties enforced?

**Pattern**:
```python
def test_datasource_basepl<bolthole>in_compliance():
    """CHARACTERIZATION: Prove datasources inherit from BasePlugin."""
    from elspeth.core.base.plugin import BasePlugin
    ds = BaseCSVDataSource(path="test.csv", security_level=SecurityLevel.SECRET, retain_local=False)
    assert isinstance(ds, BasePlugin)  # ✅ Should PASS (already compliant)

def test_datasource_returns_classified_dataframe():
    """CHARACTERIZATION: Prove datasources DON'T use SecureDataFrame yet."""
    ds = BaseCSVDataSource(path="test.csv", security_level=SecurityLevel.SECRET, retain_local=False)
    result = ds.load()
    assert isinstance(result, pd.DataFrame)  # ✅ Currently TRUE
    assert not isinstance(result, SecureDataFrame)  # ✅ Currently TRUE (NOT using secure container)
```

---

### Phase 0.5: Security Property Tests (4-6 hours)

**Deliverable**: `tests/test_adr002_003_004_security_properties.py` (NEW FILE)

**Purpose**: Define MUST-HAVE security behaviors (many will be @pytest.mark.xfail initially)

**Test Categories**:
1. **T1 Prevention** - Pipeline minimum level computed correctly?
2. **T2 Prevention** - Plugins cannot lie about clearance?
3. **T3 Prevention** - Runtime validation catches start-time bypass?
4. **T4 Prevention** - Constructor protection prevents laundering?

**Pattern**:
```python
@pytest.mark.xfail(reason="Datasources don't use SecureDataFrame yet", strict=True)
def test_datasource_returns_secure_container():
    """SECURITY PROPERTY: Datasources MUST return SecureDataFrame."""
    ds = BaseCSVDataSource(path="test.csv", security_level=SecurityLevel.SECRET, retain_local=False)
    result = ds.load()
    assert isinstance(result, SecureDataFrame)  # ❌ Will FAIL (not using container yet)

@pytest.mark.xfail(reason="ADR-002 validation may not run for all plugins", strict=True)
def test_validation_runs_for_all_plugins():
    """SECURITY PROPERTY: Validation MUST run for ALL plugins."""
    # Test that SECRET datasource + UNOFFICIAL sink is BLOCKED
    ...
```

---

## Success Criteria for Phase 0

**Exit Criteria** (before ANY code changes):
- ✅ Complete plugin inventory (all 26+ plugins cataloged)
- ✅ Validation flow documented (call graph + trace)
- ✅ Test inventory complete (all existing tests identified)
- ✅ Characterization tests written (document current behavior)
- ✅ Security property tests written (define target behavior)
- ✅ Coverage ≥80% on validation code paths
- ✅ All stakeholders understand current state
- ✅ Risk assessment complete (top 3-5 risks identified)

**Estimated Effort**: 15-22 hours (2-3 days)

**Why This Is Critical**: Without comprehensive tests FIRST, we risk:
- Breaking working functionality
- Missing security regressions
- Incomplete migration (plugins left in inconsistent state)
- False confidence from passing tests that don't test real plugins

---

## Next Steps

1. ⭕ Complete this assessment (IN PROGRESS)
2. ⭕ Execute Phase 0.1: Plugin Inventory (3-4 hours)
3. ⭕ Execute Phase 0.2: Validation Flow Analysis (2-3 hours)
4. ⭕ Execute Phase 0.3: Test Inventory & Coverage (2-3 hours)
5. ⭕ Execute Phase 0.4: Characterization Tests (4-6 hours)
6. ⭕ Execute Phase 0.5: Security Property Tests (4-6 hours)
7. ⭕ Phase 0 Review: Verify exit criteria met
8. ⭕ Phase 1: Begin systematic plugin migration (ONE plugin at a time)

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

**Assessment Date**: 2025-10-26
**Author**: Migration Planning Team
**Status**: Phase 0 - Safety Net Construction (IN PROGRESS)
