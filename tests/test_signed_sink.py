from __future__ import annotations

import json
from pathlib import Path

from elspeth.plugins.nodes.sinks.signed import SignedArtifactSink


def _results() -> dict:
    return {"results": [{"row": {"id": 1}, "response": {"content": "ok"}}]}


def test_signed_sink_writes_bundle(tmp_path: Path) -> None:
    sink = SignedArtifactSink(base_path=tmp_path, bundle_name="signed", timestamped=False, key="k")
    sink.write(_results(), metadata={"experiment": "e"})
    bundle = tmp_path / "signed"
    assert (bundle / "results.json").exists()
    sig = json.loads((bundle / "signature.json").read_text(encoding="utf-8"))
    assert sig.get("algorithm") in {"hmac-sha256", "hmac-sha512"}
    assert sig.get("target") == "results.json"
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("signature", {}).get("value")


def test_signed_sink_legacy_env_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DMP_SIGNING_KEY", "legacy")
    sink = SignedArtifactSink(base_path=tmp_path, bundle_name="legacy", timestamped=False)
    sink.write(_results(), metadata={"experiment": "e"})
    assert (tmp_path / "legacy" / "signature.json").exists()


def test_signed_sink_on_error_skip_when_missing_key(tmp_path: Path) -> None:
    sink = SignedArtifactSink(base_path=tmp_path, bundle_name="nokey", timestamped=False, on_error="skip", key_env="MISSING_ENV_VAR")
    sink.write(_results(), metadata={"experiment": "e"})
    # Bundle dir may exist (results written before key resolution), but signature should be absent
    bundle = tmp_path / "nokey"
    assert (bundle / "results.json").exists()
    assert not (bundle / "signature.json").exists()
