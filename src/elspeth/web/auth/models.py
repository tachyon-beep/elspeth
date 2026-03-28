"""Authentication data models.

UserIdentity and UserProfile are frozen dataclasses. All fields are scalars,
None, or tuple of scalars -- no freeze guard needed.

AuthenticationError is the domain exception raised by all auth providers
when token validation fails.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserIdentity:
    """Minimal authenticated identity -- returned from every auth check."""

    user_id: str
    username: str


@dataclass(frozen=True, slots=True)
class UserProfile:
    """Extended user profile information."""

    user_id: str
    username: str
    display_name: str
    email: str | None = None
    groups: tuple[str, ...] = ()


class AuthenticationError(Exception):
    """Raised when authentication fails.

    Caught by the auth middleware and converted to HTTP 401.
    """

    def __init__(self, detail: str = "Authentication failed") -> None:
        self.detail = detail
        super().__init__(detail)
