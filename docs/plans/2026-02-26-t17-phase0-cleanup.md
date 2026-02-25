# T17 Phase 0: Remove Dead Fields from PluginContext

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove 5 dead fields and 2 unused methods from PluginContext before the protocol split, reducing the surface area from 20 fields to 15.

**Architecture:** Pure deletion — grep to verify zero usage, delete, fix mypy/tests.

**Tech Stack:** grep, mypy, pytest

---

## Task 1: Remove `plugin_name` field

**Files:**
- Modify: `src/elspeth/contracts/plugin_context.py:102`
- Test: Run full suite to detect breakage

**Step 1: Verify zero usage**

Run: `grep -rn 'plugin_name' src/elspeth/ --include='*.py' | grep -v 'plugin_context.py' | grep -v '__pycache__'`
Expected: Zero matches (or only unrelated occurrences like plugin class `.name` attributes)

**Step 2: Delete the field**

In `src/elspeth/contracts/plugin_context.py`, delete line 102:
```python
    plugin_name: str | None = field(default=None)
```

**Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/ -x --timeout=120 -q`
Expected: All pass

**Step 4: Run mypy**

Run: `.venv/bin/python -m mypy src/`
Expected: Clean

---

## Task 2: Remove `llm_client` and `http_client` fields

**Files:**
- Modify: `src/elspeth/contracts/plugin_context.py:135-136` (fields)
- Modify: `src/elspeth/contracts/plugin_context.py:38-39` (TYPE_CHECKING imports)

**Step 1: Verify zero usage**

Run: `grep -rn 'llm_client\|http_client' src/elspeth/ --include='*.py' | grep -v 'plugin_context.py' | grep -v '__pycache__' | grep -v 'plugins/clients/'`
Expected: Zero matches outside the field definitions and client module itself

**Step 2: Delete the fields and imports**

In `src/elspeth/contracts/plugin_context.py`:

Delete lines 133-136 (the fields):
```python
    # === Phase 6: Audited Clients ===
    # Set by executor when processing LLM transforms
    llm_client: AuditedLLMClient | None = None
    http_client: AuditedHTTPClient | None = None
```

Delete the TYPE_CHECKING imports for these (lines 38-39):
```python
    from elspeth.plugins.clients.http import AuditedHTTPClient
    from elspeth.plugins.clients.llm import AuditedLLMClient
```

**Step 3: Run tests + mypy**

Run: `.venv/bin/python -m pytest tests/ -x --timeout=120 -q && .venv/bin/python -m mypy src/`
Expected: All pass

---

## Task 3: Remove `tracer` field + `start_span()` method

**Files:**
- Modify: `src/elspeth/contracts/plugin_context.py:95` (field)
- Modify: `src/elspeth/contracts/plugin_context.py:225-236` (method)
- Modify: `src/elspeth/contracts/plugin_context.py:28` (TYPE_CHECKING import)

**Step 1: Verify zero usage**

Run: `grep -rn 'ctx\.tracer\|ctx\.start_span\|\.start_span(' src/elspeth/ --include='*.py' | grep -v 'plugin_context.py' | grep -v '__pycache__'`
Expected: Zero matches in production code (test references are OK to update)

**Step 2: Delete the field, method, and imports**

In `src/elspeth/contracts/plugin_context.py`:

Delete line 95 (the field):
```python
    tracer: Tracer | None = None
```

Delete lines 225-236 (the method):
```python
    def start_span(self, name: str) -> AbstractContextManager[Span | None]:
        ...
```

Delete the TYPE_CHECKING import (line 28):
```python
    from opentelemetry.trace import Span, Tracer
```

Also remove the now-unused imports at the top: `AbstractContextManager`, `nullcontext` (from `contextlib`). Verify these are not used elsewhere in the file first.

**Step 3: Fix test breakage**

Run: `grep -rn 'tracer\|start_span' tests/ --include='*.py'`
Update any tests that reference these fields — they should be testing PluginContext features that no longer exist.

**Step 4: Run tests + mypy**

Run: `.venv/bin/python -m pytest tests/ -x --timeout=120 -q && .venv/bin/python -m mypy src/`
Expected: All pass

---

## Task 4: Remove `get()` method

**Files:**
- Modify: `src/elspeth/contracts/plugin_context.py:206-223`

**Step 1: Verify zero usage**

Run: `grep -rn 'ctx\.get(' src/elspeth/ --include='*.py' | grep -v 'plugin_context.py' | grep -v '__pycache__'`
Expected: Zero matches in production code

**Step 2: Delete the method**

In `src/elspeth/contracts/plugin_context.py`, delete lines 206-223:
```python
    def get(self, key: str, *, default: Any = None) -> Any:
        ...
```

**Step 3: Fix test breakage**

Run: `grep -rn '\.get(' tests/ --include='*.py' | grep -i 'plugin_context\|ctx\.get'`
Update any tests that exercise the deleted `get()` method.

**Step 4: Run tests + mypy**

Run: `.venv/bin/python -m pytest tests/ -x --timeout=120 -q && .venv/bin/python -m mypy src/`
Expected: All pass

---

## Task 5: Clean up docstring and phase comments

**Files:**
- Modify: `src/elspeth/contracts/plugin_context.py`

**Step 1: Update class docstring**

Remove references to `get()` and `start_span()` from the docstring (lines 75-86). Remove the example that uses these methods. Update the "Phase 3" language to reflect current state.

**Step 2: Remove stale comments**

Remove "Phase 2/Phase 3" placeholder comments throughout the file — these are pre-1.0 scaffolding comments that are now misleading.

**Step 3: Run tests + mypy**

Run: `.venv/bin/python -m pytest tests/ -x --timeout=120 -q && .venv/bin/python -m mypy src/`
Expected: All pass

---

## Task 6: Commit Phase 0

**Step 1: Commit**

```bash
git add src/elspeth/contracts/plugin_context.py tests/
git commit -m "refactor(T17): Phase 0 — remove 5 dead fields + 2 unused methods from PluginContext

Remove plugin_name, llm_client, http_client, tracer fields and
start_span(), get() methods. All had zero production callers.
Reduces PluginContext surface from 20 fields to 15 before protocol split."
```

**Step 2: Verify clean state**

Run: `.venv/bin/python -m pytest tests/ -x --timeout=120 -q && .venv/bin/python -m mypy src/ && .venv/bin/python -m ruff check src/`
Expected: All pass
