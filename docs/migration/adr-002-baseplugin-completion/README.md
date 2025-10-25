# ADR-002 BasePlugin Implementation Completion

**Project Type**: Critical Security Implementation Gap
**Status**: Planning Complete - Ready for Execution
**Priority**: P0 - SECURITY BLOCKER
**Branch**: feature/adr-002-security-enforcement (current)
**Estimated Effort**: 6-8 hours (1 day)
**Risk Level**: MEDIUM
**Confidence**: VERY HIGH

---

## Executive Summary

**CRITICAL ISSUE DISCOVERED**: ADR-002 security validation (start-time envelope checks) **never runs in production** because concrete plugin classes don't implement the `BasePlugin` protocol methods that validation code checks for.

**Current State**:
```python
# Validation code in suite_runner.py
if hasattr(datasource, "validate_can_operate_at_level"):  # ← Always FALSE!
    datasource.validate_can_operate_at_level(operating_level)
# → Short-circuits, validation skipped!
```

**Impact**:
- SECRET datasources can flow to UNOFFICIAL sinks unchecked ❌
- ADR-002 threat model (T1, T3) controls are bypassed ❌
- 72 passing tests create false confidence (they don't test real plugins!) ❌

**Solution**: Add `get_security_level()` and `validate_can_operate_at_level()` to all 26 concrete plugin classes using systematic TDD methodology.

---

## Problem Statement

### What Should Happen (ADR-002 Design)

```python
# suite_runner.py - ADR-002 start-time validation
def _validate_component_clearances(operating_level):
    # Datasource validation
    datasource.validate_can_operate_at_level(operating_level)  # Should raise!

    # Sink validation
    for sink in sinks:
        sink.validate_can_operate_at_level(operating_level)  # Should raise!
```

**Expected**: SECRET datasource + UNOFFICIAL sink → `SecurityValidationError` before data retrieval

### What Actually Happens (Current Implementation)

```python
# Actual behavior - defensive programming backfires!
if hasattr(datasource, "validate_can_operate_at_level"):
    datasource.validate_can_operate_at_level(operating_level)
else:
    pass  # ← SILENTLY SKIPS! No validation runs!
```

**Reality**: SECRET datasource + UNOFFICIAL sink → No error, data flows unchecked! 🚨

### Root Cause

**BasePlugin Protocol Exists** (protocols.py:62):
```python
class BasePlugin(Protocol):
    """Security protocol all plugins must implement."""

    def get_security_level(self) -> SecurityLevel:
        raise NotImplementedError

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        raise NotImplementedError
```

**Concrete Plugins DON'T Implement It** (e.g., _csv_base.py:23):
```python
class BaseCSVDataSource(DataSource):  # ← NOT BasePlugin!
    def __init__(self, ..., security_level: SecurityLevel | None = None):
        self.security_level = ensure_security_level(security_level)  # Attribute only!

    # ❌ NO get_security_level() method
    # ❌ NO validate_can_operate_at_level() method
```

**Result**: `hasattr` checks fail → validation code short-circuits → security bypass!

---

## Scope

### Affected Components (26 Plugin Classes)

**Datasources (4 classes)**:
- `src/elspeth/plugins/nodes/sources/_csv_base.py` - BaseCSVDataSource
- `src/elspeth/plugins/nodes/sources/csv_local.py` - CSVLocalDataSource
- `src/elspeth/plugins/nodes/sources/csv_blob.py` - CSVBlobDataSource
- `src/elspeth/plugins/nodes/sources/blob.py` - BlobDataSource

**LLM Clients (6 classes)**:
- `src/elspeth/plugins/nodes/transforms/llm/azure_openai.py` - AzureOpenAIClient
- `src/elspeth/plugins/nodes/transforms/llm/openai_http.py` - OpenAIHTTPClient
- `src/elspeth/plugins/nodes/transforms/llm/mock_llm.py` - MockLLMClient
- `src/elspeth/plugins/nodes/transforms/llm/static_llm.py` - StaticLLMClient
- (Plus middleware wrappers as needed)

**Sinks (16 classes)**:
- All implementations in `src/elspeth/plugins/nodes/sinks/`
  - CSV, Excel, JSON, Markdown, visual analytics, signed bundles, repositories, etc.

### Files Requiring Changes

**Implementation** (26 plugin files):
- Add 2 methods to each plugin class (~5 minutes per class = 130 minutes = 2.2 hours)

**Tests** (NEW file):
- `tests/test_adr002_baseplugin_compliance.py` - Comprehensive validation tests

**Validation Code** (1 file):
- `src/elspeth/core/experiments/suite_runner.py` - Remove hasattr defensive checks (now guaranteed safe)

---

## Design Principle: Fail Fast and Loud

**CRITICAL**: This is a security-critical system. Plugins that don't implement BasePlugin protocol are **configuration bugs** that MUST be caught immediately.

**NO FALLBACKS**:
- ❌ No hasattr checks that silently skip validation
- ❌ No graceful degradation when methods missing
- ❌ No "optional" BasePlugin compliance

**FAIL FAST**:
- ✅ Missing BasePlugin methods → AttributeError at validation time
- ✅ Clear error message pointing to migration docs
- ✅ Future enhancement: Fail at registration time (Phase 1.5 - optional)

**Rationale**: Classified data systems cannot tolerate silent failures. If a plugin doesn't implement BasePlugin, the system MUST crash immediately with a clear error message, not silently skip validation.

---

## Methodology: Test-First Implementation

Following the refactoring methodology from `docs/refactoring/METHODOLOGY.md`, adapted for implementation completion:

### Phase 0: Safety Net Construction (2-3 hours) 🔴 RED

**Objective**: Build tests that PROVE validation currently short-circuits

**Deliverables**:
1. **Characterization Tests** - Document current broken behavior
2. **Security Property Tests** - Define what MUST work after fix
3. **Integration Tests** - End-to-end validation with real plugins

**Test File**: `tests/test_adr002_baseplugin_compliance.py`

**Critical Tests**:

```python
def test_baseplugin_protocol_conformance():
    """CHARACTERIZATION: Prove concrete plugins DON'T implement BasePlugin."""
    from elspeth.core.base.protocols import BasePlugin

    # Datasources
    ds = BaseCSVDataSource(path="test.csv", retain_local=False, security_level=SecurityLevel.SECRET)
    assert not hasattr(ds, "get_security_level")  # ← Currently TRUE (missing!)
    assert not hasattr(ds, "validate_can_operate_at_level")  # ← Currently TRUE (missing!)

    # Sinks
    sink = CSVFileSink(path="out.csv", security_level=SecurityLevel.UNOFFICIAL)
    assert not hasattr(sink, "get_security_level")  # ← Currently TRUE (missing!)
    assert not hasattr(sink, "validate_can_operate_at_level")  # ← Currently TRUE (missing!)


def test_validation_currently_short_circuits():
    """SECURITY BUG: Prove validation doesn't run (allows SECRET→UNOFFICIAL)."""
    secret_ds = create_datasource(security_level=SecurityLevel.SECRET)
    unofficial_sink = create_sink(security_level=SecurityLevel.UNOFFICIAL)

    # Currently PASSES (should FAIL!) because validation skips
    result = run_experiment(datasource=secret_ds, sinks=[unofficial_sink])

    # ❌ WRONG: Data flowed without validation!
    assert result.success  # This MUST fail after fix!


@pytest.mark.xfail(reason="ADR-002 validation not yet implemented", strict=True)
def test_secret_datasource_unofficial_sink_blocked():
    """SECURITY PROPERTY: SECRET data MUST NOT flow to UNOFFICIAL sink."""
    secret_ds = BaseCSVDataSource(
        path="data/secret.csv",
        retain_local=False,
        security_level=SecurityLevel.SECRET
    )
    unofficial_sink = CSVFileSink(
        path="outputs/public.csv",
        security_level=SecurityLevel.UNOFFICIAL
    )

    # MUST raise SecurityValidationError during _validate_component_clearances
    with pytest.raises(SecurityValidationError, match="requires SECRET.*UNOFFICIAL"):
        run_experiment(datasource=secret_ds, sinks=[unofficial_sink])


@pytest.mark.xfail(reason="ADR-002 validation not yet implemented", strict=True)
def test_all_datasources_have_baseplugin_methods():
    """PROTOCOL COMPLIANCE: All datasources MUST implement BasePlugin."""
    from elspeth.core.base.protocols import BasePlugin

    datasource_classes = [
        BaseCSVDataSource,
        CSVLocalDataSource,
        CSVBlobDataSource,
        BlobDataSource,
    ]

    for cls in datasource_classes:
        # Create instance
        ds = cls(path="test.csv", retain_local=False, security_level=SecurityLevel.OFFICIAL)

        # MUST have BasePlugin methods
        assert hasattr(ds, "get_security_level"), f"{cls.__name__} missing get_security_level()"
        assert hasattr(ds, "validate_can_operate_at_level"), f"{cls.__name__} missing validate_can_operate_at_level()"

        # Methods MUST be callable
        assert callable(getattr(ds, "get_security_level"))
        assert callable(getattr(ds, "validate_can_operate_at_level"))

        # get_security_level() MUST return SecurityLevel
        level = ds.get_security_level()
        assert isinstance(level, SecurityLevel)
        assert level == SecurityLevel.OFFICIAL


@pytest.mark.xfail(reason="ADR-002 validation not yet implemented", strict=True)
def test_all_sinks_have_baseplugin_methods():
    """PROTOCOL COMPLIANCE: All sinks MUST implement BasePlugin."""
    # Similar to datasource test, but for all 16 sink classes
    pass


@pytest.mark.xfail(reason="ADR-002 validation not yet implemented", strict=True)
def test_validation_no_longer_short_circuits():
    """INTEGRATION: Prove validation ACTUALLY RUNS after fix."""
    secret_ds = create_datasource(security_level=SecurityLevel.SECRET)
    unofficial_sink = create_sink(security_level=SecurityLevel.UNOFFICIAL)

    # After fix: MUST raise during validation (not short-circuit)
    with pytest.raises(SecurityValidationError):
        run_experiment(datasource=secret_ds, sinks=[unofficial_sink])
```

**Exit Criteria**:
- ✅ Characterization tests document current broken state (PASS with current code)
- ✅ Security property tests defined with @pytest.mark.xfail (FAIL with current code)
- ✅ Test coverage ≥ 95% on validation code paths
- ✅ All stakeholders understand the security gap

---

### Phase 1: Implementation (2-3 hours) 🟢 GREEN

**Objective**: Add BasePlugin methods to all 26 plugin classes

**Strategy**: Update ONE plugin class at a time, run tests after each

**Template** (applies to all plugins):

```python
# Example: src/elspeth/plugins/nodes/sources/_csv_base.py

class BaseCSVDataSource(DataSource):
    """Base class for CSV datasources with common functionality."""

    def __init__(self, ..., security_level: SecurityLevel | None = None):
        # Existing code unchanged
        self.security_level = ensure_security_level(security_level)

    # ========== NEW: BasePlugin Protocol Implementation ==========

    def get_security_level(self) -> SecurityLevel:
        """Return the minimum security level this datasource requires.

        Implements BasePlugin protocol for ADR-002 start-time validation.

        Returns:
            SecurityLevel: Minimum clearance required for this datasource

        Example:
            >>> ds = BaseCSVDataSource(path="secret.csv", security_level=SecurityLevel.SECRET)
            >>> ds.get_security_level()
            SecurityLevel.SECRET
        """
        return self.security_level

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        """Validate this datasource can operate at the given security level.

        Implements BasePlugin protocol for ADR-002 start-time validation.
        This is the PRIMARY security control preventing SECRET→UNOFFICIAL data flow.

        Args:
            operating_level: Security level of the operating envelope (minimum across all components)

        Raises:
            SecurityValidationError: If operating_level < this datasource's required level

        Example:
            >>> ds = BaseCSVDataSource(path="secret.csv", security_level=SecurityLevel.SECRET)
            >>> ds.validate_can_operate_at_level(SecurityLevel.OFFICIAL)
            SecurityValidationError: BaseCSVDataSource requires SECRET clearance, but operating envelope is OFFICIAL
        """
        if operating_level < self.security_level:
            from elspeth.core.validation.base import SecurityValidationError
            raise SecurityValidationError(
                f"{self.__class__.__name__} requires {self.security_level.name} "
                f"clearance, but operating envelope is {operating_level.name}"
            )

    # ========== END BasePlugin Implementation ==========

    # Existing methods unchanged...
```

**Execution Protocol** (per plugin class):

1. **Add methods** to one plugin class
2. **Run tests**: `pytest tests/test_adr002_baseplugin_compliance.py -v -k <ClassName>`
3. **Verify**: xfail tests now pass for this plugin
4. **Commit**: `git add <file> && git commit -m "feat: Add BasePlugin protocol to <ClassName>"`
5. **Repeat** for next plugin class

**Exit Criteria**:
- ✅ All 26 plugin classes have `get_security_level()` method
- ✅ All 26 plugin classes have `validate_can_operate_at_level()` method
- ✅ All protocol compliance tests pass (no more xfails)
- ✅ MyPy clean (protocol conformance verified)

---

### Phase 2: Validation Code Cleanup (30 minutes) 🔵 REFACTOR

**Objective**: Remove defensive hasattr checks (no longer needed)

**File**: `src/elspeth/core/experiments/suite_runner.py`

**Changes**:

```python
# BEFORE (defensive, allows short-circuit):
def _validate_component_clearances(self, operating_level: SecurityLevel) -> None:
    """Validate all components can operate at the computed envelope level."""

    # Validate datasource
    if hasattr(self.datasource, "validate_can_operate_at_level"):  # ← REMOVE THIS!
        try:
            self.datasource.validate_can_operate_at_level(operating_level)
        except Exception as e:
            raise SecurityValidationError(...) from e

    # Validate sinks
    for sink in self.sinks:
        if hasattr(sink, "validate_can_operate_at_level"):  # ← REMOVE THIS!
            try:
                sink.validate_can_operate_at_level(operating_level)
            except Exception as e:
                raise SecurityValidationError(...) from e


# AFTER (guaranteed safe, no short-circuit possible):
def _validate_component_clearances(self, operating_level: SecurityLevel) -> None:
    """Validate all components can operate at the computed envelope level.

    All plugins MUST implement BasePlugin protocol (get_security_level, validate_can_operate_at_level).
    This is enforced by protocol compliance tests and type checking.
    """

    # Validate datasource - GUARANTEED to have method (BasePlugin protocol)
    try:
        self.datasource.validate_can_operate_at_level(operating_level)
    except Exception as e:
        raise SecurityValidationError(
            f"ADR-002 Start-Time Validation Failed: Datasource "
            f"{type(self.datasource).__name__} cannot operate at "
            f"{operating_level.name} level: {e}"
        ) from e

    # Validate sinks - GUARANTEED to have method (BasePlugin protocol)
    for sink in self.sinks:
        try:
            sink.validate_can_operate_at_level(operating_level)
        except Exception as e:
            raise SecurityValidationError(
                f"ADR-002 Start-Time Validation Failed: Sink "
                f"{type(sink).__name__} cannot operate at "
                f"{operating_level.name} level: {e}"
            ) from e
```

**Exit Criteria**:
- ✅ No more hasattr checks in validation code
- ✅ All integration tests pass
- ✅ MyPy clean (no protocol violations)

---

### Phase 3: End-to-End Verification (1-2 hours) ✅ VERIFY

**Objective**: Prove ADR-002 validation now works end-to-end

**Verification Tests**:

1. **Full test suite**: `pytest tests/ -v` (all 800+ tests must pass)
2. **Security-specific**: `pytest tests/test_adr002*.py -v` (all ADR-002 tests pass)
3. **Type checking**: `mypy src/elspeth --strict` (no protocol violations)
4. **Linting**: `ruff check src tests` (clean)

**Manual Verification**:

```bash
# Create test config with SECRET→UNOFFICIAL mismatch
cat > /tmp/test_validation.yaml <<EOF
datasources:
  secret_data:
    type: csv_local
    path: data/secret.csv
    security_level: SECRET

sinks:
  public_output:
    type: csv_file
    path: outputs/public.csv
    security_level: UNOFFICIAL
EOF

# Run experiment - MUST fail with SecurityValidationError
python -m elspeth.cli \
  --settings /tmp/test_validation.yaml \
  --suite-root config/sample_suite \
  --reports-dir /tmp/outputs

# Expected output:
# ❌ SecurityValidationError: CSVFileSink requires UNOFFICIAL clearance,
#    but operating envelope is SECRET
# (Or similar - datasource/sink mismatch caught!)
```

**Exit Criteria**:
- ✅ All 800+ tests pass (zero regressions)
- ✅ SECRET→UNOFFICIAL configurations correctly blocked
- ✅ UNOFFICIAL→SECRET configurations correctly allowed (uplifting works)
- ✅ MyPy, Ruff clean
- ✅ Manual verification confirms validation runs

---

## Risk Assessment

### Risk 1: Breaking Existing Configurations (MEDIUM)

**Impact**: Configurations that previously "worked" (due to validation skipping) now fail

**Probability**: LOW (most configs are correct; validation was designed correctly)

**Mitigation**:
- Comprehensive test suite validates existing configs still work
- If legitimate configs break, it reveals actual security misconfigurations

**Fallback**: Can add temporary feature flag to enable/disable validation

---

### Risk 2: Performance Impact (LOW)

**Impact**: Adding method calls to hot path

**Probability**: VERY LOW (validation runs once at start-time, not per-row)

**Mitigation**:
- Start-time validation is by design (ADR-002)
- Negligible performance impact (<1ms total per suite)

**Fallback**: None needed

---

### Risk 3: Type System Complexity (LOW)

**Impact**: MyPy errors with protocol conformance

**Probability**: LOW (BasePlugin is well-designed protocol)

**Mitigation**:
- Incremental implementation (one plugin at a time)
- MyPy verification after each plugin
- Clear error messages guide fixes

**Fallback**: Can use `typing.cast` as temporary workaround

---

## Timeline

**Total Effort**: 6-8 hours (1 day)

| Phase | Activity | Hours | Risk | Exit Criteria |
|-------|----------|-------|------|---------------|
| **Phase 0** | **Safety Net** | **2-3** | **LOW** | Characterization + security tests written |
| 0.1 | Write characterization tests | 1 | LOW | Current broken behavior documented |
| 0.2 | Write security property tests | 1-2 | LOW | xfail tests define success criteria |
| **Phase 1** | **Implementation** | **2-3** | **MEDIUM** | All plugins have BasePlugin methods |
| 1.1 | Add methods to datasources (4 classes) | 0.5 | LOW | Datasource tests pass |
| 1.2 | Add methods to LLM clients (6 classes) | 0.75 | LOW | LLM tests pass |
| 1.3 | Add methods to sinks (16 classes) | 1.5 | MEDIUM | Sink tests pass |
| **Phase 2** | **Refactor Validation** | **0.5** | **LOW** | hasattr checks removed |
| **Phase 3** | **Verification** | **1-2** | **LOW** | All tests pass, manual verification done |
| **Total** | | **6-8** | **MEDIUM** | ADR-002 validation proven to work |

---

## Success Criteria

### Must-Have (Blocking Merge)

- ✅ All 26 plugin classes implement `get_security_level()`
- ✅ All 26 plugin classes implement `validate_can_operate_at_level()`
- ✅ All security property tests pass (no xfails)
- ✅ SECRET→UNOFFICIAL configurations correctly blocked
- ✅ All 800+ existing tests pass (zero regressions)
- ✅ MyPy clean, Ruff clean

### Should-Have (Quality)

- ✅ hasattr defensive checks removed from validation code
- ✅ Manual verification with real configs confirms validation runs
- ✅ Documentation updated (ADR-002 implementation status)

### Nice-to-Have (Future)

- ⭕ Add runtime warning if plugin doesn't implement BasePlugin
- ⭕ Add Ruff rule to enforce BasePlugin conformance
- ⭕ Performance benchmarks (validation overhead measurement)

---

## Next Steps

### Immediate (Before Starting)

1. ✅ Review this plan with team
2. ⭕ Approve 6-8 hour effort estimate
3. ⭕ Confirm this blocks merge of ADR-002 branch

### Execute (Test-First)

1. ⭕ Phase 0: Write characterization + security tests (2-3 hours)
2. ⭕ Phase 1: Implement BasePlugin methods (2-3 hours)
3. ⭕ Phase 2: Remove hasattr checks (30 minutes)
4. ⭕ Phase 3: Full verification (1-2 hours)

### Post-Completion

1. ⭕ Update ADR-002 documentation (mark as "COMPLETE - validation proven")
2. ⭕ Merge ADR-002 branch
3. ⭕ Proceed with ADR-003/004 migration (now on solid foundation)

---

## Related Documents

- **ADR-002**: Multi-Level Security Enforcement (`docs/architecture/decisions/002-security-architecture.md`)
- **ADR-002-A**: Trusted Container Model (`docs/architecture/decisions/002-a-trusted-container-model.md`)
- **Threat Model**: ADR-002 security controls (`docs/security/adr-002-threat-model.md`)
- **Refactoring Methodology**: `docs/refactoring/METHODOLOGY.md` (methodology adapted from here)
- **BasePlugin Protocol**: `src/elspeth/core/base/protocols.py` (lines 62-100)

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

**Project Created**: 2025-10-25
**Author**: Security Team + Platform Team
**Priority**: P0 - BLOCKS ADR-002 MERGE
