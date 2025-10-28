# Sprint 2 Prep Analysis: Automated Central Plugin Registry

**Date**: 2025-10-27
**Sprint**: Sprint 2 - ADR-003 Central Plugin Registry Implementation
**Status**: PREP COMPLETE - Ready to Start

---

## Executive Summary

Sprint 2 will implement ADR-003 Central Plugin Registry with **automated plugin discovery** to eliminate manual registration attack surface. Current pattern uses import-time side effects which can be bypassed. New design uses automatic module scanning to ensure ALL plugins go through central validation.

**Key Security Improvement**: Automated discovery prevents plugins from bypassing security validation by being loaded directly without registration.

---

## Critical Security Insight

**User Requirement**:
> "also please make sure the design for the central registery is automated rather than requiring manual registration - manual registration creates another attack surface"

**Attack Vector**: Manual registration allows:
1. **Forgotten Registration**: Developer loads plugin class directly without registering
2. **Import Bypass**: Plugin loaded via `from elspeth.plugins.X import Y` skips validation
3. **Side Effect Skip**: Import order issues could skip registration code
4. **Direct Instantiation**: `CSVDataSource(...)` bypasses security validation entirely

**Solution**: Automatic plugin discovery via module scanning ensures EVERY plugin goes through central registry validation.

---

## Current Registry Landscape

### Existing Registry Infrastructure

**BasePluginRegistry Framework** (`src/elspeth/core/registries/base.py`):
- Generic base class: `BasePluginRegistry[T]`
- Unified API: `.register()`, `.create()`, `.validate()`, `.list_plugins()`
- Security enforcement: `declared_security_level` (ADR-002-B)
- Schema validation: Pre-compiled JSON Schema validators
- Context handling: `PluginContext` propagation

**Specialized Registries** (all using `BasePluginRegistry[T]`):

1. **Core Node Registries** (`src/elspeth/core/registries/`):
   - `datasource_registry: BasePluginRegistry[DataSource]` (datasource.py:32)
   - `llm_registry: BasePluginRegistry[LLMClient]` (llm.py)
   - `sink_registry: BasePluginRegistry[Sink]` (sink.py)
   - `middleware_registry: BasePluginRegistry[Middleware]` (middleware.py)

2. **Experiment Plugin Registries** (`src/elspeth/core/experiments/experiment_registries.py`):
   - `row_plugin_registry: BasePluginRegistry[RowExperimentPlugin]`
   - `aggregation_plugin_registry: BasePluginRegistry[AggregationExperimentPlugin]`
   - `baseline_plugin_registry: BasePluginRegistry[BaselineComparisonPlugin]`
   - `validation_plugin_registry: BasePluginRegistry[ValidationPlugin]`
   - `early_stop_plugin_registry: BasePluginRegistry[EarlyStopPlugin]`

3. **Control Registries** (`src/elspeth/core/controls/`):
   - `rate_limiter_registry: BasePluginRegistry[RateLimiter]` (rate_limiter_registry.py)
   - `cost_tracker_registry: BasePluginRegistry[CostTracker]` (cost_tracker_registry.py)

**Total Registries**: 11 specialized registries (good - already using BasePluginRegistry!)

### Current Registration Pattern

**Example from datasource.py** (lines 170-189):
```python
# Module-level registration (import-time side effect)
datasource_registry.register(
    "azure_blob",
    _create_blob_datasource,
    schema=_BLOB_DATASOURCE_SCHEMA,
    declared_security_level="UNOFFICIAL",  # ADR-002-B
)

datasource_registry.register(
    "csv_blob",
    _create_csv_blob_datasource,
    schema=_CSV_BLOB_DATASOURCE_SCHEMA,
    declared_security_level="UNOFFICIAL",
)

datasource_registry.register(
    "local_csv",
    _create_csv_datasource,
    schema=_CSV_DATASOURCE_SCHEMA,
    declared_security_level="UNOFFICIAL",
)
```

**Problem**: If someone does `from elspeth.plugins.nodes.sources import CSVDataSource` and instantiates directly, they bypass registry validation.

---

## Automated Discovery Design

### Approach: Module Scanning with Entry Point Support

**Phase 2A (Sprint 2 - Core Implementation)**:
1. **Automatic Internal Plugin Discovery**
   - Scan `src/elspeth/plugins/` directory recursively
   - Import all Python modules (triggers existing registration side effects)
   - Validate all plugins are registered (security check)
   - Happens at framework initialization (single point of control)

2. **Validation Layer**
   - After auto-discovery, verify ALL expected plugins are registered
   - Fail fast if plugins missing (prevents bypasses)
   - Log discovered plugins for audit trail

**Phase 2B (Future - Post-1.0)**:
- Entry point support for external/third-party plugins
- Standard Python plugin pattern via `pyproject.toml`

### Implementation Pattern

```python
# src/elspeth/core/registry/auto_discover.py

def auto_discover_internal_plugins():
    """Automatically discover and import all internal plugins.

    SECURITY: This function ensures ALL internal plugins go through
    registration and validation. Bypassing this function is a security breach.

    Discovery process:
    1. Scan src/elspeth/plugins/ for all .py files
    2. Import each module (triggers registration side effects)
    3. Validate expected plugins are registered
    4. Log discovery for audit trail

    Raises:
        SecurityValidationError: If expected plugins are missing (bypass detected)
    """
    import os
    import importlib
    from pathlib import Path

    plugins_dir = Path(__file__).parent.parent.parent / "plugins"

    # Discover all plugin modules
    for root, dirs, files in os.walk(plugins_dir):
        # Skip __pycache__ and hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('_') and not d.startswith('.')]

        for file in files:
            if file.endswith('.py') and not file.startswith('_'):
                # Convert path to module name
                module_path = Path(root) / file
                relative_path = module_path.relative_to(plugins_dir.parent)
                module_name = str(relative_path.with_suffix('')).replace(os.sep, '.')

                # Import module (triggers registration side effects)
                try:
                    importlib.import_module(f"elspeth.{module_name}")
                except Exception as exc:
                    logger.warning(f"Failed to import plugin module {module_name}: {exc}")
                    # Continue - don't fail discovery for broken plugins

    # Validation happens in CentralPluginRegistry.__init__()
```

### CentralPluginRegistry Design

```python
# src/elspeth/core/registry/central.py

class CentralPluginRegistry:
    """Central registry for all plugin types with automated discovery.

    SECURITY: This is the single enforcement point for plugin validation.
    All plugins MUST be created via this registry to ensure security validation.

    Architecture:
    - Type-based namespacing (prevents name collisions)
    - Unified API across all plugin types
    - Automatic plugin discovery (prevents bypass)
    - Centralized security enforcement
    """

    def __init__(self, auto_discover: bool = True):
        """Initialize central registry.

        Args:
            auto_discover: If True, automatically discover internal plugins
        """
        self._registries: dict[str, BasePluginRegistry] = {}

        # Register existing registries
        self._register_core_registries()

        # Automatic discovery (SECURITY: ensures all plugins are registered)
        if auto_discover:
            from .auto_discover import auto_discover_internal_plugins
            auto_discover_internal_plugins()
            self._validate_discovery()

    def _register_core_registries(self):
        """Register all existing specialized registries."""
        from elspeth.core.registries import (
            datasource_registry,
            llm_registry,
            sink_registry,
            middleware_registry,
        )
        from elspeth.core.experiments.experiment_registries import (
            row_plugin_registry,
            aggregation_plugin_registry,
            baseline_plugin_registry,
            validation_plugin_registry,
            early_stop_plugin_registry,
        )
        from elspeth.core.controls.registry import (
            rate_limiter_registry,
            cost_tracker_registry,
        )

        # Register each specialized registry
        self._registries["datasource"] = datasource_registry
        self._registries["llm"] = llm_registry
        self._registries["sink"] = sink_registry
        self._registries["middleware"] = middleware_registry
        self._registries["row_plugin"] = row_plugin_registry
        self._registries["aggregation_plugin"] = aggregation_plugin_registry
        self._registries["baseline_plugin"] = baseline_plugin_registry
        self._registries["validation_plugin"] = validation_plugin_registry
        self._registries["early_stop_plugin"] = early_stop_plugin_registry
        self._registries["rate_limiter"] = rate_limiter_registry
        self._registries["cost_tracker"] = cost_tracker_registry

    def _validate_discovery(self):
        """Validate that expected plugins were discovered.

        SECURITY: This prevents bypasses where plugins are loaded but not registered.
        """
        # Define minimum expected plugins for each type
        expected = {
            "datasource": ["local_csv", "csv_blob", "azure_blob"],
            "llm": ["mock", "azure_openai"],
            "sink": ["csv", "json", "markdown"],
            # ... other expected plugins
        }

        for plugin_type, expected_names in expected.items():
            registry = self._registries.get(plugin_type)
            if not registry:
                raise SecurityValidationError(
                    f"Plugin type '{plugin_type}' not registered - discovery failure"
                )

            registered = set(registry.list_plugins())
            missing = set(expected_names) - registered

            if missing:
                raise SecurityValidationError(
                    f"Expected plugins missing from {plugin_type} registry: {missing}. "
                    "This indicates a registration bypass attempt or incomplete discovery."
                )

    def create(
        self,
        plugin_type: str,
        name: str,
        options: dict[str, Any],
        *,
        parent_context: PluginContext | None = None,
    ):
        """Create a plugin instance via the appropriate registry.

        SECURITY: This is the ONLY approved way to create plugins.
        Direct instantiation bypasses security validation.

        Args:
            plugin_type: Type category (e.g., "datasource", "llm", "sink")
            name: Plugin name within the type
            options: Plugin configuration
            parent_context: Optional parent context for inheritance

        Returns:
            Plugin instance with security validation applied

        Raises:
            ValueError: If plugin_type or name not registered
            SecurityValidationError: If security validation fails
        """
        registry = self._get_registry(plugin_type)
        return registry.create(name, options, parent_context=parent_context)

    def list(self, plugin_type: str) -> list[str]:
        """List all registered plugins of a given type."""
        registry = self._get_registry(plugin_type)
        return registry.list_plugins()

    def list_all(self) -> dict[str, list[str]]:
        """List all registered plugins across all types."""
        return {
            plugin_type: registry.list_plugins()
            for plugin_type, registry in self._registries.items()
        }

    def list_types(self) -> list[str]:
        """List all registered plugin types."""
        return sorted(self._registries.keys())

    def _get_registry(self, plugin_type: str) -> BasePluginRegistry:
        """Get registry for plugin type, raising if not found."""
        try:
            return self._registries[plugin_type]
        except KeyError as exc:
            raise ValueError(
                f"Unknown plugin type '{plugin_type}'. "
                f"Available types: {', '.join(sorted(self._registries.keys()))}"
            ) from exc

# Singleton instance (initialized once at framework startup)
registry = CentralPluginRegistry(auto_discover=True)
```

### Security Properties

**Automated Discovery Ensures**:
1. ✅ **No Bypass**: All plugins must be imported → triggers registration
2. ✅ **Single Enforcement Point**: `registry.create()` validates every plugin
3. ✅ **Fail Fast**: Missing plugins detected at startup (not runtime)
4. ✅ **Audit Trail**: Discovery logged for security monitoring
5. ✅ **Type Safety**: Generic `BasePluginRegistry[T]` enforces types

**Attack Mitigation**:
- ❌ **Direct Import Bypass**: Blocked - auto-discovery imports all plugins
- ❌ **Registration Skip**: Blocked - validation checks expected plugins
- ❌ **Import Order Attack**: Blocked - framework controls discovery order
- ❌ **Direct Instantiation**: Blocked - validation only happens via registry

---

## Migration Plan

### Phase 0: ADR-003 PLUGIN_TYPE_REGISTRY (1.5-2 hours)

**Goal**: Create registry of all plugin attributes in `ExperimentSuiteRunner`

**Deliverables**:
- `PLUGIN_TYPE_REGISTRY` dict in `src/elspeth/core/base/plugin_types.py`
- `collect_all_plugins(runner)` helper function
- Test enforcement (`test_plugin_registry_complete()`)

**Why First**: Establishes authoritative list of plugin types for validation

### Phase 1: Auto-Discovery Infrastructure (2-3 hours)

**Goal**: Implement automated plugin discovery

**Deliverables**:
- `src/elspeth/core/registry/auto_discover.py` with module scanning
- Discovery validation (ensures expected plugins registered)
- Audit logging for discovered plugins
- Unit tests for discovery logic

**Key Files**:
- Create: `src/elspeth/core/registry/auto_discover.py`
- Create: `src/elspeth/core/registry/__init__.py`

### Phase 2: CentralPluginRegistry Core (3-4 hours)

**Goal**: Create unified registry interface

**Deliverables**:
- `CentralPluginRegistry` class in `src/elspeth/core/registry/central.py`
- Methods: `create()`, `list()`, `list_all()`, `list_types()`
- Integration with existing `BasePluginRegistry` instances
- Singleton `registry` instance with auto-discovery

**Key Files**:
- Create: `src/elspeth/core/registry/central.py`
- Update: `src/elspeth/core/registry/__init__.py` (export `registry`)

### Phase 3: Framework Migration (4-5 hours + 2-3 hour buffer)

**Goal**: Update all framework imports to use central registry

**Deliverables**:
- Update `suite_runner.py`, `runner.py`, `orchestrator.py`
- Update all plugin creation code in core framework
- Fix all test imports (100+ files)
- Verify 1445 tests still pass

**Key Pattern**:
```python
# Before (scattered imports)
from elspeth.core.registries.datasource import datasource_registry
datasource = datasource_registry.create("local_csv", {...})

# After (central registry)
from elspeth.core.registry import registry
datasource = registry.create("datasource", "local_csv", {...})
```

**High-Risk Files** (update first):
- `src/elspeth/core/experiments/suite_runner.py`
- `src/elspeth/core/experiments/runner.py`
- `src/elspeth/core/orchestrator.py`
- `src/elspeth/core/settings.py`
- `src/elspeth/core/cli/*.py`

### Phase 4: Documentation (1-2 hours)

**Goal**: Document breaking changes and new patterns

**Deliverables**:
- Update `docs/architecture/component-diagram.md`
- Update `docs/development/plugin-authoring.md`
- Add `docs/architecture/automated-plugin-discovery.md`
- Update `CHANGELOG.md` with breaking changes
- Update `CLAUDE.md` with new import patterns

---

## Test Strategy

### Phase 0 Tests (PLUGIN_TYPE_REGISTRY)
- `test_plugin_registry_complete()`: Verify all runner attributes registered
- `test_collect_all_plugins_coverage()`: Verify helper collects all plugin types
- `test_plugin_registry_cardinality()`: Verify singleton vs list types

### Phase 1 Tests (Auto-Discovery)
- `test_auto_discover_finds_all_internal_plugins()`: Verify discovery completeness
- `test_auto_discover_validates_expected_plugins()`: Verify validation layer
- `test_auto_discover_logs_audit_trail()`: Verify audit logging
- `test_auto_discover_handles_broken_plugins()`: Verify graceful degradation
- `test_auto_discover_prevents_bypass()`: SECURITY TEST - verify bypass blocked

### Phase 2 Tests (CentralPluginRegistry)
- `test_central_registry_creates_plugins()`: Basic creation flow
- `test_central_registry_lists_plugins()`: Discovery API
- `test_central_registry_lists_all_types()`: Cross-type listing
- `test_central_registry_validates_security()`: Security enforcement
- `test_central_registry_rejects_unknown_type()`: Error handling
- `test_central_registry_rejects_unknown_name()`: Error handling

### Phase 3 Tests (Migration)
- `test_suite_runner_uses_central_registry()`: Integration test
- `test_orchestrator_uses_central_registry()`: Integration test
- ALL existing tests (1445 tests) must pass

### Security Tests (Critical)
- `test_direct_instantiation_warning()`: Document that direct instantiation bypasses validation
- `test_auto_discovery_prevents_missing_plugins()`: Verify discovery validation
- `test_central_registry_enforces_security_levels()`: Verify ADR-002 enforcement

---

## Risk Assessment

### High Risks

**Risk 1: Import Churn (100+ files)**
- **Impact**: Breaking changes across entire codebase
- **Mitigation**:
  1. Update in dependency order (core → experiments → tests)
  2. Run tests after each major subsystem
  3. Use `git bisect` if tests fail
- **Buffer**: +2-3 hours for comprehensive testing

**Risk 2: Circular Import Issues**
- **Impact**: Auto-discovery triggers circular imports
- **Mitigation**:
  1. Lazy imports in auto_discover.py
  2. Defer plugin validation to after discovery
  3. Test discovery in isolation
- **Contingency**: Make auto_discover optional (manual mode for debugging)

### Medium Risks

**Risk 3: Performance Regression**
- **Impact**: Auto-discovery adds startup time
- **Mitigation**:
  1. Discovery only happens once at framework init
  2. Cache discovered plugins
  3. Use lazy imports where possible
- **Acceptance**: <100ms startup overhead acceptable

**Risk 4: Third-Party Plugin Compatibility**
- **Impact**: External plugins won't be discovered
- **Mitigation**:
  1. Document entry point pattern for future (Phase 2B)
  2. Provide manual registration API for external plugins
  3. Pre-1.0 status means breaking changes acceptable
- **Future Work**: Entry point support in post-1.0

### Low Risks

**Risk 5: Test Suite Breakage**
- **Impact**: Tests import old registries directly
- **Mitigation**:
  1. Update test utilities first
  2. Fix test failures in batches
  3. Use pytest markers to run subsets
- **Rollback**: Clean revert if >50 test failures

---

## Acceptance Criteria

### Functional Requirements
- [ ] `CentralPluginRegistry` class implemented with auto-discovery
- [ ] All 11 registry types registered in central registry
- [ ] Automated plugin discovery scans `src/elspeth/plugins/`
- [ ] Discovery validation detects missing/bypassed plugins
- [ ] Unified API: `registry.create()`, `registry.list()`, `registry.list_all()`
- [ ] All framework code uses central registry
- [ ] Old scattered registry imports removed/deprecated

### Security Requirements
- [ ] Auto-discovery prevents registration bypass attacks
- [ ] Discovery validation fails fast for missing plugins
- [ ] Audit logging for plugin discovery
- [ ] `test_auto_discover_prevents_bypass()` passes
- [ ] Direct instantiation documented as security bypass

### Quality Requirements
- [ ] Test coverage ≥95% for central registry module
- [ ] All 1445 existing tests pass
- [ ] No new test failures introduced
- [ ] Performance: <100ms discovery overhead
- [ ] Documentation: Breaking changes in CHANGELOG.md

---

## Pre-Implementation Checklist

**Environment**:
- [x] Sprint 1 complete (1445 tests passing)
- [x] No uncommitted changes
- [x] Feature branch: `feature/adr-002-security-enforcement`
- [x] All Sprint 1 work committed

**Documentation Reviewed**:
- [x] ADR-003 specification
- [x] VULN-003 implementation guide
- [x] Existing registry architecture (BasePluginRegistry)
- [x] Current registration patterns

**Design Decisions Made**:
- [x] Auto-discovery via module scanning (Phase 2A)
- [x] Entry points deferred to post-1.0 (Phase 2B)
- [x] CentralPluginRegistry wraps existing registries
- [x] Breaking changes acceptable (pre-1.0)

**Ready to Start**: ✅ YES

---

## Next Steps

1. **Update TodoWrite** with Phase 0 tasks
2. **Create Phase 0 branch** from current feature branch
3. **Implement PLUGIN_TYPE_REGISTRY** (1.5-2 hours)
4. **Proceed to Phase 1** (auto-discovery infrastructure)

---

## References

- **ADR-003**: `docs/architecture/decisions/003-plugin-type-registry.md`
- **VULN-003**: `docs/implementation/VULN-003-central-plugin-registry.md`
- **BasePluginRegistry**: `src/elspeth/core/registries/base.py`
- **Sprint 1 Summary**: Git commit da7dfe4 "Refactor security level handling across tests and plugins (ADR-002-B)"
