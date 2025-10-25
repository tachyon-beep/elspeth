# Phase 1.5: Registry Enforcement (OPTIONAL - Future Hardening)

**Objective**: Add registration-time checks to reject plugins without BasePlugin methods

**Estimated Effort**: 1-2 hours (OPTIONAL - can be deferred to post-merge)
**Priority**: P2 - Nice to have, not blocking

---

## Rationale

**Current approach (Phase 1-3)**:
- Plugins without BasePlugin methods fail at **runtime** when validation code calls methods
- Clear AttributeError with helpful message pointing to migration docs

**Enhanced approach (Phase 1.5)**:
- Plugins without BasePlugin methods fail at **registration time**
- Prevents bad plugins from ever being instantiated in production
- **Earlier detection** = better developer experience

---

## Implementation Strategy

### Option A: Protocol Validation in Registry

**File**: `src/elspeth/core/registries/base.py`

**Add validation to `BasePluginRegistry.register()` method**:

```python
from typing import Protocol, runtime_checkable
from elspeth.core.base.plugin import BasePlugin


class BasePluginRegistry(Generic[T]):
    """Base registry with BasePlugin enforcement."""

    def register(self, name: str, plugin_class: Type[T]) -> None:
        """Register a plugin class.

        Args:
            name: Plugin identifier
            plugin_class: Plugin class to register

        Raises:
            TypeError: If plugin_class doesn't implement BasePlugin protocol

        Example:
            >>> registry.register("csv", BaseCSVDataSource)  # ✅ Valid
            >>> registry.register("broken", BrokenPlugin)    # ❌ Raises TypeError
        """
        # VALIDATION: Check for BasePlugin protocol compliance
        if not self._implements_baseplugin(plugin_class):
            missing_methods = self._get_missing_baseplugin_methods(plugin_class)
            raise TypeError(
                f"Plugin class '{plugin_class.__name__}' cannot be registered: "
                f"missing required BasePlugin protocol methods: {missing_methods}. "
                f"All plugins MUST implement: get_security_level() and "
                f"validate_can_operate_at_level(operating_level). "
                f"See: docs/migration/adr-002-baseplugin-completion/README.md"
            )

        # Proceed with registration
        self._plugins[name] = plugin_class

    def _implements_baseplugin(self, plugin_class: Type[T]) -> bool:
        """Check if plugin class implements BasePlugin protocol.

        Args:
            plugin_class: Plugin class to check

        Returns:
            True if class has both required methods
        """
        required_methods = ["get_security_level", "validate_can_operate_at_level"]
        return all(hasattr(plugin_class, method) for method in required_methods)

    def _get_missing_baseplugin_methods(self, plugin_class: Type[T]) -> list[str]:
        """Get list of missing BasePlugin methods.

        Args:
            plugin_class: Plugin class to check

        Returns:
            List of missing method names
        """
        required_methods = ["get_security_level", "validate_can_operate_at_level"]
        return [
            method for method in required_methods
            if not hasattr(plugin_class, method)
        ]
```

---

### Option B: MyPy-Only Enforcement

**Pros**:
- Zero runtime overhead
- Catches issues during type checking (pre-commit)
- Simpler code (no runtime validation)

**Cons**:
- Only catches issues if MyPy run
- Doesn't help with dynamically-loaded plugins

**Implementation**: Already done! MyPy enforces protocol conformance.

---

## Testing

### Test: Registry Rejects Non-BasePlugin

```python
def test_registry_rejects_plugin_without_baseplugin():
    """Registry MUST reject plugins missing BasePlugin methods at registration."""
    from elspeth.core.registries.datasource_registry import DatasourceRegistry

    class BrokenDatasource:
        """Missing BasePlugin methods."""
        def __init__(self, path: str):
            self.path = path

        def load(self) -> pd.DataFrame:
            return pd.DataFrame({"col": [1]})

        # ❌ NO get_security_level()
        # ❌ NO validate_can_operate_at_level()

    registry = DatasourceRegistry()

    # MUST raise TypeError at registration
    with pytest.raises(TypeError) as exc_info:
        registry.register("broken", BrokenDatasource)

    # Error message MUST be helpful
    error_msg = str(exc_info.value)
    assert "BasePlugin" in error_msg
    assert "get_security_level" in error_msg
    assert "validate_can_operate_at_level" in error_msg
```

### Test: Registry Accepts Valid BasePlugin

```python
def test_registry_accepts_plugin_with_baseplugin():
    """Registry MUST accept plugins with BasePlugin methods."""
    from elspeth.core.registries.datasource_registry import DatasourceRegistry

    class ValidDatasource:
        """Complete BasePlugin implementation."""
        def __init__(self, path: str, security_level: SecurityLevel):
            self.path = path
            self.security_level = security_level

        def load(self) -> pd.DataFrame:
            return pd.DataFrame({"col": [1]})

        # ✅ BasePlugin methods
        def get_security_level(self) -> SecurityLevel:
            return self.security_level

        def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
            # Bell-LaPadula "no read up"
            if operating_level > self.security_level:
                raise SecurityValidationError("Insufficient clearance")

    registry = DatasourceRegistry()

    # MUST succeed
    registry.register("valid", ValidDatasource)
    assert "valid" in registry.list()
```

---

## Decision: Include Phase 1.5?

### ✅ Recommendation: DEFER to post-merge

**Rationale**:
1. **Phase 1-3 already provides fail-fast**: AttributeError at validation time
2. **MyPy already enforces protocol**: Type checking catches missing methods
3. **Adding registry checks = additional complexity**: More code to maintain
4. **Low ROI**: Most plugin development happens in-tree (MyPy catches issues)

**When to add Phase 1.5**:
- If you have **external plugin developers** (out-of-tree plugins)
- If you want **even earlier detection** (registration vs. validation time)
- If you observe **configuration bugs in production** (plugins without BasePlugin)

### Current Plan: Skip Phase 1.5 for initial merge

**What we have** (Phases 1-3):
- ✅ All 26 in-tree plugins implement BasePlugin
- ✅ MyPy enforces protocol conformance
- ✅ Runtime AttributeError if method missing (clear error message)
- ✅ Good enough for initial merge!

**Add later if needed**:
- ⭕ Phase 1.5 registry enforcement (1-2 hours)
- ⭕ Can be added in follow-up PR if external plugins become common

---

## Exit Criteria (if implementing)

- [ ] Registry validation code added to `BasePluginRegistry`
- [ ] Tests pass: `pytest tests/test_registry_enforcement.py -v`
- [ ] All existing registrations still work (no false positives)
- [ ] Clear error message if plugin missing methods
- [ ] MyPy clean
- [ ] Documentation updated

---

**Status**: OPTIONAL - Recommended to defer post-merge
**Next Phase**: [PHASE_2_VALIDATION_CLEANUP.md](./PHASE_2_VALIDATION_CLEANUP.md)
