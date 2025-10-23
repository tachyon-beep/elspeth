from __future__ import annotations

import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from elspeth.plugins.nodes.sinks.signed import SignedArtifactSink


def _make_rsa_keypair_pem() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    pub_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return priv_pem, pub_pem


def test_signed_artifact_sink_fetches_key_from_keyvault(monkeypatch, tmp_path: Path):
    # Monkeypatch fetch_secret_from_keyvault to avoid Azure SDK/runtime dependency
    priv_pem, _ = _make_rsa_keypair_pem()

    def _fake_fetch(uri: str) -> str:  # noqa: ARG001
        return priv_pem

    # Monkeypatch at the sink module import site
    import elspeth.plugins.nodes.sinks.signed as signed_mod

    monkeypatch.setattr(signed_mod, "fetch_secret_from_keyvault", _fake_fetch)

    sink = SignedArtifactSink(
        base_path=str(tmp_path / "signed"),
        bundle_name="b",
        timestamped=False,
        algorithm="rsa-pss-sha256",
        key_vault_secret_uri="https://example.vault.azure.net/secrets/signing/123",
    )
    payload = {"results": [{"row": {"x": 1}, "response": {"content": "ok"}}]}
    sink.write(payload, metadata={"experiment": "e"})

    sig_path = tmp_path / "signed" / "b" / sink.signature_name
    assert sig_path.exists()
    sig = json.loads(sig_path.read_text(encoding="utf-8"))
    assert sig["algorithm"] == "rsa-pss-sha256"
