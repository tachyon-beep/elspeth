import json
from datetime import datetime, timezone

from elspeth.core.security import verify_signature
from elspeth.plugins.nodes.sinks.signed import SignedArtifactSink


def fake_results():
    return {
        "results": [
            {
                "row": {"APPID": "1"},
                "response": {"content": "ok"},
            }
        ],
    }


def test_signed_artifact_sink(tmp_path):
    base = tmp_path / "signed"
    sink = SignedArtifactSink(base_path=base, key="secret", timestamped=False, bundle_name="exp1")
    sink.write(fake_results(), metadata={"experiment": "exp1"})

    bundle_dir = base / "exp1"
    results_path = bundle_dir / "results.json"
    signature_path = bundle_dir / "signature.json"
    manifest_path = bundle_dir / "manifest.json"

    results_bytes = results_path.read_bytes()
    signature_payload = json.loads(signature_path.read_text(encoding="utf-8"))
    assert verify_signature(results_bytes, signature_payload["signature"], "secret")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["signature"]["value"] == signature_payload["signature"]
    assert manifest["rows"] == 1


def test_signed_artifact_sink_env_key_and_timestamp(tmp_path, monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    monkeypatch.setenv("ELSPETH_SIGNING_KEY", "env-secret")
    monkeypatch.setattr("elspeth.plugins.nodes.sinks.signed.datetime", FixedDateTime)

    base = tmp_path / "signed"
    sink = SignedArtifactSink(base_path=base, bundle_name="exp", timestamped=True)
    sink.write(fake_results(), metadata={"name": "exp"})

    bundle_dirs = list(base.iterdir())
    assert len(bundle_dirs) == 1
    assert bundle_dirs[0].name == "exp_20240102T030405Z"
    assert sink.key == "env-secret"


def test_signed_artifact_sink_skip_on_error(monkeypatch, tmp_path, caplog):
    monkeypatch.delenv("ELSPETH_SIGNING_KEY", raising=False)
    sink = SignedArtifactSink(base_path=tmp_path / "signed", bundle_name="exp", timestamped=False, on_error="skip")

    with caplog.at_level("WARNING"):
        sink.write(fake_results(), metadata={})

    assert any("skipping bundle creation" in record.message for record in caplog.records)
