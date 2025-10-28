# Automation Script Documentation

**✅ Scripts implemented and tested** - Ready for Phase 1-3 execution

**Location**: `docs/migration/test-suite-reorganization/` (copy to `scripts/` when executing)

---

## Overview

Four Python scripts automate test suite analysis, duplicate detection, fixture analysis, and file migration. All scripts are **implemented and tested** as part of planning phase updates (2025-10-27).

---

## audit_tests.py

**Purpose**: Extract metadata from all test files for Phase 1 analysis

**Status**: ✅ **IMPLEMENTED**

**Features**:
- AST-based analysis (no code execution)
- Extracts test counts, imports, fixture usage
- Identifies parametrized tests and slow markers
- Generates markdown or JSON reports

**Usage**:
```bash
# Generate markdown report
python docs/migration/test-suite-reorganization/audit_tests.py \
    --test-dir tests \
    --output docs/migration/test-suite-reorganization/TEST_AUDIT_REPORT.md \
    --format markdown

# Generate JSON for programmatic use
python docs/migration/test-suite-reorganization/audit_tests.py \
    --test-dir tests \
    --output test_metadata.json \
    --format json
```

**Outputs**:
- `TEST_AUDIT_REPORT.md` - Comprehensive metadata analysis
  - Summary statistics (test counts, LOC, fixtures)
  - Largest files (top 20 by lines)
  - Files with most tests (top 20)
  - Most common imports (top 30)
  - Most used fixtures (top 30)
  - Files by directory

**Example Output**:
```
## Summary Statistics
- Total test functions: 1,079
- Total test classes: 42
- Total fixtures: 156
- Total lines of code: 29,498
- Total size: 289.5 KB
```

---

## find_duplicates.py

**Purpose**: Detect duplicate and overlapping tests for Phase 1/3

**Status**: ✅ **IMPLEMENTED**

**Features**:
- Exact duplicate detection (same test name)
- Functional duplicate detection (same logic/AST)
- Similarity analysis (configurable threshold)
- Consolidation recommendations

**Usage**:
```bash
# Detect duplicates with 85% similarity threshold
python docs/migration/test-suite-reorganization/find_duplicates.py \
    --test-dir tests \
    --output docs/migration/test-suite-reorganization/DUPLICATES_ANALYSIS.md \
    --threshold 0.85

# Stricter threshold for Phase 3
python docs/migration/test-suite-reorganization/find_duplicates.py \
    --test-dir tests \
    --output DUPLICATES_STRICT.md \
    --threshold 0.95
```

**Outputs**:
- `DUPLICATES_ANALYSIS.md` - Duplicate test report
  - Exact duplicates (same name across files)
  - Functional duplicates (identical logic)
  - Similar tests (≥threshold similarity)
  - Consolidation recommendations

**Example Output**:
```
## Exact Duplicates
### Test name 'test_csv_sink_writes' appears in 3 files
**Similarity**: 100%

- `tests/test_outputs_csv.py::test_csv_sink_writes`
- `tests/plugins/sinks/test_csv_sink_edges.py::test_csv_sink_writes`
- `tests/unit/plugins/nodes/sinks/csv/test_write.py::test_csv_sink_writes`

**Recommendation**: Keep one, delete others (review logic first)
```

---

## analyze_fixtures.py

**Purpose**: Analyze fixture definitions and usage for Phase 1/2

**Status**: ✅ **IMPLEMENTED**

**Features**:
- Fixture definition discovery (location, scope)
- Fixture usage analysis (which tests use which fixtures)
- Dependency graph (fixtures depending on other fixtures)
- Migration recommendations (global vs. local placement)

**Usage**:
```bash
# Analyze all fixtures
python docs/migration/test-suite-reorganization/analyze_fixtures.py \
    --test-dir tests \
    --output docs/migration/test-suite-reorganization/FIXTURE_ANALYSIS.md
```

**Outputs**:
- `FIXTURE_ANALYSIS.md` - Fixture dependency analysis
  - Fixtures by scope (session/module/class/function)
  - Files with most fixtures (top 20)
  - Most used fixtures (top 30 with usage counts)
  - Fixture dependency chains
  - Migration recommendations by category

**Example Output**:
```
## Migration Recommendations

### Session Fixtures (Global)
These fixtures should be in `tests/fixtures/conftest.py`:

- `sample_classified_dataframe` (tests/conftest.py) - Used 42 times
- `mock_llm_client` (tests/conftest.py) - Used 38 times

### Module Fixtures (Local)
These fixtures should remain in category-specific conftest.py:

- `csv_sink_config` (tests/conftest.py) - Used 12 times (only by CSV sink tests)
```

---

## migrate_tests.py

**Purpose**: Automated file movement and import updates for Phase 2

**Status**: ✅ **IMPLEMENTED**

**Features**:
- Git mv for history preservation
- Batch file moves from YAML mapping
- Import path updates (relative → absolute)
- Dry-run mode for safety

**Usage**:
```bash
# DRY RUN - show what would happen
python docs/migration/test-suite-reorganization/migrate_tests.py move \
    --mapping FILE_MAPPING.yaml \
    --dry-run

# EXECUTE - actually move files
python docs/migration/test-suite-reorganization/migrate_tests.py move \
    --mapping FILE_MAPPING.yaml

# UPDATE IMPORTS - after files moved
python docs/migration/test-suite-reorganization/migrate_tests.py update-imports \
    --test-dir tests/ \
    --dry-run  # Optional: preview changes

python docs/migration/test-suite-reorganization/migrate_tests.py update-imports \
    --test-dir tests/  # Execute
```

**Mapping File Format** (`FILE_MAPPING.yaml`):
```yaml
moves:
  - old: tests/test_adr002_invariants.py
    new: tests/compliance/adr002/test_invariants.py
  - old: tests/test_outputs_csv.py
    new: tests/unit/plugins/nodes/sinks/csv/test_write.py
  - old: tests/test_llm_azure.py
    new: tests/unit/plugins/nodes/transforms/llm/test_azure_openai.py
```

**Import Update Patterns**:
- `from ..plugins.sinks.csv import X` → `from elspeth.plugins.nodes.sinks.csv import X`
- `from elspeth.plugins.sinks.csv import X` → `from elspeth.plugins.nodes.sinks.csv import X`
- `from conftest import X` → `from ...conftest import X` (adjusts relative depth)

---

## Installation & Setup

### Prerequisites

```bash
# Python 3.12+
python --version

# Install PyYAML for migrate_tests.py
pip install pyyaml
```

### Copy Scripts to Project Root

```bash
# When ready to execute (after ADR-002-003-004 unblocks)
cp docs/migration/test-suite-reorganization/*.py scripts/

# Make executable
chmod +x scripts/audit_tests.py
chmod +x scripts/find_duplicates.py
chmod +x scripts/analyze_fixtures.py
chmod +x scripts/migrate_tests.py
```

---

## Execution Workflow

### Phase 1: Audit (6-8 hours)

```bash
# Step 1: Audit test metadata
python scripts/audit_tests.py \
    --test-dir tests \
    --output docs/migration/test-suite-reorganization/TEST_AUDIT_REPORT.md

# Step 2: Find duplicates
python scripts/find_duplicates.py \
    --test-dir tests \
    --output docs/migration/test-suite-reorganization/DUPLICATES_ANALYSIS.md \
    --threshold 0.85

# Step 3: Analyze fixtures
python scripts/analyze_fixtures.py \
    --test-dir tests \
    --output docs/migration/test-suite-reorganization/FIXTURE_ANALYSIS.md

# Step 4: Review reports
# (Manual stakeholder review of generated reports)
```

---

### Phase 2: Reorganization (10-14 hours)

```bash
# Prepare FILE_MAPPING.yaml based on Phase 1 analysis
# (Manual: Create mapping file)

# Step 1: Dry run
python scripts/migrate_tests.py move \
    --mapping FILE_MAPPING.yaml \
    --dry-run

# Step 2: Execute moves (batch by batch)
python scripts/migrate_tests.py move \
    --mapping FILE_MAPPING_BATCH1.yaml  # Compliance tests
pytest tests/compliance/ -v  # Verify

python scripts/migrate_tests.py move \
    --mapping FILE_MAPPING_BATCH2.yaml  # Sink tests
pytest tests/unit/plugins/nodes/sinks/ -v  # Verify

# ... continue for all batches ...

# Step 3: Update imports
python scripts/migrate_tests.py update-imports \
    --test-dir tests/ \
    --dry-run  # Preview

python scripts/migrate_tests.py update-imports \
    --test-dir tests/  # Execute

# Step 4: Verify
pytest --collect-only -q
pytest -v
```

---

## Troubleshooting

### Script fails with "ModuleNotFoundError"

**Cause**: Script can't find elspeth package

**Solution**:
```bash
# Add project root to PYTHONPATH
export PYTHONPATH="/home/john/elspeth:$PYTHONPATH"

# Or install in editable mode
pip install -e .
```

---

### audit_tests.py shows "Syntax error"

**Cause**: Test file has syntax error (Python 3.12 required)

**Solution**: Fix syntax error in test file, or exclude from analysis

---

### migrate_tests.py "git mv" fails

**Cause**: Target directory doesn't exist

**Solution**: Create directories first (script should do this, but verify)

---

### Import updates break tests

**Cause**: Complex import patterns not handled by script

**Solution**: Manual import fixes, or update `migrate_tests.py` patterns

---

## Testing the Scripts

Before executing on real test suite:

```bash
# Test on small subset
mkdir /tmp/test_sample
cp tests/test_config.py /tmp/test_sample/
cp tests/conftest.py /tmp/test_sample/

python scripts/audit_tests.py --test-dir /tmp/test_sample --output /tmp/audit.md
cat /tmp/audit.md  # Verify report format

# Clean up
rm -rf /tmp/test_sample
```

---

## Script Maintenance

**Location during planning**: `docs/migration/test-suite-reorganization/`

**Location during execution**: `scripts/` (copy when ready)

**Version control**: Scripts are committed, tested, ready for use

**Updates**: If patterns change, update scripts in planning directory first, test, then copy to scripts/

---

## Success Criteria

✅ All scripts executable (`python script.py --help` works)
✅ All scripts tested on sample data
✅ Reports generate correctly (markdown format)
✅ Dry-run mode works (shows changes without executing)
✅ Scripts handle edge cases (syntax errors, missing files)
✅ Documentation complete

---

**Last Updated**: 2025-10-27 (Scripts implemented and documented)
**Status**: ✅ Ready for execution post-blocker
**Author**: Architecture Team
