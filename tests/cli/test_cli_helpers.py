"""Tests for CLI helper functions."""

from pathlib import Path

import pytest

from elspeth.cli_helpers import instantiate_plugins_from_config
from elspeth.core.config import load_settings
from elspeth.plugins.base import BaseSink, BaseSource, BaseTransform


def test_instantiate_plugins_from_config(tmp_path: Path):
    """Verify helper instantiates all plugins from config."""
    config_yaml = """
datasource:
  plugin: csv
  options:
    path: test.csv
    schema:
      fields: dynamic
    on_validation_failure: discard

row_plugins:
  - plugin: passthrough
    options:
      schema:
        fields: dynamic

sinks:
  output:
    plugin: csv
    options:
      path: output.csv
      schema:
        fields: dynamic

output_sink: output
"""
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(config_yaml)

    config = load_settings(config_file)
    plugins = instantiate_plugins_from_config(config)

    # Verify structure
    assert "source" in plugins
    assert "transforms" in plugins
    assert "sinks" in plugins
    assert "aggregations" in plugins

    # Verify types
    assert isinstance(plugins["source"], BaseSource)
    assert len(plugins["transforms"]) == 1
    assert isinstance(plugins["transforms"][0], BaseTransform)
    assert "output" in plugins["sinks"]
    assert isinstance(plugins["sinks"]["output"], BaseSink)

    # CRITICAL: Verify schemas NOT None
    assert plugins["source"].output_schema is not None
    assert plugins["transforms"][0].input_schema is not None


def test_instantiate_plugins_raises_on_invalid_plugin():
    """Verify helper raises clear error for unknown plugin."""
    from pydantic import TypeAdapter

    from elspeth.cli_helpers import instantiate_plugins_from_config
    from elspeth.core.config import ElspethSettings

    config_dict = {
        "datasource": {"plugin": "nonexistent", "options": {}},
        "sinks": {"out": {"plugin": "csv", "options": {"path": "o.csv"}}},
        "output_sink": "out",
    }

    adapter = TypeAdapter(ElspethSettings)
    config = adapter.validate_python(config_dict)

    with pytest.raises(ValueError, match="nonexistent"):
        instantiate_plugins_from_config(config)
