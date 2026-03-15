# P4 Migration Instructions — Property Test Factory Adoption

## Task

Replace inline `LandscapeDB.in_memory()` and `LandscapeRecorder(...)` constructions in property test files with centralized factory calls from `tests/fixtures/landscape.py`.

## Why

Constructor changes to `LandscapeDB` or `LandscapeRecorder` would break every inline construction. Routing through factories means only the factory needs updating.

## Replacement Patterns

### Pattern 1: `LandscapeDB.in_memory()` → `make_landscape_db()`

```python
# BEFORE
db = LandscapeDB.in_memory()

# AFTER
db = make_landscape_db()
```

### Pattern 2: `LandscapeRecorder(db)` → `make_recorder(db)`

```python
# BEFORE
recorder = LandscapeRecorder(db)

# AFTER
recorder = make_recorder(db)
```

### Pattern 3: Full 4-step boilerplate → `make_recorder_with_run()`

When you see this 4-step pattern together:
```python
# BEFORE
db = LandscapeDB.in_memory()
recorder = LandscapeRecorder(db)
run = recorder.begin_run(config={}, canonical_version="v1")
source = recorder.register_node(
    run_id=run.run_id,
    plugin_name="source",
    node_type=NodeType.SOURCE,
    plugin_version="1.0",
    config={},
    schema_config=DYNAMIC_SCHEMA,  # or SchemaConfig.from_dict({"mode": "observed"})
)
# Then uses: db, recorder, run.run_id, source.node_id
```

Replace with:
```python
# AFTER
setup = make_recorder_with_run()
db, recorder, run_id, source_node_id = setup.db, setup.recorder, setup.run_id, setup.source_node_id
```

If the original code uses a non-default `canonical_version` (e.g., `"sha256-rfc8785-v1"` or a Hypothesis-generated value), pass it explicitly:
```python
setup = make_recorder_with_run(canonical_version=cv)
```

If the original code uses an explicit `run_id` or `source_node_id`, pass those too:
```python
setup = make_recorder_with_run(run_id="test-run-1", source_node_id="source-1")
```

### Pattern 4: Additional nodes after Pattern 3

If after the 4-step boilerplate, additional nodes are registered:
```python
# BEFORE (after Pattern 3)
transform = recorder.register_node(
    run_id=run.run_id,
    plugin_name="transform",
    node_type=NodeType.TRANSFORM,
    plugin_version="1.0",
    config={},
    schema_config=DYNAMIC_SCHEMA,
)

# AFTER (using the returned recorder from Pattern 3)
transform_node_id = register_test_node(recorder, run_id, "transform-1")
```

For non-default node types:
```python
sink_node_id = register_test_node(recorder, run_id, "sink-1", node_type=NodeType.SINK, plugin_name="sink")
```

## Import Changes

### Add these imports (as needed):

```python
from tests.fixtures.landscape import make_landscape_db, make_recorder
```

Or for Pattern 3/4:
```python
from tests.fixtures.landscape import make_recorder_with_run, register_test_node
```

Or both:
```python
from tests.fixtures.landscape import (
    make_landscape_db,
    make_recorder,
    make_recorder_with_run,
    register_test_node,
)
```

### Remove these imports (only if no longer used in file):

```python
from elspeth.core.landscape.database import LandscapeDB  # Remove if no other LandscapeDB usage
from elspeth.core.landscape.recorder import LandscapeRecorder  # Remove if no other LandscapeRecorder usage
```

**IMPORTANT:** Only remove an import if ZERO references to that symbol remain in the file. Check the entire file before removing. Some files use `LandscapeRecorder` or `LandscapeDB` in type annotations or other non-construction contexts — those imports must stay.

## Critical Rules

1. **MECHANICAL ONLY.** Do not refactor, rename variables, reformat code, add comments, improve logic, or change anything beyond the exact replacements described above. If a line is not a `LandscapeDB.in_memory()` or `LandscapeRecorder(` call, do NOT touch it.

2. **Preserve variable names.** If the original code uses `db = LandscapeDB.in_memory()`, the replacement must assign to `db`. If it uses `landscape_db = LandscapeDB.in_memory()`, the replacement must assign to `landscape_db`. Do not rename variables.

3. **Preserve semantics.** If a test passes `payload_store=...` to `LandscapeRecorder(db, payload_store=store)`, do NOT migrate it — `make_recorder()` does not accept `payload_store`. Leave it unchanged.

4. **Property tests can't use fixtures.** `@given` decorated tests cannot receive pytest fixtures. All factory calls must be inside the test body, NOT as parameters.

5. **Check for non-default parameters.** Some `LandscapeDB.in_memory()` calls may have no arguments (the common case). Some `LandscapeRecorder(db)` calls may have extra kwargs like `payload_store=`. Only migrate the simple cases.

6. **`DYNAMIC_SCHEMA` vs `SchemaConfig.from_dict(...)`.** Both are equivalent for Pattern 3. The factory `make_recorder_with_run()` uses `SchemaConfig.from_dict({"mode": "observed"})` internally. You don't need to worry about this — just replace the whole boilerplate block.

7. **Don't touch non-construction uses.** `LandscapeRecorder` or `LandscapeDB` may appear in type annotations, isinstance checks, or other contexts. Only replace actual constructor/factory calls.

8. **Import ordering.** Place `tests.fixtures.landscape` imports AFTER all `elspeth.*` imports and AFTER all standard library / third-party imports. Follow the existing import ordering in the file. If in doubt, put them at the end of the import block.

9. **No git commands.** Do NOT run any git commands.

## Factory API Reference

```python
# tests/fixtures/landscape.py

def make_landscape_db() -> LandscapeDB:
    """Factory for in-memory LandscapeDB."""

def make_recorder(db: LandscapeDB | None = None) -> LandscapeRecorder:
    """Factory for LandscapeRecorder. Creates a DB if none provided."""

def make_recorder_with_run(
    *,
    run_id: str | None = None,           # Auto-generated if None
    source_node_id: str | None = None,    # Auto-generated if None
    source_plugin_name: str = "source",
    canonical_version: str = "v1",
) -> RecorderSetup:
    """RecorderSetup has: .db, .recorder, .run_id, .source_node_id"""

def register_test_node(
    recorder: LandscapeRecorder,
    run_id: str,
    node_id: str,
    *,
    node_type: NodeType = NodeType.TRANSFORM,
    plugin_name: str = "transform",
) -> str:  # returns node_id
```

## Verification

After making changes, the subagent should verify the file still parses correctly:
```bash
.venv/bin/python -c "import ast; ast.parse(open('FILE_PATH').read()); print('OK')"
```

And run the tests in that specific file:
```bash
.venv/bin/python -m pytest FILE_PATH -x -q 2>&1 | tail -5
```
