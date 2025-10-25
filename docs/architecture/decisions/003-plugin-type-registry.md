# ADR-003: Central Plugin Type Registry for Security Validation

**Status**: PROPOSED
**Date**: 2025-10-25
**Deciders**: Security Team, Core Platform Team
**Related**: ADR-002 (Suite-level security), ADR-004 (Mandatory BasePlugin inheritance)

---

## Executive Summary

**Problem**: P1 security gap discovered where 4 plugin types bypassed ADR-002 validation due to manual enumeration in `suite_runner.py`.

**Solution**: Three-layer defense:
1. **Layer 1 (ADR-004)**: Nominal typing - plugins must inherit `BasePlugin` ABC
2. **Layer 2**: Central `PLUGIN_TYPE_REGISTRY` - explicit list of all plugin types
3. **Layer 3**: Test enforcement - fails if registry incomplete

**Impact**: Prevents future plugin types from bypassing security validation.

**Effort**: ~1.5-2 hours implementation + ~1-1.5 hours optional hardening (H1-H4)

---

## Context and Problem Statement

### The Incident

During code review, Copilot discovered 4 plugin types (`row_plugins`, `aggregator_plugins`, `validation_plugins`, `early_stop_plugins`) were missing from ADR-002 security validation, allowing plugins to bypass minimum clearance envelope checks.

### Root Cause

Security validation manually enumerates plugin types:

```python
# suite_runner.py:593-639 (FRAGILE)
plugins = []
plugins.append(datasource)
plugins.append(llm_client)
plugins.extend(llm_middlewares)
# ❌ Easy to forget when adding new plugin type
```

### The Risk

When developers add new plugin types to `ExperimentRunner`:
- ❌ No compiler enforcement to update security validation
- ❌ No test failures if forgotten
- ❌ Silent security bypass - plugins process data without validation
- ❌ Shotgun surgery - requires edits in 3+ files

**Security Impact**: Violates ADR-002's core guarantee: "no configuration allows data at classification X to reach component with clearance Y < X"

---

## Decision Drivers

1. **Security-Critical**: Plugin validation is a security control - cannot rely on developer memory
2. **Fail-Loud Default**: New plugin types should fail immediately if not registered
3. **Developer Experience**: Clear, enforced process for adding plugin types
4. **Maintainability**: Reduce coupling between ExperimentRunner and security code
5. **Auditability**: Security team can verify completeness in one location

---

## Decision

**Chosen Solution**: Hybrid registry + test enforcement + nominal typing (3 independent layers)

### Layer 1: Nominal Typing (ADR-004)

**Mechanism**: Convert `BasePlugin` from Protocol to ABC - require explicit inheritance

```python
from abc import ABC, abstractmethod

class BasePlugin(ABC):
    @abstractmethod
    def get_security_level(self) -> SecurityLevel: ...

    @abstractmethod
    def validate_can_operate_at_level(self, level: SecurityLevel) -> None: ...
```

**Prevents**: Accidental plugin compliance via duck typing

**See**: ADR-004 for full details and implementation plan

### Layer 2: Central Registry

**Mechanism**: `PLUGIN_TYPE_REGISTRY` lists all plugin attribute names with cardinality

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
    """Collect all plugins using registry (handles both singletons and lists)."""
    plugins = []
    for attr_name, config in PLUGIN_TYPE_REGISTRY.items():
        attr = getattr(runner, attr_name, None)
        if attr is None:
            continue

        if config["type"] == "singleton":
            # Singleton plugin (e.g., llm_client)
            if isinstance(attr, BasePlugin):
                plugins.append(attr)
        elif config["type"] == "list":
            # List of plugins (e.g., llm_middlewares, row_plugins)
            plugins.extend([p for p in attr if isinstance(p, BasePlugin)])

    return plugins
```

**Prevents**: Forgetting to collect new plugin types (both singletons and lists)

### Layer 3: Test Enforcement

**Mechanism**: Test verifies registry completeness (including singleton plugins)

```python
# tests/test_plugin_registry.py
def test_plugin_registry_complete():
    """SECURITY: Verify all plugin attributes are registered (lists AND singletons)."""
    from typing import get_type_hints

    # Get all plugin-related attributes from ExperimentRunner
    runner_attrs = [
        a for a in dir(ExperimentRunner)
        if (a.endswith('_plugins') or a.endswith('_middlewares') or a.endswith('_client'))
        and not a.startswith('_')
    ]

    registered = set(PLUGIN_TYPE_REGISTRY.keys())
    missing = set(runner_attrs) - registered

    assert not missing, (
        f"SECURITY: {missing} exist in ExperimentRunner but NOT in registry. "
        f"Will bypass ADR-002 validation. Add to plugin_types.py with correct cardinality "
        f"(singleton or list)."
    )

def test_plugin_registry_cardinality_correct():
    """SECURITY: Verify registry cardinality matches actual attribute types."""
    runner = ExperimentRunner(...)  # Mock/fixture

    for attr_name, config in PLUGIN_TYPE_REGISTRY.items():
        attr = getattr(runner, attr_name, None)
        if attr is None:
            continue

        if config["type"] == "singleton":
            assert not isinstance(attr, list), (
                f"Registry declares {attr_name} as singleton but it's a list!"
            )
        elif config["type"] == "list":
            assert isinstance(attr, list), (
                f"Registry declares {attr_name} as list but it's a singleton!"
            )
```

**Prevents**: Registry falling out of sync with ExperimentRunner (both cardinality and completeness)

---

## Defense Matrix

| Failure Mode | Layer 1 (ABC) | Layer 2 (Registry) | Layer 3 (Test) | Outcome |
|--------------|---------------|-------------------|----------------|---------|
| Accidental class with matching methods | ✅ **CATCHES** | - | - | Rejected (no inheritance) |
| New plugin type, forgot to register | - | ❌ Misses | ✅ **CATCHES** | Test fails |
| New plugin type, forgot both | ✅ **CATCHES** | ❌ Misses | ✅ **CATCHES** | Test fails + rejected |
| Malicious plugin without inheritance | ✅ **CATCHES** | - | - | Rejected |
| Correct implementation | ✅ Passes | ✅ Passes | ✅ Passes | Works ✅ |

**Result**: No single point of failure. Multiple independent defenses.

---

## Swiss Cheese Model - Additional Hardening

**Optional**: Four additional measures to eliminate remaining "wiggle room":

| Hardening | Closes Hole | Enforcement | Effort | Priority |
|-----------|-------------|-------------|--------|----------|
| **H1: MyPy Type Aliases** | Layer 1 (forgot to inherit) | `mypy --strict` in CI | 15 min | HIGH |
| **H2: Pre-Commit Hook** | Layer 3 (didn't run test) | Hook runs `test_plugin_registry_complete()` | 10 min | HIGH |
| **H3: Auto-Generated Registry** | Layer 2 (forgot to register) | Generate from `ExperimentRunner` type hints | 30 min | MEDIUM |
| **H4: Ruff Custom Lint** | Layer 1 (forgot to inherit) | Custom rule detects missing `BasePlugin` | 45 min | LOW |

**Total Additional Effort**: ~1-1.5 hours

**With Hardening**: Developer would need to bypass MyPy + Ruff + pre-commit + CI (requires admin) = obvious malicious intent

**See**: Appendix A for implementation details

---

## Consequences

### Positive

- ✅ **Defense in Depth**: Three independent layers catch different failure modes
- ✅ **Fail-Loud**: Test failure alerts developers immediately (no silent bypass)
- ✅ **Auditability**: Security team reviews registry in one file
- ✅ **Type Safety**: ABC + MyPy provide compile-time checking
- ✅ **Runtime Safety**: `isinstance()` checks are reliable
- ✅ **Clear Process**: Developers know exactly what to do

### Negative

- ⚠️ **Breaking Change**: Existing code must add `(BasePlugin)` inheritance (see ADR-004)
- ⚠️ **Manual Step**: Still requires updating registry (mitigated by test enforcement)
- ⚠️ **Complexity**: Three layers to understand (justified by security criticality)

### Neutral

- ➡️ **Pre-1.0 Only**: Breaking changes acceptable now, not post-1.0
- ➡️ **One-Time Cost**: Migration is one-time, ongoing benefit

---

## Implementation Plan

### Core Implementation (~1.5-2 hours)

**Phase 0: BasePlugin Migration (45 min)** - See ADR-004
- Convert `BasePlugin` Protocol → ABC
- Update all existing plugins to inherit explicitly
- Update type hints

**Phase 1: Registry Infrastructure (30 min)**
- Create `src/elspeth/core/base/plugin_types.py` with `PLUGIN_TYPE_REGISTRY`
- Create `collect_all_plugins(runner)` helper
- Update `suite_runner.py` to use helper

**Phase 2: Test Enforcement (20 min)**
- Create `tests/test_plugin_registry.py` with `test_plugin_registry_complete()`
- Add test for accidental plugin rejection
- Add to CI as critical security test

**Phase 3: Documentation (15 min)**
- Update developer guide with "Adding New Plugin Type" workflow
- Document nominal typing requirement
- Update CERTIFICATION_EVIDENCE.md

**Migration Risk**: LOW (pre-1.0, no external plugins)

**See**: Appendix B for detailed checklist

### Implementation Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Developer ignores test failure | Low | High | Make test part of CI, cannot merge with failure |
| Registry falls out of sync | Low | High | Test catches this automatically |
| Performance of reflection in test | Low | Low | Test only runs once during suite, acceptable |
| False positive (non-plugin attribute ends with `_plugins`) | Medium | Low | Test can filter by type hints or manual exclusion list |

---

## Developer Workflow

### Adding a New Plugin Type

```python
# 1. Add to ExperimentRunner
class ExperimentRunner:
    preprocessing_plugins: list[PreprocessingPlugin] | None = None  # NEW

# 2. Add to registry (test will catch if forgotten)
PLUGIN_TYPE_REGISTRY = {
    "preprocessing_plugins": "PreprocessingPlugin",  # ← Add here
    # ...existing entries
}

# 3. Run tests
$ pytest tests/test_plugin_registry.py
# ✅ Passes if complete, ❌ fails with clear error if missing
```

**If Step 2 Forgotten**:
```
SECURITY: Plugin types {'preprocessing_plugins'} exist in ExperimentRunner
but are NOT registered in PLUGIN_TYPE_REGISTRY. This means they will bypass
ADR-002 security validation. Add them to core/base/plugin_types.py
```

---

## Compliance and Certification

**ADR-002 Impact**: Strengthens security guarantee by:
1. Ensuring ALL plugin types included in minimum clearance envelope
2. Preventing future bypass vulnerabilities
3. Making security validation auditable

**Certification Requirements**:
- [ ] Security review approval (new security control)
- [ ] Update CERTIFICATION_EVIDENCE.md with registry verification
- [ ] Add to THREAT_MODEL.md as defense for T1 (Classification Breach)

**Audit Trail**:
- Registry: `src/elspeth/core/base/plugin_types.py`
- Test: `tests/test_plugin_registry.py::test_plugin_registry_complete`
- Incident: Commit 46faef7 (Copilot P1 finding)

---

## References

- **ADR-002**: Suite-level security enforcement
- **ADR-004**: Mandatory BasePlugin inheritance (nominal typing)
- **Incident**: Copilot P1 finding (commit 46faef7) - Missing 4 plugin types
- **THREAT_MODEL.md**: T1 - Classification Breach prevention
- **CERTIFICATION_EVIDENCE.md**: Security Invariant I4
- **Python ABC**: https://docs.python.org/3/library/abc.html

---

## Decision Review

**Review Date**: TBD (6 months post-implementation)

**Success Criteria**:
- [ ] Zero incidents of plugin types bypassing validation
- [ ] Test catches all new plugin types
- [ ] Developer feedback positive (clear process)
- [ ] No security regressions

---

## Appendix A: Alternative Options Considered

### Option 1: Central Registry (Manual Only)

**Pros**: Simple, explicit, easy to audit
**Cons**: Still manual, no compile-time enforcement

### Option 2: Introspection with Naming Convention

**Pros**: Self-healing, zero maintenance
**Cons**: "Magic" behavior, could pick up unintended attributes

### Option 3: Protocol with Required Method

**Pros**: Explicit, type-checked
**Cons**: Invasive to ExperimentRunner, still manual enumeration

**Decision**: Option 4 (Hybrid) chosen for balance of explicitness and enforcement

---

## Appendix B: Hardening Implementation Details

### H1: MyPy Type Aliases

```python
# core/base/plugin_types.py
from typing import TypeAlias

RowPluginList: TypeAlias = list[BasePlugin]
AggregatorPluginList: TypeAlias = list[BasePlugin]

# ExperimentRunner
class ExperimentRunner:
    row_plugins: RowPluginList | None = None  # MyPy enforces BasePlugin
```

**Enforcement**: `mypy --strict` (already in CI)

---

### H2: Pre-Commit Hook

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
```

**Enforcement**: Cannot commit if registry incomplete

---

### H3: Auto-Generated Registry

```python
# core/base/plugin_types.py
from typing import get_type_hints

def _generate_registry() -> dict[str, str]:
    """Auto-generate registry from ExperimentRunner type hints."""
    hints = get_type_hints(ExperimentRunner)
    return {
        attr: _extract_type_name(hint)
        for attr, hint in hints.items()
        if attr.endswith('_plugins') or attr.endswith('_middlewares')
    }

PLUGIN_TYPE_REGISTRY = _generate_registry()  # Auto-generated!
```

**Enforcement**: Source of truth is type annotations (cannot forget)

---

### H4: Ruff Custom Lint Rule

```python
# .ruff_plugins/check_plugin_inheritance.py
def check_plugin_inheritance(node):
    """Lint: Classes in *_plugins must inherit BasePlugin."""
    if is_plugin_class(node) and not inherits_from(node, "BasePlugin"):
        raise LintError(
            f"Plugin {node.name} must inherit BasePlugin (ADR-003)"
        )
```

**Enforcement**: Ruff in CI (already present)

---

### Hardening Effort Summary

| Phase | Time | Cumulative |
|-------|------|------------|
| Core (3 layers) | 1.5-2h | 1.5-2h |
| H1: MyPy type aliases | 15 min | 2-2.25h |
| H2: Pre-commit hook | 10 min | 2-2.5h |
| H3: Auto-generation | 30 min | 2.5-3h |
| H4: Ruff lint rule | 45 min | 3-3.5h |

---

## Appendix C: Code Examples

### Before: Manual Enumeration (Fragile)

```python
# suite_runner.py (BEFORE - P1 vulnerability)
def _validate_experiment_security(self, runner, sinks):
    plugins = []

    datasource = self.datasource or getattr(runner, "datasource", None)
    if datasource and isinstance(datasource, BasePlugin):
        plugins.append(datasource)

    llm_client = getattr(runner, "llm_client", None)
    if llm_client and isinstance(llm_client, BasePlugin):
        plugins.append(llm_client)

    # ❌ FRAGILE: Easy to forget new plugin types
    # ❌ NO ENFORCEMENT
    # ❌ SILENT BYPASS
```

### After: Registry-Based (Robust)

```python
# core/base/plugin_types.py
PLUGIN_TYPE_REGISTRY = {
    "llm_client": {"type": "singleton", "protocol": "LLMClient"},  # ✓ Singleton handling
    "llm_middlewares": {"type": "list", "protocol": "LLMMiddleware"},
    "row_plugins": {"type": "list", "protocol": "RowExperimentPlugin"},
    "aggregator_plugins": {"type": "list", "protocol": "AggregationExperimentPlugin"},
    "validation_plugins": {"type": "list", "protocol": "ValidationPlugin"},
    "early_stop_plugins": {"type": "list", "protocol": "EarlyStopPlugin"},
}

def collect_all_plugins(runner) -> list[BasePlugin]:
    """Collect all plugins using registry (handles both singletons and lists)."""
    plugins = []
    for attr_name, config in PLUGIN_TYPE_REGISTRY.items():
        attr = getattr(runner, attr_name, None)
        if attr is None:
            continue

        if config["type"] == "singleton":
            if isinstance(attr, BasePlugin):
                plugins.append(attr)  # ✓ Singleton added
        elif config["type"] == "list":
            plugins.extend([p for p in attr if isinstance(p, BasePlugin)])

    return plugins

# suite_runner.py (AFTER)
from elspeth.core.base.plugin_types import collect_all_plugins

def _validate_experiment_security(self, runner, sinks):
    plugins = collect_all_plugins(runner)  # ✅ Registry ensures completeness

    # Datasource and sinks handled separately
    if self.datasource and isinstance(self.datasource, BasePlugin):
        plugins.append(self.datasource)
    for sink in sinks:
        if isinstance(sink, BasePlugin):
            plugins.append(sink)

    # Rest of validation...
```

### Layer 1 Example: Nominal Typing

```python
# ❌ REJECTED: No inheritance (accidental compliance)
class AccidentalHelper:
    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.UNOFFICIAL
    def validate_can_operate_at_level(self, level: SecurityLevel) -> None:
        pass

helper = AccidentalHelper()
isinstance(helper, BasePlugin)  # False - rejected ✅

# ✅ ACCEPTED: Explicit inheritance
class SecretPlugin(BasePlugin):
    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.SECRET
    def validate_can_operate_at_level(self, level: SecurityLevel) -> None:
        if level < SecurityLevel.SECRET:
            raise SecurityValidationError(...)

plugin = SecretPlugin()
isinstance(plugin, BasePlugin)  # True - accepted ✅
```

---

**Author**: Claude Code
**Approvers**: [Pending Security Team Review]
**Implementation**: [Pending ADR-004 approval]

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
