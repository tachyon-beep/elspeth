"""
VULN-011 Phase 2: Tamper-Evident Seal Tests

These tests verify that SecureDataFrame has a tamper-evident seal that
detects unauthorized modification via object.__setattr__() bypass.

TDD Cycle: RED → GREEN → REFACTOR
Current Status: RED (tests will fail until seal implemented)
"""

import pandas as pd
import pytest

from elspeth.core.base.types import SecurityLevel
from elspeth.core.security.secure_data import SecureDataFrame
from elspeth.core.validation.base import SecurityValidationError


def test_seal_exists_after_construction():
    """SECURITY: Verify seal is computed and stored during construction.

    The seal protects against tampering even though dataclass is frozen.
    Frozen dataclass prevents casual assignment, but object.__setattr__()
    can still bypass it. Seal detects this bypass.

    Expected: Private _seal field exists with computed HMAC
    """
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2, 3]}), SecurityLevel.OFFICIAL
    )

    # Access private _seal field (testing only)
    seal = object.__getattribute__(frame, "_seal")

    # Seal should be non-empty bytes
    assert isinstance(seal, bytes)
    assert len(seal) > 0  # HMAC-BLAKE2s produces 32 bytes


def test_seal_changes_with_security_level():
    """SECURITY: Verify seal binds to security_level (prevents relabeling).

    Tampering attack: Attacker uses object.__setattr__() to change
    security_level from SECRET to OFFICIAL, bypassing immutability.

    Expected: Different security levels produce different seals
    """
    data = pd.DataFrame({"col": [1, 2, 3]})

    frame1 = SecureDataFrame.create_from_datasource(data, SecurityLevel.OFFICIAL)
    frame2 = SecureDataFrame.create_from_datasource(data, SecurityLevel.SECRET)

    seal1 = object.__getattribute__(frame1, "_seal")
    seal2 = object.__getattribute__(frame2, "_seal")

    # Same data, different security level → different seals
    assert seal1 != seal2


def test_seal_changes_with_data_identity():
    """SECURITY: Verify seal binds to DataFrame identity (prevents swapping).

    Tampering attack: Attacker uses object.__setattr__() to swap
    .data reference to different DataFrame, bypassing immutability.

    Expected: Different DataFrames produce different seals
    """
    frame1 = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2, 3]}), SecurityLevel.OFFICIAL
    )
    frame2 = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [4, 5, 6]}), SecurityLevel.OFFICIAL
    )

    seal1 = object.__getattribute__(frame1, "_seal")
    seal2 = object.__getattribute__(frame2, "_seal")

    # Different data, same security level → different seals
    assert seal1 != seal2


def test_tampering_detected_on_access():
    """SECURITY: Verify tampering detection on validate_compatible_with().

    Attack scenario:
    1. Create SECRET frame
    2. Use object.__setattr__() to change security_level to OFFICIAL
    3. Try to access via validate_compatible_with()

    Expected: SecurityValidationError with "tamper" in message
    """
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2, 3]}), SecurityLevel.SECRET
    )

    # Tamper: Downgrade security level (bypass frozen dataclass)
    object.__setattr__(frame, "security_level", SecurityLevel.OFFICIAL)

    # Attempt to use tampered frame
    with pytest.raises(SecurityValidationError, match="[Tt]amper"):
        frame.validate_compatible_with(SecurityLevel.OFFICIAL)


def test_data_swap_detected():
    """SECURITY: Verify data swapping is detected.

    Attack scenario:
    1. Create OFFICIAL frame with sensitive data
    2. Create OFFICIAL frame with public data
    3. Use object.__setattr__() to swap .data references
    4. Try to access swapped frame

    Expected: SecurityValidationError with "tamper" in message
    """
    sensitive_data = pd.DataFrame({"secret": ["classified"]})
    public_data = pd.DataFrame({"public": ["unclassified"]})

    frame_sensitive = SecureDataFrame.create_from_datasource(
        sensitive_data, SecurityLevel.SECRET
    )
    frame_public = SecureDataFrame.create_from_datasource(
        public_data, SecurityLevel.OFFICIAL
    )

    # Tamper: Swap data references (bypass frozen dataclass)
    original_data = frame_sensitive.data
    object.__setattr__(frame_sensitive, "data", frame_public.data)

    # Attempt to use tampered frame (seal should detect data swap)
    with pytest.raises(SecurityValidationError, match="[Tt]amper"):
        frame_sensitive.validate_compatible_with(SecurityLevel.SECRET)

    # Cleanup: restore original (for test hygiene)
    object.__setattr__(frame_sensitive, "data", original_data)


def test_legitimate_access_succeeds():
    """SECURITY: Verify legitimate access still works with seal validation.

    Seal verification should not break normal operations.
    This ensures seal is transparent to correct usage.

    Expected: validate_compatible_with() succeeds for untampered frame
    """
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2, 3]}), SecurityLevel.OFFICIAL
    )

    # Should not raise (untampered frame)
    frame.validate_compatible_with(SecurityLevel.OFFICIAL)
    frame.validate_compatible_with(SecurityLevel.SECRET)  # Higher clearance OK


def test_seal_recomputed_on_uplift():
    """SECURITY: Verify new seal computed when security level uplifted.

    When with_uplifted_security_level() creates new instance,
    new seal must be computed for new security level.

    Expected: Uplifted frame has different seal than original
    """
    frame1 = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2, 3]}), SecurityLevel.OFFICIAL
    )
    frame2 = frame1.with_uplifted_security_level(SecurityLevel.SECRET)

    seal1 = object.__getattribute__(frame1, "_seal")
    seal2 = object.__getattribute__(frame2, "_seal")

    # Uplifted security level → new seal
    assert seal1 != seal2


def test_seal_preserved_with_same_data():
    """SECURITY: Verify seal consistency for with_new_data().

    When with_new_data() replaces DataFrame but keeps security level,
    seal must be recomputed for new data identity.

    Expected: New data → new seal (even if same security level)
    """
    frame1 = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2, 3]}), SecurityLevel.OFFICIAL
    )
    frame2 = frame1.with_new_data(pd.DataFrame({"new": [4, 5, 6]}))

    seal1 = object.__getattribute__(frame1, "_seal")
    seal2 = object.__getattribute__(frame2, "_seal")

    # Different data identity → different seal
    assert seal1 != seal2


def test_seal_key_is_module_private():
    """SECURITY: Verify seal key is closure-encapsulated (CVE-ADR-002-A-008).

    The HMAC key should NOT be accessible as module attribute.
    This prevents plugins from importing the key and forging seals.

    Expected: Key does NOT exist as module attribute (closure-encapsulated)
    """
    import elspeth.core.security.secure_data as module

    # CRITICAL: _SEAL_KEY should NOT exist as module attribute
    assert not hasattr(module, "_SEAL_KEY"), (
        "_SEAL_KEY is accessible via import! This allows seal forgery. "
        "CVE-ADR-002-A-008: Seal key must be closure-encapsulated."
    )

    # Verify __all__ doesn't export it either (if __all__ is defined)
    if hasattr(module, "__all__"):
        assert "_SEAL_KEY" not in module.__all__, "_SEAL_KEY should not be in __all__"

    # Verify _CONSTRUCTION_TOKEN also not accessible (same fix)
    assert not hasattr(module, "_CONSTRUCTION_TOKEN"), (
        "_CONSTRUCTION_TOKEN is accessible via import! This allows bypass. "
        "CVE-ADR-002-A-008: Token must be closure-encapsulated."
    )


def test_error_message_is_security_conscious():
    """USABILITY: Verify tamper error doesn't leak seal internals.

    Error message should indicate tampering without revealing:
    - Seal value
    - HMAC algorithm details
    - Key material

    Expected: Generic "tamper detected" message
    """
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1]}), SecurityLevel.SECRET
    )

    # Tamper with security level
    object.__setattr__(frame, "security_level", SecurityLevel.OFFICIAL)

    with pytest.raises(SecurityValidationError) as exc_info:
        frame.validate_compatible_with(SecurityLevel.OFFICIAL)

    error_msg = str(exc_info.value).lower()

    # Should mention tampering
    assert "tamper" in error_msg

    # Should NOT leak seal internals
    assert "hmac" not in error_msg
    assert "blake2s" not in error_msg
    assert "_seal" not in error_msg
