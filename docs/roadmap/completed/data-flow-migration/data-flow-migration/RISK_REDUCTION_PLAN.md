# Risk Reduction Plan: Data Flow Migration

**Date**: October 14, 2025
**Project**: Data Flow Architecture Migration
**Estimated Risk Reduction Time**: 8-12 hours (before 12-17 hour migration)

---

## Executive Summary

Before executing the data flow migration, we must reduce implementation risk through:
1. **Comprehensive testing baseline** - Ensure current system is fully characterized
2. **Silent default audit** - Find all security vulnerabilities before migration
3. **Dependency mapping** - Understand all import chains and coupling points
4. **Backward compatibility surface** - Identify what external code depends on
5. **Performance baseline** - Measure current behavior to detect regressions

**Goal**: De-risk migration by ensuring we can detect any breakage immediately and roll back safely.

---

## Critical Risks & Mitigations

### Risk 1: Breaking Existing Tests (HIGH)

**Risk**: Migration breaks existing functionality without tests catching it

**Indicators**:
- Current test coverage is 84% (good, but gaps exist)
- Some plugins have minimal test coverage
- Edge cases may not be tested
- Integration tests may be sparse

**Mitigation Activities**:
1. **Audit test coverage** (2-3 hours)
   - Run coverage report: `python -m pytest --cov=elspeth --cov-report=html --cov-report=term-missing`
   - Identify files <80% coverage
   - Identify critical paths with no coverage
   - Document coverage gaps

2. **Create characterization tests** (2-3 hours)
   - Test current registry behavior (all 18 registries)
   - Test current plugin creation patterns
   - Test configuration merge behavior
   - Test security level resolution
   - Document expected behavior (golden output tests)

3. **Create end-to-end smoke tests** (1-2 hours)
   - Test: Load datasource → LLM → sink (basic experiment)
   - Test: Configuration merge (defaults → pack → config)
   - Test: Security level enforcement
   - Test: Artifact pipeline dependency resolution
   - Test: Suite runner with multiple experiments

**Success Criteria**:
- [ ] Test coverage report generated and reviewed
- [ ] All critical paths have tests
- [ ] Characterization tests for all registries
- [ ] 5+ end-to-end smoke tests pass
- [ ] All 545 current tests pass

---

### Risk 2: Silent Default Security Holes (CRITICAL)

**Risk**: We miss silent defaults during migration, creating security vulnerabilities

**Indicators**:
- We found 2 silent defaults so far (P0 in `plugin_helpers.py`, module-level properties)
- Unknown how many more exist
- Silent defaults bypass security requirements

**Mitigation Activities**:
1. **Comprehensive silent default audit** (2-3 hours)
   ```bash
   # Search for .get() with defaults
   rg "\.get\(['\"][^'\"]+['\"],\s*[^)]" src/elspeth/ > silent_defaults_audit.txt

   # Search for "or" fallbacks
   rg "\|\|\s*['\"]" src/elspeth/ >> silent_defaults_audit.txt

   # Search for default parameter values in factory functions
   rg "def create_.*\(.*=.*\):" src/elspeth/ >> silent_defaults_audit.txt
   ```

2. **Categorize silent defaults** (1 hour)
   - **CRITICAL**: Security-related (security_level, authentication, validation)
   - **HIGH**: Configuration-related (models, endpoints, timeouts)
   - **MEDIUM**: Behavioral (retry counts, buffer sizes)
   - **LOW**: Cosmetic (display names, formatting)

3. **Create security default tests** (1-2 hours)
   - Test that all plugins fail without explicit security_level
   - Test that all plugins fail without required config
   - Test that schema validation catches missing fields
   - Document all current defaults for comparison

**Success Criteria**:
- [ ] Complete audit of silent defaults in codebase
- [ ] All CRITICAL and HIGH defaults documented
- [ ] Tests enforce explicit configuration
- [ ] Zero P0/P1 silent defaults remain

---

### Risk 3: Broken Import Chains (HIGH)

**Risk**: Moving files breaks import chains in unexpected places

**Indicators**:
- 18 registry files will be moved/consolidated
- Unknown external dependencies on current structure
- Tests import from current locations
- Configuration code may hard-code imports

**Mitigation Activities**:
1. **Map all registry imports** (1-2 hours)
   ```bash
   # Find all imports of registries
   rg "from elspeth\.core\.registry" src/ tests/ > registry_imports.txt
   rg "from elspeth\.core\.datasource_registry" src/ tests/ >> registry_imports.txt
   rg "from elspeth\.core\.llm_registry" src/ tests/ >> registry_imports.txt
   rg "from elspeth\.plugins\.llms" src/ tests/ >> registry_imports.txt
   rg "from elspeth\.plugins\.datasources" src/ tests/ >> registry_imports.txt
   rg "from elspeth\.plugins\.outputs" src/ tests/ >> registry_imports.txt
   rg "from elspeth\.plugins\.experiments" src/ tests/ >> registry_imports.txt
   ```

2. **Identify external API surface** (1 hour)
   - What do users import directly? (from docs, examples, config files)
   - What do tests import? (indicates API surface)
   - What's in `__all__` exports? (public API)
   - Document what MUST stay backward compatible

3. **Design backward compatibility shims** (1-2 hours)
   - Create shim modules at old locations
   - Re-export from new locations
   - Add deprecation warnings (but don't break)
   - Plan timeline for shim removal

**Success Criteria**:
- [ ] Complete map of all registry imports
- [ ] Identified external API surface
- [ ] Backward compatibility shim design complete
- [ ] Migration plan includes shim creation

---

### Risk 4: Configuration Schema Changes (MEDIUM)

**Risk**: Migration changes configuration structure, breaking existing configs

**Indicators**:
- Suite configs reference plugins by current names
- Prompt packs have existing structure
- Unknown how many external config files exist

**Mitigation Activities**:
1. **Audit existing configurations** (1 hour)
   ```bash
   # Find all YAML configs
   find . -name "*.yaml" -o -name "*.yml" | grep -v ".venv" > configs_inventory.txt

   # Check for plugin references
   rg "plugin:\s*" config/ tests/ >> plugin_references.txt
   ```

2. **Test configuration parsing** (1-2 hours)
   - Load all sample configs
   - Validate against current schemas
   - Document current config structure
   - Identify deprecation candidates

3. **Design configuration compatibility layer** (1 hour)
   - Support old plugin names (aliases)
   - Support old configuration keys
   - Add validation warnings for deprecated structure
   - Document migration path for configs

**Success Criteria**:
- [ ] All existing configs inventoried
- [ ] All sample configs parse successfully
- [ ] Configuration compatibility design complete
- [ ] Old config formats will still work post-migration

---

### Risk 5: Performance Regressions (MEDIUM)

**Risk**: Migration introduces performance degradation without detection

**Indicators**:
- No current performance baseline
- Registry lookups may change
- Plugin creation may be slower
- Unknown performance-critical paths

**Mitigation Activities**:
1. **Create performance baseline** (1-2 hours)
   ```bash
   # Run sample suite with timing
   time python -m elspeth.cli \
     --settings config/sample_suite/settings.yaml \
     --suite-root config/sample_suite \
     --reports-dir outputs/perf_baseline \
     --head 100

   # Profile registry lookups
   python -m cProfile -o registry_profile.prof -m elspeth.cli ...
   ```

2. **Identify performance-critical paths** (1 hour)
   - Registry lookups (called once per plugin creation)
   - Plugin creation (called per experiment)
   - Configuration merge (called per experiment)
   - Artifact pipeline resolution (called per suite)

3. **Create performance regression tests** (1-2 hours)
   - Time registry lookups (should be <1ms)
   - Time plugin creation (should be <10ms)
   - Time configuration merge (should be <50ms)
   - Time artifact pipeline (should be <100ms)
   - Document baseline metrics

**Success Criteria**:
- [ ] Performance baseline established
- [ ] Critical paths identified and timed
- [ ] Regression tests created
- [ ] Acceptable performance thresholds documented

---

### Risk 6: Incomplete Migration (MEDIUM)

**Risk**: Migration leaves system in half-migrated state

**Indicators**:
- 5 phases over 12-17 hours
- High chance of interruption
- Dependencies between phases
- Need to maintain working system throughout

**Mitigation Activities**:
1. **Design phase checkpoints** (1 hour)
   - Each phase must leave system in working state
   - All tests must pass after each phase
   - Each phase should be separately committable
   - Document rollback procedure for each phase

2. **Create migration checklist** (1 hour)
   - Detailed task list per phase
   - Success criteria per phase
   - Testing requirements per phase
   - Rollback procedure per phase

3. **Set up feature flags** (2-3 hours)
   - Environment variable to use old vs new registries
   - Gradual rollout capability
   - Ability to A/B test migration
   - Easy rollback without code changes

**Success Criteria**:
- [ ] Each phase has clear checkpoint
- [ ] Migration checklist created
- [ ] Feature flags implemented
- [ ] Rollback tested for each phase

---

## Pre-Migration Activities (Ordered by Priority)

### Week 1: Critical Risk Reduction (8-10 hours)

**Day 1-2**: Security & Testing Baseline
1. ✅ **Silent default audit** (2-3 hours) - CRITICAL
   - Find all silent defaults
   - Categorize by severity
   - Document CRITICAL/HIGH defaults
   - Create enforcement tests

2. ✅ **Test coverage audit** (2-3 hours) - HIGH
   - Generate coverage report
   - Identify gaps in critical paths
   - Create characterization tests for registries
   - Ensure all 545 tests pass

**Day 3**: Dependency Mapping
3. ✅ **Import chain mapping** (2-3 hours) - HIGH
   - Map all registry imports
   - Identify external API surface
   - Design backward compatibility shims
   - Document what must stay stable

**Day 4**: Performance & Configuration
4. ✅ **Performance baseline** (1-2 hours) - MEDIUM
   - Run perf baseline tests
   - Profile critical paths
   - Document acceptable thresholds

5. ✅ **Configuration audit** (1-2 hours) - MEDIUM
   - Inventory all configs
   - Test parsing
   - Design compatibility layer

### Week 2: Migration Execution (12-17 hours)

Only proceed to migration after ALL Week 1 activities complete successfully.

---

## Risk Reduction Checklist

### Before Starting Migration

**Security** (CRITICAL):
- [ ] Silent default audit complete
- [ ] All CRITICAL/HIGH defaults documented
- [ ] Security enforcement tests created
- [ ] Zero P0/P1 silent defaults remain

**Testing** (CRITICAL):
- [ ] Coverage report generated (target: >85%)
- [ ] All critical paths tested
- [ ] Characterization tests for all 18 registries
- [ ] 5+ end-to-end smoke tests created
- [ ] All 545 tests passing

**Dependencies** (HIGH):
- [ ] Import chain map complete
- [ ] External API surface identified
- [ ] Backward compatibility shims designed
- [ ] Migration includes shim creation

**Performance** (MEDIUM):
- [ ] Baseline metrics established
- [ ] Critical path timings documented
- [ ] Regression tests created
- [ ] Acceptable thresholds defined

**Configuration** (MEDIUM):
- [ ] All configs inventoried
- [ ] Sample configs tested
- [ ] Compatibility layer designed
- [ ] Old formats will still work

**Process** (MEDIUM):
- [ ] Phase checkpoints defined
- [ ] Migration checklist created
- [ ] Feature flags implemented (optional but recommended)
- [ ] Rollback procedures tested

### During Migration (After Each Phase)

- [ ] All tests pass (545 + new tests)
- [ ] Mypy: 0 errors
- [ ] Ruff: passing
- [ ] Performance metrics within thresholds
- [ ] Git commit with clear message
- [ ] Rollback tested and documented

---

## Rollback Procedures

### If Tests Fail During Phase
1. Review failure details
2. Determine if fixable in <30 minutes
3. If yes: fix and re-test
4. If no: `git reset --hard HEAD` and review plan

### If Performance Degrades
1. Compare to baseline metrics
2. Profile the regression
3. If >20% degradation: halt and investigate
4. If <20%: document and continue (fix later)

### If External Breakage Detected
1. Identify broken external usage
2. Determine if shim can fix
3. If yes: add shim and continue
4. If no: halt and redesign compatibility

### If Lost or Confused
1. `git status` - see what changed
2. `git diff` - review changes
3. Consult migration checklist
4. Review phase success criteria
5. If uncertain: commit current state and pause

---

## Testing Strategy During Risk Reduction

### Characterization Tests (Capture Current Behavior)

```python
# tests/characterization/test_registry_behavior.py
"""Characterization tests for current registry behavior.

These tests document how registries currently work, so we can
detect any behavioral changes during migration.
"""

def test_datasource_registry_lookup():
    """Document current datasource registry behavior."""
    from elspeth.core.registry import registry

    # Current behavior: can look up by name
    factory = registry._datasources.get("csv_local")
    assert factory is not None

    # Current behavior: factory is callable
    assert callable(factory)

    # Document current structure
    assert isinstance(registry._datasources, dict)
    assert "csv_local" in registry._datasources
    assert "csv_blob" in registry._datasources
    assert "blob" in registry._datasources

def test_llm_registry_lookup():
    """Document current LLM registry behavior."""
    from elspeth.core.llm.registry import llm_client_registry

    # Current behavior
    factory = llm_client_registry._plugins.get("azure_openai")
    assert factory is not None

    # Document clients
    assert "azure_openai" in llm_client_registry._plugins
    assert "openai_http" in llm_client_registry._plugins
    assert "mock" in llm_client_registry._plugins

def test_plugin_creation_with_context():
    """Document current plugin creation behavior."""
    from elspeth.core.experiments.plugin_registry import create_row_plugin
    from elspeth.core.plugins.context import PluginContext

    context = PluginContext(
        security_level="internal",
        plugin_kind="row_plugin",
        plugin_name="score_extractor",
    )

    plugin = create_row_plugin(
        {"name": "score_extractor"},
        parent_context=context,
    )

    assert plugin is not None
    assert hasattr(plugin, "name")
    assert plugin.name == "score_extractor"

# ... more characterization tests
```

### Security Enforcement Tests

```python
# tests/security/test_explicit_configuration.py
"""Test that all plugins require explicit configuration."""

import pytest
from elspeth.core.exceptions import ConfigurationError

def test_datasource_requires_security_level():
    """All datasources must have explicit security_level."""
    from elspeth.core.registry import registry

    with pytest.raises(ConfigurationError, match="security_level"):
        registry.create_datasource({
            "plugin": "csv_local",
            "path": "/tmp/test.csv",
            # Missing: security_level
        })

def test_llm_requires_all_critical_fields():
    """LLM clients must have explicit model, temperature, security_level."""
    from elspeth.core.llm.registry import llm_client_registry
    from elspeth.core.plugins.context import PluginContext

    context = PluginContext(security_level="internal", plugin_kind="llm", plugin_name="test")

    # Missing model
    with pytest.raises(ConfigurationError, match="model"):
        llm_client_registry.create("azure_openai", {"temperature": 0.7}, parent_context=context)

    # Missing temperature
    with pytest.raises(ConfigurationError, match="temperature"):
        llm_client_registry.create("azure_openai", {"model": "gpt-4"}, parent_context=context)

# ... more enforcement tests
```

### Performance Regression Tests

```python
# tests/performance/test_registry_performance.py
"""Performance regression tests."""

import time

def test_registry_lookup_performance():
    """Registry lookups should be fast (<1ms)."""
    from elspeth.core.registry import registry

    start = time.perf_counter()
    for _ in range(1000):
        factory = registry._datasources.get("csv_local")
    end = time.perf_counter()

    avg_time = (end - start) / 1000
    assert avg_time < 0.001, f"Registry lookup too slow: {avg_time*1000:.2f}ms"

def test_plugin_creation_performance():
    """Plugin creation should be fast (<10ms)."""
    from elspeth.core.experiments.plugin_registry import create_row_plugin
    from elspeth.core.plugins.context import PluginContext

    context = PluginContext(
        security_level="internal",
        plugin_kind="row_plugin",
        plugin_name="score_extractor",
    )

    start = time.perf_counter()
    plugin = create_row_plugin({"name": "score_extractor"}, parent_context=context)
    end = time.perf_counter()

    elapsed = end - start
    assert elapsed < 0.010, f"Plugin creation too slow: {elapsed*1000:.2f}ms"

# ... more performance tests
```

---

## Success Metrics

**Before migration can start**, all of the following must be true:

1. **Security**:
   - ✅ Silent default audit complete
   - ✅ All CRITICAL defaults removed or documented
   - ✅ Enforcement tests created and passing

2. **Testing**:
   - ✅ Test coverage >85%
   - ✅ All 545 tests passing
   - ✅ Characterization tests for all registries
   - ✅ 5+ end-to-end smoke tests

3. **Dependencies**:
   - ✅ Import chain map complete
   - ✅ Backward compatibility design approved

4. **Documentation**:
   - ✅ Migration checklist created
   - ✅ Rollback procedures documented
   - ✅ Phase checkpoints defined

**Estimated total time**: 8-12 hours of risk reduction before starting 12-17 hour migration.

---

## Next Steps

1. **Review this plan** with stakeholders
2. **Approve risk reduction activities**
3. **Schedule Week 1** (risk reduction)
4. **Gate migration** on Week 1 success criteria
5. **Execute migration** only after all gates pass

**Key Principle**: **Measure twice, cut once.** The 8-12 hours of risk reduction will save 20+ hours of debugging and rollback during migration.
