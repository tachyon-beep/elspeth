from pathlib import Path

import pandas as pd
import pytest

from elspeth.core.experiments import plugin_registry
from elspeth.core.registry import registry
from elspeth.core.validation import ConfigurationError


def test_registry_creates_blob_datasource(tmp_path, monkeypatch):
    cfg = tmp_path / "blob.yaml"
    cfg.write_text(
        """
        default:
          connection_name: workspace
          azureml_datastore_uri: azureml://example
          account_name: acct
          container_name: container
          blob_path: blob.csv
          sas_token: sig=123
        """,
        encoding="utf-8",
    )

    def fake_load_blob_csv(config_path, profile="default", pandas_kwargs=None):
        assert config_path == cfg.as_posix()
        assert profile == "default"
        return pd.DataFrame({"value": [1]})

    import elspeth.plugins.datasources.blob as blob_module

    monkeypatch.setattr(blob_module, "load_blob_csv", fake_load_blob_csv)

    ds = registry.create_datasource(
        "azure_blob", {"config_path": cfg.as_posix(), "security_level": "official"}
    )

    frame = ds.load()
    assert isinstance(frame, pd.DataFrame)
    assert list(frame.columns) == ["value"]


def test_registry_unknown_plugin_raises():
    import pytest

    with pytest.raises(ValueError):
        registry.create_datasource("missing", {})


def test_registry_creates_csv_blob_datasource(tmp_path):
    csv_path = tmp_path / "data.csv"
    pd.DataFrame({"value": [1, 2]}).to_csv(csv_path, index=False)

    ds = registry.create_datasource(
        "csv_blob", {"path": csv_path.as_posix(), "security_level": "official"}
    )
    frame = ds.load()

    assert list(frame["value"]) == [1, 2]


def test_registry_constructs_llm_and_sink(monkeypatch):
    class DummyLLM:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class DummySink:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    import elspeth.core.registry as registry_module

    registry_module.registry._llms["dummy"] = registry_module.PluginFactory(lambda options, context: DummyLLM(**options))
    registry_module.registry._sinks["dummy"] = registry_module.PluginFactory(lambda options, context: DummySink(**options))

    llm = registry.create_llm("dummy", {"name": "llm", "security_level": "official"})
    sink = registry.create_sink("dummy", {"name": "sink", "security_level": "official"})

    assert isinstance(llm, DummyLLM)
    assert isinstance(sink, DummySink)


def test_create_row_plugin_requires_known_name():
    with pytest.raises(ValueError, match="Unknown row experiment plugin"):
        plugin_registry.create_row_plugin({"name": "missing"})


def test_create_row_plugin_validates_schema():
    def build_plugin(options, context):
        class _Plugin:
            name = "limited"

            def process_row(self, row, responses):
                return {}

        return _Plugin()

    plugin_registry.register_row_plugin(
        "limited",
        build_plugin,
        schema={
            "type": "object",
            "properties": {"threshold": {"type": "number"}},
            "required": ["threshold"],
        },
    )

    with pytest.raises(ConfigurationError):
        plugin_registry.validate_row_plugin_definition({"name": "limited", "security_level": "official", "options": {}})

    plugin_registry.validate_row_plugin_definition({"name": "limited", "security_level": "official", "options": {"threshold": 0.5}})


def test_normalize_early_stop_definitions_handles_various_forms():
    entries = [
        {"name": "custom", "options": {"limit": 5}, "security_level": "official"},
        {"plugin": "custom", "threshold": 2, "security_level": "official"},
        {"limit": 3, "security_level": "official"},
    ]
    normalized = plugin_registry.normalize_early_stop_definitions(entries)
    assert normalized == [
        {"name": "custom", "options": {"limit": 5, "security_level": "official"}},
        {"name": "custom", "options": {"threshold": 2, "security_level": "official"}},
        {"name": "threshold", "options": {"limit": 3, "security_level": "official"}},
    ]


def test_normalize_early_stop_definitions_rejects_invalid_types():
    with pytest.raises(ConfigurationError):
        plugin_registry.normalize_early_stop_definitions("invalid")
    with pytest.raises(ConfigurationError):
        plugin_registry.normalize_early_stop_definitions([1, 2])


def test_registry_validate_sink_schema_errors():
    with pytest.raises(ConfigurationError):
        registry.validate_sink("csv", {"path": None, "security_level": "official"})
    with pytest.raises(ConfigurationError):
        registry.validate_sink("file_copy", {"destination": None, "security_level": "official"})


def test_registry_sink_schema_success(tmp_path):
    dest = tmp_path / "out.txt"
    registry.validate_sink("csv", {"path": dest.as_posix(), "security_level": "official"})
    registry.validate_sink(
        "file_copy", {"destination": dest.as_posix(), "security_level": "official"}
    )
    sink = registry.create_sink(
        "file_copy", {"destination": dest.as_posix(), "security_level": "official"}
    )
    from elspeth.core.interfaces import Artifact

    src = tmp_path / "src.txt"
    src.write_text("hello", encoding="utf-8")
    sink.prepare_artifacts({"input": [Artifact(id="a", type="text/plain", path=str(src))]})
    sink.write({}, metadata={})
    artifacts = sink.collect_artifacts()
    assert Path(artifacts["file"].path).read_text(encoding="utf-8") == "hello"
