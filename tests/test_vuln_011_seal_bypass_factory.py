"""
VULN-011 Critical Fix: Seal Verification in Factory Methods

These tests demonstrate P0 vulnerabilities where the tamper-evident seal
can be bypassed by tampering before calling factory methods.

Attack Vector:
1. Create SECRET frame
2. Use object.__setattr__() to downgrade security_level to UNOFFICIAL
3. Call with_uplifted_security_level(UNOFFICIAL) or with_new_data()
4. Method reads tampered security_level WITHOUT verifying seal
5. Creates new "legitimate" frame with downgraded classification
6. Subsequent validate_compatible_with() calls succeed
7. Result: Tamper-evident seal completely bypassed

TDD Cycle: RED → GREEN
Current Status: RED (demonstrates vulnerability exists)
"""

import pandas as pd
import pytest

from elspeth.core.base.types import SecurityLevel
from elspeth.core.security.secure_data import SecureDataFrame
from elspeth.core.validation.base import SecurityValidationError


def test_uplift_detects_tampering_before_reading_security_level():
    """SECURITY: Verify with_uplifted_security_level() checks seal BEFORE reading security_level.

    Attack scenario:
    1. Create SECRET frame
    2. Tamper: downgrade security_level to UNOFFICIAL via object.__setattr__()
    3. Call with_uplifted_security_level(SecurityLevel.UNOFFICIAL)
    4. WITHOUT seal verification, max(UNOFFICIAL, UNOFFICIAL) = UNOFFICIAL
    5. Creates new "legitimate" UNOFFICIAL frame with matching seal
    6. Tamper-evident seal bypassed, classification laundered

    Expected: SecurityValidationError on step 3 (seal verification fails)
    """
    # Create legitimate SECRET frame
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"secret_data": ["classified"]}), SecurityLevel.SECRET
    )

    # ATTACK: Downgrade classification (bypass frozen dataclass)
    object.__setattr__(frame, "security_level", SecurityLevel.UNOFFICIAL)

    # Attempt to "uplift" using tampered value
    # BUG: If seal NOT verified first, this succeeds and creates UNOFFICIAL frame
    # FIX: Should raise SecurityValidationError (tamper detected)
    with pytest.raises(SecurityValidationError, match="[Tt]amper"):
        frame.with_uplifted_security_level(SecurityLevel.UNOFFICIAL)


def test_uplift_detects_tampering_even_with_higher_target():
    """SECURITY: Verify seal check happens even when uplifting to higher level.

    Attack scenario (variant):
    1. Create SECRET frame
    2. Tamper: downgrade to OFFICIAL
    3. Call with_uplifted_security_level(SecurityLevel.SECRET)
    4. max(OFFICIAL, SECRET) = SECRET, creates SECRET frame
    5. But this "legitimizes" a tampered container!

    Expected: SecurityValidationError on step 3 (seal verification fails)
    """
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"secret_data": ["classified"]}), SecurityLevel.SECRET
    )

    # ATTACK: Downgrade to OFFICIAL
    object.__setattr__(frame, "security_level", SecurityLevel.OFFICIAL)

    # Attempt to uplift to SECRET
    # Even though result would be SECRET, we should detect tampering FIRST
    with pytest.raises(SecurityValidationError, match="[Tt]amper"):
        frame.with_uplifted_security_level(SecurityLevel.SECRET)


def test_with_new_data_detects_tampering_before_reading_security_level():
    """SECURITY: Verify with_new_data() checks seal BEFORE reading security_level.

    Attack scenario:
    1. Create SECRET frame
    2. Tamper: downgrade security_level to UNOFFICIAL via object.__setattr__()
    3. Call with_new_data(new_df)
    4. WITHOUT seal verification, preserves tampered UNOFFICIAL level
    5. Creates new "legitimate" UNOFFICIAL frame with matching seal
    6. Tamper-evident seal bypassed, classification laundered

    Expected: SecurityValidationError on step 3 (seal verification fails)
    """
    # Create legitimate SECRET frame
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"secret_data": ["classified"]}), SecurityLevel.SECRET
    )

    # ATTACK: Downgrade classification
    object.__setattr__(frame, "security_level", SecurityLevel.UNOFFICIAL)

    # Attempt to replace data using tampered container
    # BUG: If seal NOT verified first, this succeeds and creates UNOFFICIAL frame
    # FIX: Should raise SecurityValidationError (tamper detected)
    with pytest.raises(SecurityValidationError, match="[Tt]amper"):
        frame.with_new_data(pd.DataFrame({"new_data": ["public"]}))


def test_with_new_data_detects_data_swap_tampering():
    """SECURITY: Verify with_new_data() detects data swapping before cloning.

    Attack scenario (variant):
    1. Create SECRET frame with DataFrame A
    2. Tamper: swap data reference to DataFrame B
    3. Call with_new_data(DataFrame C)
    4. Method should detect seal mismatch (data A vs B)

    Expected: SecurityValidationError on step 3 (seal verification fails)
    """
    original_data = pd.DataFrame({"secret": ["classified"]})
    swapped_data = pd.DataFrame({"swapped": ["different"]})

    frame = SecureDataFrame.create_from_datasource(
        original_data, SecurityLevel.SECRET
    )

    # ATTACK: Swap data reference
    object.__setattr__(frame, "data", swapped_data)

    # Attempt to create new frame from tampered container
    # Should detect seal mismatch (seal was computed for original_data)
    with pytest.raises(SecurityValidationError, match="[Tt]amper"):
        frame.with_new_data(pd.DataFrame({"new": ["data"]}))


def test_legitimate_uplift_still_works_after_fix():
    """USABILITY: Verify legitimate uplifting still works after adding seal checks.

    Seal verification should NOT break normal operations.

    Expected: Uplifting succeeds for untampered frames
    """
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"data": [1, 2, 3]}), SecurityLevel.OFFICIAL
    )

    # Should succeed (untampered frame)
    uplifted = frame.with_uplifted_security_level(SecurityLevel.SECRET)
    assert uplifted.security_level == SecurityLevel.SECRET
    assert len(uplifted.data) == 3


def test_legitimate_with_new_data_still_works_after_fix():
    """USABILITY: Verify legitimate with_new_data() still works after adding seal checks.

    Seal verification should NOT break normal operations.

    Expected: with_new_data() succeeds for untampered frames
    """
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"data": [1, 2, 3]}), SecurityLevel.OFFICIAL
    )

    # Should succeed (untampered frame)
    new_frame = frame.with_new_data(pd.DataFrame({"new": [4, 5, 6]}))
    assert new_frame.security_level == SecurityLevel.OFFICIAL  # Preserved
    assert "new" in new_frame.data.columns
    assert len(new_frame.data) == 3


def test_error_messages_reference_factory_methods():
    """USABILITY: Verify error messages guide developers to correct usage.

    When factory methods detect tampering, error messages should:
    - Indicate which method detected the tampering
    - Reference ADR-002-A
    - Explain WHY tampering is blocked

    Expected: Clear, actionable error messages
    """
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"data": [1]}), SecurityLevel.SECRET
    )

    # Tamper with security level
    object.__setattr__(frame, "security_level", SecurityLevel.UNOFFICIAL)

    # Verify error message is clear
    with pytest.raises(SecurityValidationError) as exc_info:
        frame.with_uplifted_security_level(SecurityLevel.UNOFFICIAL)

    error_msg = str(exc_info.value).lower()

    # Should mention tampering
    assert "tamper" in error_msg or "integrity" in error_msg
