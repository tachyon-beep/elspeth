from __future__ import annotations

from pathlib import Path

import pytest

from elspeth.plugins.nodes.sinks.local_bundle import LocalBundleSink


def _results(n: int = 2) -> dict:
    return {
        "results": [
            {"row": {"a": i}, "response": {"content": "ok"}} for i in range(n)
        ]
    }


def test_local_bundle_writes_under_allowed_base(tmp_path: Path) -> None:
    base = tmp_path / "outputs"
    base.mkdir()
    sink = LocalBundleSink(base_path=base, bundle_name="bundle", timestamped=False, write_json=True, write_csv=True)
    sink._allowed_base = base.resolve()  # type: ignore[attr-defined]
    sink.write(_results(), metadata={"experiment": "e"})
    bundle_dir = base / "bundle"
    assert (bundle_dir / "manifest.json").exists()
    assert (bundle_dir / "results.json").exists()
    assert (bundle_dir / "results.csv").exists()


def test_local_bundle_rejects_escape_outside_base(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    allowed = tmp_path / "outputs"
    allowed.mkdir()
    sink = LocalBundleSink(base_path=base_dir, bundle_name="b", timestamped=False)
    sink._allowed_base = allowed.resolve()  # type: ignore[attr-defined]
    with pytest.raises(ValueError):
        sink.write(_results(), metadata={"experiment": "e"})

