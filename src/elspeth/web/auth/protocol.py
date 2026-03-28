"""Authentication provider protocol.

Defines the two-method interface that all auth implementations must satisfy.
No exception definitions here -- AuthenticationError lives in models.py.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from elspeth.web.auth.models import UserIdentity, UserProfile


@runtime_checkable
class AuthProvider(Protocol):
    """Protocol for pluggable authentication providers."""

    async def authenticate(self, token: str) -> UserIdentity:
        """Validate a token and return the authenticated identity.

        Raises AuthenticationError if the token is invalid, expired,
        or otherwise unacceptable.
        """
        ...

    async def get_user_info(self, token: str) -> UserProfile:
        """Get full user profile from a valid token.

        Raises AuthenticationError if the token is invalid.
        """
        ...
