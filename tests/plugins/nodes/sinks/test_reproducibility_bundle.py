from __future__ import annotations

from pathlib import Path

from elspeth.plugins.nodes.sinks.reproducibility_bundle import ReproducibilityBundleSink


def test_reproducibility_bundle_minimal_write(tmp_path: Path) -> None:
    # Minimal configuration: JSON only, signed, deterministic name
    sink = ReproducibilityBundleSink(
        base_path=str(tmp_path),
        bundle_name="bundle",
        timestamped=False,
        include_results_json=True,
        include_results_csv=False,
        include_source_data=True,  # exercise _is_dataframe/_get_retained_path fallbacks
        include_config=False,
        include_prompts=False,
        include_plugins=False,
        include_framework_code=False,
        key="test-key",
    )

    results = {"results": [], "failures": []}
    metadata = {"name": "exp1", "source_data": object(), "datasource_config": None}

    sink.write(results, metadata=metadata)

    archive = tmp_path / "bundle.tar.gz"
    assert archive.exists(), "expected reproducibility archive to be created"

    # Artifact collection should expose the created archive (and clear last path)
    artifacts = sink.collect_artifacts()
    assert "reproducibility_bundle" in artifacts
    assert artifacts["reproducibility_bundle"].path.endswith("bundle.tar.gz")
