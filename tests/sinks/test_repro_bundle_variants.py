from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pandas as pd

from elspeth.plugins.nodes.sinks.reproducibility_bundle import ReproducibilityBundleSink


def _results(n: int = 3) -> dict:
    # Include a few non-serializable-like objects to exercise _json_serializer
    class ObjA:
        def to_dict(self):  # noqa: D401
            return {"a": 1}

    class ObjB:
        def __init__(self):
            self.x = 2
            self._hide = "secret"

    class ObjC:
        def model_dump(self):  # noqa: D401
            return {"m": 3}

    return {
        "results": [
            {"row": {"idx": i}, "response": {"content": f"ok-{i}"}, "meta": ObjA(), "obj": ObjB(), "m": ObjC()}
            for i in range(n)
        ],
        "aggregates": {"score": {"mean": 0.9}},
    }


def test_repro_bundle_full_paths_and_csv_and_config_and_prompts(tmp_path: Path) -> None:
    # Source data DataFrame to be saved when include_source_data=True (no retained path)
    df = pd.DataFrame({"x": [1, 2]})
    # Minimal config and prompts metadata
    config = {"a": 1, "b": {"c": 2}}
    plugins = {"sinks": [{"name": "csv_file"}]}

    sink = ReproducibilityBundleSink(
        base_path=tmp_path,
        bundle_name="bundle",
        timestamped=False,
        include_results_json=True,
        include_results_csv=True,
        include_source_data=True,
        include_config=True,
        include_prompts=True,
        include_plugins=True,
        include_framework_code=False,
        key="secret",
        compression="none",
    )

    sink.prepare_artifacts({})  # no-op path
    sink.write(
        _results(),
        metadata={
            "experiment": "exp",
            "source_data": df,
            "datasource_config": {"path": "x.csv"},
            "config": config,
            "prompt_templates": {"system": "s", "user": "u"},
            "plugins": plugins,
        },
    )

    archive = tmp_path / "bundle.tar"
    assert archive.exists()
    # Open the archive and assert key files exist
    with tarfile.open(archive, "r") as tf:
        names = set(tf.getnames())
        # expect results.json, results.csv, source_data.csv, prompts.json, MANIFEST.json, SIGNATURE.json at top-level dir
        # names include top-level folder; keep suffix checks
        assert any(name.endswith("results.json") for name in names)
        assert any(name.endswith("results.csv") for name in names)
        assert any(name.endswith("source_data.csv") for name in names)
        assert any(name.endswith("prompts.json") for name in names)
        assert any(name.endswith("MANIFEST.json") for name in names)
        assert any(name.endswith("SIGNATURE.json") for name in names)

    # collect_artifacts should expose the newly created archive once
    artifact_map = sink.collect_artifacts()
    assert "reproducibility_bundle" in artifact_map
    # Second call returns empty (consumed)
    assert sink.collect_artifacts() == {}


def test_repro_bundle_framework_and_artifacts_payload(tmp_path: Path) -> None:
    # Prepare artifacts (one payload JSON, one temp file)
    from elspeth.core.base.protocols import Artifact

    extra = tmp_path / "payload.bin"
    extra.write_bytes(b"xyz")

    sink = ReproducibilityBundleSink(
        base_path=tmp_path,
        bundle_name="bundle2",
        timestamped=False,
        include_results_json=True,
        include_results_csv=False,
        include_source_data=False,
        include_config=False,
        include_prompts=False,
        include_plugins=False,
        include_framework_code=True,
        key="secret",
        compression="gz",
    )

    sink.prepare_artifacts({
        "bundle": [
            Artifact(id="a1", type="blob", payload={"k": 1}),
            Artifact(id="a2", type="blob", path=str(extra)),
        ]
    })

    sink.write({"results": []}, metadata={"experiment": "e"})
    tar_path = tmp_path / "bundle2.tar.gz"
    assert tar_path.exists()

