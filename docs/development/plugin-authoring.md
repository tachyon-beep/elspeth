# Plugin Authoring Guide

Audience: Plugin authors and integrators building datasources, experiment plugins, sinks, or middleware for Elspeth.

This guide explains plugin types, registration APIs, schemas, security context, testing, and best practices. It reflects Phase 2 layout and WP002 schema enforcement.

## 1) Plugin Types & Locations

- Nodes (Phase 2 layout):
  - Sources: `src/elspeth/plugins/nodes/sources/`
  - Transforms (LLM adapters): `src/elspeth/plugins/nodes/transforms/`
  - Sinks: `src/elspeth/plugins/nodes/sinks/`
- Experiment plugins (row/aggregation/baseline/validation/early-stop):
  - `src/elspeth/plugins/experiments/{row,aggregators,baseline,validation,early_stop}/`
- LLM middleware: `src/elspeth/plugins/llms/middleware/` (registry lives under `core/registries/middleware.py`).

Naming: module names should be descriptive (e.g., `score_extractor.py`, `analytics_report.py`). Classes use `PascalCase`; functions and files use `snake_case`.

## 2) Registration APIs (Factories + Schemas)

Experiment plugin registries (facade): `elspeth.core.experiments.plugin_registry`

```python
from elspeth.core.experiments.plugin_registry import (
    register_row_plugin,
    register_aggregation_plugin,
    register_baseline_plugin,
    register_validation_plugin,
    register_early_stop_plugin,
)

def make_row(options, context):
    class MyRow:
        name = "my_row"
        def input_schema(self):  # Optional unless enforced (see §4)
            return None
        def process_row(self, row: dict, responses: dict) -> dict:
            return {}
    return MyRow()

register_row_plugin(
    "my_row",
    make_row,
    schema={"type": "object", "properties": {}, "additionalProperties": True},
    requires_input_schema=False,  # set True when plugin depends on row fields
)
```

Sinks, datasources, middleware use core registries:

```python
from elspeth.core.registries.sink import sink_registry
from elspeth.core.base.protocols import ResultSink, Artifact, ArtifactDescriptor

class MySink(ResultSink):
    def __init__(self, *, path: str, **kwargs):
        self.path = path
    def write(self, results: dict, *, metadata: dict | None = None) -> None:
        # persist results
        ...
    def produces(self) -> list[ArtifactDescriptor]:  # REQUIRED (Phase 2)
        return [ArtifactDescriptor(name="json", type="application/json", persist=True, alias="json")]
    def consumes(self) -> list[str]:  # REQUIRED (Phase 2)
        return []
    def collect_artifacts(self) -> dict[str, Artifact]:  # Optional
        return {}

sink_registry.register(
    "my_sink",
    lambda options, ctx: MySink(**options),
    schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
)
```

Datasources must declare or infer an output schema (see §3, §4) and should derive from a shared base where practical (e.g., `BaseCSVDataSource`).

## 3) Security & Plugin Context

All plugins receive a `PluginContext` at creation. The registry stamps:

- `security_level` and `determinism_level` (attributes: `security_level`, `_elspeth_security_level`, `determinism_level`, `_elspeth_determinism_level`)
- `plugin_context` and `_elspeth_context` (immutable Pydantic context)
- A structured `plugin_logger` via `elspeth.core.utils.logging.attach_plugin_logger`

Never downgrade security levels in code. Use the attached logger to record events; avoid printing secrets.

## 4) WP002: DataFrame Schemas & Validation

- Datasources: must attach a `DataFrameSchema` to the returned DataFrame (either via explicit config schema → `schema_from_config()` or inference when enabled).
  - Example (CSV datasource config):
    ```yaml
    datasource:
      plugin: local_csv
      options:
        path: data/input.csv
        schema:
          APPID: str
          title: string
          score: float
    ```
- Experiment plugins: may declare `input_schema()` to express required columns/types.
  - Enforcement: registries can mark plugins as requiring an input schema via `requires_input_schema=True`. Preflight (`validate-schemas`) and the runner will fail if missing.
- CLI preflight (`python -m elspeth.cli validate-schemas`):
  - Requires datasource schema
  - Validates plugin compatibility (`validate_plugin_schemas`) and presence of `prompt_fields` in the datasource schema
  - Ensures sinks implement `produces()`/`consumes()`

See code: `src/elspeth/core/base/schema/*`, `src/elspeth/core/experiments/validation.py`.

## 5) Configuration (YAML) → Registry

Experiment definitions supply plugin names and options; the registry validates options against JSON Schemas and constructs instances with context:

```yaml
row_plugins:
  - name: score_extractor
    security_level: OFFICIAL
    determinism_level: guaranteed
    options:
      key: score
aggregator_plugins:
  - name: score_stats
    security_level: OFFICIAL
    determinism_level: guaranteed
```

## 6) Testing Patterns

- Unit tests: construct plugins directly or via registry; use `temporary_override()` to stub factories.
- Schema validation tests: import `validate_plugin_schemas` and `DataFrameSchema` to check compatibility without running the orchestrator.
- CLI tests: use `validate-schemas` subcommand with monkeypatched settings.

Examples:

```python
from elspeth.core.experiments.validation import validate_plugin_schemas
from elspeth.core.base.schema import DataFrameSchema

class DS(DataFrameSchema):
    x: int

class MyRow:
    name = "row"
    def input_schema(self):
        class RequireX(DataFrameSchema):
            x: int
        return RequireX

validate_plugin_schemas(DS, row_plugins=[MyRow()])
```

## 7) External Services & Security Checks

- Use endpoint validators for external HTTP services (OpenAI/Azure) via `elspeth.core.security.approved_endpoints`.
- Honor timeouts/retries and never execute untrusted input (no `eval/exec`).
- For sinks targeting repositories or clouds, implement dry‑run modes and avoid destructive operations.

## 8) Performance & Determinism

- Long‑running or resource‑heavy plugins should expose configuration for concurrency and backpressure; avoid global state and ensure idempotency where applicable.
- For reproducibility, prefer deterministic algorithms and record seeds where randomness is used.

## 9) Checklist for New Plugins

- [ ] Module under correct directory; clear name and docstring
- [ ] Registered with appropriate registry and JSON Schema for options
- [ ] Declares `input_schema()` if it depends on row fields; set `requires_input_schema=True` at registration when required
- [ ] Uses `plugin_logger` for events/errors; no secret leakage
- [ ] Sinks implement `produces()` and `consumes()`; `collect_artifacts()` when exporting files
- [ ] Tests cover option validation, happy paths, error handling; add CLI preflight tests if relevant
- [ ] Documentation updated (brief description in the plugin catalogue)

## 10) References

- Registries: `src/elspeth/core/registries/*`, `src/elspeth/core/experiments/plugin_registry.py`
- Schema base/utilities: `src/elspeth/core/base/schema/*`
- Security model: `docs/architecture/plugin-security-model.md`
- Plugin catalogue: `docs/architecture/plugin-catalogue.md`

## 11) Recipes

### A. Minimal End-to-End Trio (Datasource + Row Plugin + Sink)

1) Register a tiny datasource (returns a DataFrame with an attached schema):

```python
from __future__ import annotations

import pandas as pd
from elspeth.core.base.schema import DataFrameSchema
from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.registries.datasource import datasource_registry


def create_demo_datasource(options: dict, context: PluginContext):
    class DemoSource:
        def load(self) -> pd.DataFrame:
            class DS(DataFrameSchema):  # noqa: N801
                x: int
                name: str

            df = pd.DataFrame({"x": [1, 2], "name": ["a", "b"]})
            df.attrs["schema"] = DS
            return df

    return DemoSource()


datasource_registry.register(
    "demo_source",
    create_demo_datasource,
    schema={"type": "object", "properties": {}, "additionalProperties": True},
)
```

2) Register a row plugin that requires `x`:

```python
from elspeth.core.base.schema import DataFrameSchema
from elspeth.core.experiments.plugin_registry import register_row_plugin


def make_gate(options, context):
    class RequireX:
        name = "require_x"

        def input_schema(self):  # required columns/types
            class RequireXSchema(DataFrameSchema):  # noqa: N801
                x: int

            return RequireXSchema

        def process_row(self, row: dict, responses: dict) -> dict:
            return {"x_doubled": int(row.get("x", 0)) * 2}

    return RequireX()


register_row_plugin(
    "require_x",
    make_gate,
    schema={"type": "object", "properties": {}, "additionalProperties": True},
    requires_input_schema=True,
)
```

3) Register a sink that writes JSON and declares produced/consumed artifacts:

```python
import json
from pathlib import Path
from elspeth.core.base.protocols import ArtifactDescriptor, Artifact
from elspeth.core.registries.sink import sink_registry


def make_json_sink(options, context):
    class JsonSink:
        def __init__(self, *, path: str):
            self.path = Path(path)
            self._last = None

        def write(self, results: dict, *, metadata: dict | None = None) -> None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(results, ensure_ascii=False)
            self.path.write_text(payload, encoding="utf-8")
            self._last = str(self.path)

        def produces(self) -> list[ArtifactDescriptor]:
            return [ArtifactDescriptor(name="json", type="application/json", persist=True, alias="json")]

        def consumes(self) -> list[str]:
            return []

        def collect_artifacts(self) -> dict[str, Artifact]:
            if not self._last:
                return {}
            art = Artifact(id="", type="application/json", path=self._last, metadata={"path": self._last}, persist=True)
            self._last = None
            return {"json": art}

    return JsonSink(**options)


sink_registry.register(
    "json_file",
    make_json_sink,
    schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
)
```

4) Wire it via YAML and run preflight and execution:

```yaml
# settings.yaml
default:
  datasource:
    plugin: demo_source
    security_level: OFFICIAL
    determinism_level: guaranteed
    options: {}
  llm:
    plugin: mock
    security_level: OFFICIAL
    determinism_level: guaranteed
    options: {seed: 1}
  row_plugins:
    - name: require_x
      security_level: OFFICIAL
      determinism_level: guaranteed
  sinks:
    - plugin: json_file
      security_level: OFFICIAL
      determinism_level: guaranteed
      options: {path: outputs/demo.json}
  prompts:
    system: S
    user: U {{ x }}
  prompt_fields: [x]
```

```bash
# Preflight schema checks (datasource schema present, plugin compatible, prompt_fields covered, sinks declared)
python -m elspeth.cli validate-schemas --settings settings.yaml --profile default

# Execute a single run
python -m elspeth.cli --settings settings.yaml --profile default --single-run --head 0
```

### B. Pytest Snippets

1) Validate schema compatibility without running the orchestrator:

```python
from elspeth.core.experiments.validation import validate_plugin_schemas
from elspeth.core.base.schema import DataFrameSchema


class DS(DataFrameSchema):  # datasource schema
    x: int


class Row:
    name = "row"
    def input_schema(self):
        class RequireX(DataFrameSchema):
            x: int
        return RequireX


def test_compatibility():
    validate_plugin_schemas(DS, row_plugins=[Row()])
```

2) CLI preflight with a temporary settings object and a bad sink:

```python
import argparse
import pandas as pd
import pytest
import elspeth.cli as cli
from elspeth.core.base.schema import DataFrameSchema
from elspeth.core.orchestrator import OrchestratorConfig
from elspeth.core.validation import ValidationReport


def test_cli_preflight_enforces_sinks(monkeypatch, tmp_path):
    class DS(DataFrameSchema):
        x: int

    df = pd.DataFrame({"x": [1]}); df.attrs["schema"] = DS

    class Source:
        def load(self): return df

    class LLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None): return {"content": user_prompt}

    class BadSink:
        def produces(self): return None  # wrong type to trigger failure
        def consumes(self): return []

    settings = argparse.Namespace(
        datasource=Source(), llm=LLM(), sinks=[BadSink()],
        orchestrator_config=OrchestratorConfig(
            llm_prompt={"system": "S", "user": "U {x}"}, prompt_fields=["x"],
            criteria=None, row_plugin_defs=None, aggregator_plugin_defs=None, validation_plugin_defs=None, prompt_defaults=None),
        suite_root=None, suite_defaults={}, rate_limiter=None, cost_tracker=None, prompt_packs={}, prompt_pack=None, config_path=None)

    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: settings)
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())
    parser = cli.build_parser()
    args = parser.parse_args(["validate-schemas", "--settings", "cfg.yaml", "--profile", "default"])
    with pytest.raises(SystemExit):
        cli.run(args)
```
