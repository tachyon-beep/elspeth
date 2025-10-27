"""VULN-009: SecureDataFrame Immutability Bypass via __dict__ Manipulation

SECURITY VULNERABILITY (CVSS 9.1 CRITICAL):
    Python frozen dataclasses prevent attribute assignment via __setattr__,
    but attackers can bypass this by directly manipulating __dict__, enabling
    classification laundering attacks that defeat the ADR-002-A security model.

Attack Scenario:
    1. Create SECRET-classified data
    2. Bypass frozen check via frame.__dict__['security_level'] = UNOFFICIAL
    3. Validation doesn't detect modification
    4. SECRET data processed as UNOFFICIAL → classification breach

Fix:
    Add slots=True to @dataclass decorator to eliminate __dict__ entirely.

Test-Driven Development:
    This test is written FIRST (RED state) to demonstrate the vulnerability.
    It WILL FAIL until slots=True is added to SecureDataFrame.

Expected Behavior After Fix:
    Attempting __dict__ access should raise AttributeError because
    __dict__ doesn't exist when slots=True is enabled.
"""

import pandas as pd
import pytest

from elspeth.core.base.types import SecurityLevel
from elspeth.core.security.secure_data import SecureDataFrame


def test_secure_dataframe_dict_manipulation_blocked():
    """SECURITY: Verify __dict__ bypass impossible with slots=True.

    VULN-009: Python frozen dataclasses prevent __setattr__ but NOT __dict__ access.
    This test verifies that __dict__ manipulation is blocked by slots=True.

    Attack Vector (BEFORE fix):
        frame.__dict__['security_level'] = SecurityLevel.UNOFFICIAL
        # ✅ SUCCEEDS - Classification laundering attack

    Defense (AFTER fix with slots=True):
        frame.__dict__['security_level'] = SecurityLevel.UNOFFICIAL
        # ❌ AttributeError: 'SecureDataFrame' object has no attribute '__dict__'

    Expected State: WILL FAIL (RED) until slots=True added to SecureDataFrame.
    """
    # Arrange - Create SECRET-classified data
    data = pd.DataFrame({"col": [1, 2, 3]})
    frame = SecureDataFrame.create_from_datasource(
        data=data,
        security_level=SecurityLevel.SECRET
    )

    # Act & Assert - Attempt __dict__ bypass should raise AttributeError
    # (no __dict__ exists when slots=True is enabled)
    with pytest.raises(
        AttributeError,
        match=r"'SecureDataFrame' object has no attribute '__dict__'"
    ):
        frame.__dict__['security_level'] = SecurityLevel.UNOFFICIAL

    # Verify - Classification unchanged (should still be SECRET)
    assert frame.security_level == SecurityLevel.SECRET


def test_classification_laundering_attack_blocked_end_to_end():
    """SECURITY: Verify end-to-end classification laundering attack blocked.

    This test demonstrates the full attack scenario from the security audit:
        1. Load SECRET data
        2. Attempt __dict__ bypass to downgrade to UNOFFICIAL
        3. Verify attack blocked (AttributeError)
        4. Verify classification remains SECRET

    Expected State: WILL FAIL (RED) until slots=True added to SecureDataFrame.
    """
    # Step 1: Create SECRET data (trusted datasource)
    secret_data = pd.DataFrame({
        "classified_info": ["SECRET-001", "SECRET-002", "SECRET-003"]
    })
    secret_frame = SecureDataFrame.create_from_datasource(
        data=secret_data,
        security_level=SecurityLevel.SECRET
    )

    # Step 2: ATTACK - Attempt to downgrade classification via __dict__ bypass
    # This should raise AttributeError (no __dict__ exists with slots=True)
    with pytest.raises(AttributeError, match="__dict__"):
        secret_frame.__dict__['security_level'] = SecurityLevel.UNOFFICIAL

    # Step 3: Verify attack blocked - classification unchanged
    assert secret_frame.security_level == SecurityLevel.SECRET

    # Step 4: Verify data integrity maintained
    assert len(secret_frame.data) == 3
    assert "classified_info" in secret_frame.data.columns


def test_secure_dataframe_has_slots_not_dict():
    """SECURITY: Verify SecureDataFrame uses __slots__ instead of __dict__.

    This is a structural test verifying that the fix (slots=True) is applied.
    SecureDataFrame should use C-level slots for attribute storage, not __dict__.

    Expected State: WILL FAIL (RED) until slots=True added to SecureDataFrame.
    """
    # Arrange - Create any SecureDataFrame instance
    data = pd.DataFrame({"test": [1]})
    frame = SecureDataFrame.create_from_datasource(
        data=data,
        security_level=SecurityLevel.UNOFFICIAL
    )

    # Act & Assert - Verify __slots__ exists and __dict__ doesn't
    assert hasattr(SecureDataFrame, '__slots__'), (
        "SecureDataFrame must use __slots__ (add slots=True to @dataclass)"
    )

    with pytest.raises(AttributeError, match="__dict__"):
        _ = frame.__dict__  # Should raise AttributeError
