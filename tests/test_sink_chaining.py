from pathlib import Path
import json

import pandas as pd

from elspeth.core.experiments.runner import ExperimentRunner
from elspeth.core.artifact_pipeline import ArtifactPipeline, SinkBinding
from elspeth.plugins.outputs.csv_file import CsvResultSink
from elspeth.plugins.outputs.file_copy import FileCopySink
from elspeth.plugins.outputs.zip_bundle import ZipResultSink
from elspeth.core.artifact_pipeline import ArtifactPipeline, SinkBinding
import zipfile


def configure_sink(
    sink,
    plugin: str,
    alias: str | None = None,
    consumes=None,
    produces=None,
    security_level: str | None = None,
):
    setattr(sink, "_elspeth_plugin_name", plugin)
    setattr(sink, "_elspeth_sink_name", alias or plugin)
    setattr(
        sink,
        "_elspeth_artifact_config",
        {
            "consumes": consumes or [],
            "produces": produces or [],
        },
    )
    if security_level:
        setattr(sink, "_elspeth_security_level", security_level)


def test_csv_to_file_copy_pipeline(tmp_path):
    csv_sink = CsvResultSink(path=tmp_path / "results.csv")
    configure_sink(
        csv_sink,
        "csv",
        alias="csv",
        produces=[{"name": "csv", "type": "file/csv", "persist": True, "security_level": "secret"}],
        security_level="secret",
    )

    copy_sink = FileCopySink(destination=str(tmp_path / "copied.csv"))
    configure_sink(
        copy_sink,
        "file_copy",
        alias="copy",
        consumes=["@csv"],
        produces=[{"name": "file", "type": "file/csv", "alias": "copied", "persist": True}],
        security_level="secret",
    )

    bindings = [
        SinkBinding("copy", "file_copy", copy_sink, copy_sink._elspeth_artifact_config, 1, security_level="secret"),
        SinkBinding("csv", "csv", csv_sink, csv_sink._elspeth_artifact_config, 0, security_level="secret"),
    ]

    pipeline = ArtifactPipeline(bindings)
    payload = {
        "results": [
            {"row": {"APPID": "1"}, "response": {"content": "ok"}},
        ]
    }
    store = pipeline.execute(payload, metadata={"security_level": "secret"})

    assert (tmp_path / "results.csv").exists()
    assert (tmp_path / "copied.csv").exists()
    copied = store.get_by_alias("copied")
    assert copied is not None and copied.security_level == "secret"


def test_runner_chaining(tmp_path):
    class DummyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            return {"content": user_prompt}

    csv_sink = CsvResultSink(path=tmp_path / "run.csv")
    configure_sink(csv_sink, "csv", alias="csv", security_level="secret")

    copy_sink = FileCopySink(destination=str(tmp_path / "copy.csv"))
    configure_sink(
        copy_sink,
        "file_copy",
        alias="copy",
        consumes=["@csv"],
        produces=[{"name": "file", "type": "file/csv", "alias": "copy"}],
        security_level="secret",
    )

    runner = ExperimentRunner(
        llm_client=DummyLLM(),
        sinks=[csv_sink, copy_sink],
        prompt_system="sys",
        prompt_fields=["APPID"],
        prompt_template="row {APPID}",
    )

    df = pd.DataFrame({"APPID": ["1"]})
    runner.run(df)

    assert (tmp_path / "run.csv").exists()
    assert (tmp_path / "copy.csv").exists()


def test_zip_consumes_all_files(tmp_path):
    csv_one = CsvResultSink(path=tmp_path / "one.csv")
    configure_sink(csv_one, "csv", alias="csv_one", security_level="secret")

    csv_two = CsvResultSink(path=tmp_path / "two.csv")
    configure_sink(csv_two, "csv", alias="csv_two", security_level="secret")

    zip_sink = ZipResultSink(
        base_path=tmp_path,
        bundle_name="bundle",
        include_manifest=True,
        include_results=False,
    )
    configure_sink(
        zip_sink,
        "zip_bundle",
        alias="zip",
        consumes=[{"token": "file/csv", "mode": "all"}],
        security_level="secret",
    )

    bindings = [
        SinkBinding("csv1", "csv", csv_one, csv_one._elspeth_artifact_config, 0, security_level="secret"),
        SinkBinding("csv2", "csv", csv_two, csv_two._elspeth_artifact_config, 1, security_level="secret"),
        SinkBinding("zip", "zip_bundle", zip_sink, zip_sink._elspeth_artifact_config, 2, security_level="secret"),
    ]

    payload = {
        "results": [
            {"row": {"APPID": "1"}, "response": {"content": "ok"}},
        ]
    }

    pipeline = ArtifactPipeline(bindings)
    pipeline.execute(payload, metadata={"security_level": "secret"})

    archives = list(tmp_path.glob("bundle_*.zip"))
    assert archives
    with zipfile.ZipFile(archives[0]) as zf:
        names = set(zf.namelist())
        assert "one.csv" in names
        assert "two.csv" in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["metadata"]["security_level"] == "secret"
