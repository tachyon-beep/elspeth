# Automation Script Specifications

**Scripts to automate Phase 1-3 tasks**

---

## scripts/audit_tests.py

**Purpose**: Extract metadata from all test files (Phase 1.1)

**Usage**:
```bash
python scripts/audit_tests.py \
    --test-dir tests \
    --output TEST_AUDIT_REPORT.md \
    --format markdown
```

**Outputs**: `TEST_AUDIT_REPORT.md`

---

## scripts/find_duplicates.py

**Purpose**: Detect duplicate/overlapping tests (Phase 1.2)

**Usage**:
```bash
python scripts/find_duplicates.py \
    --test-dir tests \
    --coverage-data .coverage \
    --output DUPLICATES_ANALYSIS.md \
    --threshold 0.85
```

**Outputs**: `DUPLICATES_ANALYSIS.md`

---

## scripts/assess_value.py

**Purpose**: Identify low-value tests (Phase 1.3)

**Usage**:
```bash
python scripts/assess_value.py \
    --test-dir tests \
    --audit-report TEST_AUDIT_REPORT.md \
    --output POINTLESS_TESTS_CANDIDATES.md
```

**Outputs**: `POINTLESS_TESTS_CANDIDATES.md`

---

## scripts/migrate_tests.py

**Purpose**: Automated file movement and import updates (Phase 2)

**Usage**:
```bash
# Move files
python scripts/migrate_tests.py move \
    --mapping FILE_MAPPING.yaml \
    --dry-run

# Update imports
python scripts/migrate_tests.py update-imports \
    --test-dir tests/
```

**Note**: All scripts are specifications. Implementation required before Phase 1 execution.

---

**See**: Individual phase documentation for detailed script specifications
