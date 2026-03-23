# Errorworks Migration — Replace In-Tree Chaos Modules with `errorworks` Package

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the in-tree `elspeth.testing.chaos{engine,llm,web,llm_mcp}` modules with the `errorworks` PyPI package (v0.1.1), eliminating ~30 maintained source files and ~1,500 lines of duplicated code.

**Architecture:** The chaos modules have zero coupling to ELSPETH internals (no imports from `contracts/`, `core/`, or `engine/`). They were extracted into the standalone `errorworks` package which is already published on PyPI. errorworks 0.1.1 is a superset of the in-tree code with additional hardening (admin auth, input validation, StrEnum types). The migration is a mechanical import rewrite + dependency swap + directory deletion.

**Tech Stack:** `errorworks>=0.1.1` (PyPI), `uv` for dependency management, `pytest` for validation.

---

## Import Path Mapping

| In-tree path | errorworks path |
|---|---|
| `elspeth.testing.chaosengine` | `errorworks.engine` |
| `elspeth.testing.chaosengine.types` | `errorworks.engine.types` |
| `elspeth.testing.chaosengine.injection_engine` | `errorworks.engine.injection_engine` |
| `elspeth.testing.chaosengine.latency` | `errorworks.engine.latency` |
| `elspeth.testing.chaosengine.metrics_store` | `errorworks.engine.metrics_store` |
| `elspeth.testing.chaosengine.config_loader` | `errorworks.engine.config_loader` |
| `elspeth.testing.chaosengine.vocabulary` | `errorworks.engine.vocabulary` |
| `elspeth.testing.chaosllm` | `errorworks.llm` |
| `elspeth.testing.chaosllm.config` | `errorworks.llm.config` |
| `elspeth.testing.chaosllm.server` | `errorworks.llm.server` |
| `elspeth.testing.chaosllm.error_injector` | `errorworks.llm.error_injector` |
| `elspeth.testing.chaosllm.metrics` | `errorworks.llm.metrics` |
| `elspeth.testing.chaosllm.response_generator` | `errorworks.llm.response_generator` |
| `elspeth.testing.chaosllm.cli` | `errorworks.llm.cli` |
| `elspeth.testing.chaosweb` | `errorworks.web` |
| `elspeth.testing.chaosweb.config` | `errorworks.web.config` |
| `elspeth.testing.chaosweb.server` | `errorworks.web.server` |
| `elspeth.testing.chaosweb.content_generator` | `errorworks.web.content_generator` |
| `elspeth.testing.chaosweb.error_injector` | `errorworks.web.error_injector` |
| `elspeth.testing.chaosweb.metrics` | `errorworks.web.metrics` |
| `elspeth.testing.chaosweb.cli` | `errorworks.web.cli` |
| `elspeth.testing.chaosllm_mcp` | `errorworks.llm_mcp` |
| `elspeth.testing.chaosllm_mcp.server` | `errorworks.llm_mcp.server` |

## API Differences (errorworks 0.1.1 vs in-tree)

1. **`SelectionMode` StrEnum** — `errorworks.engine.types.SelectionMode` replaces bare `"priority"`/`"weighted"` strings. The enum accepts string values via `StrEnum`, so `SelectionMode("priority")` works. Existing string comparisons (`== "priority"`) will still work against StrEnum values due to `StrEnum` semantics.
2. **`SqlType` StrEnum** — `errorworks.engine.types.SqlType` replaces `_VALID_SQL_TYPES` frozenset. Tests referencing the frozenset directly need updating.
3. **`_get_current_config()` → `get_current_config()`** — Made public in errorworks. Any test that calls or mocks the private method needs updating.
4. **`get_admin_token()` method** — New public method on server classes. No action needed (additive).
5. **`admin.py` module** — Admin endpoint logic extracted. No direct test impact unless tests mock internal handler functions.
6. **`validators.py` module** — New shared validation. No action needed (additive).
7. **`DANGEROUS_BIND_HOSTS` constant** — New export from `errorworks.engine.types`. No action needed (additive).

## Files Affected

**Delete (4 directories, ~30 files):**
- `src/elspeth/testing/chaosengine/` (8 files + `__pycache__`)
- `src/elspeth/testing/chaosllm/` (7 files + `presets/` dir)
- `src/elspeth/testing/chaosweb/` (7 files + `presets/` dir)
- `src/elspeth/testing/chaosllm_mcp/` (2 files)

**Modify — source:**
- `pyproject.toml` — add dep, remove entry points, remove chaos-only deps
- `src/elspeth/cli.py:28-29,72-73` — repoint CLI imports
- `src/elspeth/testing/__init__.py:1-16` — update docstring

**Modify — test fixtures:**
- `tests/fixtures/chaosllm.py:19-23` — repoint imports
- `tests/fixtures/chaosweb.py:34-35` — repoint imports

**Modify — conftest files (import-only changes):**
- `tests/performance/stress/conftest.py` — chaos config imports
- (conftest files that only re-export fixtures need no change — they import from `tests.fixtures.*`)

**Modify — unit tests (~20 files):**
- `tests/unit/testing/chaosengine/` — all test files
- `tests/unit/testing/chaosllm/` — all test files
- `tests/unit/testing/chaosweb/` — all test files
- `tests/unit/testing/chaosllm_mcp/` — all test files

**Modify — property tests (~3 files):**
- `tests/property/testing/` — all chaos-related property tests

**Modify — integration tests:**
- Any files under `tests/integration/plugins/llm/` importing chaos modules directly

**Modify — other:**
- `tests/unit/plugins/test_post_init_validations.py` — conditional chaos imports
- `config/cicd/enforce_tier_model/testing.yaml` — remove chaos module allowlist entries

**NOT modified (verified no chaos imports):**
- `tests/unit/testing/chaosllm/conftest.py` — imports from `tests.fixtures.chaosllm`, not the module
- `tests/unit/testing/chaosweb/conftest.py` — same pattern
- `tests/integration/plugins/llm/conftest.py` — same pattern

---

### Task 1: Add `errorworks` dependency and install

**Files:**
- Modify: `pyproject.toml:69-91` (dev extras)

- [ ] **Step 1: Add errorworks to dev dependencies**

In `pyproject.toml`, in the `[project.optional-dependencies]` `dev` list, replace the ChaosLLM-specific starlette/uvicorn comments and add errorworks. Keep starlette and uvicorn since they're still needed by test fixtures (TestClient).

```toml
# In dev = [...]
# Replace these two lines:
#    "starlette>=0.45,<1",  # ASGI framework for ChaosLLM
#    "uvicorn>=0.34,<1",  # ASGI server for ChaosLLM
# With:
    "errorworks>=0.1.1",  # Chaos testing servers (ChaosLLM, ChaosWeb)
    "starlette>=0.45,<1",  # ASGI framework (needed for TestClient in fixtures)
```

Do the same in the `all = [...]` section (lines 161-162) — replace:
```toml
    "starlette>=0.45,<1",
    "uvicorn>=0.34,<1",
```
with:
```toml
    "errorworks>=0.1.1",
    "starlette>=0.45,<1",
```

Note: `uvicorn` can be dropped from elspeth's deps entirely — errorworks pulls it transitively, and elspeth's test fixtures only need `starlette.testclient.TestClient` (which doesn't need uvicorn).

- [ ] **Step 2: Install and verify**

Run: `cd /home/john/elspeth && uv pip install -e ".[dev]"`
Expected: Successful install with errorworks 0.1.1 in the environment.

Run: `python -c "import errorworks; print(errorworks.__version__)"`
Expected: `0.1.1`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add errorworks dependency for chaos module migration"
```

---

### Task 2: Repoint test fixtures to errorworks

These are the central integration point — all test files use chaos servers through these fixtures. Fix them first so the fixture→module path is clean before touching tests.

**Files:**
- Modify: `tests/fixtures/chaosllm.py:19-23`
- Modify: `tests/fixtures/chaosweb.py:34-35`

- [ ] **Step 1: Update chaosllm fixture imports**

In `tests/fixtures/chaosllm.py`, change:
```python
# Old (lines 19-23):
from elspeth.testing.chaosllm.config import (
    ChaosLLMConfig,
    load_config,
)
from elspeth.testing.chaosllm.server import ChaosLLMServer

# New:
from errorworks.llm.config import (
    ChaosLLMConfig,
    load_config,
)
from errorworks.llm.server import ChaosLLMServer
```

- [ ] **Step 2: Update chaosweb fixture imports**

In `tests/fixtures/chaosweb.py`, change:
```python
# Old (lines 34-35):
from elspeth.testing.chaosweb.config import ChaosWebConfig, load_config
from elspeth.testing.chaosweb.server import ChaosWebServer

# New:
from errorworks.web.config import ChaosWebConfig, load_config
from errorworks.web.server import ChaosWebServer
```

- [ ] **Step 3: Run fixture-dependent tests to verify**

Run: `.venv/bin/python -m pytest tests/unit/testing/chaosllm/test_server.py -x -v --timeout=30 2>&1 | head -40`
Expected: Tests still pass (fixtures now import from errorworks).

Run: `.venv/bin/python -m pytest tests/unit/testing/chaosweb/test_server.py -x -v --timeout=30 2>&1 | head -40`
Expected: Tests still pass.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/chaosllm.py tests/fixtures/chaosweb.py
git commit -m "refactor: repoint test fixtures to errorworks imports"
```

---

### Task 3: Repoint chaosengine unit tests

**Files:**
- Modify: all `tests/unit/testing/chaosengine/test_*.py` files

- [ ] **Step 1: List files to update**

Run: `find tests/unit/testing/chaosengine -name "test_*.py" -type f | sort`

- [ ] **Step 2: Rewrite imports in each file**

Apply this substitution across all files in the directory:
- `from elspeth.testing.chaosengine.` → `from errorworks.engine.`
- `from elspeth.testing.chaosengine import` → `from errorworks.engine import`

**API change to handle:** If any test references `_VALID_SQL_TYPES` directly, it may need updating to use `SqlType` enum or the new frozenset. If any test compares `selection_mode` with string literals, it still works (StrEnum == str).

- [ ] **Step 3: Run chaosengine tests**

Run: `.venv/bin/python -m pytest tests/unit/testing/chaosengine/ -x -v --timeout=30 2>&1 | tail -20`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/testing/chaosengine/
git commit -m "refactor: repoint chaosengine tests to errorworks.engine"
```

---

### Task 4: Repoint chaosllm unit tests

**Files:**
- Modify: all `tests/unit/testing/chaosllm/test_*.py` files (~8 files)

- [ ] **Step 1: Rewrite imports in each file**

Apply across all files:
- `from elspeth.testing.chaosllm.` → `from errorworks.llm.`
- `from elspeth.testing.chaosllm import` → `from errorworks.llm import`
- `from elspeth.testing.chaosengine.` → `from errorworks.engine.` (some chaosllm tests import engine types)

**API change:** If any test calls `server._get_current_config()`, change to `server.get_current_config()`.

- [ ] **Step 2: Run chaosllm tests**

Run: `.venv/bin/python -m pytest tests/unit/testing/chaosllm/ -x -v --timeout=30 2>&1 | tail -20`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/testing/chaosllm/
git commit -m "refactor: repoint chaosllm tests to errorworks.llm"
```

---

### Task 5: Repoint chaosweb unit tests

**Files:**
- Modify: all `tests/unit/testing/chaosweb/test_*.py` files (~5 files)

- [ ] **Step 1: Rewrite imports in each file**

Apply across all files:
- `from elspeth.testing.chaosweb.` → `from errorworks.web.`
- `from elspeth.testing.chaosweb import` → `from errorworks.web import`
- `from elspeth.testing.chaosengine.` → `from errorworks.engine.`

**API change:** If any test calls `server._get_current_config()`, change to `server.get_current_config()`.

- [ ] **Step 2: Run chaosweb tests**

Run: `.venv/bin/python -m pytest tests/unit/testing/chaosweb/ -x -v --timeout=30 2>&1 | tail -20`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/testing/chaosweb/
git commit -m "refactor: repoint chaosweb tests to errorworks.web"
```

---

### Task 6: Repoint chaosllm_mcp unit tests

**Files:**
- Modify: all `tests/unit/testing/chaosllm_mcp/test_*.py` files

- [ ] **Step 1: Rewrite imports**

- `from elspeth.testing.chaosllm_mcp.` → `from errorworks.llm_mcp.`
- `from elspeth.testing.chaosllm_mcp import` → `from errorworks.llm_mcp import`

- [ ] **Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/testing/chaosllm_mcp/ -x -v --timeout=30 2>&1 | tail -20`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/testing/chaosllm_mcp/
git commit -m "refactor: repoint chaosllm_mcp tests to errorworks.llm_mcp"
```

---

### Task 7: Repoint property tests and integration tests

**Files:**
- Modify: `tests/property/testing/` — chaos-related property test files
- Modify: `tests/integration/plugins/llm/` — any files importing chaos modules directly
- Modify: `tests/performance/stress/conftest.py` — chaos config imports
- Modify: `tests/unit/plugins/test_post_init_validations.py` — conditional chaos imports

- [ ] **Step 1: Find all remaining import sites**

Run: `grep -rn "from elspeth\.testing\.chaos" tests/ --include="*.py" | grep -v __pycache__`

This should show only the files not yet updated (property, integration, stress, plugin validation tests).

- [ ] **Step 2: Rewrite imports in each file**

Apply the same substitution pattern:
- `elspeth.testing.chaosengine` → `errorworks.engine`
- `elspeth.testing.chaosllm` → `errorworks.llm`
- `elspeth.testing.chaosweb` → `errorworks.web`
- `elspeth.testing.chaosllm_mcp` → `errorworks.llm_mcp`

For `tests/performance/stress/conftest.py`: Update the chaos config and server imports.

For `tests/unit/plugins/test_post_init_validations.py`: This file has inline imports at function scope (not try/except blocks). Update the import paths in each function body.

- [ ] **Step 3: Run affected tests**

Run: `.venv/bin/python -m pytest tests/property/testing/ -x -v --timeout=60 2>&1 | tail -20`
Run: `.venv/bin/python -m pytest tests/unit/plugins/test_post_init_validations.py -x -v --timeout=30 2>&1 | tail -20`
Expected: All pass.

- [ ] **Step 4: Verify no remaining old imports in tests/**

Run: `grep -rn "from elspeth\.testing\.chaos" tests/ --include="*.py" | grep -v __pycache__`
Expected: Zero matches.

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "refactor: repoint remaining test imports to errorworks"
```

---

### Task 8: Update CLI integration

**Files:**
- Modify: `src/elspeth/cli.py:28-29,72-73`

- [ ] **Step 1: Update CLI imports and registration**

In `src/elspeth/cli.py`, change:
```python
# Old (lines 28-29):
from elspeth.testing.chaosllm.cli import app as chaosllm_app
from elspeth.testing.chaosllm.cli import mcp_app as chaosllm_mcp_app

# New:
from errorworks.llm.cli import app as chaosllm_app
from errorworks.llm.cli import mcp_app as chaosllm_mcp_app
```

Lines 72-73 (the `app.add_typer()` calls) remain unchanged — they just reference the local variable names.

- [ ] **Step 2: Verify CLI works**

Run: `cd /home/john/elspeth && .venv/bin/python -m elspeth.cli chaosllm --help`
Expected: ChaosLLM help text appears.

Run: `.venv/bin/python -m elspeth.cli chaosllm-mcp --help`
Expected: ChaosLLM MCP help text appears.

- [ ] **Step 3: Commit**

```bash
git add src/elspeth/cli.py
git commit -m "refactor: repoint CLI chaos subcommands to errorworks"
```

---

### Task 9: Update pyproject.toml entry points

**Files:**
- Modify: `pyproject.toml:190-193`

- [ ] **Step 1: Remove elspeth chaos entry points**

The `errorworks` package already provides `chaosengine`, `chaosllm`, `chaosllm-mcp`, and `chaosweb` console scripts. Remove the duplicate entries from elspeth's `[project.scripts]`:

```toml
# Remove these 4 lines:
chaosengine = "elspeth.testing.chaosengine.cli:main"
chaosllm = "elspeth.testing.chaosllm.cli:main"
chaosllm-mcp = "elspeth.testing.chaosllm.cli:mcp_main_entry"
chaosweb = "elspeth.testing.chaosweb.cli:main"
```

Keep `elspeth`, `elspeth-mcp`, and `check-contracts`.

- [ ] **Step 2: Reinstall to update entry points**

Run: `cd /home/john/elspeth && uv pip install -e ".[dev]"`

- [ ] **Step 3: Verify entry points work**

Run: `chaosllm --help`
Expected: Help text from errorworks (not elspeth).

Run: `chaosweb --help`
Expected: Help text from errorworks.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: remove chaos CLI entry points — now provided by errorworks"
```

---

### Task 10: Update testing package docstring

**Files:**
- Modify: `src/elspeth/testing/__init__.py:1-16`

- [ ] **Step 1: Update docstring**

Replace lines 1-16:
```python
"""Test infrastructure for ELSPETH pipelines.

Factories for constructing production types with sensible defaults.
When a backbone type's constructor changes, update the factory here.
Tests and benchmarks that use factories need ZERO changes.

Chaos testing servers (ChaosLLM, ChaosWeb, ChaosEngine) have been
extracted to the ``errorworks`` package (PyPI). Import from there:
    from errorworks.llm import ChaosLLMServer
    from errorworks.web import ChaosWebServer
    from errorworks.engine import InjectionEngine

Usage:
    from elspeth.testing import make_row, make_source_row, make_contract
    from elspeth.testing import make_success, make_error, make_gate_continue
"""
```

- [ ] **Step 2: Commit**

```bash
git add src/elspeth/testing/__init__.py
git commit -m "docs: update testing package docstring for errorworks migration"
```

---

### Task 11: Remove tier model allowlist entries for deleted code

**Files:**
- Modify: `config/cicd/enforce_tier_model/testing.yaml`

- [ ] **Step 1: Remove chaos module entries**

Remove all `per_file_rules` entries with patterns matching `testing/chaos*`:
- `testing/chaosengine/config_loader.py`
- `testing/chaosengine/metrics_store.py`
- `testing/chaosllm/config.py`
- `testing/chaosllm/response_generator.py`
- `testing/chaosweb/config.py`
- `testing/chaosweb/content_generator.py`
- `testing/chaosweb/server.py`

Remove all `allow_hits` entries with keys starting `testing/chaos*` (28 entries, lines 51-231).

Keep the `testing/__init__.py` entry (line 2-7) — that's for the test factories, not chaos modules.

- [ ] **Step 2: Verify tier model enforcement still passes**

Run: `.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model`
Expected: Pass (the code being allowlisted is about to be deleted anyway).

- [ ] **Step 3: Commit**

```bash
git add config/cicd/enforce_tier_model/testing.yaml
git commit -m "chore: remove tier model allowlist entries for deleted chaos modules"
```

---

### Task 12: Delete in-tree chaos modules

**Files:**
- Delete: `src/elspeth/testing/chaosengine/` (entire directory)
- Delete: `src/elspeth/testing/chaosllm/` (entire directory)
- Delete: `src/elspeth/testing/chaosweb/` (entire directory)
- Delete: `src/elspeth/testing/chaosllm_mcp/` (entire directory)

- [ ] **Step 1: Verify no remaining imports from deleted modules**

Run: `grep -rn "from elspeth\.testing\.chaos" src/ tests/ --include="*.py" | grep -v __pycache__`
Expected: Zero matches.

- [ ] **Step 2: Delete the directories**

```bash
rm -rf src/elspeth/testing/chaosengine/
rm -rf src/elspeth/testing/chaosllm/
rm -rf src/elspeth/testing/chaosweb/
rm -rf src/elspeth/testing/chaosllm_mcp/
```

- [ ] **Step 3: Verify imports resolve through errorworks**

Run: `python -c "from errorworks.llm import ChaosLLMServer; print('OK')"`
Run: `python -c "from errorworks.web import ChaosWebServer; print('OK')"`
Run: `python -c "from errorworks.engine import InjectionEngine; print('OK')"`
Run: `python -c "from errorworks.llm_mcp import ChaosLLMAnalyzer; print('OK')"`
Expected: All print OK.

- [ ] **Step 4: Commit**

```bash
git add -A  # stages the deletions
git commit -m "refactor: delete in-tree chaos modules — replaced by errorworks package"
```

---

### Task 13: Full test suite validation

- [ ] **Step 1: Run full unit test suite**

Run: `.venv/bin/python -m pytest tests/unit/ -x --timeout=120 2>&1 | tail -30`
Expected: All pass.

- [ ] **Step 2: Run property tests**

Run: `.venv/bin/python -m pytest tests/property/ -x --timeout=120 2>&1 | tail -20`
Expected: All pass.

- [ ] **Step 3: Run type checking**

Run: `.venv/bin/python -m mypy src/elspeth/ 2>&1 | tail -20`
Expected: No new errors (chaos modules are gone, so no type-checking of deleted code).

- [ ] **Step 4: Run linting**

Run: `.venv/bin/python -m ruff check src/ tests/ 2>&1 | tail -20`
Expected: Clean (or pre-existing issues only).

- [ ] **Step 5: Run tier model enforcement**

Run: `.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model`
Expected: Pass.

- [ ] **Step 6: Run config contracts**

Run: `.venv/bin/python -m scripts.check_contracts`
Expected: Pass.

---

### Task 14: Update ruff known-first-party (if needed)

**Files:**
- Possibly modify: `pyproject.toml` ruff isort config

- [ ] **Step 1: Check if errorworks needs to be in known-third-party**

Run: `.venv/bin/python -m ruff check src/ tests/ --select=I 2>&1 | head -20`

If ruff sorts errorworks imports incorrectly (treating it as first-party), add to pyproject.toml:
```toml
[tool.ruff.lint.isort]
known-first-party = ["elspeth"]
known-third-party = ["errorworks"]
```

This is likely unnecessary since ruff auto-detects third-party packages, but verify.

- [ ] **Step 2: Commit if needed**

```bash
git add pyproject.toml
git commit -m "build: add errorworks to ruff known-third-party"
```

---

## Post-Migration Cleanup (Not Part of This Plan)

These items are noted for future work but are out of scope:

1. **Documentation updates** — `docs/reference/chaosllm.md` and `docs/reference/chaosllm-mcp.md` reference `elspeth.testing.chaosllm` paths. Update import examples to use `errorworks`.
2. **Architecture analysis docs** — Several files under `docs/arch-analysis-*` reference the in-tree modules. These are point-in-time snapshots and should not be retroactively edited.
3. **mypy overrides** — If there was a mypy override for `elspeth.testing.chaos*` modules, it can be removed. Check `[[tool.mypy.overrides]]` sections.
4. **Test infrastructure audit** — `docs/audits/test-infrastructure-audit-2026-03-01.md` references in-tree chaos modules.
