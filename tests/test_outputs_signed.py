import json

from elspeth.core.security import verify_signature
from elspeth.plugins.outputs.signed import SignedArtifactSink


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
