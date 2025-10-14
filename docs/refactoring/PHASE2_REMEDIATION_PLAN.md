# Phase 2 Registry Migration - Detailed Remediation Plan

**Date**: 2025-10-14
**Status**: Draft - Ready for Implementation
**Estimated Effort**: 12-16 hours (2 working days)
**Risk Level**: Low (all changes backward compatible)

---

## Executive Summary

This document provides a detailed, step-by-step remediation plan to complete Phase 2 of the registry consolidation migration. After deep analysis, the migration is **75% complete** with specific gaps identified and solutions designed.

### Current State Analysis

**Completed Migrations** (5 registries):
- ✅ Datasource registry → `datasource_registry.py` (**GOOD**)
- ✅ LLM registry → `llm_registry.py` (**GOOD**)
- ✅ Sink registry → `sink_registry.py` (**GOOD**)
- ⚠️ Controls registry → Split but manual context handling (**NEEDS IMPROVEMENT**)
- ⚠️ Experiments registry → Split but duplicated logic (**NEEDS IMPROVEMENT**)

**Incomplete Migrations** (2 registries):
- ❌ Utilities registry → Uses BasePluginRegistry but manual context (**NEEDS REFACTOR**)
- ❌ Middleware registry → Uses BasePluginRegistry but manual context (**NEEDS REFACTOR**)

**Test Encapsulation Issues**:
- ❌ **111 test lines** directly access `._datasources`, `._llms`, `._sinks`, `._plugins`
- ❌ 6 test files break encapsulation (test_config.py, test_config_suite.py, test_utilities_plugin_registry.py)

### Key Finding: "Controls Pattern" Is Intentional

After analysis, I discovered that the manual context creation in utilities, middleware, controls, and experiments registries is **not a bug—it's a deliberate design pattern**:

```python
# "Controls Pattern" - Manual context creation
def create_rate_limiter(definition, *, parent_context=None):
    # 1. Manual security level coalescing
    level = coalesce_security_level(definition_level, option_level)

    # 2. Manual context creation/derivation
    context = parent_context.derive(...) if parent_context else PluginContext(...)

    # 3. Use registry but pass pre-built context
    return rate_limiter_registry.create(
        name, payload,
        parent_context=context,  # ← Pre-built context
        require_security=False,  # ← Skip extraction
    )
```

**Why This Pattern Exists**:
1. **Optional plugins**: rate_limiter/cost_tracker can be None
2. **Inheritance without nesting**: experiment plugins inherit parent context without creating nested derivations
3. **Special coalescing logic**: controls need custom security resolution rules
4. **Backward compatibility**: existing tests depend on specific context structure

**The Real Problem**: This pattern is **duplicated 12+ times** across registries.

---

## Gap Analysis

### Gap 1: Utilities Registry - Manual Context Pattern

**File**: `src/elspeth/core/utilities/plugin_registry.py`
**Lines**: 140 (29-117 is manual context creation)
**Status**: ❌ Uses BasePluginRegistry but doesn't leverage `extract_security_levels`

**Code Smell**:
```python
# Lines 52-95: Manual security/determinism coalescing (44 lines)
entry_level = definition.get("security_level")
option_level = options.get("security_level")
parent_level = getattr(parent_context, "security_level", None)
# ... 40 more lines of manual logic
```

**Issue**: Duplicates logic from `context_utils.extract_security_levels()`

**Impact**: **Low** (only 1 utility plugin currently: `retrieval_context`)

---

### Gap 2: Middleware Registry - Manual Context Pattern

**File**: `src/elspeth/core/llm/registry.py`
**Lines**: 147 (31-94 is manual context creation)
**Status**: ❌ Uses BasePluginRegistry but duplicates coalescing logic

**Code Smell**:
```python
# Lines 53-90: Manual security coalescing and context creation (38 lines)
definition_level = definition.get("security_level")
option_level = options.get("security_level")
level = coalesce_security_level(definition_level, option_level)
# ... manual context creation ...
```

**Issue**: Identical pattern to utilities registry

**Impact**: **Medium** (8 middleware plugins: audit_logger, prompt_shield, azure_content_safety, etc.)

---

### Gap 3: Controls Registry - Pre-Built Context Workaround

**File**: `src/elspeth/core/controls/registry.py`
**Lines**: 305 (68-135 is create_rate_limiter, 137-203 is create_cost_tracker)
**Status**: ⚠️ Uses BasePluginRegistry but works around its API

**Code Smell**:
```python
# Lines 88-125: Manual coalescing then pass context to registry.create()
level = coalesce_security_level(definition_level, option_level)
context = parent_context.derive(...) if parent_context else PluginContext(...)
return rate_limiter_registry.create(
    name, payload,
    parent_context=context,  # Pre-built context
    require_security=False,  # Skip registry's extraction
)
```

**Why It Works This Way**:
- `create_rate_limiter()` returns `None` if definition is None (optional plugin)
- Can't use registry.create() directly because it would raise error on None

**Issue**: Creates context manually, then passes to registry which creates context again (but ignores it with `require_security=False`)

**Impact**: **Low** (works correctly, just inefficient)

---

### Gap 4: Experiment Plugins - 5x Duplication

**Files**:
- `src/elspeth/core/experiments/plugin_registry.py` (643 lines)

**Status**: ⚠️ Facade delegates to 5 registries, but each `create_*_plugin()` has duplicate logic

**Code Smell**: Manual coalescing logic repeated 5 times:
```python
# create_row_plugin (lines 108-172): 65 lines with manual context
# create_aggregation_plugin (lines 175-232): 58 lines with manual context
# create_baseline_plugin (lines 235-291): 57 lines with manual context
# create_validation_plugin (lines 294-350): 57 lines with manual context
# create_early_stop_plugin (lines 353-409): 57 lines with manual context
```

**Pattern** (all 5 functions):
```python
def create_row_plugin(definition, *, parent_context=None):
    name = definition.get("name")
    options = dict(definition.get("options", {}) or {})

    # Coalesce security level (10-15 lines)
    definition_level = definition.get("security_level")
    option_level = options.get("security_level")
    sources: list[str] = []
    # ... provenance tracking ...
    level = coalesce_security_level(definition_level, option_level)

    # Prepare payload (2-3 lines)
    payload = dict(options)
    payload.pop("security_level", None)

    # Create context manually (10-15 lines)
    if parent_context:
        context = parent_context.derive(...)
    else:
        context = PluginContext(...)

    # Instantiate via factory (2-3 lines)
    factory = row_plugin_registry._get_factory(name)
    return factory.instantiate(payload, plugin_context=context, ...)
```

**Issue**: This pattern is **copy-pasted 5 times** with only `plugin_kind` and registry name changing

**Impact**: **High** (294 lines of duplicate code across 5 functions)

---

### Gap 5: Test Encapsulation Violations

**Files**:
- `tests/test_config.py`: 48 lines accessing `._datasources`, `._llms`, `._sinks`
- `tests/test_config_suite.py`: 36 lines accessing internal dicts
- `tests/test_utilities_plugin_registry.py`: 2 lines accessing `._utility_plugins`

**Pattern**:
```python
# Backup original factories
orig_ds = registry_module.registry._datasources["azure_blob"]
orig_llm = registry_module.registry._llms["azure_openai"]

# Replace with mocks
registry_module.registry._datasources["azure_blob"] = registry_module.PluginFactory(...)

try:
    # Run test
    ...
finally:
    # Restore originals
    registry_module.registry._datasources["azure_blob"] = orig_ds
```

**Issue**: Tests depend on internal `_plugins` dict structure

**Why This Exists**: No public API for:
- Temporarily overriding plugin factories
- Clearing registries between tests
- Unregistering plugins

**Impact**: **High** - Prevents refactoring `BasePluginRegistry._plugins` structure

---

## Root Cause: Missing Helper Function

After analyzing all gaps, the root cause is clear:

**There is no shared helper function for the "controls pattern"**

All registries (utilities, middleware, controls, experiments) need:
1. Optional security/determinism levels (inherit from parent if not specified)
2. Manual provenance tracking
3. Context derivation or creation
4. Return None if definition is None (for optional plugins)

This logic is **copy-pasted 12+ times** because there's no abstraction for it.

---

## Remediation Strategy

### Option A: Extract "Controls Pattern" Helper (RECOMMENDED)

**Create**: `src/elspeth/core/registry/plugin_helpers.py`

**Add**:
```python
def create_plugin_with_inheritance(
    registry: BasePluginRegistry[T],
    definition: Dict[str, Any] | None,
    *,
    plugin_kind: str,
    parent_context: PluginContext | None = None,
    allow_none: bool = False,
) -> T | None:
    """
    Create plugin with inheritance pattern (used by controls, experiments, middleware).

    This helper consolidates the "controls pattern" used across multiple registries:
    1. Optional plugin support (return None if definition is None)
    2. Security/determinism level inheritance from parent
    3. Manual provenance tracking
    4. Context derivation or creation

    Args:
        registry: The registry to create from
        definition: Plugin definition dict
        plugin_kind: Plugin type for provenance (e.g., "rate_limiter", "row_plugin")
        parent_context: Optional parent context to inherit from
        allow_none: If True, return None when definition is None

    Returns:
        Plugin instance or None (if allow_none=True and definition is None)
    """
    if not definition:
        if allow_none:
            return None
        raise ValueError(f"{plugin_kind} definition cannot be empty")

    name = definition.get("name") or definition.get("plugin")
    if not name:
        raise ValueError(f"{plugin_kind} definition missing 'name' or 'plugin'")

    options = dict(definition.get("options", {}) or {})

    # Coalesce security level
    definition_level = definition.get("security_level")
    option_level = options.get("security_level")
    sources: list[str] = []
    if definition_level is not None:
        sources.append(f"{plugin_kind}:{name}.definition.security_level")
    if option_level is not None:
        sources.append(f"{plugin_kind}:{name}.options.security_level")

    try:
        level = coalesce_security_level(definition_level, option_level)
    except ValueError as exc:
        raise ConfigurationError(f"{plugin_kind}:{name}: {exc}") from exc

    # Handle determinism_level
    definition_det = definition.get("determinism_level")
    option_det = options.get("determinism_level")
    if definition_det is not None:
        sources.append(f"{plugin_kind}:{name}.definition.determinism_level")
    if option_det is not None:
        sources.append(f"{plugin_kind}:{name}.options.determinism_level")

    try:
        det_level = coalesce_determinism_level(definition_det, option_det)
    except ValueError as exc:
        raise ConfigurationError(f"{plugin_kind}:{name}: {exc}") from exc

    # Inherit from parent if not specified
    if level is None and parent_context:
        level = parent_context.security_level
    if det_level is None and parent_context:
        det_level = parent_context.determinism_level

    provenance = tuple(sources or (f"{plugin_kind}:{name}.resolved",))

    # Prepare payload
    payload = dict(options)
    payload.pop("security_level", None)
    payload.pop("determinism_level", None)

    # Create context manually
    if parent_context:
        context = parent_context.derive(
            plugin_name=name,
            plugin_kind=plugin_kind,
            security_level=level,
            determinism_level=det_level,
            provenance=provenance,
        )
    else:
        context = PluginContext(
            plugin_name=name,
            plugin_kind=plugin_kind,
            security_level=level,
            determinism_level=det_level,
            provenance=provenance,
        )

    # Use registry but pass pre-built context
    return registry.create(
        name,
        payload,
        parent_context=context,
        provenance=provenance,
        require_security=False,  # We've already built the context
        require_determinism=False,
    )
```

**Benefits**:
- Eliminates 300+ lines of duplicate code
- Single source of truth for "controls pattern"
- Easy to test and maintain
- Preserves exact behavior of all registries

**Effort**: 4 hours (implement + test)

---

### Option B: Add Registry Helper Methods (Alternative)

**Modify**: `src/elspeth/core/registry/base.py`

**Add to BasePluginRegistry**:
```python
def create_with_inheritance(
    self,
    name: str,
    options: Dict[str, Any],
    *,
    parent_context: PluginContext | None = None,
    inherit_security: bool = True,
    inherit_determinism: bool = True,
) -> T:
    """Create plugin with optional inheritance from parent context."""
    # ... implementation similar to Option A ...
```

**Benefits**:
- Keeps logic in BasePluginRegistry
- More discoverable API

**Drawbacks**:
- Adds complexity to base class
- Less flexible for special cases

**Effort**: 6 hours (modify base class + update all registries + test)

---

## Recommended Approach: Hybrid Solution

**Combine Option A + Test API Improvements**

### Step 1: Add Test Helper Methods (2 hours)

**Modify**: `src/elspeth/core/registry/base.py`

```python
class BasePluginRegistry(Generic[T]):
    # ... existing code ...

    def unregister(self, name: str) -> None:
        """
        Unregister a plugin (for testing).

        Args:
            name: Plugin name to remove

        Raises:
            KeyError: If plugin not found
        """
        del self._plugins[name]

    def clear(self) -> None:
        """Clear all registered plugins (for testing)."""
        self._plugins.clear()

    def temporary_override(self, name: str, factory: Callable, *, schema: Mapping | None = None):
        """
        Context manager to temporarily override a plugin factory (for testing).

        Usage:
            with registry.temporary_override("csv", mock_factory):
                # Use mocked plugin
                plugin = registry.create("csv", {...})
            # Original factory restored
        """
        from contextlib import contextmanager

        @contextmanager
        def _override():
            original = self._plugins.get(name)
            self.register(name, factory, schema=schema)
            try:
                yield
            finally:
                if original is not None:
                    self._plugins[name] = original
                else:
                    self._plugins.pop(name, None)

        return _override()
```

**Benefits**:
- Tests can use public API instead of `._plugins` access
- Backward compatible (old code still works)
- Enables future refactoring of `_plugins` structure

---

### Step 2: Extract "Controls Pattern" Helper (4 hours)

**Create**: `src/elspeth/core/registry/plugin_helpers.py` (see Option A above)

**Add tests**: `tests/test_registry_plugin_helpers.py`

```python
def test_create_plugin_with_inheritance_basic():
    """Helper creates plugin with manual context."""

def test_create_plugin_with_inheritance_none():
    """Helper returns None when allow_none=True."""

def test_create_plugin_with_inheritance_parent():
    """Helper inherits security level from parent."""

def test_create_plugin_with_inheritance_provenance():
    """Helper tracks provenance correctly."""
```

---

### Step 3: Refactor Registries (4-6 hours)

**Order** (easiest to hardest):

#### 3.1: Middleware Registry (1 hour)

**File**: `src/elspeth/core/llm/registry.py`

**Before** (94 lines):
```python
def create_middleware(definition, *, parent_context=None, provenance=None):
    # 60 lines of manual logic
    ...
```

**After** (10 lines):
```python
def create_middleware(definition, *, parent_context=None, provenance=None):
    from elspeth.core.registry.plugin_helpers import create_plugin_with_inheritance

    return create_plugin_with_inheritance(
        _middleware_registry,
        definition,
        plugin_kind="llm_middleware",
        parent_context=parent_context,
        allow_none=False,
    )
```

**Savings**: 84 lines removed

---

#### 3.2: Utilities Registry (1 hour)

**File**: `src/elspeth/core/utilities/plugin_registry.py`

**Before** (117 lines):
```python
def create_utility_plugin(definition, *, parent_context=None, provenance=None):
    # 88 lines of manual logic
    ...
```

**After** (10 lines):
```python
def create_utility_plugin(definition, *, parent_context=None, provenance=None):
    from elspeth.core.registry.plugin_helpers import create_plugin_with_inheritance

    return create_plugin_with_inheritance(
        _utility_registry,
        definition,
        plugin_kind="utility",
        parent_context=parent_context,
        allow_none=False,
    )
```

**Savings**: 107 lines removed

---

#### 3.3: Controls Registry (2 hours)

**File**: `src/elspeth/core/controls/registry.py`

**Before** (305 lines total):
- `create_rate_limiter()`: 68 lines
- `create_cost_tracker()`: 67 lines

**After** (each 10 lines):
```python
def create_rate_limiter(definition, *, parent_context=None, provenance=None):
    from elspeth.core.registry.plugin_helpers import create_plugin_with_inheritance

    return create_plugin_with_inheritance(
        rate_limiter_registry,
        definition,
        plugin_kind="rate_limiter",
        parent_context=parent_context,
        allow_none=True,  # ← Optional plugin
    )

def create_cost_tracker(definition, *, parent_context=None, provenance=None):
    from elspeth.core.registry.plugin_helpers import create_plugin_with_inheritance

    return create_plugin_with_inheritance(
        cost_tracker_registry,
        definition,
        plugin_kind="cost_tracker",
        parent_context=parent_context,
        allow_none=True,  # ← Optional plugin
    )
```

**Savings**: 125 lines removed

---

#### 3.4: Experiment Plugin Registry (2 hours)

**File**: `src/elspeth/core/experiments/plugin_registry.py`

**Before** (643 lines total):
- Each `create_*_plugin()`: ~60 lines × 5 = 300 lines

**After** (each ~10 lines):
```python
def create_row_plugin(definition, *, parent_context=None):
    from elspeth.core.registry.plugin_helpers import create_plugin_with_inheritance

    return create_plugin_with_inheritance(
        row_plugin_registry,
        definition,
        plugin_kind="row_plugin",
        parent_context=parent_context,
        allow_none=False,
    )

# Similarly for create_aggregation_plugin, create_baseline_plugin,
# create_validation_plugin, create_early_stop_plugin
```

**Savings**: 250 lines removed

---

### Step 4: Refactor Tests (2 hours)

**Goal**: Replace `._plugins` access with `temporary_override()`

**Files to update**:
- `tests/test_config.py` (48 lines)
- `tests/test_config_suite.py` (36 lines)
- `tests/test_utilities_plugin_registry.py` (2 lines)

**Before**:
```python
orig_ds = registry._datasources["azure_blob"]
registry._datasources["azure_blob"] = PluginFactory(...)
try:
    # test
finally:
    registry._datasources["azure_blob"] = orig_ds
```

**After**:
```python
with datasource_registry.temporary_override("azure_blob", mock_factory):
    # test
# Automatically restored
```

**Benefit**: Tests no longer depend on `_plugins` dict structure

---

## Implementation Timeline

### Day 1: Core Infrastructure (6 hours)

**Morning** (3 hours):
- ☐ Add test helper methods to BasePluginRegistry (unregister, clear, temporary_override)
- ☐ Write tests for test helpers
- ☐ Create plugin_helpers.py with create_plugin_with_inheritance()

**Afternoon** (3 hours):
- ☐ Write comprehensive tests for plugin_helpers.py
- ☐ Validate all tests pass (baseline)

### Day 2: Registry Refactoring (6 hours)

**Morning** (3 hours):
- ☐ Refactor middleware registry
- ☐ Refactor utilities registry
- ☐ Run full test suite after each (ensure no regressions)

**Afternoon** (3 hours):
- ☐ Refactor controls registry
- ☐ Refactor experiment plugin registry
- ☐ Run full test suite

### Day 3: Test Cleanup (2 hours) - Optional

**Morning** (2 hours):
- ☐ Refactor test_config.py to use temporary_override()
- ☐ Refactor test_config_suite.py to use temporary_override()
- ☐ Refactor test_utilities_plugin_registry.py

**Afternoon**: Buffer time / documentation

---

## Success Criteria

### Code Metrics

**Before**:
- Utilities registry: 140 lines
- Middleware registry: 147 lines
- Controls registry: 305 lines
- Experiments registry: 643 lines
- **Total**: 1,235 lines

**After**:
- plugin_helpers.py: +150 lines (new helper)
- Utilities registry: 50 lines (-90 lines)
- Middleware registry: 60 lines (-87 lines)
- Controls registry: 180 lines (-125 lines)
- Experiments registry: 393 lines (-250 lines)
- **Total**: 833 lines
- **Net reduction**: **-402 lines (-33%)**

### Test Coverage

- ☐ plugin_helpers.py: >95% coverage
- ☐ All existing tests pass (502 passed, 3 skipped)
- ☐ No new test skips or xfails
- ☐ Test encapsulation violations reduced from 111 lines to 0

### Functional Requirements

- ☐ Sample suite runs without changes
- ☐ All plugin types create correctly
- ☐ Context inheritance works as before
- ☐ Provenance tracking preserved
- ☐ Optional plugins (rate_limiter, cost_tracker) return None correctly
- ☐ Security level coalescing identical to before
- ☐ Determinism level handling identical to before

---

## Risk Assessment

### Low Risk Items ✅

1. **Adding test helpers**: Non-breaking addition
2. **Creating plugin_helpers.py**: New file, no dependencies
3. **Refactoring middleware/utilities**: Low usage (8 + 1 plugins)

### Medium Risk Items ⚠️

4. **Refactoring controls registry**: Used in orchestrator, suite_runner
5. **Refactoring experiments registry**: Used in runner (complex)

### Mitigation Strategies

**For Medium Risk Items**:
- Refactor one function at a time
- Run full test suite after each change
- Keep git commits small and atomic
- Add rollback tags: `git tag phase2-pre-controls` before risky changes

**Rollback Plan**:
```bash
# If controls refactor breaks
git revert phase2-controls-start..phase2-controls-end

# If experiments refactor breaks
git revert phase2-experiments-start..phase2-experiments-end
```

---

## Testing Strategy

### Unit Tests

**New tests** (plugin_helpers):
- ✅ Basic plugin creation
- ✅ Optional plugin (return None)
- ✅ Security level inheritance from parent
- ✅ Determinism level inheritance
- ✅ Provenance tracking
- ✅ Error handling (missing name, coalescing conflicts)

**Regression tests**:
- ✅ All existing registry tests pass unchanged
- ✅ All existing experiment tests pass
- ✅ All existing config tests pass

### Integration Tests

**Run**:
```bash
# Full suite
python -m pytest

# Sample suite
make sample-suite

# Specific integration tests
python -m pytest tests/test_suite_runner_integration.py
python -m pytest tests/test_cli_end_to_end.py
```

### Manual Verification

**Check**:
1. Create rate limiter with definition
2. Create rate limiter with None (returns None)
3. Create experiment plugins with parent context
4. Create middleware with custom security level
5. Create utility plugin with inheritance

---

## Documentation Updates

### Code Documentation

**Update**:
- ☐ plugin_helpers.py: Full module docstring with examples
- ☐ BasePluginRegistry: Document new test helper methods
- ☐ Each refactored registry: Update module docstring to reference plugin_helpers

### Architecture Documentation

**Update** (Phase 3):
- ☐ `docs/architecture/registry-architecture.md`: Document "controls pattern"
- ☐ `CLAUDE.md`: Update registry section with new helper
- ☐ `docs/refactoring/README.md`: Mark Phase 2 as complete

---

## Acceptance Checklist

### Phase 2 Complete When:

**Code Quality**:
- ☑ plugin_helpers.py implemented and tested
- ☑ All 4 registries refactored (utilities, middleware, controls, experiments)
- ☑ Net code reduction >300 lines
- ☑ No duplicate coalescing logic

**Testing**:
- ☑ All 502+ tests passing
- ☑ New plugin_helpers tests added
- ☑ Test encapsulation violations addressed
- ☑ Integration tests pass

**Functionality**:
- ☑ Sample suite runs successfully
- ☑ All plugin types create correctly
- ☑ Context inheritance preserved
- ☑ Optional plugin behavior unchanged

**Documentation**:
- ☑ Code comments updated
- ☑ Phase 2 completion report written
- ☑ MIGRATION_REVIEW.md updated with status

---

## Next Steps After Phase 2

### Immediate (Phase 3 Preparation):
1. Create PHASE2_COMPLETION.md documenting:
   - What was refactored
   - Code metrics (before/after)
   - Test results
   - Breaking changes (none expected)

2. Update refactoring README:
   - Mark Phase 2 as ✅ Complete
   - Update status table
   - Document new plugin_helpers.py

3. Tag commit:
   ```bash
   git tag -a phase2-complete -m "Phase 2: Registry consolidation complete"
   ```

### Future (Phase 3):
1. Remove backward compatibility hacks:
   - Remove `_datasources`, `_llms`, `_sinks` properties from PluginRegistry
   - Remove old PluginFactory compatibility check in BasePluginRegistry

2. Folder renaming:
   - `datasources/` → `adapters/` (if still desired)

3. Documentation:
   - Create comprehensive registry architecture guide
   - Update plugin development guide

---

## Conclusion

Phase 2 can be completed in **2 working days (12-16 hours)** with:
- **Low risk** (all changes backward compatible)
- **High impact** (400+ lines of duplicate code removed)
- **Clear benefits** (easier maintenance, consistent patterns)

The key insight is that the "controls pattern" is **intentional and correct**, not a bug—it just needs to be **extracted into a shared helper** to eliminate duplication.

**Recommended Start**: Implement plugin_helpers.py first, then refactor registries one at a time with full test runs between each.

---

**Plan Version**: 1.0
**Author**: Claude (Architectural Analysis)
**Review Status**: Ready for Implementation
**Next Review**: After Step 1 completion
