# Phase 0: Consolidate Existing Subdirectories

**Objective**: Merge redundant test hierarchies into unified structure BEFORE main reorganization

**Estimated Effort**: 3-4 hours
**Prerequisites**: None (executes before Phase 1)
**Risk Level**: Low (small file count, clear conflicts)

---

## Executive Summary

**Problem**: Test suite has **multiple competing hierarchies** created over time:
- `tests/sinks/` (11 files) - Legacy location
- `tests/plugins/sinks/` (10 files) - Partially migrated
- `tests/plugins/nodes/sinks/` (1 file) - New ADR-aligned structure

**Without Phase 0**: Phase 2 will attempt to move files TO locations that already contain files, creating merge conflicts and duplicate tests.

**With Phase 0**: Consolidate all existing subdirectories into **single unified structure** aligned with `src/elspeth/`, then Phase 1-3 proceed cleanly.

**Scope**: 58 files in existing subdirectories (26% of test suite)

---

## Current State Inventory

### Existing Subdirectories (58 files)

```
tests/adapters/          1 file   (blob store config)
tests/cli/               7 files  (CLI subcommands, schema validation)
tests/middleware/        4 files  (Azure middleware)
tests/orchestrators/     1 file   (experiment lazy import)
tests/plugins/
  ├── experiments/       1 file   (stats helpers)
  ├── nodes/
  │   ├── sinks/         1 file   (reproducibility bundle)
  │   ├── sources/       1 file   (CSV allowed base)
  │   └── transforms/
  │       └── llm/       2 files  (Azure/HTTP OpenAI clients)
  ├── sinks/            10 files  (repository, visual, zip edges)
  ├── sources/           2 files  (blob/CSV edges)
  ├── utilities/         1 file   (retrieval context)
  └── <root>/            1 file   (classified middleware)
tests/retrieval/         6 files  (embedding, pgvector, search)
tests/security/          5 files  (keyvault, signing, hardening)
tests/signed/            1 file   (signed sink env)
tests/sinks/            11 files  (blob, bundle, repro, embeddings)
tests/tools/             2 files  (reporting helpers/viz)
tests/utils/             1 file   (logging)
```

**Total**: 58 files

---

## Redundancy Analysis

### Conflict 1: Sink Tests (3 competing locations)

**tests/sinks/** (11 files):
- `test_blob_sink_edges.py`
- `test_blob_sink_uploads.py`
- `test_embeddings_azure_embedder_requires_endpoint.py`
- `test_local_bundle_success.py`
- `test_repo_sinks.py`
- `test_repository_more_edges.py`
- `test_repro_bundle_*.py` (5 files)
- `test_signed_sink_error_skip.py`

**tests/plugins/sinks/** (10 files):
- `test_azure_devops_repo_edges.py`
- `test_csv_sink_edges.py`
- `test_excel_sink_edges.py`
- `test_repository_edges.py`
- `test_repository_helpers.py`
- `test_visual_base_*.py` (2 files)
- `test_visual_sinks_*.py` (2 files)
- `test_zip_sink_edges.py`

**tests/plugins/nodes/sinks/** (1 file):
- `test_reproducibility_bundle.py`

**Resolution**: Merge ALL to `tests/plugins/nodes/sinks/` (ADR-aligned)

---

### Conflict 2: Source Tests (2 competing locations)

**tests/plugins/sources/** (2 files):
- `test_blob_datasource.py`
- `test_csv_base_edges.py`

**tests/plugins/nodes/sources/** (1 file):
- `test_csv_allowed_base.py`

**Resolution**: Merge ALL to `tests/plugins/nodes/sources/`

---

### Conflict 3: CLI Tests (isolated but messy)

**tests/cli/** (7 files):
- All CLI-related, no conflicts
- BUT: 12+ more CLI tests in root `tests/test_cli_*.py`

**Resolution**: Keep in `tests/cli/`, will absorb root CLI tests in Phase 2

---

## Consolidation Strategy

### Rule 1: Prefer ADR-Aligned Locations

**Priority order**:
1. `tests/plugins/nodes/` (aligns with `src/elspeth/plugins/nodes/`)
2. `tests/plugins/` (fallback for experiments, utilities)
3. `tests/<category>/` (delete after merge)

**Rationale**: Phase 2-3 will create `tests/unit/plugins/nodes/`, so starting from aligned location minimizes future moves.

---

### Rule 2: Use `git mv` for History Preservation

```bash
# Preserve file history
git mv tests/sinks/test_blob_sink_edges.py \
       tests/plugins/nodes/sinks/test_blob_sink_edges.py
```

---

### Rule 3: Organize by Concern Within Target

After consolidation, `tests/plugins/nodes/sinks/` should have:
```
tests/plugins/nodes/sinks/
├── blob/
│   ├── test_blob_sink_edges.py
│   └── test_blob_sink_uploads.py
├── bundles/
│   ├── test_local_bundle_success.py
│   ├── test_reproducibility_bundle.py
│   └── test_repro_bundle_*.py (5 files)
├── repository/
│   ├── test_azure_devops_repo_edges.py
│   ├── test_repo_sinks.py
│   ├── test_repository_edges.py
│   ├── test_repository_helpers.py
│   └── test_repository_more_edges.py
├── signed/
│   └── test_signed_sink_error_skip.py
├── visual/
│   ├── test_visual_base_more_coverage.py
│   ├── test_visual_base_validation.py
│   ├── test_visual_sinks_edges.py
│   └── test_visual_sinks_more_edges.py
└── utilities/
    ├── test_csv_sink_edges.py
    ├── test_excel_sink_edges.py
    ├── test_embeddings_azure_embedder_requires_endpoint.py
    └── test_zip_sink_edges.py
```

---

## Execution Protocol

### Step 0.1: Backup Current State (15 minutes)

```bash
# Create Phase 0 branch
git checkout -b test-suite-phase0-consolidation
git commit --allow-empty -m "Checkpoint: Before Phase 0 consolidation"

# Document current structure
find tests -type d -not -path "*/\.*" | sort > PHASE0_BEFORE.txt
find tests -name "test_*.py" | wc -l  # Should be ~218
```

---

### Step 0.2: Create Target Directories (15 minutes)

```bash
# Create unified sink structure
mkdir -p tests/plugins/nodes/sinks/{blob,bundles,repository,signed,visual,utilities}

# Create unified source structure
mkdir -p tests/plugins/nodes/sources/{csv,blob}

# Create unified transform structure (already exists)
# tests/plugins/nodes/transforms/llm/ exists with 2 files

# Keep existing:
# tests/cli/ (7 files)
# tests/middleware/ (4 files)
# tests/retrieval/ (6 files)
# tests/security/ (5 files)
# tests/signed/ (1 file)
# tests/tools/ (2 files)
# tests/utils/ (1 file)
```

---

### Step 0.3: Consolidate Sink Tests (1-1.5 hours)

#### Batch A: Blob Sinks
```bash
git mv tests/sinks/test_blob_sink_edges.py \
       tests/plugins/nodes/sinks/blob/test_blob_sink_edges.py
git mv tests/sinks/test_blob_sink_uploads.py \
       tests/plugins/nodes/sinks/blob/test_blob_sink_uploads.py

# Verify
pytest tests/plugins/nodes/sinks/blob/ --collect-only -q
git commit -m "test(phase0): Consolidate blob sink tests"
```

#### Batch B: Bundle Sinks
```bash
git mv tests/sinks/test_local_bundle_success.py \
       tests/plugins/nodes/sinks/bundles/test_local_bundle_success.py
git mv tests/plugins/nodes/sinks/test_reproducibility_bundle.py \
       tests/plugins/nodes/sinks/bundles/test_reproducibility_bundle.py
git mv tests/sinks/test_repro_bundle_filter.py \
       tests/plugins/nodes/sinks/bundles/test_repro_bundle_filter.py
git mv tests/sinks/test_repro_bundle_internal.py \
       tests/plugins/nodes/sinks/bundles/test_repro_bundle_internal.py
git mv tests/sinks/test_repro_bundle_plugins_edges.py \
       tests/plugins/nodes/sinks/bundles/test_repro_bundle_plugins_edges.py
git mv tests/sinks/test_repro_bundle_variants.py \
       tests/plugins/nodes/sinks/bundles/test_repro_bundle_variants.py

pytest tests/plugins/nodes/sinks/bundles/ --collect-only -q
git commit -m "test(phase0): Consolidate bundle sink tests"
```

#### Batch C: Repository Sinks
```bash
git mv tests/plugins/sinks/test_azure_devops_repo_edges.py \
       tests/plugins/nodes/sinks/repository/test_azure_devops_repo_edges.py
git mv tests/sinks/test_repo_sinks.py \
       tests/plugins/nodes/sinks/repository/test_repo_sinks.py
git mv tests/plugins/sinks/test_repository_edges.py \
       tests/plugins/nodes/sinks/repository/test_repository_edges.py
git mv tests/plugins/sinks/test_repository_helpers.py \
       tests/plugins/nodes/sinks/repository/test_repository_helpers.py
git mv tests/sinks/test_repository_more_edges.py \
       tests/plugins/nodes/sinks/repository/test_repository_more_edges.py

pytest tests/plugins/nodes/sinks/repository/ --collect-only -q
git commit -m "test(phase0): Consolidate repository sink tests"
```

#### Batch D: Visual Sinks
```bash
git mv tests/plugins/sinks/test_visual_base_more_coverage.py \
       tests/plugins/nodes/sinks/visual/test_visual_base_more_coverage.py
git mv tests/plugins/sinks/test_visual_base_validation.py \
       tests/plugins/nodes/sinks/visual/test_visual_base_validation.py
git mv tests/plugins/sinks/test_visual_sinks_edges.py \
       tests/plugins/nodes/sinks/visual/test_visual_sinks_edges.py
git mv tests/plugins/sinks/test_visual_sinks_more_edges.py \
       tests/plugins/nodes/sinks/visual/test_visual_sinks_more_edges.py

pytest tests/plugins/nodes/sinks/visual/ --collect-only -q
git commit -m "test(phase0): Consolidate visual sink tests"
```

#### Batch E: Utility Sinks
```bash
git mv tests/plugins/sinks/test_csv_sink_edges.py \
       tests/plugins/nodes/sinks/utilities/test_csv_sink_edges.py
git mv tests/plugins/sinks/test_excel_sink_edges.py \
       tests/plugins/nodes/sinks/utilities/test_excel_sink_edges.py
git mv tests/sinks/test_embeddings_azure_embedder_requires_endpoint.py \
       tests/plugins/nodes/sinks/utilities/test_embeddings_azure_embedder_requires_endpoint.py
git mv tests/plugins/sinks/test_zip_sink_edges.py \
       tests/plugins/nodes/sinks/utilities/test_zip_sink_edges.py

pytest tests/plugins/nodes/sinks/utilities/ --collect-only -q
git commit -m "test(phase0): Consolidate utility sink tests"
```

#### Batch F: Signed Sinks
```bash
git mv tests/sinks/test_signed_sink_error_skip.py \
       tests/plugins/nodes/sinks/signed/test_signed_sink_error_skip.py

pytest tests/plugins/nodes/sinks/signed/ --collect-only -q
git commit -m "test(phase0): Consolidate signed sink tests"
```

---

### Step 0.4: Consolidate Source Tests (30 minutes)

```bash
# Move to unified location
git mv tests/plugins/sources/test_blob_datasource.py \
       tests/plugins/nodes/sources/blob/test_blob_datasource.py
git mv tests/plugins/sources/test_csv_base_edges.py \
       tests/plugins/nodes/sources/csv/test_csv_base_edges.py
# test_csv_allowed_base.py already in tests/plugins/nodes/sources/, move to csv/
git mv tests/plugins/nodes/sources/test_csv_allowed_base.py \
       tests/plugins/nodes/sources/csv/test_csv_allowed_base.py

pytest tests/plugins/nodes/sources/ --collect-only -q
git commit -m "test(phase0): Consolidate source tests"
```

---

### Step 0.5: Clean Up Empty Directories (15 minutes)

```bash
# Remove now-empty directories
rmdir tests/sinks tests/plugins/sinks tests/plugins/sources 2>/dev/null || true

# Verify
find tests -type d -empty | xargs rmdir 2>/dev/null || true

git commit -m "test(phase0): Remove empty directories"
```

---

### Step 0.6: Verification (30 minutes)

#### Verification Checklist

- [ ] All 58 files accounted for (no files lost)
- [ ] tests/sinks/ empty (or deleted)
- [ ] tests/plugins/sinks/ empty (or deleted)
- [ ] tests/plugins/nodes/sinks/ contains 22 files (11 from tests/sinks + 10 from tests/plugins/sinks + 1 existing)
- [ ] tests/plugins/nodes/sources/ contains 3 files
- [ ] All tests collect successfully: `pytest --collect-only -q`
- [ ] Full test suite runs: `pytest -v`
- [ ] Git history preserved: `git log --follow tests/plugins/nodes/sinks/blob/test_blob_sink_edges.py`

#### Commands

```bash
# Count files moved
find tests/plugins/nodes/sinks -name "test_*.py" | wc -l
# Expected: 22

find tests/plugins/nodes/sources -name "test_*.py" | wc -l
# Expected: 3

# Verify no stragglers
find tests/sinks tests/plugins/sinks tests/plugins/sources -name "test_*.py" 2>/dev/null | wc -l
# Expected: 0 (or error if dirs deleted)

# Collect all tests
pytest --collect-only -q | tail -1
# Expected: Same test count as before Phase 0 (~1,800 tests)

# Run full suite
pytest -v --tb=short

# Verify history
git log --follow --oneline tests/plugins/nodes/sinks/blob/test_blob_sink_edges.py | head -5
# Should show history from tests/sinks/test_blob_sink_edges.py
```

---

## Phase 0 Deliverables

- [ ] All sink tests consolidated into `tests/plugins/nodes/sinks/`
- [ ] All source tests consolidated into `tests/plugins/nodes/sources/`
- [ ] Empty directories removed
- [ ] All tests passing
- [ ] Git history preserved
- [ ] `PHASE0_SUMMARY.md` generated

---

## Rollback Strategy

**If Phase 0 fails**:
```bash
# Revert to pre-Phase 0 state
git reset --hard origin/main
git branch -D test-suite-phase0-consolidation
```

**Partial rollback** (revert specific batch):
```bash
git revert <commit-sha>
```

---

## Success Criteria

✅ **22 sink test files in tests/plugins/nodes/sinks/**
✅ **3 source test files in tests/plugins/nodes/sources/**
✅ **0 files in tests/sinks/, tests/plugins/sinks/, tests/plugins/sources/**
✅ **All tests passing**
✅ **Git history preserved**
✅ **Test count unchanged**

---

## Next Steps

Once Phase 0 complete:
1. Generate `PHASE0_SUMMARY.md` (file count, mappings)
2. Update `README.md` status tracker
3. Proceed to Phase 1: `00-AUDIT_METHODOLOGY.md`

---

**Phase 0 Time Estimate**: 3-4 hours
**Risk Level**: Low (small scope, clear conflicts, easily reversible)
**Dependencies**: None (executes first)

**Last Updated**: 2025-10-27
**Author**: Architecture Team
