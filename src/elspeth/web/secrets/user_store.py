"""Fernet-encrypted user-scoped secret store.

Each secret is encrypted with a key derived from ``master_key`` + a per-secret
random salt via PBKDF2-HMAC-SHA256.  The salt is stored alongside the
ciphertext so decryption can re-derive the same key.

All methods are synchronous and open their own connection, making them safe to
call from worker threads without sharing connection state.
"""

from __future__ import annotations

import base64
import hashlib
import os
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
import structlog
from cryptography.fernet import Fernet
from sqlalchemy.engine import Engine

from elspeth.contracts.secrets import SecretInventoryItem
from elspeth.contracts.security import secret_fingerprint
from elspeth.core.security.secret_loader import SecretNotFoundError, SecretRef
from elspeth.web.sessions.models import user_secrets_table

slog = structlog.get_logger()

_PBKDF2_ITERATIONS = 480_000
_SALT_BYTES = 16


def _compute_fingerprint(name: str, value: str) -> str:
    """Compute HMAC fingerprint of a secret value.

    Returns a 64-char hex digest.  Raises if ELSPETH_FINGERPRINT_KEY is
    not set — the fingerprint is required for audit trail integrity, and
    an empty value would crash downstream at SecretResolutionInput
    validation with a confusing generic error.
    """
    fp_key = os.environ.get("ELSPETH_FINGERPRINT_KEY")
    if not fp_key:
        raise RuntimeError(
            f"ELSPETH_FINGERPRINT_KEY is not set — cannot compute fingerprint for secret {name!r}. "
            "Set the environment variable before starting the web server."
        )
    return secret_fingerprint(value, key=fp_key.encode("utf-8"))


def _derive_fernet_key(master_key: str, salt: bytes) -> bytes:
    """Derive a 32-byte Fernet key from *master_key* and *salt* via PBKDF2."""
    raw = hashlib.pbkdf2_hmac(
        "sha256",
        master_key.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
    )
    # Fernet requires url-safe base64 encoded 32-byte key
    return base64.urlsafe_b64encode(raw)


class UserSecretStore:
    """Encrypted persistence for user-scoped secrets.

    Parameters
    ----------
    engine:
        SQLAlchemy ``Engine`` connected to the session database.
    master_key:
        Application-level master key used (with a per-secret salt) to derive
        Fernet encryption keys.
    """

    def __init__(self, engine: Engine, master_key: str) -> None:
        self._engine = engine
        self._master_key = master_key

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def has_secret(self, name: str, *, user_id: str) -> bool:
        """Check if a user secret exists without decrypting."""
        t = user_secrets_table
        with self._engine.connect() as conn:
            row = conn.execute(sa.select(t.c.id).where(sa.and_(t.c.name == name, t.c.user_id == user_id))).first()
            return row is not None

    def get_secret(self, name: str, *, user_id: str) -> tuple[str, SecretRef]:
        """Retrieve and decrypt a user secret.

        Returns
        -------
        tuple[str, SecretRef]
            The plaintext value and an audit-safe reference (no value).

        Raises
        ------
        SecretNotFoundError
            If no secret with *name* exists for *user_id*.
        """
        t = user_secrets_table
        stmt = sa.select(t.c.encrypted_value, t.c.salt).where(sa.and_(t.c.name == name, t.c.user_id == user_id))

        with self._engine.connect() as conn:
            row = conn.execute(stmt).first()

        if row is None:
            raise SecretNotFoundError(f"Secret {name!r} not found for user {user_id!r}")

        key = _derive_fernet_key(self._master_key, row.salt)
        plaintext = Fernet(key).decrypt(row.encrypted_value).decode("utf-8")
        fp = _compute_fingerprint(name, plaintext)
        ref = SecretRef(name=name, fingerprint=fp, source="user")
        return plaintext, ref

    def set_secret(self, name: str, *, value: str, user_id: str) -> None:
        """Create or update a user secret (upsert semantics).

        A fresh random salt is generated on every write so that updating a
        secret also rotates the derived key.
        """
        salt = os.urandom(_SALT_BYTES)
        key = _derive_fernet_key(self._master_key, salt)
        encrypted = Fernet(key).encrypt(value.encode("utf-8"))
        now = datetime.now(UTC)

        t = user_secrets_table

        with self._engine.begin() as conn:
            # Check for existing row
            existing = conn.execute(sa.select(t.c.id).where(sa.and_(t.c.name == name, t.c.user_id == user_id))).first()

            if existing is not None:
                conn.execute(
                    t.update()
                    .where(t.c.id == existing.id)
                    .values(
                        encrypted_value=encrypted,
                        salt=salt,
                        updated_at=now,
                    )
                )
            else:
                conn.execute(
                    t.insert().values(
                        id=str(uuid.uuid4()),
                        name=name,
                        user_id=user_id,
                        encrypted_value=encrypted,
                        salt=salt,
                        created_at=now,
                        updated_at=now,
                    )
                )

    def delete_secret(self, name: str, *, user_id: str) -> bool:
        """Delete a user secret.

        Returns ``True`` if a row was deleted, ``False`` if it did not exist.
        """
        t = user_secrets_table

        with self._engine.begin() as conn:
            result = conn.execute(t.delete().where(sa.and_(t.c.name == name, t.c.user_id == user_id)))
        return result.rowcount > 0

    def list_secrets(self, *, user_id: str) -> list[SecretInventoryItem]:
        """List secret metadata for a user (no values returned)."""
        t = user_secrets_table
        stmt = sa.select(t.c.name).where(t.c.user_id == user_id).order_by(t.c.name)

        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()

        return [
            SecretInventoryItem(
                name=row.name,
                scope="user",
                available=True,
                source_kind="user_store",
            )
            for row in rows
        ]
