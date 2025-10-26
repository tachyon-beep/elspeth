# VULN-003: Central Plugin Registry Implementation

**Priority**: P1 (HIGH)
**Effort**: 9.5-13 hours (1 week)
**Sprint**: Sprint 2
**Status**: NOT STARTED
**Depends On**: None (independent of other sprints)
**Pre-1.0**: Breaking changes acceptable, no backwards compatibility required

---

## Vulnerability Description

### VULN-003: ADR-003 Central Plugin Registry Not Implemented

**Finding**: Plugin registration is scattered across 15+ independent registry modules:
- `src/elspeth/core/registries/llm.py` (LLM clients)
- `src/elspeth/core/registries/datasource.py` (data sources)
- `src/elspeth/core/registries/sink.py` (result sinks)
- `src/elspeth/core/experiments/plugin_registry.py` (experiment plugins)
- `src/elspeth/core/experiments/experiment_registries.py` (5 sub-registries)
- Plus 8 more specialized registries

**Impact**:
- **Discovery**: No way to list all available plugins across types
- **Validation**: Each registry implements validation differently
- **Security**: No centralized enforcement point for security policies
- **Maintenance**: Changes require updating 15+ files
- **Testing**: Must mock 15+ registries instead of 1

**ADR-003 Requirement**:
> "All plugin types shall register through a single CentralPluginRegistry that provides unified discovery, validation, and lifecycle management."

**Status**: ADR-003 written but **never implemented**.

---

## Current State Analysis

### Existing Registry Landscape

```
Current (15+ scattered registries):

elspeth.core.registries.llm.llm_registry
elspeth.core.registries.datasource.datasource_registry
elspeth.core.registries.sink.sink_registry
elspeth.core.registries.middleware.middleware_registry
elspeth.core.experiments.experiment_registries:
  ├── row_plugin_registry
  ├── aggregation_plugin_registry
  ├── baseline_plugin_registry
  ├── validation_plugin_registry
  └── early_stop_plugin_registry
elspeth.core.controls.rate_limiter_registry
elspeth.core.controls.cost_tracker_registry
[+ 3 more specialized registries]
```

**Problems**:
1. Each registry has slightly different API
2. Security validation logic duplicated across registries
3. No unified plugin discovery mechanism
4. Testing requires mocking each registry separately
5. Schema validation inconsistent across types

### Target Architecture (ADR-003)

```
Target (unified registry):

elspeth.core.registry.CentralPluginRegistry
  ├── llm_plugins
  ├── datasource_plugins
  ├── sink_plugins
  ├── middleware_plugins
  ├── experiment_plugins
  │     ├── row_plugins
  │     ├── aggregation_plugins
  │     ├── baseline_plugins
  │     ├── validation_plugins
  │     └── early_stop_plugins
  ├── rate_limiter_plugins
  └── cost_tracker_plugins
```

**Benefits**:
1. Single import: `from elspeth.core.registry import registry`
2. Unified API: `registry.register()`, `registry.create()`, `registry.list()`
3. Centralized security enforcement
4. Easy to list ALL plugins: `registry.list_all()`
5. Single point for testing/mocking

---

## Design Decisions

### 1. Central Registry API

```python
from elspeth.core.registry import CentralPluginRegistry, registry

# Registration (plugin author)
registry.register(
    plugin_type="datasource",
    name="local_csv",
    factory=create_local_csv_datasource,
    schema=CSV_SCHEMA,
    declared_security_level="UNOFFICIAL",
    capabilities=frozenset(["streaming", "incremental"])
)

# Creation (framework user)
plugin = registry.create(
    plugin_type="datasource",
    name="local_csv",
    options={"path": "data.csv"},
    parent_context=context
)

# Discovery
all_datasources = registry.list("datasource")
all_plugins = registry.list_all()  # Returns dict[str, list[str]]

# Validation
registry.validate(
    plugin_type="datasource",
    name="local_csv",
    options={"path": "data.csv"}
)
```

**Key Features**:
- **Namespaced by type**: Avoid name collisions (e.g., "mock" LLM vs "mock" datasource)
- **Unified method names**: `register()`, `create()`, `list()`, `validate()`
- **Single import**: All plugins via `from elspeth.core.registry import registry`
- **Type-safe**: Validate `plugin_type` is known category

### 2. Registry Consolidation Pattern

**Phase 2.1: Create CentralPluginRegistry (3-4 hours)**
```python
# New unified registry
class CentralPluginRegistry:
    def __init__(self):
        self._registries: dict[str, BasePluginRegistry] = {}

    def register_type(self, plugin_type: str, registry: BasePluginRegistry):
        """Add a plugin type category."""
        self._registries[plugin_type] = registry

    def register(self, plugin_type: str, name: str, factory, **kwargs):
        """Register a plugin to the appropriate sub-registry."""
        self._registries[plugin_type].register(name, factory, **kwargs)

# Singleton instance
registry = CentralPluginRegistry()

# Register existing registries
registry.register_type("datasource", datasource_registry)
registry.register_type("llm", llm_registry)
registry.register_type("sink", sink_registry)
# ... etc for all 15 types
```

**Phase 2.2: Update Core Framework (4-5 hours) - Direct Cut-Over**
```python
# Before (scattered imports) - DELETE these files
from elspeth.core.registries.llm import llm_registry
from elspeth.core.registries.datasource import datasource_registry
from elspeth.core.registries.sink import sink_registry

llm = llm_registry.create("mock", {})
ds = datasource_registry.create("local_csv", {"path": "data.csv"})

# After (unified import) - UPDATE all imports in single commit
from elspeth.core.registry import registry

llm = registry.create("llm", "mock", {})
ds = registry.create("datasource", "local_csv", {"path": "data.csv"})
```

**Pre-1.0 Approach**:
- ❌ NO deprecation warnings
- ❌ NO backwards compatibility shims
- ✅ Delete old registry modules immediately
- ✅ Update ALL imports in one commit
- ✅ Fix all test failures in same commit

### 3. Security Integration

**Centralized Security Enforcement**:
```python
class CentralPluginRegistry:
    def create(self, plugin_type, name, options, parent_context=None):
        # Step 1: Create plugin via type-specific registry
        plugin = self._registries[plugin_type].create(name, options, parent_context)

        # Step 2: ALWAYS validate security (centralized enforcement)
        if isinstance(plugin, BasePlugin):
            # Verify declared_security_level matches plugin code
            declared = self._registries[plugin_type].get_declared_level(name)
            actual = plugin.security_level

            if declared != actual:
                raise SecurityValidationError(
                    f"Plugin '{plugin_type}:{name}' security mismatch: "
                    f"declared={declared}, actual={actual}"
                )

        return plugin
```

**Why This Helps**:
- Single enforcement point (not 15 separate checks)
- Impossible to bypass by using old registry imports
- Automatic validation for ALL plugin types

---

## Implementation Phases (TDD Approach)

### Phase 0: Design & Planning (30 min - 1 hour)

**Deliverables**:
- [ ] API specification document
- [ ] Migration checklist (all 15 registries)
- [ ] Pre-1.0 breaking change documentation in CHANGELOG

### Phase 1: ADR-003 Plugin Type Registry (1.5-2 hours) - SECURITY CRITICAL

**Deliverables**:
- [ ] `PLUGIN_TYPE_REGISTRY` dict in `src/elspeth/core/base/plugin_types.py`
- [ ] `collect_all_plugins(runner)` helper function
- [ ] Update `suite_runner.py` to use `collect_all_plugins()`
- [ ] Test enforcement (`test_plugin_registry_complete()`)

**TDD Cycle**:
```python
# RED
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
        "Will bypass ADR-002 validation."
    )

# GREEN
PLUGIN_TYPE_REGISTRY = {
    "llm_client": {"type": "singleton"},
    "llm_middlewares": {"type": "list"},
    "row_plugins": {"type": "list"},
    # ... etc
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

# REFACTOR: Add cardinality validation tests
```

**Test Coverage Target**: 100% (5-8 tests)

### Phase 2: CentralPluginRegistry Core (3-4 hours)

**Deliverables**:
- [ ] `CentralPluginRegistry` class in `src/elspeth/core/registry/central.py`
- [ ] `.register_type()`, `.register()`, `.create()` methods
- [ ] `.list()`, `.list_all()` discovery methods
- [ ] Singleton `registry` instance

**TDD Cycle**:
```python
# RED
def test_central_registry_registers_multiple_types():
    registry = CentralPluginRegistry()
    registry.register_type("datasource", datasource_registry)
    registry.register_type("llm", llm_registry)

    assert "datasource" in registry.list_types()
    assert "llm" in registry.list_types()

# GREEN
class CentralPluginRegistry:
    def __init__(self):
        self._registries = {}

    def register_type(self, plugin_type, registry):
        self._registries[plugin_type] = registry

    def list_types(self):
        return list(self._registries.keys())

# REFACTOR: Add validation, type hints, docstrings
```

**Test Coverage Target**: 100% (20-25 tests)

### Phase 3: Core Framework Migration (4-5 hours) - Direct Cut-Over

**Note**: Consider adding 2-3 hour buffer for comprehensive testing after mass import changes (100+ files).

**Deliverables**:
- [ ] Update all imports in `src/elspeth/core/` to use central registry
- [ ] Update orchestrator, runner, suite_runner
- [ ] Update plugin creation code throughout

**Files to Update** (partial list):
- `src/elspeth/core/orchestrator.py`
- `src/elspeth/core/experiments/runner.py`
- `src/elspeth/core/experiments/suite_runner.py`
- `src/elspeth/core/settings.py`
- `src/elspeth/core/cli/*.py`

**TDD Cycle**:
```python
# RED
def test_orchestrator_uses_central_registry():
    # Mock central registry
    with patch('elspeth.core.orchestrator.registry') as mock_registry:
        orchestrator = Orchestrator(...)
        orchestrator.run()

        # Verify central registry used (not old datasource_registry)
        mock_registry.create.assert_called_with("datasource", "local_csv", ...)

# GREEN
# In orchestrator.py:
from elspeth.core.registry import registry  # Not from .registries.datasource

datasource = registry.create("datasource", name, options)

# REFACTOR: Update all registry.create() calls consistently
```

**Test Coverage Target**: 90% (30-40 tests)

**Pre-1.0 Migration**:
- ❌ NO backwards compatibility testing
- ✅ Delete old registry modules in same commit
- ✅ Update ALL imports (100+ files) in single commit
- ✅ Fix test failures immediately

### Phase 4: Documentation & Test Updates (1-2 hours)

**Deliverables**:
- [ ] Update architecture docs (component diagram, registry documentation)
- [ ] Add API examples to documentation
- [ ] Document breaking change in CHANGELOG
- [ ] Update plugin authoring guide with new import patterns

---

## Test Strategy

### Unit Tests (35-45 tests)
- PLUGIN_TYPE_REGISTRY completeness
- collect_all_plugins() coverage
- CentralPluginRegistry registration
- Multi-type support
- Discovery (list, list_all)
- Security enforcement at central point

### Integration Tests (30-40 tests)
- End-to-end plugin creation through central registry
- suite_runner uses collect_all_plugins() for validation
- All existing tests pass after import updates

### Performance Tests (5-10 tests)
- Central registry lookup overhead (<1ms)
- Memory overhead of central registry (<5MB)
- No regression in plugin creation time

---

## Risk Assessment

### Medium Risks

**Risk 1: Import Churn**
- **Impact**: 100+ files import old registries, mass changes risky
- **Mitigation**: Update all imports in single commit with comprehensive test verification
- **Rollback**: Clean revert of entire commit

**Risk 2: Breaking Third-Party Plugins**
- **Impact**: External plugins using old registry APIs break
- **Mitigation**: Pre-1.0 status means API instability is expected
- **Rollback**: None (external authors track main branch at own risk)

### Low Risks

**Risk 3: Performance Regression**
- **Impact**: Extra indirection through central registry
- **Mitigation**: Performance tests, caching
- **Rollback**: None needed (overhead minimal)

---

## Acceptance Criteria

### Functional
- [ ] `CentralPluginRegistry` class implemented
- [ ] All 15 registry types registered
- [ ] Unified API (`register`, `create`, `list`)
- [ ] Discovery works (`list_all()` returns all plugins)
- [ ] Old registry modules deleted

### Security
- [ ] Central security enforcement for all plugin types
- [ ] Validation happens at single enforcement point
- [ ] VULN-003 resolved (security audit sign-off)

### Quality
- [ ] Test coverage ≥95% for central registry module
- [ ] All existing tests pass (1445+ tests)
- [ ] No new failing tests introduced
- [ ] Breaking changes documented in CHANGELOG

---

## Migration Checklist

### Registries to Consolidate (15 total)

**Core Registries**:
- [ ] `llm_registry` (LLM clients)
- [ ] `datasource_registry` (data sources)
- [ ] `sink_registry` (result sinks)
- [ ] `middleware_registry` (LLM middleware)

**Experiment Plugin Registries**:
- [ ] `row_plugin_registry`
- [ ] `aggregation_plugin_registry`
- [ ] `baseline_plugin_registry`
- [ ] `validation_plugin_registry`
- [ ] `early_stop_plugin_registry`

**Control Registries**:
- [ ] `rate_limiter_registry`
- [ ] `cost_tracker_registry`

**Specialized Registries**:
- [ ] [Additional registries as discovered]

### Core Framework Updates

**High Priority**:
- [ ] `src/elspeth/core/orchestrator.py`
- [ ] `src/elspeth/core/experiments/runner.py`
- [ ] `src/elspeth/core/experiments/suite_runner.py`

**Medium Priority**:
- [ ] `src/elspeth/core/settings.py`
- [ ] `src/elspeth/core/cli/*.py` (5 files)

**Low Priority**:
- [ ] Test files (gradual migration)
- [ ] Example scripts

---

## Rollback Plan

### If Central Registry Causes Issues

**Clean Revert Only (Pre-1.0 Approach)**
```bash
# Revert Phase 4 (Documentation)
git revert HEAD

# Revert Phase 3 (Migration)
git revert HEAD~1

# Revert Phase 2 (CentralPluginRegistry)
git revert HEAD~2

# Revert Phase 1 (ADR-003)
git revert HEAD~3

# Verify tests pass
pytest
```

**No Feature Flags**: Pre-1.0 status means clean revert only, no flag-based rollback

---

## Next Steps After Completion

1. **Sprint 3**: Implement registry-level enforcement (VULN-004)
2. **Performance Monitoring**: Track registry lookup times in production
3. **Documentation**: Update plugin authoring guide for external developers
