from pathlib import Path

import pandas as pd
import pytest

from elspeth.core.experiments import plugin_registry
from elspeth.core.registries.datasource import datasource_registry
from elspeth.core.registries.llm import llm_registry
from elspeth.core.registries.sink import sink_registry
from elspeth.core.validation import ConfigurationError


def test_registry_creates_blob_datasource(tmp_path, monkeypatch):
    from elspeth.core.base.plugin_context import PluginContext

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

    parent_context = PluginContext(
        plugin_name="test", plugin_kind="test", security_level="OFFICIAL", determinism_level="guaranteed"
    )
    ds = datasource_registry.create(
        "azure_blob",
        {"config_path": cfg.as_posix(), "determinism_level": "guaranteed", "retain_local": False},
        parent_context=parent_context,
    )

    frame = ds.load()
    assert isinstance(frame, pd.DataFrame)
    assert list(frame.columns) == ["value"]


def test_registry_unknown_plugin_raises():
    with pytest.raises(ValueError):
        datasource_registry.create("missing", {})


def test_registry_creates_csv_blob_datasource(tmp_path):
    from elspeth.core.base.plugin_context import PluginContext

    csv_path = tmp_path / "data.csv"
    pd.DataFrame({"value": [1, 2]}).to_csv(csv_path, index=False)

    parent_context = PluginContext(
        plugin_name="test", plugin_kind="test", security_level="OFFICIAL", determinism_level="guaranteed"
    )
    ds = datasource_registry.create(
        "csv_blob", {"path": csv_path.as_posix(), "determinism_level": "guaranteed", "retain_local": False},
        parent_context=parent_context,
    )
    frame = ds.load()

    assert list(frame["value"]) == [1, 2]


def test_registry_constructs_llm_and_sink(monkeypatch):
    from elspeth.core.base.plugin_context import PluginContext

    class DummyLLM:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class DummySink:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    parent_context = PluginContext(
        plugin_name="test", plugin_kind="test", security_level="OFFICIAL", determinism_level="guaranteed"
    )
    with (
        llm_registry.temporary_override("dummy", lambda options, context: DummyLLM(**options)),
        sink_registry.temporary_override("dummy", lambda options, context: DummySink(**options)),
    ):
        llm = llm_registry.create("dummy", {"name": "llm", "determinism_level": "guaranteed"}, parent_context=parent_context)
        sink = sink_registry.create("dummy", {"name": "sink", "determinism_level": "guaranteed"}, parent_context=parent_context)

    assert isinstance(llm, DummyLLM)
    assert isinstance(sink, DummySink)


def test_create_row_plugin_requires_known_name():
    with pytest.raises(ValueError, match="Unknown row experiment plugin"):
        plugin_registry.create_row_plugin({"name": "missing"})


def test_create_row_plugin_validates_schema():
    def build_plugin(_options, _context):
        class _Plugin:
            name = "limited"

            def process_row(self, _row, _responses):
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


def test_create_row_plugin_inherits_parent_context():
    from elspeth.core.base.plugin_context import PluginContext

    parent_context = PluginContext(plugin_name="suite", plugin_kind="suite", security_level="SECRET", determinism_level="none")
    plugin = plugin_registry.create_row_plugin(
        {
            "name": "score_extractor",
            # ADR-002-B Phase 2: security_level in config is IGNORED (plugin-author-owned)
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
    # ADR-002-B Phase 2: plugin.security_level is immutably UNOFFICIAL (hard-coded in plugin __init__)
    assert plugin.security_level == "UNOFFICIAL"


def test_normalize_early_stop_definitions_handles_various_forms():
    entries = [
        {"name": "custom", "options": {"limit": 5}, "determinism_level": "guaranteed"},
        {"plugin": "custom", "threshold": 2, "determinism_level": "guaranteed"},
        {"limit": 3, "determinism_level": "guaranteed"},
    ]
    normalized = plugin_registry.normalize_early_stop_definitions(entries)
    assert normalized == [
        {"name": "custom", "options": {"limit": 5, "determinism_level": "guaranteed"}},
        {"name": "custom", "options": {"threshold": 2, "determinism_level": "guaranteed"}},
        {"name": "threshold", "options": {"limit": 3, "determinism_level": "guaranteed"}},
    ]


def test_normalize_early_stop_definitions_rejects_invalid_types():
    with pytest.raises(ConfigurationError):
        plugin_registry.normalize_early_stop_definitions("invalid")
    with pytest.raises(ConfigurationError):
        plugin_registry.normalize_early_stop_definitions([1, 2])


def test_registry_validate_sink_schema_errors():
    with pytest.raises(ConfigurationError):
        sink_registry.validate("csv", {"path": None})
    with pytest.raises(ConfigurationError):
        sink_registry.validate("file_copy", {"destination": None})


def test_registry_sink_schema_success(tmp_path):
    from elspeth.core.base.plugin_context import PluginContext

    dest = tmp_path / "out.txt"
    sink_registry.validate("csv", {"path": dest.as_posix()})
    sink_registry.validate("file_copy", {"destination": dest.as_posix()})

    parent_context = PluginContext(
        plugin_name="test", plugin_kind="test", security_level="OFFICIAL", determinism_level="guaranteed"
    )
    sink = sink_registry.create(
        "file_copy", {"destination": dest.as_posix()},
        parent_context=parent_context,
    )
    from elspeth.core.base.protocols import Artifact

    src = tmp_path / "src.txt"
    src.write_text("hello", encoding="utf-8")
    sink.prepare_artifacts({"input": [Artifact(id="a", type="text/plain", path=str(src))]})
    sink.write({}, metadata={})
    artifacts = sink.collect_artifacts()
    assert Path(artifacts["file"].path).read_text(encoding="utf-8") == "hello"
