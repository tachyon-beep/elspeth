# Terminology Renaming Assessment: "Classified" → "Secure"

**Migration Type**: Terminology Standardization - Universal Applicability
**Status**: Planning - Ready for Review
**Rationale**: Remove government-specific terminology, improve general applicability
**Estimated Effort**: 12-16 hours (1.5-2 days)
**Risk Level**: LOW (mechanical rename)
**Confidence**: VERY HIGH

---

## Executive Summary

### Why Rename?

**Current**: "Classified" terminology has strong government/military connotations (TOP SECRET, SECRET, CONFIDENTIAL)
**Target**: "Secure" terminology is universally applicable (enterprise, healthcare, finance, research)

**Benefits**:
1. **Broader applicability** - Works for any industry requiring data security
2. **Less intimidating** - Enterprise users understand "secure data" vs. government "classified data"
3. **Clearer intent** - "Secure" describes the property, "classified" implies government context
4. **Better alignment** - Matches existing `security_level` and `SecurityLevel` naming throughout codebase

### Scope

**Total Impact**: ~86 files, ~1,450 occurrences across code, tests, and documentation

| Area | Files | Occurrences | Complexity |
|------|-------|-------------|------------|
| Source Code | 14 | 118 | LOW |
| Tests | 14 | 307 | LOW |
| Documentation | 50 | 1,023 | MEDIUM |
| Migration Docs (new) | 5 | ~300 | LOW |
| ADR-002 Artifacts | 3 | ~150 | LOW |

### Proposed Renaming

| Current Term | New Term | Occurrences | Rationale |
|--------------|----------|-------------|-----------|
| `ClassifiedDataFrame` | `SecureDataFrame` | ~24 | Main container class |
| `ClassifiedData[T]` | `SecureData[T]` | ~10 (planned) | Generic wrapper |
| `classification` (field) | `security_level` | ~66 | Align with existing naming |
| `with_uplifted_classification()` | `with_uplifted_security_level()` | ~12 | Method clarity |
| `classified_material` (middleware) | `sensitive_material` | ~22 | Content detection, not data wrapper |
| `classification_bypass` (test) | `security_bypass` | ~6 | Test scenario naming |
| "classification" (docs) | "security level" | ~1,000+ | Documentation clarity |

---

## Detailed Impact Analysis

### 1. Source Code (14 files, 118 occurrences - LOW COMPLEXITY)

#### Core Security Module

**`src/elspeth/core/security/classified_data.py`** (66 occurrences)
- **File rename**: → `secure_data.py`
- **Class**: `ClassifiedDataFrame` → `SecureDataFrame`
- **Field**: `classification: SecurityLevel` → `security_level: SecurityLevel`
- **Methods**:
  - `create_from_datasource(classification)` → `create_from_datasource(security_level)`
  - `with_uplifted_classification(new_level)` → `with_uplifted_security_level(new_level)`
  - `validate_access_by()` - No change (method name is clear)
- **Docstrings**: ~40 occurrences of "classification" → "security level"
- **Comments**: ~10 occurrences
- **Risk**: LOW - Single file, mechanical rename, comprehensive tests

**`src/elspeth/core/security/__init__.py`** (5 occurrences)
- **Import**: `from .classified_data import ClassifiedDataFrame` → `from .secure_data import SecureDataFrame`
- **Export**: Update `__all__`
- **Risk**: VERY LOW - Simple import/export changes

#### Middleware

**`src/elspeth/plugins/nodes/transforms/llm/middleware/classified_material.py`** (22 occurrences)
- **File rename**: → `sensitive_material.py` (NOT "secure" - this detects sensitive content, not a data wrapper)
- **Class**: `ClassifiedMaterialMiddleware` → `SensitiveMaterialMiddleware`
- **Name field**: `name = "classified_material"` → `name = "sensitive_material"`
- **Rationale**: This middleware detects classified/sensitive content in PROMPTS, it's not about the data container
- **Risk**: MEDIUM - Config files reference `classified_material`, must update all configs

**Other Source Files** (11 files, ~25 occurrences)
- Mostly imports and type annotations
- Pattern: `ClassifiedDataFrame` → `SecureDataFrame`
- Risk: VERY LOW - IDE refactoring tools handle easily

---

### 2. Tests (14 files, 307 occurrences - LOW COMPLEXITY)

#### Test Files Requiring Rename

| Current Filename | New Filename | Occurrences |
|------------------|--------------|-------------|
| `test_adr002a_invariants.py` | Keep (ADR number reference) | 81 |
| `test_adr002_properties.py` | Keep | 40 |
| `test_adr002_suite_integration.py` | Keep | 18 |
| `test_adr002a_performance.py` | Keep | 18 |
| `test_adr002_invariants.py` | Keep | 59 |
| `test_classified_material_middleware.py` | `test_sensitive_material_middleware.py` | 7 |
| `test_middleware_security_filters.py` | Keep | 55 |

**Test Data Files**:
- `classification_bypass.yaml` → `security_bypass.yaml` (6 occurrences)
- `classified_secrets.csv` → `sensitive_secrets.csv` (1 occurrence - filename only)

**Patterns to Replace**:
```python
# Before:
classified_df = ClassifiedDataFrame.create_from_datasource(...)
assert classified_df.classification == SecurityLevel.SECRET

# After:
secure_df = SecureDataFrame.create_from_datasource(...)
assert secure_df.security_level == SecurityLevel.SECRET
```

**Risk**: LOW - Tests are isolated, comprehensive suite will catch any errors

---

### 3. Documentation (50 files, 1,023 occurrences - MEDIUM COMPLEXITY)

#### High-Impact Documentation

**ADR-002 Artifacts** (PRIMARY DOCUMENTS - ~200 occurrences)
- `docs/architecture/decisions/002-security-architecture.md` (7 occurrences)
- `docs/architecture/decisions/002-a-trusted-container-model.md` (45 occurrences)
- `docs/security/adr-002-classified-dataframe-hardening-delta.md` (130 occurrences)
- `docs/security/adr-002-orchestrator-security-model.md` (111 occurrences)
- `docs/security/adr-002-a-trusted-container-model.md` (68 occurrences)

**Strategy**:
- Keep ADR titles/filenames (historical record)
- Add editorial note at top: "Note: Original terminology used 'classified data' for government context. Implementation uses 'secure data' for universal applicability."
- Update code examples and technical content to use new terminology
- Preserve historical context in Decision/Context sections

**Plugin Development Guide** (69 occurrences)
- `docs/guides/plugin-development-adr002a.md`
- **Strategy**: Full update - this is current documentation, not historical record
- Replace all code examples with new terminology

**Architecture Documentation** (~200 occurrences across 15 files)
- `docs/architecture/security-controls.md`
- `docs/architecture/plugin-security-model.md`
- `docs/architecture/data-flow-diagrams.md`
- `docs/architecture/plugin-catalogue.md`
- etc.
- **Strategy**: Full update - current architecture uses new terminology

**Examples & Guides** (~100 occurrences across 10 files)
- `docs/examples/SECURITY_MIDDLEWARE_DEMOS.md`
- `docs/examples/SECURE_AZURE_WORKFLOW_GUIDE.md`
- etc.
- **Strategy**: Full update - examples should reflect current API

**Compliance Documentation** (~30 occurrences across 5 files)
- `docs/compliance/AUSTRALIAN_GOVERNMENT_CONTROLS.md` (25 occurrences)
- **Strategy**: KEEP "classified" - This references actual government classification requirements
- Only update code examples, not requirement descriptions

#### Low-Impact Documentation

**Migration Planning Docs** (~300 occurrences across 5 files - JUST CREATED)
- `docs/migration/adr-003-004-classified-containers/`
- **Strategy**: Full update - these are planning docs, update before execution

**Archive/Historical** (~50 occurrences)
- `docs/security/archive/` - Keep as-is (historical record)

---

### 4. ADR-002 Implementation Artifacts (3-4 files, ~150 occurrences)

**`ADR002_IMPLEMENTATION/THREAT_MODEL.md`**
- **Strategy**: Add editorial note, update code examples, preserve threat descriptions using original terminology
- T4 threat references "Classification Mislabeling" - keep for historical accuracy
- Code examples: Update to `SecureDataFrame`

**`ADR002_IMPLEMENTATION/CERTIFICATION_EVIDENCE.md`**
- **Strategy**: Keep as-is (historical certification record)
- Add note: "Certification completed using 'classified' terminology, implementation updated to 'secure' for broader applicability"

**`ADR002_IMPLEMENTATION/ADR002A_PLAN.md`**
- **Strategy**: Keep as-is (historical planning document)

---

## Detailed Renaming Map

### Python Class & Method Names

| Category | Before | After | Files Affected |
|----------|--------|-------|----------------|
| **Core Class** | `ClassifiedDataFrame` | `SecureDataFrame` | 14 source, 14 test |
| **Generic Wrapper** | `ClassifiedData[T]` | `SecureData[T]` | TBD (new in ADR-004) |
| **Field Name** | `.classification` | `.security_level` | 14 source, 14 test |
| **Factory Method** | `create_from_datasource(..., classification)` | `create_from_datasource(..., security_level)` | 4 datasources |
| **Uplift Method** | `with_uplifted_classification(level)` | `with_uplifted_security_level(level)` | 14 source, 14 test |
| **Middleware Class** | `ClassifiedMaterialMiddleware` | `SensitiveMaterialMiddleware` | 1 middleware |
| **Middleware Name** | `"classified_material"` | `"sensitive_material"` | 1 middleware + configs |

### File Renames

| Category | Before | After | Risk |
|----------|--------|-------|------|
| **Core Module** | `classified_data.py` | `secure_data.py` | LOW |
| **Middleware** | `classified_material.py` | `sensitive_material.py` | MEDIUM (config refs) |
| **Test File** | `test_classified_material_middleware.py` | `test_sensitive_material_middleware.py` | LOW |
| **Test Data** | `classification_bypass.yaml` | `security_bypass.yaml` | LOW |
| **Test Data** | `classified_secrets.csv` | `sensitive_secrets.csv` | LOW |
| **ADR Docs** | KEEP as-is (historical record) | N/A | N/A |

### Variable Naming Patterns

| Before | After | Context |
|--------|-------|---------|
| `classified_df` | `secure_df` | Local variables |
| `classified_data` | `secure_data` | Local variables |
| `classification` | `security_level` | Field access |
| `uplifted_classification` | `uplifted_level` | Intermediate variables |
| `new_classification` | `new_security_level` | Parameter names |

### Documentation Terminology

| Before | After | Context |
|--------|-------|---------|
| "classification" (noun) | "security level" | Technical prose |
| "classified data" | "secure data" | Data references |
| "classification uplifting" | "security level uplifting" | Process descriptions |
| "classification mislabeling" | "security level mislabeling" | Threat descriptions |
| "classification laundering" | "security level laundering" | Attack scenarios |
| "classified material" | "sensitive material" | Content detection |

---

## Migration Strategy (3 Phases)

### Phase 1: Core Code (4-5 hours)

**Objective**: Rename core classes and fields in source code.

**Steps**:
1. **Rename core module** (30 min):
   - `classified_data.py` → `secure_data.py`
   - Update imports in `__init__.py`

2. **Rename ClassifiedDataFrame** (2 hours):
   - Class name: `ClassifiedDataFrame` → `SecureDataFrame`
   - Field: `classification` → `security_level`
   - Methods: `with_uplifted_classification()` → `with_uplifted_security_level()`
   - Docstrings: Update all references (~40 occurrences)
   - Run tests after each change

3. **Update imports across codebase** (1 hour):
   - Use IDE refactoring: "Find and Replace in Files"
   - Pattern: `from .classified_data import` → `from .secure_data import`
   - Pattern: `ClassifiedDataFrame` → `SecureDataFrame`
   - Verify with grep: `grep -r "ClassifiedDataFrame" src/`

4. **Update datasources** (30 min):
   - 4 files: `_csv_base.py`, `csv_local.py`, `csv_blob.py`, `blob.py`
   - Pattern: `classification=` → `security_level=` (parameter names)

5. **Update middleware** (1 hour):
   - Rename file: `classified_material.py` → `sensitive_material.py`
   - Rename class: `ClassifiedMaterialMiddleware` → `SensitiveMaterialMiddleware`
   - Update name field: `"classified_material"` → `"sensitive_material"`
   - Update imports in `__init__.py`
   - **CRITICAL**: Update config files referencing middleware

**Exit Criteria**:
- ✅ All source files renamed
- ✅ All imports updated
- ✅ MyPy clean
- ✅ Ruff clean
- ❌ Tests NOT yet updated (will fail)

---

### Phase 2: Tests & Test Data (3-4 hours)

**Objective**: Update all test code and test data files.

**Steps**:
1. **Rename test files** (15 min):
   - `test_classified_material_middleware.py` → `test_sensitive_material_middleware.py`
   - `classification_bypass.yaml` → `security_bypass.yaml`
   - `classified_secrets.csv` → `sensitive_secrets.csv`

2. **Update test code** (2.5 hours):
   - 14 test files with 307 occurrences
   - Pattern: `ClassifiedDataFrame` → `SecureDataFrame`
   - Pattern: `.classification` → `.security_level`
   - Pattern: `classified_df` → `secure_df` (variable names)
   - Pattern: `with_uplifted_classification` → `with_uplifted_security_level`
   - Use IDE refactoring for speed

3. **Update test docstrings** (30 min):
   - Test function names can stay as-is (descriptive)
   - Update docstrings and comments: "classification" → "security level"

4. **Run full test suite** (30 min):
   - `python -m pytest tests/ -v`
   - Fix any remaining references
   - Verify 100% pass rate

**Exit Criteria**:
- ✅ All test files updated
- ✅ All test data files renamed
- ✅ Full test suite passing (100%)
- ✅ No references to old terminology in code/tests

---

### Phase 3: Documentation (4-6 hours)

**Objective**: Update documentation with editorial strategy.

**Steps**:

1. **Update Plugin Development Guide** (1 hour):
   - `docs/guides/plugin-development-adr002a.md` (69 occurrences)
   - Full update - this is current documentation
   - All code examples use new terminology
   - All prose uses "secure data" / "security level"

2. **Update Architecture Docs** (1.5 hours):
   - ~15 files, ~200 occurrences
   - Pattern: "classified data" → "secure data"
   - Pattern: "classification uplifting" → "security level uplifting"
   - Update all code examples
   - Update diagrams if any reference terminology

3. **Update Examples & Guides** (1 hour):
   - ~10 files, ~100 occurrences
   - Full update - examples should reflect current API
   - All code samples use `SecureDataFrame`

4. **Update Migration Planning Docs** (1 hour):
   - `docs/migration/adr-003-004-classified-containers/` (5 files, ~300 occurrences)
   - Full update before ADR-003/004 execution
   - Rename folder: → `adr-003-004-secure-containers/`

5. **Add Editorial Notes to ADRs** (30 min):
   - `docs/architecture/decisions/002-a-trusted-container-model.md`
   - `docs/security/adr-002-classified-dataframe-hardening-delta.md`
   - `docs/security/adr-002-orchestrator-security-model.md`
   - Add at top:
     ```markdown
     > **Editorial Note (2025-10-25)**: Original design used "classified data"
     > terminology for government context. Implementation uses "secure data"
     > for universal applicability. Technical content updated to reflect
     > implementation; historical context preserved in Decision/Context sections.
     ```

6. **Compliance Docs - Selective Update** (30 min):
   - `docs/compliance/AUSTRALIAN_GOVERNMENT_CONTROLS.md`
   - Keep references to actual government classification requirements
   - Update only code examples to use `SecureDataFrame`

7. **Verification** (30 min):
   - Grep for remaining "classified" references: `grep -r "classified" docs/ | grep -v "archive" | wc -l`
   - Review each remaining occurrence - should only be in historical/compliance contexts
   - Verify all code examples use new terminology

**Exit Criteria**:
- ✅ All current documentation updated
- ✅ ADRs have editorial notes
- ✅ Compliance docs preserve government terminology
- ✅ All code examples use new API
- ⭕ Historical/archive docs unchanged (intentional)

---

## Risk Assessment

### Critical Risks (Mitigation Required)

**Risk 1: Breaking Middleware Configurations** (MEDIUM RISK - Pre-1.0 Acceptable)
- **Impact**: Configs referencing `classified_material` middleware will fail
- **Affected**: Sample suite configs, any user configs
- **Mitigation** (Pre-1.0 Fail-Fast):
  1. Update all in-tree configs (`config/sample_suite/**/*.yaml`)
  2. **No auto-mapping** - configs must use new name `sensitive_material`
  3. Document migration in CHANGELOG as breaking change
- **Approach**: **Fail-fast** - old names → clear error message pointing to migration guide

**Risk 2: Import Errors from Module Rename** (LOW RISK - Pre-1.0 Acceptable)
- **Impact**: Any code importing `from elspeth.core.security.classified_data` will break
- **Mitigation** (Pre-1.0 Fail-Fast):
  1. **No shims** - remove old module entirely
  2. Update all in-tree imports
  3. Document migration in CHANGELOG
- **Approach**: **Fail-fast** - `ImportError` with clear message: "ClassifiedDataFrame renamed to SecureDataFrame in v0.X"

**Risk 3: Documentation Inconsistency** (LOW RISK)
- **Impact**: Users see "classified" in old docs, "secure" in new code
- **Mitigation**:
  1. Update all user-facing docs (guides, examples)
  2. Add editorial notes to ADRs explaining historical terminology
  3. Create migration guide in CHANGELOG
- **Approach**: Documentation-only risk, no code changes needed

### Minor Risks (Acceptable for Pre-1.0)

**Risk 4: Search/Discovery Impact** (VERY LOW RISK)
- **Impact**: Users searching for "classified data" won't find docs
- **Mitigation**: Keep "classified" in historical docs (compliance docs, ADRs) with editorial notes
- **Approach**: Pre-1.0 accepts this risk

**Risk 5: External References** (NOT APPLICABLE)
- **Impact**: N/A - Pre-1.0 has no external documentation
- **Approach**: Not a concern for pre-1.0 software

---

## Effort Breakdown

| Phase | Hours | Complexity | Parallelizable |
|-------|-------|------------|----------------|
| **Phase 1: Core Code** | 4-5 | LOW | No |
| **Phase 2: Tests** | 3-4 | LOW | Yes (with Phase 1 done) |
| **Phase 3: Documentation** | 4-6 | MEDIUM | Yes (with Phase 1-2 done) |
| **Verification** | 1 | LOW | No |
| **TOTAL** | **12-16 hours** | **LOW-MEDIUM** | Phases 2-3 can partially overlap |

**Conservative Estimate**: 14-16 hours (accounting for config updates, testing, verification)

---

## Success Criteria

### Must-Have (Blocking)

- ✅ All source code uses `SecureDataFrame` / `SecureData[T]`
- ✅ All field names use `security_level` (aligned with existing codebase)
- ✅ All method names updated (`with_uplifted_security_level`)
- ✅ All tests passing (100%)
- ✅ MyPy clean, Ruff clean
- ✅ **No "ClassifiedDataFrame" references in code** (clean removal, no shims)
- ✅ Sample suite runs successfully with new terminology

### Should-Have (Quality)

- ✅ All current documentation updated (guides, architecture, examples)
- ✅ ADRs have editorial notes explaining terminology change
- ✅ Config files updated for middleware rename
- ✅ Migration guide in CHANGELOG documenting breaking changes

### Not Applicable (Pre-1.0)

- ❌ ~~Deprecation warnings~~ - Pre-1.0 clean cut-over
- ❌ ~~Backward compatibility shims~~ - Not needed pre-1.0
- ❌ ~~External documentation~~ - No external docs yet

---

## Coordination with ADR-003/004 Migration

### Sequencing Options

**Option A: Rename BEFORE ADR-003/004 Migration** (RECOMMENDED)
- **Pros**:
  - ADR-003/004 docs use correct terminology from start
  - Cleaner migration (no need to rename during migration)
  - One-time terminology change, then move forward
- **Cons**:
  - Additional branch to manage
  - Delays ADR-003/004 start by ~2 days
- **Effort**: 14-16 hours

**Option B: Rename DURING ADR-003/004 Migration**
- **Pros**:
  - Combined effort, single PR
  - No intermediate branch
- **Cons**:
  - More complex PR review
  - Terminology confusion during migration
  - Migration docs need immediate update
- **Effort**: 14-16 hours + migration complexity

**Option C: Rename AFTER ADR-003/004 Migration**
- **Pros**:
  - Focus on functional migration first
  - Terminology change is simple cleanup afterward
- **Cons**:
  - Migration docs use old terminology
  - Two rounds of documentation updates
  - More total work (update docs twice)
- **Effort**: 14-16 hours + doc rework

### Recommendation: **Option A** (Rename First)

**Rationale**:
1. Clean separation of concerns
2. ADR-003/004 docs reference `SecureDataFrame` from the start
3. Simpler code review (terminology change is mechanical)
4. One-time terminology change across entire codebase

**Sequencing**:
1. ✅ Merge current branch (`feature/adr-002-security-enforcement`)
2. ⭕ Create rename branch (`refactor/terminology-secure-data`)
3. ⭕ Execute 3-phase rename (14-16 hours)
4. ⭕ Merge rename branch
5. ⭕ Update ADR-003/004 migration docs to use `SecureDataFrame`
6. ⭕ Create ADR-003/004 migration branch
7. ⭕ Execute ADR-003/004 migration using new terminology

---

## Tools & Automation

### IDE Refactoring

**Recommended**: Use IDE refactoring tools for speed and accuracy

**PyCharm / VS Code**:
1. "Rename Symbol" for class/method names
2. "Find and Replace in Files" for terminology in strings/docs
3. "Move/Rename File" for module renames

**Patterns for Find/Replace**:
```regex
# Code
ClassifiedDataFrame → SecureDataFrame
ClassifiedData\[ → SecureData[
\.classification → .security_level
with_uplifted_classification → with_uplifted_security_level

# Variables (more selective)
classified_df → secure_df
classified_data → secure_data

# Documentation
classified data → secure data
classification uplifting → security level uplifting
classification mislabeling → security level mislabeling
```

### Automated Verification

**Post-rename checks**:
```bash
# No old class names in source (except deprecation shims)
grep -r "ClassifiedDataFrame" src/ | grep -v "__init__.py" | wc -l
# Should be 0

# No old module references
grep -r "classified_data" src/ | grep "import" | wc -l
# Should be 0 (except __init__.py shim)

# All tests pass
python -m pytest tests/ -v
# Should be 100%

# Type checking clean
python -m mypy src/elspeth
# Should have no errors

# Linting clean
python -m ruff check src tests
# Should have no errors
```

---

## Breaking Changes

### User-Facing Breaking Changes (Pre-1.0 Clean Cut-Over)

**Python API** (Immediate Breaking Changes):
- ❌ `ClassifiedDataFrame` → ✅ `SecureDataFrame` (**No shim - ImportError**)
- ❌ `from elspeth.core.security.classified_data` → ✅ `from elspeth.core.security.secure_data` (**Module removed**)
- ❌ `.classification` → ✅ `.security_level` (**AttributeError**)
- ❌ `with_uplifted_classification()` → ✅ `with_uplifted_security_level()` (**AttributeError**)

**Config Files** (Immediate Breaking Changes):
- ❌ `classified_material` middleware → ✅ `sensitive_material` (**No auto-mapping - ConfigError**)

**Documentation**:
- Terminology change throughout guides and examples
- ADRs retain historical context with editorial notes
- CHANGELOG documents all breaking changes

### Migration Path (Pre-1.0 Fail-Fast)

**Approach**: **Fix-on-fail** - no backward compatibility

**Expected Errors**:
```python
# Old code will fail immediately with clear errors:

# ImportError:
from elspeth.core.security.classified_data import ClassifiedDataFrame
# → ImportError: No module named 'elspeth.core.security.classified_data'
#   See CHANGELOG for v0.X migration guide (ClassifiedDataFrame → SecureDataFrame)

# AttributeError:
secure_df.classification
# → AttributeError: 'SecureDataFrame' has no attribute 'classification'
#   Use .security_level instead (see CHANGELOG v0.X)
```

**Migration Steps**:
1. Update imports: `from elspeth.core.security.secure_data import SecureDataFrame`
2. Update field access: `.security_level` (not `.classification`)
3. Update method calls: `.with_uplifted_security_level()` (not `with_uplifted_classification()`)
4. Update configs: `sensitive_material` middleware (not `classified_material`)

**Timeline**: Single version (no gradual migration)
- **Version 0.X**: Breaking changes applied immediately
- **No deprecation period** - Pre-1.0 clean cut-over

---

## Next Steps

1. ⭕ **Review this assessment** with team
2. ⭕ **Approve terminology change** and sequencing (Option A recommended)
3. ⭕ **Merge ADR-002-A** (current branch)
4. ⭕ **Create rename branch** (`refactor/terminology-secure-data`)
5. ⭕ **Execute Phase 1** (Core code - 4-5 hours)
6. ⭕ **Execute Phase 2** (Tests - 3-4 hours)
7. ⭕ **Execute Phase 3** (Documentation - 4-6 hours)
8. ⭕ **Merge rename branch**
9. ⭕ **Update ADR-003/004 migration docs** to reference `SecureDataFrame`
10. ⭕ **Proceed with ADR-003/004 migration**

---

## Appendix: Terminology Comparison

### Current (Government-Specific)

| Term | Context | Connotation |
|------|---------|-------------|
| Classified Data | Government, military, intelligence | Formal, requires clearance |
| Classification | Government security levels | TOP SECRET, SECRET, CONFIDENTIAL |
| Classification Uplifting | Government data flow | Formal security process |
| Classified Material | Government documents | Requires special handling |

### Proposed (Universal)

| Term | Context | Connotation |
|------|---------|-------------|
| Secure Data | Enterprise, healthcare, finance, research | Professional, accessible |
| Security Level | Data sensitivity levels | HIGH, MEDIUM, LOW (or custom) |
| Security Level Uplifting | Data protection mechanism | Technical security process |
| Sensitive Material | Content requiring protection | General data protection |

### Industry Alignment

| Industry | Preferred Terminology | Alignment |
|----------|----------------------|-----------|
| **Healthcare** | PHI (Protected Health Information), Sensitive Data | ✅ "Secure" fits well |
| **Finance** | PII (Personally Identifiable Information), Confidential Data | ✅ "Secure" fits well |
| **Enterprise** | Confidential, Internal, Public | ✅ "Secure" fits well |
| **Research** | Sensitive Data, Restricted Data | ✅ "Secure" fits well |
| **Government** | Classified, TOP SECRET, SECRET | ⭕ "Classified" more specific, but "Secure" acceptable |

**Conclusion**: "Secure" terminology has broader industry applicability while remaining acceptable in government contexts.

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

**Assessment Date**: 2025-10-25
**Confidence**: VERY HIGH (mechanical rename, comprehensive analysis)
**Recommendation**: **APPROVE** - Execute before ADR-003/004 migration
