"""Frozen Plugin Capability Tests (ADR-005).

Tests the allow_downgrade=False capability for strict level enforcement.
Verifies both default trusted downgrade behavior and frozen plugin behavior.

Test Coverage:
- Default allow_downgrade=True (backwards compatibility)
- Frozen allow_downgrade=False (strict enforcement)
- Property-based testing with all SecurityLevel combinations
"""

import pytest
from hypothesis import given, strategies as st

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.types import SecurityLevel
from elspeth.core.validation.base import SecurityValidationError


# ============================================================================
# TEST FIXTURES
# ============================================================================


class MockPlugin(BasePlugin):
    """Mock plugin for testing frozen capability."""

    def __init__(
        self,
        *,
        security_level: SecurityLevel,
        allow_downgrade: bool = True
    ):
        super().__init__(
            security_level=security_level,
            allow_downgrade=allow_downgrade
        )


# ============================================================================
# TEST DEFAULT TRUSTED DOWNGRADE (ADR-002 Semantics)
# ============================================================================


class TestDefaultTrustedDowngrade:
    """Test default allow_downgrade=True behavior (ADR-002 semantics).

    These tests verify backwards compatibility - the default behavior should
    allow trusted downgrade as specified in ADR-002.
    """

    def test_default_parameter_is_true(self):
        """Default allow_downgrade parameter is True (backwards compatible)."""
        plugin = MockPlugin(security_level=SecurityLevel.SECRET)
        assert plugin.allow_downgrade is True

    def test_trusted_downgrade_to_lower_level(self):
        """SECRET plugin can operate at OFFICIAL level (trusted downgrade)."""
        plugin = MockPlugin(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=True
        )
        # Should not raise - trusted downgrade allowed
        plugin.validate_can_operate_at_level(SecurityLevel.OFFICIAL)

    def test_trusted_downgrade_to_lowest_level(self):
        """SECRET plugin can operate at UNOFFICIAL level (trusted downgrade)."""
        plugin = MockPlugin(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=True
        )
        # Should not raise - trusted downgrade allowed
        plugin.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)

    def test_exact_match_allowed(self):
        """Plugin can operate at exact declared level."""
        plugin = MockPlugin(
            security_level=SecurityLevel.OFFICIAL,
            allow_downgrade=True
        )
        # Should not raise - exact match
        plugin.validate_can_operate_at_level(SecurityLevel.OFFICIAL)

    def test_insufficient_clearance_rejected(self):
        """Plugin cannot operate ABOVE its clearance (Bell-LaPadula)."""
        plugin = MockPlugin(
            security_level=SecurityLevel.OFFICIAL,
            allow_downgrade=True
        )
        with pytest.raises(SecurityValidationError) as exc_info:
            plugin.validate_can_operate_at_level(SecurityLevel.SECRET)

        error_msg = str(exc_info.value)
        assert "Insufficient clearance" in error_msg
        assert "OFFICIAL" in error_msg
        assert "SECRET" in error_msg


# ============================================================================
# TEST FROZEN PLUGIN (ADR-005 Capability)
# ============================================================================


class TestFrozenPlugin:
    """Test allow_downgrade=False behavior (frozen plugins).

    These tests verify the new ADR-005 frozen plugin capability that enables
    strict level enforcement.
    """

    def test_frozen_property_reflects_parameter(self):
        """allow_downgrade property reflects constructor parameter."""
        plugin = MockPlugin(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=False
        )
        assert plugin.allow_downgrade is False

    def test_frozen_exact_match_allowed(self):
        """Frozen plugin can operate at exact declared level."""
        plugin = MockPlugin(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=False
        )
        # Should not raise - exact match allowed
        plugin.validate_can_operate_at_level(SecurityLevel.SECRET)

    def test_frozen_downgrade_rejected(self):
        """Frozen plugin cannot operate at lower level."""
        plugin = MockPlugin(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=False
        )
        with pytest.raises(SecurityValidationError) as exc_info:
            plugin.validate_can_operate_at_level(SecurityLevel.OFFICIAL)

        error_msg = str(exc_info.value)
        assert "frozen at SECRET" in error_msg
        assert "allow_downgrade=False" in error_msg
        assert "OFFICIAL" in error_msg

    def test_frozen_two_level_downgrade_rejected(self):
        """Frozen plugin cannot operate two levels below."""
        plugin = MockPlugin(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=False
        )
        with pytest.raises(SecurityValidationError) as exc_info:
            plugin.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)

        error_msg = str(exc_info.value)
        assert "frozen at SECRET" in error_msg

    def test_frozen_insufficient_clearance_rejected(self):
        """Frozen plugin still enforces insufficient clearance check."""
        plugin = MockPlugin(
            security_level=SecurityLevel.OFFICIAL,
            allow_downgrade=False
        )
        with pytest.raises(SecurityValidationError) as exc_info:
            plugin.validate_can_operate_at_level(SecurityLevel.SECRET)

        error_msg = str(exc_info.value)
        # Should get insufficient clearance error, not frozen error
        assert "Insufficient clearance" in error_msg


# ============================================================================
# PROPERTY-BASED TESTS (Coverage Matrix)
# ============================================================================


class TestPropertyBased:
    """Property-based tests covering all SecurityLevel combinations.

    Uses hypothesis to generate test cases for all possible combinations
    of plugin clearance levels and operating levels.
    """

    @pytest.mark.parametrize("plugin_level", [
        SecurityLevel.UNOFFICIAL,
        SecurityLevel.OFFICIAL,
        SecurityLevel.SECRET,
    ])
    @pytest.mark.parametrize("operating_level", [
        SecurityLevel.UNOFFICIAL,
        SecurityLevel.OFFICIAL,
        SecurityLevel.SECRET,
    ])
    def test_trusted_downgrade_matrix(self, plugin_level, operating_level):
        """Trusted downgrade: plugin can operate at same or lower level.

        Matrix of test cases:
        - Plugin level ≥ Operating level → ALLOW (same or downgrade)
        - Plugin level < Operating level → REJECT (insufficient clearance)
        """
        plugin = MockPlugin(security_level=plugin_level, allow_downgrade=True)

        if operating_level <= plugin_level:
            # Should succeed (same level or downgrade)
            plugin.validate_can_operate_at_level(operating_level)
        else:
            # Should fail (insufficient clearance)
            with pytest.raises(SecurityValidationError):
                plugin.validate_can_operate_at_level(operating_level)

    @pytest.mark.parametrize("plugin_level", [
        SecurityLevel.UNOFFICIAL,
        SecurityLevel.OFFICIAL,
        SecurityLevel.SECRET,
    ])
    @pytest.mark.parametrize("operating_level", [
        SecurityLevel.UNOFFICIAL,
        SecurityLevel.OFFICIAL,
        SecurityLevel.SECRET,
    ])
    def test_frozen_matrix(self, plugin_level, operating_level):
        """Frozen: plugin can ONLY operate at exact level.

        Matrix of test cases:
        - Plugin level == Operating level → ALLOW (exact match)
        - Plugin level != Operating level → REJECT (frozen or insufficient)
        """
        plugin = MockPlugin(security_level=plugin_level, allow_downgrade=False)

        if operating_level == plugin_level:
            # Should succeed (exact match)
            plugin.validate_can_operate_at_level(operating_level)
        else:
            # Should fail (frozen downgrade or insufficient clearance)
            with pytest.raises(SecurityValidationError):
                plugin.validate_can_operate_at_level(operating_level)


# ============================================================================
# EDGE CASES
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_unofficial_plugin_cannot_upgrade(self):
        """UNOFFICIAL plugin (lowest) cannot operate at higher levels."""
        plugin = MockPlugin(
            security_level=SecurityLevel.UNOFFICIAL,
            allow_downgrade=True
        )

        # Cannot operate at OFFICIAL (insufficient clearance)
        with pytest.raises(SecurityValidationError):
            plugin.validate_can_operate_at_level(SecurityLevel.OFFICIAL)

        # Cannot operate at SECRET (insufficient clearance)
        with pytest.raises(SecurityValidationError):
            plugin.validate_can_operate_at_level(SecurityLevel.SECRET)

    def test_secret_plugin_can_downgrade_to_all(self):
        """SECRET plugin (highest) can operate at all lower levels."""
        plugin = MockPlugin(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=True
        )

        # Can operate at all levels
        plugin.validate_can_operate_at_level(SecurityLevel.SECRET)
        plugin.validate_can_operate_at_level(SecurityLevel.OFFICIAL)
        plugin.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)

    def test_frozen_secret_plugin_only_at_secret(self):
        """Frozen SECRET plugin can ONLY operate at SECRET level."""
        plugin = MockPlugin(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=False
        )

        # Can operate at SECRET
        plugin.validate_can_operate_at_level(SecurityLevel.SECRET)

        # Cannot operate at OFFICIAL (frozen)
        with pytest.raises(SecurityValidationError):
            plugin.validate_can_operate_at_level(SecurityLevel.OFFICIAL)

        # Cannot operate at UNOFFICIAL (frozen)
        with pytest.raises(SecurityValidationError):
            plugin.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)


# ============================================================================
# ERROR MESSAGE QUALITY
# ============================================================================


class TestErrorMessages:
    """Test that error messages are clear and actionable."""

    def test_insufficient_clearance_error_message(self):
        """Insufficient clearance error provides clear guidance."""
        plugin = MockPlugin(
            security_level=SecurityLevel.OFFICIAL,
            allow_downgrade=True
        )

        with pytest.raises(SecurityValidationError) as exc_info:
            plugin.validate_can_operate_at_level(SecurityLevel.SECRET)

        error_msg = str(exc_info.value)
        # Should mention both levels
        assert "OFFICIAL" in error_msg
        assert "SECRET" in error_msg
        # Should mention Bell-LaPadula or insufficient clearance
        assert ("Insufficient clearance" in error_msg or "Bell-LaPadula" in error_msg)

    def test_frozen_downgrade_error_message(self):
        """Frozen downgrade error provides clear guidance."""
        plugin = MockPlugin(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=False
        )

        with pytest.raises(SecurityValidationError) as exc_info:
            plugin.validate_can_operate_at_level(SecurityLevel.OFFICIAL)

        error_msg = str(exc_info.value)
        # Should mention frozen status
        assert "frozen" in error_msg
        # Should mention allow_downgrade=False
        assert "allow_downgrade=False" in error_msg
        # Should mention both levels
        assert "SECRET" in error_msg
        assert "OFFICIAL" in error_msg
        # Should mention exact matching requirement
        assert "exact" in error_msg


# ============================================================================
# TEST SUMMARY
# ============================================================================


"""
Test Coverage Summary:

Default Trusted Downgrade (5 tests):
- default_parameter_is_true
- trusted_downgrade_to_lower_level
- trusted_downgrade_to_lowest_level
- exact_match_allowed
- insufficient_clearance_rejected

Frozen Plugin (5 tests):
- frozen_property_reflects_parameter
- frozen_exact_match_allowed
- frozen_downgrade_rejected
- frozen_two_level_downgrade_rejected
- frozen_insufficient_clearance_rejected

Property-Based (18 parameterized tests):
- trusted_downgrade_matrix (3×3 = 9 combinations)
- frozen_matrix (3×3 = 9 combinations)

Edge Cases (3 tests):
- unofficial_plugin_cannot_upgrade
- secret_plugin_can_downgrade_to_all
- frozen_secret_plugin_only_at_secret

Error Messages (2 tests):
- insufficient_clearance_error_message
- frozen_downgrade_error_message

TOTAL: 33 test cases
"""
