# Test Audit: tests/mcp/test_contract_tools.py

**Audit Date:** 2026-02-05
**Auditor:** Claude Code
**Test File:** `/home/john/elspeth-rapid/tests/mcp/test_contract_tools.py`
**Lines:** 458

## Summary

Tests for MCP server contract analysis tools (`get_run_contract`, `explain_field`, `list_contract_violations`). The file tests the LandscapeAnalyzer methods used for debugging validation failures and tracing field provenance.

## Findings

### 1. MEDIUM: Unconventional Object Construction Pattern

**Location:** Lines 32-34, 82-84, 98-101, 115-117, and many more

**Issue:** Tests construct `LandscapeAnalyzer` using `__new__` and manually set private attributes:
```python
analyzer = LandscapeAnalyzer.__new__(LandscapeAnalyzer)
analyzer._db = db
analyzer._recorder = LandscapeRecorder(db)
```

**Impact:** This bypasses `__init__` which may contain important initialization logic. If `LandscapeAnalyzer.__init__` is modified to include additional setup, these tests will not catch bugs where that setup is required.

**Recommendation:** Either:
1. Create a proper test factory/fixture for `LandscapeAnalyzer`
2. Use production construction path if available
3. Add a class method like `LandscapeAnalyzer.for_testing(db)` that tests can use

### 2. LOW: Tests for Method Existence Add Little Value

**Location:** Lines 405-418 (`TestMCPToolIntegration`)

**Issue:** Tests like `test_get_run_contract_method_exists` only check that methods exist:
```python
def test_get_run_contract_method_exists(self) -> None:
    assert hasattr(LandscapeAnalyzer, "get_run_contract")
    assert callable(LandscapeAnalyzer.get_run_contract)
```

**Impact:** These provide minimal value - type checkers and imports would catch missing methods. The real test at line 421 (`test_contract_tools_return_json_serializable_results`) is more valuable as it actually exercises the methods.

**Recommendation:** Remove the `*_method_exists` tests or combine them into a single structural test if truly needed for documentation.

### 3. LOW: No Test for Large Result Set Handling

**Location:** `TestListContractViolations` class

**Issue:** `test_respects_limit_parameter` only tests with 5 violations limited to 3. There's no test for:
- Very large numbers of violations (performance)
- Limit of 0 (edge case)
- Limit larger than total violations

**Recommendation:** Add edge case tests for limit parameter behavior.

### 4. INFO: Repeated Database Setup Could Use Fixtures

**Location:** Throughout all test classes

**Issue:** Every test method creates its own `LandscapeDB.in_memory()` and manually constructs the analyzer. This is repeated ~15 times.

**Recommendation:** Use pytest fixtures:
```python
@pytest.fixture
def analyzer():
    db = LandscapeDB.in_memory()
    analyzer = LandscapeAnalyzer.__new__(LandscapeAnalyzer)
    analyzer._db = db
    analyzer._recorder = LandscapeRecorder(db)
    return analyzer
```

### 5. POSITIVE: Good Error Path Coverage

The tests properly cover error conditions:
- Nonexistent run
- Run without contract
- Nonexistent field
- Empty violations list

### 6. POSITIVE: JSON Serializability Test

Line 421-458 tests that all contract tools return JSON-serializable results, which is important for MCP protocol compliance.

## Test Path Integrity

**Status:** ACCEPTABLE

The tests bypass `LandscapeAnalyzer.__init__` but this is reasonable for unit testing the individual methods. The `LandscapeRecorder` and `LandscapeDB` are used with their production paths. The tests don't involve `ExecutionGraph` or DAG construction.

## Verdict

**PASS with recommendations**

The tests are functional and cover the main scenarios. The main issues are:
1. Unconventional construction pattern that could hide init bugs
2. Redundant method-existence tests
3. Repeated setup code

No critical defects found. The tests properly validate the MCP contract tools for their intended use case.
