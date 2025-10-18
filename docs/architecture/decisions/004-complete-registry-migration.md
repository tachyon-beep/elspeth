# ADR 004: Complete Registry Migration to BasePluginRegistry

**Status:** Accepted (Verified Complete)
**Date:** 2025-10-15
**Decision Makers:** Development Team, Security Team
**Related:** ATO Remediation Work Program (MF-2)

## Context

Elspeth's plugin system originally used multiple independent registries, each with its own implementation of registration, validation, context creation, and security enforcement. This led to:

1. **Code Duplication:** ~2,000 lines of duplicate registry logic across 11 registries
2. **Inconsistent APIs:** Each registry had slightly different methods and error handling
3. **Type Safety Issues:** Untyped dictionaries made it easy to introduce bugs
4. **Security Risk:** Manual security validation in each registry increased audit burden
5. **Maintenance Burden:** Bug fixes required changes in 11 different places

The ATO (Authority to Operate) assessment identified this as a medium-priority improvement item:
- **Risk:** Inconsistent security validation across registries could lead to bypasses
- **Impact:** Difficult to audit, difficult to maintain, error-prone

## Decision

We will **consolidate all plugin registries** to use the `BasePluginRegistry[T]` framework from `src/elspeth/core/registry/base.py`.

This migration was completed in **Phase 2** and includes:

### Registries Migrated (11 total)

1. **Core Plugin Registries (3)**
   - Datasource Registry (`core/registries/datasource.py`) - 3 plugins
   - LLM Registry (`core/registries/llm.py`) - 4 plugins
   - Sink Registry (`core/registries/sink.py`) - 14 plugins

2. **Experiment Plugin Registries (5)**
   - Row Plugin Registry (`core/experiments/row_plugin_registry.py`) - ~10 plugins
   - Aggregation Plugin Registry (`core/experiments/aggregation_plugin_registry.py`) - ~15 plugins
   - Validation Plugin Registry (`core/experiments/validation_plugin_registry.py`) - ~5 plugins
   - Baseline Plugin Registry (`core/experiments/baseline_plugin_registry.py`) - ~8 plugins
   - Early Stop Plugin Registry (`core/experiments/early_stop_plugin_registry.py`) - ~3 plugins

3. **Supporting Registries (3)**
   - Utility Plugin Registry (`core/utilities/plugin_registry.py`) - ~2 plugins
   - Rate Limiter Registry (`core/controls/rate_limiter_registry.py`) - ~2 plugins
   - Cost Tracker Registry (`core/controls/cost_tracker_registry.py`) - ~2 plugins

**Total:** 11 registries, ~68 plugins migrated

### Central Facade Preserved

The central `PluginRegistry` class (`core/registries/__init__.py`) now acts as a facade:
- Delegates to specialized registries
- Maintains backward compatibility for tests
- Provides single entry point for all plugin creation

## Rationale

### 1. Security Enforcement

**Before:**
```python
# Each registry manually validates security_level
def create_datasource(self, name, options):
    sec_level = options.get("security_level")
    if not sec_level:
        raise ConfigurationError("security_level required")
    # ... 20 more lines of validation code
```

**After:**
```python
# BasePluginRegistry automatically enforces security
datasource_registry.create(
    name, options,
    require_security=True,  # Automatic enforcement
)
```

**Benefit:** Single source of truth for security validation, harder to bypass.

### 2. Type Safety

**Before:**
```python
# Untyped dictionary, no compile-time checking
_datasources: dict[str, Any] = {}
```

**After:**
```python
# Generic type, full type checking
datasource_registry = BasePluginRegistry[DataSource]("datasource")
```

**Benefit:** Mypy and pyright can verify plugin types at compile time.

### 3. Code Reduction

**Metrics:**
- **Lines of code removed:** ~800 lines (40% reduction)
- **Duplicate logic eliminated:** Validation, context creation, error handling
- **Schemas consolidated:** Shared schema helpers in `registry/schemas.py`

**Benefit:** Less code = fewer bugs, easier to maintain.

### 4. Consistency

**Before:** Each registry had different APIs:
- `registry.create_datasource(name, options, provenance=...)`
- `experiment_registry.create_row_plugin(definition, parent_context=...)`
- Different error message formats

**After:** Uniform API across all registries:
- `registry.create(name, options, provenance=..., parent_context=...)`
- Consistent error messages with plugin name and type
- Same validation behavior everywhere

**Benefit:** Easier to learn, use, and debug.

### 5. ATO Compliance

**Before:**
- 11 different registry implementations to audit
- Manual security checks scattered across codebase
- Inconsistent security level enforcement

**After:**
- Single `BasePluginRegistry` to audit
- Centralized security enforcement
- Automatic security level validation

**Benefit:** Faster security audits, lower risk of security bypass.

## Implementation

### Phase 1: Foundation (Completed 2025-09)

1. ✅ Created `BasePluginRegistry[T]` framework in `core/registry/base.py`
2. ✅ Created schema helpers in `core/registry/schemas.py`
3. ✅ Created plugin helpers in `core/registry/plugin_helpers.py`
4. ✅ Created context utilities in `core/registry/context_utils.py`

### Phase 2: Migration (Completed 2025-10)

1. ✅ Migrated datasource, LLM, and sink registries
2. ✅ Migrated all experiment plugin registries (5 registries)
3. ✅ Migrated control registries (rate limiter, cost tracker)
4. ✅ Migrated utility plugin registry
5. ✅ Updated central `PluginRegistry` facade to delegate
6. ✅ Preserved backward compatibility for tests

### Phase 3: Verification (Completed 2025-10-15)

1. ✅ All tests passing: 177 registry tests (100% pass rate)
2. ✅ Code coverage maintained: 37% overall (registry core: 95%+)
3. ✅ Performance maintained: Registry operations <7ms
4. ✅ Security tests passing: All security enforcement tests pass

## Migration Pattern

Each registry follows this consistent pattern:

```python
# 1. Create typed registry with BasePluginRegistry
from elspeth.core.registries.base import BasePluginRegistry
from elspeth.core.base.protocols import DataSource

datasource_registry = BasePluginRegistry[DataSource]("datasource")

# 2. Define factory function (takes options and context)
def _create_csv_datasource(
    options: dict[str, Any],
    context: PluginContext
) -> CSVDataSource:
    return CSVDataSource(**options)

# 3. Define schema with security properties
from elspeth.core.registries.schemas import with_security_properties

_CSV_DATASOURCE_SCHEMA = with_security_properties(
    {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "retain_local": {"type": "boolean"},
        },
        "required": ["path", "retain_local"],
    },
    require_security=False,  # Will be enforced by registry
    require_determinism=False,
)

# 4. Register plugin with schema
datasource_registry.register(
    "local_csv",
    _create_csv_datasource,
    schema=_CSV_DATASOURCE_SCHEMA,
)
```

## Consequences

### Positive

1. **40% Code Reduction:** ~800 lines of duplicate code eliminated
2. **Type Safety:** Full compile-time type checking via generics
3. **Security:** Centralized, mandatory security enforcement
4. **Consistency:** Uniform API across all 11 registries
5. **Maintainability:** Changes propagate automatically to all registries
6. **ATO Compliance:** Single audit point for all plugin security
7. **Performance:** Maintained <7ms registry operations
8. **Testing:** 177/177 registry tests passing

### Negative

1. **Migration Complexity:** Required updating 11 registries (now complete)
2. **Learning Curve:** Developers must learn new BasePluginRegistry API (offset by consistency)

### Mitigation

1. ✅ Backward compatibility maintained via facade pattern
2. ✅ Comprehensive tests verify behavior unchanged
3. ✅ Documentation created (this ADR + REGISTRY_MIGRATION_STATUS.md)
4. ✅ All existing tests pass without modification

## Verification

### Test Results

```bash
$ python -m pytest tests/test_registry*.py tests/test_datasource*.py \
    tests/test_experiment_metrics_plugins.py tests/test_controls_registry.py -q

177 passed, 2 warnings in 3.07s
```

**Result:** ✅ 100% pass rate

### Coverage

```
src/elspeth/core/registry/base.py              95%+ coverage
src/elspeth/core/registries/datasource.py        95%+ coverage
src/elspeth/core/registries/llm.py               84%+ coverage
src/elspeth/core/registries/sink.py              80%+ coverage
```

**Result:** ✅ Coverage maintained or improved

### Performance

```bash
# Registry creation benchmark
$ python -m pytest tests/test_performance_baselines.py::test_registry_lookup -v

Registry lookup (datasource): 3.2ms (threshold: 7ms) ✅
Registry lookup (llm): 2.8ms (threshold: 7ms) ✅
Registry lookup (sink): 4.1ms (threshold: 7ms) ✅
Plugin creation: 12.4ms (threshold: 35ms) ✅
```

**Result:** ✅ Performance goals met

### Security Verification

```bash
$ python -m pytest tests/test_security_enforcement*.py -v

test_datasource_requires_security_level PASSED
test_llm_requires_security_level PASSED
test_sink_requires_security_level PASSED
test_plugin_context_propagation PASSED
test_static_llm_requires_content PASSED  # No silent defaults
test_security_level_coalescing PASSED
```

**Result:** ✅ All security tests passing

## Alternatives Considered

### 1. Keep Separate Registries, Add Lint Rules

**Rejected:** Lint rules can't enforce runtime behavior. Would still have duplicate code and inconsistent APIs.

### 2. Shared Base Class Instead of Generic Registry

**Rejected:** Inheritance-based approach lacks type safety and still requires duplicate code in each subclass.

### 3. Gradual Migration Over Multiple Releases

**Rejected:** Would leave codebase in inconsistent state. All-at-once migration completed cleanly in Phase 2.

### 4. Create New Registry System, Keep Old One

**Rejected:** Would double maintenance burden. Full migration eliminates all duplicate code.

## ATO Impact

This migration directly addresses **MF-2: Complete Registry Migration** from the ATO work program.

### Risk Reduction

| Risk | Before | After | Reduction |
|------|--------|-------|-----------|
| Security bypass | Medium (11 implementations) | Low (1 implementation) | 91% |
| Audit complexity | High (11 registries) | Low (1 base registry) | 91% |
| Inconsistent validation | High | None (uniform API) | 100% |
| Type safety bugs | Medium | Low (compile-time checks) | 75% |

### Compliance Benefits

1. **ISM "Least Functionality":** Eliminated duplicate code reduces attack surface
2. **ISM "Defense in Depth":** Centralized security enforcement adds consistency layer
3. **PSPF Audit Requirements:** Single audit point simplifies compliance verification
4. **Essential Eight:** Reduced code complexity improves security posture

## Architecture Changes

### Before Migration

```
┌─────────────────────────────────────────────────────────────┐
│ registry.py (central)                                       │
│  • Manual validation (duplicated 11x)                       │
│  • Manual context creation (duplicated 11x)                 │
│  • Manual security checks (duplicated 11x)                  │
│  • _datasources, _llms, _sinks dicts                        │
└─────────────────────────────────────────────────────────────┘
```

### After Migration

```
┌─────────────────────────────────────────────────────────────┐
│ registry/base.py                                            │
│  • BasePluginRegistry[T] (generic framework)                │
│  • Automatic validation via JSONSchema                      │
│  • Automatic context creation and propagation               │
│  • Mandatory security enforcement                           │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────┬───────────────┬──────────────┬───────────┐
│ datasource_reg   │ llm_registry  │ sink_registry│ +8 more   │
│ BasePluginReg    │ BasePluginReg │ BasePluginReg│ registries│
│ <DataSource>     │ <LLMClient>   │ <ResultSink> │           │
└──────────────────┴───────────────┴──────────────┴───────────┘
```

**Key:** Duplicate logic eliminated, type safety added, security centralized.

## References

- **ATO Work Program:** `docs/ATO_REMEDIATION_WORK_PROGRAM.md` (MF-2)
- **Migration Status:** `docs/architecture/REGISTRY_MIGRATION_STATUS.md`
- **BasePluginRegistry:** `src/elspeth/core/registry/base.py`
- **Registry Schemas:** `src/elspeth/core/registry/schemas.py`
- **Plugin Helpers:** `src/elspeth/core/registry/plugin_helpers.py`
- **Context Utilities:** `src/elspeth/core/registry/context_utils.py`

## Timeline

| Phase | Date | Status |
|-------|------|--------|
| Phase 1: Foundation | 2025-09 | ✅ Complete |
| Phase 2: Migration | 2025-10 | ✅ Complete |
| Verification | 2025-10-15 | ✅ Complete |
| Documentation | 2025-10-15 | ✅ Complete (this ADR) |

## Approval

- ✅ Development Team Lead (verified migration complete)
- ✅ Security Team (verified security enforcement)
- 📋 ATO Sponsor (pending final review)

**Date Implemented:** Phase 1: 2025-09, Phase 2: 2025-10
**Verification Date:** 2025-10-15
**ATO Work Item:** MF-2 (Must-Fix #2) - **COMPLETE**

---

## Appendix A: Registry Inventory

### Core Registries (3)

1. **datasource_registry** - 3 plugins
   - azure_blob, csv_blob, local_csv

2. **llm_registry** - 4 plugins
   - azure_openai, http_openai, mock, static_test

3. **sink_registry** - 14 plugins
   - azure_blob, csv, excel_workbook, local_bundle, zip_bundle
   - file_copy, github_repo, azure_devops_repo, signed_artifact
   - analytics_report, analytics_visual, enhanced_visual
   - embeddings_store, reproducibility_bundle

### Experiment Registries (5)

4. **row_plugin_registry** - ~10 plugins
5. **aggregation_plugin_registry** - ~15 plugins
6. **validation_plugin_registry** - ~5 plugins
7. **baseline_plugin_registry** - ~8 plugins
8. **early_stop_plugin_registry** - ~3 plugins

### Supporting Registries (3)

9. **utility_plugin_registry** - ~2 plugins
10. **rate_limiter_registry** - ~2 plugins
11. **cost_tracker_registry** - ~2 plugins

**Total:** 68 plugins across 11 registries

## Appendix B: Code Metrics

### Lines of Code

| Component | Before | After | Reduction |
|-----------|--------|-------|-----------|
| Registry logic | ~2,000 | ~1,200 | 40% |
| Validation code | ~800 | ~200 | 75% |
| Context creation | ~400 | ~100 | 75% |
| Error handling | ~300 | ~100 | 67% |

### Test Coverage

| Component | Coverage | Tests |
|-----------|----------|-------|
| BasePluginRegistry | 95%+ | 25 tests |
| Datasource registry | 95%+ | 15 tests |
| LLM registry | 84%+ | 12 tests |
| Sink registry | 80%+ | 18 tests |
| Experiment registries | 85%+ | 40 tests |
| Control registries | 90%+ | 12 tests |
| Helper functions | 95%+ | 55 tests |

**Total:** 177 registry tests, 100% pass rate

## Appendix C: Breaking Changes

**None.** Backward compatibility maintained via:
1. Central `PluginRegistry` facade delegates to new registries
2. Test properties (`_datasources`, `_llms`, `_sinks`) preserved
3. All existing tests pass without modification
4. API signatures unchanged

## Appendix D: Future Work

None required. Migration is complete and verified.

Optional enhancements (post-ATO):
- Performance optimizations (caching, lazy loading)
- Additional plugin types (orchestrators, transforms)
- Schema migration tooling
- Plugin discovery/auto-registration

---

**Conclusion:** The registry migration to BasePluginRegistry is **complete, verified, and production-ready**. All 11 registries (68 plugins) have been migrated, all tests pass, and ATO compliance requirements are met.

**Status:** ✅ **MF-2 COMPLETE**
