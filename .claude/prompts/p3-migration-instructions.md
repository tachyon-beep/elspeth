# P3 Migration Instructions: Inline Plugin Class Deduplication

## Overview

Replace inline plugin class definitions in test files with imports from `tests/fixtures/plugins.py`. This is a MECHANICAL replacement — do not refactor surrounding code, do not change test logic, do not add/remove tests.

## CRITICAL RULES

1. **Read the entire file first** before making any changes.
2. **Only delete the inline class definitions** and replace references. Do NOT change test structure.
3. **Handle attribute name differences carefully** — see section below.
4. **Do NOT run git commands.** No git add, commit, push, diff, status, or any other git command.
5. **Preserve test semantics exactly.** If a test expects `sink.written`, change it to `sink.results`. If a test constructs `IdentityTransform(config)`, understand what `config` was for.
6. **Remove now-unused imports** after deleting inline classes (e.g., `BaseTransform`, `BaseSink`, `BaseSource`, `TransformResult`, etc.) — but only if truly unused.
7. **Keep imports sorted** — fixture imports (`from tests.fixtures.plugins import ...`) go AFTER all `elspeth.*` imports and AFTER `tests.fixtures.factories`/`tests.fixtures.landscape` imports.

## Available Fixture Classes (signatures)

### PassTransform
```python
from tests.fixtures.plugins import PassTransform

# REPLACES: IdentityTransform, PassthroughTransform, SimpleTransform (when they just pass through)
# Constructor (all keyword-only):
PassTransform(*, name=None, input_connection=None, on_success=None, on_error=None)

# Behavior: .process(row, ctx) returns TransformResult.success(row, success_reason={"action": "passthrough"})
# Has: .name (default "pass_transform"), .input_schema, .output_schema
```

### ListSource
```python
from tests.fixtures.plugins import ListSource

# REPLACES: SimpleSource (when it just yields from a list)
# Constructor:
ListSource(data: list[dict], name: str = "list_source", on_success: str = "default")

# Behavior: .load(ctx) yields SourceRow objects from data list
# Has: .name, .output_schema
```

### CollectSink
```python
from tests.fixtures.plugins import CollectSink

# REPLACES: SimpleSink, CollectingSink, MemorySink
# Constructor:
CollectSink(name: str = "collect", *, node_id: str | None = None)

# Behavior: .write(rows, ctx) appends rows to self.results
# Has: .results (list), .rows_written (alias for .results), .name
```

### FailingSink
```python
from tests.fixtures.plugins import FailingSink

# REPLACES: Inline FailingSink classes
# Constructor:
FailingSink(name: str = "failing_sink", *, node_id: str | None = None, error_message: str = "Sink write failed")

# Behavior: .write() always raises RuntimeError(error_message)
```

### FailingSource
```python
from tests.fixtures.plugins import FailingSource

# REPLACES: Inline FailingSource classes
# Constructor:
FailingSource(*, name: str = "failing_source", error_message: str = "Source failed intentionally")

# Behavior: .load() always raises RuntimeError(error_message)
```

## Attribute Name Mapping

When replacing inline sink classes, check how the test code accesses results:

| Inline class attribute | CollectSink equivalent |
|---|---|
| `sink.written` | `sink.results` |
| `sink.rows` | `sink.results` |
| `sink.collected` | `sink.results` |
| `sink.results` | `sink.results` (no change) |
| `len(sink.written)` | `len(sink.results)` |

## Constructor Mapping

| Inline pattern | Fixture replacement |
|---|---|
| `IdentityTransform(config)` or `IdentityTransform({})` | `PassTransform()` |
| `PassthroughTransform({})` | `PassTransform()` |
| `SimpleTransform({})` or `SimpleTransform(config)` | `PassTransform()` |
| `SimpleSource(data)` | `ListSource(data)` |
| `SimpleSink()` | `CollectSink()` |
| `SimpleSink(name="x")` | `CollectSink(name="x")` |
| `CollectingSink()` | `CollectSink()` |
| `FailingSink()` | `FailingSink()` (same name, from fixtures) |
| `FailingSource()` | `FailingSource()` (same name, from fixtures) |

## Name attribute handling

Some inline classes have `name = "identity"` or `name = "simple"`. The fixture versions have different default names (e.g., PassTransform has `name = "pass_transform"`). **If the test code relies on the plugin name** (e.g., in assertions like `assert node.plugin_name == "identity"`), pass the name explicitly: `PassTransform(name="identity")`. If the test doesn't assert on the name, the default is fine.

Similarly for ListSource (default `name = "list_source"`) and CollectSink (default `name = "collect"`). Check assertions and pipeline configurations that reference plugin names.

## Import cleanup

After deleting inline classes, these imports often become unused:
- `from elspeth.plugins.infrastructure.base import BaseTransform, BaseSource, BaseSink`
- `from elspeth.plugins.infrastructure.results import TransformResult`
- `from elspeth.contracts import SourceRow, PipelineRow, ArtifactDescriptor`
- `from elspeth.contracts.contexts import TransformContext, SourceContext, SinkContext`
- `from elspeth.testing import make_pipeline_row`
- `from collections.abc import Iterator`
- `from typing import Any`

**Only remove an import if it is truly unused** after the replacement. Check if any remaining code in the file still uses it.

## Inline class location patterns

Classes may be defined:
1. **At module level** — delete the entire class block from the module
2. **Inside a test function** — delete the class block from inside the function
3. **Inside a test class** — delete from the class body

In all cases, add the fixture import at the file's top-level import section.

## Verification

After making changes, verify:
1. All references to the deleted class are replaced with the fixture class
2. No broken references remain (no `NameError` at runtime)
3. Attribute accesses are updated (`.written` → `.results`, etc.)
4. Constructor calls are compatible with fixture constructors
5. Unused imports are removed
6. New imports are properly placed
