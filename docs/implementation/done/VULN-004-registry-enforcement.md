# VULN-004: Registry-Level Security Enforcement Implementation

**Priority**: P2 (MEDIUM)
**Effort**: 13-18 hours (1-2 weeks)
**Sprint**: Sprint 3
**Status**: ✅ **COMPLETE** (October 27, 2025)
**Depends On**: None (works with existing BasePluginRegistry)
**Pre-1.0**: Breaking changes acceptable, no backwards compatibility required

**Implementation**: Three-layer defense-in-depth system deployed and tested (1500/1500 tests passing).
- Layer 1 (e8c1c80): Schema enforcement - 12 schemas with `additionalProperties: false`
- Layer 2 (e23aee3): Registry sanitization - Runtime rejection of security policy fields
- Layer 3 (6a92546, 3d18f10): Post-creation verification - Declared vs actual matching
- Bug Fix (a0297a5): HttpOpenAIClient security_level mismatch caught by Layer 3

**Outcome**: Configuration override attack vector eliminated. Security policy is now truly immutable per ADR-002-B.

---

## Vulnerability Description

### VULN-004: Configuration Override Attack Vector

**Finding**: Although ADR-002-B Phase 2 established that security policies are hard-coded in plugin code (not configurable via YAML), the registry system still accepts `security_level` in plugin option dictionaries during creation.

**Attack Scenario**:
```yaml
# Malicious configuration in experiment YAML
experiments:
  - name: malicious_test
    plugins:
      datasource:
        plugin: local_csv
        options:
          path: secret_data.csv
          security_level: "UNOFFICIAL"  # ⚠️ ATTEMPT TO DOWNGRADE
```

**Current Behavior**:
1. Registry calls factory function with `options` dict
2. Factory extracts `security_level` from options (if present)
3. Plugin is created with attacker-specified level
4. Hard-coded security level in plugin code is overridden

**Impact**:
- **Bypass Phase 2 immutability**: Attacker can override hard-coded security levels via configuration
- **Privilege escalation**: UNOFFICIAL clearance plugin could be upgraded to SECRET
- **Data exfiltration**: SECRET datasource downgraded to UNOFFICIAL, allowing UNOFFICIAL sinks to receive classified data
- **Audit trail corruption**: Logs show plugin's declared level, not actual operating level

**Status**: ADR-002-B Phase 2 incomplete - registry validation not implemented.

---

## Current State Analysis

### Existing Registry Validation

**What Exists**:
```python
# In BasePluginRegistry.register():
self._plugins[name] = PluginRegistration(
    factory=factory,
    schema=schema,
    declared_security_level=declared_security_level,  # Stored at registration
    # ...
)
```

**What's Missing**:
1. **No validation during creation** - Registry doesn't verify created plugin matches declared level
2. **No schema enforcement** - Schemas don't prohibit `security_level` in options
3. **No runtime comparison** - No check that `plugin.security_level == declared_security_level`

### Attack Surface Analysis

**Entry Point 1: YAML Configuration**
```yaml
# User-controlled configuration
datasource:
  plugin: local_csv
  options:
    path: data.csv
    security_level: "SECRET"  # Attacker-controlled
```

**Entry Point 2: Factory Functions**
```python
def _build_csv_datasource(options: dict[str, Any], context: PluginContext):
    # Factory receives options dict directly from YAML
    level = options.get("security_level", "UNOFFICIAL")  # ⚠️ VULNERABLE
    return LocalCSVDataSource(security_level=level, ...)
```

**Entry Point 3: Plugin Construction**
```python
# Old pre-Phase 2 pattern still accepted by some plugins
class VulnerablePlugin(BasePlugin):
    def __init__(self, *, security_level: SecurityLevel, ...):
        super().__init__(security_level=security_level)  # ⚠️ ACCEPTS PARAMETER
```

### Target Architecture (Secure)

**Registry Enforcement**:
```python
class BasePluginRegistry[T]:
    def create(self, name: str, options: dict[str, Any], parent_context) -> T:
        registration = self._plugins[name]

        # STEP 1: Strip security_level from options (reject override attempt)
        if "security_level" in options:
            raise SecurityValidationError(
                f"Configuration override attack blocked: "
                f"security_level cannot be specified in options for '{name}'. "
                f"Security policies are immutable and hard-coded per ADR-002-B."
            )

        # STEP 2: Create plugin via factory
        plugin = registration.factory(options, parent_context)

        # STEP 3: Verify declared level matches actual plugin code
        if isinstance(plugin, BasePlugin):
            if plugin.security_level != registration.declared_security_level:
                raise SecurityValidationError(
                    f"Security policy mismatch for plugin '{name}': "
                    f"declared={registration.declared_security_level}, "
                    f"actual={plugin.security_level}. "
                    f"This indicates plugin code was modified without updating registration."
                )

        return plugin
```

**Schema Enforcement**:
```python
# All plugin schemas MUST NOT include security_level property
DATASOURCE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        # security_level NOT ALLOWED
    },
    "additionalProperties": False,  # Strict - reject unknown keys
}
```

---

## Design Decisions

### 1. Three-Layer Defense Strategy

**Layer 1: Schema Validation (Preventive)**
- All plugin schemas set `"additionalProperties": false`
- Reject YAML containing `security_level` before plugin creation
- Early rejection provides clear error messages to users

**Layer 2: Options Sanitization (Detective)**
- Registry strips `security_level` from options dict before calling factory
- Logs warning if key present (potential attack attempt or misconfiguration)
- Ensures factory cannot receive attacker-controlled security level

**Layer 3: Post-Creation Verification (Corrective)**
- After plugin creation, compare `plugin.security_level` to `declared_security_level`
- Raise exception if mismatch (plugin code modified without updating registration)
- Catches bugs where plugin author forgot to hard-code security level

### 2. Error Message Strategy

**Clear Guidance for Users**:
```python
raise SecurityValidationError(
    f"Configuration error: 'security_level' cannot be specified in YAML for plugin '{name}'. "
    f"\n\nReason: Security policies are hard-coded in plugin code per ADR-002-B."
    f"\n\nDeclared security level for this plugin: {declared_security_level}"
    f"\n\nIf you need a plugin with a different security level, contact the plugin author "
    f"or create a new plugin with the required hard-coded security level."
)
```

**Benefits**:
- Explains WHY the error occurred (ADR-002-B immutability)
- Shows WHAT the plugin's declared level is
- Tells users HOW to fix (contact author or create new plugin)
- Distinguishes legitimate misconfiguration from attack attempts

### 3. Pre-1.0 Enforcement Strategy

**Breaking Change**: Schemas now reject `security_level` in options

**Pre-1.0 Approach**:
- ❌ NO feature flags or warn-only mode
- ❌ NO gradual migration period
- ✅ Direct enforcement (fail immediately on violation)
- ✅ Update all affected YAML files in same commit
- ✅ Breaking changes acceptable before 1.0 release

**Implementation**:
```python
# Direct enforcement - no feature flags
if "security_level" in options:
    raise SecurityValidationError(
        f"Configuration override attack blocked: "
        f"security_level cannot be specified in options for '{name}'. "
        f"Security policies are immutable and hard-coded per ADR-002-B."
    )
```

---

## Implementation Phases (TDD Approach)

### Phase 3.0: Schema Enforcement (3-4 hours)

**Deliverables**:
- [ ] Audit all plugin schemas in `src/elspeth/core/registries/`
- [ ] Set `"additionalProperties": false` on all schemas
- [ ] Add explicit `"properties"` definitions for all allowed keys
- [ ] Test that schemas reject `security_level` in options

**TDD Cycle**:
```python
# RED: Write failing test
def test_datasource_schema_rejects_security_level():
    from elspeth.core.registries.datasource import datasource_registry

    schema = datasource_registry.get_schema("local_csv")
    validator = jsonschema.Draft7Validator(schema)

    # Configuration with security_level should fail validation
    config = {
        "path": "data.csv",
        "security_level": "SECRET"  # Should be rejected
    }

    errors = list(validator.iter_errors(config))
    assert len(errors) > 0
    assert any("additionalProperties" in str(e) for e in errors)

# GREEN: Update schema
LOCAL_CSV_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        # security_level NOT in properties
    },
    "additionalProperties": False,  # Reject unknown keys
    "required": ["path"]
}

# REFACTOR: Apply pattern to all 30+ plugin schemas
```

**Test Coverage Target**: 100% (15-20 tests, one per plugin type)

### Phase 3.1: Registry Options Sanitization (2-3 hours)

**Deliverables**:
- [ ] Add `_sanitize_options()` method to `BasePluginRegistry`
- [ ] Strip `security_level` from options before factory call
- [ ] Log warning if key present (audit trail for attack attempts)
- [ ] Test that sanitization prevents factory from receiving key

**TDD Cycle**:
```python
# RED
def test_registry_strips_security_level_from_options():
    registry = datasource_registry

    # Attacker provides security_level in options
    malicious_options = {
        "path": "data.csv",
        "security_level": "SECRET"  # Should be stripped
    }

    with patch("elspeth.core.registries.base.logger") as mock_logger:
        plugin = registry.create("local_csv", malicious_options, context)

        # Verify warning logged
        mock_logger.warning.assert_called_once()
        assert "security_level" in mock_logger.warning.call_args[0][0]

        # Verify plugin has declared level, not attacker-specified
        assert plugin.security_level == "UNOFFICIAL"  # Declared level

# GREEN
class BasePluginRegistry[T]:
    def _sanitize_options(self, options: dict[str, Any], plugin_name: str) -> dict[str, Any]:
        """Remove security-sensitive keys from options dict."""
        sanitized = options.copy()

        if "security_level" in sanitized:
            logger.warning(
                f"Configuration override attempt blocked for plugin '{plugin_name}': "
                f"security_level removed from options (ADR-002-B enforcement)"
            )
            del sanitized["security_level"]

        return sanitized

    def create(self, name: str, options: dict[str, Any], parent_context) -> T:
        registration = self._plugins[name]
        sanitized_options = self._sanitize_options(options, name)
        return registration.factory(sanitized_options, parent_context)

# REFACTOR: Add audit logging with run_id, consider feature flag for strict mode
```

**Test Coverage Target**: 95% (10-15 tests)

### Phase 3.2: Post-Creation Verification (4-5 hours)

**Deliverables**:
- [ ] Add `_verify_security_level()` method to `BasePluginRegistry`
- [ ] Compare `plugin.security_level` to `declared_security_level` after creation
- [ ] Raise exception if mismatch detected
- [ ] Test verification catches plugins with incorrect hard-coded levels

**TDD Cycle**:
```python
# RED
def test_registry_detects_security_mismatch():
    # Register plugin with declared level UNOFFICIAL
    registry = BasePluginRegistry()

    def bad_factory(options, context):
        # Bug: Plugin hard-coded wrong level
        class BadPlugin(BasePlugin):
            def __init__(self):
                super().__init__(security_level="SECRET")  # Wrong!
        return BadPlugin()

    registry.register(
        "bad_plugin",
        bad_factory,
        declared_security_level="UNOFFICIAL"  # Mismatch
    )

    # Create should fail with clear error
    with pytest.raises(SecurityValidationError, match="security policy mismatch"):
        registry.create("bad_plugin", {}, context)

# GREEN
class BasePluginRegistry[T]:
    def _verify_security_level(self, plugin: T, registration: PluginRegistration) -> None:
        """Verify plugin's actual security level matches declared level."""
        if not isinstance(plugin, BasePlugin):
            return  # Only validate BasePlugin instances

        actual = plugin.security_level
        declared = registration.declared_security_level

        if actual != declared:
            raise SecurityValidationError(
                f"Security policy mismatch for plugin '{registration.name}': "
                f"declared={declared}, actual={actual}. "
                f"Plugin code must be updated to match declared level."
            )

    def create(self, name: str, options: dict[str, Any], parent_context) -> T:
        registration = self._plugins[name]
        sanitized_options = self._sanitize_options(options, name)
        plugin = registration.factory(sanitized_options, parent_context)
        self._verify_security_level(plugin, registration)
        return plugin

# REFACTOR: Add context to errors, improve error messages
```

**Test Coverage Target**: 95% (15-20 tests covering all mismatch scenarios)

### Phase 3.3: Schema Audit & Migration (3-4 hours)

**Deliverables**:
- [ ] Audit all plugin schemas for `additionalProperties: true` or missing property
- [ ] Update schemas to explicitly list allowed properties
- [ ] Set `additionalProperties: false` on all production schemas
- [ ] Create migration guide for custom plugin authors

**Files to Update** (30+ schemas):
- `src/elspeth/core/registries/datasource.py` (8 datasource schemas)
- `src/elspeth/core/registries/sink.py` (10 sink schemas)
- `src/elspeth/core/registries/llm.py` (3 LLM client schemas)
- `src/elspeth/core/registries/middleware.py` (5 middleware schemas)
- `src/elspeth/core/experiments/experiment_registries.py` (5 experiment plugin schemas)

**TDD Cycle**:
```python
# RED: Write schema audit test
def test_all_schemas_reject_security_level():
    """Verify NO plugin schema allows security_level in options."""
    from elspeth.core.registries import (
        datasource_registry,
        sink_registry,
        llm_registry,
        middleware_registry,
    )

    all_registries = [datasource_registry, sink_registry, llm_registry, middleware_registry]

    for registry in all_registries:
        for plugin_name in registry.list_plugins():
            schema = registry.get_schema(plugin_name)
            validator = jsonschema.Draft7Validator(schema)

            # Try to inject security_level
            test_config = {"security_level": "SECRET"}
            errors = list(validator.iter_errors(test_config))

            # Should fail validation
            assert len(errors) > 0, (
                f"Plugin '{plugin_name}' schema allows security_level in options! "
                f"This violates ADR-002-B."
            )

# GREEN: Update all schemas systematically
# (30+ schema updates, one per plugin type)

# REFACTOR: Add schema validation to pre-commit hook
```

**Test Coverage Target**: 100% (1 comprehensive audit test + 30+ per-plugin tests)

### Phase 3.4: Documentation & Breaking Change Notes (1-2 hours)

**Deliverables**:
- [ ] Update ADR-002-B with registry enforcement implementation
- [ ] Document breaking change in CHANGELOG
- [ ] Update plugin authoring guide with schema requirements
- [ ] Add pre-commit hook to prevent `security_level` in plugin options

**Breaking Change Documentation**:
1. **What Changed**: Schemas now reject `security_level` in options (immediate enforcement)
2. **Why**: ADR-002-B immutability enforcement
3. **Impact**: Configurations with `security_level` will fail immediately
4. **Migration Steps**: Remove `security_level` from all YAML files (done in same commit)
5. **Pre-1.0 Status**: Breaking changes acceptable, no backwards compatibility provided

---

## Test Strategy

### Unit Tests (25-30 tests)
- Schema validation rejects `security_level`
- Options sanitization strips forbidden keys
- Post-creation verification detects mismatches
- Error messages are clear and actionable

### Integration Tests (15-20 tests)
- End-to-end: YAML with `security_level` → rejected by schema
- End-to-end: Plugin created with mismatched level → rejected by registry
- End-to-end: Valid configuration → passes all validation layers
- Pre-1.0: All validation layers enforce immediately (no warn-only mode)

### Security Tests (10-15 tests)
- Attack scenario: Attacker adds `security_level: "UNOFFICIAL"` to SECRET datasource config → BLOCKED
- Attack scenario: Plugin code modified to accept security_level parameter → DETECTED by verification
- Attack scenario: Schema modified to allow `additionalProperties: true` → CAUGHT by audit test

---

## Risk Assessment

### Medium Risks

**Risk 1: Breaking Existing Configurations**
- **Impact**: YAML files with `security_level` in options will fail schema validation
- **Mitigation**: Update all affected YAML files in same commit, comprehensive grep before implementation
- **Rollback**: Clean revert of all changes

**Risk 2: Plugin Author Confusion**
- **Impact**: Custom plugin authors may not understand why `security_level` is forbidden in schemas
- **Mitigation**: Clear error messages, update plugin authoring documentation, pre-1.0 status means API changes expected
- **Rollback**: None needed (documentation clarification)

### Low Risks

**Risk 3: Performance Overhead**
- **Impact**: Post-creation verification adds isinstance() check + comparison per plugin
- **Mitigation**: Verification is O(1) operation, negligible overhead (<1ms)
- **Rollback**: None needed (overhead minimal)

**Risk 4: False Positives**
- **Impact**: Legitimate plugin code might trigger mismatch if declared_security_level not updated
- **Mitigation**: Comprehensive testing, clear error messages guide plugin author to fix
- **Rollback**: None needed (indicates real bug in plugin registration)

---

## Acceptance Criteria

### Functional
- [ ] All plugin schemas set `"additionalProperties": false`
- [ ] Registry strips `security_level` from options before factory call
- [ ] Registry verifies `plugin.security_level == declared_security_level` after creation
- [ ] Clear error messages guide users to fix configuration issues

### Security
- [ ] YAML with `security_level` in options → rejected by schema validation
- [ ] Options with `security_level` → stripped and logged as potential attack
- [ ] Plugin with mismatched level → rejected by post-creation verification
- [ ] All three layers (schema, sanitization, verification) tested independently

### Quality
- [ ] Test coverage ≥95% for registry enforcement module
- [ ] All existing tests pass (1445+ tests)
- [ ] No new failing tests introduced
- [ ] Breaking changes documented in CHANGELOG

---

## Migration Checklist

### Schema Updates (30+ files)

**Datasource Schemas**:
- [ ] `local_csv` - Set `additionalProperties: false`
- [ ] `csv_blob` - Set `additionalProperties: false`
- [ ] `dataframe_in_memory` - Set `additionalProperties: false`
- [ ] `noop` - Set `additionalProperties: false`
- [ ] [Plus Azure-specific datasources if enabled]

**Sink Schemas**:
- [ ] `csv_local` - Set `additionalProperties: false`
- [ ] `excel_local` - Set `additionalProperties: false`
- [ ] `json_local` - Set `additionalProperties: false`
- [ ] `markdown_local` - Set `additionalProperties: false`
- [ ] `visual_report_local` - Set `additionalProperties: false`
- [ ] `enhanced_visual_report` - Set `additionalProperties: false`
- [ ] `signed_bundle` - Set `additionalProperties: false`
- [ ] `local_bundle` - Set `additionalProperties: false`
- [ ] `repository` - Set `additionalProperties: false`
- [ ] [Plus Azure-specific sinks if enabled]

**LLM Client Schemas**:
- [ ] `azure_openai` - Set `additionalProperties: false`
- [ ] `openai_http` - Set `additionalProperties: false`
- [ ] `mock_llm` - Set `additionalProperties: false`

**Middleware Schemas**:
- [ ] `prompt_shield` - Set `additionalProperties: false`
- [ ] `azure_content_safety` - Set `additionalProperties: false`
- [ ] `pii_sanitizer` - Set `additionalProperties: false`
- [ ] `health_monitor` - Set `additionalProperties: false`
- [ ] `cost_tracker` - Set `additionalProperties: false`

**Experiment Plugin Schemas**:
- [ ] All row plugin schemas
- [ ] All aggregation plugin schemas
- [ ] All baseline plugin schemas
- [ ] All validation plugin schemas
- [ ] All early-stop plugin schemas

### Registry Code Updates

**High Priority**:
- [ ] `src/elspeth/core/registries/base.py` - Add `_sanitize_options()`, `_verify_security_level()`
- [ ] `src/elspeth/core/registries/datasource.py` - Enable strict validation
- [ ] `src/elspeth/core/registries/sink.py` - Enable strict validation

**Medium Priority**:
- [ ] `src/elspeth/core/registries/llm.py` - Enable strict validation
- [ ] `src/elspeth/core/registries/middleware.py` - Enable strict validation
- [ ] `src/elspeth/core/experiments/experiment_registries.py` - Enable strict validation for all 5 sub-registries

### Configuration File Audit

**Search for Violations**:
```bash
# Find all YAML files with security_level in plugin options
grep -r "security_level:" config/ tests/ --include="*.yaml"
```

**Update Affected Files**:
- [ ] Remove `security_level` from datasource options
- [ ] Remove `security_level` from sink options
- [ ] Remove `security_level` from LLM client options
- [ ] Remove `security_level` from middleware options

---

## Rollback Plan

### If Registry Enforcement Causes Issues

**Clean Revert Only (Pre-1.0 Approach)**
```bash
# Revert Phase 3.4 (Documentation)
git revert HEAD

# Revert Phase 3.3 (Schema Audit)
git revert HEAD~1

# Revert Phase 3.2 (Post-Creation Verification)
git revert HEAD~2

# Revert Phase 3.1 (Options Sanitization)
git revert HEAD~3

# Revert Phase 3.0 (Schema Enforcement)
git revert HEAD~4

# Verify tests pass
pytest
```

**No Feature Flags**: Pre-1.0 status means clean revert only, no warn-only mode or gradual rollback

### If Verification Detects Legitimate Mismatches

**Update Plugin Registration** (if plugin code is correct):
```python
register_datasource_plugin(
    "local_csv",
    create_local_csv,
    declared_security_level="UNOFFICIAL",  # Update to match plugin code
)
```

**Fix Plugin Code** (if declared level is correct):
```python
class LocalCSVDataSource(BasePlugin, DataSource):
    def __init__(self, ...):
        super().__init__(
            security_level=SecurityLevel.UNOFFICIAL,  # Update to match declaration
            allow_downgrade=True
        )
```

---

## Next Steps After Completion

1. **Post-Implementation**: Monitor audit logs for blocked `security_level` attempts (indicates misconfiguration or attack attempts)
2. **Plugin Ecosystem**: Update plugin authoring guide for external developers
3. **Security Audit**: Final sign-off on ADR-002-B complete implementation
4. **IRAP Certification**: Submit updated security controls documentation

---

## Integration with Other Work

**Depends On**:
- None (works with existing BasePluginRegistry from Phase 2)

**Enables**:
- Complete ADR-002-B implementation (Phase 2 immutability + registry enforcement)
- Hardened security model with defense-in-depth (schema + sanitization + verification)
- Clear audit trail for configuration override attempts

**Related ADRs**:
- ADR-002: Multi-Level Security Enforcement
- ADR-002-B: Immutable Security Policies (Phase 2)
- ADR-003: Central Plugin Registry (prerequisite)
- ADR-005: Trusted Downgrade Operations
