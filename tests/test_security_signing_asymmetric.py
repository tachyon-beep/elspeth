from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from elspeth.core.security import generate_signature, public_key_fingerprint, verify_signature
from elspeth.plugins.nodes.sinks.signed import SignedArtifactSink


def _make_rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv_pem.decode("utf-8"), pub_pem.decode("utf-8")


def test_asymmetric_generate_verify_rsa_pss():
    priv_pem, pub_pem = _make_rsa_keypair()
    data = b"hello-world"
    sig = generate_signature(data, priv_pem, algorithm="rsa-pss-sha256")
    assert isinstance(sig, str)
    assert verify_signature(data, sig, pub_pem, algorithm="rsa-pss-sha256")
    assert not verify_signature(b"tampered", sig, pub_pem, algorithm="rsa-pss-sha256")
    fp = public_key_fingerprint(pub_pem)
    assert len(fp) == 64  # hex sha256


def test_signed_artifact_sink_with_rsa_pss(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    priv_pem, pub_pem = _make_rsa_keypair()
    monkeypatch.setenv("ELSPETH_SIGNING_PRIVATE_PEM", priv_pem)
    base = tmp_path / "signed"
    sink = SignedArtifactSink(
        base_path=str(base),
        bundle_name="bundle",
        timestamped=False,
        algorithm="rsa-pss-sha256",
        key_env="ELSPETH_SIGNING_PRIVATE_PEM",
        public_key_env=None,  # not required; sink computes fingerprint best-effort
        on_error="abort",
    )

    results = {"results": [{"row": {"x": 1}, "response": {"content": "ok"}}]}
    sink.write(results, metadata={"experiment": "e"})

    sig_path = base / "bundle" / sink.signature_name
    res_path = base / "bundle" / sink.results_name
    assert sig_path.exists() and res_path.exists()

    sig_payload = json.loads(sig_path.read_text(encoding="utf-8"))
    assert sig_payload["algorithm"] == "rsa-pss-sha256"
    assert "signature" in sig_payload
    # Verify signature using the test-generated public PEM
    sig = sig_payload["signature"]
    raw = res_path.read_bytes()
    assert verify_signature(raw, sig, pub_pem, algorithm="rsa-pss-sha256")

