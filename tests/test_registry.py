from pathlib import Path

import pandas as pd
import pytest

from elspeth.core.datasource_registry import datasource_registry
from elspeth.core.experiments import plugin_registry
from elspeth.core.llm_registry import llm_registry
from elspeth.core.sink_registry import sink_registry
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

    import elspeth.plugins.nodes.sources.blob as blob_module

    monkeypatch.setattr(blob_module, "load_blob_csv", fake_load_blob_csv)

    ds = datasource_registry.create(
        "azure_blob",
        {"config_path": cfg.as_posix(), "security_level": "OFFICIAL", "determinism_level": "guaranteed", "retain_local": False},
    )

    frame = ds.load()
    assert isinstance(frame, pd.DataFrame)
    assert list(frame.columns) == ["value"]


def test_registry_unknown_plugin_raises():
    import pytest

    with pytest.raises(ValueError):
        datasource_registry.create("missing", {})


def test_registry_creates_csv_blob_datasource(tmp_path):
    csv_path = tmp_path / "data.csv"
    pd.DataFrame({"value": [1, 2]}).to_csv(csv_path, index=False)

    ds = datasource_registry.create(
        "csv_blob", {"path": csv_path.as_posix(), "security_level": "OFFICIAL", "determinism_level": "guaranteed", "retain_local": False}
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

    from elspeth.core.registry.base import BasePluginFactory

    llm_registry._plugins["dummy"] = BasePluginFactory(lambda options, context: DummyLLM(**options))
    sink_registry._plugins["dummy"] = BasePluginFactory(lambda options, context: DummySink(**options))

    llm = llm_registry.create("dummy", {"name": "llm", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})
    sink = sink_registry.create("dummy", {"name": "sink", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})

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
        plugin_registry.validate_row_plugin_definition(
            {"name": "limited", "security_level": "OFFICIAL", "determinism_level": "guaranteed", "options": {}}
        )

    plugin_registry.validate_row_plugin_definition(
        {"name": "limited", "security_level": "OFFICIAL", "determinism_level": "guaranteed", "options": {"threshold": 0.5}}
    )


def test_create_row_plugin_conflicting_security_levels():
    with pytest.raises(ConfigurationError) as exc:
        plugin_registry.create_row_plugin(
            {
                "name": "score_extractor",
                "security_level": "OFFICIAL",
                "determinism_level": "guaranteed",
                "options": {"security_level": "SECRET", "determinism_level": "guaranteed"},
            }
        )
    assert "Conflicting security_level values" in str(exc.value)


def test_create_row_plugin_inherits_parent_context():
    from elspeth.core.plugin_context import PluginContext

    parent_context = PluginContext(plugin_name="suite", plugin_kind="suite", security_level="SECRET", determinism_level="none")
    plugin = plugin_registry.create_row_plugin(
        {
            "name": "score_extractor",
            "security_level": "SECRET",
            "determinism_level": "guaranteed",
            "options": {
                "key": "score",
                "parse_json_content": True,
                "allow_missing": False,
                "threshold_mode": "gte",
                "flag_field": "score_flags",
            },
        },
        parent_context=parent_context,
    )
    assert plugin.plugin_context.parent == parent_context
    assert plugin.plugin_context.security_level == "SECRET"
    assert plugin.security_level == "SECRET"


def test_normalize_early_stop_definitions_handles_various_forms():
    entries = [
        {"name": "custom", "options": {"limit": 5}, "security_level": "OFFICIAL", "determinism_level": "guaranteed"},
        {"plugin": "custom", "threshold": 2, "security_level": "OFFICIAL", "determinism_level": "guaranteed"},
        {"limit": 3, "security_level": "OFFICIAL", "determinism_level": "guaranteed"},
    ]
    normalized = plugin_registry.normalize_early_stop_definitions(entries)
    assert normalized == [
        {"name": "custom", "options": {"limit": 5, "security_level": "OFFICIAL", "determinism_level": "guaranteed"}},
        {"name": "custom", "options": {"threshold": 2, "security_level": "OFFICIAL", "determinism_level": "guaranteed"}},
        {"name": "threshold", "options": {"limit": 3, "security_level": "OFFICIAL", "determinism_level": "guaranteed"}},
    ]


def test_normalize_early_stop_definitions_rejects_invalid_types():
    with pytest.raises(ConfigurationError):
        plugin_registry.normalize_early_stop_definitions("invalid")
    with pytest.raises(ConfigurationError):
        plugin_registry.normalize_early_stop_definitions([1, 2])


def test_registry_validate_sink_schema_errors():
    with pytest.raises(ConfigurationError):
        sink_registry.validate("csv", {"path": None, "security_level": "OFFICIAL", "determinism_level": "guaranteed"})
    with pytest.raises(ConfigurationError):
        sink_registry.validate("file_copy", {"destination": None, "security_level": "OFFICIAL", "determinism_level": "guaranteed"})


def test_registry_sink_schema_success(tmp_path):
    dest = tmp_path / "out.txt"
    sink_registry.validate("csv", {"path": dest.as_posix(), "security_level": "OFFICIAL", "determinism_level": "guaranteed"})
    sink_registry.validate("file_copy", {"destination": dest.as_posix(), "security_level": "OFFICIAL", "determinism_level": "guaranteed"})
    sink = sink_registry.create(
        "file_copy", {"destination": dest.as_posix(), "security_level": "OFFICIAL", "determinism_level": "guaranteed"}
    )
    from elspeth.core.protocols import Artifact

    src = tmp_path / "src.txt"
    src.write_text("hello", encoding="utf-8")
    sink.prepare_artifacts({"input": [Artifact(id="a", type="text/plain", path=str(src))]})
    sink.write({}, metadata={})
    artifacts = sink.collect_artifacts()
    assert Path(artifacts["file"].path).read_text(encoding="utf-8") == "hello"
