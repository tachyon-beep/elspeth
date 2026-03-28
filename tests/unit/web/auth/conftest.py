"""Shared fixtures for auth provider tests.

Provides RSA keypair generation, JWKS response building, and JWT
signing for both OIDC and Entra test modules.
"""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwk
from jose import jwt as jose_jwt


@pytest.fixture
def rsa_keypair():
    """Generate an RSA key pair for signing test JWTs."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def jwks_response(rsa_keypair):
    """Build a JWKS response dict from the test RSA public key."""
    _, public_key = rsa_keypair
    pub_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    # Convert to JWK format
    key_obj = jwk.RSAKey(algorithm="RS256", key=pub_pem.decode())
    key_dict = key_obj.to_dict()
    key_dict["kid"] = "test-key-1"
    key_dict["use"] = "sig"
    return {"keys": [key_dict]}


def make_rs256_token(private_key, claims: dict) -> str:
    """Sign a JWT with an RSA private key (RS256, kid=test-key-1).

    Not a fixture — a plain helper function imported explicitly by
    test modules that need it.
    """
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return jose_jwt.encode(
        claims,
        priv_pem.decode(),
        algorithm="RS256",
        headers={"kid": "test-key-1"},
    )
