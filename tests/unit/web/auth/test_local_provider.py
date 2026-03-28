"""Tests for LocalAuthProvider -- SQLite user store, bcrypt hashing, JWT tokens."""

from __future__ import annotations

import time

import pytest

from elspeth.web.auth.local import LocalAuthProvider
from elspeth.web.auth.models import AuthenticationError, UserIdentity, UserProfile


@pytest.fixture
def provider(tmp_path):
    """Create a LocalAuthProvider with a temporary SQLite database."""
    return LocalAuthProvider(
        db_path=tmp_path / "auth.db",
        secret_key="test-secret-key-for-unit-tests",
        token_expiry_hours=24,
    )


class TestCreateUser:
    """Tests for user creation."""

    def test_create_user_succeeds(self, provider) -> None:
        provider.create_user("alice", "password123", display_name="Alice Smith")
        # No exception means success

    def test_create_user_with_email(self, provider) -> None:
        provider.create_user(
            "alice",
            "password123",
            display_name="Alice Smith",
            email="alice@example.com",
        )

    def test_create_duplicate_user_raises_value_error(self, provider) -> None:
        provider.create_user("alice", "password123", display_name="Alice")
        with pytest.raises(ValueError, match="alice"):
            provider.create_user("alice", "other-password", display_name="Alice 2")

    def test_create_user_empty_display_name_raises(self, provider) -> None:
        with pytest.raises(ValueError, match="display_name must not be empty"):
            provider.create_user("alice", "password123", display_name="")


class TestLogin:
    """Tests for username/password login."""

    def test_login_returns_jwt_string(self, provider) -> None:
        provider.create_user("alice", "password123", display_name="Alice")
        token = provider.login("alice", "password123")
        assert isinstance(token, str)
        assert len(token) > 0
        # JWT has three dot-separated segments
        assert len(token.split(".")) == 3

    def test_login_wrong_password_raises(self, provider) -> None:
        provider.create_user("alice", "password123", display_name="Alice")
        with pytest.raises(AuthenticationError, match="Invalid credentials"):
            provider.login("alice", "wrong-password")

    def test_login_unknown_user_raises(self, provider) -> None:
        with pytest.raises(AuthenticationError, match="Invalid credentials"):
            provider.login("nonexistent", "password")


class TestAuthenticate:
    """Tests for JWT token validation."""

    @pytest.mark.asyncio
    async def test_authenticate_valid_token(self, provider) -> None:
        provider.create_user("alice", "pw", display_name="Alice")
        token = provider.login("alice", "pw")
        identity = await provider.authenticate(token)
        assert isinstance(identity, UserIdentity)
        assert identity.user_id == "alice"
        assert identity.username == "alice"

    @pytest.mark.asyncio
    async def test_authenticate_garbage_token(self, provider) -> None:
        with pytest.raises(AuthenticationError, match="Invalid token"):
            await provider.authenticate("garbage-not-a-jwt")

    @pytest.mark.asyncio
    async def test_authenticate_expired_token(self, tmp_path) -> None:
        """Token with 0-second expiry should fail after creation."""
        from jose import jwt as jose_jwt

        provider = LocalAuthProvider(
            db_path=tmp_path / "auth.db",
            secret_key="test-key",
            token_expiry_hours=24,
        )
        provider.create_user("alice", "pw", display_name="Alice")

        # Manually create an already-expired token
        payload = {
            "sub": "alice",
            "username": "alice",
            "exp": int(time.time()) - 10,  # 10 seconds in the past
        }
        expired_token = jose_jwt.encode(payload, "test-key", algorithm="HS256")

        with pytest.raises(AuthenticationError):
            await provider.authenticate(expired_token)

    @pytest.mark.asyncio
    async def test_authenticate_wrong_secret_key(self, tmp_path) -> None:
        """Token signed with a different key should fail."""
        from jose import jwt as jose_jwt

        provider = LocalAuthProvider(
            db_path=tmp_path / "auth.db",
            secret_key="correct-key",
        )
        payload = {
            "sub": "alice",
            "username": "alice",
            "exp": int(time.time()) + 3600,
        }
        bad_token = jose_jwt.encode(payload, "wrong-key", algorithm="HS256")
        with pytest.raises(AuthenticationError, match="Invalid token"):
            await provider.authenticate(bad_token)


class TestGetUserInfo:
    """Tests for full user profile retrieval."""

    @pytest.mark.asyncio
    async def test_get_user_info_returns_profile(self, provider) -> None:
        provider.create_user(
            "alice",
            "pw",
            display_name="Alice Smith",
            email="alice@example.com",
        )
        token = provider.login("alice", "pw")
        profile = await provider.get_user_info(token)
        assert isinstance(profile, UserProfile)
        assert profile.user_id == "alice"
        assert profile.username == "alice"
        assert profile.display_name == "Alice Smith"
        assert profile.email == "alice@example.com"
        assert profile.groups == ()

    @pytest.mark.asyncio
    async def test_get_user_info_no_email(self, provider) -> None:
        provider.create_user("bob", "pw", display_name="Bob")
        token = provider.login("bob", "pw")
        profile = await provider.get_user_info(token)
        assert profile.email is None

    @pytest.mark.asyncio
    async def test_get_user_info_invalid_token(self, provider) -> None:
        with pytest.raises(AuthenticationError):
            await provider.get_user_info("garbage-token")

    @pytest.mark.asyncio
    async def test_get_user_info_deleted_user(self, provider) -> None:
        """User deleted between login (token issued) and get_user_info call."""
        provider.create_user("alice", "pw", display_name="Alice")
        token = provider.login("alice", "pw")

        # Delete the user directly via sqlite3
        import sqlite3

        with sqlite3.connect(str(provider._db_path)) as conn:
            conn.execute("DELETE FROM users WHERE user_id = ?", ("alice",))

        with pytest.raises(AuthenticationError, match="User not found"):
            await provider.get_user_info(token)


class TestLoginEdgeCases:
    """Edge-case tests for login input validation."""

    def test_login_empty_username_raises(self, provider) -> None:
        with pytest.raises(AuthenticationError, match="Invalid credentials"):
            provider.login("", "some-password")

    def test_login_empty_password_raises(self, provider) -> None:
        provider.create_user("alice", "pw", display_name="Alice")
        with pytest.raises(AuthenticationError, match="Invalid credentials"):
            provider.login("alice", "")


class TestProtocolConformance:
    """Verify LocalAuthProvider satisfies the AuthProvider protocol."""

    def test_local_satisfies_auth_provider(self, provider) -> None:
        from elspeth.web.auth.protocol import AuthProvider

        typed: AuthProvider = provider
        assert callable(type(typed).authenticate)
        assert callable(type(typed).get_user_info)
