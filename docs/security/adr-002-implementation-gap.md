# ADR-002 Suite-Level Security Enforcement - Implementation Gap Analysis

**Document Status**: Implementation Specification
**Created**: 2025-10-25
**Related ADR**: [ADR-002 Multi-Level Security Enforcement](../architecture/decisions/002-security-architecture.md)
**Related PR**: #11 (suite_runner.py refactoring)

---

## Executive Summary

ADR-002 (accepted 2025-10-23) mandates two-layer security enforcement:
1. ✅ **Plugin-level enforcement** - Child plugins cannot downgrade parent security levels (IMPLEMENTED)
2. ❌ **Suite-level enforcement** - Suite runner computes pipeline minimum security level and fails fast before data retrieval (NOT IMPLEMENTED)

This document specifies the **missing suite-level enforcement** that must be implemented to achieve full ADR-002 compliance.

---

## ADR-002 Requirements

### Requirement 1: Pipeline-Wide Security Computation

**From ADR-002 lines 52-60:**

```python
# Example: UNOFFICIAL datasource in SECRET pipeline (insufficient clearance)
datasource.security_level = SecurityLevel.OFFICIAL  # Only cleared for OFFICIAL
llm_transform.security_level = SecurityLevel.SECRET
sink_prod.security_level = SecurityLevel.SECRET

# Compute pipeline minimum
pipeline_level = min(SecurityLevel.OFFICIAL, SecurityLevel.SECRET, SecurityLevel.SECRET)
# => SecurityLevel.OFFICIAL

# Each component validates: Can I operate at this level?
# Datasource: OFFICIAL clearance, asked to operate at OFFICIAL → ✅ OK
# LLM: SECRET clearance, asked to operate at OFFICIAL → ✅ OK (can downgrade)
# Sink: SECRET clearance, asked to operate at OFFICIAL → ✅ OK (can downgrade)

# Now suppose pipeline requires SECRET (misconfigured - datasource has insufficient clearance):
pipeline_level_secret = SecurityLevel.SECRET

# Datasource refuses to operate ABOVE its clearance (Bell-LaPadula "no read up")
if pipeline_level_secret > datasource.security_level:
    raise SecurityError(
        "Cannot operate OFFICIAL datasource in SECRET pipeline - insufficient clearance"
    )
```

**Key requirement**: Fail-fast BEFORE data retrieval.

### Requirement 2: Suite Runner Responsibilities

**From ADR-002 lines 99-100:**

> "Suite runner changes – Prior to instantiation, the suite runner computes the minimum level and enforces it via the plugin registry/context"

**From ADR-002 line 106:**

> "Testing requirements – Security level enforcement must be validated in integration tests with misconfigured pipeline scenarios"

---

## Current Implementation Status

### ✅ What Exists Today

#### 1. Plugin-Level Security Enforcement
**File**: `tests/test_security_level_enforcement.py` (9 tests, 356 lines)

**Coverage**:
- Child plugins cannot downgrade parent `security_level` ✅
- Security inheritance through plugin chains ✅
- Security level conflicts detected in definition + options ✅
- Upgrades allowed (more restrictive is safe) ✅

**Example Test**:
```python
def test_child_plugin_cannot_downgrade_parent_security_official_to_public():
    """SECURITY REGRESSION TEST: Child cannot downgrade OFFICIAL to PUBLIC."""
    # Parent has OFFICIAL classification
    parent_context = PluginContext(
        plugin_name="parent",
        plugin_kind="test",
        security_level="official",
        determinism_level="none",
    )

    # Child attempts downgrade to PUBLIC - rejected
    definition = {
        "name": "test",
        "security_level": "public",  # ❌ Attempting downgrade
        "determinism_level": "none",
    }

    with pytest.raises(ConfigurationError,
                       match="security_level 'UNOFFICIAL' cannot downgrade parent level 'OFFICIAL'"):
        create_plugin_with_inheritance(registry, definition,
                                       plugin_kind="test_plugin",
                                       parent_context=parent_context)
```

#### 2. Security Level Resolution in Suite Runner
**File**: `src/elspeth/core/experiments/suite_runner.py`

**Lines 229-231**: Experiment-level security resolution
```python
security_level = resolve_security_level(
    config.security_level,
    pack.get("security_level") if pack else None,
    defaults.get("security_level"),
)
```

**Lines 370-372**: Sink security validation (requires declaration)
```python
security_level = entry.get("security_level", raw_options.get("security_level"))
if security_level is None:
    raise ConfigurationError(f"sink '{plugin}' requires a security_level")
```

#### 3. Component-Level Security Validation
**File**: `tests/test_config_validation.py`

**Tests exist for**:
- Missing datasource security_level (line 44)
- Missing LLM security_level (line 61)
- Missing sink security_level (line 78)

---

## ❌ What's Missing: Suite-Level Fail-Fast Enforcement

### Gap 1: No Pipeline-Wide Security Computation

**Required behavior**: Before instantiating any components, compute:
```python
pipeline_min_level = min(
    datasource.security_level,
    *[transform.security_level for transform in transforms],
    *[sink.security_level for sink in sinks],
    *[middleware.security_level for middleware in middlewares]
)
```

**Current behavior**: Each component validates independently, but no global minimum is computed.

**Impact**: A SECRET datasource + UNOFFICIAL sink will **start execution** and **retrieve data** before the sink write fails. ADR-002 requires aborting BEFORE data retrieval.

### Gap 2: No Orchestrator Operating Level Validation

**Required behavior** (from ADR-002 + Cryptographic Plugin Model):

The orchestrator asks all cryptographically signed plugins for their security levels, computes the MINIMUM, and operates at that level. High-security components then refuse to participate if the orchestrator's operating level is below their requirement.

```python
# 1. Collect security levels from ALL plugins (signed, trusted declarations)
plugin_levels = {
    'datasource': SecurityLevel.SECRET,
    'llm': SecurityLevel.SECRET,
    'sink1': SecurityLevel.SECRET,
    'sink2': SecurityLevel.UNOFFICIAL,  # One low-security component
}

# 2. Orchestrator operates at MINIMUM (like a clearance envelope)
orchestrator_operating_level = min(plugin_levels.values())  # => UNOFFICIAL

# 3. Validate ALL components can operate at orchestrator's level
for component_name, required_level in plugin_levels.items():
    if required_level > orchestrator_operating_level:
        raise SecurityError(
            f"Component '{component_name}' requires {required_level} "
            f"but orchestrator operating at {orchestrator_operating_level}. "
            f"Job cannot start - remove low-security component or create separate pipeline."
        )

# 4. Set orchestrator operating level in execution context (for runtime validation)
self.operating_level = orchestrator_operating_level
```

**Defense in depth**: Each plugin ALSO validates at runtime:
```python
class SecretDataSource:
    security_level = SecurityLevel.SECRET  # Clearance: up to SECRET

    def get_data(self, orchestrator_context):
        # Runtime validation (even if start-time check somehow bypassed)
        # Bell-LaPadula "no read up": Reject if asked to operate ABOVE clearance
        if orchestrator_context.operating_level > self.security_level:
            raise SecurityError(
                f"Datasource cleared for {self.security_level}, "
                f"but orchestrator requires {orchestrator_context.operating_level}. "
                f"Insufficient clearance - refusing to operate."
            )
        # If operating_level <= clearance, we can operate (possibly filtering data)
        return self._retrieve_filtered_data(orchestrator_context.operating_level)
```

**Current behavior**: No orchestrator operating level concept exists. No start-time validation. No runtime validation.

**Impact**: A pipeline with SECRET datasource + UNOFFICIAL sink will start execution and retrieve sensitive data before failing at sink write time. ADR-002 requires failing BEFORE data retrieval.

### Gap 3: No Integration Tests for Misconfigured Pipelines

**Required tests** (from ADR-002 line 106):
- Suite with SECRET datasource + UNOFFICIAL sink (should fail before data retrieval)
- Suite with matching security levels (should succeed)
- Suite with security upgrade in pipeline (should succeed)

**Current tests**: None matching this pattern.

---

## Implementation Roadmap

### Phase 1: Add Security Computation to Suite Runner (HIGH PRIORITY)

**Location**: `src/elspeth/core/experiments/suite_runner.py::run()` method

**Implementation point**: Lines 281-310 (after experiment loop setup, before first experiment executes)

**Suggested approach**:

```python
def run(
    self,
    data: pd.DataFrame,
    defaults: dict[str, Any],
    sink_factory: Callable[[ExperimentConfig], list[ResultSink]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Execute all experiments in the suite.

    Security Note: This method enforces ADR-002 suite-level security by:
    1. Collecting security levels from all cryptographically signed plugins
    2. Computing orchestrator operating level (minimum across all components)
    3. Validating ALL components can operate at that level BEFORE data retrieval
    4. Setting operating level in execution context for runtime validation
    """
    # ... existing validation ...

    # NEW: ADR-002 orchestrator operating level enforcement
    plugin_security_levels = self._collect_plugin_security_levels(
        suite=self.suite,
        defaults=defaults,
        sink_factory=sink_factory,
    )

    # Orchestrator operates at minimum security level (clearance envelope model)
    orchestrator_operating_level = self._compute_orchestrator_operating_level(
        plugin_security_levels
    )

    # Validate ALL components can operate at orchestrator's level (fail-fast)
    self._validate_components_at_operating_level(
        plugin_security_levels,
        orchestrator_operating_level
    )

    # Set operating level in execution context for runtime validation
    self.operating_level = orchestrator_operating_level

    # ... existing execution logic ...
```

### Phase 2: Implement Helper Methods

#### Method 1: `_compute_pipeline_security_level()`

**Purpose**: Compute minimum security level across all pipeline components.

**Signature**:
```python
def _compute_pipeline_security_level(
    self,
    suite: ExperimentSuite,
    defaults: dict[str, Any],
    sink_factory: Callable[[ExperimentConfig], list[ResultSink]] | None,
) -> str:
    """Compute minimum security level across entire pipeline.

    ADR-002 Requirement: Suite runner computes minimum level across:
    - Datasource (suite-level or defaults)
    - LLM client (suite-level)
    - All experiment sinks (resolved via 5-level priority)
    - All middlewares

    Args:
        suite: The experiment suite configuration
        defaults: Default configuration dictionary
        sink_factory: Optional sink factory for dynamic sink creation

    Returns:
        Minimum security level string (e.g., "UNOFFICIAL", "OFFICIAL", "SECRET")

    Raises:
        ConfigurationError: If any component lacks security_level declaration
    """
    from elspeth.core.security import SecurityLevel, compare_security_levels

    levels: list[str] = []

    # 1. Datasource security level
    datasource_level = suite.datasource_config.get("security_level") if suite.datasource_config else None
    if not datasource_level:
        datasource_level = defaults.get("datasource", {}).get("security_level")
    if not datasource_level:
        raise ConfigurationError("Datasource must declare security_level for ADR-002 compliance")
    levels.append(datasource_level)

    # 2. LLM client security level
    llm_level = getattr(self.llm_client, "security_level", None)
    if not llm_level:
        raise ConfigurationError("LLM client must declare security_level for ADR-002 compliance")
    levels.append(llm_level)

    # 3. Experiment sink security levels (via 5-level resolution)
    for experiment in suite.experiments:
        if not experiment.enabled:
            continue

        # Resolve sinks using existing 5-level priority logic
        resolved_sinks = self._resolve_experiment_sinks(
            experiment, defaults, sink_factory
        )

        for sink in resolved_sinks:
            sink_level = getattr(sink, "security_level", None)
            if not sink_level:
                raise ConfigurationError(
                    f"Sink for experiment '{experiment.name}' must declare security_level"
                )
            levels.append(sink_level)

    # 4. Middleware security levels
    for middleware in self.middlewares:
        mw_level = getattr(middleware, "security_level", None)
        if mw_level:  # Middlewares are optional components
            levels.append(mw_level)

    # Compute minimum across all declared levels
    canonical_levels = [SecurityLevel.from_string(level) for level in levels]
    min_level = min(canonical_levels)

    return min_level.value
```

#### Method 2: `_validate_datasource_security()`

**Purpose**: Validate datasource can operate at pipeline minimum security level.

**Signature**:
```python
def _validate_datasource_security(self, pipeline_min_level: str) -> None:
    """Validate datasource can operate at pipeline minimum security level.

    ADR-002 Requirement: Datasources refuse to operate ABOVE their clearance.
    This prevents insufficient-clearance datasources from participating in
    higher-classification pipelines (Bell-LaPadula "no read up" rule).

    Note: Datasources with HIGHER clearance CAN operate at LOWER pipeline levels
    (trusted to filter data appropriately, validated through certification).

    Args:
        pipeline_min_level: Minimum security level across pipeline components

    Raises:
        SecurityError: If pipeline_min_level > datasource security_level
    """
    from elspeth.core.security import SecurityLevel

    # Get datasource security level
    datasource_config = self.suite.datasource_config or {}
    datasource_level_str = datasource_config.get("security_level")

    if not datasource_level_str:
        # Already validated in _compute_pipeline_security_level
        return

    datasource_level = SecurityLevel.from_string(datasource_level_str)
    pipeline_level = SecurityLevel.from_string(pipeline_min_level)

    # Fail fast if pipeline requires higher clearance than datasource has
    if pipeline_level > datasource_level:
        raise SecurityError(
            f"Cannot operate {datasource_level.value} datasource in {pipeline_level.value} pipeline. "
            f"ADR-002 fail-fast enforcement: Datasource has insufficient clearance. "
            f"Minimum pipeline security level is {pipeline_level.value}, but datasource requires {datasource_level.value}."
        )
```

### Phase 3: Add Integration Tests

**File**: Create `tests/test_suite_runner_adr002_security.py`

**Required test cases**:

```python
"""ADR-002 Suite-Level Security Enforcement Tests.

These tests validate the fail-fast security enforcement required by ADR-002.
The suite runner must compute the minimum security level across all pipeline
components and abort execution BEFORE data retrieval if misconfigured.

CRITICAL: These tests validate certification-blocking security requirements.
"""

import pandas as pd
import pytest

from elspeth.core.experiments.config import ExperimentConfig, ExperimentSuite
from elspeth.core.experiments.suite_runner import ExperimentSuiteRunner
from elspeth.core.validation import SecurityError
from tests.conftest import SimpleLLM


def test_adr002_fail_fast_secret_datasource_unofficial_sink():
    """ADR-002: SECRET datasource with UNOFFICIAL sink fails BEFORE data retrieval.

    ╔═══════════════════════════════════════════════════════════════════════════╗
    ║ CERTIFICATION IMPACT: CRITICAL                                            ║
    ║                                                                           ║
    ║ This test validates ADR-002's fail-fast security enforcement. Failure    ║
    ║ indicates the system may RETRIEVE CLASSIFIED DATA before detecting the   ║
    ║ misconfiguration, violating fail-fast principle.                         ║
    ║                                                                           ║
    ║ Regulatory Impact:                                                        ║
    ║ • Classified data could be retrieved before security check               ║
    ║ • Violates fail-fast principle (data in memory before abort)            ║
    ║ • Could result in data spillage to low-security sinks                   ║
    ║                                                                           ║
    ║ This is NOT a config issue - this is ADR-002 security enforcement.       ║
    ║ If this test fails, DO NOT proceed to certification without fixing.     ║
    ╚═══════════════════════════════════════════════════════════════════════════╝
    """
    suite = ExperimentSuite(
        root=Path("/tmp"),
        baseline=None,
        datasource_config={
            "plugin": "csv",
            "security_level": "secret",  # HIGH security
            "determinism_level": "guaranteed",
            "path": "/tmp/test.csv",
        },
        experiments=[
            ExperimentConfig(
                name="exp1",
                temperature=0.7,
                max_tokens=100,
                sink_defs=[
                    {
                        "plugin": "csv_file",
                        "security_level": "public",  # LOW security - MISCONFIGURED
                        "determinism_level": "guaranteed",
                        "options": {"path": "/tmp/output.csv"},
                    }
                ],
            )
        ],
    )

    runner = ExperimentSuiteRunner(
        suite=suite,
        llm_client=SimpleLLM(security_level="secret"),
        sinks=[],
    )

    defaults = {
        "prompt_system": "Test",
        "prompt_template": "{{ text }}",
        "security_level": "secret",
    }

    # Must fail BEFORE data retrieval
    with pytest.raises(SecurityError, match="Cannot operate SECRET datasource in UNOFFICIAL pipeline"):
        runner.run(pd.DataFrame([{"text": "test"}]), defaults)


def test_adr002_pass_matching_security_levels():
    """ADR-002: Suite with matching security levels executes successfully."""
    suite = ExperimentSuite(
        root=Path("/tmp"),
        baseline=None,
        datasource_config={
            "plugin": "csv",
            "security_level": "official",
            "determinism_level": "guaranteed",
            "path": "/tmp/test.csv",
        },
        experiments=[
            ExperimentConfig(
                name="exp1",
                temperature=0.7,
                max_tokens=100,
                sink_defs=[
                    {
                        "plugin": "collecting",
                        "security_level": "official",  # MATCHING security
                        "determinism_level": "guaranteed",
                    }
                ],
            )
        ],
    )

    runner = ExperimentSuiteRunner(
        suite=suite,
        llm_client=SimpleLLM(security_level="official"),
        sinks=[],
    )

    defaults = {
        "prompt_system": "Test",
        "prompt_template": "{{ text }}",
        "security_level": "official",
    }

    # Should succeed - all components at OFFICIAL level
    results = runner.run(pd.DataFrame([{"text": "test"}]), defaults)
    assert "exp1" in results


def test_adr002_pass_security_upgrade_in_pipeline():
    """ADR-002: Pipeline with security UPGRADE (more restrictive) is allowed."""
    suite = ExperimentSuite(
        root=Path("/tmp"),
        baseline=None,
        datasource_config={
            "plugin": "csv",
            "security_level": "official",  # OFFICIAL datasource
            "determinism_level": "guaranteed",
            "path": "/tmp/test.csv",
        },
        experiments=[
            ExperimentConfig(
                name="exp1",
                temperature=0.7,
                max_tokens=100,
                sink_defs=[
                    {
                        "plugin": "collecting",
                        "security_level": "secret",  # UPGRADED to SECRET (safe)
                        "determinism_level": "guaranteed",
                    }
                ],
            )
        ],
    )

    runner = ExperimentSuiteRunner(
        suite=suite,
        llm_client=SimpleLLM(security_level="secret"),
        sinks=[],
    )

    defaults = {
        "prompt_system": "Test",
        "prompt_template": "{{ text }}",
        "security_level": "secret",
    }

    # Should succeed - pipeline minimum is OFFICIAL, datasource is OFFICIAL
    results = runner.run(pd.DataFrame([{"text": "test"}]), defaults)
    assert "exp1" in results


def test_adr002_fail_fast_protected_datasource_official_sink():
    """ADR-002: PROTECTED datasource with OFFICIAL sink fails before data retrieval."""
    suite = ExperimentSuite(
        root=Path("/tmp"),
        baseline=None,
        datasource_config={
            "plugin": "csv",
            "security_level": "protected",
            "determinism_level": "guaranteed",
            "path": "/tmp/test.csv",
        },
        experiments=[
            ExperimentConfig(
                name="exp1",
                temperature=0.7,
                max_tokens=100,
                sink_defs=[
                    {
                        "plugin": "collecting",
                        "security_level": "official",  # Downgrade attempt
                        "determinism_level": "guaranteed",
                    }
                ],
            )
        ],
    )

    runner = ExperimentSuiteRunner(
        suite=suite,
        llm_client=SimpleLLM(security_level="protected"),
        sinks=[],
    )

    defaults = {
        "prompt_system": "Test",
        "prompt_template": "{{ text }}",
        "security_level": "protected",
    }

    with pytest.raises(SecurityError, match="Cannot operate PROTECTED datasource in OFFICIAL pipeline"):
        runner.run(pd.DataFrame([{"text": "test"}]), defaults)


def test_adr002_multiple_experiments_minimum_level_enforced():
    """ADR-002: Minimum security level across ALL experiments is enforced."""
    suite = ExperimentSuite(
        root=Path("/tmp"),
        baseline=None,
        datasource_config={
            "plugin": "csv",
            "security_level": "secret",
            "determinism_level": "guaranteed",
            "path": "/tmp/test.csv",
        },
        experiments=[
            ExperimentConfig(
                name="exp1",
                temperature=0.7,
                max_tokens=100,
                sink_defs=[
                    {
                        "plugin": "collecting",
                        "security_level": "secret",  # OK
                        "determinism_level": "guaranteed",
                    }
                ],
            ),
            ExperimentConfig(
                name="exp2",
                temperature=0.9,
                max_tokens=100,
                sink_defs=[
                    {
                        "plugin": "collecting",
                        "security_level": "official",  # MISCONFIGURED - one bad sink fails all
                        "determinism_level": "guaranteed",
                    }
                ],
            ),
        ],
    )

    runner = ExperimentSuiteRunner(
        suite=suite,
        llm_client=SimpleLLM(security_level="secret"),
        sinks=[],
    )

    defaults = {
        "prompt_system": "Test",
        "prompt_template": "{{ text }}",
        "security_level": "secret",
    }

    # Must fail because exp2 has OFFICIAL sink, bringing pipeline min to OFFICIAL
    with pytest.raises(SecurityError, match="Cannot operate SECRET datasource in OFFICIAL pipeline"):
        runner.run(pd.DataFrame([{"text": "test"}]), defaults)
```

---

## Integration Points in suite_runner.py

### Current Structure (Post-PR #11)

**Lines 281-419**: `run()` method orchestration
- Lines 281-310: Validation and setup
- Lines 311-357: Middleware notification loop
- Lines 359-419: Main experiment execution loop

### Recommended Integration Point

**Location**: After line 310 (before middleware notification)

**Rationale**:
- After DataFrame validation (line 297)
- After context setup is complete
- BEFORE middleware notifications (fail-fast principle)
- BEFORE any experiment execution (line 359+)

**Code insertion point**:
```python
# Line 310 (current code)
ctx = SuiteExecutionContext(
    results={},
    baseline_payload=None,
    baseline_experiment=self.suite.baseline,
)

# NEW: ADR-002 suite-level security enforcement
pipeline_min_level = self._compute_pipeline_security_level(
    suite=self.suite,
    defaults=defaults,
    sink_factory=sink_factory,
)
self._validate_datasource_security(pipeline_min_level)

# Line 311 (existing code continues)
notified_middlewares: dict[int, Any] = {}
```

---

## Risk Assessment

### Security Risks if NOT Implemented

| Risk | Likelihood | Impact | Severity |
|------|-----------|--------|----------|
| Classified data retrieved before security check | HIGH | CRITICAL | **P0** |
| Data spillage to low-security sinks | HIGH | CRITICAL | **P0** |
| Certification invalidation | MEDIUM | CRITICAL | **HIGH** |
| Audit trail shows security bypass | MEDIUM | HIGH | **MEDIUM** |

### Implementation Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Performance impact from security computation | LOW | LOW | Computation happens once at suite start, O(n) where n = component count |
| Breaking existing pipelines with undeclared levels | MEDIUM | HIGH | Fail-closed enforcement + clear error messages guide fixes |
| Sink resolution complexity | LOW | MEDIUM | Reuse existing 5-level resolution logic |

---

## Success Criteria

### Minimum Viable Implementation

1. ✅ `_compute_pipeline_security_level()` method added to suite_runner.py
2. ✅ `_validate_datasource_security()` method added to suite_runner.py
3. ✅ Both methods called in `run()` before middleware notification
4. ✅ 5 integration tests pass in `test_suite_runner_adr002_security.py`
5. ✅ All existing 39 suite_runner tests still pass
6. ✅ Security documentation updated in suite_runner.py docstrings

### Full Compliance

7. ✅ Certification test documentation added (similar to PR #11 format)
8. ✅ Error messages reference ADR-002 for operator guidance
9. ✅ Performance validation (security check < 10ms for typical suite)
10. ✅ ADR-002 marked as "Implemented" in architecture docs

---

## Estimated Effort

**Development**: 3-4 hours
- Helper methods: 1.5 hours
- Integration into suite_runner.py: 1 hour
- Test suite: 1.5 hours

**Testing & Validation**: 1-2 hours
- Existing test regression: 30 minutes
- New security tests: 30 minutes
- Edge case validation: 30 minutes

**Documentation**: 30 minutes
- Docstring updates
- ADR-002 status update

**Total**: 4.5-6.5 hours

---

## Next Steps

1. **Merge PR #11** - Complexity reduction refactoring (39/39 tests passing)
2. **Create ADR-002 implementation ticket** - Reference this document
3. **Implement Phase 1** - Add helper methods to suite_runner.py
4. **Implement Phase 2** - Integrate into run() method
5. **Implement Phase 3** - Add 5 integration tests
6. **Validation** - Run full test suite + certification tests
7. **Update ADR-002** - Mark as "Implemented" with commit reference

---

## References

- **ADR-002**: `docs/architecture/decisions/002-security-architecture.md`
- **ADR-001**: `docs/architecture/decisions/001-design-philosophy.md` (security > data integrity > availability)
- **Existing Plugin-Level Enforcement**: `tests/test_security_level_enforcement.py`
- **Suite Runner Code**: `src/elspeth/core/experiments/suite_runner.py`
- **Security Module**: `src/elspeth/core/security/__init__.py`

---

**Document Approval**: Ready for implementation after PR #11 merge

**Reviewed By**: [To be filled during implementation]
**Implementation PR**: [To be created]
