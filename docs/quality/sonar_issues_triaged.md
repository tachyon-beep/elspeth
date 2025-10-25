# SonarQube Issues Triage Report
**Generated:** 2025-10-23
**Last Updated:** 2025-10-24
**Project:** tachyon-beep_elspeth
**Total Issues Found:** 295 (118 OPEN, 177 CLOSED)

## 🎯 Progress Tracker

| Phase | Status | Completed | Remaining |
|-------|--------|-----------|-----------|
| **Phase 1: Quick Wins** | 🔴 Not Started | 0/22 | 22 items |
| **Phase 2: Critical Complexity** | 🟡 In Progress | ✅ 2/12 (16.7%) | 10 functions |
| **Phase 3: Modernization** | 🔴 Not Started | 0/? | TBD |
| **Phase 4: Moderate Complexity** | 🔴 Not Started | 0/37 | 37 functions |

### Recent Completions
- ✅ **2025-10-24** - `runner.py::run_experiment` refactored (73 → 11 complexity) - PR #10
- ✅ **2025-10-24** - `runner.py::_run_row_processing` extracted into helpers - PR #10

---

## 🔴 CRITICAL MUST-DO (High Priority)

### 1. Extreme Cognitive Complexity (Complexity > 40)
**Impact:** Very difficult to maintain, test, and debug. High risk of bugs.

| File | Function | Line | Complexity | Severity | Status |
|------|----------|------|------------|----------|--------|
| `src/elspeth/core/experiments/suite_runner.py` | `run_suite` | 281 | **69** | CRITICAL | 🔴 TODO |
| `src/elspeth/core/experiments/runner.py` | `run_experiment` | 75 | ~~**73**~~ → **11** | ~~CRITICAL~~ ✅ | ✅ **DONE** (PR #10) |
| `src/elspeth/core/experiments/runner.py` | `_run_row_processing` | 557 | ~~**45**~~ → *extracted* | ~~CRITICAL~~ ✅ | ✅ **DONE** (PR #10) |
| `src/elspeth/plugins/nodes/sinks/visual_report.py` | `_generate_visualizations` | 216 | **63** | CRITICAL | 🔴 TODO |
| `src/elspeth/plugins/nodes/sinks/zip_bundle.py` | `execute` | 80 | **54** | CRITICAL | 🔴 TODO |
| `src/elspeth/plugins/nodes/transforms/llm/middleware/pii_shield.py` | `_apply_masking` | 474 | **56** | CRITICAL | 🔴 TODO |
| `src/elspeth/plugins/nodes/transforms/llm/middleware/classified_material.py` | `_detect_patterns` | 379 | **41** | CRITICAL | 🔴 TODO |
| `src/elspeth/plugins/experiments/baseline/score_significance.py` | `aggregate` | 73 | **51** | CRITICAL | 🔴 TODO |
| `src/elspeth/plugins/experiments/aggregators/score_agreement.py` | `aggregate` | 53 | **43** | CRITICAL | 🔴 TODO |
| `src/elspeth/plugins/experiments/_stats_helpers.py` | `_run_bayesian_analysis` | 123 | **42** | CRITICAL | 🔴 TODO |
| `src/elspeth/core/pipeline/artifact_pipeline.py` | `_resolve_dependencies` | 335 | **45** | CRITICAL | 🔴 TODO |
| `src/elspeth/core/config/validation.py` | `validate_experiment_config` | 142 | **59** | CRITICAL | 🔴 TODO |

**Recommendation:** These ~~12~~ **10** functions need immediate refactoring. Extract helper functions, use early returns, and break into smaller units.

**✅ Completed (2/12):**
- `runner.py::run_experiment` - Reduced from 73 to 11 complexity (85% reduction) - See PR #10
- `runner.py::_run_row_processing` - Extracted into focused helpers - See PR #10

---

### 2. High Cognitive Complexity (Complexity 30-40)
**Impact:** Hard to maintain and error-prone.

| File | Function | Line | Complexity |
|------|----------|------|------------|
| `src/elspeth/core/experiments/suite_runner.py` | `_prepare_experiments` | 47 | 33 |
| `src/elspeth/core/experiments/validation.py` | `validate_suite_settings` | 10 | 30 |
| `src/elspeth/core/cli/validate.py` | `validate_command` | 16 | 30 |
| `src/elspeth/core/utils/logging.py` | `_format_log_entry` | 108 | 39 |
| `src/elspeth/core/registries/plugin_helpers.py` | `create_plugin_instance` | 34 | 32 |
| `src/elspeth/core/security/approved_endpoints.py` | `validate_endpoint` | 190 | 29 |
| `src/elspeth/core/config/validation.py` | `_validate_prompt_config` | 26 | 27 |
| `src/elspeth/plugins/nodes/sinks/enhanced_visual_report.py` | `_create_charts` | 185 | 34 |
| `src/elspeth/plugins/nodes/sinks/enhanced_visual_report.py` | `_generate_summary` | 71 | 28 |
| `src/elspeth/plugins/nodes/sinks/visual_report.py` | `execute` | 53 | 29 |
| `src/elspeth/plugins/experiments/baseline/referee_alignment.py` | `aggregate` | 86 | 31 |
| `src/elspeth/plugins/experiments/baseline/score_flip_analysis.py` | `aggregate` | 71 | 30 |
| `src/elspeth/retrieval/service.py` | `search` | 57 | 31 |

**Recommendation:** Refactor before adding new features to these areas.

---

### 3. Too Many Parameters (S107)
**Impact:** Functions are hard to use and prone to argument errors.

| File | Function | Line | Param Count |
|------|----------|------|-------------|
| `src/elspeth/plugins/nodes/sinks/embeddings_store.py` | `__init__` | 235-250 | **14** |
| `src/elspeth/plugins/nodes/sinks/blob.py` | `__init__` | 38-53 | **14** |

**Recommendation:** Use configuration objects or dataclasses instead of 14 individual parameters.

---

### 4. Issue Suppression Syntax Errors (S7632)
**Impact:** Suppression comments don't work, issues aren't actually suppressed.

| File | Line |
|------|------|
| `src/elspeth/plugins/experiments/validation.py` | 98 |
| `src/elspeth/plugins/experiments/validation.py` | 99 |

**Recommendation:** Fix immediately - these are probably trying to suppress false positives.

---

## 🟡 NICE-TO-HAVE (Medium Priority)

### 5. Moderate Cognitive Complexity (Complexity 20-29)
**Count:** 37 functions
**Recommendation:** Address when working in these areas.

Sample high-value targets:
- `src/elspeth/core/experiments/runner.py::run_aggregation` (26)
- `src/elspeth/core/experiments/runner.py::_handle_retries` (21)
- `src/elspeth/core/cli/common.py::_merge_configs` (23)
- `src/elspeth/plugins/nodes/sinks/analytics_report.py::execute` (21)
- `src/elspeth/plugins/nodes/sinks/reproducibility_bundle.py::execute` (21)
- `src/elspeth/plugins/nodes/sinks/excel.py::execute` (23)
- `src/elspeth/plugins/nodes/sinks/local_bundle.py::execute` (27)
- `src/elspeth/plugins/nodes/sinks/zip_bundle.py::_sanitize_entries` (25)
- `src/elspeth/plugins/nodes/sinks/embeddings_store.py::execute` (24)
- `src/elspeth/plugins/nodes/sinks/embeddings_store.py::_store_to_azure` (21)
- `src/elspeth/plugins/nodes/sinks/blob.py::execute` (22)
- `src/elspeth/plugins/nodes/sinks/signed.py::execute` (39)
- `src/elspeth/plugins/nodes/transforms/llm/middleware_azure.py::process_request` (18)
- `src/elspeth/plugins/experiments/prompt_variants.py::prepare` (23)
- `src/elspeth/plugins/experiments/_stats_helpers.py` - multiple functions
- `src/elspeth/retrieval/providers.py` - multiple functions

---

### 6. Old-Style Generics (S6792, S6796) - Python 3.12 Syntax
**Impact:** Not using modern Python type syntax (PEP 695).

| File | Line | Issue |
|------|------|-------|
| `src/elspeth/core/registries/base.py` | 27 | Use `type` parameter syntax for generic class |
| `src/elspeth/core/registries/base.py` | 104 | Use generic type parameter instead of TypeVar |
| `src/elspeth/core/registries/base.py` | 148 | Use `type` parameter syntax for generic class |
| `src/elspeth/core/registries/base.py` | 261 | Use generic type parameter instead of TypeVar |

**Example Fix:**
```python
# Old style
T = TypeVar('T')
class Registry(Generic[T]):
    pass

# New Python 3.12 style
class Registry[T]:
    pass
```

**Recommendation:** Modernize when touching these files. Not urgent but good for consistency.

---

### 7. Empty Code Blocks (S108)
**Impact:** Incomplete implementation or missing documentation.

**Count:** 11 instances in baseline experiment plugins
**Files:**
- `src/elspeth/plugins/experiments/baseline/*.py` - multiple files

**Recommendation:** Add TODO comments or implement the empty `prepare()` methods.

---

### 8. Nested If Statement Merging (S1066)
**Impact:** Minor readability improvement.

| File | Line |
|------|------|
| `src/elspeth/core/security/secure_mode.py` | 167 |

**Recommendation:** Merge when touching this code.

---

### 9. Return Type Hints (S5886)
**Impact:** Type safety improvement.

| File | Line | Issue |
|------|------|-------|
| `src/elspeth/core/base/protocols.py` | 168-173 | Return `LLMRequest` instead of `DataclassInstance` |

**Recommendation:** Improve type hints for better IDE support and type checking.

---

## 🟢 QUICK WINS (Easy Fixes)

### 10. Redundant Exception Catching (S5713)
**Count:** 11 instances
**Severity:** MINOR
**Effort:** 2 minutes each

| File | Line |
|------|------|
| `src/elspeth/core/cli/common.py` | 154 |
| `src/elspeth/plugins/nodes/sinks/analytics_report.py` | 83 |
| `src/elspeth/plugins/nodes/sinks/csv_file.py` | 171 |
| `src/elspeth/plugins/nodes/sinks/file_copy.py` | 101 |
| `src/elspeth/plugins/nodes/sinks/signed.py` | 106 |
| `src/elspeth/plugins/nodes/sinks/visual_report.py` | 145 |
| `src/elspeth/plugins/nodes/sources/_csv_base.py` | 132 |
| `src/elspeth/plugins/nodes/sources/_csv_base.py` | 246 |

**Example Fix:**
```python
# Before
try:
    something()
except (ValueError, Exception) as e:  # ValueError is redundant
    pass

# After
try:
    something()
except Exception as e:
    pass
```

**Recommendation:** Fix all in one PR. Search for the pattern.

---

### 11. Naming Convention Violations (S117)
**Count:** 4 instances
**Severity:** MINOR
**Effort:** 1 minute each

| File | Variable | Line |
|------|----------|------|
| `src/elspeth/plugins/experiments/_stats_helpers.py` | `De` | 425 |
| `src/elspeth/plugins/experiments/_stats_helpers.py` | `Do` | 449 |
| `src/elspeth/plugins/experiments/_stats_helpers.py` | `De` | 477 |
| `src/elspeth/plugins/experiments/_stats_helpers.py` | `Do` | 500 |

**Fix:** Rename to `d_e` and `d_o` (snake_case).

**Recommendation:** Quick find-and-replace in one file.

---

### 12. Unused Variables (S1481)
**Count:** 2 instances
**Severity:** MINOR
**Effort:** 30 seconds each

| File | Variable | Line |
|------|----------|------|
| `src/elspeth/plugins/experiments/_stats_helpers.py` | `unique` | 474 |

**Fix:** Replace `unique` with `_` to indicate intentionally unused.

**Recommendation:** One-line fixes.

---

### 13. Regex Simplification (S6353)
**Count:** 1 instance
**Severity:** MINOR
**Effort:** 30 seconds

| File | Line |
|------|------|
| `src/elspeth/core/prompts/engine.py` | 15 |

**Fix:** Replace `[a-zA-Z0-9_]` with `\w`.

**Recommendation:** Trivial improvement.

---

### 14. String Literal Duplication (S1192)
**Count:** 1 instance
**Severity:** CRITICAL (but trivial to fix)
**Effort:** 2 minutes

| File | Literal | Count | Line |
|------|---------|-------|------|
| `src/elspeth/plugins/nodes/sinks/analytics_report.py` | `"```json"` | 4 | 177 |

**Fix:**
```python
JSON_CODE_BLOCK = "```json"
# Use JSON_CODE_BLOCK throughout
```

**Recommendation:** Define constant at module level.

---

### 15. Unused Function Parameters (S1172)
**Count:** 1 instance
**Severity:** MAJOR
**Effort:** 1 minute

| File | Parameter | Line |
|------|-----------|------|
| `src/elspeth/plugins/experiments/baseline/score_distribution.py` | `records` | 50 |

**Fix:** Remove parameter or prefix with `_` if required by interface.

**Recommendation:** Check if this is part of a protocol/ABC.

---

## 📊 Summary Statistics

| Category | Count | Completed | Remaining | Total Effort Est. |
|----------|-------|-----------|-----------|-------------------|
| **Critical Must-Do** | 12 functions | ✅ 2 | 🔴 10 | ~~40-80 hours~~ → 30-65 hours |
| **Nice-to-Have** | 50+ items | - | 50+ | 20-40 hours |
| **Quick Wins** | 19 items | - | 19 | 30 minutes |

**Progress:** 2/12 critical complexity functions refactored (16.7% complete)

### By Severity (OPEN issues only)
- CRITICAL: 88 issues
- MAJOR: 20 issues
- MINOR: 10 issues

### By Rule Type (Top Issues)
1. **S3776** (Cognitive Complexity): 75 issues
2. **S5713** (Redundant Exception): 8 issues
3. **S6792/S6796** (Generic Type Syntax): 4 issues
4. **S117** (Naming Convention): 4 issues
5. **S108** (Empty Blocks): 11 issues

---

## 🎯 Recommended Action Plan

### Phase 1: Quick Wins (1 hour)
1. ✅ Fix all redundant exception catching (S5713) - 11 fixes
2. ✅ Fix naming conventions (S117) - 4 fixes
3. ✅ Fix unused variables (S1481) - 2 fixes
4. ✅ Fix regex simplification (S6353) - 1 fix
5. ✅ Fix string duplication (S1192) - 1 fix
6. ✅ Fix issue suppression syntax (S7632) - 2 fixes
7. ✅ Fix unused parameters (S1172) - 1 fix

**Result:** 22 issues closed in ~1 hour

---

### Phase 2: Critical Complexity Reduction (2-3 sprints)
Priority order by risk/impact:

1. **Suite Runner** (`suite_runner.py:281`, complexity 69) 🔴 TODO
   - Most critical orchestration code
   - High risk of bugs

2. ~~**Experiment Runner**~~ ✅ **DONE** (PR #10)
   - ~~`runner.py:75`, complexity 73~~ → **Reduced to 11**
   - ~~Core execution engine~~ → **Refactored using Template Method pattern**
   - ~~Hardest to test~~ → **13 characterization tests added, 75% coverage**
   - **Achievement:** 85% complexity reduction, 15 helper methods extracted

3. **Config Validation** (`validation.py:142`, complexity 59) 🔴 TODO
   - Security-critical
   - Complex validation logic

4. **Artifact Pipeline** (`artifact_pipeline.py:335`, complexity 45) 🔴 TODO
   - DAG resolution is complex
   - Affects all sinks

5. **Visual Reports** (`visual_report.py:216`, complexity 63) 🔴 TODO
   - Less critical, but still complex

6. **PII Shield** (`pii_shield.py:474`, complexity 56) 🔴 TODO
   - Security-critical
   - Pattern matching complexity

---

### Phase 3: Modernization (Low Priority)
1. Update generic type syntax to Python 3.12 style (S6792, S6796)
2. Fill empty blocks in baseline experiments (S108)
3. Reduce parameter counts (S107) using config objects

---

### Phase 4: Moderate Complexity (Ongoing)
- Address complexity 20-29 functions when touching the code
- No dedicated sprint needed
- Improve gradually during feature work

---

## 💡 Insights

1. **Complexity Hotspots:** The experiment runner (`runner.py`) and suite runner (`suite_runner.py`) are the most complex parts of the system. These are prime candidates for refactoring.

2. **Sink Complexity:** Many sinks (`visual_report`, `zip_bundle`, `signed`, `local_bundle`) have high complexity. Consider extracting common patterns into base classes or helper functions.

3. **Statistical Helpers:** `_stats_helpers.py` has multiple complex functions. This suggests the statistical analysis logic could benefit from better decomposition.

4. **Quick Wins Available:** 22 trivial issues can be fixed in ~1 hour, immediately improving code quality metrics.

5. **Security-Critical:** Both `pii_shield.py` and `classified_material.py` have high complexity. These security-critical components should be prioritized for refactoring.

---

## 🔧 Tools & Techniques for Refactoring

### For Cognitive Complexity:
1. **Extract Method:** Move nested logic into separate functions
2. **Early Returns:** Reduce nesting with guard clauses
3. **Strategy Pattern:** Replace complex conditionals with polymorphism
4. **State Machines:** For complex state transitions
5. **Builder Pattern:** For complex object construction

### Example Refactoring:
```python
# Before (complexity 30+)
def complex_function(data):
    if condition1:
        if condition2:
            for item in items:
                if item.valid:
                    result = process(item)
                    if result:
                        # ... more nesting
                        pass

# After (complexity < 15)
def complex_function(data):
    if not condition1:
        return default_value
    if not condition2:
        return default_value

    return process_items(items)

def process_items(items):
    valid_items = [i for i in items if i.valid]
    return [process_single_item(i) for i in valid_items]

def process_single_item(item):
    result = process(item)
    if not result:
        return None
    return handle_result(result)
```

---

**Generated with ❤️ by Claude Code**
