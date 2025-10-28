# Fixture Migration Strategy

**Objective**: Migrate fixtures during test reorganization without breaking tests or changing fixture scoping

**Estimated Effort**: Included in Phase 2 (10-14 hours total)
**Risk Level**: Medium (fixture scoping can cause subtle bugs)

---

## Overview

Fixtures are critical test infrastructure that must be carefully migrated to maintain test functionality. Incorrect fixture placement can cause:
- Tests not finding fixtures (import errors)
- Tests unexpectedly sharing state (wrong scope)
- Performance degradation (session fixtures becoming function-scoped)

This strategy ensures fixtures are correctly placed and scoped after reorganization.

---

## Current Fixture Landscape

### Fixture Locations

**Root conftest.py** (`tests/conftest.py`): 307 lines
- Contains global fixtures available to all tests
- Session and module-scoped fixtures
- Critical fixtures like `assert_sanitized_artifact`

**ADR-002 Test Helpers** (`tests/adr002_test_helpers.py`): [SIZE TBD]
- ADR-002 specific fixtures and helpers
- Used by compliance tests

**Subdirectory conftest.py** (various):
- Local fixtures for specific test categories
- Currently scattered and inconsistent

---

## Fixture Classification System

### Class 1: Global Session Fixtures

**Definition**: Fixtures used by >5 tests, session-scoped, no category-specific logic

**Examples**:
- Database connections
- Temporary directory setup
- Mock service stubs (if truly global)

**Target Location**: `tests/fixtures/conftest.py`

**Migration**:
```python
# Before: tests/conftest.py
@pytest.fixture(scope="session")
def sample_classified_dataframe():
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    return SecureDataFrame.create_from_datasource(df, SecurityLevel.OFFICIAL)

# After: tests/fixtures/conftest.py (unchanged)
@pytest.fixture(scope="session")
def sample_classified_dataframe():
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    return SecureDataFrame.create_from_datasource(df, SecurityLevel.OFFICIAL)
```

---

### Class 2: ADR-Specific Fixtures

**Definition**: Fixtures supporting ADR compliance tests

**Examples**:
- Security level test helpers
- Plugin mock factories for ADR-002
- Baseline comparison fixtures

**Target Location**: `tests/fixtures/adr002_test_helpers.py` (existing), `tests/fixtures/adr005_test_helpers.py` (if needed)

**Migration**:
```python
# Before: tests/adr002_test_helpers.py (root)
def create_test_plugin_with_level(level: SecurityLevel):
    ...

# After: tests/fixtures/adr002_test_helpers.py
def create_test_plugin_with_level(level: SecurityLevel):
    ...

# Usage in compliance tests:
from tests.fixtures import adr002_test_helpers
```

---

### Class 3: Category-Local Fixtures

**Definition**: Fixtures used only within a category (e.g., only sink tests, only CLI tests)

**Examples**:
- Mock sink configurations
- CLI argument builders
- Test data generators for specific plugin types

**Target Location**: Category-specific `conftest.py`
- `tests/unit/plugins/nodes/sinks/conftest.py`
- `tests/integration/cli/conftest.py`
- `tests/compliance/adr002/conftest.py`

**Migration**:
```python
# Before: tests/conftest.py (global, but only used by sinks)
@pytest.fixture
def mock_sink_config():
    return {"output_dir": "/tmp/test"}

# After: tests/unit/plugins/nodes/sinks/conftest.py
@pytest.fixture
def mock_sink_config():
    return {"output_dir": "/tmp/test"}

# Accessible to all tests under tests/unit/plugins/nodes/sinks/
```

---

### Class 4: File-Local Fixtures

**Definition**: Fixtures used only within a single test file

**Examples**:
- Test-specific data setup
- One-off mocks

**Target Location**: Stay in the test file itself

**Migration**: No change needed (move with the test file)

---

## Fixture Scoping Rules

### Scope Preservation is CRITICAL

**Rule**: Fixture scope MUST be preserved during migration. Changing scope is a behavioral change.

**Examples**:

❌ **WRONG** - Scope changed:
```python
# Before: session-scoped
@pytest.fixture(scope="session")
def db_connection():
    return connect()

# After: function-scoped (WRONG!)
@pytest.fixture
def db_connection():
    return connect()
# This breaks tests expecting shared connection
```

✅ **CORRECT** - Scope preserved:
```python
# Before: session-scoped
@pytest.fixture(scope="session")
def db_connection():
    return connect()

# After: session-scoped (CORRECT)
@pytest.fixture(scope="session")
def db_connection():
    return connect()
```

### Scoping Hierarchy

**pytest fixture scoping** (narrowest to widest):
1. **function** - New instance per test function (default)
2. **class** - Shared across test class
3. **module** - Shared across test file
4. **session** - Shared across entire test run

**Directory hierarchy** (narrowest to widest):
1. Test file itself
2. `tests/unit/plugins/nodes/sinks/conftest.py`
3. `tests/unit/conftest.py`
4. `tests/conftest.py` (global)

**Rule**: Fixture scope should match usage scope:
- Session-scoped → `tests/conftest.py` or `tests/fixtures/conftest.py`
- Module-scoped → Category `conftest.py` or test file
- Function-scoped → Usually test file

---

## Migration Protocol

### Step F1: Analyze Fixture Usage (included in Phase 1)

```bash
# Run fixture analysis script
python analyze_fixtures.py \\
    --test-dir tests \\
    --output FIXTURE_ANALYSIS.md

# Review output:
# - Which fixtures are used by which tests
# - Fixture dependency chains
# - Fixture scopes
```

**Deliverable**: `FIXTURE_ANALYSIS.md` with fixture classification recommendations

---

### Step F2: Create Target Fixture Files (Phase 2 prep)

```bash
# Create fixture directory structure
mkdir -p tests/fixtures

# Create category-specific conftest files
mkdir -p tests/unit/plugins/nodes/sinks
touch tests/unit/plugins/nodes/sinks/conftest.py

mkdir -p tests/integration/cli
touch tests/integration/cli/conftest.py

mkdir -p tests/compliance/adr002
touch tests/compliance/adr002/conftest.py
```

---

### Step F3: Migrate Global Fixtures (Phase 2, early)

**Do this BEFORE moving test files**

```bash
# Move global fixtures to tests/fixtures/conftest.py
# Extract from tests/conftest.py:
# 1. Session-scoped fixtures used by >5 tests
# 2. Widely-used helper fixtures

# Keep in tests/conftest.py:
# 1. Pytest configuration (pytest_configure, pytest_collection_modifyitems)
# 2. Root-level imports for path setup
```

**Example migration**:
```python
# tests/conftest.py (keep minimal)
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import fixtures from centralized location
pytest_plugins = ["tests.fixtures.conftest"]

# tests/fixtures/conftest.py (new)
import pytest
from elspeth.core.security.secure_data import SecureDataFrame
from elspeth.core.base.types import SecurityLevel

@pytest.fixture(scope="session")
def sample_classified_dataframe():
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    return SecureDataFrame.create_from_datasource(df, SecurityLevel.OFFICIAL)
```

---

### Step F4: Migrate ADR Fixtures (Phase 2, after ADR tests moved)

```bash
# Move ADR-002 helpers
git mv tests/adr002_test_helpers.py tests/fixtures/adr002_test_helpers.py

# Update imports in compliance tests
# From: import adr002_test_helpers
# To: from tests.fixtures import adr002_test_helpers
```

---

### Step F5: Migrate Category-Local Fixtures (Phase 2, during test moves)

**For each category** (sinks, CLI, etc.):

1. Identify fixtures used only by that category (from FIXTURE_ANALYSIS.md)
2. Extract to category `conftest.py`
3. Update test imports (usually automatic - pytest discovers conftest.py)

**Example**:
```python
# tests/conftest.py
@pytest.fixture
def mock_csv_sink_config():  # Only used by CSV sink tests
    return {"path": "/tmp/test.csv"}

# After migration:
# tests/unit/plugins/nodes/sinks/csv/conftest.py
@pytest.fixture
def mock_csv_sink_config():
    return {"path": "/tmp/test.csv"}

# Tests in tests/unit/plugins/nodes/sinks/csv/ automatically discover this
```

---

### Step F6: Verify Fixture Imports (Phase 2, verification)

```bash
# After all test files moved, verify fixtures resolve correctly
pytest --collect-only -q

# Should see no "fixture not found" errors

# Run subset of tests to verify scoping
pytest tests/unit/plugins/nodes/sinks/ -v -k "test_csv"
```

---

## Common Pitfalls & Solutions

### Pitfall 1: Fixture Not Found After Move

**Symptom**:
```
fixture 'mock_sink_config' not found
```

**Cause**: Fixture was in root `conftest.py`, test moved to subdirectory, fixture not moved

**Solution**:
1. Check FIXTURE_ANALYSIS.md to see where fixture should be
2. Move fixture to appropriate `conftest.py` (global, category, or test file)
3. If global, import in test: `from tests.fixtures.conftest import mock_sink_config`

---

### Pitfall 2: Tests Share Unexpected State

**Symptom**: Tests pass individually but fail when run together

**Cause**: Fixture scope changed from `function` to `module` or `session`

**Solution**:
1. Check original fixture scope in git history
2. Restore original scope
3. If fixture must be shared, explicitly document in docstring

---

### Pitfall 3: Slow Test Suite After Migration

**Symptom**: Tests run slower after migration

**Cause**: Session-scoped fixtures became function-scoped (created per test instead of once)

**Solution**:
1. Review FIXTURE_ANALYSIS.md for fixture scopes
2. Restore session scope for expensive fixtures (DB connections, mock services)
3. Verify with `pytest --durations=10`

---

### Pitfall 4: Circular Fixture Dependencies

**Symptom**:
```
fixture 'A' requested in fixture 'B', which is requested in fixture 'A'
```

**Cause**: Fixture reorganization created circular dependency

**Solution**:
1. Review fixture dependency graph in FIXTURE_ANALYSIS.md
2. Refactor one fixture to not depend on the other
3. Or combine into single fixture

---

## Verification Checklist

After fixture migration complete:

- [ ] All tests collect successfully: `pytest --collect-only -q`
- [ ] No "fixture not found" errors
- [ ] All tests pass: `pytest -v`
- [ ] Test duration unchanged (±10%): `pytest --durations=20`
- [ ] Fixture scopes match original (verified via git log)
- [ ] No unexpected state sharing (tests pass individually and together)
- [ ] `tests/fixtures/conftest.py` created with global fixtures
- [ ] ADR helpers moved to `tests/fixtures/adr002_test_helpers.py`
- [ ] Category-local fixtures in appropriate `conftest.py` files

---

## Rollback

If fixture migration fails:

```bash
# Revert fixture changes
git revert <fixture-migration-commit>

# Or reset to before fixture migration
git reset --hard <commit-before-fixture-migration>

# Verify tests pass
pytest -v
```

---

## Success Criteria

✅ All fixtures accessible from migrated tests
✅ Fixture scopes preserved (function/module/session)
✅ No circular dependencies
✅ Test suite runtime unchanged (±10%)
✅ `FIXTURE_ANALYSIS.md` generated and reviewed
✅ Fixture locations documented

---

**Estimated Effort**: Included in Phase 2 (2-3 hours of Phase 2's 10-14 hours)
**Risk Level**: Medium (careful execution required, but straightforward with analysis)
**Dependencies**: Phase 1 complete (FIXTURE_ANALYSIS.md generated)

---

**Last Updated**: 2025-10-27
**Author**: Architecture Team
