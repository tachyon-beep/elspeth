# CI/CD Update Checklist

**Objective**: Update CI/CD configuration after test reorganization to maintain build integrity

**Estimated Effort**: 1-2 hours (after Phase 2 complete)
**Risk Level**: Medium (CI failures block merges)

---

## Overview

Test file reorganization impacts CI/CD systems that reference test paths, patterns, or caching strategies. This checklist ensures all CI/CD configurations are updated to maintain:
- Test discovery and execution
- Coverage reporting
- Test result caching
- Build performance

**Execute this checklist AFTER Phase 2 complete, BEFORE merging reorganization branch.**

---

## GitHub Actions Workflows

### Workflow Files to Review

```bash
# List all workflow files
find .github/workflows/ -name "*.yml" -o -name "*.yaml"
```

**Typical files**:
- `.github/workflows/test.yml` - Main test suite
- `.github/workflows/pr-checks.yml` - PR validation
- `.github/workflows/coverage.yml` - Coverage reporting
- `.github/workflows/security-scan.yml` - Security tests

---

### Update 1: Test Discovery Paths

**Check for hardcoded test paths**:

```yaml
# Before (hardcoded root path)
- name: Run tests
  run: pytest tests/test_*.py

# After (use discovery)
- name: Run tests
  run: pytest tests/
```

**Better**: Use pytest's automatic discovery:
```yaml
- name: Run unit tests
  run: pytest tests/unit/

- name: Run integration tests
  run: pytest tests/integration/

- name: Run compliance tests
  run: pytest tests/compliance/
```

---

### Update 2: Coverage Reporting

**Check coverage configuration**:

```yaml
# Before (may have path-based exclusions)
- name: Generate coverage
  run: |
    pytest --cov=elspeth --cov-report=xml \\
      --cov-config=.coveragerc

# After: Verify .coveragerc doesn't exclude new paths
# See .coveragerc section below
```

---

### Update 3: Test Result Caching

**Check if test results are cached**:

```yaml
# If using cache keys based on test file paths
- uses: actions/cache@v3
  with:
    path: .pytest_cache
    key: pytest-${{ hashFiles('tests/**/*.py') }}  # May need update
```

**Recommendation**: Cache key should still work with new structure, but verify cache hit rate doesn't drop.

---

### Update 4: Parallel Test Execution

**Check if tests are split for parallelization**:

```yaml
# If using test splitting by path
strategy:
  matrix:
    test-group:
      - tests/test_adr002*.py  # OLD - may not exist
      - tests/test_outputs*.py  # OLD - may not exist

# After (use new structure)
strategy:
  matrix:
    test-group:
      - tests/compliance/adr002/
      - tests/unit/plugins/nodes/sinks/
      - tests/integration/
```

---

### Update 5: Security Compliance Tests

**Check if ADR-002 compliance tests are explicitly run**:

```yaml
# Before (hardcoded file patterns)
- name: Run ADR-002 compliance tests
  run: pytest tests/test_adr002*.py -v

# After (use compliance directory)
- name: Run ADR-002 compliance tests
  run: pytest tests/compliance/adr002/ -v
```

---

## Coverage Configuration (.coveragerc or pyproject.toml)

### Check Coverage Exclusions

```ini
# .coveragerc
[run]
omit =
    tests/test_*.py  # OLD - may need update
    tests/**/conftest.py
    tests/fixtures/*

# After (verify paths still correct)
[run]
omit =
    tests/**/conftest.py
    tests/fixtures/*
    # Pattern tests/test_*.py may not match new structure
```

**Recommendation**: Use `tests/**/test_*.py` or just `tests/**/*.py` for broader match.

---

### Check Source Paths

```ini
[run]
source = elspeth

[paths]
source =
    src/elspeth
    */site-packages/elspeth

# Should NOT need changes (source code unchanged)
```

---

## pytest.ini or pyproject.toml

### Check Test Discovery Patterns

```ini
# pytest.ini
[pytest]
testpaths = tests  # Good - discovers all subdirectories
python_files = test_*.py  # Good - pattern-based
python_classes = Test*
python_functions = test_*

# Should NOT need changes (patterns still match)
```

---

### Check Marker Definitions

```ini
[pytest]
markers =
    slow: Slow tests (>1s)
    integration: Integration tests
    compliance: ADR compliance tests
    adr002: ADR-002 specific tests

# Add if not present:
#   compliance_adr002: ADR-002 Multi-Level Security tests
#   compliance_adr005: ADR-005 Frozen plugins tests
```

---

## Pre-commit Hooks (.pre-commit-config.yaml)

### Check Test-Related Hooks

```yaml
# If pre-commit runs tests on changed files
- repo: local
  hooks:
    - id: pytest-check
      name: pytest
      entry: pytest
      language: system
      types: [python]
      pass_filenames: false  # Runs all tests (good)
      # OR
      # args: ['--co']  # Collection only (fast check)
```

**Recommendation**: If hook uses file paths, ensure it handles new structure.

---

## Documentation Links

### Update Test Documentation

**Check for hardcoded test file references**:

```bash
# Find documentation referencing test files
grep -r "tests/test_" docs/ --include="*.md"
grep -r "tests/test_" README.md
```

**Update patterns**:
- `tests/test_adr002_invariants.py` → `tests/compliance/adr002/test_invariants.py`
- `tests/test_outputs_csv.py` → `tests/unit/plugins/nodes/sinks/csv/test_write.py`

---

## IDE/Editor Configuration

### VS Code (.vscode/settings.json)

```json
{
  "python.testing.pytestArgs": [
    "tests"  // Good - discovers subdirectories
  ],
  "python.testing.unittestEnabled": false,
  "python.testing.pytestEnabled": true,

  // If file watchers are path-specific, update:
  "files.watcherExclude": {
    "**/.git/objects/**": true,
    "**/.git/subtree-cache/**": true,
    "**/node_modules/*/**": true,
    "**/.pytest_cache/**": true,
    "**/__pycache__/**": true
  }
}
```

**Should NOT need changes** (pattern-based exclusions still work).

---

### PyCharm (.idea/)

**Check Run Configurations**:
1. Open Run → Edit Configurations
2. Verify pytest configurations use `tests/` directory (not specific files)
3. Update any saved configurations that reference old paths

---

## Makefile Targets

### Check Test Targets

```makefile
# Check all test-related targets
grep -n "pytest" Makefile

# Common targets:
.PHONY: test
test:
    pytest tests/  # Good - discovers all

.PHONY: test-unit
test-unit:
    pytest tests/ -m "not slow"  # Good - marker-based

.PHONY: test-compliance
test-compliance:
    pytest tests/test_adr002*.py  # BAD - hardcoded pattern
```

**Update hardcoded paths**:
```makefile
.PHONY: test-compliance
test-compliance:
    pytest tests/compliance/  # Uses new structure
```

---

## Dependency Review Workflow

**Check if test dependencies are audited**:

```yaml
# .github/workflows/dependency-review.yml
- name: Check test dependencies
  run: |
    pip-audit -r requirements-dev.lock
```

**Should NOT need changes** (dependencies unchanged, only test file locations).

---

## Verification Protocol

### Step 1: Local Verification (BEFORE pushing)

```bash
# Verify pytest collection
pytest --collect-only -q
# Expected: Same test count as before reorganization

# Verify tests run
pytest tests/ -v

# Verify coverage
pytest --cov=elspeth --cov-report=term-missing
# Expected: Coverage ≥ baseline (±2%)
```

---

### Step 2: CI Dry Run (in PR)

```bash
# Push reorganization branch
git push origin test-suite-reorganization

# Open PR (draft mode)
gh pr create --draft --title "Test suite reorganization" --body "Dry run for CI"

# Monitor CI results
gh pr checks

# Expected:
# ✓ All CI checks pass
# ✓ Coverage report generated
# ✓ No test discovery errors
# ✓ Build time similar (±20%)
```

---

### Step 3: Review CI Logs

**Check for warnings**:
```bash
# Download CI logs
gh run view <run-id> --log

# Search for issues
grep -i "warning" ci.log
grep -i "deprecated" ci.log
grep -i "not found" ci.log
```

**Common warnings to address**:
- `PytestCollectionWarning: cannot collect test class 'Test*'` → Check test class naming
- `coverage warning: No data was collected` → Check coverage paths
- `cache miss` → Cache keys may need update

---

## CI/CD Update Checklist

**Complete this checklist BEFORE merging reorganization PR**:

### GitHub Actions
- [ ] All `.github/workflows/*.yml` reviewed
- [ ] Test discovery paths updated (if hardcoded)
- [ ] Coverage reporting paths verified
- [ ] Test result caching verified
- [ ] Parallel test execution updated (if path-based)
- [ ] Security compliance tests updated
- [ ] Workflow execution logs reviewed (no errors/warnings)

### Configuration Files
- [ ] `.coveragerc` or `pyproject.toml` [coverage] section verified
- [ ] `pytest.ini` or `pyproject.toml` [tool.pytest.ini_options] verified
- [ ] `.pre-commit-config.yaml` updated (if test-path-specific)
- [ ] `Makefile` test targets updated
- [ ] No hardcoded test file paths remain

### Documentation
- [ ] `README.md` updated (test command examples)
- [ ] `CONTRIBUTING.md` updated (test organization guidance)
- [ ] `docs/development/testing-overview.md` updated
- [ ] Architecture docs updated (test structure diagrams)
- [ ] Inline test path references updated

### IDE Configuration
- [ ] `.vscode/settings.json` verified (if committed)
- [ ] PyCharm run configurations updated (if shared)
- [ ] `.idea/` reviewed (if committed)

### Verification
- [ ] Local pytest collection works: `pytest --collect-only -q`
- [ ] Local test suite passes: `pytest -v`
- [ ] Local coverage baseline maintained: `pytest --cov`
- [ ] CI checks pass in PR
- [ ] CI build time similar (±20%)
- [ ] No CI warnings related to test paths

---

## Rollback

If CI/CD updates fail:

```bash
# Revert configuration changes
git revert <ci-config-commit>

# Or restore from backup
cp .github/workflows/test.yml.bak .github/workflows/test.yml

# Verify CI passes
git push
```

---

## Success Criteria

✅ All CI workflows pass
✅ Coverage reporting works correctly
✅ Test discovery finds all tests
✅ Build time unchanged (±20%)
✅ No CI warnings or errors
✅ Documentation references updated
✅ Team can run tests locally without issues

---

**Estimated Effort**: 1-2 hours (checklist-driven, mostly verification)
**Risk Level**: Medium (CI failures are easily reversible, but block merges)
**Dependencies**: Phase 2 complete

---

**Last Updated**: 2025-10-27
**Author**: Architecture Team
