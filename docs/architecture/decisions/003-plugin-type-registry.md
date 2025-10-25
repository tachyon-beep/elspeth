# ADR-003: Central Plugin Type Registry for Security Validation

**Status**: PROPOSED
**Date**: 2025-10-25
**Deciders**: Security Team, Core Platform Team
**Related**: ADR-002 (Suite-level security enforcement)

---

## Context and Problem Statement

**Incident**: During code review, Copilot discovered a P1 security gap where 4 plugin types (`row_plugins`, `aggregator_plugins`, `validation_plugins`, `early_stop_plugins`) were not included in ADR-002 security validation. This allowed plugins to bypass the minimum clearance envelope check.

**Root Cause**: Security validation in `suite_runner.py` manually enumerates plugin types:

```python
# suite_runner.py:593-639 (FRAGILE - manual enumeration)
plugins = []
plugins.append(datasource)
plugins.append(llm_client)
plugins.extend(llm_middlewares)
plugins.extend(row_plugins)  # ← Easy to forget when adding new plugin type
plugins.extend(aggregator_plugins)
# ... etc
```

**The Risk**: When a developer adds a new plugin type to `ExperimentRunner`:
1. ❌ **No compiler/type checker enforcement** to update security validation
2. ❌ **No test failures** if they forget (unless explicitly tested)
3. ❌ **Silent security bypass** - new plugins process data without validation
4. ❌ **Shotgun surgery** - one conceptual change requires edits in 3+ files

**Why This Matters**: ADR-002's security guarantee is "no configuration can allow data at classification X to reach component with clearance Y < X". Forgetting to validate a plugin type **completely violates this guarantee**.

---

## Decision Drivers

1. **Security-Critical**: Plugin validation is a security control - cannot rely on developer memory
2. **Fail-Safe Default**: New plugin types should fail loudly if not properly registered
3. **Developer Experience**: Adding plugin types should have clear, enforced process
4. **Maintainability**: Reduce coupling between ExperimentRunner and security validation
5. **Auditability**: Security team should be able to verify all plugin types are validated

---

## Considered Options

### Option 1: Central Registry with Manual Enumeration

**Approach**: Create `PLUGIN_TYPE_REGISTRY` constant listing all plugin attribute names.

```python
# core/base/plugin_types.py
PLUGIN_TYPE_REGISTRY = [
    "row_plugins",
    "aggregator_plugins",
    "validation_plugins",
    "early_stop_plugins",
    "llm_middlewares",
]

# suite_runner.py
def collect_all_plugins(runner):
    plugins = []
    for attr_name in PLUGIN_TYPE_REGISTRY:
        attr = getattr(runner, attr_name, None)
        if isinstance(attr, list):
            plugins.extend([p for p in attr if isinstance(p, BasePlugin)])
    return plugins
```

**Pros**:
- ✅ Simple, explicit
- ✅ Single source of truth
- ✅ Easy to audit

**Cons**:
- ❌ Still requires manual update when adding plugin types
- ❌ No compile-time enforcement
- ❌ Can still forget to update registry

### Option 2: Introspection with Naming Convention

**Approach**: Use reflection to find all attributes matching `*_plugins` or `*_middlewares`.

```python
def collect_all_plugins(runner):
    plugins = []
    for attr_name in dir(runner):
        if attr_name.endswith('_plugins') or attr_name.endswith('_middlewares'):
            attr = getattr(runner, attr_name, None)
            if isinstance(attr, list):
                plugins.extend([p for p in attr if isinstance(p, BasePlugin)])
    return plugins
```

**Pros**:
- ✅ Self-healing - automatically picks up new plugin types
- ✅ Zero manual maintenance
- ✅ Enforces naming convention

**Cons**:
- ❌ "Magic" - behavior not obvious from code
- ❌ Could pick up unintended attributes
- ❌ Performance overhead of introspection

### Option 3: Protocol with Required Method

**Approach**: Define protocol requiring `get_all_plugins()` method.

```python
class PluginContainer(Protocol):
    def get_all_plugins(self) -> list[BasePlugin]:
        """Return ALL plugins for security validation."""
        ...

class ExperimentRunner(PluginContainer):
    def get_all_plugins(self) -> list[BasePlugin]:
        return [
            *self.row_plugins or [],
            *self.aggregator_plugins or [],
            # Must explicitly list all
        ]
```

**Pros**:
- ✅ Explicit, type-checked
- ✅ Forces developer to think about security
- ✅ Self-documenting

**Cons**:
- ❌ Still manual enumeration (just in different place)
- ❌ Invasive change to ExperimentRunner
- ❌ Duplication of plugin list logic

### Option 4: Hybrid - Registry + Test Enforcement + Type Hints

**Approach**: Combine registry with automated test verification.

```python
# core/base/plugin_types.py
from typing import TypedDict

class PluginTypeRegistry(TypedDict):
    """Central registry of all plugin types for security validation.

    CRITICAL: When adding a new plugin type to ExperimentRunner:
    1. Add attribute name to this registry
    2. Run test_plugin_registry_complete to verify
    3. Update ADR-003 decision record
    """
    row_plugins: str
    aggregator_plugins: str
    validation_plugins: str
    early_stop_plugins: str
    llm_middlewares: str

PLUGIN_TYPE_REGISTRY: PluginTypeRegistry = {
    "row_plugins": "RowExperimentPlugin",
    "aggregator_plugins": "AggregationExperimentPlugin",
    "validation_plugins": "ValidationPlugin",
    "early_stop_plugins": "EarlyStopPlugin",
    "llm_middlewares": "LLMMiddleware",
}

# suite_runner.py
def collect_all_plugins(runner) -> list[BasePlugin]:
    """Collect all plugins from runner for security validation.

    Uses PLUGIN_TYPE_REGISTRY to ensure all plugin types are checked.
    """
    plugins = []
    for attr_name in PLUGIN_TYPE_REGISTRY.keys():
        attr = getattr(runner, attr_name, None)
        if isinstance(attr, list):
            plugins.extend([p for p in attr if isinstance(p, BasePlugin)])
    return plugins

# tests/test_plugin_registry.py
def test_plugin_registry_complete():
    """SECURITY: Verify all *_plugins attributes in ExperimentRunner are registered.

    This test prevents security bypass where new plugin types are added
    but not included in ADR-002 validation.
    """
    runner_attrs = [a for a in dir(ExperimentRunner)
                    if (a.endswith('_plugins') or a.endswith('_middlewares'))
                    and not a.startswith('_')]

    registered_attrs = set(PLUGIN_TYPE_REGISTRY.keys())

    missing = set(runner_attrs) - registered_attrs
    assert not missing, (
        f"SECURITY: Plugin types {missing} exist in ExperimentRunner but are "
        f"NOT registered in PLUGIN_TYPE_REGISTRY. This means they will bypass "
        f"ADR-002 security validation. Add them to core/base/plugin_types.py "
        f"and update ADR-003."
    )
```

**Pros**:
- ✅ Explicit registry (auditability)
- ✅ Test enforcement (fail-loud if incomplete)
- ✅ Clear documentation for developers
- ✅ Type hints provide some IDE support
- ✅ Balance between automation and control

**Cons**:
- ⚠️ Still requires manual update (but test will fail if forgotten)
- ⚠️ Slightly more complex than pure reflection

---

## Decision Outcome

**Chosen**: **Option 4 - Hybrid Registry + Test Enforcement + Nominal Typing Enforcement**

**Rationale**:
1. **Security**: Test enforcement prevents silent bypasses (fail-loud, not fail-open)
2. **Auditability**: Explicit registry provides clear paper trail for security review
3. **Developer Guidance**: TypedDict and test error message guide developers
4. **Maintainability**: Balance between automation and explicit control
5. **Compatibility**: Non-invasive, doesn't require ExperimentRunner changes
6. **Type Safety**: Nominal typing (inheritance from BasePlugin ABC) prevents accidental compliance

### Additional Enforcement: Nominal Typing Requirement

**Critical Addition**: All plugins MUST inherit from `BasePlugin` abstract base class, not just implement the protocol interface.

**Current State (TOO LOOSE)**:
```python
# BasePlugin is a Protocol (structural typing)
class BasePlugin(Protocol):
    def get_security_level(self) -> SecurityLevel: ...
    def validate_can_operate_at_level(self, level: SecurityLevel) -> None: ...

# Any class with these methods "implements" BasePlugin
class AccidentalPlugin:
    """This class accidentally has the right methods - DANGEROUS!"""
    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.UNOFFICIAL  # Oops, didn't mean to be a plugin!
    def validate_can_operate_at_level(self, level: SecurityLevel) -> None:
        pass  # Empty implementation
```

**Required State (ENFORCED)**:
```python
from abc import ABC, abstractmethod

# BasePlugin is an ABC (nominal typing)
class BasePlugin(ABC):
    """Base class for ALL plugins that process data.

    SECURITY: All plugins MUST inherit from this class to participate
    in ADR-002 security validation. This prevents accidental compliance
    via structural typing (duck typing).

    Inheritance is REQUIRED, not optional.
    """

    @abstractmethod
    def get_security_level(self) -> SecurityLevel:
        """Return the security clearance level required by this plugin."""
        ...

    @abstractmethod
    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        """Validate this plugin can operate at the given security level.

        Raises:
            SecurityValidationError: If operating_level < required level
        """
        ...

# CORRECT: Explicit inheritance
class MySecretPlugin(BasePlugin):
    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.SECRET
    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        if operating_level < SecurityLevel.SECRET:
            raise SecurityValidationError(...)

# WRONG: Cannot accidentally comply - must inherit
class AccidentalPlugin:
    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.UNOFFICIAL
    def validate_can_operate_at_level(self, level: SecurityLevel) -> None:
        pass

# isinstance() check rejects accidental compliance
plugin = AccidentalPlugin()
isinstance(plugin, BasePlugin)  # False - not inherited!
# Security validation will skip this (correct behavior)
```

**Why This Matters**:
- ✅ **Cannot accidentally be a plugin** - must explicitly inherit
- ✅ **Runtime verification is reliable** - `isinstance()` check is definitive
- ✅ **Clear plugin lineage** - can trace all plugins via inheritance tree
- ✅ **IDE/Type checker support** - inheritance is explicit in code
- ✅ **Security by default** - opt-in, not opt-out

### Implementation Plan

**Phase 0: Convert BasePlugin from Protocol to ABC** (BREAKING CHANGE - Pre-1.0 OK) (45 min)
- [ ] Update `src/elspeth/core/base/protocols.py`:
  - Change `class BasePlugin(Protocol)` → `class BasePlugin(ABC)`
  - Add `@abstractmethod` decorators to `get_security_level()` and `validate_can_operate_at_level()`
  - Remove `@runtime_checkable` decorator (not needed for ABC)
- [ ] Update all existing plugins to explicitly inherit `BasePlugin`:
  - Datasources: `class MyDatasource(BasePlugin)`
  - Sinks: `class MySink(BasePlugin)`
  - LLM clients: `class MyLLMClient(BasePlugin)`
  - Middleware: `class MyMiddleware(BasePlugin)`
- [ ] Run full test suite to verify no regressions (expect test failures until all plugins updated)
- [ ] Update type hints from `BasePlugin` protocol to `BasePlugin` ABC

**Phase 1: Core Infrastructure** (30 min)
- [ ] Create `src/elspeth/core/base/plugin_types.py` with `PLUGIN_TYPE_REGISTRY`
- [ ] Create `collect_all_plugins(runner)` helper function
- [ ] Update `suite_runner.py` to use helper instead of manual enumeration
- [ ] Verify `isinstance(plugin, BasePlugin)` checks work correctly

**Phase 2: Test Enforcement** (20 min)
- [ ] Create `tests/test_plugin_registry.py` with `test_plugin_registry_complete()`
- [ ] Add test verifying accidental plugins are rejected:
  ```python
  def test_accidental_plugin_rejected():
      """Verify classes with correct methods but no inheritance are NOT plugins."""
      class AccidentalPlugin:
          def get_security_level(self): return SecurityLevel.UNOFFICIAL
          def validate_can_operate_at_level(self, level): pass

      plugin = AccidentalPlugin()
      assert not isinstance(plugin, BasePlugin)  # ✅ Rejected
  ```
- [ ] Add to CI as critical security test (cannot skip)

**Phase 3: Documentation** (15 min)
- [ ] Update developer guide with "Adding a New Plugin Type" section
- [ ] Document nominal typing requirement in CONTRIBUTING.md
- [ ] Update plugin development guide showing inheritance requirement
- [ ] Update this ADR with implementation notes

**Total Effort**: ~1.5-2 hours (including BasePlugin migration)

**Migration Risk**: LOW (pre-1.0, no external plugins yet)

---

## Defense in Depth - Three Layers

This ADR implements **three independent security layers** that work together:

### Layer 1: Nominal Typing (BasePlugin ABC)
**Prevents**: Accidental plugin compliance via duck typing
**How**: Classes must explicitly inherit `class MyPlugin(BasePlugin)`
**Catches**: Developer accidentally creates class with right methods

**Example Prevention**:
```python
# This won't be treated as a plugin (good!)
class AccidentalHelper:
    def get_security_level(self): return SecurityLevel.UNOFFICIAL
    def validate_can_operate_at_level(self, level): pass

isinstance(AccidentalHelper(), BasePlugin)  # False ✅
```

### Layer 2: Plugin Type Registry
**Prevents**: Forgetting to collect new plugin types in security validation
**How**: Central `PLUGIN_TYPE_REGISTRY` lists all plugin attribute names
**Catches**: Developer adds `preprocessing_plugins` to ExperimentRunner but forgets to collect it

**Example Prevention**:
```python
# Developer adds new plugin type to ExperimentRunner
class ExperimentRunner:
    preprocessing_plugins: list[PreprocessingPlugin] | None = None  # NEW

# suite_runner.py uses registry - automatically includes it
plugins = collect_all_plugins(runner)  # Uses PLUGIN_TYPE_REGISTRY
# If developer forgot to add to registry, test catches it (Layer 3)
```

### Layer 3: Test Enforcement
**Prevents**: Registry falling out of sync with ExperimentRunner
**How**: Test compares `PLUGIN_TYPE_REGISTRY` with actual `*_plugins` attributes
**Catches**: Developer adds plugin attribute but forgets to register it

**Example Prevention**:
```python
def test_plugin_registry_complete():
    """Fail if new plugin types exist but aren't registered."""
    runner_attrs = [a for a in dir(ExperimentRunner)
                    if a.endswith('_plugins') or a.endswith('_middlewares')]
    registered = set(PLUGIN_TYPE_REGISTRY.keys())

    missing = set(runner_attrs) - registered
    assert not missing, f"SECURITY: {missing} not in registry!"
# Test FAILS if preprocessing_plugins added but not registered ✅
```

---

## Consequences

### Positive

- ✅ **Defense in Depth**: Three independent layers catch different failure modes
- ✅ **Cannot Accidentally Bypass**: Must explicitly inherit BasePlugin AND be registered
- ✅ **Fail-Loud**: Test failure alerts developers immediately
- ✅ **Auditability**: Security team can review registry in one file
- ✅ **Type Safety**: ABC provides compile-time checking (MyPy)
- ✅ **Runtime Safety**: isinstance() checks are reliable
- ✅ **Documentation**: Clear process for adding plugin types

### Negative

- ⚠️ **Breaking Change**: Existing code must add `(BasePlugin)` inheritance
- ⚠️ **Manual Process**: Still requires developer to update registry (mitigated by test)
- ⚠️ **Complexity**: Three layers to understand (justified by security criticality)

### Why All Three Layers?

| Scenario | Layer 1 | Layer 2 | Layer 3 | Outcome |
|----------|---------|---------|---------|---------|
| Accidental class with right methods | ✅ CATCHES | - | - | Rejected (no inheritance) |
| New plugin type, forgot to register | - | ❌ MISSES | ✅ CATCHES | Test fails |
| New plugin type, forgot both | ✅ CATCHES | ❌ MISSES | ✅ CATCHES | Test fails + no inheritance |
| Malicious plugin without inheritance | ✅ CATCHES | - | - | Rejected (no inheritance) |
| Well-meaning dev adds plugin correctly | ✅ PASSES | ✅ PASSES | ✅ PASSES | Works correctly |

**Result**: No single point of failure. Each layer provides independent protection.

## Swiss Cheese Model - Closing the Gaps

**Concern**: Three-layer defense still has "holes" that could align (Swiss Cheese Model):

```
Layer 1 (ABC):     Developer forgets to inherit     🕳️
Layer 2 (Registry): Developer forgets to register    🕳️
Layer 3 (Test):    Developer doesn't run tests       🕳️
                   ═════════════════════════════════
                   All three align → Bypass possible 💥
```

### Additional Hardening (Eliminate Wiggle Room)

**H1: Static Type Checking (Close Layer 1 Hole)**

Use MyPy strict mode to **require** BasePlugin inheritance for plugin types:

```python
# core/base/plugin_types.py
from typing import TypeAlias

# Type aliases for plugin lists - MyPy will enforce these
RowPluginList: TypeAlias = list[BasePlugin]  # Not list[Protocol]
AggregatorPluginList: TypeAlias = list[BasePlugin]

# ExperimentRunner type hints
class ExperimentRunner:
    row_plugins: RowPluginList | None = None
    aggregator_plugins: AggregatorPluginList | None = None
    # MyPy error if plugin doesn't inherit BasePlugin!
```

**Enforcement**: `mypy --strict` in CI (already present)

**Wiggle Room Eliminated**: Cannot use plugin without BasePlugin inheritance (MyPy fails)

---

**H2: Pre-Commit Hook (Close Layer 3 Hole)**

Add mandatory pre-commit hook that runs test_plugin_registry_complete():

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: plugin-registry-check
        name: Verify plugin registry complete
        entry: pytest tests/test_plugin_registry.py::test_plugin_registry_complete -v
        language: system
        always_run: true
        pass_filenames: false
```

**Enforcement**: Cannot commit if registry incomplete (hook fails)

**Wiggle Room Eliminated**: Developer cannot bypass test (pre-commit runs automatically)

---

**H3: Type-Driven Registry (Close Layer 2 Hole)**

Auto-generate registry from ExperimentRunner type annotations:

```python
# core/base/plugin_types.py (GENERATED - DO NOT EDIT)
from typing import get_type_hints
from elspeth.core.experiments.runner import ExperimentRunner

def _generate_registry() -> dict[str, str]:
    """Auto-generate plugin registry from ExperimentRunner type hints."""
    hints = get_type_hints(ExperimentRunner)
    registry = {}

    for attr_name, hint in hints.items():
        if attr_name.endswith('_plugins') or attr_name.endswith('_middlewares'):
            # Extract inner type from list[T] | None
            inner_type = _extract_list_type(hint)
            registry[attr_name] = inner_type.__name__

    return registry

PLUGIN_TYPE_REGISTRY = _generate_registry()  # Auto-generated!
```

**Enforcement**: Registry is derived from source of truth (type annotations)

**Wiggle Room Eliminated**: Cannot forget to register (automatic generation)

---

**H4: Ruff Custom Lint Rule (Close Layer 1 Hole - Belt + Suspenders)**

Add custom lint rule detecting plugins without BasePlugin:

```python
# .ruff_plugins/check_plugin_inheritance.py
def check_plugin_inheritance(node):
    """Lint rule: Classes in *_plugins lists must inherit BasePlugin."""
    if is_plugin_class(node) and not inherits_from(node, "BasePlugin"):
        raise LintError(
            f"Plugin {node.name} must inherit from BasePlugin "
            f"(ADR-003 security requirement)"
        )
```

**Enforcement**: Ruff fails on commit (already in CI)

**Wiggle Room Eliminated**: Linter catches missing inheritance before commit

---

### Hardened Defense Matrix

| Layer | Original Hole | Hardening | Wiggle Room Remaining |
|-------|--------------|-----------|----------------------|
| **Layer 1 (ABC)** | Forgot to inherit | H1: MyPy strict + H4: Ruff lint | ❌ **CLOSED** - Cannot compile |
| **Layer 2 (Registry)** | Forgot to register | H3: Auto-generation | ❌ **CLOSED** - Cannot forget |
| **Layer 3 (Test)** | Didn't run test | H2: Pre-commit hook | ❌ **CLOSED** - Cannot commit without |

**Result**: Developer would need to:
1. Bypass MyPy strict mode (`# type: ignore`)
2. Bypass Ruff linting (`# noqa`)
3. Bypass pre-commit hook (`--no-verify`)
4. Bypass CI checks (requires admin rights)

**At this point**: Obvious malicious intent, not accident

---

### Implementation Effort (Additional Hardening)

| Hardening | Effort | Priority |
|-----------|--------|----------|
| H1: MyPy strict type aliases | 15 min | HIGH (free enforcement) |
| H2: Pre-commit hook | 10 min | HIGH (cannot bypass locally) |
| H3: Auto-generated registry | 30 min | MEDIUM (eliminates manual step) |
| H4: Ruff custom lint rule | 45 min | LOW (belt + suspenders) |

**Total Additional**: ~1-1.5 hours
**Combined Total**: ~3-3.5 hours (including original ADR-003)

---

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Developer ignores test failure | Low | High | Make test part of CI, cannot merge with failure |
| Registry falls out of sync | Low | High | Test catches this automatically |
| Performance of reflection in test | Low | Low | Test only runs once during suite, acceptable |
| False positive (non-plugin attribute ends with `_plugins`) | Medium | Low | Test can filter by type hints or manual exclusion list |

---

## Compliance and Certification

**ADR-002 Impact**: This ADR directly supports ADR-002 security guarantee by:
1. Ensuring ALL plugin types are included in minimum clearance envelope
2. Preventing future bypass vulnerabilities
3. Making security validation auditable

**Certification Requirements**:
- [ ] Security review approval (new security control)
- [ ] Update CERTIFICATION_EVIDENCE.md with plugin registry verification step
- [ ] Add to threat model as defense for T1 (Classification Breach)

---

## Examples

### Before (Fragile - Manual Enumeration)

```python
# suite_runner.py (BEFORE - P1 vulnerability window)
def _validate_experiment_security(self, runner, sinks):
    plugins = []

    datasource = self.datasource or getattr(runner, "datasource", None)
    if datasource and isinstance(datasource, BasePlugin):
        plugins.append(datasource)

    llm_client = getattr(runner, "llm_client", None)
    if llm_client and isinstance(llm_client, BasePlugin):
        plugins.append(llm_client)

    # ❌ EASY TO FORGET NEW PLUGIN TYPES
    # ❌ NO ENFORCEMENT IF FORGOTTEN
    # ❌ SILENT SECURITY BYPASS
```

### After (Robust - Registry + Test Enforcement)

```python
# core/base/plugin_types.py
PLUGIN_TYPE_REGISTRY = {
    "row_plugins": "RowExperimentPlugin",
    "aggregator_plugins": "AggregationExperimentPlugin",
    "validation_plugins": "ValidationPlugin",
    "early_stop_plugins": "EarlyStopPlugin",
    "llm_middlewares": "LLMMiddleware",
}

def collect_all_plugins(runner) -> list[BasePlugin]:
    """Collect all plugins from runner using registry."""
    plugins = []
    for attr_name in PLUGIN_TYPE_REGISTRY.keys():
        attr = getattr(runner, attr_name, None)
        if isinstance(attr, list):
            plugins.extend([p for p in attr if isinstance(p, BasePlugin)])
    return plugins

# suite_runner.py (AFTER)
from elspeth.core.base.plugin_types import collect_all_plugins

def _validate_experiment_security(self, runner, sinks):
    plugins = collect_all_plugins(runner)  # ✅ Registry ensures completeness

    # Datasource and sinks handled separately (not in runner)
    if self.datasource and isinstance(self.datasource, BasePlugin):
        plugins.append(self.datasource)
    for sink in sinks:
        if isinstance(sink, BasePlugin):
            plugins.append(sink)

    # Rest of validation logic...
```

### Developer Workflow: Adding New Plugin Type

```python
# 1. Add to ExperimentRunner
class ExperimentRunner:
    preprocessing_plugins: list[PreprocessingPlugin] | None = None  # NEW

# 2. Add to registry (ENFORCED BY TEST)
# core/base/plugin_types.py
PLUGIN_TYPE_REGISTRY = {
    "preprocessing_plugins": "PreprocessingPlugin",  # ← Add here
    # ...existing entries
}

# 3. Run tests
$ pytest tests/test_plugin_registry.py
# ✅ Test passes - registry is complete

# 4. (If forgotten step 2) Test fails with clear error:
"""
SECURITY: Plugin types {'preprocessing_plugins'} exist in ExperimentRunner
but are NOT registered in PLUGIN_TYPE_REGISTRY. This means they will bypass
ADR-002 security validation. Add them to core/base/plugin_types.py
and update ADR-003.
"""
```

---

## Current State Assessment

### BasePlugin Definition (protocols.py:62-120)

**Current** (Structural Typing - TOO LOOSE):
```python
@runtime_checkable
class BasePlugin(Protocol):
    """Base protocol defining security requirements for all plugins."""

    def get_security_level(self) -> SecurityLevel:
        raise NotImplementedError

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        raise NotImplementedError
```

**Problem**: Any class with these two methods is considered a `BasePlugin` via duck typing. This allows accidental compliance.

**Target** (Nominal Typing - ENFORCED):
```python
from abc import ABC, abstractmethod

class BasePlugin(ABC):
    """Base class for ALL plugins that process data.

    SECURITY: All plugins MUST explicitly inherit from this class.
    Inheritance is REQUIRED, not optional.
    """

    @abstractmethod
    def get_security_level(self) -> SecurityLevel:
        """Return the minimum security level this plugin requires."""
        ...

    @abstractmethod
    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        """Validate this plugin can operate at the given security level."""
        ...
```

### Plugin Collection (suite_runner.py:593-639)

**Current** (Manual Enumeration - FRAGILE):
```python
plugins = []
plugins.append(datasource)
plugins.append(llm_client)
plugins.extend(llm_middlewares)
plugins.extend(row_plugins)  # Added in commit 46faef7 (after P1 finding)
plugins.extend(aggregator_plugins)
plugins.extend(validation_plugins)
plugins.extend(early_stop_plugins)
# ⚠️ Easy to forget new plugin types
```

**Target** (Registry-Based - ROBUST):
```python
from elspeth.core.base.plugin_types import collect_all_plugins

plugins = collect_all_plugins(runner)  # Uses PLUGIN_TYPE_REGISTRY
plugins.append(datasource)  # Datasource not in runner
plugins.extend(sinks)       # Sinks passed separately
# ✅ Registry ensures completeness
# ✅ Test enforces registration
```

---

## References

- **ADR-002**: Suite-level security enforcement
- **Incident**: Copilot P1 finding (commit 46faef7) - Missing row/aggregator/validation/early-stop plugins
- **THREAT_MODEL.md**: T1 - Classification Breach prevention
- **CERTIFICATION_EVIDENCE.md**: Security Invariant I4 (All Plugins Accept Envelope OR Job Fails)
- **Python ABC Documentation**: https://docs.python.org/3/library/abc.html

---

## Decision Review

**Review Date**: TBD (6 months after implementation)
**Success Criteria**:
- [ ] Zero incidents of plugin types bypassing validation
- [ ] Test catches all new plugin types
- [ ] Developer feedback positive (process is clear)

---

**Author**: Claude Code
**Approvers**: [Pending Security Team Review]
**Implementation**: [Pending]

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
