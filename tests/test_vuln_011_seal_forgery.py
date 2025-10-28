"""
VULN-011 P0 Critical: Seal Forgery via Exposed _compute_seal()

Demonstrates P0 vulnerability where exposing _compute_seal() as @staticmethod
allows untrusted plugins to forge valid seals after tampering.

Attack Vector:
1. Get SECRET frame
2. Use object.__setattr__() to downgrade security_level to UNOFFICIAL
3. Use SecureDataFrame._compute_seal() to forge valid seal for downgraded level
4. Use object.__setattr__() to install forged seal
5. Validation succeeds (seal matches tampered state)
6. RESULT: Tamper-evident seal completely bypassed

TDD Cycle: RED → GREEN
Current Status: RED (demonstrates vulnerability exists)
"""

import pandas as pd
import pytest

from elspeth.core.base.types import SecurityLevel
from elspeth.core.security.secure_data import SecureDataFrame
from elspeth.core.validation.base import SecurityValidationError


def test_seal_forgery_via_exposed_compute_seal():
    """SECURITY: Verify _compute_seal() cannot be used to forge valid seals.

    Attack scenario:
    1. Create SECRET frame
    2. Downgrade security_level to UNOFFICIAL via object.__setattr__()
    3. Forge valid seal using exposed SecureDataFrame._compute_seal()
    4. Install forged seal via object.__setattr__()
    5. validate_compatible_with() succeeds (seal matches tampered state)

    Expected: Either _compute_seal() not accessible, or forgery detected
    """
    # Create legitimate SECRET frame
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"secret_data": ["classified"]}), SecurityLevel.SECRET
    )

    # ATTACK Phase 1: Downgrade security level
    object.__setattr__(frame, "security_level", SecurityLevel.UNOFFICIAL)

    # ATTACK Phase 2: Forge valid seal for downgraded level
    # BUG: _compute_seal() is exposed as @staticmethod, allowing forgery
    try:
        forged_seal = SecureDataFrame._compute_seal(frame.data, SecurityLevel.UNOFFICIAL)

        # ATTACK Phase 3: Install forged seal
        object.__setattr__(frame, "_seal", forged_seal)

        # ATTACK Phase 4: Validation should FAIL but might succeed with forged seal
        # Expected behavior after fix: Should raise SecurityValidationError
        with pytest.raises(SecurityValidationError, match="[Tt]amper"):
            frame.validate_compatible_with(SecurityLevel.UNOFFICIAL)

    except AttributeError:
        # GOOD: _compute_seal() not accessible after fix
        pytest.skip("_compute_seal() correctly not accessible (fix applied)")


def test_seal_forgery_with_data_swap():
    """SECURITY: Verify forged seals don't work for data swapping.

    Attack scenario variant:
    1. Create SECRET frame with sensitive data
    2. Swap data to public data via object.__setattr__()
    3. Forge valid seal for swapped data
    4. Try to access as if legitimate

    Expected: Forgery not possible or detected
    """
    secret_data = pd.DataFrame({"secret": ["classified"]})
    public_data = pd.DataFrame({"public": ["unclassified"]})

    frame = SecureDataFrame.create_from_datasource(secret_data, SecurityLevel.SECRET)

    # ATTACK Phase 1: Swap data
    object.__setattr__(frame, "data", public_data)

    # ATTACK Phase 2: Forge seal for swapped data
    try:
        forged_seal = SecureDataFrame._compute_seal(public_data, SecurityLevel.SECRET)
        object.__setattr__(frame, "_seal", forged_seal)

        # ATTACK Phase 3: Validation should fail
        with pytest.raises(SecurityValidationError, match="[Tt]amper"):
            frame.validate_compatible_with(SecurityLevel.SECRET)

    except AttributeError:
        # GOOD: _compute_seal() not accessible after fix
        pytest.skip("_compute_seal() correctly not accessible (fix applied)")


def test_legitimate_seal_recomputation_via_factory_methods():
    """USABILITY: Verify legitimate seal updates still work.

    Factory methods must still be able to compute seals internally.
    This test ensures the fix doesn't break legitimate operations.

    Expected: Factory methods work, external forgery blocked
    """
    # Factory method should work (internal seal computation)
    frame1 = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"data": [1, 2, 3]}), SecurityLevel.OFFICIAL
    )

    # Uplifting should work (internal seal recomputation)
    frame2 = frame1.with_uplifted_security_level(SecurityLevel.SECRET)
    assert frame2.security_level == SecurityLevel.SECRET

    # with_new_data should work (internal seal recomputation)
    frame3 = frame2.with_new_data(pd.DataFrame({"new": [4, 5, 6]}))
    assert "new" in frame3.data.columns

    # All operations should succeed (legitimate seal updates)


def test_compute_seal_not_accessible_from_plugins():
    """SECURITY: Verify _compute_seal() not accessible to plugin code.

    After fix, attempting to access _compute_seal() should either:
    1. Raise AttributeError (method doesn't exist on class)
    2. Raise TypeError (method requires internal token)

    Expected: Plugin code cannot call seal computation
    """
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"data": [1]}), SecurityLevel.OFFICIAL
    )

    # Attempt to access _compute_seal() as plugin would
    with pytest.raises((AttributeError, TypeError)):
        SecureDataFrame._compute_seal(frame.data, SecurityLevel.OFFICIAL)


def test_seal_key_remains_module_private():
    """SECURITY: Verify seal key is NOT accessible via import (CVE-ADR-002-A-008).

    After closure encapsulation, _SEAL_KEY must NOT exist as module attribute.
    This prevents plugins from importing and using it to forge seals.

    Expected: Module attribute does NOT exist, but seals still work (closure-based)
    """
    import elspeth.core.security.secure_data as module

    # CRITICAL: _SEAL_KEY should NOT be importable (closure-encapsulated)
    assert not hasattr(module, "_SEAL_KEY"), (
        "_SEAL_KEY is accessible via import! This allows seal forgery. "
        "CVE-ADR-002-A-008: Seal key must be closure-encapsulated."
    )

    # But seal computation should still work (via closure)
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"data": [1]}), SecurityLevel.OFFICIAL
    )
    # If seal computation failed, create_from_datasource would have raised
    assert frame.security_level == SecurityLevel.OFFICIAL


def test_error_message_guides_developers():
    """USABILITY: Verify error messages explain seal computation is internal.

    When developers try to access _compute_seal(), error should guide them
    to use factory methods instead.

    Expected: Clear error message on attempted access
    """
    with pytest.raises((AttributeError, TypeError)) as exc_info:
        SecureDataFrame._compute_seal(pd.DataFrame(), SecurityLevel.OFFICIAL)

    # Error message should indicate method not available or internal-only
    # (Specific message depends on implementation approach)
