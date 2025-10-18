from __future__ import annotations

import tarfile
from pathlib import Path

from elspeth.plugins.nodes.sinks.reproducibility_bundle import ReproducibilityBundleSink


def _results(n: int = 2) -> dict:
    return {
        "results": [
            {"row": {"a": i}, "response": {"content": f"ok-{i}"}, "request": {"system_prompt": "s", "user_prompt": "u", "metadata": {}}}
            for i in range(n)
        ]
    }


def test_repro_bundle_minimal_success(tmp_path: Path) -> None:
    sink = ReproducibilityBundleSink(
        base_path=tmp_path,
        bundle_name="bundle",
        timestamped=False,
        include_results_json=True,
        include_results_csv=False,
        include_source_data=False,
        include_config=False,
        include_prompts=True,
        include_plugins=False,
        include_framework_code=False,
        key="secret",
        compression="gz",
    )

    sink.write(_results(), metadata={"experiment": "e"})
    archive = tmp_path / "bundle.tar.gz"
    assert archive.exists()
    # Check manifest and signature entries exist in the tarball
    with tarfile.open(archive, "r:gz") as tf:
        names = tf.getnames()
        # Top-level directory is bundle/
        members = {name.split("/", 1)[-1] for name in names if name.endswith(".json")}
        assert {"MANIFEST.json", "SIGNATURE.json"}.issubset(members)


def test_repro_bundle_on_error_skip(tmp_path: Path, monkeypatch) -> None:
    sink = ReproducibilityBundleSink(
        base_path=tmp_path,
        bundle_name="fail",
        timestamped=False,
        include_results_json=True,
        include_results_csv=False,
        include_source_data=False,
        include_config=False,
        include_prompts=False,
        include_plugins=False,
        include_framework_code=False,
        key="secret",
        on_error="skip",
    )

    def _boom(*_args, **_kwargs):  # noqa: D401
        raise RuntimeError("fail")

    monkeypatch.setattr(sink, "_create_archive", _boom)
    sink.write(_results(), metadata={"experiment": "e"})
    assert not (tmp_path / "fail.tar.gz").exists()

