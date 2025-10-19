from __future__ import annotations

import base64

import pytest

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

import elspeth.core.security.signing as signing


def test_hmac_with_bytes_key_and_unsupported_hmac():
    data = b"hello"
    key_bytes = b"secret"
    sig = signing.generate_signature(data, key_bytes, algorithm="hmac-sha256")
    assert isinstance(sig, str)

    with pytest.raises(ValueError):
        signing.generate_signature(data, key_bytes, algorithm="hmac-sha1")


def test_asymmetric_unavailable_guard(monkeypatch):
    # Force asymmetric to be unavailable
    monkeypatch.setattr(signing, "_ASYM_AVAILABLE", False)
    with pytest.raises(RuntimeError):
        signing.generate_signature(b"data", "-----BEGIN PRIVATE KEY-----\nX\n", algorithm="rsa-pss-sha256")


def test_ecdsa_sign_verify_and_unsupported_algo():
    # Generate P-256 key
    private_key = ec.generate_private_key(ec.SECP256R1())
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    pub_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    data = b"payload"
    sig = signing.generate_signature(data, priv_pem, algorithm="ecdsa-p256-sha256")
    assert isinstance(sig, str)
    assert signing.verify_signature(data, sig, pub_pem, algorithm="ecdsa-p256-sha256")

    # Unsupported verify algorithm path
    with pytest.raises(ValueError):
        signing.verify_signature(data, base64.b64encode(b"x").decode("ascii"), pub_pem, algorithm="ecdsa-unknown")

