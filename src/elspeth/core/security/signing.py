"""Signing helpers supporting HMAC and asymmetric (RSA/ECDSA) schemes.

This module intentionally keeps a small surface area so that callers can use
the same ``generate_signature`` / ``verify_signature`` APIs for both HMAC and
asymmetric algorithms.

For asymmetric keys, pass PEM-encoded private/public keys as the ``key``
argument (bytes or str). No password handling is implemented here; provide
unencrypted PEM for test/CI or inject a pre-decrypted key from your KMS client.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Literal

try:  # asymmetric crypto is optional at runtime, but available in dev/test
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, padding

    _ASYM_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency guard
    _ASYM_AVAILABLE = False

Algorithm = Literal[
    "hmac-sha256",
    "hmac-sha512",
    "rsa-pss-sha256",
    "ecdsa-p256-sha256",
]


def _normalize_key(key: str | bytes) -> bytes:
    """Ensure secret keys are bytes prior to HMAC operations."""

    if isinstance(key, bytes):
        return key
    return key.encode("utf-8")


def _resolve_digest(algorithm: Algorithm):
    """Return the hashlib constructor for the requested algorithm."""

    if algorithm == "hmac-sha256":
        return hashlib.sha256
    if algorithm == "hmac-sha512":
        return hashlib.sha512
    # Asymmetric algorithms use cryptography.hazmat (handled separately)
    raise ValueError(f"Unsupported HMAC algorithm '{algorithm}'")


def _is_hmac(algorithm: Algorithm) -> bool:
    return algorithm.startswith("hmac-")


def _ensure_asym_available() -> None:
    if not _ASYM_AVAILABLE:
        raise RuntimeError("Asymmetric signing requires 'cryptography' package")


def _load_private_key(pem: str | bytes):
    _ensure_asym_available()
    if isinstance(pem, str):
        pem_b = pem.encode("utf-8")
    else:
        pem_b = pem
    return serialization.load_pem_private_key(pem_b, password=None)


def _load_public_key(pem: str | bytes):
    _ensure_asym_available()
    if isinstance(pem, str):
        pem_b = pem.encode("utf-8")
    else:
        pem_b = pem
    return serialization.load_pem_public_key(pem_b)


def public_key_fingerprint(public_pem: str | bytes) -> str:
    """Compute SHA256 fingerprint of a public key (SubjectPublicKeyInfo DER).

    Returns a lowercase hex digest for portability.
    """
    _ensure_asym_available()
    pub = _load_public_key(public_pem)
    der = pub.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(der).hexdigest()


def generate_signature(data: bytes, key: str | bytes, algorithm: Algorithm = "hmac-sha256") -> str:
    """Generate a base64-encoded signature for the payload.

    - For HMAC algorithms, ``key`` is a shared secret.
    - For asymmetric algorithms, ``key`` is a PEM-encoded private key.
    """
    if _is_hmac(algorithm):
        digest = _resolve_digest(algorithm)
        signer = hmac.new(_normalize_key(key), data, digest)
        return base64.b64encode(signer.digest()).decode("ascii")

    # Asymmetric schemes
    _ensure_asym_available()
    priv = _load_private_key(key)
    if algorithm == "rsa-pss-sha256":
        sig = priv.sign(
            data,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        return base64.b64encode(sig).decode("ascii")
    if algorithm == "ecdsa-p256-sha256":
        # Expect an EC private key (secp256r1)
        sig = priv.sign(data, ec.ECDSA(hashes.SHA256()))
        return base64.b64encode(sig).decode("ascii")
    raise ValueError(f"Unsupported algorithm '{algorithm}'")


def verify_signature(data: bytes, signature: str, key: str | bytes, algorithm: Algorithm = "hmac-sha256") -> bool:
    """Verify a signature for the payload.

    - For HMAC, ``key`` is the shared secret.
    - For asymmetric, ``key`` is a PEM-encoded public key.
    """
    if _is_hmac(algorithm):
        expected = generate_signature(data, key, algorithm)
        return hmac.compare_digest(expected, signature)

    # Asymmetric verification
    _ensure_asym_available()
    pub = _load_public_key(key)
    sig_bytes = base64.b64decode(signature.encode("ascii"))
    try:
        if algorithm == "rsa-pss-sha256":
            pub.verify(
                sig_bytes,
                data,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            return True
        if algorithm == "ecdsa-p256-sha256":
            pub.verify(sig_bytes, data, ec.ECDSA(hashes.SHA256()))
            return True
    except Exception:
        return False
    raise ValueError(f"Unsupported algorithm '{algorithm}'")


__all__ = [
    "Algorithm",
    "generate_signature",
    "verify_signature",
    "public_key_fingerprint",
]
