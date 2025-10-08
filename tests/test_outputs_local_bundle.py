import json
from pathlib import Path

from dmp.plugins.outputs.local_bundle import LocalBundleSink


def test_local_bundle_sink_creates_bundle(tmp_path):
    base = tmp_path / "archives"
    sink = LocalBundleSink(base_path=base, bundle_name="exp1", timestamped=False, write_json=True, write_csv=True)

    sink.write(
        {
            "results": [
                {
                    "row": {"APPID": "1", "field": "value"},
                    "response": {"content": "ok"},
                }
            ],
            "aggregates": {"score": {"mean": 0.5}},
        },
        metadata={"experiment": "exp1"},
    )

    bundle_dir = base / "exp1"
    assert bundle_dir.exists()

    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    results_json = json.loads((bundle_dir / "results.json").read_text(encoding="utf-8"))
    csv_path = bundle_dir / "results.csv"

    assert manifest["rows"] == 1
    assert manifest["metadata"]["experiment"] == "exp1"
    assert "field" in manifest["columns"]
    assert results_json["results"][0]["row"]["APPID"] == "1"
    assert csv_path.exists()
