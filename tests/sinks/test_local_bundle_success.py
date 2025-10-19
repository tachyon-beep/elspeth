from __future__ import annotations

import json
from pathlib import Path

from elspeth.plugins.nodes.sinks.local_bundle import LocalBundleSink


def test_local_bundle_writes_manifest_results_and_csv(tmp_path: Path):
    sink = LocalBundleSink(
        base_path=tmp_path,
        bundle_name="bundle",
        timestamped=False,
        write_json=True,
        write_csv=True,
        allowed_base_path=str(tmp_path),
    )

    results = {"results": [{"row": {"a": 1, "b": 2}}]}
    sink.write(results, metadata={"experiment": "exp"})

    target = tmp_path / "bundle"
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest.get("columns", [])) == {"a", "b"}
    assert (target / "results.json").exists()
    assert (target / "results.csv").exists()

