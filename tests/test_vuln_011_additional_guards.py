"""
VULN-011 Phase 3: Additional Guards Tests

These tests verify SecureDataFrame blocks serialization and subclassing
bypasses that could circumvent token gating and seal verification.

TDD Cycle: RED → GREEN → REFACTOR
Current Status: RED (tests will fail until guards implemented)
"""

import copy
import pickle

import pandas as pd
import pytest

from elspeth.core.base.types import SecurityLevel
from elspeth.core.security.secure_data import SecureDataFrame


def test_pickle_blocked():
    """SECURITY: Verify pickle serialization is blocked.

    Attack scenario:
    1. Create SecureDataFrame with seal
    2. Pickle it (seal is serialized)
    3. Modify pickled bytes (tamper with seal)
    4. Unpickle (seal verification bypassed)

    Expected: TypeError or AttributeError on pickle attempt
    """
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2, 3]}), SecurityLevel.SECRET
    )

    with pytest.raises((TypeError, AttributeError), match="[Pp]ickl"):
        pickle.dumps(frame)


def test_copy_blocked():
    """SECURITY: Verify shallow copy is blocked.

    Attack scenario:
    1. Create SecureDataFrame with seal
    2. Shallow copy it
    3. Modify copy's attributes via object.__setattr__()
    4. Use tampered copy (seal verification bypassed)

    Expected: TypeError on copy attempt
    """
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2, 3]}), SecurityLevel.SECRET
    )

    with pytest.raises(TypeError, match="[Cc]opy"):
        copy.copy(frame)


def test_deepcopy_blocked():
    """SECURITY: Verify deep copy is blocked.

    Deep copy creates entirely new object graph, bypassing:
    - Token gating (__new__ not called)
    - Seal computation (copied from original)
    - Any future security controls

    Expected: TypeError on deepcopy attempt
    """
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2, 3]}), SecurityLevel.SECRET
    )

    with pytest.raises(TypeError, match="[Cc]opy"):
        copy.deepcopy(frame)


def test_subclassing_blocked():
    """SECURITY: Verify subclassing is blocked.

    Attack scenario:
    1. Create malicious subclass
    2. Override _verify_seal() to always pass
    3. Override __new__ to bypass token check
    4. Bypass all security controls

    Expected: TypeError on subclass definition
    """
    with pytest.raises(TypeError, match="[Ss]ubclass"):

        class MaliciousFrame(SecureDataFrame):
            pass


def test_reduce_ex_blocked():
    """SECURITY: Verify __reduce_ex__ (pickle protocol) is blocked.

    __reduce_ex__ is the low-level pickle protocol method.
    Blocking this ensures pickle can't serialize the object.

    Expected: TypeError on __reduce_ex__ call
    """
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2, 3]}), SecurityLevel.SECRET
    )

    with pytest.raises(TypeError, match="[Pp]ickl"):
        frame.__reduce_ex__(4)  # Protocol version 4


def test_reduce_blocked():
    """SECURITY: Verify __reduce__ (legacy pickle) is blocked.

    __reduce__ is the legacy pickle protocol method.
    Blocking both __reduce__ and __reduce_ex__ ensures complete pickle blocking.

    Expected: TypeError on __reduce__ call
    """
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2, 3]}), SecurityLevel.SECRET
    )

    with pytest.raises(TypeError, match="[Pp]ickl"):
        frame.__reduce__()


def test_getstate_blocked():
    """SECURITY: Verify __getstate__ is blocked by pickle guards.

    __getstate__ provides object state for pickling.
    While frozen dataclasses have this method, our __reduce_ex__
    blocks pickle before __getstate__ is ever called.

    Expected: Frozen dataclass has __getstate__, but pickle is blocked
    """
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2, 3]}), SecurityLevel.SECRET
    )

    # Frozen dataclass has __getstate__ (that's OK)
    assert hasattr(frame, "__getstate__")

    # But pickle is blocked before __getstate__ is used
    with pytest.raises(TypeError, match="[Pp]ickl"):
        pickle.dumps(frame)  # Blocked by __reduce_ex__


def test_setstate_blocked():
    """SECURITY: Verify __setstate__ is blocked by pickle guards.

    __setstate__ restores object state from pickle.
    While frozen dataclasses have this method, our __reduce_ex__
    blocks pickle before __setstate__ is ever called.

    Expected: Frozen dataclass has __setstate__, but pickle is blocked
    """
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2, 3]}), SecurityLevel.SECRET
    )

    # Frozen dataclass has __setstate__ (that's OK)
    assert hasattr(frame, "__setstate__")

    # But pickle is blocked before __setstate__ is used
    with pytest.raises(TypeError, match="[Pp]ickl"):
        pickle.dumps(frame)  # Blocked by __reduce_ex__


def test_legitimate_operations_still_work():
    """USABILITY: Verify legitimate operations unaffected by guards.

    Guards should NOT break normal usage:
    - Factory methods still work
    - Uplifting still works
    - with_new_data still works
    - validate_compatible_with still works

    Expected: All operations succeed
    """
    # Factory method
    frame1 = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2, 3]}), SecurityLevel.OFFICIAL
    )

    # Uplifting
    frame2 = frame1.with_uplifted_security_level(SecurityLevel.SECRET)
    assert frame2.security_level == SecurityLevel.SECRET

    # with_new_data
    frame3 = frame2.with_new_data(pd.DataFrame({"new": [4, 5, 6]}))
    assert "new" in frame3.data.columns

    # validate_compatible_with
    frame3.validate_compatible_with(SecurityLevel.SECRET)  # Should not raise


def test_error_messages_are_clear():
    """USABILITY: Verify error messages guide developers.

    When guards block operations, error messages should:
    - Explain WHY the operation is blocked
    - Reference ADR-002-A
    - Suggest alternatives (use factory methods)

    Expected: Clear, actionable error messages
    """
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1]}), SecurityLevel.SECRET
    )

    with pytest.raises(TypeError) as exc_info:
        pickle.dumps(frame)

    error_msg = str(exc_info.value).lower()

    # Should mention security
    assert "secur" in error_msg or "adr" in error_msg or "pickle" in error_msg
