"""Performance benchmarks for schema validation pipeline.

Migrated from tests/performance/test_baseline_schema_validation.py.
Measures plugin instantiation, graph construction, and end-to-end validation time.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from elspeth.cli_helpers import instantiate_plugins_from_config
from elspeth.core.config import load_settings
from elspeth.core.dag import ExecutionGraph
from tests_v2.performance.conftest import benchmark_timer


@pytest.mark.performance
def test_plugin_instantiation_performance() -> None:
    """Measure plugin instantiation time.

    Baseline: Instantiation should be < 200ms for a simple pipeline with
    3 passthrough transforms.
    """
    config_yaml = """
source:
  plugin: csv
  options:
    path: test.csv
    schema:
      mode: observed
    on_validation_failure: discard

transforms:
  - plugin: passthrough
    options:
      schema:
        mode: observed
  - plugin: passthrough
    options:
      schema:
        mode: observed
  - plugin: passthrough
    options:
      schema:
        mode: observed

sinks:
  output:
    plugin: json
    options:
      path: output.json
      schema:
        mode: observed
      format: jsonl

default_sink: output
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_yaml)
        config_file = Path(f.name)

    try:
        config = load_settings(config_file)

        with benchmark_timer() as timing:
            _ = instantiate_plugins_from_config(config)

        assert timing.wall_seconds < 0.200, (
            f"Plugin instantiation took {timing.wall_seconds * 1000:.2f}ms (expected < 200ms)"
        )
    finally:
        config_file.unlink()


@pytest.mark.performance
def test_graph_construction_performance() -> None:
    """Measure graph construction and validation time.

    Baseline: Graph construction + validation should be < 100ms.
    """
    config_yaml = """
source:
  plugin: csv
  options:
    path: test.csv
    schema:
      mode: observed
    on_validation_failure: discard

transforms:
  - plugin: passthrough
    options:
      schema:
        mode: observed

sinks:
  output:
    plugin: json
    options:
      path: output.json
      schema:
        mode: observed
      format: jsonl

default_sink: output
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_yaml)
        config_file = Path(f.name)

    try:
        config = load_settings(config_file)
        plugins = instantiate_plugins_from_config(config)

        with benchmark_timer() as timing:
            graph = ExecutionGraph.from_plugin_instances(
                source=plugins["source"],
                transforms=plugins["transforms"],
                sinks=plugins["sinks"],
                aggregations=plugins["aggregations"],
                gates=list(config.gates),
                default_sink=config.default_sink,
            )
            graph.validate()

        assert timing.wall_seconds < 0.100, (
            f"Graph construction took {timing.wall_seconds * 1000:.2f}ms (expected < 100ms)"
        )
    finally:
        config_file.unlink()


@pytest.mark.performance
def test_end_to_end_validation_performance() -> None:
    """Measure end-to-end validation performance.

    Baseline: Full config load + plugin instantiation + graph build + validate
    should be < 200ms.
    """
    config_yaml = """
source:
  plugin: csv
  options:
    path: test.csv
    schema:
      mode: observed
    on_validation_failure: discard

transforms:
  - plugin: passthrough
    options:
      schema:
        mode: observed
  - plugin: passthrough
    options:
      schema:
        mode: observed

sinks:
  output:
    plugin: json
    options:
      path: output.json
      schema:
        mode: observed
      format: jsonl

default_sink: output
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_yaml)
        config_file = Path(f.name)

    try:
        with benchmark_timer() as timing:
            config = load_settings(config_file)
            plugins = instantiate_plugins_from_config(config)
            graph = ExecutionGraph.from_plugin_instances(
                source=plugins["source"],
                transforms=plugins["transforms"],
                sinks=plugins["sinks"],
                aggregations=plugins["aggregations"],
                gates=list(config.gates),
                default_sink=config.default_sink,
            )
            graph.validate()

        assert timing.wall_seconds < 0.200, (
            f"End-to-end validation took {timing.wall_seconds * 1000:.2f}ms (expected < 200ms)"
        )
    finally:
        config_file.unlink()
