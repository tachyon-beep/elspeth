"""Local authentication provider -- SQLite user store with bcrypt and JWT.

Uses bcrypt for password hashing and python-jose for JWT token creation
and validation. The SQLite database is created at db_path on first use.
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path

import bcrypt
from jose import JWTError, jwt

from elspeth.web.auth.models import AuthenticationError, UserIdentity, UserProfile


class LocalAuthProvider:
    """Authenticates users against a local SQLite database with bcrypt + JWT."""

    def __init__(
        self,
        db_path: Path,
        secret_key: str,
        token_expiry_hours: int = 24,
    ) -> None:
        self._db_path = db_path
        self._secret_key = secret_key
        self._token_expiry_hours = token_expiry_hours
        self._ensure_schema()
        self._dummy_hash = bcrypt.hashpw(b"dummy", bcrypt.gensalt())

    def _get_conn(self) -> sqlite3.Connection:
        """Open a connection to the SQLite database."""
        return sqlite3.connect(str(self._db_path))

    def _ensure_schema(self) -> None:
        """Create the users table if it does not exist."""
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    email TEXT
                )
                """
            )

    def create_user(
        self,
        user_id: str,
        password: str,
        display_name: str,
        email: str | None = None,
    ) -> None:
        """Create a new user with a bcrypt-hashed password.

        Raises ValueError if a user with the given user_id already exists
        or if display_name is empty.
        """
        if not display_name:
            raise ValueError("display_name must not be empty")
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        with self._get_conn() as conn:
            try:
                conn.execute(
                    "INSERT INTO users (user_id, password_hash, display_name, email) VALUES (?, ?, ?, ?)",
                    (user_id, password_hash, display_name, email),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"User already exists: {user_id}") from exc

    def login(self, username: str, password: str) -> str:
        """Authenticate with username/password and return a JWT.

        Raises AuthenticationError("Invalid credentials") on failure.
        Uses constant-time comparison to prevent username enumeration
        via timing side-channel.
        """
        if not username or not password:
            raise AuthenticationError("Invalid credentials")

        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE user_id = ?",
                (username,),
            ).fetchone()

        if row is None:
            # Constant-time: hash against dummy to prevent timing oracle
            bcrypt.checkpw(password.encode(), self._dummy_hash)
            raise AuthenticationError("Invalid credentials")

        if not bcrypt.checkpw(password.encode(), row[0].encode()):
            raise AuthenticationError("Invalid credentials")

        payload = {
            "sub": username,
            "username": username,
            "exp": int(time.time()) + self._token_expiry_hours * 3600,
        }
        token: str = jwt.encode(payload, self._secret_key, algorithm="HS256")
        return token

    def refresh(self, user_id: str, username: str) -> str:
        """Issue a new JWT for an already-authenticated user.

        Verifies the user still exists in the database -- a deleted
        user must not be able to obtain fresh tokens via refresh.

        Called by the token refresh route. Does NOT re-verify
        credentials -- the caller (get_current_user middleware)
        has already validated the existing token.
        """
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            raise AuthenticationError("User not found")

        payload = {
            "sub": user_id,
            "username": username,
            "exp": int(time.time()) + self._token_expiry_hours * 3600,
        }
        token: str = jwt.encode(payload, self._secret_key, algorithm="HS256")
        return token

    async def authenticate(self, token: str) -> UserIdentity:
        """Validate a JWT and return the authenticated identity.

        Raises AuthenticationError("Invalid token") on decode failure or expiry.
        """
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=["HS256"])
        except JWTError as exc:
            raise AuthenticationError("Invalid token") from exc

        return UserIdentity(
            user_id=payload["sub"],
            username=payload["username"],
        )

    def _query_user(self, user_id: str) -> tuple[str, str | None] | None:
        """Synchronous DB lookup — called via asyncio.to_thread."""
        with self._get_conn() as conn:
            row: tuple[str, str | None] | None = conn.execute(
                "SELECT display_name, email FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return row

    async def get_user_info(self, token: str) -> UserProfile:
        """Decode the JWT, then query the users table for full profile.

        The DB query is offloaded to a thread to avoid blocking the
        event loop — sqlite3 is synchronous.
        """
        identity = await self.authenticate(token)

        row = await asyncio.to_thread(self._query_user, identity.user_id)

        if row is None:
            raise AuthenticationError("User not found")

        return UserProfile(
            user_id=identity.user_id,
            username=identity.username,
            display_name=row[0],
            email=row[1],
        )
