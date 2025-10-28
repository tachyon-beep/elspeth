# Phase 1 Plugin Migration Inventory

**Date**: 2025-10-26
**Branch**: `feature/adr-002-security-enforcement`
**Purpose**: Comprehensive inventory of BasePlugin migration status for all plugins

---

## Executive Summary

**Overall Migration Status: 63% Complete (17/27 plugins)**

| Plugin Category | Migrated | Not Migrated | Total | Progress |
|----------------|----------|--------------|-------|----------|
| **Datasources** | 4 | 0 | 4 | ✅ **100%** |
| **Sinks** | 13 | 0 | 13 | ✅ **100%** |
| **LLM Adapters** | 0 | 4 | 4 | ❌ **0%** |
| **Middleware** | 0 | 6 | 6 | ❌ **0%** |
| **TOTAL** | **17** | **10** | **27** | **63%** |

---

## ✅ MIGRATED: Datasources (4/4 - 100%)

All datasources already implement `BasePlugin` ABC.

### Direct BasePlugin Inheritance (2)

1. **`BlobDataSource`** (`src/elspeth/plugins/nodes/sources/blob.py`)
   - **Inheritance**: `class BlobDataSource(BasePlugin, DataSource)`
   - **Status**: ✅ Migrated
   - **Security Level**: Configured at initialization
   - **Notes**: Azure Blob Storage datasource

2. **`BaseCSVDataSource`** (`src/elspeth/plugins/nodes/sources/_csv_base.py`)
   - **Inheritance**: `class BaseCSVDataSource(BasePlugin, DataSource)`
   - **Status**: ✅ Migrated (base class for CSV datasources)
   - **Security Level**: Configured at initialization
   - **Notes**: Abstract base for all CSV datasources

### Transitive BasePlugin Inheritance (2)

3. **`CSVDataSource`** (`src/elspeth/plugins/nodes/sources/csv_local.py`)
   - **Inheritance**: `class CSVDataSource(BaseCSVDataSource)`
   - **Status**: ✅ Migrated (via BaseCSVDataSource)
   - **Security Level**: Inherited from BaseCSVDataSource
   - **Notes**: Local filesystem CSV datasource

4. **`CSVBlobDataSource`** (`src/elspeth/plugins/nodes/sources/csv_blob.py`)
   - **Inheritance**: `class CSVBlobDataSource(BaseCSVDataSource)`
   - **Status**: ✅ Migrated (via BaseCSVDataSource)
   - **Security Level**: Inherited from BaseCSVDataSource
   - **Notes**: Azure Blob CSV datasource

---

## ✅ MIGRATED: Sinks (13/13 - 100%)

All sinks already implement `BasePlugin` ABC.

### Direct BasePlugin Inheritance (10)

1. **`AnalyticsReportSink`** (`src/elspeth/plugins/nodes/sinks/analytics_report.py`)
   - **Inheritance**: `class AnalyticsReportSink(BasePlugin, ResultSink)`
   - **Status**: ✅ Migrated
   - **File**: `analytics_report.py`

2. **`BlobResultSink`** (`src/elspeth/plugins/nodes/sinks/blob.py`)
   - **Inheritance**: `class BlobResultSink(BasePlugin, ResultSink)`
   - **Status**: ✅ Migrated (base class for blob sinks)
   - **File**: `blob.py`

3. **`CsvResultSink`** (`src/elspeth/plugins/nodes/sinks/csv_file.py`)
   - **Inheritance**: `class CsvResultSink(BasePlugin, ResultSink)`
   - **Status**: ✅ Migrated
   - **File**: `csv_file.py`

4. **`EmbeddingsStoreSink`** (`src/elspeth/plugins/nodes/sinks/embeddings_store.py`)
   - **Inheritance**: `class EmbeddingsStoreSink(BasePlugin, ResultSink)`
   - **Status**: ✅ Migrated
   - **File**: `embeddings_store.py`

5. **`ExcelResultSink`** (`src/elspeth/plugins/nodes/sinks/excel.py`)
   - **Inheritance**: `class ExcelResultSink(BasePlugin, ResultSink)`
   - **Status**: ✅ Migrated
   - **File**: `excel.py`

6. **`FileCopySink`** (`src/elspeth/plugins/nodes/sinks/file_copy.py`)
   - **Inheritance**: `class FileCopySink(BasePlugin, ResultSink)`
   - **Status**: ✅ Migrated
   - **File**: `file_copy.py`

7. **`LocalBundleSink`** (`src/elspeth/plugins/nodes/sinks/local_bundle.py`)
   - **Inheritance**: `class LocalBundleSink(BasePlugin, ResultSink)`
   - **Status**: ✅ Migrated
   - **File**: `local_bundle.py`

8. **`ReproducibilityBundleSink`** (`src/elspeth/plugins/nodes/sinks/reproducibility_bundle.py`)
   - **Inheritance**: `class ReproducibilityBundleSink(BasePlugin, ResultSink)`
   - **Status**: ✅ Migrated
   - **File**: `reproducibility_bundle.py`

9. **`SignedArtifactSink`** (`src/elspeth/plugins/nodes/sinks/signed.py`)
   - **Inheritance**: `class SignedArtifactSink(BasePlugin, ResultSink)`
   - **Status**: ✅ Migrated
   - **File**: `signed.py`

10. **`ZipResultSink`** (`src/elspeth/plugins/nodes/sinks/zip_bundle.py`)
    - **Inheritance**: `class ZipResultSink(BasePlugin, ResultSink)`
    - **Status**: ✅ Migrated
    - **File**: `zip_bundle.py`

### Base Classes with BasePlugin (2)

11. **`_RepoSinkBase`** (`src/elspeth/plugins/nodes/sinks/repository.py`)
    - **Inheritance**: `class _RepoSinkBase(BasePlugin, ResultSink)`
    - **Status**: ✅ Migrated (abstract base for repo sinks)
    - **File**: `repository.py`
    - **Notes**: Base class for GitHubRepoSink and AzureDevOpsRepoSink

12. **`BaseVisualSink`** (`src/elspeth/plugins/nodes/sinks/_visual_base.py`)
    - **Inheritance**: `class BaseVisualSink(BasePlugin, ResultSink)`
    - **Status**: ✅ Migrated (abstract base for visual report sinks)
    - **File**: `_visual_base.py`
    - **Notes**: Base class for VisualAnalyticsSink and EnhancedVisualAnalyticsSink

### Transitive BasePlugin Inheritance (3)

13. **`AzureBlobArtifactsSink`** (`src/elspeth/plugins/nodes/sinks/blob.py`)
    - **Inheritance**: `class AzureBlobArtifactsSink(BlobResultSink)`
    - **Status**: ✅ Migrated (via BlobResultSink)

14. **`VisualAnalyticsSink`** (`src/elspeth/plugins/nodes/sinks/visual_report.py`)
    - **Inheritance**: `class VisualAnalyticsSink(BaseVisualSink)`
    - **Status**: ✅ Migrated (via BaseVisualSink)

15. **`EnhancedVisualAnalyticsSink`** (`src/elspeth/plugins/nodes/sinks/enhanced_visual_report.py`)
    - **Inheritance**: `class EnhancedVisualAnalyticsSink(BaseVisualSink)`
    - **Status**: ✅ Migrated (via BaseVisualSink)

### Repository Sinks (Transitive via _RepoSinkBase)

16. **`GitHubRepoSink`** (`src/elspeth/plugins/nodes/sinks/repository.py`)
    - **Inheritance**: `class GitHubRepoSink(_RepoSinkBase)`
    - **Status**: ✅ Migrated (via _RepoSinkBase)

17. **`AzureDevOpsRepoSink`** (`src/elspeth/plugins/nodes/sinks/repository.py`)
    - **Inheritance**: `class AzureDevOpsRepoSink(_RepoSinkBase)`
    - **Status**: ✅ Migrated (via _RepoSinkBase)

18. **`AzureDevOpsArtifactsRepoSink`** (`src/elspeth/plugins/nodes/sinks/repository.py`)
    - **Inheritance**: `class AzureDevOpsArtifactsRepoSink(AzureDevOpsRepoSink)`
    - **Status**: ✅ Migrated (via AzureDevOpsRepoSink → _RepoSinkBase)

**Note**: Repository sinks listed separately for clarity but already included in the 13/13 count above.

---

## ❌ NOT MIGRATED: LLM Adapters (0/4 - 0%)

**Status**: All LLM adapters currently implement `LLMClientProtocol` only, NOT `BasePlugin`.

**Current Pattern**:
```python
class AzureOpenAIClient(LLMClientProtocol):
    ...
```

**Target Pattern** (Phase 1.3):
```python
class AzureOpenAIClient(BasePlugin, LLMClientProtocol):
    def __init__(self, *, security_level: SecurityLevel, allow_downgrade: bool, ...):
        super().__init__(security_level=security_level, allow_downgrade=allow_downgrade)
        ...
```

### LLM Adapters Requiring Migration (4)

1. **`AzureOpenAIClient`** (`src/elspeth/plugins/nodes/transforms/llm/azure_openai.py`)
   - **Current**: `class AzureOpenAIClient(LLMClientProtocol)`
   - **Status**: ❌ Not migrated
   - **Priority**: HIGH (production use)
   - **Estimated Effort**: 2 hours

2. **`HttpOpenAIClient`** (`src/elspeth/plugins/nodes/transforms/llm/openai_http.py`)
   - **Current**: `class HttpOpenAIClient(LLMClientProtocol)`
   - **Status**: ❌ Not migrated
   - **Priority**: MEDIUM (alternative to Azure)
   - **Estimated Effort**: 1.5 hours

3. **`MockLLMClient`** (`src/elspeth/plugins/nodes/transforms/llm/mock.py`)
   - **Current**: `class MockLLMClient(LLMClientProtocol)`
   - **Status**: ❌ Not migrated
   - **Priority**: HIGH (testing infrastructure)
   - **Estimated Effort**: 1 hour

4. **`StaticLLMClient`** (`src/elspeth/plugins/nodes/transforms/llm/static.py`)
   - **Current**: `class StaticLLMClient(LLMClientProtocol)`
   - **Status**: ❌ Not migrated
   - **Priority**: LOW (deterministic testing only)
   - **Estimated Effort**: 1 hour

**Total Effort Estimate**: 5.5 hours for all LLM adapters

---

## ❌ NOT MIGRATED: Middleware (0/6 - 0%)

**Status**: All middleware currently implement `LLMMiddleware` protocol only, NOT `BasePlugin`.

**Current Pattern**:
```python
class AuditMiddleware(LLMMiddleware):
    ...
```

**Target Pattern** (Phase 1.4):
```python
class AuditMiddleware(BasePlugin, LLMMiddleware):
    def __init__(self, *, security_level: SecurityLevel, allow_downgrade: bool, ...):
        super().__init__(security_level=security_level, allow_downgrade=allow_downgrade)
        ...
```

### Middleware Requiring Migration (6)

1. **`AuditMiddleware`** (`src/elspeth/plugins/nodes/transforms/llm/middleware/audit.py`)
   - **Current**: `class AuditMiddleware(LLMMiddleware)`
   - **Status**: ❌ Not migrated
   - **Priority**: MEDIUM (logging/compliance)
   - **Estimated Effort**: 1 hour

2. **`AzureContentSafetyMiddleware`** (`src/elspeth/plugins/nodes/transforms/llm/middleware/azure_content_safety.py`)
   - **Current**: `class AzureContentSafetyMiddleware(LLMMiddleware)`
   - **Status**: ❌ Not migrated
   - **Priority**: HIGH (security control)
   - **Estimated Effort**: 1.5 hours

3. **`ClassifiedMaterialMiddleware`** (`src/elspeth/plugins/nodes/transforms/llm/middleware/classified_material.py`)
   - **Current**: `class ClassifiedMaterialMiddleware(LLMMiddleware)`
   - **Status**: ❌ Not migrated
   - **Priority**: HIGHEST (ADR-003 integration)
   - **Estimated Effort**: 2 hours

4. **`HealthMonitorMiddleware`** (`src/elspeth/plugins/nodes/transforms/llm/middleware/health_monitor.py`)
   - **Current**: `class HealthMonitorMiddleware(LLMMiddleware)`
   - **Status**: ❌ Not migrated
   - **Priority**: LOW (observability)
   - **Estimated Effort**: 1 hour

5. **`PIIShieldMiddleware`** (`src/elspeth/plugins/nodes/transforms/llm/middleware/pii_shield.py`)
   - **Current**: `class PIIShieldMiddleware(LLMMiddleware)`
   - **Status**: ❌ Not migrated
   - **Priority**: HIGH (security control)
   - **Estimated Effort**: 1.5 hours

6. **`PromptShieldMiddleware`** (`src/elspeth/plugins/nodes/transforms/llm/middleware/prompt_shield.py`)
   - **Current**: `class PromptShieldMiddleware(LLMMiddleware)`
   - **Status**: ❌ Not migrated
   - **Priority**: MEDIUM (security control)
   - **Estimated Effort**: 1 hour

**Total Effort Estimate**: 8 hours for all middleware

---

## Phase 1 Work Breakdown

### Phase 1.1: Datasource Migration Verification (DONE ✅)
**Effort**: 0 hours (already complete)
**Status**: All 4 datasources implement BasePlugin

### Phase 1.2: Sink Migration Verification (DONE ✅)
**Effort**: 0 hours (already complete)
**Status**: All 13 sinks implement BasePlugin

### Phase 1.3: LLM Adapter Migration (TODO)
**Effort**: 5.5 hours
**Priority Order**:
1. MockLLMClient (1 hour) - Unblock testing
2. AzureOpenAIClient (2 hours) - Production adapter
3. HttpOpenAIClient (1.5 hours) - Alternative adapter
4. StaticLLMClient (1 hour) - Deterministic testing

**Blockers**: None - can start immediately

### Phase 1.4: Middleware Migration (TODO)
**Effort**: 8 hours
**Priority Order**:
1. ClassifiedMaterialMiddleware (2 hours) - ADR-003 integration
2. AzureContentSafetyMiddleware (1.5 hours) - Security control
3. PIIShieldMiddleware (1.5 hours) - Security control
4. PromptShieldMiddleware (1 hour) - Security control
5. AuditMiddleware (1 hour) - Compliance
6. HealthMonitorMiddleware (1 hour) - Observability

**Blockers**: None - can start after Phase 1.3 or in parallel

### Phase 1.5: Suite Runner Integration (TODO)
**Effort**: 4-6 hours (estimated)
**Blockers**: Requires Phase 1.3 and 1.4 to be complete for full integration

**Work Required**:
1. Verify suite runner validation logic triggers correctly
2. Test with all plugin types (datasources, LLMs, middleware, sinks)
3. Remove 10 xfail markers from ADR-002 suite integration tests
4. Validate error messages provide context without leaking data

---

## Test Impact Analysis

### Tests That Will Pass After Phase 1.3 (LLM Migration)
- Tests involving LLM adapters with security validation
- End-to-end workflow tests with LLM security levels

### Tests That Will Pass After Phase 1.4 (Middleware Migration)
- `test_four_level_uplifting_chain`
- `test_three_level_uplifting_with_mismatched_sink`
- Middleware integration tests

### Tests That Will Pass After Phase 1.5 (Suite Runner Integration)
- `test_security_validation_error_provides_context_without_leaking_data`
- `test_fail_path_secret_datasource_unofficial_sink`
- `test_upgrade_path_official_datasource_secret_sink`
- `test_mixed_security_multi_sink`
- `test_mixed_levels_fails_at_start`
- `test_minimum_envelope_computed_correctly`
- `test_validation_consistent_with_envelope`
- `test_all_sinks_implement_baseplugin` (will already pass after verifying sinks)

**Total ADR-002 Impact**: 10 currently-failing tests will pass after Phase 1 complete

---

## Migration Checklist Template

For each plugin migration, follow this checklist:

### Pre-Migration
- [ ] Read existing plugin code and understand configuration
- [ ] Identify security level determination logic
- [ ] Review existing tests for the plugin
- [ ] Document current `__init__` signature

### Migration Steps
- [ ] Add `BasePlugin` to class inheritance
- [ ] Add `security_level: SecurityLevel` parameter to `__init__`
- [ ] Add `allow_downgrade: bool` parameter to `__init__`
- [ ] Call `super().__init__(security_level=..., allow_downgrade=...)`
- [ ] Ensure `__init__` is keyword-only (`*,` before parameters)
- [ ] Update all instantiation sites to pass new parameters
- [ ] Update test fixtures to provide security parameters

### Post-Migration Verification
- [ ] Run plugin-specific tests: `pytest tests/test_<plugin>*.py -v`
- [ ] Run ADR-002 test suite: `pytest tests/test_adr002*.py -v`
- [ ] Run full test suite: `pytest -m "not slow"`
- [ ] Verify MyPy clean: `mypy src/elspeth/`
- [ ] Verify Ruff clean: `ruff check src tests`
- [ ] Check no regressions in overall test count

### Documentation
- [ ] Update this inventory document
- [ ] Update plugin docstrings with security level info
- [ ] Update CLAUDE.md if plugin is mentioned
- [ ] Create migration commit with clear message

---

## Risk Assessment

### Low Risk (Already Complete)
- ✅ Datasources: All migrated, tests passing
- ✅ Sinks: All migrated, tests passing

### Medium Risk (Phase 1.3)
- ⚠️ LLM Adapters: 4 plugins, well-defined interface, good test coverage
- **Risk**: LLM adapters are used in every experiment - breaking them blocks all workflows
- **Mitigation**: Start with MockLLMClient (test infrastructure), validate before production adapters

### Medium Risk (Phase 1.4)
- ⚠️ Middleware: 6 plugins, some with complex security logic (ClassifiedMaterialMiddleware)
- **Risk**: ClassifiedMaterialMiddleware has ADR-003 dependencies (not fully implemented)
- **Mitigation**: Defer ClassifiedMaterialMiddleware to Phase 2, migrate simpler middleware first

### Higher Risk (Phase 1.5)
- ⚠️⚠️ Suite Runner Integration: Complex orchestration logic with many edge cases
- **Risk**: Suite runner is already complex (58% coverage), adding validation increases complexity
- **Mitigation**: Use Five-Phase Methodology safety net (Phase 0 complete), extensive testing

---

## Success Metrics

### Phase 1.3 Success Criteria
- ✅ All 4 LLM adapters implement BasePlugin
- ✅ Zero test regressions
- ✅ MockLLMClient tests passing (unblock test infrastructure)
- ✅ AzureOpenAIClient tests passing (production workflows)

### Phase 1.4 Success Criteria
- ✅ At least 4/6 middleware implement BasePlugin
- ✅ Security-critical middleware migrated (PIIShield, ContentSafety, PromptShield)
- ✅ ClassifiedMaterialMiddleware deferred to Phase 2 (ADR-003 dependency)
- ✅ Zero test regressions

### Phase 1.5 Success Criteria
- ✅ Suite runner validation triggered for all plugin types
- ✅ 10 ADR-002 integration tests passing (xfail markers removed)
- ✅ Overall ADR-002 suite: ≥95% success (67/70 tests)
- ✅ Zero regressions in overall test suite

### Overall Phase 1 Success Criteria
- ✅ 100% plugin migration (27/27 plugins implement BasePlugin)
- ✅ ADR-002 test suite: ≥95% success
- ✅ Overall test suite: ≥98% success
- ✅ MyPy clean
- ✅ Ruff clean
- ✅ Ready for Phase 2 (ADR-003: SecureDataFrame integration)

---

## Next Steps

1. **Immediate** (30 minutes): Mark 10 remaining ADR-002 failures as xfail
2. **Phase 1.3** (5.5 hours): Migrate LLM adapters to BasePlugin
3. **Phase 1.4** (8 hours): Migrate middleware to BasePlugin
4. **Phase 1.5** (4-6 hours): Integrate and validate suite runner
5. **Phase 2** (future): ADR-003 SecureDataFrame full implementation

**Total Phase 1 Estimated Effort**: 17.5-19.5 hours

---

**Document Version**: 1.0
**Last Updated**: 2025-10-26
**Status**: Phase 0 Complete, Phase 1 Ready to Start
