# PipelineConfig Immutable Type Annotations — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the mypy feedback loop on PipelineConfig by replacing mutable `list`/`dict` annotations with immutable `Sequence`/`Mapping`, and add a CI linter to prevent recurrence.

**Architecture:** Two commits. Commit 1: atomic annotation refactoring across ~10 files + new `TestPipelineConfig` class. Commit 2: CI linter script (`enforce_frozen_annotations.py`) + linter tests + pre-commit hook.

**Tech Stack:** Python type annotations (`collections.abc.Sequence`, `collections.abc.Mapping`), mypy, AST walking (`ast` stdlib), pytest, pre-commit hooks.

**Spec:** `docs/superpowers/specs/2026-03-22-pipelineconfig-immutable-annotations-design.md`

---

## Commit 1: Annotation Refactoring + Tests

All tasks in this commit are atomic — they must all land together for mypy to pass. Do NOT commit individual tasks. Commit once after Task 4.

### Task 1: Write TestPipelineConfig tests (write tests FIRST)

**Files:**
- Modify: `tests/unit/engine/orchestrator/test_types.py` (append after line 271)

- [ ] **Step 1: Read existing test patterns**

Read `tests/unit/engine/orchestrator/test_types.py` to understand imports, fixtures, and the `TestGraphArtifacts` / `TestAggregationFlushResult` patterns used for frozen dataclass testing.

- [ ] **Step 2: Write TestPipelineConfig class**

Append to `tests/unit/engine/orchestrator/test_types.py`:

```python
class TestPipelineConfig:
    """PipelineConfig freezes mutable containers in __post_init__."""

    def _make_config(self) -> PipelineConfig:
        """Minimal valid PipelineConfig for testing."""
        source = Mock()
        source.node_id = None
        transform = Mock()
        transform.node_id = None
        transform.on_error = "discard"
        sink = Mock()
        sink.node_id = None
        return PipelineConfig(
            source=source,
            transforms=[transform],
            sinks={"output": sink},
            config={"key": "value"},
            gates=[Mock()],
            aggregation_settings={"agg-1": Mock()},
            coalesce_settings=[Mock()],
        )

    def test_list_fields_frozen_to_tuple(self) -> None:
        config = self._make_config()
        assert isinstance(config.transforms, tuple)
        assert isinstance(config.gates, tuple)
        assert isinstance(config.coalesce_settings, tuple)

    def test_dict_fields_frozen_to_mapping_proxy(self) -> None:
        config = self._make_config()
        assert isinstance(config.sinks, MappingProxyType)
        assert isinstance(config.config, MappingProxyType)
        assert isinstance(config.aggregation_settings, MappingProxyType)

    def test_tuple_fields_reject_append(self) -> None:
        config = self._make_config()
        with pytest.raises(AttributeError):
            config.transforms.append(Mock())  # type: ignore[union-attr]

    def test_mapping_proxy_fields_reject_assignment(self) -> None:
        config = self._make_config()
        with pytest.raises(TypeError):
            config.sinks["new"] = Mock()  # type: ignore[index]
        with pytest.raises(TypeError):
            config.config["new"] = "value"  # type: ignore[index]

    def test_idempotent_with_already_frozen_inputs(self) -> None:
        source = Mock()
        source.node_id = None
        sink = Mock()
        sink.node_id = None
        frozen_transforms = (Mock(),)
        frozen_sinks = MappingProxyType({"output": sink})
        frozen_config = MappingProxyType({"key": "value"})
        frozen_gates = (Mock(),)
        frozen_agg = MappingProxyType({"agg-1": Mock()})
        frozen_coal = (Mock(),)

        config = PipelineConfig(
            source=source,
            transforms=frozen_transforms,
            sinks=frozen_sinks,
            config=frozen_config,
            gates=frozen_gates,
            aggregation_settings=frozen_agg,
            coalesce_settings=frozen_coal,
        )
        assert isinstance(config.transforms, tuple)
        assert isinstance(config.sinks, MappingProxyType)
        assert config.transforms == frozen_transforms
        assert config.sinks == frozen_sinks
```

`MappingProxyType` is already imported at line 13. `PipelineConfig` is NOT imported — add it to the existing import block:
```python
from elspeth.engine.orchestrator.types import AggregationFlushResult, ExecutionCounters, PipelineConfig
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/engine/orchestrator/test_types.py::TestPipelineConfig -v`
Expected: All 5 tests PASS (the `__post_init__` freezing already works at runtime)

---

### Task 2: Update PipelineConfig field annotations

**Files:**
- Modify: `src/elspeth/engine/orchestrator/types.py:89-95`

- [ ] **Step 1: Change field annotations**

At lines 89-95, change:
```python
    source: SourceProtocol
    transforms: list[RowPlugin]
    sinks: dict[str, SinkProtocol]
    config: dict[str, Any] = field(default_factory=dict)
    gates: list[GateSettings] = field(default_factory=list)
    aggregation_settings: dict[str, AggregationSettings] = field(default_factory=dict)
    coalesce_settings: list[CoalesceSettings] = field(default_factory=list)
```

To:
```python
    source: SourceProtocol
    transforms: Sequence[RowPlugin]
    sinks: Mapping[str, SinkProtocol]
    config: Mapping[str, Any] = field(default_factory=dict)
    gates: Sequence[GateSettings] = field(default_factory=list)
    aggregation_settings: Mapping[str, AggregationSettings] = field(default_factory=dict)
    coalesce_settings: Sequence[CoalesceSettings] = field(default_factory=list)
```

`Sequence` and `Mapping` are already imported from `collections.abc` at line 23. No import changes needed.

---

### Task 3: Update downstream function signatures

**Files:**
- Modify: `src/elspeth/engine/orchestrator/core.py:691-699`
- Modify: `src/elspeth/engine/orchestrator/validation.py:36-43,93-96`
- Modify: `src/elspeth/engine/orchestrator/export.py:39-44`
- Modify: `src/elspeth/engine/processor.py:15,1148-1157,1216-1225`
- Modify: `src/elspeth/contracts/plugin_context.py:13,80`
- Modify: `src/elspeth/core/landscape/recorder.py:195-205`
- Modify: `src/elspeth/core/landscape/run_lifecycle_repository.py:55-65`

- [ ] **Step 1: Update `core.py` — `_assign_plugin_node_ids`**

At lines 691-699, change:
```python
    def _assign_plugin_node_ids(
        self,
        source: SourceProtocol,
        transforms: list[RowPlugin],
        sinks: dict[str, SinkProtocol],
        source_id: NodeID,
        transform_id_map: dict[int, NodeID],
        sink_id_map: dict[SinkName, NodeID],
    ) -> None:
```

To:
```python
    def _assign_plugin_node_ids(
        self,
        source: SourceProtocol,
        transforms: Sequence[RowPlugin],
        sinks: Mapping[str, SinkProtocol],
        source_id: NodeID,
        transform_id_map: Mapping[int, NodeID],
        sink_id_map: Mapping[SinkName, NodeID],
    ) -> None:
```

`core.py:25` already imports both `Mapping` and `Sequence` from `collections.abc`. No import changes needed.

- [ ] **Step 2: Update `validation.py` — `validate_route_destinations`**

At lines 36-43, change:
```python
def validate_route_destinations(
    route_resolution_map: dict[tuple[NodeID, str], RouteDestination],
    available_sinks: set[str],
    transform_id_map: dict[int, NodeID],
    transforms: list[RowPlugin],
    config_gate_id_map: dict[GateName, NodeID] | None = None,
    config_gates: list[GateSettings] | None = None,
) -> None:
```

To:
```python
def validate_route_destinations(
    route_resolution_map: Mapping[tuple[NodeID, str], RouteDestination],
    available_sinks: set[str],
    transform_id_map: Mapping[int, NodeID],
    transforms: Sequence[RowPlugin],
    config_gate_id_map: Mapping[GateName, NodeID] | None = None,
    config_gates: Sequence[GateSettings] | None = None,
) -> None:
```

- [ ] **Step 3: Update `validation.py` — `validate_transform_error_sinks`**

At lines 93-96, change:
```python
def validate_transform_error_sinks(
    transforms: list[RowPlugin],
    available_sinks: set[str],
) -> None:
```

To:
```python
def validate_transform_error_sinks(
    transforms: Sequence[RowPlugin],
    available_sinks: set[str],
) -> None:
```

Add `from collections.abc import Mapping, Sequence` to `validation.py` after line 19 (`from __future__ import annotations`) and before the `TYPE_CHECKING` block — validation.py currently has no `collections.abc` imports

- [ ] **Step 4: Update `export.py` — `export_landscape`**

At lines 39-44, change `sinks: dict[str, SinkProtocol]` to `sinks: Mapping[str, SinkProtocol]`.

Add `from collections.abc import Mapping` if not already imported.

- [ ] **Step 5: Update `processor.py` — `process_row` and `process_existing_row`**

At line 15, change:
```python
from collections.abc import Mapping
```
To:
```python
from collections.abc import Mapping, Sequence
```

At line 1152, change `transforms: list[Any]` to `transforms: Sequence[RowPlugin]`.
At line 1220, change `transforms: list[Any]` to `transforms: Sequence[RowPlugin]`.

Add `from elspeth.engine.orchestrator.types import RowPlugin` to the TYPE_CHECKING block if not already present. Check if `RowPlugin` is available — if this import creates a circular dependency, fall back to `Sequence[Any]`.

- [ ] **Step 6: Update `plugin_context.py` — `PluginContext.config`**

At line 13, change:
```python
from collections.abc import Callable
```
To:
```python
from collections.abc import Callable, Mapping
```

At line 80, change `config: dict[str, Any]` to `config: Mapping[str, Any]`.

- [ ] **Step 7: Update `recorder.py` — `begin_run`**

At line 197, change `config: dict[str, Any]` to `config: Mapping[str, Any]`.

`recorder.py:23` already imports `Mapping`. No import changes needed.

- [ ] **Step 8: Update `run_lifecycle_repository.py` — `begin_run`**

At line 57, change `config: dict[str, Any]` to `config: Mapping[str, Any]`.

`run_lifecycle_repository.py:10` already imports `Mapping`. No import changes needed.

---

### Task 4: Verify and commit

- [ ] **Step 1: Run mypy**

Run: `.venv/bin/python -m mypy src/`
Expected: Clean (zero errors). This is the primary success criterion. If there are errors, read them carefully — they indicate either a missed signature update or a genuine mutation site that needs fixing.

If `Sequence[RowPlugin]` on `process_row`/`process_existing_row` causes errors, fall back to `Sequence[Any]` for those two signatures only.

- [ ] **Step 2: Run unit tests**

Run: `.venv/bin/python -m pytest tests/unit/ -x --tb=short -q`
Expected: All tests pass. No runtime changes were made — failures indicate a test that was relying on the concrete `list`/`dict` type.

- [ ] **Step 3: Run linters**

Run: `.venv/bin/python -m ruff check src/ tests/` and `.venv/bin/python -m ruff format --check src/ tests/`
Expected: Clean.

- [ ] **Step 4: Run tier model enforcer**

Run: `.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model`
Expected: Clean.

- [ ] **Step 5: Commit**

```bash
git add src/elspeth/engine/orchestrator/types.py \
       src/elspeth/engine/orchestrator/core.py \
       src/elspeth/engine/orchestrator/validation.py \
       src/elspeth/engine/orchestrator/export.py \
       src/elspeth/engine/processor.py \
       src/elspeth/contracts/plugin_context.py \
       src/elspeth/core/landscape/recorder.py \
       src/elspeth/core/landscape/run_lifecycle_repository.py \
       tests/unit/engine/orchestrator/test_types.py
git commit -m "refactor: PipelineConfig annotations list/dict → Sequence/Mapping

Close the mypy feedback loop: field annotations now match the frozen
runtime types (tuple/MappingProxyType) so mypy prevents mutation bugs
at write time instead of runtime.

Changes:
- PipelineConfig: 6 field annotations widened
- Downstream signatures: _assign_plugin_node_ids, validate_route_destinations,
  validate_transform_error_sinks, export_landscape, process_row,
  process_existing_row, PluginContext.config, begin_run (recorder + repo)
- New TestPipelineConfig class: freezing, immutability, idempotency assertions

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Commit 2: CI Linter

### Task 5: Write linter tests

**Files:**
- Create: `tests/unit/scripts/cicd/test_enforce_frozen_annotations.py`

- [ ] **Step 1: Create test directory if needed**

The directory `tests/unit/scripts/cicd/` already exists with `__init__.py` and `test_enforce_tier_model.py`. No directory creation needed.

- [ ] **Step 2: Write linter tests**

Create `tests/unit/scripts/cicd/test_enforce_frozen_annotations.py`:

```python
"""Tests for enforce_frozen_annotations.py CI linter."""

from __future__ import annotations

import textwrap

import pytest

from scripts.cicd.enforce_frozen_annotations import find_violations


def _parse(source: str) -> list[dict[str, str]]:
    """Run the linter on a source string and return violations."""
    return find_violations(textwrap.dedent(source), filename="test.py")


class TestFrozenDataclassDetection:
    """Linter must detect frozen=True with various keyword combinations."""

    def test_frozen_true_detected(self) -> None:
        violations = _parse("""
            from dataclasses import dataclass

            @dataclass(frozen=True)
            class Foo:
                items: list[int]
        """)
        assert len(violations) == 1
        assert "list[" in violations[0]["annotation"]

    def test_frozen_true_slots_true_detected(self) -> None:
        violations = _parse("""
            from dataclasses import dataclass

            @dataclass(frozen=True, slots=True)
            class Foo:
                items: list[int]
        """)
        assert len(violations) == 1

    def test_non_frozen_ignored(self) -> None:
        violations = _parse("""
            from dataclasses import dataclass

            @dataclass
            class Foo:
                items: list[int]
        """)
        assert len(violations) == 0

    def test_frozen_false_ignored(self) -> None:
        violations = _parse("""
            from dataclasses import dataclass

            @dataclass(frozen=False)
            class Foo:
                items: list[int]
        """)
        assert len(violations) == 0


class TestAnnotationDetection:
    """Linter must detect mutable container annotations."""

    def test_list_detected(self) -> None:
        violations = _parse("""
            from dataclasses import dataclass

            @dataclass(frozen=True)
            class Foo:
                items: list[int]
        """)
        assert len(violations) == 1

    def test_dict_detected(self) -> None:
        violations = _parse("""
            from dataclasses import dataclass

            @dataclass(frozen=True)
            class Foo:
                mapping: dict[str, int]
        """)
        assert len(violations) == 1

    def test_set_detected(self) -> None:
        violations = _parse("""
            from dataclasses import dataclass

            @dataclass(frozen=True)
            class Foo:
                unique: set[str]
        """)
        assert len(violations) == 1

    def test_union_with_none_detected(self) -> None:
        violations = _parse("""
            from dataclasses import dataclass

            @dataclass(frozen=True)
            class Foo:
                items: list[int] | None
        """)
        assert len(violations) == 1

    def test_sequence_clean(self) -> None:
        violations = _parse("""
            from dataclasses import dataclass
            from collections.abc import Sequence

            @dataclass(frozen=True)
            class Foo:
                items: Sequence[int]
        """)
        assert len(violations) == 0

    def test_mapping_clean(self) -> None:
        violations = _parse("""
            from dataclasses import dataclass
            from collections.abc import Mapping

            @dataclass(frozen=True)
            class Foo:
                mapping: Mapping[str, int]
        """)
        assert len(violations) == 0

    def test_tuple_clean(self) -> None:
        violations = _parse("""
            from dataclasses import dataclass

            @dataclass(frozen=True)
            class Foo:
                items: tuple[int, ...]
        """)
        assert len(violations) == 0


class TestFutureAnnotations:
    """Linter must work with from __future__ import annotations (PEP 563)."""

    def test_stringified_list_detected(self) -> None:
        violations = _parse("""
            from __future__ import annotations
            from dataclasses import dataclass

            @dataclass(frozen=True)
            class Foo:
                items: list[int]
        """)
        assert len(violations) == 1

    def test_stringified_sequence_clean(self) -> None:
        violations = _parse("""
            from __future__ import annotations
            from dataclasses import dataclass
            from collections.abc import Sequence

            @dataclass(frozen=True)
            class Foo:
                items: Sequence[int]
        """)
        assert len(violations) == 0


class TestMultipleFields:
    """Linter reports all violations, not just the first."""

    def test_multiple_violations_reported(self) -> None:
        violations = _parse("""
            from dataclasses import dataclass

            @dataclass(frozen=True)
            class Foo:
                items: list[int]
                mapping: dict[str, str]
                unique: set[float]
        """)
        assert len(violations) == 3

    def test_mixed_clean_and_violations(self) -> None:
        violations = _parse("""
            from dataclasses import dataclass
            from collections.abc import Sequence

            @dataclass(frozen=True)
            class Foo:
                items: list[int]
                safe: Sequence[int]
                name: str
        """)
        assert len(violations) == 1
        assert "list[" in violations[0]["annotation"]
```

- [ ] **Step 3: Run tests to verify they fail (script doesn't exist yet)**

Run: `.venv/bin/python -m pytest tests/unit/scripts/cicd/test_enforce_frozen_annotations.py -v`
Expected: ImportError — `scripts.cicd.enforce_frozen_annotations` does not exist yet.

---

### Task 6: Write the linter script

**Files:**
- Create: `scripts/cicd/enforce_frozen_annotations.py`
- Create: `config/cicd/enforce_frozen_annotations/` (empty allowlist directory)

- [ ] **Step 1: Create allowlist directory**

Run: `mkdir -p config/cicd/enforce_frozen_annotations`

- [ ] **Step 2: Write the linter**

Create `scripts/cicd/enforce_frozen_annotations.py`:

```python
#!/usr/bin/env python3
"""Detect mutable container annotations on frozen dataclass fields.

Frozen dataclasses that convert list→tuple and dict→MappingProxyType in
__post_init__ must use Sequence/Mapping annotations, not list/dict.
Without this, mypy permits .append() / [key]=value on fields that will
reject them at runtime.

Usage:
    python scripts/cicd/enforce_frozen_annotations.py check --root src/elspeth
    python scripts/cicd/enforce_frozen_annotations.py check --root src/elspeth --allowlist config/cicd/enforce_frozen_annotations
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
import yaml
from pathlib import Path
from typing import Any


# Mutable container patterns to detect in annotation strings
MUTABLE_PATTERNS = re.compile(r"\b(list|dict|set)\[")


def find_violations(source: str, filename: str = "<unknown>") -> list[dict[str, str]]:
    """Find mutable container annotations on frozen dataclass fields.

    Args:
        source: Python source code string
        filename: Filename for error messages

    Returns:
        List of violation dicts with keys: file, line, class, field, annotation
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    violations: list[dict[str, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        if not _is_frozen_dataclass(node):
            continue

        for item in node.body:
            if not isinstance(item, ast.AnnAssign):
                continue
            if item.target is None or not isinstance(item.target, ast.Name):
                continue

            annotation_str = ast.unparse(item.annotation)
            if MUTABLE_PATTERNS.search(annotation_str):
                violations.append({
                    "file": filename,
                    "line": str(item.lineno),
                    "class": node.name,
                    "field": item.target.id,
                    "annotation": annotation_str,
                })

    return violations


def _is_frozen_dataclass(node: ast.ClassDef) -> bool:
    """Check if a class is decorated with @dataclass(frozen=True)."""
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Call):
            func = decorator.func
            if isinstance(func, ast.Name) and func.id == "dataclass":
                for kw in decorator.keywords:
                    if kw.arg == "frozen":
                        if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            return True
            elif isinstance(func, ast.Attribute) and func.attr == "dataclass":
                for kw in decorator.keywords:
                    if kw.arg == "frozen":
                        if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            return True
    return False


def _load_allowlist(allowlist_dir: Path) -> set[str]:
    """Load allowlisted violations from YAML files in the allowlist directory."""
    allowed: set[str] = set()
    if not allowlist_dir.exists():
        return allowed
    for yaml_file in sorted(allowlist_dir.glob("*.yaml")):
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
            if data and "allow" in data:
                for entry in data["allow"]:
                    key = entry.get("key", "")
                    if key:
                        allowed.add(key)
    return allowed


def _violation_key(v: dict[str, str]) -> str:
    """Generate a unique key for a violation (for allowlisting)."""
    return f"{v['file']}:{v['class']}:{v['field']}"


def check_directory(root: Path, allowlist_dir: Path | None = None) -> list[dict[str, str]]:
    """Check all Python files under root for violations."""
    allowed = _load_allowlist(allowlist_dir) if allowlist_dir else set()
    all_violations: list[dict[str, str]] = []

    for py_file in sorted(root.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        rel_path = str(py_file.relative_to(root.parent.parent))  # relative to src/
        source = py_file.read_text()
        violations = find_violations(source, filename=rel_path)
        for v in violations:
            if _violation_key(v) not in allowed:
                all_violations.append(v)

    return all_violations


def main() -> None:
    parser = argparse.ArgumentParser(description="Enforce immutable annotations on frozen dataclasses")
    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check", help="Check for violations")
    check.add_argument("--root", type=Path, required=True, help="Root directory to scan")
    check.add_argument("--allowlist", type=Path, default=None, help="Directory containing allowlist YAML files")

    args = parser.parse_args()

    if args.command != "check":
        parser.print_help()
        sys.exit(1)

    violations = check_directory(args.root, args.allowlist)

    if violations:
        print(f"\n{'=' * 60}")
        print(f"FROZEN ANNOTATION VIOLATIONS: {len(violations)}")
        print(f"{'=' * 60}\n")
        for v in violations:
            print(f"{v['file']}:{v['line']}")
            print(f"  Class: {v['class']}")
            print(f"  Field: {v['field']}")
            print(f"  Annotation: {v['annotation']}")
            print(f"  Fix: Use Sequence/Mapping/tuple/frozenset instead of list/dict/set")
            print(f"  Allowlist key: {_violation_key(v)}")
            print()
        print(f"{'=' * 60}")
        print("CHECK FAILED")
        print(f"{'=' * 60}")
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run linter tests**

Run: `.venv/bin/python -m pytest tests/unit/scripts/cicd/test_enforce_frozen_annotations.py -v`
Expected: All tests PASS.

- [ ] **Step 4: Run the linter against the codebase**

Run: `.venv/bin/python scripts/cicd/enforce_frozen_annotations.py check --root src/elspeth`
Expected: Clean (zero violations) — Commit 1 already fixed PipelineConfig's annotations.

If violations are found, they are real — either a frozen dataclass we missed or one that legitimately needs `list`/`dict`. Create an allowlist entry for legitimate exceptions.

---

### Task 7: Add pre-commit hook and commit

**Files:**
- Modify: `.pre-commit-config.yaml` (add entry after the `enforce-tier-model` hook at line 46)

- [ ] **Step 1: Add pre-commit hook**

After line 53 in `.pre-commit-config.yaml` (after the `check-contracts` hook entry), add:

```yaml
  - id: enforce-frozen-annotations
    name: Enforce Frozen Annotations
    entry: .venv/bin/python scripts/cicd/enforce_frozen_annotations.py check --root src/elspeth --allowlist config/cicd/enforce_frozen_annotations
    language: system
    types: [python]
    pass_filenames: false
```

- [ ] **Step 2: Run full verification**

Run:
```bash
.venv/bin/python -m pytest tests/unit/scripts/cicd/test_enforce_frozen_annotations.py tests/unit/engine/orchestrator/test_types.py -v
.venv/bin/python -m ruff check scripts/cicd/enforce_frozen_annotations.py tests/unit/scripts/cicd/
.venv/bin/python scripts/cicd/enforce_frozen_annotations.py check --root src/elspeth
```
Expected: All clean.

- [ ] **Step 3: Commit**

```bash
git add scripts/cicd/enforce_frozen_annotations.py \
       tests/unit/scripts/cicd/test_enforce_frozen_annotations.py \
       config/cicd/enforce_frozen_annotations/ \
       .pre-commit-config.yaml
git commit -m "feat: CI linter for mutable annotations on frozen dataclasses

AST-walking script that detects list[]/dict[]/set[] annotations on
frozen=True dataclass fields. Handles both standard and PEP 563
stringified annotations via ast.unparse().

Prevents recurrence of the PipelineConfig annotation gap (c8205de3).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Verification Checklist

After both commits:

- [ ] `mypy src/` — clean
- [ ] `pytest tests/unit/ -x -q` — all pass
- [ ] `ruff check src/ tests/` — clean
- [ ] `enforce_tier_model.py check` — clean
- [ ] `enforce_frozen_annotations.py check` — clean
- [ ] Pre-commit hooks pass on both commits
