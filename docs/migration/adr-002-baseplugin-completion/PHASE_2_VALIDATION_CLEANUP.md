# Phase 2: Validation Code Cleanup

**Objective**: Remove defensive `hasattr` checks from validation code

**Estimated Effort**: 30 minutes
**Files**: `src/elspeth/core/experiments/suite_runner.py`

---

## Problem

**Current validation code uses defensive programming** (hasattr checks):

```python
# suite_runner.py - _validate_component_clearances method
if hasattr(self.datasource, "validate_can_operate_at_level"):
    try:
        self.datasource.validate_can_operate_at_level(operating_level)
    except Exception as e:
        raise SecurityValidationError(...) from e
```

**Why this was added**: Defensive programming to handle plugins that don't implement BasePlugin

**Why it's now wrong**: With Phase 1 complete, ALL plugins implement BasePlugin. The hasattr check is:
1. **Redundant** - Always returns True now
2. **Misleading** - Suggests validation might skip (it won't)
3. **Performance overhead** - Unnecessary runtime check

---

## Solution

Replace hasattr checks with **direct method calls** + **comprehensive docstring**

---

## Implementation

### File: `src/elspeth/core/experiments/suite_runner.py`

**Locate method**: `_validate_component_clearances` (around line 400-450)

**BEFORE**:
```python
def _validate_component_clearances(self, operating_level: SecurityLevel) -> None:
    """Validate all components can operate at the computed envelope level.

    This performs ADR-002 start-time validation to ensure no component
    is forced to operate below its security requirements.

    Args:
        operating_level: The minimum security level across all components

    Raises:
        SecurityValidationError: If any component cannot operate at the given level
    """
    # Validate datasource
    if hasattr(self.datasource, "validate_can_operate_at_level"):  # ← REMOVE
        try:
            self.datasource.validate_can_operate_at_level(operating_level)
        except Exception as e:
            raise SecurityValidationError(
                f"ADR-002 Start-Time Validation Failed: Datasource "
                f"{type(self.datasource).__name__} cannot operate at "
                f"{operating_level.name} level: {e}"
            ) from e

    # Validate LLM client (if present)
    if self.llm_client and hasattr(self.llm_client, "validate_can_operate_at_level"):  # ← REMOVE
        try:
            self.llm_client.validate_can_operate_at_level(operating_level)
        except Exception as e:
            raise SecurityValidationError(
                f"ADR-002 Start-Time Validation Failed: LLM Client "
                f"{type(self.llm_client).__name__} cannot operate at "
                f"{operating_level.name} level: {e}"
            ) from e

    # Validate sinks
    for sink in self.sinks:
        if hasattr(sink, "validate_can_operate_at_level"):  # ← REMOVE
            try:
                sink.validate_can_operate_at_level(operating_level)
            except Exception as e:
                raise SecurityValidationError(
                    f"ADR-002 Start-Time Validation Failed: Sink "
                    f"{type(sink).__name__} cannot operate at "
                    f"{operating_level.name} level: {e}"
                ) from e
```

**AFTER**:
```python
def _validate_component_clearances(self, operating_level: SecurityLevel) -> None:
    """Validate all components can operate at the computed envelope level.

    This performs ADR-002 start-time validation to ensure no component
    is forced to operate below its security requirements.

    **CRITICAL SECURITY CONTROL (ADR-002 Threat T1, T3)**:
    This validation runs BEFORE data retrieval, implementing fail-fast principle.
    If validation fails, the pipeline aborts and datasource.load() is never called,
    preventing classified data from being exposed to unauthorized sinks.

    **Protocol Requirement - FAIL FAST ON VIOLATIONS**:
    All plugins (datasources, LLM clients, sinks, middleware) MUST implement
    the BasePlugin protocol, which requires:
    - get_security_level() -> SecurityLevel
    - validate_can_operate_at_level(operating_level) -> None (raises on mismatch)

    If a plugin does NOT implement these methods, Python will raise AttributeError
    immediately when this method is called. This is INTENTIONAL - plugins missing
    BasePlugin compliance are configuration bugs that MUST be caught before production.

    **NO FALLBACKS**: There are no hasattr checks, no graceful degradation, no silent
    skips. Missing BasePlugin methods = immediate crash with clear error message.

    This is enforced by:
    - Protocol compliance tests (tests/test_adr002_baseplugin_compliance.py)
    - Type checking (MyPy verifies protocol conformance)
    - Integration tests (tests/test_adr002_suite_integration.py)
    - Runtime (AttributeError if method missing - FAIL FAST!)

    Args:
        operating_level: The minimum security level across all components (envelope)

    Raises:
        SecurityValidationError: If any component cannot operate at the given level
        AttributeError: If plugin missing BasePlugin methods (CONFIGURATION BUG!)

    Example:
        >>> # SECRET datasource + UNOFFICIAL sink
        >>> operating_level = min(datasource.get_security_level(), sink.get_security_level())
        >>> # → operating_level = UNOFFICIAL (minimum)
        >>> datasource.validate_can_operate_at_level(operating_level)
        >>> # → Raises SecurityValidationError: "Datasource requires SECRET, envelope is UNOFFICIAL"
        >>>
        >>> # Plugin missing BasePlugin methods
        >>> broken_plugin.validate_can_operate_at_level(operating_level)
        >>> # → Raises AttributeError: 'BrokenPlugin' has no attribute 'validate_can_operate_at_level'
        >>> # → This is GOOD - configuration bug caught immediately!
    """
    # Validate datasource
    # NO hasattr check - if method missing, AttributeError raised (INTENTIONAL!)
    try:
        self.datasource.validate_can_operate_at_level(operating_level)
    except AttributeError as e:
        # Plugin missing BasePlugin methods - CONFIGURATION BUG!
        raise SecurityValidationError(
            f"CONFIGURATION ERROR: Datasource {type(self.datasource).__name__} "
            f"does not implement BasePlugin protocol (missing validate_can_operate_at_level method). "
            f"All datasources MUST implement BasePlugin. See: "
            f"docs/migration/adr-002-baseplugin-completion/README.md"
        ) from e
    except Exception as e:
        raise SecurityValidationError(
            f"ADR-002 Start-Time Validation Failed: Datasource "
            f"{type(self.datasource).__name__} cannot operate at "
            f"{operating_level.name} level: {e}"
        ) from e

    # Validate LLM client (if present)
    # NO hasattr check - if method missing, AttributeError raised (INTENTIONAL!)
    if self.llm_client:
        try:
            self.llm_client.validate_can_operate_at_level(operating_level)
        except AttributeError as e:
            # Plugin missing BasePlugin methods - CONFIGURATION BUG!
            raise SecurityValidationError(
                f"CONFIGURATION ERROR: LLM Client {type(self.llm_client).__name__} "
                f"does not implement BasePlugin protocol (missing validate_can_operate_at_level method). "
                f"All LLM clients MUST implement BasePlugin. See: "
                f"docs/migration/adr-002-baseplugin-completion/README.md"
            ) from e
        except Exception as e:
            raise SecurityValidationError(
                f"ADR-002 Start-Time Validation Failed: LLM Client "
                f"{type(self.llm_client).__name__} cannot operate at "
                f"{operating_level.name} level: {e}"
            ) from e

    # Validate sinks
    # NO hasattr check - if method missing, AttributeError raised (INTENTIONAL!)
    for sink in self.sinks:
        try:
            sink.validate_can_operate_at_level(operating_level)
        except AttributeError as e:
            # Plugin missing BasePlugin methods - CONFIGURATION BUG!
            raise SecurityValidationError(
                f"CONFIGURATION ERROR: Sink {type(sink).__name__} "
                f"does not implement BasePlugin protocol (missing validate_can_operate_at_level method). "
                f"All sinks MUST implement BasePlugin. See: "
                f"docs/migration/adr-002-baseplugin-completion/README.md"
            ) from e
        except Exception as e:
            raise SecurityValidationError(
                f"ADR-002 Start-Time Validation Failed: Sink "
                f"{type(sink).__name__} cannot operate at "
                f"{operating_level.name} level: {e}"
            ) from e
```

---

## What Changed

**Removed**:
- ❌ `if hasattr(..., "validate_can_operate_at_level"):` checks (3 places)
- ❌ Silent skipping when methods don't exist
- ❌ Any graceful degradation or fallback behavior

**Added**:
- ✅ **Comprehensive docstring** explaining protocol requirement
- ✅ **Security rationale** (ADR-002 Threat T1, T3)
- ✅ **Protocol enforcement documentation** (tests, type checking)
- ✅ **Explicit AttributeError handling** - catches missing methods, raises clear error
- ✅ **Fail-fast philosophy** - missing BasePlugin = immediate configuration error
- ✅ **Example** showing both validation failure and missing method scenarios

**Changed**:
- ✅ Error handling now catches `AttributeError` separately
- ✅ Clear error message if plugin missing BasePlugin methods
- ✅ Error message includes link to migration docs

**Unchanged**:
- ✅ Control flow (validation still happens same way)
- ✅ Security properties (validation still blocks mismatches)

---

## Testing

### Test 1: Integration Tests Still Pass

```bash
# Run ADR-002 integration tests
pytest tests/test_adr002_suite_integration.py -v

# Expected: All tests PASS (validation now guaranteed to run)
```

### Test 2: MyPy Verification

```bash
# Type check suite_runner.py
mypy src/elspeth/core/experiments/suite_runner.py

# Expected: Clean (no protocol violations)
```

### Test 3: Manual Verification

```python
# Create test with SECRET datasource + UNOFFICIAL sink
from elspeth.core.base.types import SecurityLevel
from elspeth.plugins.nodes.sources.csv_local import CSVLocalDataSource
from elspeth.plugins.nodes.sinks.csv_file import CSVFileSink
from elspeth.core.experiments.suite_runner import ExperimentSuiteRunner
from elspeth.core.validation.base import SecurityValidationError

# Create components
secret_ds = CSVLocalDataSource(
    path="data/secret.csv",
    retain_local=False,
    security_level=SecurityLevel.SECRET
)

unofficial_sink = CSVFileSink(
    path="outputs/public.csv",
    security_level=SecurityLevel.UNOFFICIAL
)

# Build experiment config
config = {...}  # Minimal config

# Run - MUST raise SecurityValidationError
try:
    runner = ExperimentSuiteRunner(config)
    runner.run()
    print("❌ FAIL: Validation didn't catch mismatch!")
except SecurityValidationError as e:
    print(f"✅ PASS: Validation caught mismatch: {e}")
```

---

## Verification Checklist

After making changes:

- [ ] Removed all `hasattr(..., "validate_can_operate_at_level")` checks
- [ ] Updated docstring with protocol requirement explanation
- [ ] MyPy clean: `mypy src/elspeth/core/experiments/suite_runner.py`
- [ ] Ruff clean: `ruff check src/elspeth/core/experiments/suite_runner.py`
- [ ] Integration tests pass: `pytest tests/test_adr002_suite_integration.py -v`
- [ ] Full test suite passes: `pytest tests/ -v`
- [ ] Manual verification confirms validation runs

---

## Commit

```bash
git add src/elspeth/core/experiments/suite_runner.py
git commit -m "refactor: Remove hasattr checks from ADR-002 validation (BasePlugin guaranteed)

All plugins now implement BasePlugin protocol (Phase 1 complete).
Validation is guaranteed to run - hasattr defensive checks no longer needed.

Updated docstring to document protocol requirement and security rationale.
"
```

---

## Exit Criteria

- ✅ No more `hasattr` checks in `_validate_component_clearances()`
- ✅ Comprehensive docstring explains protocol requirement
- ✅ All integration tests pass
- ✅ MyPy clean
- ✅ Ruff clean
- ✅ Manual verification confirms validation still works

---

**Next Phase**: [PHASE_3_VERIFICATION.md](./PHASE_3_VERIFICATION.md)
