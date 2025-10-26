# ADR 003 – Central Plugin Type Registry for Security Validation (LITE)

## Status

**IMPLEMENTED** (Alternative Approach - 2025-10-27)
**Original Date**: 2025-10-25
**Implementation**: Sprint 2 (commits 3344cd5 through 9940da4)

## Context

**Problem**: P1 security gap - 4 plugin types (`row_plugins`, `aggregator_plugins`, `validation_plugins`, `early_stop_plugins`) bypassed ADR-002 validation due to manual enumeration in `suite_runner.py`.

**Root Cause**: Security validation manually enumerates plugin types:

```python
# suite_runner.py (FRAGILE)
plugins = []
plugins.append(datasource)
plugins.append(llm_client)
# ❌ Easy to forget when adding new plugin type
```

**Risk**: When adding new plugin types:

- ❌ No compiler enforcement to update validation
- ❌ No test failures if forgotten
- ❌ Silent security bypass - plugins process data without validation
- ❌ Violates ADR-002 guarantee: "no data at classification X reaches component with clearance Y < X"

## Decision: Three-Layer Defense

### Layer 1: Nominal Typing (ADR-004)

Convert `BasePlugin` from Protocol to ABC - require explicit inheritance:

```python
from abc import ABC, abstractmethod

class BasePlugin(ABC):
    @abstractmethod
    def get_security_level(self) -> SecurityLevel: ...
    @abstractmethod
    def validate_can_operate_at_level(self, level: SecurityLevel) -> None: ...
```

**Prevents**: Accidental plugin compliance via duck typing

### Layer 2: Central Registry

`PLUGIN_TYPE_REGISTRY` lists all plugin attributes with cardinality:

```python
# core/base/plugin_types.py
PLUGIN_TYPE_REGISTRY = {
    "llm_client": {"type": "singleton", "protocol": "LLMClient"},
    "llm_middlewares": {"type": "list", "protocol": "LLMMiddleware"},
    "row_plugins": {"type": "list", "protocol": "RowExperimentPlugin"},
    "aggregator_plugins": {"type": "list", "protocol": "AggregationExperimentPlugin"},
    "validation_plugins": {"type": "list", "protocol": "ValidationPlugin"},
    "early_stop_plugins": {"type": "list", "protocol": "EarlyStopPlugin"},
}

def collect_all_plugins(runner) -> list[BasePlugin]:
    plugins = []
    for attr_name, config in PLUGIN_TYPE_REGISTRY.items():
        attr = getattr(runner, attr_name, None)
        if attr is None:
            continue
        
        if config["type"] == "singleton":
            if isinstance(attr, BasePlugin):
                plugins.append(attr)
        elif config["type"] == "list":
            plugins.extend([p for p in attr if isinstance(p, BasePlugin)])
    
    return plugins
```

**Prevents**: Forgetting to collect new plugin types

### Layer 3: Test Enforcement

Test verifies registry completeness:

```python
def test_plugin_registry_complete():
    """SECURITY: Verify all plugin attributes are registered."""
    runner_attrs = [
        a for a in dir(ExperimentRunner)
        if (a.endswith('_plugins') or a.endswith('_middlewares') or a.endswith('_client'))
        and not a.startswith('_')
    ]
    
    registered = set(PLUGIN_TYPE_REGISTRY.keys())
    missing = set(runner_attrs) - registered
    
    assert not missing, (
        f"SECURITY: {missing} exist in ExperimentRunner but NOT in registry. "
        "Will bypass ADR-002 validation. Add to plugin_types.py."
    )

def test_plugin_registry_cardinality_correct():
    """SECURITY: Verify registry cardinality matches actual types."""
    # Verifies singleton vs list declarations match reality
```

**Prevents**: Registry falling out of sync with ExperimentRunner

## Defense Matrix

| Failure Mode | Layer 1 (ABC) | Layer 2 (Registry) | Layer 3 (Test) | Outcome |
|--------------|---------------|-------------------|----------------|---------|
| Accidental class with matching methods | ✅ CATCHES | - | - | Rejected |
| New plugin type, forgot to register | - | ❌ Misses | ✅ CATCHES | Test fails |
| New plugin type, forgot both | ✅ CATCHES | ❌ Misses | ✅ CATCHES | Test fails + rejected |
| Malicious plugin without inheritance | ✅ CATCHES | - | - | Rejected |
| Correct implementation | ✅ Passes | ✅ Passes | ✅ Passes | Works ✅ |

**Result**: No single point of failure. Multiple independent defenses.

## Optional Hardening (Swiss Cheese Model)

| Hardening | Closes Hole | Enforcement | Effort | Priority |
|-----------|-------------|-------------|--------|----------|
| **H1: MyPy Type Aliases** | Forgot to inherit | `mypy --strict` in CI | 15 min | HIGH |
| **H2: Pre-Commit Hook** | Didn't run test | Hook runs registry test | 10 min | HIGH |
| **H3: Auto-Generated Registry** | Forgot to register | Generate from type hints | 30 min | MEDIUM |
| **H4: Ruff Custom Lint** | Forgot to inherit | Custom rule | 45 min | LOW |

**Total Additional Effort**: ~1-1.5 hours

**With Hardening**: Developer must bypass MyPy + Ruff + pre-commit + CI = obvious malicious intent

## Implementation Plan

**Core Implementation (~1.5-2 hours)**:

1. **Phase 0: BasePlugin Migration (45 min)** - See ADR-004
   - Convert Protocol → ABC
   - Update all plugins to inherit explicitly

2. **Phase 1: Registry Infrastructure (30 min)**
   - Create `plugin_types.py` with `PLUGIN_TYPE_REGISTRY`
   - Create `collect_all_plugins()` helper
   - Update `suite_runner.py` to use helper

3. **Phase 2: Test Enforcement (20 min)**
   - Add `test_plugin_registry_complete()`
   - Add `test_plugin_registry_cardinality_correct()`

4. **Phase 3: Verification (15 min)**
   - Run full test suite
   - Verify security validation catches all plugins

## Consequences

**Positive**:

- ✅ Defense in depth (3 independent layers)
- ✅ Fail-loud (test alerts immediately)
- ✅ Auditability (registry in one file)
- ✅ Type safety (ABC + MyPy)

**Negative**:

- ⚠️ Breaking change: Existing code must add `(BasePlugin)` inheritance (see ADR-004)
- ⚠️ Manual step: Still requires updating registry (mitigated by test)
- ⚠️ Complexity: Three layers to understand (justified by security criticality)

## Usage Example

**Before (Fragile)**:

```python
def _validate_experiment_security(self, runner, sinks):
    plugins = []
    plugins.append(datasource)
    plugins.append(llm_client)
    # ❌ FRAGILE: Easy to forget new types
```

**After (Robust)**:

```python
from elspeth.core.base.plugin_types import collect_all_plugins

def _validate_experiment_security(self, runner, sinks):
    plugins = collect_all_plugins(runner)  # ✅ Registry ensures completeness
    
    # Add datasource and sinks separately
    if self.datasource:
        plugins.append(self.datasource)
    plugins.extend(sinks)
```

## Implementation Update (Sprint 2)

**Actual Implementation** took an **alternative architectural approach**:

**What Was Built**: `CentralPluginRegistry` facade (not PLUGIN_TYPE_REGISTRY for ExperimentRunner)

**Key Components**:
- `src/elspeth/core/registry/central.py` - Unified registry facade
- `src/elspeth/core/registry/auto_discover.py` - Automatic plugin discovery
- `EXPECTED_PLUGINS` baseline - Validation of discovered plugins

**Security Mechanism**:
- Single enforcement point for all plugin access
- Automatic discovery via module scanning (no manual registration)
- Validation layer ensures expected plugins present
- Fail-fast at import time (catches missing plugins before runtime)

**Migration Pattern**:
```python
# Before (scattered)
from elspeth.core.registries.datasource import datasource_registry
datasource = datasource_registry.create("local_csv", options)

# After (centralized)
from elspeth.core.registry import central_registry
datasource_registry = central_registry.get_registry("datasource")
datasource = datasource_registry.create("local_csv", options)
```

**Status**: ✅ COMPLETE
- 9 files migrated (6 source, 3 test)
- 1480 tests passing (up from 1466)
- Zero regressions
- Documentation complete (ADR-003, CLAUDE.md)

**Relationship to Original Vision**:
- Original plan: PLUGIN_TYPE_REGISTRY for ExperimentRunner plugin collection
- Actual implementation: CentralPluginRegistry for registry access consolidation
- Both achieve core objective: No plugin bypasses security validation
- Original PLUGIN_TYPE_REGISTRY concept remains valid for future enhancement

## Related

ADR-002 (MLS enforcement), ADR-004 (BasePlugin ABC), ADR-008 (Unified Registry Pattern), Incident: Commit 46faef7 (Copilot P1 finding)

---
**Last Updated**: 2025-10-27 (Sprint 2 Implementation Complete)
**Original Effort**: ~1.5-2 hours core + ~1-1.5 hours optional hardening
**Actual Effort**: ~16.5 hours (enhanced with auto-discovery + validation)
