# Runtime-Equivalent Composer Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an authoritative composer preflight path so composer preview, final assistant responses, persisted composer state, YAML export, `/validate`, and `/execute` agree about runtime-blocking pipeline failures before any side-effectful run starts.

**Architecture:** Keep `CompositionState.validate()` as the pure, fast authoring validator. Add a shared web execution preflight boundary that generates composer YAML, resolves runtime-relative paths, resolves deferred secret references in memory, loads settings with `load_settings_from_yaml_string()`, instantiates plugins, builds an `ExecutionGraph`, then runs `graph.validate()` and `graph.validate_edge_compatibility()` through the same production path as execution. Composer code consumes that boundary as an additional authoritative result; it must not copy engine rules into `CompositionState.validate()`.

**Tech Stack:** Python 3.12+, FastAPI route handlers, Pydantic response schemas, SQLAlchemy Core session tables, existing ELSPETH composer state/YAML generator, `load_settings_from_yaml_string()`, `instantiate_plugins_from_config()`, `ExecutionGraph.from_plugin_instances()`, pytest.

---

## Issue

Tracker issue: `elspeth-34baf10c01` - Runtime-equivalent composer preflight / dry-run validation before complete-and-valid claims.

The defect is not that `CompositionState.validate()` needs more local rules. It is intentionally pure and context-free. The defect is that composer prompt/tool/final/persistence surfaces treat that authoring validator as authoritative even though `/validate` and `/execute` use stronger runtime setup paths.

## Reviewer Fixes Folded In

- All composer-to-DB state write paths must use one persisted-validation helper: `send_message`, `recompose`, `_handle_convergence_error`, and `_handle_plugin_crash`.
- Do not use a natural-language completion regex. Final preflight is deterministic: run when the state changed in the current compose turn, or reuse a runtime preflight already returned by `preview_pipeline`.
- If the visible assistant message is replaced with a synthetic preflight-failure message, persist the raw model text separately in `chat_messages.raw_content`; do not expose it through `ChatMessageResponse`.
- Unexpected runtime-preflight exceptions must not be laundered into user-fixable `ValidationResult` objects. Expected runtime validation blockers remain `ValidationResult(is_valid=False, ...)`; unexpected programmer/infrastructure failures become a typed composer error with partial-state preservation.
- YAML export must validate the exact state snapshot that it serializes, not re-read current state through `execution_service.validate(session_id)`.
- Scenario tests must use the real helpers in `tests/integration/pipeline/test_composer_llm_eval_characterization.py`: `_scenario_2_files(tmp_path)` and `_aggregation_state(source_path, output_path, *, ...)`.

## Scope Check

This plan touches one coherent subsystem: web composer validation and execution preflight. It crosses several files, but all changes serve one testable behavior: generated composer state must be checked by the same pre-execution truth the runtime uses before the system reports or persists it as valid.

Out of scope:

- Running sample data rows.
- Adding plugin-specific side-effectful dry-run hooks.
- Exposing hidden model reasoning.
- Frontend UI redesign. A follow-up can rename the visible "Errors" heading if runtime-flavored messages need clearer copy.
- Expanding path rewriting beyond existing source/sink option keys. Transform/aggregation path options are a separate pre-existing gap and should be tracked separately if found.

## File Structure

- Create `src/elspeth/web/execution/preflight.py`
  - Own shared, side-effect-free preflight helpers.
  - Move YAML path resolution here from `execution/service.py`.
  - Provide typed plugin/graph setup helpers without collapsing `graph_structure` and `schema_compatibility` validation checks.

- Modify `src/elspeth/web/execution/protocol.py`
  - Add a small `ValidationSettings` protocol with `data_dir`.

- Modify `src/elspeth/web/execution/validation.py`
  - Keep `validate_pipeline()` as the public direct-state validation API.
  - Use shared path resolution and runtime graph helpers.
  - Preserve separate check names: `plugin_instantiation`, `graph_structure`, and `schema_compatibility`.

- Modify `src/elspeth/web/execution/service.py`
  - Use the shared path resolver and runtime graph helper in `_execute_locked()` / `_run_pipeline()`.
  - Keep run creation, blob ownership, audit, progress, and orchestration here.

- Modify `src/elspeth/web/composer/tools.py`
  - Add optional runtime preflight callback to `execute_tool()`.
  - Add `ToolResult.runtime_preflight`.
  - Make `preview_pipeline` include both authoring validation and runtime preflight when available.

- Modify `src/elspeth/web/composer/service.py`
  - Store runtime-validation settings.
  - Pass runtime preflight into tools.
  - Track the latest preview preflight result.
  - Gate final responses deterministically with no text regex.

- Modify `src/elspeth/web/composer/protocol.py`
  - Extend `ComposerResult` with `runtime_preflight` and `raw_assistant_content`.
  - Add `ComposerRuntimePreflightError` for unexpected internal preflight failures.

- Modify `src/elspeth/web/sessions/models.py`, `protocol.py`, `service.py`, `schemas.py`, and `routes.py`
  - Add nullable `chat_messages.raw_content` for raw model text when visible content is replaced.
  - Persist runtime validation truth through all composer state write paths.
  - Keep `raw_content` out of `ChatMessageResponse`.
  - Gate YAML export by validating the exact state snapshot being exported.

- Tests:
  - `tests/unit/web/execution/test_validation.py`
  - `tests/unit/web/execution/test_service.py`
  - `tests/unit/web/composer/test_tools.py`
  - `tests/unit/web/composer/test_service.py`
  - `tests/unit/web/sessions/test_routes.py`
  - `tests/integration/pipeline/test_composer_llm_eval_characterization.py`

## Design Rules

- `CompositionState.validate()` remains pure: no settings, no session, no DB, no filesystem, no plugin instantiation.
- Runtime preflight is the authority for "runnable" and "complete".
- `composition_states.is_valid` must have one meaning after this change: runtime-preflight-valid when runtime preflight is available; otherwise false with an explicit validation error if preflight could not be completed.
- Composer preview shows authoring validation plus runtime preflight; it does not hide authoring warnings.
- Expected plugin/config/user pipeline errors become structured validation entries.
- Unexpected internal failures stay internal failures. They must preserve partial composer state where possible, return sanitized 500s, and avoid exposing raw exception text to the client or LLM.
- Secret values must never be logged or persisted in generated YAML. Resolved secret values are in-memory only.
- Tests must use production code paths: `load_settings_from_yaml_string()`, `instantiate_plugins_from_config()`, `ExecutionGraph.from_plugin_instances()`, `graph.validate()`, and `graph.validate_edge_compatibility()`.

---

### Task 1: Shared Preflight Foundations And Path Parity

**Files:**
- Create: `src/elspeth/web/execution/preflight.py`
- Modify: `src/elspeth/web/execution/protocol.py`
- Modify: `src/elspeth/web/execution/validation.py`
- Modify: `src/elspeth/web/execution/service.py`
- Test: `tests/unit/web/execution/test_validation.py`

- [ ] **Step 1: Add failing path-resolution tests**

Append to `tests/unit/web/execution/test_validation.py`:

```python
class TestValidatePipelineRuntimePathResolution:
    def test_validate_pipeline_resolves_relative_source_and_sink_paths_before_settings_load(self) -> None:
        state = CompositionState(
            source=SourceSpec(
                plugin="csv",
                on_success="main",
                options={"path": "blobs/session/input.csv"},
                on_validation_failure="discard",
            ),
            nodes=(),
            edges=(),
            outputs=(
                OutputSpec(
                    name="main",
                    plugin="csv",
                    options={"path": "outputs/out.csv"},
                    on_write_failure="discard",
                ),
            ),
            metadata=PipelineMetadata(),
            version=1,
        )
        settings = _make_settings(data_dir="/tmp/test_data")
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = """
source:
  plugin: csv
  on_success: main
  options:
    path: blobs/session/input.csv
    on_validation_failure: discard
sinks:
  main:
    plugin: csv
    options:
      path: outputs/out.csv
"""

        with patch("elspeth.web.execution.validation.load_settings_from_yaml_string") as mock_load:
            mock_load.side_effect = ValueError("stop after settings-load input capture")
            validate_pipeline(state, settings, mock_yaml_gen)

        loaded_yaml = mock_load.call_args.args[0]
        parsed = yaml.safe_load(loaded_yaml)
        assert parsed["source"]["options"]["path"] == "/tmp/test_data/blobs/session/input.csv"
        assert parsed["sinks"]["main"]["options"]["path"] == "/tmp/test_data/outputs/out.csv"

    def test_validate_pipeline_preserves_absolute_paths_before_settings_load(self) -> None:
        state = CompositionState(
            source=SourceSpec(
                plugin="csv",
                on_success="main",
                options={"path": "/tmp/test_data/blobs/input.csv"},
                on_validation_failure="discard",
            ),
            nodes=(),
            edges=(),
            outputs=(
                OutputSpec(
                    name="main",
                    plugin="csv",
                    options={"path": "/tmp/test_data/outputs/out.csv"},
                    on_write_failure="discard",
                ),
            ),
            metadata=PipelineMetadata(),
            version=1,
        )
        settings = _make_settings(data_dir="/tmp/test_data")
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = """
source:
  plugin: csv
  on_success: main
  options:
    path: /tmp/test_data/blobs/input.csv
    on_validation_failure: discard
sinks:
  main:
    plugin: csv
    options:
      path: /tmp/test_data/outputs/out.csv
"""

        with patch("elspeth.web.execution.validation.load_settings_from_yaml_string") as mock_load:
            mock_load.side_effect = ValueError("stop after settings-load input capture")
            validate_pipeline(state, settings, mock_yaml_gen)

        loaded_yaml = mock_load.call_args.args[0]
        parsed = yaml.safe_load(loaded_yaml)
        assert parsed["source"]["options"]["path"] == "/tmp/test_data/blobs/input.csv"
        assert parsed["sinks"]["main"]["options"]["path"] == "/tmp/test_data/outputs/out.csv"
```

- [ ] **Step 2: Run the failing path tests**

Run:

```bash
uv run pytest -q tests/unit/web/execution/test_validation.py::TestValidatePipelineRuntimePathResolution
```

Expected: the relative-path test fails because `validate_pipeline()` currently passes relative paths to `load_settings_from_yaml_string()`.

- [ ] **Step 3: Add a validation settings protocol**

Modify `src/elspeth/web/execution/protocol.py`:

```python
from typing import Any, Protocol, runtime_checkable


class ValidationSettings(Protocol):
    """Settings needed by direct runtime preflight validation."""

    @property
    def data_dir(self) -> Any: ...
```

Keep the existing `YamlGenerator` and `ExecutionService` protocols.

- [ ] **Step 4: Create `preflight.py` with path resolution and typed graph helpers**

Create `src/elspeth/web/execution/preflight.py`:

```python
"""Shared runtime preflight helpers for web validation and execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from elspeth.cli_helpers import PluginBundle, instantiate_plugins_from_config
from elspeth.core.dag.graph import ExecutionGraph


@dataclass(slots=True)
class RuntimeGraphBundle:
    """Transient runtime setup result.

    Not frozen: ExecutionGraph is mutable runtime state. This object is not
    persisted and should not cross request boundaries.
    """

    plugin_bundle: PluginBundle
    graph: ExecutionGraph


def resolve_runtime_yaml_paths(pipeline_yaml: str, data_dir: str) -> str:
    """Rewrite relative source/sink paths in pipeline YAML to absolute paths."""
    from elspeth.web.paths import resolve_data_path

    if not isinstance(pipeline_yaml, str):
        raise TypeError(f"YamlGenerator.generate_yaml() must return str; got {type(pipeline_yaml).__name__}")

    config = yaml.safe_load(pipeline_yaml)
    if not isinstance(config, dict):
        raise TypeError(f"YAML generator produced non-dict top-level value (got {type(config).__name__})")

    source = config.get("source")
    if source is not None:
        if not isinstance(source, dict):
            raise TypeError(f"YAML generator produced non-dict 'source' value (got {type(source).__name__})")
        opts = source.get("options")
        if opts is not None:
            if not isinstance(opts, dict):
                raise TypeError(f"YAML generator produced non-dict 'source.options' value (got {type(opts).__name__})")
            for key in ("path", "file"):
                if key in opts and not Path(str(opts[key])).is_absolute():
                    opts[key] = str(resolve_data_path(str(opts[key]), data_dir))

    sinks = config.get("sinks")
    if sinks is not None:
        if not isinstance(sinks, dict):
            raise TypeError(f"YAML generator produced non-dict 'sinks' value (got {type(sinks).__name__})")
        for sink_name, sink_cfg in sinks.items():
            if sink_cfg is not None:
                if not isinstance(sink_cfg, dict):
                    raise TypeError(f"YAML generator produced non-dict sink '{sink_name}' value (got {type(sink_cfg).__name__})")
                opts = sink_cfg.get("options")
                if opts is not None:
                    if not isinstance(opts, dict):
                        raise TypeError(f"YAML generator produced non-dict 'sinks.{sink_name}.options' value (got {type(opts).__name__})")
                    for key in ("path", "file"):
                        if key in opts and not Path(str(opts[key])).is_absolute():
                            opts[key] = str(resolve_data_path(str(opts[key]), data_dir))

    return yaml.dump(config, default_flow_style=False)


def instantiate_runtime_plugins(settings: Any) -> PluginBundle:
    """Instantiate configured plugins through the production helper."""
    return instantiate_plugins_from_config(settings)


def build_runtime_graph(settings: Any, bundle: PluginBundle) -> ExecutionGraph:
    """Build an ExecutionGraph through the production graph factory."""
    return ExecutionGraph.from_plugin_instances(
        source=bundle.source,
        source_settings=bundle.source_settings,
        transforms=bundle.transforms,
        sinks=bundle.sinks,
        aggregations=bundle.aggregations,
        gates=list(settings.gates),
        coalesce_settings=(list(settings.coalesce) if settings.coalesce else None),
    )


def build_validated_runtime_graph(settings: Any) -> RuntimeGraphBundle:
    """Instantiate plugins, build the graph, and run both runtime graph checks."""
    bundle = instantiate_runtime_plugins(settings)
    graph = build_runtime_graph(settings, bundle)
    graph.validate()
    graph.validate_edge_compatibility()
    return RuntimeGraphBundle(plugin_bundle=bundle, graph=graph)
```

- [ ] **Step 5: Use path resolution in validation and execution**

In `src/elspeth/web/execution/validation.py`, import:

```python
from elspeth.web.execution.preflight import resolve_runtime_yaml_paths
from elspeth.web.execution.protocol import ValidationSettings, YamlGenerator
```

Change the `settings` parameter type from `WebSettings` to `ValidationSettings`.

After YAML generation in `validate_pipeline()`:

```python
    pipeline_yaml = yaml_generator.generate_yaml(state)
    pipeline_yaml = resolve_runtime_yaml_paths(pipeline_yaml, str(settings.data_dir))
```

In `src/elspeth/web/execution/service.py`, import:

```python
from elspeth.web.execution.preflight import resolve_runtime_yaml_paths
```

Replace the `_execute_locked()` call to the local path resolver with:

```python
        pipeline_yaml = resolve_runtime_yaml_paths(pipeline_yaml, str(self._settings.data_dir))
```

Delete the old `_resolve_yaml_paths()` function from `execution/service.py` after replacing all callers.

- [ ] **Step 6: Run path tests**

Run:

```bash
uv run pytest -q tests/unit/web/execution/test_validation.py::TestValidatePipelineRuntimePathResolution
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add src/elspeth/web/execution/preflight.py src/elspeth/web/execution/protocol.py src/elspeth/web/execution/validation.py src/elspeth/web/execution/service.py tests/unit/web/execution/test_validation.py
git commit -m "fix(web): resolve composer yaml paths during validation preflight"
```

---

### Task 2: Share Runtime Plugin And Graph Setup Without Collapsing Checks

**Files:**
- Modify: `src/elspeth/web/execution/validation.py`
- Modify: `src/elspeth/web/execution/service.py`
- Test: `tests/unit/web/execution/test_validation.py`
- Test: `tests/unit/web/execution/test_service.py`

- [ ] **Step 1: Add validation tests for separate graph and schema checks**

Append to `tests/unit/web/execution/test_validation.py`:

```python
class TestValidatePipelineRuntimeCheckBoundaries:
    @patch("elspeth.web.execution.validation.load_settings_from_yaml_string")
    @patch("elspeth.web.execution.validation.instantiate_runtime_plugins")
    @patch("elspeth.web.execution.validation.build_runtime_graph")
    def test_graph_structure_failure_uses_graph_check(
        self,
        mock_build_graph: MagicMock,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        state = _make_state(
            source_options={"path": "/tmp/test_data/blobs/input.csv"},
            outputs=(_make_output({"path": "/tmp/test_data/outputs/out.csv"}),),
        )
        settings = _make_settings(data_dir="/tmp/test_data")
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = """
source:
  plugin: csv
  on_success: primary
  options:
    path: /tmp/test_data/blobs/input.csv
    on_validation_failure: discard
sinks:
  primary:
    plugin: csv
    options:
      path: /tmp/test_data/outputs/out.csv
"""
        fake_settings = MagicMock()
        fake_graph = MagicMock()
        fake_graph.validate.side_effect = GraphValidationError("bad graph")
        mock_load.return_value = fake_settings
        mock_instantiate.return_value = MagicMock()
        mock_build_graph.return_value = fake_graph

        result = validate_pipeline(state, settings, mock_yaml_gen)

        assert result.is_valid is False
        assert _check(result, "graph_structure").passed is False
        assert any(check.name == "schema_compatibility" and not check.passed for check in result.checks)
        fake_graph.validate_edge_compatibility.assert_not_called()

    @patch("elspeth.web.execution.validation.load_settings_from_yaml_string")
    @patch("elspeth.web.execution.validation.instantiate_runtime_plugins")
    @patch("elspeth.web.execution.validation.build_runtime_graph")
    def test_schema_failure_uses_schema_check(
        self,
        mock_build_graph: MagicMock,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        state = _make_state(
            source_options={"path": "/tmp/test_data/blobs/input.csv"},
            outputs=(_make_output({"path": "/tmp/test_data/outputs/out.csv"}),),
        )
        settings = _make_settings(data_dir="/tmp/test_data")
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = """
source:
  plugin: csv
  on_success: primary
  options:
    path: /tmp/test_data/blobs/input.csv
    on_validation_failure: discard
sinks:
  primary:
    plugin: csv
    options:
      path: /tmp/test_data/outputs/out.csv
"""
        fake_settings = MagicMock()
        fake_graph = MagicMock()
        fake_graph.validate_edge_compatibility.side_effect = GraphValidationError("schema mismatch")
        mock_load.return_value = fake_settings
        mock_instantiate.return_value = MagicMock()
        mock_build_graph.return_value = fake_graph

        result = validate_pipeline(state, settings, mock_yaml_gen)

        assert result.is_valid is False
        assert _check(result, "graph_structure").passed is True
        assert _check(result, "schema_compatibility").passed is False
```

- [ ] **Step 2: Run the failing boundary tests**

Run:

```bash
uv run pytest -q tests/unit/web/execution/test_validation.py::TestValidatePipelineRuntimeCheckBoundaries
```

Expected: fail until `validation.py` imports and uses `instantiate_runtime_plugins()` and `build_runtime_graph()` separately.

- [ ] **Step 3: Update validation to use shared helpers but preserve check names**

In `src/elspeth/web/execution/validation.py`, import:

```python
from elspeth.web.execution.preflight import (
    build_runtime_graph,
    instantiate_runtime_plugins,
    resolve_runtime_yaml_paths,
)
```

Replace the plugin/graph/schema section with this shape:

```python
    try:
        bundle = instantiate_runtime_plugins(elspeth_settings)
        checks.append(
            ValidationCheck(
                name=_CHECK_PLUGINS,
                passed=True,
                detail="All plugins instantiated",
            )
        )
    except (PluginNotFoundError, PluginConfigError) as exc:
        comp_type = _infer_component_type_from_plugin_error(exc)
        plugin_name = exc.plugin_name if isinstance(exc, PluginConfigError) else None
        if isinstance(exc, PluginConfigError) and exc.cause is not None and plugin_name is not None:
            detail = f"Invalid configuration for {comp_type} '{plugin_name}': {exc.cause}"
        else:
            detail = str(exc)
        checks.append(ValidationCheck(name=_CHECK_PLUGINS, passed=False, detail=detail))
        errors.append(
            ValidationError(
                component_id=plugin_name,
                component_type=comp_type,
                message=detail,
                suggestion=None,
            )
        )
        checks.extend(_skipped_checks(_CHECK_PLUGINS))
        return ValidationResult(
            is_valid=False,
            checks=checks,
            errors=errors,
            semantic_contracts=serialize_semantic_contracts(semantic_contracts),
        )

    try:
        graph = build_runtime_graph(elspeth_settings, bundle)
        graph.validate()
        checks.append(
            ValidationCheck(
                name=_CHECK_GRAPH,
                passed=True,
                detail="Graph structure is valid",
            )
        )
    except GraphValidationError as exc:
        checks.append(ValidationCheck(name=_CHECK_GRAPH, passed=False, detail=str(exc)))
        errors.append(
            ValidationError(
                component_id=exc.component_id,
                component_type=exc.component_type,
                message=str(exc),
                suggestion=None,
            )
        )
        checks.extend(_skipped_checks(_CHECK_GRAPH))
        return ValidationResult(
            is_valid=False,
            checks=checks,
            errors=errors,
            semantic_contracts=serialize_semantic_contracts(semantic_contracts),
        )

    try:
        graph.validate_edge_compatibility()
        checks.append(
            ValidationCheck(
                name=_CHECK_SCHEMA,
                passed=True,
                detail="All edge schemas compatible",
            )
        )
    except GraphValidationError as exc:
        checks.append(ValidationCheck(name=_CHECK_SCHEMA, passed=False, detail=str(exc)))
        errors.append(
            ValidationError(
                component_id=exc.component_id,
                component_type=exc.component_type,
                message=str(exc),
                suggestion=None,
            )
        )
        return ValidationResult(
            is_valid=False,
            checks=checks,
            errors=errors,
            semantic_contracts=serialize_semantic_contracts(semantic_contracts),
        )
```

- [ ] **Step 4: Update execution service to use the all-in-one runtime helper**

In `src/elspeth/web/execution/service.py`, import:

```python
from elspeth.web.execution.preflight import build_validated_runtime_graph, resolve_runtime_yaml_paths
```

Replace the `_run_pipeline()` plugin/graph setup block with:

```python
            runtime_graph = build_validated_runtime_graph(settings)
            bundle = runtime_graph.plugin_bundle
            graph = runtime_graph.graph
```

Remove now-unused imports of `instantiate_plugins_from_config` and `ExecutionGraph` from `execution/service.py`.

- [ ] **Step 5: Run validation and execution service tests**

Run:

```bash
uv run pytest -q tests/unit/web/execution/test_validation.py tests/unit/web/execution/test_service.py
```

Expected: pass. Required patch-target updates are:

- Tests that patch `elspeth.web.execution.service.ExecutionGraph` should patch `elspeth.web.execution.preflight.ExecutionGraph`.
- Tests that patch `elspeth.web.execution.service.instantiate_plugins_from_config` should patch `elspeth.web.execution.preflight.instantiate_plugins_from_config`.
- Tests that verify `validate_pipeline()` orchestration should patch the new symbols imported by `elspeth.web.execution.validation`, not the execution-service module.

- [ ] **Step 6: Commit**

```bash
git add src/elspeth/web/execution/preflight.py src/elspeth/web/execution/validation.py src/elspeth/web/execution/service.py tests/unit/web/execution/test_validation.py tests/unit/web/execution/test_service.py
git commit -m "refactor(web): share runtime graph setup for validation and execution"
```

---

### Task 3: Expose Runtime Preflight Through `preview_pipeline`

**Files:**
- Modify: `src/elspeth/web/composer/tools.py`
- Modify: `src/elspeth/web/composer/service.py`
- Test: `tests/unit/web/composer/test_tools.py`
- Test: `tests/unit/web/composer/test_service.py`

- [ ] **Step 1: Add failing preview test**

Append to `tests/unit/web/composer/test_tools.py` inside `TestPreviewPipeline`:

```python
    def test_preview_pipeline_surfaces_runtime_preflight_failure(self) -> None:
        state = _empty_state().with_source(
            SourceSpec(
                plugin="csv",
                on_success="main",
                options={"path": "/data/blobs/input.csv", "schema": {"mode": "observed"}},
                on_validation_failure="discard",
            )
        ).with_output(
            OutputSpec(
                name="main",
                plugin="csv",
                options={"path": "/data/outputs/out.csv", "schema": {"mode": "observed"}},
                on_write_failure="discard",
            )
        )
        catalog = _mock_catalog()
        runtime_preflight = MagicMock(
            return_value=ValidationResult(
                is_valid=False,
                checks=[
                    ValidationCheck(
                        name="settings_load",
                        passed=False,
                        detail="Forbidden name: 'end_of_source'",
                    )
                ],
                errors=[
                    ValidationError(
                        component_id="agg1",
                        component_type="aggregation",
                        message="Forbidden name: 'end_of_source'",
                        suggestion="Omit trigger for end-of-source-only aggregation.",
                    )
                ],
            )
        )

        result = execute_tool(
            "preview_pipeline",
            {},
            state,
            catalog,
            data_dir="/data",
            runtime_preflight=runtime_preflight,
        )

        assert result.success is True
        assert result.runtime_preflight is not None
        assert result.data["authoring_validation"]["is_valid"] is True
        assert result.data["runtime_preflight"]["is_valid"] is False
        assert result.data["is_valid"] is False
        assert result.data["runtime_preflight"]["errors"][0]["message"] == "Forbidden name: 'end_of_source'"
        runtime_preflight.assert_called_once_with(state)
```

Add imports if needed:

```python
from elspeth.web.execution.schemas import ValidationCheck, ValidationError, ValidationResult
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
uv run pytest -q tests/unit/web/composer/test_tools.py::TestPreviewPipeline::test_preview_pipeline_surfaces_runtime_preflight_failure
```

Expected: fail because `execute_tool()` does not accept `runtime_preflight` and `ToolResult` has no `runtime_preflight` field.

- [ ] **Step 3: Add `ToolResult.runtime_preflight` and payload helper**

In `src/elspeth/web/composer/tools.py`, import `ValidationResult`:

```python
from elspeth.web.execution.schemas import ValidationResult
```

Add type alias near `ToolHandler`:

```python
RuntimePreflight = Callable[[CompositionState], ValidationResult]
```

Extend `ToolResult`:

```python
    runtime_preflight: ValidationResult | None = None
```

Update `to_dict()` so runtime preflight is visible to the LLM:

```python
        if self.runtime_preflight is not None:
            result["runtime_preflight"] = self.runtime_preflight.model_dump()
```

Add helper:

```python
def _authoring_validation_payload(validation: ValidationSummary) -> dict[str, Any]:
    return {
        "is_valid": validation.is_valid,
        "errors": [e.to_dict() for e in validation.errors],
        "warnings": [e.to_dict() for e in validation.warnings],
        "suggestions": [e.to_dict() for e in validation.suggestions],
        "edge_contracts": [ec.to_dict() for ec in validation.edge_contracts],
        "semantic_contracts": _semantic_contracts_payload(validation.semantic_contracts),
    }
```

- [ ] **Step 4: Thread runtime preflight into preview only**

Change `_execute_preview_pipeline()` signature:

```python
def _execute_preview_pipeline(
    args: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    data_dir: str | None = None,
    *,
    runtime_preflight: RuntimePreflight | None = None,
) -> ToolResult:
```

Use this summary shape:

```python
    validation = state.validate()
    authoring_payload = _authoring_validation_payload(validation)
    runtime_result = runtime_preflight(state) if runtime_preflight is not None else None

    summary: dict[str, Any] = {
        "is_valid": validation.is_valid if runtime_result is None else validation.is_valid and runtime_result.is_valid,
        "errors": authoring_payload["errors"],
        "warnings": authoring_payload["warnings"],
        "suggestions": authoring_payload["suggestions"],
        "edge_contracts": authoring_payload["edge_contracts"],
        "semantic_contracts": authoring_payload["semantic_contracts"],
        "authoring_validation": authoring_payload,
        "runtime_preflight": runtime_result.model_dump() if runtime_result is not None else None,
        "source": None,
        "node_count": len(state.nodes),
        "output_count": len(state.outputs),
        "nodes": [{"id": n.id, "node_type": n.node_type, "plugin": n.plugin} for n in state.nodes],
        "outputs": [{"name": o.name, "plugin": o.plugin} for o in state.outputs],
    }
```

Return:

```python
    return ToolResult(
        success=True,
        updated_state=state,
        validation=validation,
        affected_nodes=(),
        data=summary,
        runtime_preflight=runtime_result,
    )
```

- [ ] **Step 5: Add `runtime_preflight` to `execute_tool()`**

Change the `execute_tool()` signature:

```python
    runtime_preflight: RuntimePreflight | None = None,
```

Add this special case before `diff_pipeline`:

```python
    if tool_name == "preview_pipeline":
        return _execute_preview_pipeline(
            arguments,
            state,
            catalog,
            data_dir,
            runtime_preflight=runtime_preflight,
        )
```

- [ ] **Step 6: Build the runtime preflight callback in composer service**

In `src/elspeth/web/composer/service.py`, import:

```python
from functools import partial

from elspeth.web.composer import yaml_generator
from elspeth.web.execution.schemas import ValidationResult
from elspeth.web.execution.validation import validate_pipeline
```

Store settings in `ComposerServiceImpl.__init__()`:

```python
        self._settings = settings
```

Add:

```python
    def _runtime_preflight(self, state: CompositionState, user_id: str | None) -> ValidationResult:
        return validate_pipeline(
            state,
            self._settings,
            yaml_generator,
            secret_service=self._secret_service,
            user_id=user_id,
        )
```

Pass into `execute_tool()`:

```python
                        runtime_preflight=partial(self._runtime_preflight, user_id=user_id),
```

Track preview preflight in `_compose_loop()`:

```python
                last_runtime_preflight = result.runtime_preflight or last_runtime_preflight
```

Initialize `last_runtime_preflight: ValidationResult | None = None` before the loop.

- [ ] **Step 7: Run preview tests**

Run:

```bash
uv run pytest -q tests/unit/web/composer/test_tools.py::TestPreviewPipeline
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add src/elspeth/web/composer/tools.py src/elspeth/web/composer/service.py tests/unit/web/composer/test_tools.py tests/unit/web/composer/test_service.py
git commit -m "feat(composer): expose runtime preflight in pipeline preview"
```

---

### Task 4: Gate Final Composer Responses And Preserve Raw Model Text

**Files:**
- Modify: `src/elspeth/web/composer/protocol.py`
- Modify: `src/elspeth/web/composer/service.py`
- Test: `tests/unit/web/composer/test_service.py`

- [ ] **Step 1: Add failing final-gate tests**

Append to `tests/unit/web/composer/test_service.py`:

```python
class TestComposerRuntimePreflightFinalGate:
    @pytest.mark.asyncio
    async def test_changed_state_completion_is_replaced_when_runtime_preflight_fails(self) -> None:
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()
        changed_state = state.with_source(
            SourceSpec(
                plugin="csv",
                on_success="main",
                options={"path": "/data/blobs/input.csv", "schema": {"mode": "observed"}},
                on_validation_failure="discard",
            )
        ).with_output(
            OutputSpec(
                name="main",
                plugin="csv",
                options={"path": "/data/outputs/out.csv", "schema": {"mode": "observed"}},
                on_write_failure="discard",
            )
        )
        changed_state = replace(changed_state, version=state.version + 1)

        llm_response = _make_llm_response(content="The pipeline is complete and valid.")
        failed_preflight = ValidationResult(
            is_valid=False,
            checks=[
                ValidationCheck(
                    name="settings_load",
                    passed=False,
                    detail="Forbidden name: 'end_of_source'",
                )
            ],
            errors=[
                ValidationError(
                    component_id="agg1",
                    component_type="aggregation",
                    message="Forbidden name: 'end_of_source'",
                    suggestion="Omit trigger for end-of-source-only aggregation.",
                )
            ],
        )

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = llm_response
            with patch.object(service, "_runtime_preflight", return_value=failed_preflight) as mock_preflight:
                result = await service._finalize_no_tool_response(
                    content="The pipeline is complete and valid.",
                    state=changed_state,
                    initial_version=state.version,
                    user_id="user-1",
                    last_runtime_preflight=None,
                )

        assert "runtime preflight failed" in result.message.lower()
        assert "Forbidden name: 'end_of_source'" in result.message
        assert "complete and valid" not in result.message.lower()
        assert result.raw_assistant_content == "The pipeline is complete and valid."
        assert result.runtime_preflight == failed_preflight
        mock_preflight.assert_called_once_with(changed_state, "user-1")

    @pytest.mark.asyncio
    async def test_unchanged_text_without_preview_does_not_run_preflight(self) -> None:
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        with patch.object(service, "_runtime_preflight") as mock_preflight:
            result = await service._finalize_no_tool_response(
                content="I can help with that.",
                state=state,
                initial_version=state.version,
                user_id="user-1",
                last_runtime_preflight=None,
            )

        assert result.message == "I can help with that."
        assert result.raw_assistant_content is None
        assert result.runtime_preflight is None
        mock_preflight.assert_not_called()

    @pytest.mark.asyncio
    async def test_passing_preflight_preserves_original_message_verbatim(self) -> None:
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()
        changed_state = replace(state, version=state.version + 1)
        passed_preflight = ValidationResult(is_valid=True, checks=[], errors=[])

        with patch.object(service, "_runtime_preflight", return_value=passed_preflight):
            result = await service._finalize_no_tool_response(
                content="The pipeline is complete and valid.",
                state=changed_state,
                initial_version=state.version,
                user_id="user-1",
                last_runtime_preflight=None,
            )

        assert result.message == "The pipeline is complete and valid."
        assert result.raw_assistant_content is None
        assert result.runtime_preflight == passed_preflight

    @pytest.mark.asyncio
    async def test_unexpected_preflight_exception_preserves_partial_state(self) -> None:
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()
        changed_state = replace(state, version=state.version + 1)

        with patch.object(service, "_runtime_preflight", side_effect=RuntimeError("boom")):
            with pytest.raises(ComposerRuntimePreflightError) as exc_info:
                await service._finalize_no_tool_response(
                    content="The pipeline is complete.",
                    state=changed_state,
                    initial_version=state.version,
                    user_id="user-1",
                    last_runtime_preflight=None,
                )

        assert exc_info.value.partial_state == changed_state
        assert exc_info.value.exc_class == "RuntimeError"
```

Add imports:

```python
from dataclasses import replace
from elspeth.web.composer.protocol import ComposerRuntimePreflightError
from elspeth.web.execution.schemas import ValidationCheck, ValidationError, ValidationResult
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
uv run pytest -q tests/unit/web/composer/test_service.py::TestComposerRuntimePreflightFinalGate
```

Expected: fail because `ComposerResult.raw_assistant_content`, `ComposerRuntimePreflightError`, and deterministic final gating do not exist.

- [ ] **Step 3: Extend composer protocol**

Modify `src/elspeth/web/composer/protocol.py`:

```python
from elspeth.web.execution.schemas import ValidationResult
```

Update `ComposerResult`:

```python
@dataclass(frozen=True, slots=True)
class ComposerResult:
    """Result of a compose() call."""

    message: str
    state: CompositionState
    runtime_preflight: ValidationResult | None = None
    raw_assistant_content: str | None = None
```

Add:

```python
class ComposerRuntimePreflightError(ComposerServiceError):
    """Unexpected internal failure while running final composer preflight."""

    _FROZEN_ATTRS: ClassVar[frozenset[str]] = frozenset({"partial_state", "exc_class"})

    def __init__(self, *, original_exc: BaseException, partial_state: CompositionState | None) -> None:
        super().__init__("Composer runtime preflight failed internally.")
        self.original_exc = original_exc
        self.partial_state = partial_state
        self.exc_class = type(original_exc).__name__

    def __setattr__(self, name: str, value: object) -> None:
        if name in type(self)._FROZEN_ATTRS and name in self.__dict__:
            raise AttributeError(f"{type(self).__name__}.{name} is frozen after construction")
        super().__setattr__(name, value)

    @classmethod
    def capture(
        cls,
        exc: BaseException,
        *,
        state: CompositionState,
        initial_version: int,
    ) -> ComposerRuntimePreflightError:
        partial = state if state.version > initial_version else None
        return cls(original_exc=exc, partial_state=partial)
```

- [ ] **Step 4: Add deterministic finalization in composer service**

In `src/elspeth/web/composer/service.py`, import `ComposerRuntimePreflightError` and remove any planned regex import.

Add helper:

```python
    @staticmethod
    def _runtime_preflight_failure_message(result: ValidationResult) -> str:
        if result.errors:
            first = result.errors[0]
            suggestion = f" Suggested fix: {first.suggestion}" if first.suggestion else ""
            return f"I cannot mark this pipeline complete yet because runtime preflight failed: {first.message}.{suggestion}"
        failed_checks = [check for check in result.checks if not check.passed]
        if failed_checks:
            return f"I cannot mark this pipeline complete yet because runtime preflight failed: {failed_checks[0].detail}."
        return "I cannot mark this pipeline complete yet because runtime preflight failed."

    async def _finalize_no_tool_response(
        self,
        *,
        content: str,
        state: CompositionState,
        initial_version: int,
        user_id: str | None,
        last_runtime_preflight: ValidationResult | None,
    ) -> ComposerResult:
        runtime_result = last_runtime_preflight
        if state.version > initial_version:
            try:
                runtime_result = await run_sync_in_worker(self._runtime_preflight, state, user_id)
            except Exception as exc:
                raise ComposerRuntimePreflightError.capture(
                    exc,
                    state=state,
                    initial_version=initial_version,
                ) from exc

        if runtime_result is None:
            return ComposerResult(message=content, state=state)

        if not runtime_result.is_valid:
            return ComposerResult(
                message=self._runtime_preflight_failure_message(runtime_result),
                state=state,
                runtime_preflight=runtime_result,
                raw_assistant_content=content,
            )

        return ComposerResult(message=content, state=state, runtime_preflight=runtime_result)
```

This intentionally catches broad `Exception` only at the LLM-service boundary to convert an unexpected internal preflight failure into a typed 500 path with partial-state preservation. Do not convert those exceptions into a user-fixable `ValidationResult`.

- [ ] **Step 5: Replace no-tool return sites**

In both no-tool return sites inside `_compose_loop()`, return:

```python
                return await self._finalize_no_tool_response(
                    content=assistant_message.content or "",
                    state=state,
                    initial_version=initial_version,
                    user_id=user_id,
                    last_runtime_preflight=last_runtime_preflight,
                )
```

- [ ] **Step 6: Run final-gate tests**

Run:

```bash
uv run pytest -q tests/unit/web/composer/test_service.py::TestComposerRuntimePreflightFinalGate
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add src/elspeth/web/composer/protocol.py src/elspeth/web/composer/service.py tests/unit/web/composer/test_service.py
git commit -m "fix(composer): gate final responses on runtime preflight"
```

---

### Task 5: Persist Runtime Validity And Raw Model Text Across All Composer Write Paths

**Files:**
- Modify: `src/elspeth/web/sessions/models.py`
- Modify: `src/elspeth/web/sessions/protocol.py`
- Modify: `src/elspeth/web/sessions/service.py`
- Modify: `src/elspeth/web/sessions/schemas.py`
- Modify: `src/elspeth/web/sessions/routes.py`
- Test: `tests/unit/web/sessions/test_routes.py`

- [ ] **Step 1: Add route/helper tests for state persistence semantics**

Append to `tests/unit/web/sessions/test_routes.py`:

```python
def test_runtime_preflight_errors_are_used_for_composition_state_persistence() -> None:
    from elspeth.web.sessions.routes import _composer_persisted_validation

    authoring = ValidationSummary(is_valid=True, errors=(), warnings=(), suggestions=())
    runtime = ValidationResult(
        is_valid=False,
        checks=[
            ValidationCheck(
                name="plugin_instantiation",
                passed=False,
                detail="Invalid configuration for transform 'batch_stats'",
            )
        ],
        errors=[
            ValidationError(
                component_id="agg1",
                component_type="transform",
                message="Invalid configuration for transform 'batch_stats'",
                suggestion="Remove required_input_fields from batch-aware transform options.",
            )
        ],
    )

    is_valid, messages = _composer_persisted_validation(authoring, runtime, preflight_failed=False)

    assert is_valid is False
    assert messages == ["Invalid configuration for transform 'batch_stats'"]


def test_authoring_validity_is_not_marked_valid_when_runtime_preflight_failed_internally() -> None:
    from elspeth.web.sessions.routes import _composer_persisted_validation

    authoring = ValidationSummary(is_valid=True, errors=(), warnings=(), suggestions=())

    is_valid, messages = _composer_persisted_validation(authoring, None, preflight_failed=True)

    assert is_valid is False
    assert messages == ["runtime_preflight_failed"]
```

Add imports:

```python
from elspeth.web.composer.state import ValidationSummary
from elspeth.web.execution.schemas import ValidationCheck, ValidationError, ValidationResult
```

Also extend the existing write-path route tests so B1 is mechanically pinned, not just described:

- Add a recompose success-path test that mirrors the existing `/recompose` setup: seed a session, seed a last user message, have the composer return a changed `ComposerResult` with `runtime_preflight=ValidationResult(is_valid=False, ...)`, then assert the persisted current state has `is_valid is False` and the runtime error message.
- Extend `test_recompose_convergence_preserves_partial_state` by patching `elspeth.web.sessions.routes._runtime_preflight_for_state` to return an invalid `ValidationResult`; assert the persisted partial-state row is invalid with the runtime error message while the HTTP response remains 422.
- Extend `test_compose_plugin_crash_persists_partial_state` the same way; assert the persisted partial-state row is invalid with the runtime error message while the HTTP response remains the structured 500.
- The send-message success path is covered by the raw-content test below because it persists a changed state with an invalid `runtime_preflight`.

- [ ] **Step 2: Add raw content persistence test**

Append:

```python
def test_assistant_raw_content_is_persisted_but_not_returned(tmp_path) -> None:
    app, service = _make_app(tmp_path)
    client = TestClient(app)

    session_resp = client.post("/api/sessions", json={"title": "Chat"})
    session_id = uuid.UUID(session_resp.json()["id"])

    changed_state = CompositionState(
        source=None,
        nodes=(),
        edges=(),
        outputs=(),
        metadata=PipelineMetadata(name="runtime preflight failed"),
        version=_EMPTY_STATE.version + 1,
    )
    composer_result = ComposerResult(
        message="I cannot mark this pipeline complete yet because runtime preflight failed: bad config.",
        state=changed_state,
        runtime_preflight=ValidationResult(
            is_valid=False,
            checks=[],
            errors=[
                ValidationError(
                    component_id=None,
                    component_type=None,
                    message="bad config",
                    suggestion=None,
                )
            ],
        ),
        raw_assistant_content="The pipeline is complete and valid.",
    )
    composer = AsyncMock()
    composer.compose = AsyncMock(return_value=composer_result)
    app.state.composer_service = composer

    resp = client.post(f"/api/sessions/{session_id}/messages", json={"content": "build it"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["message"]["content"].startswith("I cannot mark this pipeline complete")
    assert "raw_content" not in body["message"]

    loop = asyncio.new_event_loop()
    try:
        messages = loop.run_until_complete(service.get_messages(session_id, limit=None))
    finally:
        loop.close()
    assistant = next(message for message in messages if message.role == "assistant")
    assert assistant.raw_content == "The pipeline is complete and valid."
```

- [ ] **Step 3: Run failing route tests**

Run:

```bash
uv run pytest -q tests/unit/web/sessions/test_routes.py -k "runtime_preflight_errors_are_used or runtime_preflight_failed_internally or raw_content"
```

Expected: fail because the helper, raw-content column, and service parameter do not exist yet.

- [ ] **Step 4: Add `chat_messages.raw_content` to session models and DTOs**

Modify `src/elspeth/web/sessions/models.py`:

```python
    Column("raw_content", Text, nullable=True),
```

Place it after `Column("content", Text, nullable=False)`.

Modify `ChatMessageRecord` in `src/elspeth/web/sessions/protocol.py`:

```python
    raw_content: str | None = None
```

Place it after `content` if test factories use keyword args. If positional construction breaks, update call sites to keywords.

Modify `SessionServiceProtocol.add_message()`:

```python
        raw_content: str | None = None,
```

Modify `SessionServiceImpl.add_message()` in `src/elspeth/web/sessions/service.py`:

```python
        raw_content: str | None = None,
```

Include it in the insert:

```python
                        raw_content=raw_content,
```

Include it in the returned `ChatMessageRecord`:

```python
            raw_content=raw_content,
```

Modify `_row_to_message_record()` or equivalent row conversion to pass `raw_content=row.raw_content`.

Do not add `raw_content` to `ChatMessageResponse` in `src/elspeth/web/sessions/schemas.py`; it is persisted for audit/provenance, not returned to normal clients.

- [ ] **Step 5: Add route validation helpers**

In `src/elspeth/web/sessions/routes.py`, import:

```python
from typing import Any, Literal, cast

from elspeth.web.composer import yaml_generator
from elspeth.web.composer.protocol import ComposerRuntimePreflightError
from elspeth.web.execution.validation import validate_pipeline
from elspeth.web.execution.schemas import ValidationResult
```

If `routes.py` already imports `cast`, extend that import rather than adding a second `typing` import. Keep the existing `ValidationEntry` import; the partial-state guard still needs it.

Add helpers near `_state_response()`:

```python
_PreflightExceptionPolicy = Literal["raise", "persist_invalid"]


def _composer_persisted_validation(
    authoring: ValidationSummary,
    runtime_preflight: ValidationResult | None,
    *,
    preflight_failed: bool,
) -> tuple[bool, list[str] | None]:
    """Return persisted validity/errors for a composer-produced state."""
    if runtime_preflight is not None:
        messages = [error.message for error in runtime_preflight.errors]
        return runtime_preflight.is_valid, messages or None
    if preflight_failed:
        return False, ["runtime_preflight_failed"]
    messages = [error.message for error in authoring.errors]
    return authoring.is_valid, messages or None


async def _runtime_preflight_for_state(
    state: CompositionState,
    *,
    settings: Any,
    secret_service: Any | None,
    user_id: str | None,
) -> ValidationResult:
    return await run_sync_in_worker(
        validate_pipeline,
        state,
        settings,
        yaml_generator,
        secret_service=secret_service,
        user_id=user_id,
    )


async def _state_data_from_composer_state(
    state: CompositionState,
    *,
    settings: Any,
    secret_service: Any | None,
    user_id: str | None,
    runtime_preflight: ValidationResult | None,
    preflight_failed: bool,
    preflight_exception_policy: _PreflightExceptionPolicy,
    initial_version: int | None,
    log_prefix: str,
    session_id: UUID,
) -> tuple[CompositionStateData, ValidationSummary]:
    try:
        authoring = state.validate()
    except (ValueError, TypeError, KeyError) as val_err:
        slog.warning(
            f"{log_prefix}_validation_failed",
            session_id=str(session_id),
            exc_class=type(val_err).__name__,
        )
        authoring = ValidationSummary(
            is_valid=False,
            errors=(ValidationEntry("validation", "validation_failed", "high"),),
        )

    runtime = runtime_preflight
    failed = preflight_failed
    if runtime is None and not failed and authoring.is_valid:
        try:
            runtime = await _runtime_preflight_for_state(
                state,
                settings=settings,
                secret_service=secret_service,
                user_id=user_id,
            )
        except Exception as exc:
            if preflight_exception_policy == "raise":
                raise ComposerRuntimePreflightError.capture(
                    exc,
                    state=state,
                    initial_version=initial_version if initial_version is not None else state.version,
                ) from exc
            slog.error(
                "composer_runtime_preflight_failed",
                session_id=str(session_id),
                exc_class=type(exc).__name__,
            )
            failed = True
    persisted_is_valid, persisted_errors = _composer_persisted_validation(
        authoring,
        runtime,
        preflight_failed=failed,
    )
    state_d = state.to_dict()
    return (
        CompositionStateData(
            source=state_d["source"],
            nodes=state_d["nodes"],
            edges=state_d["edges"],
            outputs=state_d["outputs"],
            metadata_=state_d["metadata"],
            is_valid=persisted_is_valid,
            validation_errors=persisted_errors,
        ),
        authoring,
    )
```

This helper deliberately preserves the existing damaged-partial-state guard from `_handle_convergence_error()` and `_handle_plugin_crash()`: only `state.validate()` may catch `(ValueError, TypeError, KeyError)`. A `TypeError` or `KeyError` from `state.to_dict()` or `CompositionStateData(...)` is a Tier 1 invariant bug and must still propagate. Do not broaden the DB persistence guards around this helper; existing `SQLAlchemyError`-only catches remain the right boundary.

Use `preflight_exception_policy="raise"` for normal `send_message` and `recompose` success paths so unexpected internal preflight failures become `ComposerRuntimePreflightError` and return the typed partial-state-preserving 500. Use `preflight_exception_policy="persist_invalid"` only inside `_handle_convergence_error()` and `_handle_plugin_crash()`, where preserving the original 422/500 response is more important than running preflight again. In both cases, do not log raw exception text; the allowed diagnostics are event name, session id, and sanitized exception class.

- [ ] **Step 6: Update all four state write paths**

In `send_message` and `recompose`, replace local `result.state.validate()` / `CompositionStateData(...)` construction with:

```python
                state_data, validation = await _state_data_from_composer_state(
                    result.state,
                    settings=settings,
                    secret_service=request.app.state.scoped_secret_resolver,
                    user_id=str(user.user_id),
                    runtime_preflight=result.runtime_preflight,
                    preflight_failed=False,
                    preflight_exception_policy="raise",
                    initial_version=state.version,
                    log_prefix="compose",  # use "recompose" in the recompose handler
                    session_id=session.id,
                )
```

When saving the assistant message in both handlers, pass:

```python
                raw_content=result.raw_assistant_content,
```

Update `_handle_convergence_error()` and `_handle_plugin_crash()` signatures to accept:

```python
    settings: Any,
    secret_service: Any | None,
```

Inside both helpers, replace local `CompositionStateData(...)` construction with:

```python
            state_data, validation = await _state_data_from_composer_state(
                exc.partial_state,
                settings=settings,
                secret_service=secret_service,
                user_id=user_id,
                runtime_preflight=None,
                preflight_failed=False,
                preflight_exception_policy="persist_invalid",
                initial_version=None,
                log_prefix=log_prefix,
                session_id=session_id,
            )
```

Update all call sites to pass `settings=request.app.state.settings` and `secret_service=request.app.state.scoped_secret_resolver`.

Add a catch for `ComposerRuntimePreflightError` before the generic `ComposerServiceError` catch in both `send_message` and `recompose`. Reuse `_handle_plugin_crash()` response semantics, but use `log_prefix` values `compose_runtime_preflight` and `recompose_runtime_preflight`, and raise HTTP 500 from `exc.original_exc`.

- [ ] **Step 7: Run route tests**

Run:

```bash
uv run pytest -q tests/unit/web/sessions/test_routes.py
```

Expected: pass. Update the known in-file helper `_ProgressRouteSessionService.add_message()` to accept `raw_content: str | None = None` and pass it into `ChatMessageRecord`. `_make_composer_mock()` can continue omitting raw content because `ComposerResult.raw_assistant_content` defaults to `None`.

- [ ] **Step 8: Commit**

```bash
git add src/elspeth/web/sessions/models.py src/elspeth/web/sessions/protocol.py src/elspeth/web/sessions/service.py src/elspeth/web/sessions/schemas.py src/elspeth/web/sessions/routes.py tests/unit/web/sessions/test_routes.py
git commit -m "fix(web): persist runtime composer validity across write paths"
```

---

### Task 6: Gate YAML Export Against The Exact State Snapshot

**Files:**
- Modify: `src/elspeth/web/sessions/routes.py`
- Test: `tests/unit/web/sessions/test_routes.py`

- [ ] **Step 1: Add failing exact-snapshot YAML export test**

Add near existing state YAML route tests:

If Task 5 has not already added it, update the test import to:

```python
from unittest.mock import AsyncMock, patch
```

```python
@pytest.mark.asyncio
async def test_get_state_yaml_validates_exact_state_snapshot(tmp_path) -> None:
    app, service = _make_app(tmp_path)
    client = TestClient(app)
    session = await service.create_session("alice", "Pipeline", "local")
    await service.save_composition_state(
        session.id,
        CompositionStateData(
            source={
                "plugin": "csv",
                "on_success": "main",
                "options": {"path": "/data/blobs/input.csv", "schema": {"mode": "observed"}},
                "on_validation_failure": "quarantine",
            },
            outputs=[
                {
                    "name": "main",
                    "plugin": "csv",
                    "options": {"path": "outputs/out.csv", "schema": {"mode": "observed"}},
                    "on_write_failure": "discard",
                }
            ],
            metadata_={"name": "Snapshot", "description": ""},
            is_valid=True,
        ),
    )

    captured_states: list[CompositionState] = []

    async def fake_runtime_preflight(state, *, settings, secret_service, user_id):
        captured_states.append(state)
        return ValidationResult(is_valid=False, checks=[], errors=[
            ValidationError(
                component_id="source",
                component_type="source",
                message="runtime preflight failed for captured state",
                suggestion=None,
            )
        ])

    with patch("elspeth.web.sessions.routes._runtime_preflight_for_state", side_effect=fake_runtime_preflight):
        resp = client.get(f"/api/sessions/{session.id}/state/yaml")

    assert resp.status_code == 409
    assert "runtime preflight failed for captured state" in resp.json()["detail"]
    assert len(captured_states) == 1
    assert captured_states[0].source is not None
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
uv run pytest -q tests/unit/web/sessions/test_routes.py::test_get_state_yaml_validates_exact_state_snapshot
```

Expected: fail because `get_state_yaml()` currently validates authoring state only.

- [ ] **Step 3: Update `get_state_yaml()`**

In `src/elspeth/web/sessions/routes.py`, replace authoring-only validation with:

```python
        state = _state_from_record(state_record)
        runtime_validation = await _runtime_preflight_for_state(
            state,
            settings=request.app.state.settings,
            secret_service=request.app.state.scoped_secret_resolver,
            user_id=str(user.user_id),
        )
        if not runtime_validation.is_valid:
            detail = "Current composition state failed runtime preflight. Fix validation errors before exporting YAML."
            if runtime_validation.errors:
                detail = f"{detail} First error: {runtime_validation.errors[0].message}"
            raise HTTPException(status_code=409, detail=detail)
        yaml_str = generate_yaml(state)
```

Do not call `execution_service.validate(session.id)` here; that method re-reads current state internally and can validate a different snapshot than the route serializes.

- [ ] **Step 4: Run YAML route tests**

Run:

```bash
uv run pytest -q tests/unit/web/sessions/test_routes.py -k state_yaml
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/elspeth/web/sessions/routes.py tests/unit/web/sessions/test_routes.py
git commit -m "fix(web): validate exact state before yaml export"
```

---

### Task 7: Add Corrected Scenario-Level Composer Eval Regressions

**Files:**
- Modify: `tests/integration/pipeline/test_composer_llm_eval_characterization.py`

- [ ] **Step 1: Add corrected preview/runtime scenario test**

Append:

```python
def test_runtime_preflight_preview_blocks_scenario_2_invalid_trigger(tmp_path: Path) -> None:
    """Scenario 2: preview must show runtime failure, not authoring-only validity."""
    data_dir, source_path, output_path = _scenario_2_files(tmp_path)
    state = _aggregation_state(
        source_path,
        output_path,
        trigger={"condition": "end_of_source"},
        aggregation_options={"schema": {"mode": "observed"}, "value_field": "amount"},
    )
    settings = _web_settings(data_dir)

    runtime_preflight = lambda candidate: validate_pipeline(candidate, settings, composer_yaml_generator)
    preview = execute_tool(
        "preview_pipeline",
        {},
        state,
        _mock_catalog(),
        data_dir=str(data_dir),
        runtime_preflight=runtime_preflight,
    )

    assert preview.success is True
    assert preview.data["is_valid"] is False
    assert preview.data["runtime_preflight"]["is_valid"] is False
    assert "end_of_source" in json.dumps(preview.data["runtime_preflight"])
```

- [ ] **Step 2: Add corrected final gate scenario test**

Append:

```python
@pytest.mark.asyncio
async def test_final_completion_claim_is_replaced_by_runtime_preflight_failure(tmp_path: Path) -> None:
    """The composer must not repeat an LLM complete/valid claim after dry-run failure."""
    data_dir, source_path, output_path = _scenario_2_files(tmp_path)
    settings = _web_settings(data_dir)
    composer = ComposerServiceImpl(catalog=_mock_catalog(), settings=settings)
    state = _aggregation_state(
        source_path,
        output_path,
        trigger={"condition": "end_of_source"},
        aggregation_options={"schema": {"mode": "observed"}, "value_field": "amount"},
    )
    changed_state = replace(state, version=state.version + 1)

    result = await composer._finalize_no_tool_response(
        content="The pipeline is complete and valid.",
        state=changed_state,
        initial_version=state.version,
        user_id=EVAL_USER_ID,
        last_runtime_preflight=None,
    )

    assert "runtime preflight failed" in result.message.lower()
    assert "complete and valid" not in result.message.lower()
    assert result.raw_assistant_content == "The pipeline is complete and valid."
    assert result.runtime_preflight is not None
    assert result.runtime_preflight.is_valid is False
```

Add import if needed:

```python
from dataclasses import replace
```

- [ ] **Step 3: Run scenario tests**

Run:

```bash
uv run pytest -q tests/integration/pipeline/test_composer_llm_eval_characterization.py -k "runtime_preflight or final_completion_claim"
```

Expected: pass.

- [ ] **Step 4: Run full characterization suite**

Run:

```bash
uv run pytest -q tests/integration/pipeline/test_composer_llm_eval_characterization.py
```

Expected: pass, respecting existing expected xfails.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/pipeline/test_composer_llm_eval_characterization.py
git commit -m "test(composer): cover runtime preflight eval scenarios"
```

---

### Task 8: Final Verification And Tracker Closeout

**Files:**
- No code files unless verification exposes a real regression.
- Update tracker issue `elspeth-34baf10c01`.

- [ ] **Step 1: Run targeted tests**

Run:

```bash
uv run pytest -q tests/unit/web/execution/test_validation.py tests/unit/web/execution/test_service.py tests/unit/web/composer/test_tools.py::TestPreviewPipeline tests/unit/web/composer/test_service.py::TestComposerRuntimePreflightFinalGate tests/unit/web/sessions/test_routes.py -k "state_yaml or runtime_preflight or raw_content or composer"
```

Expected: pass.

- [ ] **Step 2: Run composer eval characterization**

Run:

```bash
uv run pytest -q tests/integration/pipeline/test_composer_llm_eval_characterization.py
```

Expected: pass, respecting existing expected xfails.

- [ ] **Step 3: Run lint on touched files**

Run:

```bash
uv run ruff check src/elspeth/web/execution/preflight.py src/elspeth/web/execution/protocol.py src/elspeth/web/execution/validation.py src/elspeth/web/execution/service.py src/elspeth/web/composer/tools.py src/elspeth/web/composer/service.py src/elspeth/web/composer/protocol.py src/elspeth/web/sessions/models.py src/elspeth/web/sessions/protocol.py src/elspeth/web/sessions/service.py src/elspeth/web/sessions/schemas.py src/elspeth/web/sessions/routes.py tests/unit/web/execution/test_validation.py tests/unit/web/execution/test_service.py tests/unit/web/composer/test_tools.py tests/unit/web/composer/test_service.py tests/unit/web/sessions/test_routes.py tests/integration/pipeline/test_composer_llm_eval_characterization.py
```

Expected: pass.

- [ ] **Step 4: Run type checking for touched packages**

Run:

```bash
uv run mypy src/elspeth/web/execution src/elspeth/web/composer src/elspeth/web/sessions
```

Expected: pass or existing unrelated baseline only. Fix new errors before continuing.

- [ ] **Step 5: Check dependent tracker context before closing**

Run:

```bash
filigree show elspeth-34baf10c01
filigree show elspeth-528bde62bb
filigree show elspeth-87f6d5dea5
filigree show elspeth-f936acd071
filigree show elspeth-dcf12c061b
```

Expected: confirm `elspeth-34baf10c01` itself is complete. Do not close sibling issues unless their acceptance criteria were explicitly implemented and verified.

- [ ] **Step 6: Add tracker evidence**

Run:

```bash
filigree add-comment elspeth-34baf10c01 "Implemented runtime-equivalent composer preflight. Verification: execution validation/service tests, composer preview/final-gate tests, session route persistence/YAML export tests, and composer LLM eval characterization suite."
```

- [ ] **Step 7: Close issue only if acceptance criteria are met**

Run:

```bash
filigree close elspeth-34baf10c01 --reason="Composer preview and final responses now use runtime preflight; persisted validity and YAML export are gated by runtime validation; targeted tests pass."
```

---

## Follow-Up Observations To Track Separately

- Runtime preflight currently resolves only `source.options.{path,file}` and `sinks.<name>.options.{path,file}`. If transform or aggregation plugins carry filesystem paths, create a separate issue for transform/aggregation path resolution.
- Runtime-flavored validation strings may appear under existing frontend "Errors" labels. If this is confusing in UX review, create a frontend copy issue; do not block runtime parity on it.
- `elspeth-dcf12c061b` remains relevant for LLM transform authoring. This preflight work can still land independently because runtime validation catches plugin config failures, but LLM schema guidance may still need its own fix.

## Self-Review

Spec coverage:

- Composer validation round-trips generated YAML through runtime settings loader: Tasks 1 and 2.
- Path allowlist and relative path parity: Task 1.
- Trigger grammar, batch dispatch, and plugin pre-execution blockers composer-visible: Tasks 3 and 7.
- Composer cannot emit complete-and-valid claims after runtime preflight failure: Task 4.
- Raw LLM content remains attributable when visible text is replaced: Tasks 4 and 5.
- Persisted state truthfulness across all composer write paths: Task 5.
- YAML export truthfulness without a double-read race: Task 6.
- Scenario 1B/3 blob and Scenario 2 aggregation coverage: Task 7 plus existing characterization tests.
- Audit/logging policy: no row-level logs added; pre-execution validation facts live in `composition_states`, chat message provenance, and HTTP responses.

Placeholder scan:

- No red-flag placeholder markers from the writing-plans checklist are present in implementation steps.

Type consistency:

- `ValidationSettings` is the protocol accepted by `validate_pipeline()`.
- `RuntimePreflight` is a callable from `CompositionState` to `ValidationResult`.
- `RuntimeGraphBundle.plugin_bundle` is typed as `PluginBundle`; `RuntimeGraphBundle` is not frozen because it carries mutable `ExecutionGraph`.
- `ComposerResult.runtime_preflight` is `ValidationResult | None`.
- `ComposerResult.raw_assistant_content` is `str | None`.
- `ToolResult.runtime_preflight` is `ValidationResult | None`.
- `ChatMessageRecord.raw_content` is persisted but not exposed in `ChatMessageResponse`.
