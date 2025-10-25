"""Shared test fixtures for ADR-002 security tests.

This module contains common mock components used across ADR-002 test files.
Keeping them separate avoids Hypothesis health check warnings about nested @given.
"""

from elspeth.core.base.types import SecurityLevel


class MockPlugin:
    """Mock plugin with configurable security level for testing."""

    def __init__(self, security_level: SecurityLevel):
        self._security_level = security_level

    def get_security_level(self) -> SecurityLevel:
        """Return this plugin's security requirement."""
        return self._security_level

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        """Validate plugin can operate at the given envelope level.

        Raises:
            SecurityValidationError: If operating_level < self._security_level
        """
        from elspeth.core.validation.base import SecurityValidationError

        if operating_level < self._security_level:
            raise SecurityValidationError(
                f"{self.__class__.__name__} requires {self._security_level.name}, "
                f"but orchestrator operating at {operating_level.name}"
            )


class UnofficialPlugin(MockPlugin):
    """Plugin that handles UNOFFICIAL data."""

    def __init__(self):
        super().__init__(SecurityLevel.UNOFFICIAL)


class OfficialPlugin(MockPlugin):
    """Plugin that requires OFFICIAL clearance."""

    def __init__(self):
        super().__init__(SecurityLevel.OFFICIAL)


class SecretPlugin(MockPlugin):
    """Plugin that requires SECRET clearance."""

    def __init__(self):
        super().__init__(SecurityLevel.SECRET)
