# Phase 1: Audit & Documentation Methodology

**Objective**: Comprehensive analysis of test suite quality, duplication, and organization WITHOUT moving files

**Estimated Effort**: 6-8 hours (with implemented automation scripts)
**Prerequisites**:
- **Phase 0 complete** (existing subdirectories consolidated)
- Test suite stable, all tests passing or properly xfailed
**Deliverables**: 4 analysis documents

---

## Overview

Phase 1 builds a complete understanding of the test suite's current state through automated analysis. This phase produces **actionable data** for Phases 2 and 3, ensuring reorganization and deduplication are evidence-based.

### Success Criteria

- ✅ All test files analyzed (~175-185 files post-Phase 0)
- ✅ Duplicate detection complete (exact, functional, overlapping)
- ✅ Fixture analysis complete (see `03-FIXTURE_STRATEGY.md` and `analyze_fixtures.py`)
- ✅ Value assessment identifies low-ROI tests
- ✅ Proposed structure finalized with file mappings
- ✅ Stakeholders review and approve findings

---

## Step 1.1: Automated Metadata Analysis (1.5 hours)

### Objective

Extract comprehensive metadata from all test files to understand distribution, complexity, dependencies, and fixture usage.

### Implementation

**Script**: ✅ **IMPLEMENTED** - `docs/migration/test-suite-reorganization/audit_tests.py` (see `TOOLS.md` for usage)

**Data to Extract**:
1. **Per-File Metrics**:
   - Test function count (`def test_*`, `class Test*`)
   - Lines of code (LOC)
   - Import statements (dependencies)
   - Fixture usage (from conftest, local)
   - Pytest markers (`@pytest.mark.slow`, `@pytest.mark.integration`)
   - Docstring coverage

2. **Per-Test Metrics**:
   - Test function name
   - Parametrization count
   - Assertion count
   - External dependencies (mocks, fixtures)

3. **Coverage Analysis** (if available):
   - Code coverage per test file
   - Overlapping coverage (multiple tests hitting same code)

### Execution

```bash
# Run audit script (will be copied to scripts/ during execution)
python docs/migration/test-suite-reorganization/audit_tests.py \
    --test-dir tests \
    --output docs/migration/test-suite-reorganization/TEST_AUDIT_REPORT.md \
    --format markdown

# Verify output
cat docs/migration/test-suite-reorganization/TEST_AUDIT_REPORT.md | grep "Total test files"

# Also run fixture analysis
python docs/migration/test-suite-reorganization/analyze_fixtures.py \
    --test-dir tests \
    --output docs/migration/test-suite-reorganization/FIXTURE_ANALYSIS.md
```

### Output Format

**`TEST_AUDIT_REPORT.md`** (~500 lines):

```markdown
# Test Suite Audit Report

**Generated**: 2025-10-26
**Total Files**: 218
**Total Tests**: ~1,500 (TBD)
**Total LOC**: ~29,498

## Summary Statistics

| Metric | Value |
|--------|-------|
| Files in root | 136 |
| Average tests per file | 7.5 |
| Median file size (LOC) | 180 |
| Largest file | test_experiment_metrics_plugins.py (1,342 LOC) |
| Tests with no assertions | 12 |
| Tests with >100 LOC | 8 |

## Files by Size (Top 20)

| File | LOC | Tests | Tests/LOC Ratio |
|------|-----|-------|-----------------|
| test_experiment_metrics_plugins.py | 1,342 | 45 | 0.034 |
| test_adr002_baseplugin_compliance.py | 967 | 22 | 0.023 |
| ... | ... | ... | ... |

## Files by Test Count (Top 20)

...

## Fixture Usage Analysis

| Fixture | Used By (Files) | Total Uses |
|---------|-----------------|------------|
| tmp_path | 98 | 234 |
| assert_sanitized_artifact | 15 | 47 |
| ... | ... | ... |

## Marker Distribution

| Marker | Test Count |
|--------|------------|
| @pytest.mark.slow | 42 |
| @pytest.mark.integration | 87 |
| (unmarked) | 1,371 |

## Import Dependency Graph

Top 10 most imported modules:
1. elspeth.core.base.types (imported by 89 files)
2. elspeth.plugins.nodes.sinks.csv_file (imported by 12 files)
...

## Recommendations

- Files >800 LOC should be split
- Tests with 0 assertions should be reviewed
- Heavy fixture dependencies may indicate integration tests
```

---

## Step 1.2: Duplication Detection (1.5 hours)

### Objective

Identify redundant tests through three detection strategies: **exact**, **functional**, and **overlapping coverage**.

### Duplication Types

#### 1. Exact Duplicates
**Definition**: Identical test logic in multiple files (copy-paste)

**Detection**:
- AST-based structural comparison
- Normalized code comparison (ignoring whitespace, comments)
- Same assertions, same setup

**Example**:
```python
# tests/test_outputs_csv.py
def test_csv_sink_writes(tmp_path):
    sink = CsvResultSink(path=tmp_path / "out.csv")
    sink.write({"results": [...]})
    assert (tmp_path / "out.csv").exists()

# tests/test_csv_sink_path_guard.py
def test_csv_sink_writes_under_allowed_base(tmp_path):
    sink = CsvResultSink(path=tmp_path / "outputs" / "out.csv")
    sink.write({"results": [...]})
    assert (tmp_path / "outputs" / "out.csv").exists()
```
**Verdict**: Functional duplicate (same behavior, minor path difference)

#### 2. Functional Duplicates
**Definition**: Different code, same assertions and coverage

**Detection**:
- Compare assertion targets
- Compare code coverage paths
- Similarity >85% → flag as duplicate

**Example**:
```python
# File A
def test_cost_summary_on_error_skip():
    aggregator = CostSummaryAggregator(on_error="skip")
    result = aggregator.aggregate([...])
    assert result["status"] == "partial_success"

# File B (different file, same test name!)
def test_cost_summary_on_error_skip():
    plugin = CostSummaryAggregator(on_error="skip")
    output = plugin.aggregate([...])
    assert output["status"] == "partial_success"
```
**Verdict**: Exact duplicate (same test in 2 files)

#### 3. Overlapping Coverage
**Definition**: Multiple tests exercise same code paths with >80% overlap

**Detection**:
- Run `pytest --cov --cov-report=json`
- Parse coverage JSON to map tests → covered lines
- Identify tests with >80% overlap
- Flag for consolidation via parametrization

**Example**:
```python
# Current: 3 separate tests
def test_csv_sink_writes(): ...
def test_excel_sink_writes(): ...
def test_json_sink_writes(): ...

# Proposed: Single parametrized test
@pytest.mark.parametrize("sink_class,ext", [
    (CsvResultSink, ".csv"),
    (ExcelResultSink, ".xlsx"),
    (JsonResultSink, ".json"),
])
def test_sink_writes_successfully(sink_class, ext, tmp_path):
    sink = sink_class(path=tmp_path / f"out{ext}")
    sink.write({"results": [...]})
    assert (tmp_path / f"out{ext}").exists()
```

### Implementation

**Script**: ✅ **IMPLEMENTED** - `docs/migration/test-suite-reorganization/find_duplicates.py` (see `TOOLS.md` for usage)

**Execution**:
```bash
# Run duplication detection (will be copied to scripts/ during execution)
python docs/migration/test-suite-reorganization/find_duplicates.py \
    --test-dir tests \
    --output docs/migration/test-suite-reorganization/DUPLICATES_ANALYSIS.md \
    --threshold 0.85

# Preview findings
grep "DUPLICATE" docs/migration/test-suite-reorganization/DUPLICATES_ANALYSIS.md | wc -l
```

### Output Format

**`DUPLICATES_ANALYSIS.md`** (~200 lines):

```markdown
# Test Duplication Analysis

**Generated**: 2025-10-26
**Exact Duplicates Found**: 5 test names
**Functional Duplicates**: 12 test pairs
**Overlapping Coverage**: 18 test groups

---

## Exact Duplicates (Same Test Name in Multiple Files)

### 1. `cost_summary_on_error_skip`
**Files**:
- `tests/test_aggregators_cost_summary.py:45`
- `tests/test_experiment_metrics_plugins.py:234`

**Recommendation**: DELETE one, keep in test_aggregators_cost_summary.py

**Justification**: Identical test logic, same assertions

---

### 2. `invalid_on_error_raises`
**Files**:
- `tests/test_aggregators_cost_summary.py:67`
- `tests/test_aggregators_score_stats.py:89`

**Recommendation**: CONSOLIDATE via parametrization

**Justification**: Same pattern, different aggregators

---

## Functional Duplicates

### 1. CSV Path Guard Tests
**Files**:
- `tests/test_outputs_csv.py::test_csv_result_sink_writes`
- `tests/test_csv_sink_path_guard.py::test_csv_sink_writes_under_allowed_base`

**Similarity**: 87%
**Recommendation**: MERGE into single file, use parametrization for path scenarios

---

## Overlapping Coverage (>80% Code Path Overlap)

### Group 1: Sink Write Tests
**Tests**:
1. test_outputs_csv.py::test_csv_result_sink_writes (85 lines covered)
2. test_outputs_excel.py::test_excel_result_sink_writes (92 lines covered)
3. test_outputs_blob.py::test_blob_result_sink_writes (88 lines covered)

**Overlap**: 81 lines (95% overlap)
**Recommendation**: CONSOLIDATE via parametrization

**Proposed**:
```python
@pytest.mark.parametrize("sink_class,config", [
    (CsvResultSink, {"path": "out.csv"}),
    (ExcelResultSink, {"path": "out.xlsx"}),
    (BlobResultSink, {"account": "test", "container": "c"}),
])
def test_sink_writes_successfully(sink_class, config):
    ...
```

---

## Summary

- **Total redundancy**: ~18% of test suite (estimated 35-40 tests)
- **Deletion candidates**: 5-8 tests (exact duplicates)
- **Consolidation candidates**: 25-30 tests (parametrization)
- **Estimated LOC reduction**: 1,500-2,000 lines
```

---

## Step 1.3: Value Assessment (2 hours)

### Objective

Apply **aggressive criteria** to identify low-value tests that should be deleted or refactored.

### Assessment Criteria

#### 1. Low Value-to-Maintenance Ratio
**Trigger**: Test >100 LOC but covers trivial code

**Example**:
```python
def test_plugin_initialization_sets_all_properties():
    """200 LOC test that verifies 15 dataclass fields are set correctly."""
    plugin = MyPlugin(field1=1, field2=2, ..., field15=15)
    assert plugin.field1 == 1
    assert plugin.field2 == 2
    # ... 13 more assertions
```
**Verdict**: REFACTOR (use parametrization or snapshot testing)

#### 2. Implementation Detail Tests
**Trigger**: Tests private methods, internal state, or implementation details

**Example**:
```python
def test_internal_cache_invalidation():
    plugin = MyPlugin()
    plugin._cache = {"key": "value"}  # Accessing private attribute
    plugin._invalidate_cache()        # Testing private method
    assert plugin._cache == {}
```
**Verdict**: DELETE (testing implementation, not behavior)

#### 3. Fragile Tests
**Trigger**: Test breaks when refactoring unrelated code

**Heuristic**: If test imports >5 internal modules or mocks >3 components → fragile

**Example**:
```python
from elspeth.core.experiments.runner import ExperimentRunner
from elspeth.core.pipeline.artifacts import ArtifactPipeline
from elspeth.core.registries.sink import SinkRegistry
from elspeth.plugins.nodes.sinks.csv_file import CsvResultSink
from elspeth.plugins.experiments.aggregators import CostAggregator

@patch('elspeth.core.experiments.runner.ArtifactPipeline')
@patch('elspeth.core.registries.sink.SinkRegistry.get')
@patch('elspeth.plugins.nodes.sinks.csv_file.CsvResultSink.write')
def test_complex_integration(mock1, mock2, mock3):
    # 50 lines of mock setup
    ...
```
**Verdict**: REFACTOR (too coupled, should be integration test with real components)

#### 4. Trivial Assertions
**Trigger**: Test with <3 assertions, all trivial

**Example**:
```python
def test_plugin_exists():
    plugin = MyPlugin()
    assert plugin is not None
    assert isinstance(plugin, MyPlugin)
```
**Verdict**: DELETE (no value, constructor raises if broken)

#### 5. Overlapping Integration Tests
**Trigger**: Multiple end-to-end tests with >90% same steps

**Example**:
- `test_cli_end_to_end.py::test_suite_with_csv_output` (150 LOC)
- `test_cli_end_to_end.py::test_suite_with_excel_output` (148 LOC, 95% same)
- `test_cli_end_to_end.py::test_suite_with_json_output` (147 LOC, 95% same)

**Verdict**: CONSOLIDATE via parametrization (reduce to 1 test, 3 parameter sets)

#### 6. Outdated Tests
**Trigger**: Tests for removed features, deprecated APIs

**Detection**: Grep for `@pytest.mark.skip("deprecated")`, imports of removed modules

---

### Implementation

**Manual Process** (based on `TEST_AUDIT_REPORT.md` and `DUPLICATES_ANALYSIS.md` outputs)

**Execution**:
```bash
# Review audit report for low-value patterns
cat docs/migration/test-suite-reorganization/TEST_AUDIT_REPORT.md

# Review duplication analysis
cat docs/migration/test-suite-reorganization/DUPLICATES_ANALYSIS.md

# Create candidates list manually
# Based on criteria above (trivial assertions, implementation details, etc.)
vim docs/migration/test-suite-reorganization/POINTLESS_TESTS_CANDIDATES.md
```

**Note**: Value assessment requires human judgment and stakeholder input. Use automation outputs as guidance.

### Output Format

**`POINTLESS_TESTS_CANDIDATES.md`** (~150 lines):

```markdown
# Low-Value Test Assessment

**Generated**: 2025-10-26
**Total Candidates**: 28 tests
**Recommended Deletions**: 8 tests
**Recommended Refactors**: 20 tests

⚠️ **Manual Review Required**: All candidates require stakeholder approval before deletion

---

## Category 1: Trivial Assertions (8 tests)

### test_plugin_initialization.py::test_datasource_exists
**LOC**: 5
**Assertions**: 2
**Verdict**: DELETE
**Rationale**: No-op test, constructor raises if broken
```python
def test_datasource_exists():
    ds = MyDatasource()
    assert ds is not None
    assert isinstance(ds, MyDatasource)
```

---

## Category 2: Implementation Details (5 tests)

### test_registry.py::test_internal_cache_structure
**LOC**: 45
**Assertions**: 8
**Verdict**: DELETE
**Rationale**: Tests private `_cache` dict structure, not public API
**Impact**: No coverage loss (public API tested elsewhere)

---

## Category 3: Low Value-to-Maintenance (7 tests)

### test_experiment_metrics_plugins.py::test_all_aggregator_fields
**LOC**: 287
**Assertions**: 42
**Verdict**: REFACTOR (snapshot testing)
**Rationale**: 287 LOC to verify dataclass fields → use pytest-snapshot
**Savings**: ~250 LOC

---

## Category 4: Fragile Tests (6 tests)

### test_orchestrator.py::test_full_suite_with_mocks
**LOC**: 156
**Assertions**: 12
**Imports**: 9 internal modules
**Mocks**: 5 components
**Verdict**: REFACTOR (integration test)
**Rationale**: Should use real components, not mocks
**Action**: Move to tests/integration/, remove mocks

---

## Category 5: Overlapping Integration (2 groups)

### Group: CLI End-to-End Output Format Tests
**Tests**:
1. test_cli_end_to_end.py::test_suite_with_csv_output (150 LOC)
2. test_cli_end_to_end.py::test_suite_with_excel_output (148 LOC)
3. test_cli_end_to_end.py::test_suite_with_json_output (147 LOC)

**Overlap**: 95%
**Verdict**: CONSOLIDATE
**Savings**: ~290 LOC
**Proposed**:
```python
@pytest.mark.parametrize("output_format", ["csv", "excel", "json"])
def test_suite_with_output_format(output_format):
    # Single 50-line test with parametrized output
```

---

## Summary

| Category | Candidates | DELETE | REFACTOR | LOC Saved |
|----------|------------|--------|----------|-----------|
| Trivial | 8 | 8 | 0 | ~40 |
| Implementation Details | 5 | 5 | 0 | ~180 |
| Low Value-to-Maintenance | 7 | 0 | 7 | ~1,200 |
| Fragile | 6 | 0 | 6 | ~500 (via simplification) |
| Overlapping | 2 groups | 0 | 6 tests | ~580 |
| **TOTAL** | **28** | **13** | **19** | **~2,500** |

**Expected Impact**:
- Test count reduction: 13 deleted + 13 consolidated (from overlapping) = **-26 tests (~12%)**
- LOC reduction: **~2,500 lines (~8.5%)**
- Maintenance improvement: High (fragile tests removed)
```

---

## Step 1.4: Proposed Structure Design (0.5 hours)

### Objective

Finalize directory structure and create file mapping for Phase 2.

### Design Principles

1. **Mirror source structure**: `tests/unit/core/` maps to `src/elspeth/core/`
2. **Separation of concerns**: Unit vs Integration vs Compliance vs Performance
3. **Flat hierarchies**: Max 3 levels deep (excluding `tests/`)
4. **Clear naming**: Directory names match source code modules

### Proposed Structure

See `PROPOSED_STRUCTURE.md` for complete tree with examples and mapping rules.

**High-Level Layout**:
```
tests/
├── unit/              # Fast (<1s each), isolated, no I/O
├── integration/       # Multi-component, may have I/O
├── compliance/        # ADR enforcement tests
├── performance/       # Slow (>1s), benchmarks
└── fixtures/          # Shared fixtures, test data
```

### File Mapping Example

| Current Location | New Location | Rationale |
|------------------|--------------|-----------|
| `test_outputs_csv.py` | `unit/plugins/nodes/sinks/csv/test_write.py` | Unit test for CSV sink |
| `test_csv_sink_path_guard.py` | `unit/plugins/nodes/sinks/csv/test_path_guard.py` | Unit test, path guard concern |
| `test_cli_end_to_end.py` | `integration/cli/test_suite_execution.py` | Integration test |
| `test_adr002_baseplugin_compliance.py` | `compliance/adr002/test_baseplugin.py` | ADR-002 compliance |

### Deliverable

**`PROPOSED_STRUCTURE.md`** - See separate file (created in next step)

---

## Phase 1 Deliverables Checklist

- [ ] `TEST_AUDIT_REPORT.md` generated (Step 1.1)
- [ ] `FIXTURE_ANALYSIS.md` generated (Step 1.1)
- [ ] `DUPLICATES_ANALYSIS.md` generated (Step 1.2)
- [ ] `POINTLESS_TESTS_CANDIDATES.md` generated (Step 1.3)
- [ ] `PROPOSED_STRUCTURE.md` finalized (Step 1.4)
- [ ] Stakeholder review complete
- [ ] Approval to proceed to Phase 2

---

## Stakeholder Review Process

1. **Distribute Reports**: Share all 4 deliverables with team
2. **Review Meeting** (1 hour):
   - Review duplication findings
   - Discuss pointless test candidates
   - Approve/reject deletions
   - Approve final structure
3. **Document Decisions**: Update `POINTLESS_TESTS_CANDIDATES.md` with "APPROVED" or "REJECTED" for each
4. **Sign-off**: Get approval to proceed to Phase 2

---

## Troubleshooting

### Issue: Coverage data unavailable
**Solution**: Run `pytest --cov --cov-report=json` to generate `.coverage` file first

### Issue: AST parsing fails on certain files
**Solution**: Exclude problematic files, note in audit report, manual review

### Issue: Too many candidates flagged
**Solution**: Increase thresholds (e.g., 90% similarity instead of 85%)

---

## Next Steps

Once Phase 1 complete:
1. Archive deliverables in `docs/migration/test-suite-reorganization/phase1_results/`
2. Proceed to Phase 2: `01-REORGANIZATION_PLAN.md`
3. Update `README.md` status tracker

---

**Phase 1 Success Criteria**:
✅ All test files analyzed (~175-185 post-Phase 0)
✅ Fixture dependencies mapped
✅ Duplicates identified with high confidence
✅ Value assessment complete
✅ Structure approved by stakeholders
✅ Ready to execute Phase 2
