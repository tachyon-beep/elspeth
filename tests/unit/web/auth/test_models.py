"""Tests for authentication data models."""

from __future__ import annotations

import pytest

from elspeth.web.auth.models import AuthenticationError, UserIdentity, UserProfile


class TestUserIdentity:
    """Tests for the minimal authentication identity."""

    def test_frozen_immutability(self) -> None:
        identity = UserIdentity(user_id="alice", username="alice")
        with pytest.raises(AttributeError):
            identity.user_id = "bob"  # type: ignore[misc]


class TestUserProfile:
    """Tests for the extended user profile."""

    def test_construction_all_fields(self) -> None:
        profile = UserProfile(
            user_id="alice",
            username="alice",
            display_name="Alice Smith",
            email="alice@example.com",
            groups=("admin", "users"),
        )
        assert profile.user_id == "alice"
        assert profile.display_name == "Alice Smith"
        assert profile.email == "alice@example.com"
        assert profile.groups == ("admin", "users")

    def test_defaults(self) -> None:
        profile = UserProfile(
            user_id="bob",
            username="bob",
            display_name="Bob",
        )
        assert profile.email is None
        assert profile.groups == ()

    def test_frozen_immutability(self) -> None:
        profile = UserProfile(
            user_id="alice",
            username="alice",
            display_name="Alice",
        )
        with pytest.raises(AttributeError):
            profile.email = "x@y.com"  # type: ignore[misc]


class TestAuthenticationError:
    """Tests for the authentication exception."""

    def test_default_message(self) -> None:
        err = AuthenticationError()
        assert err.detail == "Authentication failed"
        assert str(err) == "Authentication failed"

    def test_custom_message(self) -> None:
        err = AuthenticationError("Token expired")
        assert err.detail == "Token expired"
        assert str(err) == "Token expired"

    def test_is_exception(self) -> None:
        err = AuthenticationError()
        assert isinstance(err, Exception)
