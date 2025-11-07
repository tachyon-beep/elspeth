"""
VULN-011 CVE-ADR-002-A-008: Secret Import Prevention

These tests verify that closure encapsulation prevents plugins from
importing secrets needed to forge frames or seals.

Defense-in-Depth Layer:
- Primary: Positively audited plugins in secure environment
- Secondary (this): Closure encapsulation blocks casual secret access
- Tertiary: gc.get_referents() inspection still possible but detectable

Attack Vector (BLOCKED):
1. Import _CONSTRUCTION_TOKEN or _SEAL_KEY from secure_data module
2. Use SecureDataFrame.__new__(SecureDataFrame, _token=token) to bypass factory
3. Use forge seal with imported key to bypass tamper detection
4. Result: Complete security bypass

Expected: All import attempts raise AttributeError (secrets don't exist in module namespace)
"""

import pandas as pd
import pytest

from elspeth.core.base.types import SecurityLevel
from elspeth.core.security.secure_data import SecureDataFrame


def test_construction_token_not_importable():
    """SECURITY: Verify _CONSTRUCTION_TOKEN cannot be imported.

    Blocked Attack:
        from elspeth.core.security.secure_data import _CONSTRUCTION_TOKEN
        frame = SecureDataFrame.__new__(SecureDataFrame, _token=_CONSTRUCTION_TOKEN)
        # Bypass factory methods completely

    Expected: AttributeError (token doesn't exist in module namespace)
    """
    import elspeth.core.security.secure_data as module

    # CRITICAL: Token should NOT be importable
    assert not hasattr(module, "_CONSTRUCTION_TOKEN"), (
        "SECURITY VIOLATION: _CONSTRUCTION_TOKEN is importable! "
        "Attackers can bypass factory methods by calling "
        "__new__(SecureDataFrame, _token=imported_token). "
        "Token must be closure-encapsulated."
    )

    # Verify import attempt fails
    with pytest.raises(AttributeError, match="has no attribute.*CONSTRUCTION_TOKEN"):
        _ = module._CONSTRUCTION_TOKEN  # type: ignore[attr-defined]


def test_seal_key_not_importable():
    """SECURITY: Verify _SEAL_KEY cannot be imported.

    Blocked Attack:
        from elspeth.core.security.secure_data import _SEAL_KEY
        # Compute valid seal for tampered frame
        forged_seal = hashlib.blake2s(seal_input, key=_SEAL_KEY, digest_size=32).digest()
        # Bypass tamper detection

    Expected: AttributeError (key doesn't exist in module namespace)
    """
    import elspeth.core.security.secure_data as module

    # CRITICAL: Seal key should NOT be importable
    assert not hasattr(module, "_SEAL_KEY"), (
        "SECURITY VIOLATION: _SEAL_KEY is importable! "
        "Attackers can forge valid seals after tampering. "
        "Seal key must be closure-encapsulated."
    )

    # Verify import attempt fails
    with pytest.raises(AttributeError, match="has no attribute.*SEAL_KEY"):
        _ = module._SEAL_KEY  # type: ignore[attr-defined]


def test_module_dict_does_not_contain_secrets():
    """SECURITY: Verify module __dict__ doesn't expose secrets.

    Even if hasattr() passes, attackers might try module.__dict__ access.

    Expected: Neither secret appears in module dictionary
    """
    import elspeth.core.security.secure_data as module

    module_dict = module.__dict__

    assert "_CONSTRUCTION_TOKEN" not in module_dict, (
        "SECURITY VIOLATION: _CONSTRUCTION_TOKEN in module.__dict__! "
        "Accessible via module.__dict__['_CONSTRUCTION_TOKEN']."
    )

    assert "_SEAL_KEY" not in module_dict, (
        "SECURITY VIOLATION: _SEAL_KEY in module.__dict__! "
        "Accessible via module.__dict__['_SEAL_KEY']."
    )


def test_dir_does_not_list_secrets():
    """SECURITY: Verify dir() doesn't list secrets.

    Attackers might use dir() to discover available attributes.

    Expected: Neither secret appears in dir() output
    """
    import elspeth.core.security.secure_data as module

    module_attrs = dir(module)

    assert "_CONSTRUCTION_TOKEN" not in module_attrs, (
        "SECURITY VIOLATION: _CONSTRUCTION_TOKEN appears in dir(module)! "
        "Discoverable via introspection."
    )

    assert "_SEAL_KEY" not in module_attrs, (
        "SECURITY VIOLATION: _SEAL_KEY appears in dir(module)! "
        "Discoverable via introspection."
    )


def test_legitimate_operations_still_work():
    """USABILITY: Verify closure encapsulation doesn't break legitimate usage.

    Factory methods must still work (they access secrets via closure).

    Expected: All factory methods succeed
    """
    # Factory method should work (uses closure-encapsulated token)
    frame1 = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"data": [1, 2, 3]}), SecurityLevel.OFFICIAL
    )
    assert frame1.security_level == SecurityLevel.OFFICIAL

    # Uplifting should work (uses closure-encapsulated token and seal key)
    frame2 = frame1.with_uplifted_security_level(SecurityLevel.SECRET)
    assert frame2.security_level == SecurityLevel.SECRET

    # with_new_data should work (uses closure-encapsulated token and seal key)
    frame3 = frame2.with_new_data(pd.DataFrame({"new": [4, 5, 6]}))
    assert "new" in frame3.data.columns

    # Validation should work (uses closure-encapsulated seal key)
    frame3.validate_compatible_with(SecurityLevel.SECRET)


def test_bypass_attempt_with_wrong_token_fails():
    """SECURITY: Verify forged tokens don't work.

    Even if attacker guesses token format, it won't match closure-encapsulated value.

    Expected: SecurityValidationError (token verification fails)
    """
    from elspeth.core.validation.base import SecurityValidationError

    # Attacker tries to forge a token (256-bit like real token)
    import secrets

    forged_token = secrets.token_bytes(32)

    # Attempt to bypass factory with forged token
    # Match both standalone ("authorized factory methods") and sidecar ("construction ticket") mode messages
    with pytest.raises(SecurityValidationError, match="(authorized factory methods|construction ticket)"):
        SecureDataFrame.__new__(SecureDataFrame, _token=forged_token)


def test_bypass_attempt_with_none_token_fails():
    """SECURITY: Verify None token is rejected.

    Attacker might try passing _token=None to bypass check.

    Expected: SecurityValidationError (None not accepted)
    """
    from elspeth.core.validation.base import SecurityValidationError

    # Match both standalone ("authorized factory methods") and sidecar ("construction ticket") mode messages
    with pytest.raises(SecurityValidationError, match="(authorized factory methods|construction ticket)"):
        SecureDataFrame.__new__(SecureDataFrame, _token=None)


def test_bypass_attempt_without_token_fails():
    """SECURITY: Verify missing token is rejected.

    Attacker might try omitting _token parameter entirely.

    Expected: SecurityValidationError (defaults to None, rejected)
    """
    from elspeth.core.validation.base import SecurityValidationError

    # Match both standalone ("authorized factory methods") and sidecar ("construction ticket") mode messages
    with pytest.raises(SecurityValidationError, match="(authorized factory methods|construction ticket)"):
        SecureDataFrame.__new__(SecureDataFrame)
