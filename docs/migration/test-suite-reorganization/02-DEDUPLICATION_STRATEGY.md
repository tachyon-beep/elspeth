# Phase 3: Deduplication & Cleanup Strategy

**Objective**: Remove/consolidate redundant tests identified in Phase 1

**Estimated Effort**: 4-6 hours
**Prerequisites**: Phase 2 complete, tests reorganized and passing
**Risk Level**: Low (working with organized test suite, frequent verification)

---

## Overview

Phase 3 reduces test suite bloat by eliminating exact duplicates, consolidating overlapping tests via parametrization, and removing low-value tests approved for deletion in Phase 1.

### Target Metrics

- **Test count reduction**: 15-20% (~26-35 tests removed/consolidated)
- **LOC reduction**: ~2,500 lines
- **Coverage**: Maintained within ±2%
- **Performance**: 10-20% faster test suite runtime

---

## Step 3.1: Stakeholder Review (1 hour)

### Review Process

**Deliverable from Phase 1**: `POINTLESS_TESTS_CANDIDATES.md`

**Actions**:
1. Team reviews all flagged tests
2. Mark each as: `APPROVED_DELETE`, `APPROVED_REFACTOR`, or `KEEP`
3. Document rationale for `KEEP` decisions
4. Update candidate list with decisions

---

## Step 3.2: Safe Deletions (1 hour)

### Exact Duplicates

Delete tests with identical logic in multiple files (from Phase 1 analysis).

**Example**:
```bash
# Delete duplicate test (keep in primary location)
git rm tests/unit/plugins/experiments/aggregators/test_metrics_plugins.py::test_cost_summary_on_error_skip
# (Duplicate of test in test_cost_summary.py)

# Verify coverage unchanged
pytest --cov tests/unit/plugins/experiments/aggregators/

# Commit
git commit -m "test: Remove exact duplicate test_cost_summary_on_error_skip"
```

### Trivial/Pointless Tests

Delete tests approved in Step 3.1 (trivial assertions, no-op tests).

**Batch delete**:
```bash
# Remove approved pointless tests
git rm tests/unit/.../test_plugin_exists.py
git rm tests/unit/.../test_datasource_not_none.py

# Verify suite still passes
pytest -v

# Commit
git commit -m "test: Remove 8 trivial tests (zero coverage loss)"
```

---

## Step 3.3: Consolidation via Parametrization (2 hours)

### Pattern: Multiple Similar Tests → Single Parametrized Test

**Before** (3 separate tests, 450 LOC total):
```python
def test_csv_sink_writes(tmp_path):
    sink = CsvResultSink(path=tmp_path / "out.csv")
    sink.write({"results": [...]})
    assert (tmp_path / "out.csv").exists()
    df = pd.read_csv(tmp_path / "out.csv")
    assert len(df) == 3

def test_excel_sink_writes(tmp_path):
    sink = ExcelResultSink(path=tmp_path / "out.xlsx")
    sink.write({"results": [...]})
    assert (tmp_path / "out.xlsx").exists()
    df = pd.read_excel(tmp_path / "out.xlsx")
    assert len(df) == 3

def test_json_sink_writes(tmp_path):
    sink = JsonResultSink(path=tmp_path / "out.json")
    sink.write({"results": [...]})
    assert (tmp_path / "out.json").exists()
    with open(tmp_path / "out.json") as f:
        data = json.load(f)
    assert len(data) == 3
```

**After** (1 parametrized test, 50 LOC):
```python
@pytest.mark.parametrize("sink_class,file_ext,reader", [
    (CsvResultSink, ".csv", pd.read_csv),
    (ExcelResultSink, ".xlsx", pd.read_excel),
    (JsonResultSink, ".json", lambda p: json.load(open(p))),
])
def test_sink_writes_successfully(sink_class, file_ext, reader, tmp_path):
    output_path = tmp_path / f"out{file_ext}"
    sink = sink_class(path=output_path)
    sink.write({"results": [...]})
    
    assert output_path.exists()
    data = reader(output_path)
    assert len(data) == 3
```

**Savings**: 400 LOC, 2 fewer test functions, same coverage

### Execution Protocol

**For each consolidation group**:
1. Identify common pattern
2. Extract to parametrized test
3. Delete original separate tests
4. Run: `pytest <path> -v`
5. Verify coverage: `pytest <path> --cov`
6. Commit: `git commit -m "test: Consolidate X sink write tests via parametrization"`

---

## Step 3.4: Fixture Refactoring (1 hour)

### Extract Common Setup to Fixtures

**Before** (duplicated setup in 5 tests):
```python
def test_a():
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    classified = ClassifiedDataFrame.create_from_datasource(df, SecurityLevel.OFFICIAL)
    # test logic

def test_b():
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    classified = ClassifiedDataFrame.create_from_datasource(df, SecurityLevel.OFFICIAL)
    # test logic
```

**After** (shared fixture):
```python
@pytest.fixture
def sample_classified_dataframe():
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    return ClassifiedDataFrame.create_from_datasource(df, SecurityLevel.OFFICIAL)

def test_a(sample_classified_dataframe):
    # test logic

def test_b(sample_classified_dataframe):
    # test logic
```

---

## Step 3.5: Final Verification (1 hour)

### Verification Checklist

- [ ] All deletions committed with rationale
- [ ] All consolidations tested individually
- [ ] Full test suite passes: `pytest -v`
- [ ] Coverage maintained: `pytest --cov --cov-report=term-missing`
- [ ] Performance improved: Compare runtime to Phase 2 baseline
- [ ] No regressions in CI

### Metrics Comparison

Generate comparison report:

```bash
# Before Phase 3
pytest --collect-only -q | tail -1
pytest --durations=0 | grep "slowest" 
pytest --cov --cov-report=term | grep "TOTAL"

# After Phase 3
pytest --collect-only -q | tail -1
pytest --durations=0 | grep "slowest"
pytest --cov --cov-report=term | grep "TOTAL"

# Generate summary
python scripts/phase3_summary.py \
    --before <before_stats> \
    --after <after_stats> \
    --output DEDUPLICATION_SUMMARY.md
```

**Expected `DEDUPLICATION_SUMMARY.md`**:

```markdown
# Phase 3 Deduplication Summary

## Metrics

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Test files | 218 | 185 | -33 (-15%) |
| Test count | ~1,500 | ~1,300 | -200 (-13%) |
| Total LOC | 29,498 | 27,000 | -2,498 (-8.5%) |
| Coverage | 82% | 83% | +1% |
| Runtime | 120s | 95s | -25s (-21%) |

## Actions Taken

### Deletions (13 tests)
- 8 trivial tests (no-op, assert not None)
- 5 implementation detail tests (private method testing)

### Consolidations (20 tests → 7 parametrized)
- Sink write tests: 12 tests → 4 parametrized
- Path guard tests: 5 tests → 2 parametrized
- Config validation: 3 tests → 1 parametrized

### Refactorings
- Extracted 6 shared fixtures
- Simplified 4 fragile tests (removed excessive mocking)

## Coverage Impact

No coverage regression. 3 areas with improved coverage from fixture refactoring.

## Performance Impact

-21% runtime improvement from:
- Fewer test collection overhead
- Parametrized tests share setup
- Removed slow integration test duplicates
```

---

## Rollback Strategy

**If Phase 3 causes issues**:
```bash
# Revert specific commit
git revert <commit-sha>

# OR reset to end of Phase 2
git reset --hard <phase2-completion-commit>
```

---

## Success Criteria

✅ Test count reduced 15-20%
✅ LOC reduced ~2,500 lines
✅ Coverage maintained (±2%)
✅ Performance improved 10-20%
✅ All deletions approved
✅ No regressions

---

## Next Steps

1. Generate `DEDUPLICATION_SUMMARY.md`
2. Update `README.md` with final metrics
3. Archive all Phase 1-3 reports
4. Close migration issue
5. Update testing documentation

---

**Phase 3 Time Estimate**: 4-6 hours
**Risk Level**: Low (organized suite, approved changes only)
**Dependencies**: Phase 2 complete, stakeholder approval
