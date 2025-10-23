from __future__ import annotations

import pytest


def test_generate_signature_rejects_encrypted_pem():
    try:
        from cryptography.hazmat.primitives import serialization, hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
    except Exception:  # pragma: no cover - cryptography optional in some envs
        pytest.skip("cryptography not available")

    # Generate an RSA private key and serialize with password protection
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    encrypted_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(b"secret"),
    )

    from elspeth.core.security.signing import generate_signature

    with pytest.raises(ValueError) as err:
        generate_signature(b"data", encrypted_pem, algorithm="rsa-pss-sha256")
    assert "Password-protected PEM keys" in str(err.value)
