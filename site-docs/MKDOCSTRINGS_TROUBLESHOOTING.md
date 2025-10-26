# MkDocstrings Import Failure Troubleshooting

**Status**: ✅ RESOLVED (2025-10-26)
**Discovered**: 2025-10-26 (during critical issues fix-up)
**Resolution**: Two-part fix: (1) Install Elspeth package in docs build, (2) Add missing `src/elspeth/plugins/__init__.py`
**Impact**: Was blocking all API documentation using mkdocstrings `::: module.path` syntax

---

## Resolution Summary

The mkdocstrings import failure was caused by **two independent issues**:

### Issue 1: Package Not Installed in Build Environment

**Root Cause**: The Elspeth package was not installed in the documentation build environment. mkdocstrings requires the package to be importable via Python's standard import mechanism.

**Fix**: Added `python -m pip install -e . --no-deps` to both:
- `Makefile` `docs-deps` target (line 75)
- `.github/workflows/docs.yml` CI workflow (lines 48, 123)

### Issue 2: Missing `__init__.py` in `plugins/` Directory

**Root Cause**: The `src/elspeth/plugins/` directory was missing an `__init__.py` file, making it a namespace package that griffe (mkdocstrings' introspection library) could not traverse.

**Symptom**: Even after installing the package, griffe failed with `KeyError: 'plugins'` when trying to load `elspeth.plugins.experiments.aggregators`.

**Fix**: Created `/home/john/elspeth/src/elspeth/plugins/__init__.py` with minimal content:
```python
"""Elspeth plugin system."""
```

### Verification

After both fixes:
```bash
$ make docs-deps
$ ../.venv/bin/mkdocs build
INFO    -  Documentation built in 1.88 seconds
```

The generated HTML now includes full mkdocstrings API documentation with method signatures, inheritance trees, and cross-linking.

---

## Problem Statement (Original)

The MkDocs build fails when trying to auto-generate API documentation from Python docstrings using the mkdocstrings plugin. The error occurs for **all** plugin classes across datasources, transforms, sinks, aggregators, and baselines.

### Error Symptoms

```bash
$ cd site-docs && ../.venv/bin/mkdocs build --strict

INFO    -  Doc file 'api-reference/plugins/generated-aggregators.md' contains a mkdocstrings query but the plugin is not installed.
WARNING -  mkdocstrings: elspeth.plugins.experiments.aggregators.cost_summary.CostSummaryAggregator could not be found
WARNING -  mkdocstrings: elspeth.plugins.experiments.aggregators.latency_summary.LatencySummaryAggregator could not be found
WARNING -  mkdocstrings: elspeth.plugins.experiments.aggregators.rationale_analysis.RationaleAnalysisAggregator could not be found
[... repeated for all plugins ...]
ERROR   -  Error reading page 'api-reference/plugins/generated-aggregators.md': could not collect 'elspeth.plugins.experiments.aggregators.cost_summary.CostSummaryAggregator'
```

**Pattern**: mkdocstrings cannot resolve **any** Elspeth module paths when invoked from `site-docs/` context.

---

## What We've Verified

### ✅ Classes Exist and Are Importable

Direct Python imports from the repository root work correctly:

```bash
$ python -c "from elspeth.plugins.experiments.aggregators.cost_summary import CostSummaryAggregator; print(CostSummaryAggregator)"
<class 'elspeth.plugins.experiments.aggregators.cost_summary.CostSummaryAggregator'>
```

All tested classes (CostSummaryAggregator, LatencySummaryAggregator, etc.) import successfully via direct Python import.

### ✅ File Paths Are Correct

```bash
$ ls -la src/elspeth/plugins/experiments/aggregators/cost_summary.py
-rw-r--r-- 1 john john 5.2K Oct 26 10:24 src/elspeth/plugins/experiments/aggregators/cost_summary.py
```

Source files exist at the expected locations.

### ✅ mkdocstrings Plugin Is Installed

```bash
$ ../.venv/bin/pip list | grep mkdocstrings
mkdocstrings                   0.27.0
mkdocstrings-python            1.12.2
```

The mkdocstrings plugin and Python handler are installed via `requirements-docs.lock`.

### ❓ Configuration May Be Incomplete

The `mkdocs.yml` configuration includes:

```yaml
plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          paths: [../src]  # Point to elspeth source code
          options:
            docstring_style: google
            # ... other options ...
```

The `paths: [../src]` directive **should** make `src/elspeth/` discoverable, but mkdocstrings is not resolving imports.

---

## Potential Root Causes

### Hypothesis 1: Python Path Resolution Failure

**Theory**: mkdocstrings runs in the `site-docs/` context but cannot resolve `../src` relative path.

**Evidence**:
- Direct imports work from repo root (`python -c "from elspeth.plugins..."`)
- mkdocstrings imports fail from `site-docs/` context (`cd site-docs && mkdocs build`)

**Test**: Try absolute path instead of relative path in `mkdocs.yml`:
```yaml
paths: [/home/john/elspeth/src]  # Absolute path
```

### Hypothesis 2: Package Not Installed in Build Environment

**Theory**: The Elspeth package is not installed (even in editable mode) in the documentation build environment, so `import elspeth` fails.

**Evidence**:
- `requirements-docs.lock` does **not** include `elspeth` as an editable install
- `make docs-deps` only installs `mkdocs`, `mkdocstrings`, etc.
- The CI workflow (`.github/workflows/docs.yml`) does **not** run `pip install -e .` before building docs

**Test**: Add to `docs-deps` target in Makefile:
```makefile
docs-deps:
	@.venv/bin/python -m pip install -r site-docs/requirements-docs.lock --require-hashes
	@.venv/bin/python -m pip install -e . --no-deps  # Install Elspeth in editable mode
```

### Hypothesis 3: mkdocstrings Python Handler Not Finding Modules

**Theory**: The `mkdocstrings-python` handler is not searching the correct Python path.

**Evidence**:
- `paths: [../src]` should be interpreted relative to `mkdocs.yml` location
- mkdocstrings may be resolving paths incorrectly

**Test**: Add debugging to see what paths mkdocstrings is searching:
```yaml
plugins:
  - mkdocstrings:
      handlers:
        python:
          paths: [../src]
          import:
            - https://docs.python.org/3/objects.inv  # Add external inventories
```

### Hypothesis 4: Namespace Package Issues

**Theory**: Elspeth uses `src/elspeth/` layout, and mkdocstrings may not be handling namespace packages correctly.

**Evidence**:
- `src/elspeth/__init__.py` exists (not a namespace package)
- Layout is standard `src/` layout, widely supported

**Likelihood**: Low (src layout is standard).

---

## Debugging Steps Taken

1. ✅ **Verified class imports directly** → Success (classes exist and are importable)
2. ✅ **Checked mkdocstrings installation** → Installed correctly
3. ✅ **Verified source file paths** → Files exist at expected locations
4. ✅ **Examined mkdocs.yml configuration** → `paths: [../src]` present but not working
5. ⏸️ **Tested absolute paths** → Not yet attempted
6. ⏸️ **Tested installing Elspeth package** → Not yet attempted
7. ⏸️ **Enabled mkdocstrings debug logging** → Not yet attempted

---

## Recommended Solutions (Priority Order)

### Solution 1: Install Elspeth Package in Docs Build Environment ✅ IMPLEMENTED

**Rationale**: mkdocstrings expects `import elspeth` to work, which requires the package to be installed.

**Implementation** (COMPLETED 2025-10-26):

1. **Update Makefile `docs-deps` target**:
   ```makefile
   .PHONY: docs-deps
   docs-deps:  ## Install documentation dependencies from hash-pinned lockfile
       @echo "Installing documentation dependencies..."
       @.venv/bin/python -m pip install -r site-docs/requirements-docs.lock --require-hashes
       @echo "Installing Elspeth package in editable mode (no deps)..."
       @.venv/bin/python -m pip install -e . --no-deps
   ```

2. **Update CI workflow** (`.github/workflows/docs.yml`):
   ```yaml
   - name: Install documentation dependencies
     run: |
       python -m pip install --upgrade pip
       python -m pip install -r site-docs/requirements-docs.lock --require-hashes
       python -m pip install -e . --no-deps  # NEW: Install Elspeth
   ```

3. **Test locally**:
   ```bash
   make docs-deps
   cd site-docs && ../.venv/bin/mkdocs build --strict
   ```

**Expected Outcome**: ✅ mkdocstrings can import Elspeth modules via standard Python import mechanism.

**Note**: Solution 1 alone was NOT sufficient - also required fixing Issue 2 (missing `__init__.py`).

---

### Solution 1.5: Add Missing `__init__.py` to `plugins/` Directory ✅ IMPLEMENTED

**Discovery**: After implementing Solution 1, griffe still failed with `KeyError: 'plugins'`. Investigation revealed the `src/elspeth/plugins/` directory had no `__init__.py`, making it a namespace package that griffe could not traverse.

**Implementation** (COMPLETED 2025-10-26):

Created `/home/john/elspeth/src/elspeth/plugins/__init__.py`:
```python
"""Elspeth plugin system."""
```

**Verification**:
```bash
$ .venv/bin/python -c "import griffe; loader = griffe.GriffeLoader(); module = loader.load('elspeth.plugins.experiments.aggregators.cost_summary'); print('CostSummaryAggregator:', 'CostSummaryAggregator' in module.members)"
CostSummaryAggregator: True
```

**Expected Outcome**: ✅ griffe can now traverse the `elspeth.plugins` namespace and find all plugin classes.

---

### Solution 2: Use Absolute Paths in mkdocs.yml (NOT NEEDED)

**Rationale**: Relative paths (`../src`) may not resolve correctly in all environments.

**Implementation**:

1. **Update `site-docs/mkdocs.yml`**:
   ```yaml
   plugins:
     - mkdocstrings:
         handlers:
           python:
             paths:
               - /home/john/elspeth/src  # Absolute path (dev)
               - ${GITHUB_WORKSPACE}/src  # Absolute path (CI)
   ```

2. **OR** use environment variable:
   ```yaml
   paths:
     - ${ELSPETH_SRC_PATH:-../src}
   ```

   Set in CI:
   ```yaml
   env:
     ELSPETH_SRC_PATH: ${{ github.workspace }}/src
   ```

**Pros**: Explicit path resolution
**Cons**: Less portable (hardcoded paths)

---

### Solution 3: Enable mkdocstrings Debug Logging (DIAGNOSTIC)

**Rationale**: See exactly what paths mkdocstrings is searching.

**Implementation**:

1. **Add to `mkdocs.yml`**:
   ```yaml
   plugins:
     - mkdocstrings:
         handlers:
           python:
             paths: [../src]
             options:
               # ... existing options ...
         log_level: DEBUG  # Enable debug logging
   ```

2. **Run build**:
   ```bash
   cd site-docs && ../.venv/bin/mkdocs build --strict --verbose
   ```

**Expected Output**: Detailed logs showing which paths are searched and why imports fail.

---

### Solution 4: Switch to Manual API Documentation (WORKAROUND - ALREADY DONE)

**Status**: ✅ Implemented as temporary workaround

**What Was Done**:
- Switched navigation to use auto-generated docs (`generated-*.md` files)
- Backed up manual plugin API docs that had incorrect class names
- Auto-generated docs use AST-based generator (`scripts/generate_plugin_docs.py`), not mkdocstrings

**Pros**: Documentation builds successfully
**Cons**: Loses mkdocstrings' rich API rendering (method signatures, inheritance, cross-linking)

---

## Previous Workaround (No Longer Needed)

The documentation previously used **AST-based auto-generated docs** (`generated-*.md`) as a workaround while mkdocstrings was broken. These files:

1. Were generated by `scripts/generate_plugin_docs.py`
2. Included `::: module.path` directives that mkdocstrings processed
3. Are still committed to git (Phase 1 hygiene policy)
4. Are validated for staleness in CI (`.github/workflows/docs.yml`)

**Status**: mkdocstrings now works correctly and renders the `::: module.path` directives in these generated files into full API documentation.

---

## Lessons Learned

1. **mkdocstrings requires package installation**: Even with `paths: [../src]` in config, mkdocstrings/griffe expects the package to be importable via `import package_name`.

2. **Namespace packages break griffe**: Missing `__init__.py` files create namespace packages that griffe cannot traverse. All intermediate directories in the package path need `__init__.py` files.

3. **Test incrementally**: Installing the package (Solution 1) wasn't sufficient alone - the missing `__init__.py` (Solution 1.5) was a separate issue that only surfaced after the first fix.

4. **Direct import ≠ griffe import**: A module being directly importable (`python -c "from elspeth.plugins..."`) doesn't guarantee griffe can introspect it. Griffe has different requirements for package structure.

---

## Related Files

- **Configuration**: `site-docs/mkdocs.yml` (mkdocstrings plugin config)
- **Lockfile**: `site-docs/requirements-docs.lock` (docs dependencies)
- **CI Workflow**: `.github/workflows/docs.yml` (build pipeline)
- **Generator Script**: `scripts/generate_plugin_docs.py` (AST-based fallback)
- **Makefile**: `Makefile` (`docs-deps`, `docs-build`, `docs-serve` targets)

---

## Historical Context

- **PR #14**: Merged formal docs site without validating mkdocstrings worked
- **2025-10-26**: Discovered during critical issues fix-up (peer review follow-up)
- **Current State**: Using AST-based generator as workaround; mkdocstrings unresolved

**Lesson**: Always run `make docs-build` before merging documentation PRs.
