# P2 Migration Instructions — Inline Landscape Setup Replacement

## What You're Doing

You are replacing inline `LandscapeDB.in_memory()` and `LandscapeRecorder(...)` constructions in test files with centralized factory calls. This is a MECHANICAL replacement — do NOT refactor, restructure, or "improve" anything beyond the specific replacements described below.

## CRITICAL RULES

1. **NEVER run any git commands.** No `git diff`, `git status`, `git add`, `git commit`, nothing.
2. **Only modify the files explicitly assigned to you.** Do not modify any other files.
3. **Do NOT delete any tests.** The test count must not decrease.
4. **Do NOT change any test assertions or logic.** Only change setup/teardown code.
5. **Do NOT add docstrings, comments, or type annotations** to code you didn't change.
6. **Be MECHANICAL.** Each replacement follows a clear pattern. Do not invent new patterns.
7. **If you encounter something unexpected** (file doesn't match pattern, test logic is unusual, a replacement would change behavior), STOP and report it — do not improvise.

## Replacement Patterns

### Pattern 1: Simple `LandscapeDB.in_memory()` → `make_landscape_db()`

```python
# BEFORE
db = LandscapeDB.in_memory()

# AFTER
db = make_landscape_db()
```

This is ALWAYS safe. No exceptions.

### Pattern 2: Simple `LandscapeRecorder(db)` → `make_recorder(db)`

```python
# BEFORE
recorder = LandscapeRecorder(db)

# AFTER
recorder = make_recorder(db)
```

This is ALWAYS safe. Use it even when the db variable was created by `make_landscape_db()`.

### Pattern 3: The 80% Pattern — Full 4-step setup → `make_recorder_with_run()`

```python
# BEFORE (the common 4-step boilerplate)
db = LandscapeDB.in_memory()
recorder = LandscapeRecorder(db)
run = recorder.begin_run(config={}, canonical_version="v1")
source = recorder.register_node(
    run_id=run.run_id,
    plugin_name="source",
    node_type=NodeType.SOURCE,
    plugin_version="1.0",
    config={},
    schema_config=DYNAMIC_SCHEMA,  # or SchemaConfig.from_dict({"mode": "observed"}) or similar
)

# AFTER
setup = make_recorder_with_run()
db, recorder, run_id = setup.db, setup.recorder, setup.run_id
source_node_id = setup.source_node_id
```

**When to use Pattern 3:**
- The test has the 4-step pattern (in_memory → Recorder → begin_run → register_node with SOURCE)
- The test does NOT assert directly on the return value of `begin_run()` or `register_node()` themselves
- The `canonical_version` is "v1" (the factory default) — if it's something else like "1.0" or "sha256-rfc8785-v1", pass it explicitly: `make_recorder_with_run(canonical_version="1.0")`

**When NOT to use Pattern 3:**
- The test asserts on `begin_run()` return values (the run IS the system under test)
- The test asserts on `register_node()` return values
- The test is testing error handling of `begin_run()` or `register_node()`
- The test uses non-standard arguments to `begin_run()` beyond `config` and `canonical_version` (e.g., explicit `run_id`)
  - Exception: if the test passes an explicit `run_id`, use `make_recorder_with_run(run_id="the-id")`
  - Exception: if the test passes an explicit `node_id` to `register_node`, use `make_recorder_with_run(source_node_id="the-id")`

**When the test has additional nodes after the source:**

```python
# BEFORE
db = LandscapeDB.in_memory()
recorder = LandscapeRecorder(db)
run = recorder.begin_run(config={}, canonical_version="v1")
source = recorder.register_node(run_id=run.run_id, plugin_name="source", node_type=NodeType.SOURCE, ...)
transform = recorder.register_node(run_id=run.run_id, plugin_name="xform", node_type=NodeType.TRANSFORM, ...)
sink = recorder.register_node(run_id=run.run_id, plugin_name="sink", node_type=NodeType.SINK, ...)

# AFTER
setup = make_recorder_with_run()
db, recorder, run_id = setup.db, setup.recorder, setup.run_id
source_node_id = setup.source_node_id
transform_node_id = register_test_node(recorder, run_id, "xform", node_type=NodeType.TRANSFORM, plugin_name="xform")
sink_node_id = register_test_node(recorder, run_id, "sink", node_type=NodeType.SINK, plugin_name="sink")
```

Note: `register_test_node` requires a `node_id` string as the 3rd positional argument. Use the same node_id the test originally used, or a descriptive one like "transform" or "sink".

### Pattern 3b: When tests use `run.run_id` or `source.node_id` later

Many tests store the run/node objects and access `.run_id` / `.node_id` later. After migration, use the `setup.run_id` and `setup.source_node_id` fields:

```python
# BEFORE
run = recorder.begin_run(...)
source = recorder.register_node(run_id=run.run_id, ...)
# ... later in test ...
recorder.create_row(run_id=run.run_id, ...)
recorder.begin_node_state(node_id=source.node_id, ...)

# AFTER
setup = make_recorder_with_run()
# ... later in test ...
recorder.create_row(run_id=setup.run_id, ...)
recorder.begin_node_state(node_id=setup.source_node_id, ...)
```

Or destructure at the top: `db, recorder, run_id, source_node_id = setup.db, setup.recorder, setup.run_id, setup.source_node_id`

### Pattern 4: Helper functions that create recorder + run

Some files have local helper functions like `_make_recorder()`, `_setup()`, `_create_test_db()` etc. that wrap the 4-step pattern. If the helper is ONLY called within the same file and its body matches the 80% pattern, replace the helper body with `make_recorder_with_run()` delegation.

If the helper has custom logic beyond the 4-step pattern, leave it alone and just replace the `LandscapeDB.in_memory()` and `LandscapeRecorder(db)` inside it with Patterns 1 and 2.

## Import Changes

### Add these imports (as needed):

```python
from tests.fixtures.landscape import make_landscape_db, make_recorder, make_recorder_with_run, register_test_node
```

Only import the factories you actually use. If you only use Pattern 1, only import `make_landscape_db`. If you use Pattern 3, import `make_recorder_with_run` (and `register_test_node` if needed).

### Remove these imports (when no longer used):

```python
from elspeth.core.landscape.database import LandscapeDB  # Remove if no more LandscapeDB references
from elspeth.core.landscape.recorder import LandscapeRecorder  # Remove if no more LandscapeRecorder references
```

**CHECK CAREFULLY:** Before removing an import, verify the symbol is not used anywhere else in the file (e.g., in type annotations, isinstance checks, or other code paths). Use grep/search to confirm.

Also remove `NodeType` imports if no longer used after Pattern 3 migration (it was only needed for register_node calls). And remove `SchemaConfig`/`DYNAMIC_SCHEMA` imports if no longer needed.

### RecorderSetup import

If you use `make_recorder_with_run()`, you do NOT need to import `RecorderSetup` — the return type is inferred.

## Files That Are EXEMPT from Pattern 3

These files test recorder/landscape methods directly. Use ONLY Patterns 1 and 2 (simple factory wrappers), NOT Pattern 3:

- Any file where `begin_run()` return values are asserted on
- Any file where `register_node()` return values are asserted on
- Files in `tests/unit/core/landscape/` that test specific recorder methods — use your judgment per-test:
  - If the test's PURPOSE is to test `begin_run`, `register_node`, `create_row`, `create_token` → use only Patterns 1+2
  - If the test's PURPOSE is to test something else (e.g., `record_call`, `get_row_data`) and the setup is just boilerplate → Pattern 3 is fine

## What to Do After Edits

After making all replacements in your assigned file(s):

1. Read the file back to verify your edits are syntactically correct
2. Check that no imports were left dangling (imported but unused) or missing
3. Report back with:
   - Number of replacements made (by pattern)
   - Any files/tests you skipped and why
   - Any unexpected patterns you encountered

## Factory API Reference

```python
# tests/fixtures/landscape.py

def make_landscape_db() -> LandscapeDB:
    """Factory for in-memory LandscapeDB."""

def make_recorder(db: LandscapeDB | None = None) -> LandscapeRecorder:
    """Factory for LandscapeRecorder. Creates DB if db is None."""

def make_recorder_with_run(
    *,
    run_id: str | None = None,
    source_node_id: str | None = None,
    source_plugin_name: str = "source",
    canonical_version: str = "v1",
) -> RecorderSetup:
    """Create LandscapeDB + Recorder + run + source node in one call."""
    # Returns RecorderSetup(db, recorder, run_id, source_node_id)

def register_test_node(
    recorder: LandscapeRecorder,
    run_id: str,
    node_id: str,
    *,
    node_type: NodeType = NodeType.TRANSFORM,
    plugin_name: str = "transform",
) -> str:
    """Register an additional test node. Returns node_id."""
```
