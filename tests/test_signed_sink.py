from __future__ import annotations

import json
from pathlib import Path

import pytest

from elspeth.core.security.secure_mode import SecureMode
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


def test_signed_sink_on_error_skip_when_missing_key(tmp_path: Path) -> None:
    sink = SignedArtifactSink(base_path=tmp_path, bundle_name="nokey", timestamped=False, on_error="skip", key_env="MISSING_ENV_VAR")
    sink.write(_results(), metadata={"experiment": "e"})
    # Bundle dir may exist (results written before key resolution), but signature should be absent
    bundle = tmp_path / "nokey"
    assert (bundle / "results.json").exists()
    assert not (bundle / "signature.json").exists()


def test_signed_sink_strict_mode_disallows_skip(monkeypatch):
    # Enforce STRICT mode; sink should raise at init when on_error='skip'
    monkeypatch.setattr("elspeth.plugins.nodes.sinks.signed.get_secure_mode", lambda: SecureMode.STRICT)
    with pytest.raises(ValueError):
        _ = SignedArtifactSink(base_path="/tmp", on_error="skip")


def test_signed_sink_logs_debug_on_fingerprint_failure(tmp_path: Path, monkeypatch):
    # Avoid crypto deps; force fingerprint path and failure
    monkeypatch.setattr(
        "elspeth.plugins.nodes.sinks.signed.generate_signature",
        lambda payload, key, algorithm: "sig",
    )
    monkeypatch.setattr(
        "elspeth.plugins.nodes.sinks.signed.public_key_fingerprint",
        lambda pem: (_ for _ in ()).throw(RuntimeError("bad pem")),
    )

    sink = SignedArtifactSink(
        base_path=str(tmp_path),
        bundle_name="signed",
        timestamped=False,
        algorithm="rsa-pss-sha256",
        key="any-private-pem",
        public_key_env="TEST_PUB_KEY",
    )
    monkeypatch.setenv("TEST_PUB_KEY", "--- invalid public key ---")

    sink.write(_results(), metadata={"name": "exp"})

    sig_path = tmp_path / "signed" / sink.signature_name
    assert sig_path.exists()
    payload = json.loads(sig_path.read_text(encoding="utf-8"))
    assert "signature" in payload
    assert "key_fingerprint" not in payload
