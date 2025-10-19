from __future__ import annotations

from pathlib import Path

from elspeth.plugins.nodes.sinks.reproducibility_bundle import ReproducibilityBundleSink


def test_plugins_copy_handles_unknown_entries(tmp_path: Path, caplog) -> None:
    sink = ReproducibilityBundleSink(
        base_path=tmp_path,
        bundle_name="plug",
        timestamped=False,
        include_results_json=True,
        include_results_csv=False,
        include_source_data=False,
        include_config=False,
        include_prompts=False,
        include_plugins=True,
        include_framework_code=False,
        key="k",
        compression="gz",
    )

    # Mix of unsupported entries to exercise logging and filtering
    plugins = {
        "sinks": [{"name": "nonexistent_plugin"}, {"plugin": ""}, 123, None],
        "transforms": {"name": "also_missing"},
    }

    with caplog.at_level("WARNING"):
        sink.write({"results": []}, metadata={"experiment": "e", "plugins": plugins})

    # Expect archive created and warnings present for skipping plugin entries
    assert (tmp_path / "plug.tar.gz").exists()
    assert any("Skipping plugin entry" in rec.message for rec in caplog.records)
    assert any("No plugin source files found" in rec.message for rec in caplog.records)

