# VULN-001/002: SecureDataFrame Trusted Container Implementation

**Priority**: P0 (CRITICAL)
**Effort**: 48-64 hours (2-3 weeks)
**Sprint**: Sprint 1
**Status**: NOT STARTED
**Pre-1.0**: Breaking changes acceptable, no backwards compatibility required

---

## Vulnerability Description

### VULN-001: ADR-002-A Trusted Container Not Implemented

**Finding**: ADR-002 describes a two-layer security model:
1. **Plugin Clearance** - What the plugin is authorized to process (Phase 2: ✅ COMPLETE)
2. **Data Classification** - What classification level the data actually contains (Phase 1: ❌ NOT IMPLEMENTED)

**Impact**: System validates plugin clearance but never validates data classification. A datasource could claim "UNOFFICIAL" but return SECRET data, and no validation would catch this.

### VULN-002: No Runtime Data Classification Validation

**Finding**: DataFrames flow through the system as plain `pd.DataFrame` objects with no runtime enforcement of their claimed security_level (stored in `df.attrs["security_level"]`).

**Impact**:
- Malicious datasources can lie about classification
- Data classification can be stripped or modified in transit
- No fail-safe validation before data reaches plugins

**Attack Scenario**:
```python
# Datasource claims UNOFFICIAL but returns SECRET data
datasource.security_level = "UNOFFICIAL"  # Plugin accepts this clearance
df = datasource.load()  # Returns DataFrame with PII/classified content
df.attrs["security_level"] = "UNOFFICIAL"  # Lie about classification

# Pipeline validates plugin clearance only:
# ✅ Plugin has UNOFFICIAL clearance - OK to process UNOFFICIAL data
# ❌ No validation that df ACTUALLY contains only UNOFFICIAL data

# SECRET data flows to UNOFFICIAL plugin - SECURITY BREACH
```

---

## Current State Analysis

### What Exists Today

**ADR-002 Section 4.1.1: "Trusted Container Pattern"**
```
DataFrames should be wrapped in a SecureDataFrame container that:
- Stores the true classification level immutably
- Validates classification matches datasource declaration
- Prevents downgrading without explicit trusted operations
- Fails closed if classification cannot be determined
```

**Status**: Documented in ADR but **never implemented**.

### What's Missing

1. **`SecureDataFrame` class** - Trusted wrapper around pd.DataFrame
2. **Datasource integration** - All datasources must return SecureDataFrame
3. **Pipeline validation** - Runtime checks before plugin execution
4. **Classification inference** - Automatic detection when datasource doesn't declare level
5. **Fail-closed enforcement** - Reject DataFrames with mismatched classification

### Files Requiring Changes

**Core Framework**:
- `src/elspeth/core/data/classified_dataframe.py` (NEW) - SecureDataFrame implementation
- `src/elspeth/core/security/classification.py` (NEW) - Classification inference rules
- `src/elspeth/core/security/__init__.py` - Export SecureDataFrame

**Datasources** (8 files to update):
- `src/elspeth/plugins/nodes/sources/csv_local.py`
- `src/elspeth/plugins/nodes/sources/csv_blob.py`
- `src/elspeth/plugins/nodes/sources/dataframe_in_memory.py`
- `src/elspeth/plugins/nodes/sources/noop.py`
- Plus Azure-specific datasources if enabled

**Orchestration**:
- `src/elspeth/core/orchestrator.py` - Validate classification before run()
- `src/elspeth/core/experiments/runner.py` - Validate before experiment execution
- `src/elspeth/core/experiments/suite_runner.py` - Validate per-experiment

**Tests** (convert XFAIL → PASS):
- `tests/test_adr002_baseplugin_compliance.py` - 6 xfailed tests should pass

---

## Design Decisions

### 1. SecureDataFrame API Contract (ADR-002-A Pattern)

```python
from elspeth.core.data.classified_dataframe import SecureDataFrame
from elspeth.core.base.types import SecurityLevel

# Creation (datasource-only operation via factory)
# Direct construction is BLOCKED by stack inspection
cdf = SecureDataFrame.create_from_datasource(
    data=pd.DataFrame(...),
    security_level=SecurityLevel.OFFICIAL
)

# Access (read-only container, mutable content)
df: pd.DataFrame = cdf.data  # Get underlying DataFrame (mutable!)
level: SecurityLevel = cdf.classification  # Get classification (immutable)

# Validation (pipeline operation)
cdf.validate_compatible_with(plugin_clearance=SecurityLevel.OFFICIAL)
# Raises SecurityValidationError if classification > clearance

# Trusted mutation (plugins only)
# Pattern 1: In-place mutation (recommended)
cdf.data['new_column'] = transform(cdf.data['input'])
uplifted_cdf = cdf.with_uplifted_security_level(SecurityLevel.SECRET)

# Pattern 2: New data generation
new_df = generate_new_dataframe()
new_cdf = cdf.with_new_data(new_df).with_uplifted_security_level(SecurityLevel.SECRET)
```

**Key Properties (ADR-002-A)**:
- **Factory-only creation** - Direct `SecureDataFrame(...)` blocked by stack inspection
- **Container immutability** - Classification cannot change (frozen dataclass)
- **Content mutability** - `.data` DataFrame is explicitly mutable for transforms
- **Uplifting-only** - `with_uplifted_security_level()` enforces monotonic increase
- **No downgrade API** - Bell-LaPadula "no write down" enforcement
- **Fail-closed** - Stack inspection failure raises SecurityValidationError

### 2. Datasource Integration Pattern (ADR-002-A)

**Before (Phase 2 - VULNERABLE)**:
```python
class LocalCSVDataSource(BasePlugin, DataSource):
    def load(self) -> pd.DataFrame:
        df = pd.read_csv(self.path)
        df.attrs["security_level"] = self.security_level  # String, mutable
        return df
```

**After (Phase 1 - SECURE with Factory Method)**:
```python
class LocalCSVDataSource(BasePlugin, DataSource):
    def load(self) -> SecureDataFrame:
        df = pd.read_csv(self.path)
        # MUST use factory method (direct construction blocked)
        return SecureDataFrame.create_from_datasource(
            data=df,
            security_level=self.security_level  # Typed, immutable
        )
```

**Migration Strategy** (Pre-1.0 - Breaking Change):
- Return type changes from `pd.DataFrame` → `SecureDataFrame`
- ❌ NO backwards compatibility (pre-1.0 development)
- All datasources updated in single commit
- Pipeline code extracts `.data` where needed

### 3. Pipeline Validation Points

**Three validation checkpoints**:

1. **Orchestrator.run()** - Before experiment execution
```python
def run(self) -> dict[str, Any]:
    cdf = self.datasource.load()  # Returns SecureDataFrame

    # Validate: datasource classification ≤ pipeline operating level
    pipeline_level = compute_minimum_clearance(plugins)
    cdf.validate_compatible_with(pipeline_level)

    df = cdf.data  # Extract plain DataFrame for runner
    payload = self.experiment_runner.run(df)
```

2. **ExperimentRunner.run()** - Before row processing
```python
def run(self, df_or_cdf) -> dict[str, Any]:
    if isinstance(df_or_cdf, SecureDataFrame):
        df_or_cdf.validate_compatible_with(self.security_level)
        df = df_or_cdf.data
    else:
        df = df_or_cdf  # Backward compat
```

3. **ExperimentSuiteRunner._prepare_experiment()** - Per-experiment
```python
def _prepare_experiment(self, experiment, ctx):
    # Validate: experiment operating level compatible with suite level
    operating_level = compute_minimum_clearance_envelope(plugins)
    ctx.classified_df.validate_compatible_with(operating_level)
```

### 4. Stack Inspection for Constructor Protection (ADR-002-A)

**Constructor Protection Pattern**:
```python
@dataclass(frozen=True)
class SecureDataFrame:
    data: pd.DataFrame
    classification: SecurityLevel
    _created_by_datasource: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """Validate caller identity - only factory methods allowed."""
        # Allow factory method bypass
        if object.__getattribute__(self, '_created_by_datasource'):
            return

        # SECURITY: Fail-closed when stack inspection unavailable
        frame = inspect.currentframe()
        if frame is None:
            raise SecurityValidationError(
                "Cannot verify caller identity - stack inspection unavailable. "
                "SecureDataFrame creation blocked."
            )

        # Walk stack to find trusted methods
        trusted_callers = {'with_uplifted_security_level', 'with_new_data'}
        current = frame.f_back

        while current is not None:
            func_name = current.f_code.co_name
            if func_name in trusted_callers:
                # Verify caller's 'self' is SecureDataFrame instance
                caller_self = current.f_locals.get('self')
                if isinstance(caller_self, SecureDataFrame):
                    return
            current = current.f_back

        # No trusted caller found - block construction
        raise SecurityValidationError(
            "SecureDataFrame() constructor blocked - use factory method. "
            "Datasources must use create_from_datasource(). "
            "Plugins must use with_new_data() or with_uplifted_security_level()."
        )

    @classmethod
    def create_from_datasource(cls, data: pd.DataFrame,
                              classification: SecurityLevel) -> "SecureDataFrame":
        """Create initial classified frame (datasources only)."""
        obj = object.__new__(cls)
        object.__setattr__(obj, 'data', data)
        object.__setattr__(obj, 'classification', classification)
        object.__setattr__(obj, '_created_by_datasource', True)
        # Bypass __post_init__ validation
        return obj
```

**Key Security Properties**:
- Direct construction raises `SecurityValidationError`
- Stack inspection verifies trusted caller
- Fail-closed when inspection unavailable
- Factory method bypasses check via flag

---

## Implementation Phases (TDD Approach)

### Phase 1.0: SecureDataFrame Core with Stack Inspection (12-16 hours)

**Deliverables**:
- [ ] `SecureDataFrame` frozen dataclass with immutable `classification`
- [ ] `.data` property (mutable DataFrame)
- [ ] `.classification` property (immutable SecurityLevel)
- [ ] `.__post_init__()` with stack inspection to block direct construction
- [ ] `.create_from_datasource()` class method (factory pattern)
- [ ] `.with_new_data()` method for plugin data generation
- [ ] `.with_uplifted_security_level()` method (monotonic increase only)
- [ ] `.validate_compatible_with(clearance)` method

**TDD Cycle**:
```python
# RED: Write failing test for constructor blocking
def test_direct_construction_blocked():
    with pytest.raises(SecurityValidationError, match="constructor blocked"):
        SecureDataFrame(
            data=pd.DataFrame({"col": [1, 2, 3]}),
            security_level=SecurityLevel.OFFICIAL
        )

# GREEN: Implement __post_init__ with stack inspection
def __post_init__(self) -> None:
    if object.__getattribute__(self, '_created_by_datasource'):
        return
    frame = inspect.currentframe()
    if frame is None:
        raise SecurityValidationError("Stack inspection unavailable")
    # Walk stack to find trusted callers...

# REFACTOR: Add complete stack walking, error messages, docstrings
```

**Test Coverage Target**: 100% (20-25 tests including stack inspection edge cases)

### Phase 1.1: Datasource Integration (12-16 hours)

**Deliverables**:
- [ ] Update 8 datasource plugins to use `create_from_datasource()` factory
- [ ] ❌ NO backwards compatibility (pre-1.0 breaking change)
- [ ] Integration tests for each datasource
- [ ] Update all datasources in single commit

**TDD Cycle (per datasource)**:
```python
# RED
def test_local_csv_returns_classified_dataframe():
    ds = LocalCSVDataSource(path="test.csv")
    result = ds.load()
    assert isinstance(result, SecureDataFrame)
    assert result.classification == SecurityLevel.OFFICIAL

# GREEN
def load(self) -> SecureDataFrame:
    df = pd.read_csv(self.path)
    # MUST use factory method (direct construction blocked)
    return SecureDataFrame.create_from_datasource(
        data=df,
        security_level=self.security_level
    )

# REFACTOR: Add error handling, path validation
```

**Test Coverage Target**: 90% (40-50 tests, 5-6 per datasource)

### Phase 1.2: Pipeline Validation (12-16 hours)

**Deliverables**:
- [ ] Validation in `Orchestrator.run()`
- [ ] Validation in `ExperimentRunner.run()`
- [ ] Validation in `ExperimentSuiteRunner._prepare_experiment()`
- [ ] Clear error messages for classification mismatches

**TDD Cycle**:
```python
# RED
def test_orchestrator_rejects_misclassified_data():
    # Plugin has UNOFFICIAL clearance
    plugin = create_plugin(security_level="UNOFFICIAL")

    # Datasource returns SECRET data
    datasource = MockDataSource(security_level="SECRET")

    orchestrator = Orchestrator(datasource=datasource, plugins=[plugin])

    with pytest.raises(SecurityValidationError, match="SECRET data.*UNOFFICIAL plugin"):
        orchestrator.run()

# GREEN
def run(self):
    cdf = self.datasource.load()
    cdf.validate_compatible_with(self.operating_level)  # Raises if mismatch
    return self.runner.run(cdf.data)

# REFACTOR: Add context to errors, log validation success
```

**Test Coverage Target**: 95% (25-30 tests)

### Phase 1.3: Convert XFAIL Tests (4-6 hours)

**Deliverables**:
- [ ] Remove `@pytest.mark.xfail` from 6 tests in `test_adr002_baseplugin_compliance.py`
- [ ] Verify tests now PASS with SecureDataFrame
- [ ] Update test documentation

**Target Tests**:
1. `test_validate_raises_on_security_mismatch`
2. `test_validate_succeeds_when_safe`
3. `test_registry_rejects_plugin_without_baseplugin`
4. `test_registry_accepts_plugin_with_baseplugin`
5. `test_secret_datasource_unofficial_sink_blocked`
6. `test_matching_security_levels_allowed`

**Success Criteria**: All 6 tests PASS without modification

### Phase 1.4: Documentation & Audit (4-6 hours)

**Deliverables**:
- [ ] Update ADR-002-A status to IMPLEMENTED
- [ ] ❌ NO migration guide (pre-1.0 breaking change acceptable)
- [ ] Security audit report updated (VULN-001/002 resolved)
- [ ] API documentation with examples

---

## Test Strategy

### Unit Tests (60-70 tests)
- SecureDataFrame container immutability
- Stack inspection blocks direct construction
- Factory method creation (create_from_datasource)
- Validation logic (compatible vs incompatible)
- Uplifting operations (monotonic increase)
- Trusted mutation methods (with_new_data, with_uplifted_security_level)

### Integration Tests (40-50 tests)
- Datasource → SecureDataFrame → Pipeline flow
- Orchestrator validation enforcement
- Suite runner per-experiment validation
- Error propagation and messages

### Security Tests (15-20 tests)
- Attack scenario: datasource lies about classification → BLOCKED
- Attack scenario: strip attrs["security_level"] → BLOCKED (SecureDataFrame immutable)
- Attack scenario: downgrade without justification → BLOCKED

### Performance Tests (5-10 tests)
- Classification inference overhead (<50ms per DataFrame)
- Validation overhead (<10ms per check)
- Memory overhead of SecureDataFrame wrapper (<1%)

### Backward Compatibility Tests (10-15 tests)
- Old code using `df.attrs["security_level"]` still works
- `.data` property returns plain DataFrame
- Existing tests pass without modification

---

## Risk Assessment

### High Risks

**Risk 1: Breaking Changes**
- **Impact**: Datasource API changes from `pd.DataFrame` → `SecureDataFrame`
- **Mitigation**: Deprecation period, `.data` property for backward compat
- **Rollback**: Feature flag to disable SecureDataFrame validation

**Risk 2: False Positives in Classification Inference**
- **Impact**: UNOFFICIAL data misclassified as SECRET, blocking legitimate workflows
- **Mitigation**: Conservative rules, manual override in config, extensive testing
- **Rollback**: Disable inference, require explicit declaration

**Risk 3: Performance Overhead**
- **Impact**: Classification inference scans DataFrame on load
- **Mitigation**: Cache inference results, skip inference if level declared
- **Rollback**: Disable inference by default

### Medium Risks

**Risk 4: Test Coverage Gaps**
- **Impact**: Edge cases not tested, bugs in production
- **Mitigation**: Mutation testing, characterization tests, security fuzzing

**Risk 5: Breaking Third-Party Datasources**
- **Impact**: Third-party datasources break when returning pd.DataFrame
- **Mitigation**: Pre-1.0 status means API instability expected, document breaking change in CHANGELOG
- **Rollback**: Clean revert (no feature flags)

---

## Acceptance Criteria

### Functional
- [ ] `SecureDataFrame` class implemented with ADR-002-A stack inspection
- [ ] All 8 builtin datasources use `create_from_datasource()` factory
- [ ] Pipeline validates classification at 3 checkpoints
- [ ] Trusted mutation methods (`with_new_data`, `with_uplifted_security_level`) work correctly
- [ ] Direct construction blocked by stack inspection

### Security
- [ ] Attack scenario tests all PASS (classification laundering → blocked by stack inspection)
- [ ] XFAIL tests in `test_adr002_baseplugin_compliance.py` now PASS
- [ ] Security audit sign-off (VULN-001/002 resolved)
- [ ] Stack inspection fail-closed behavior tested

### Quality
- [ ] Test coverage ≥95% for SecureDataFrame module
- [ ] No new failing tests introduced
- [ ] Documentation complete (ADR-002-A updated, API docs)

### Performance
- [ ] Stack inspection overhead <5μs per construction attempt
- [ ] Validation overhead <10ms per checkpoint
- [ ] Memory overhead <1% (SecureDataFrame wrapper)

---

## Rollback Plan (Pre-1.0 Clean Revert)

### If SecureDataFrame Causes Critical Issues

**Option 1: Revert All Phases** (Recommended)
```bash
# Revert Phase 1.4 (Documentation)
git revert HEAD

# Revert Phase 1.3 (XFAIL test conversion)
git revert HEAD~1

# Revert Phase 1.2 (Pipeline validation)
git revert HEAD~2

# Revert Phase 1.1 (Datasource integration)
git revert HEAD~3

# Revert Phase 1.0 (SecureDataFrame core)
git revert HEAD~4

# Verify all tests pass
pytest
```

**Option 2: Revert to Tagged Release**
```bash
# Revert to release before Sprint 1
git reset --hard sprint-0-complete
git push --force
```

**NO Feature Flags**: Pre-1.0 status means clean revert only, no gradual rollback.

### If Implementation Blocked

1. Document blocker (technical or timeline)
2. Tag current state (`sprint-1-incomplete`)
3. Revert all Sprint 1 commits
4. Address blocker, retry Sprint 1

---

## Next Steps After Completion

1. **Sprint 2**: Implement ADR-003 Central Plugin Registry (VULN-003)
2. **Sprint 3**: Implement registry enforcement (VULN-004)
3. **Production Deployment**: Gradual rollout with feature flags
4. **Security Audit**: Final sign-off from compliance team
5. **IRAP Certification**: Clear remaining blockers
