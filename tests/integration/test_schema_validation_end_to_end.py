"""End-to-end integration tests for schema validation."""

import tempfile
from pathlib import Path

from typer.testing import CliRunner

from elspeth.cli import app


def test_compatible_pipeline_passes_validation():
    """Verify compatible pipeline passes validation."""
    runner = CliRunner()

    config_yaml = """
datasource:
  plugin: csv
  options:
    path: test_input.csv
    schema:
      mode: strict
      fields:
        - "value: float"
    on_validation_failure: discard

row_plugins:
  - plugin: passthrough
    options:
      schema:
        mode: strict
        fields:
          - "value: float"

sinks:
  output:
    plugin: csv
    options:
      path: test_output.csv
      schema:
        mode: strict
        fields:
          - "value: float"

output_sink: output
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_yaml)
        config_file = Path(f.name)

    try:
        result = runner.invoke(app, ["validate", "--settings", str(config_file)])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    finally:
        config_file.unlink()


def test_transform_chain_incompatibility_detected():
    """Verify schema validation detects incompatible transform chain."""
    runner = CliRunner()

    config_yaml = """
datasource:
  plugin: csv
  options:
    path: test_input.csv
    schema:
      mode: strict
      fields:
        - "field_a: str"
    on_validation_failure: discard

row_plugins:
  - plugin: passthrough
    options:
      schema:
        mode: strict
        fields:
          - "field_a: str"
  - plugin: passthrough
    options:
      schema:
        mode: strict
        fields:
          - "field_b: int"  # INCOMPATIBLE: requires field_b, gets field_a

sinks:
  output:
    plugin: csv
    options:
      path: test_output.csv
      schema: {fields: dynamic}

output_sink: output
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_yaml)
        config_file = Path(f.name)

    try:
        result = runner.invoke(app, ["validate", "--settings", str(config_file)])
        assert result.exit_code != 0
        assert "field_b" in result.output.lower()

    finally:
        config_file.unlink()


def test_aggregation_output_incompatibility_detected():
    """Verify validation detects aggregation output incompatible with sink."""
    runner = CliRunner()

    config_yaml = """
datasource:
  plugin: csv
  options:
    path: test_input.csv
    schema:
      mode: strict
      fields:
        - "value: float"
    on_validation_failure: discard

aggregations:
  - name: stats
    plugin: batch_stats
    trigger:
      count: 10
    options:
      schema:
        mode: strict
        fields:
          - "value: float"
      value_field: value

sinks:
  output:
    plugin: csv
    options:
      path: test_output.csv
      schema:
        mode: strict
        fields:
          - "total_records: int"  # INCOMPATIBLE: agg outputs count/sum/mean

output_sink: output
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_yaml)
        config_file = Path(f.name)

    try:
        result = runner.invoke(app, ["validate", "--settings", str(config_file)])
        assert result.exit_code != 0
        assert "total_records" in result.output.lower() or "schema" in result.output.lower()

    finally:
        config_file.unlink()


def test_dynamic_schemas_skip_validation():
    """Verify dynamic schemas (None) skip validation without error."""
    runner = CliRunner()

    config_yaml = """
datasource:
  plugin: csv
  options:
    path: test_input.csv
    schema: {fields: dynamic}  # Dynamic schema
    on_validation_failure: discard

row_plugins:
  - plugin: passthrough
    options:
      schema: {fields: dynamic}

sinks:
  output:
    plugin: csv
    options:
      path: test_output.csv
      schema: {fields: dynamic}

output_sink: output
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_yaml)
        config_file = Path(f.name)

    try:
        result = runner.invoke(app, ["validate", "--settings", str(config_file)])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    finally:
        config_file.unlink()


def test_aggregation_incoming_edge_uses_input_schema():
    """Test that incoming edge to aggregation validates against input_schema."""
    runner = CliRunner()

    config_yaml = """
datasource:
  plugin: csv
  options:
    path: test.csv
    schema:
      mode: strict
      fields:
        - "wrong_field: str"  # Aggregation expects 'value', not 'wrong_field'
    on_validation_failure: discard

aggregations:
  - name: stats
    plugin: batch_stats
    trigger:
      count: 10
    options:
      schema:
        mode: strict
        fields:
          - "value: float"  # Requires 'value' field
      value_field: value

sinks:
  output:
    plugin: csv
    options:
      path: out.csv
      schema: {fields: dynamic}

output_sink: output
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_yaml)
        config_file = Path(f.name)

    try:
        result = runner.invoke(app, ["validate", "--settings", str(config_file)])
        assert result.exit_code != 0
        # Should complain about missing 'value' field
        assert "value" in result.output.lower()

    finally:
        config_file.unlink()


def test_aggregation_outgoing_edge_uses_output_schema():
    """Test that outgoing edge from aggregation validates against output_schema."""
    runner = CliRunner()

    config_yaml = """
datasource:
  plugin: csv
  options:
    path: test.csv
    schema:
      mode: strict
      fields:
        - "value: float"
    on_validation_failure: discard

aggregations:
  - name: stats
    plugin: batch_stats
    trigger:
      count: 10
    options:
      schema:
        mode: strict
        fields:
          - "value: float"
      value_field: value
    # Outputs: count, sum, mean, etc.

sinks:
  output:
    plugin: csv
    options:
      path: out.csv
      schema:
        mode: strict
        fields:
          - "nonexistent_field: str"  # INCOMPATIBLE with aggregation output

output_sink: output
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_yaml)
        config_file = Path(f.name)

    try:
        result = runner.invoke(app, ["validate", "--settings", str(config_file)])
        assert result.exit_code != 0
        # Should complain about missing field from aggregation output
        assert "nonexistent_field" in result.output.lower() or "schema" in result.output.lower()

    finally:
        config_file.unlink()
