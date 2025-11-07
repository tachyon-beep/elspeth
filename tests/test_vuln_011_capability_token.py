"""
VULN-011 Phase 1: Capability Token Gating Tests

These tests verify that SecureDataFrame construction is gated behind
a module-private capability token, replacing fragile stack inspection.

TDD Cycle: RED → GREEN → REFACTOR
Current Status: RED (tests will fail until token gating implemented)
"""

import pandas as pd
import pytest

from elspeth.core.base.types import SecurityLevel
from elspeth.core.security.secure_data import SecureDataFrame
from elspeth.core.validation.base import SecurityValidationError


def test_direct_construction_blocked_without_token():
    """SECURITY: Verify direct __new__ blocked without token.

    Direct construction bypass would allow security level laundering:
    - Malicious plugins could create frames with arbitrary security levels
    - Bypasses uplifting logic (max() operation)
    - Breaks audit trail (no datasource provenance)

    Expected: SecurityValidationError with clear message referencing ADR-002-A
    """
    # Match both standalone ("authorized factory methods") and sidecar ("construction ticket") mode messages
    with pytest.raises(
        SecurityValidationError,
        match="(authorized factory methods|construction ticket)",
    ):
        # Attempt direct construction via __new__
        SecureDataFrame.__new__(SecureDataFrame)


def test_direct_init_blocked():
    """SECURITY: Verify direct dataclass construction blocked.

    Direct __init__ construction would bypass all security controls:
    - No datasource authorization check
    - No seal computation (Phase 2)
    - No audit trail

    Expected: SecurityValidationError during __init__
    """
    with pytest.raises(SecurityValidationError):
        SecureDataFrame(
            data=pd.DataFrame({"col": [1]}), security_level=SecurityLevel.SECRET
        )


def test_factory_method_succeeds_with_token():
    """SECURITY: Verify authorized factory can create instances.

    Factory methods must pass internal token to __new__ for authorization.
    This test ensures authorized paths still work after token gating.

    Expected: Successful creation, no errors
    """
    # Should not raise
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2, 3]}), SecurityLevel.OFFICIAL
    )
    assert frame.security_level == SecurityLevel.OFFICIAL
    assert len(frame.data) == 3


def test_with_uplifted_security_level_succeeds():
    """SECURITY: Verify uplifting method passes token correctly.

    with_uplifted_security_level() creates new instance internally.
    Must pass token to __new__ for authorization.

    Expected: Successful uplift, no errors
    """
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2, 3]}), SecurityLevel.OFFICIAL
    )

    uplifted = frame.with_uplifted_security_level(SecurityLevel.SECRET)
    assert uplifted.security_level == SecurityLevel.SECRET
    assert len(uplifted.data) == 3


def test_with_new_data_succeeds():
    """SECURITY: Verify with_new_data() method passes token correctly.

    with_new_data() replaces DataFrame while preserving security metadata.
    Must pass token to __new__ for authorization.

    Expected: Successful data replacement, security level preserved
    """
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2, 3]}), SecurityLevel.OFFICIAL
    )

    new_frame = frame.with_new_data(pd.DataFrame({"new_col": [4, 5]}))
    assert new_frame.security_level == SecurityLevel.OFFICIAL  # Preserved
    assert "new_col" in new_frame.data.columns
    assert len(new_frame.data) == 2


def test_token_not_guessable():
    """SECURITY: Verify token cannot be guessed or forged.

    Token should have:
    - 256-bit entropy (secrets.token_bytes(32))
    - Module-private scope (not exported)
    - Process-local (new token per process)

    This test documents expected properties (not testable directly).
    """
    # Token lives in module closure, not accessible externally
    # This test serves as documentation of security properties
    pass


def test_error_message_references_adr():
    """USABILITY: Verify error message guides developers to correct pattern.

    When construction fails, error should:
    - Reference ADR-002-A
    - Suggest authorized factory methods
    - Explain WHY direct construction is blocked

    Expected: Clear, actionable error message
    """
    with pytest.raises(
        SecurityValidationError,
        match="create_from_datasource",  # Error message mentions factory method
    ):
        SecureDataFrame(
            data=pd.DataFrame({"col": [1]}), security_level=SecurityLevel.SECRET
        )


def test_subclass_construction_also_blocked():
    """SECURITY: Verify subclassing doesn't bypass token gating.

    Even if subclassing is allowed (blocked in Phase 3), subclass
    construction must still go through token gating.

    Expected: SecurityValidationError even for subclasses
    """
    # Note: Phase 3 will add __init_subclass__ to prevent subclassing entirely
    # This test documents that token gating catches subclass attempts

    # Attempt to create subclass (will be blocked in Phase 3, but test token now)
    try:

        class MaliciousSubclass(SecureDataFrame):
            pass

        with pytest.raises(SecurityValidationError):
            MaliciousSubclass(
                data=pd.DataFrame({"col": [1]}), security_level=SecurityLevel.SECRET
            )
    except TypeError:
        # Phase 3 will block subclassing entirely - that's fine too
        pytest.skip("Subclassing already blocked (Phase 3 implemented)")
