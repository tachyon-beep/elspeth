# Sprint 3: VULN-004 Registry Enforcement Implementation Plan

**Status**: Design Complete - Ready for Implementation
**Date**: 2025-10-27
**Branch**: feature/adr-002-security-enforcement (continuing from Sprint 2)
**Approach**: Bottom-Up (Schema-First) - Conservative layer-by-layer implementation
**Estimated Effort**: 8-11 hours

---

## Executive Summary

This plan implements VULN-004 (Configuration Override Attack) defense using a three-layer strategy:

1. **Layer 1 (Schema Enforcement)**: Reject YAML containing security policy fields at validation time
2. **Layer 2 (Registry Sanitization)**: Fail-fast if options dict contains forbidden fields at runtime
3. **Layer 3 (Post-Creation Verification)**: Validate plugin instance matches declared security level

**Implementation Order**: Layer 1 → Layer 2 → Layer 3 (bottom-up, prevention-first)

**Risk Profile**: Conservative - Each layer builds on previous validation, clear commit points, easy rollback

---

## Background

### VULN-004: Configuration Override Attack

**Current Vulnerability**:
```yaml
# config/experiment.yaml (ATTACK VECTOR)
datasource:
  plugin: local_csv
  options:
    path: "data.csv"
    security_level: "SECRET"  # ⚠️ BYPASS ATTEMPT
```

**Impact**: User can override immutable security policy declared in plugin code, violating ADR-002-B principle that security levels are author-owned and hard-coded.

**Root Cause**: No enforcement at configuration, registry, or instantiation layers.

### ADR-002-B: Immutable Security Policy

> "Security policy fields (security_level, allow_downgrade, max_operating_level) are forbidden in configuration. These must be declared in plugin code and are immutable at runtime."

**Forbidden Fields**:
- `security_level` - Plugin's operational security level
- `allow_downgrade` - Whether plugin can downgrade data classification
- `max_operating_level` - Maximum security level plugin can handle

---

## Requirements Analysis (From User Feedback)

### Risk Tolerance: Conservative
- **Layer-by-layer implementation**: One layer per commit
- **Fix-on-fail discipline**: Immediate fixes when tests break
- **No backwards compatibility**: Pre-1.0 allows breaking changes
- **Direct enforcement**: No deprecation warnings, fail-fast immediately

### Enforcement Strategy: Fail-Fast
- **Layer 2 behavior**: Raise `SecurityValidationError` (not silent stripping)
- **Alignment with ADR-001**: Fail-closed security principle
- **Clear error messages**: Guide users to fix YAML configuration

---

## Design Overview

### Three-Layer Defense Strategy

```
┌─────────────────────────────────────────────────────────┐
│ Layer 1: Schema Enforcement (Prevention)                │
│ - additionalProperties: false in all plugin schemas     │
│ - Rejects forbidden fields at YAML parse time           │
│ - Earliest possible failure point                       │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ Layer 2: Registry Sanitization (Defense-in-Depth)       │
│ - _validate_no_security_override() in BasePluginRegistry│
│ - Checks options dict at instantiation time             │
│ - Raises SecurityValidationError immediately            │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ Layer 3: Post-Creation Verification (Validation)        │
│ - _verify_security_level() after plugin instantiation   │
│ - Compares declared vs actual security_level            │
│ - Catches plugin implementation errors                  │
└─────────────────────────────────────────────────────────┘
```

**Why Three Layers?**
- **Layer 1**: Catches honest mistakes in YAML (prevention)
- **Layer 2**: Catches programmatic injection attempts (runtime defense)
- **Layer 3**: Catches plugin implementation bugs (validation)

Each layer assumes previous layers might be bypassed → defense-in-depth.

---

## Implementation Phases

### Phase 3.0: Layer 1 - Schema Enforcement (3-4 hours)

#### Objective
Add `additionalProperties: false` to all plugin schemas to reject YAML containing forbidden fields.

#### Implementation

**Files to Modify** (12-15 schema definitions):
```python
# src/elspeth/plugins/nodes/sources/*.py
CSV_LOCAL_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        # ... other properties
    },
    "required": ["path"],
    "additionalProperties": False,  # ✅ ADD THIS
}
"""Schema for local CSV datasource.

SECURITY (ADR-002-B): Security policy fields (security_level, allow_downgrade,
max_operating_level) are forbidden in configuration. These are hard-coded in
plugin implementation and immutable.
"""
```

**Locations**:
- `src/elspeth/plugins/nodes/sources/*.py` (datasource schemas: csv_local, csv_blob, etc.)
- `src/elspeth/plugins/nodes/transforms/llm/*.py` (LLM schemas: openai, azure_openai, mock)
- `src/elspeth/plugins/nodes/sinks/*.py` (sink schemas: csv, excel, json, markdown, etc.)
- `src/elspeth/plugins/experiments/*/*.py` (experiment plugin schemas)

#### TDD Cycle

**RED - Write Failing Test**:
```python
# tests/test_vuln_004_layer1_schemas.py (NEW FILE)
import pytest
import jsonschema
from elspeth.plugins.nodes.sources._csv_base import CSV_LOCAL_SCHEMA

def test_csv_local_schema_rejects_security_level():
    """SECURITY: Ensure YAML cannot override security_level (VULN-004 Layer 1)."""
    invalid_config = {
        "path": "/data/test.csv",
        "security_level": "SECRET",  # ⚠️ Attack attempt
    }

    with pytest.raises(jsonschema.ValidationError, match="additionalProperties"):
        jsonschema.validate(invalid_config, CSV_LOCAL_SCHEMA)

@pytest.mark.parametrize("forbidden_field", [
    "security_level",
    "allow_downgrade",
    "max_operating_level",
])
def test_csv_local_schema_rejects_all_forbidden_fields(forbidden_field):
    """Verify all ADR-002-B forbidden fields are rejected."""
    invalid_config = {
        "path": "/data/test.csv",
        forbidden_field: "ANY_VALUE",
    }

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid_config, CSV_LOCAL_SCHEMA)
```

**GREEN - Implement Fix**:
```python
# Add additionalProperties: False to all 12+ plugin schemas
CSV_LOCAL_SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string"}},
    "required": ["path"],
    "additionalProperties": False,  # ✅ Fix
}
```

**REFACTOR - Add Documentation**:
```python
# Add security docstrings to all schemas
CSV_LOCAL_SCHEMA = {
    # ... schema definition ...
}
"""Schema for local CSV datasource.

SECURITY (ADR-002-B): Security policy fields are forbidden in configuration.
Security level is UNOFFICIAL (hard-coded in CsvLocalDataSource.__init__).
"""
```

#### YAML Migration

**Step 1: Discover Affected Files**
```bash
# Search for security_level in YAML files
grep -r "security_level:" config/ --include="*.yaml"
grep -r "allow_downgrade:" config/ --include="*.yaml"
grep -r "max_operating_level:" config/ --include="*.yaml"

# Expected: 0-3 matches (most YAML doesn't override security)
```

**Step 2: Fix Each Match**
```yaml
# BEFORE (INVALID after Layer 1)
datasource:
  plugin: local_csv
  options:
    path: data/test.csv
    security_level: "UNOFFICIAL"  # ⚠️ DELETE THIS

# AFTER (VALID)
datasource:
  plugin: local_csv
  options:
    path: data/test.csv
    # Security level declared in CsvLocalDataSource code (immutable)
```

**Step 3: Validate**
```bash
# Run tests to discover any YAML that breaks
python -m pytest tests/test_vuln_004_layer1_schemas.py -v

# Run full test suite
python -m pytest -v

# Expected: Some integration tests may fail if YAML contains security_level
# Fix immediately by removing forbidden fields from YAML
```

#### Exit Criteria
- [ ] All 12+ plugin schemas have `additionalProperties: false`
- [ ] Unit tests verify all schemas reject forbidden fields
- [ ] All YAML files cleaned (no forbidden fields)
- [ ] All tests passing (1480+ tests)
- [ ] MyPy clean, Ruff clean

#### Commit Plan

**Commit 1: Schema Enforcement**
```
Security: VULN-004 Layer 1 - Schema enforcement for immutable security policy

- Add `additionalProperties: false` to all 12 plugin schemas
- Prevents YAML from containing security_level, allow_downgrade, max_operating_level
- Add unit tests for all plugin schemas (tests/test_vuln_004_layer1_schemas.py)
- Add security docstrings to all schemas
- Tests: 1480 → 1492 passing (+12 schema validation tests)

Files modified:
- src/elspeth/plugins/nodes/sources/*.py (datasource schemas)
- src/elspeth/plugins/nodes/transforms/llm/*.py (LLM schemas)
- src/elspeth/plugins/nodes/sinks/*.py (sink schemas)
- src/elspeth/plugins/experiments/*/*.py (experiment schemas)
- tests/test_vuln_004_layer1_schemas.py (NEW)

ADR-002-B enforcement at schema layer.
```

**Commit 2: YAML Fixes (if needed)**
```
Security: VULN-004 - Remove security_level from YAML configurations

- Delete security_level overrides from experiment configurations
- Security policy is declared in plugin code (immutable per ADR-002-B)
- Fixes schema validation errors from Layer 1 enforcement

Files modified:
- config/sample_suite/experiments/*.yaml (0-3 files expected)
- tests/fixtures/*.yaml (if any)
```

---

### Phase 3.1: Layer 2 - Registry Sanitization (2-3 hours)

#### Objective
Add runtime check in `BasePluginRegistry.instantiate()` to reject options containing forbidden fields.

#### Implementation

**File to Modify**: `src/elspeth/core/registries/base.py`

**Changes**:
```python
class BasePluginRegistry(Generic[T], ABC):
    # EXISTING: ADR-002-B forbidden fields constant
    FORBIDDEN_CONFIG_FIELDS = frozenset({
        "security_level",
        "allow_downgrade",
        "max_operating_level",
    })

    def instantiate(self, name: str, config: dict, **kwargs) -> T:
        """Factory: Instantiate plugin with config validation.

        SECURITY (VULN-004): Three-layer defense against configuration override:
        - Layer 1: Schema validation (additionalProperties: false)
        - Layer 2: Runtime sanitization (this method)
        - Layer 3: Post-creation verification (after instantiation)
        """
        # LAYER 2: Runtime sanitization check (NEW)
        self._validate_no_security_override(name, config)  # ✅ ADD THIS

        # EXISTING: Schema validation
        if name in self._schemas:
            jsonschema.validate(config, self._schemas[name])

        # EXISTING: Type-safe instantiation
        plugin_class = self.get(name)
        return plugin_class(**config)

    def _validate_no_security_override(self, plugin_name: str, config: dict):
        """Ensure configuration doesn't attempt to override security policy.

        SECURITY (VULN-004 Layer 2): Defense-in-depth check even if schema
        validation passes (e.g., schema definition missing additionalProperties).
        Raises SecurityValidationError immediately on forbidden field detection.

        Args:
            plugin_name: Name of plugin being instantiated
            config: Configuration dict from YAML or programmatic creation

        Raises:
            SecurityValidationError: If config contains forbidden security policy fields
        """
        forbidden_present = self.FORBIDDEN_CONFIG_FIELDS & set(config.keys())

        if forbidden_present:
            raise SecurityValidationError(
                f"Configuration override attack blocked for plugin '{plugin_name}': "
                f"Attempted to set {forbidden_present} via options. "
                f"Security policy is immutable (ADR-002-B) and declared in plugin code. "
                f"Remove these fields from YAML configuration."
            )
```

#### TDD Cycle

**RED - Write Failing Test**:
```python
# tests/test_vuln_004_layer2_sanitization.py (NEW FILE)
import pytest
from elspeth.core.registries.datasource import datasource_registry
from elspeth.core.security.exceptions import SecurityValidationError

def test_registry_rejects_security_level_in_options():
    """SECURITY: Registry must reject security_level in options (VULN-004 Layer 2)."""
    malicious_config = {
        "path": "/data/test.csv",
        "security_level": "SECRET",  # ⚠️ Attack
    }

    with pytest.raises(SecurityValidationError, match="Configuration override attack"):
        datasource_registry.instantiate("local_csv", malicious_config)

@pytest.mark.parametrize("forbidden_field", [
    "security_level",
    "allow_downgrade",
    "max_operating_level",
])
def test_registry_rejects_all_forbidden_fields(forbidden_field):
    """Verify all ADR-002-B forbidden fields are blocked by registry."""
    malicious_config = {
        "path": "/data/test.csv",
        forbidden_field: "ANY_VALUE",
    }

    with pytest.raises(SecurityValidationError, match="Configuration override attack"):
        datasource_registry.instantiate("local_csv", malicious_config)

def test_registry_sanitization_multiple_fields():
    """Verify error message lists ALL forbidden fields present."""
    malicious_config = {
        "path": "/data/test.csv",
        "security_level": "SECRET",
        "allow_downgrade": True,
        "max_operating_level": "TOP_SECRET",
    }

    with pytest.raises(SecurityValidationError) as exc_info:
        datasource_registry.instantiate("local_csv", malicious_config)

    # Error message should mention all forbidden fields
    error_msg = str(exc_info.value)
    assert "security_level" in error_msg
    assert "allow_downgrade" in error_msg
    assert "max_operating_level" in error_msg

def test_registry_allows_valid_options():
    """Verify legitimate options still work after Layer 2 enforcement."""
    valid_config = {"path": "/data/test.csv"}

    # Should NOT raise (datasource_registry is real registry, not mock)
    # This test validates Layer 2 doesn't break legitimate usage
    plugin = datasource_registry.instantiate("local_csv", valid_config)
    assert plugin.security_level == SecurityLevel.UNOFFICIAL  # Hard-coded in plugin
```

**GREEN - Implement Fix**:
```python
# Add _validate_no_security_override() to BasePluginRegistry
# (code shown above in Implementation section)
```

**REFACTOR - Improve Error Messages**:
```python
def _validate_no_security_override(self, plugin_name: str, config: dict):
    """Ensure configuration doesn't attempt to override security policy."""
    forbidden_present = self.FORBIDDEN_CONFIG_FIELDS & set(config.keys())

    if forbidden_present:
        # Improved error message with guidance
        raise SecurityValidationError(
            f"Configuration override attack blocked for plugin '{plugin_name}': "
            f"Attempted to set {sorted(forbidden_present)} via options.\n\n"
            f"Security policy is immutable (ADR-002-B) and must be declared in plugin code.\n"
            f"To fix: Remove {sorted(forbidden_present)} from YAML configuration.\n\n"
            f"Example:\n"
            f"  # INVALID:\n"
            f"  datasource:\n"
            f"    plugin: {plugin_name}\n"
            f"    options:\n"
            f"      security_level: SECRET  # ⚠️ REMOVE THIS\n\n"
            f"  # VALID:\n"
            f"  datasource:\n"
            f"    plugin: {plugin_name}\n"
            f"    options:\n"
            f"      # security_level declared in plugin code\n"
        )
```

#### Integration Testing

**Test Against All Registry Types**:
```python
@pytest.mark.parametrize("registry,plugin_name", [
    (datasource_registry, "local_csv"),
    (llm_registry, "openai"),
    (sink_registry, "csv"),
    # ... test all 12 registry types
])
def test_all_registries_enforce_layer2(registry, plugin_name):
    """Verify Layer 2 enforcement works across all registry types."""
    config = get_minimal_valid_config(plugin_name)
    config["security_level"] = "SECRET"

    with pytest.raises(SecurityValidationError):
        registry.instantiate(plugin_name, config)
```

#### Exit Criteria
- [ ] `_validate_no_security_override()` added to BasePluginRegistry
- [ ] Unit tests verify all forbidden fields blocked
- [ ] Integration tests verify all 12 registry types enforce Layer 2
- [ ] Error messages provide clear guidance
- [ ] All tests passing (1492+ tests)
- [ ] MyPy clean, Ruff clean

#### Commit Plan

**Commit 3: Registry Sanitization**
```
Security: VULN-004 Layer 2 - Registry-level sanitization

- Add _validate_no_security_override() to BasePluginRegistry.instantiate()
- Fail-fast with SecurityValidationError if forbidden fields present in options
- Defense-in-depth even if schema validation bypassed
- Improved error messages with YAML fix examples
- Tests: 1492 → 1497 passing (+5 sanitization tests)

Files modified:
- src/elspeth/core/registries/base.py
- tests/test_vuln_004_layer2_sanitization.py (NEW)

ADR-002-B enforcement at registry layer.
```

---

### Phase 3.2: Layer 3 - Post-Creation Verification (3-4 hours)

#### Objective
Validate that instantiated plugin's `security_level` matches the `declared_security_level` from registration.

#### Implementation

**File to Modify**: `src/elspeth/core/registries/base.py`

**Changes**:
```python
class BasePluginRegistry(Generic[T], ABC):
    def __init__(self):
        self._plugins: dict[str, type[T]] = {}
        self._schemas: dict[str, dict] = {}
        self._declared_levels: dict[str, SecurityLevel] = {}  # ✅ ADD THIS

    def register(
        self,
        name: str,
        plugin_class: type[T],
        schema: dict | None = None,
        security_level: SecurityLevel | None = None,
    ):
        """Register plugin with validation and security stamping.

        SECURITY (VULN-004 Layer 3): Store declared_security_level for
        post-creation verification.
        """
        # EXISTING: Schema validation
        if schema:
            self._validate_schema_security(name, schema)
            self._validate_schema(schema)
            self._schemas[name] = schema

        # EXISTING: Security level stamping
        if security_level:
            self._declared_levels[name] = security_level  # ✅ ADD THIS (track declaration)
            plugin_class._elspeth_security_level = security_level

        self._plugins[name] = plugin_class

    def instantiate(self, name: str, config: dict, **kwargs) -> T:
        """Factory: Instantiate plugin with config validation."""
        # Layer 2: Sanitization check
        self._validate_no_security_override(name, config)

        # Schema validation
        if name in self._schemas:
            jsonschema.validate(config, self._schemas[name])

        # Instantiation
        plugin_class = self.get(name)
        plugin_instance = plugin_class(**config)

        # LAYER 3: Post-creation verification (NEW)
        self._verify_security_level(name, plugin_instance)  # ✅ ADD THIS

        return plugin_instance

    def _verify_security_level(self, plugin_name: str, plugin_instance: T):
        """Verify plugin's security_level matches declared level.

        SECURITY (VULN-004 Layer 3): Final validation that plugin code
        correctly implements declared security policy. Catches:
        - Plugin implementation bugs (wrong level in __init__)
        - Runtime tampering (plugin modifies security_level after creation)
        - Class attribute modification (plugin changes _elspeth_security_level)

        Args:
            plugin_name: Name of plugin
            plugin_instance: Instantiated plugin object

        Raises:
            SecurityValidationError: If declared != actual security_level
        """
        # Only verify if plugin inherits BasePlugin
        if not isinstance(plugin_instance, BasePlugin):
            return

        # Skip if no declared level (plugin registered without security_level)
        declared = self._declared_levels.get(plugin_name)
        if declared is None:
            return

        # Get actual level from plugin instance
        actual = plugin_instance.security_level

        # Verify match
        if actual != declared:
            raise SecurityValidationError(
                f"Security policy mismatch for plugin '{plugin_name}':\n"
                f"  Declared: {declared} (at registration)\n"
                f"  Actual:   {actual} (from plugin instance)\n\n"
                f"This indicates plugin implementation does not match registration.\n"
                f"Fix plugin code to use correct security_level in __init__().\n\n"
                f"Example:\n"
                f"  class {plugin_instance.__class__.__name__}(BasePlugin):\n"
                f"      def __init__(self, **kwargs):\n"
                f"          super().__init__(security_level={declared})  # ✅ Match declaration\n"
            )
```

#### TDD Cycle

**RED - Write Failing Test**:
```python
# tests/test_vuln_004_layer3_verification.py (NEW FILE)
import pytest
from elspeth.core.base.plugin import BasePlugin
from elspeth.core.security.levels import SecurityLevel
from elspeth.core.security.exceptions import SecurityValidationError
from elspeth.core.registries.datasource import DataSourceRegistry

def test_registry_detects_security_level_mismatch():
    """SECURITY: Detect mismatch between declared and actual level (VULN-004 Layer 3)."""

    # Create test plugin that returns WRONG security level
    class MaliciousDataSource(BasePlugin):
        def __init__(self, path: str):
            # Declared UNOFFICIAL during registration, but actually SECRET
            super().__init__(security_level=SecurityLevel.SECRET)
            self.path = path

    # Register with UNOFFICIAL
    test_registry = DataSourceRegistry()
    test_registry.register(
        "malicious",
        MaliciousDataSource,
        schema={"type": "object", "properties": {"path": {"type": "string"}}},
        security_level=SecurityLevel.UNOFFICIAL,  # Declared
    )

    # Instantiate should fail verification
    with pytest.raises(SecurityValidationError, match="Security policy mismatch"):
        test_registry.instantiate("malicious", {"path": "/test.csv"})

@pytest.mark.parametrize("declared,actual", [
    (SecurityLevel.UNOFFICIAL, SecurityLevel.SECRET),      # Upgrade attack
    (SecurityLevel.SECRET, SecurityLevel.UNOFFICIAL),      # Downgrade attack
    (SecurityLevel.UNOFFICIAL, SecurityLevel.TOP_SECRET),  # Large gap
])
def test_registry_detects_bidirectional_mismatch(declared, actual):
    """Verify mismatches caught in both directions."""
    class MismatchedPlugin(BasePlugin):
        def __init__(self):
            super().__init__(security_level=actual)  # Use parameterized actual

    test_registry = DataSourceRegistry()
    test_registry.register(
        "mismatched",
        MismatchedPlugin,
        security_level=declared,  # Use parameterized declared
    )

    with pytest.raises(SecurityValidationError):
        test_registry.instantiate("mismatched", {})

def test_verification_accepts_matching_levels():
    """Verify plugins with correct security_level pass verification."""
    class CorrectPlugin(BasePlugin):
        def __init__(self):
            super().__init__(security_level=SecurityLevel.UNOFFICIAL)

    test_registry = DataSourceRegistry()
    test_registry.register(
        "correct",
        CorrectPlugin,
        security_level=SecurityLevel.UNOFFICIAL,  # Matches __init__
    )

    # Should NOT raise
    plugin = test_registry.instantiate("correct", {})
    assert plugin.security_level == SecurityLevel.UNOFFICIAL

def test_verification_skips_non_baseplugin():
    """Verify plugins not inheriting BasePlugin are skipped."""
    class NonSecurityPlugin:
        def __init__(self):
            pass  # No security_level

    test_registry = DataSourceRegistry()
    test_registry.register("nonsecurity", NonSecurityPlugin)

    # Should NOT raise (verification skipped for non-BasePlugin)
    plugin = test_registry.instantiate("nonsecurity", {})
    assert not hasattr(plugin, "security_level")

def test_verification_skips_undeclared_level():
    """Verify plugins registered without security_level are skipped."""
    class UndeclaredPlugin(BasePlugin):
        def __init__(self):
            super().__init__(security_level=SecurityLevel.UNOFFICIAL)

    test_registry = DataSourceRegistry()
    test_registry.register(
        "undeclared",
        UndeclaredPlugin,
        # No security_level parameter → None in _declared_levels
    )

    # Should NOT raise (no declared level to verify against)
    plugin = test_registry.instantiate("undeclared", {})
    assert plugin.security_level == SecurityLevel.UNOFFICIAL
```

**GREEN - Implement Fix**:
```python
# Add _declared_levels tracking and _verify_security_level()
# (code shown above in Implementation section)
```

**REFACTOR - Add Edge Case Handling**:
```python
def _verify_security_level(self, plugin_name: str, plugin_instance: T):
    """Verify plugin's security_level matches declared level."""
    # Edge case 1: Not a BasePlugin → skip
    if not isinstance(plugin_instance, BasePlugin):
        return

    # Edge case 2: No declared level → skip
    declared = self._declared_levels.get(plugin_name)
    if declared is None:
        return

    # Edge case 3: Plugin doesn't have security_level (shouldn't happen with BasePlugin)
    if not hasattr(plugin_instance, "security_level"):
        raise SecurityValidationError(
            f"Plugin '{plugin_name}' inherits BasePlugin but has no security_level attribute. "
            f"This should never happen - contact framework developers."
        )

    # Verify match
    actual = plugin_instance.security_level
    if actual != declared:
        raise SecurityValidationError(
            # ... detailed error message from Implementation section ...
        )
```

#### Integration Testing

**End-to-End VULN-004 Test**:
```python
def test_vuln_004_complete_three_layer_defense():
    """VULN-004: End-to-end test of all three layers working together."""

    # Setup: Register a plugin with declared security level
    test_registry = DataSourceRegistry()
    test_registry.register(
        "test_plugin",
        CsvLocalDataSource,
        CSV_LOCAL_SCHEMA,
        security_level=SecurityLevel.UNOFFICIAL,
    )

    # LAYER 1: Schema should reject security_level in config
    invalid_config_schema = {
        "path": "/test.csv",
        "security_level": "SECRET",
    }
    with pytest.raises(jsonschema.ValidationError, match="additionalProperties"):
        jsonschema.validate(invalid_config_schema, CSV_LOCAL_SCHEMA)

    # LAYER 2: Registry should reject (if schema bypassed somehow)
    invalid_config_runtime = {
        "path": "/test.csv",
        "security_level": "SECRET",
    }
    with pytest.raises(SecurityValidationError, match="Configuration override attack"):
        test_registry.instantiate("test_plugin", invalid_config_runtime)

    # LAYER 3: Verification should catch mismatch (if Layers 1-2 bypassed)
    class MaliciousPlugin(BasePlugin):
        def __init__(self, path: str):
            super().__init__(security_level=SecurityLevel.SECRET)  # Wrong!
            self.path = path

    test_registry.register(
        "malicious",
        MaliciousPlugin,
        security_level=SecurityLevel.UNOFFICIAL,  # Declared
    )

    with pytest.raises(SecurityValidationError, match="Security policy mismatch"):
        test_registry.instantiate("malicious", {"path": "/test.csv"})

    # VALID: Legitimate usage still works
    valid_config = {"path": "/test.csv"}
    plugin = test_registry.instantiate("test_plugin", valid_config)
    assert plugin.security_level == SecurityLevel.UNOFFICIAL
```

#### Exit Criteria
- [ ] `_declared_levels` dict added to BasePluginRegistry
- [ ] `_verify_security_level()` called after instantiation
- [ ] Unit tests verify all mismatch scenarios
- [ ] Edge cases handled (non-BasePlugin, undeclared level)
- [ ] Integration test validates all three layers
- [ ] All tests passing (1497+ tests)
- [ ] MyPy clean, Ruff clean

#### Commit Plan

**Commit 4: Layer 3 Part 1 - Tracking**
```
Security: VULN-004 Layer 3 - Track declared security levels

- Add _declared_levels dict to BasePluginRegistry.__init__()
- Store security_level at registration time for post-creation verification
- Preparation for Layer 3 verification (no behavior change yet)
- Tests: No new tests (internal refactoring)

Files modified:
- src/elspeth/core/registries/base.py
```

**Commit 5: Layer 3 Part 2 - Verification**
```
Security: VULN-004 Layer 3 - Post-creation verification

- Add _verify_security_level() to BasePluginRegistry.instantiate()
- Validate plugin.security_level == declared_security_level after instantiation
- Catches implementation errors and runtime attacks
- Handle edge cases (non-BasePlugin, undeclared level)
- Tests: 1497 → 1504 passing (+7 verification tests)

Files modified:
- src/elspeth/core/registries/base.py
- tests/test_vuln_004_layer3_verification.py (NEW)

ADR-002-B enforcement at instantiation layer.
VULN-004 THREE-LAYER DEFENSE COMPLETE.
```

---

### Phase 3.3: Documentation & Cleanup (3-5 hours)

#### Objective
Update all documentation to reflect VULN-004 completion and create ADR for defense-in-depth pattern.

#### Tasks

**1. Update Implementation Status** (30 min)
```markdown
# docs/implementation/VULN-004-registry-enforcement.md

**Status**: ✅ **COMPLETE** (Commits: XXX-YYY)
**Completed**: 2025-10-27
```

**2. Update Sprint Status** (30 min)
```markdown
# docs/implementation/README.md

| Sprint | Vulnerability | Status | Commit | Tests |
|--------|---------------|--------|--------|-------|
| Sprint 3 | VULN-004: Registry Enforcement | ✅ **COMPLETE** | XXX-YYY | 1504/1504 |
```

**3. Create ADR for Defense-in-Depth** (2-3 hours)
```markdown
# docs/architecture/decisions/ai/015-vuln-004-defense-in-depth.md

## Summary
Three-layer defense against configuration override attacks (VULN-004).

## Layers
1. Schema Enforcement - Prevention at YAML validation
2. Registry Sanitization - Runtime defense at instantiation
3. Post-Creation Verification - Validation after instantiation

## Implementation
- Layer 1: additionalProperties: false (12+ schemas)
- Layer 2: _validate_no_security_override() (BasePluginRegistry)
- Layer 3: _verify_security_level() (BasePluginRegistry)

## Test Coverage
- 24 new tests across 3 test files
- 100% coverage of defense layers
- End-to-end integration test
```

**4. Update CHANGELOG** (1 hour)
```markdown
# CHANGELOG.md

## [Unreleased]

### Security
- **BREAKING**: Schema validation now rejects `security_level`, `allow_downgrade`,
  and `max_operating_level` in YAML configuration (VULN-004 Layer 1)
- Added three-layer defense against configuration override attacks:
  - Layer 1: Schema enforcement (additionalProperties: false)
  - Layer 2: Registry sanitization (_validate_no_security_override)
  - Layer 3: Post-creation verification (_verify_security_level)
- Completed ADR-002-B immutable security policy enforcement
- Resolved VULN-004 from security audit

### Breaking Changes
- YAML configuration files can no longer specify `security_level`, `allow_downgrade`,
  or `max_operating_level` in plugin options. These are declared in plugin code and
  immutable (ADR-002-B). Remove these fields from YAML configurations.
```

**5. Update Plugin Authoring Guide** (1-2 hours)
```markdown
# docs/development/plugin-authoring.md

## Security Policy Declaration (ADR-002-B)

**CRITICAL**: Security policy is declared in plugin code and IMMUTABLE.

### Forbidden in YAML Configuration
- `security_level` - Plugin's operational security level
- `allow_downgrade` - Whether plugin can downgrade data
- `max_operating_level` - Maximum security level

### Correct Pattern
```python
# Plugin code (CORRECT)
class MyDataSource(BasePlugin):
    def __init__(self, path: str):
        super().__init__(
            security_level=SecurityLevel.UNOFFICIAL,  # ✅ Hard-coded
            allow_downgrade=False,
        )
        self.path = path

# YAML config (CORRECT)
datasource:
  plugin: my_datasource
  options:
    path: /data/file.csv
    # Security level declared in code, NOT here
```

### Three-Layer Enforcement (VULN-004)
1. **Schema validation**: Rejects YAML containing security policy fields
2. **Registry sanitization**: Blocks runtime injection attempts
3. **Post-creation verification**: Validates plugin matches declaration
```

#### Exit Criteria
- [ ] All documentation updated
- [ ] ADR-015 created
- [ ] CHANGELOG updated with breaking changes
- [ ] Plugin authoring guide updated
- [ ] All tests passing (1504 tests)

#### Commit Plan

**Commit 6: Documentation**
```
Docs: VULN-004 implementation complete

- Update docs/implementation/VULN-004-registry-enforcement.md (mark COMPLETE)
- Update docs/implementation/README.md (Sprint 3 complete)
- Add docs/architecture/decisions/ai/015-vuln-004-defense-in-depth.md (NEW)
- Update CHANGELOG.md with breaking changes
- Update docs/development/plugin-authoring.md with security policy guidance

Files modified:
- docs/implementation/VULN-004-registry-enforcement.md
- docs/implementation/README.md
- docs/architecture/decisions/ai/015-vuln-004-defense-in-depth.md (NEW)
- CHANGELOG.md
- docs/development/plugin-authoring.md

Sprint 3 COMPLETE - All security architecture tasks finished.
```

---

## Risk Assessment

### Medium Risks

**Risk 1: Test Failures from YAML Containing security_level**
- **Impact**: Integration tests may fail if YAML files contain forbidden fields
- **Likelihood**: Low (code audit suggests 0-3 files)
- **Mitigation**: Fix-on-fail - delete forbidden fields from YAML immediately
- **Rollback**: Revert Layer 1 commit, keep Layer 2 & 3

**Risk 2: Plugin Implementation Bugs**
- **Impact**: Layer 3 verification catches plugins with wrong security_level
- **Likelihood**: Low (all current plugins verified during Sprint 1)
- **Mitigation**: Fix plugin __init__ to use correct security_level
- **Rollback**: Revert Layer 3 commits

### Low Risks

**Risk 3: Performance Overhead**
- **Impact**: Three layers add validation overhead
- **Likelihood**: Low (all validations are dict lookups and conditionals)
- **Mitigation**: Negligible overhead (<1ms per plugin instantiation)
- **Rollback**: N/A (not a concern)

---

## Rollback Plan

Each layer is independently revertible:

```bash
# Revert Layer 3 (commits 4-5)
git revert HEAD HEAD~1

# Revert Layer 2 (commit 3)
git revert HEAD~2

# Revert Layer 1 (commits 1-2)
git revert HEAD~3 HEAD~4

# Full rollback (all of Sprint 3)
git revert HEAD~5..HEAD

# Verify tests pass after any revert
python -m pytest -v
```

**Feature Flags**: Not needed (pre-1.0 allows direct breaking changes)

---

## Success Criteria

### Functional
- [x] Design complete with three-layer strategy
- [ ] Layer 1: All schemas have `additionalProperties: false`
- [ ] Layer 2: Registry sanitization implemented in BasePluginRegistry
- [ ] Layer 3: Post-creation verification implemented
- [ ] All YAML files cleaned (no forbidden fields)
- [ ] 24+ new tests added (8 per layer)
- [ ] All tests passing (1480 → 1504+)

### Security
- [ ] VULN-004 resolved (configuration override attack closed)
- [ ] ADR-002-B fully enforced (immutable security policy)
- [ ] Defense-in-depth validated (all three layers tested)
- [ ] Attack surface documented (ADR-015)

### Quality
- [ ] Test coverage ≥95% for new code
- [ ] MyPy clean
- [ ] Ruff clean
- [ ] Documentation complete
- [ ] CHANGELOG updated

### Completion
- [ ] Sprint 3 marked COMPLETE in docs/implementation/README.md
- [ ] All 6 commits merged to feature/adr-002-security-enforcement
- [ ] Ready for final security audit and production deployment

---

## Timeline Estimate

| Phase | Duration | Commits |
|-------|----------|---------|
| Layer 1: Schema Enforcement | 3-4 hours | 1-2 |
| Layer 2: Registry Sanitization | 2-3 hours | 1 |
| Layer 3: Post-Creation Verification | 3-4 hours | 2 |
| Documentation & Cleanup | 3-5 hours | 1 |
| **Total** | **11-16 hours** | **5-6** |

**Recommended Schedule**: 2-3 days with 4-5 hour work sessions

---

## Next Steps After Sprint 3

1. **Security Audit Sign-Off**: Submit evidence of VULN-001/002/003/004 resolution
2. **IRAP Compliance Review**: Demonstrate Bell-LaPadula enforcement
3. **Production Readiness**: All security blockers cleared
4. **Sprint 4 (Optional)**: Class renaming for generic orchestration (FEAT-001)

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
