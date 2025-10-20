from __future__ import annotations

import pytest

from elspeth.core.base.types import DeterminismLevel, SecurityLevel
from elspeth.core.security import (
    coalesce_determinism_level,
    coalesce_security_level,
    is_security_level_allowed,
    resolve_determinism_level,
    resolve_security_level,
)


def test_security_level_from_string_aliases_and_canonical_values():
    # Aliases map to PSPF canonical enums/strings
    assert SecurityLevel.from_string("internal") == SecurityLevel.OFFICIAL
    assert SecurityLevel.from_string("public") == SecurityLevel.UNOFFICIAL
    # Already canonical strings remain unchanged (case-insensitive input)
    assert SecurityLevel.from_string("official") == SecurityLevel.OFFICIAL
    assert SecurityLevel.from_string("PROTECTED") == SecurityLevel.PROTECTED


def test_is_security_level_allowed_hierarchy():
    # OFFICIAL data is allowed at OFFICIAL and above
    assert is_security_level_allowed("OFFICIAL", "OFFICIAL") is True
    assert is_security_level_allowed("OFFICIAL", "PROTECTED") is True
    # PROTECTED data is not allowed at OFFICIAL
    assert is_security_level_allowed("PROTECTED", "OFFICIAL") is False


def test_resolve_security_level_picks_most_restrictive():
    # Most restrictive wins among provided levels
    assert resolve_security_level("OFFICIAL", "PROTECTED") == SecurityLevel.PROTECTED
    assert resolve_security_level("UNOFFICIAL", "OFFICIAL") == SecurityLevel.OFFICIAL
    # When nothing provided, default to least restrictive
    assert resolve_security_level() == SecurityLevel.UNOFFICIAL


def test_coalesce_security_level_agrees_or_raises():
    # Matching inputs -> normalized canonical string
    assert coalesce_security_level("internal", "OFFICIAL") == "OFFICIAL"
    # Conflicting inputs -> error
    with pytest.raises(ValueError):
        coalesce_security_level("OFFICIAL", "PROTECTED")
    # No inputs -> error
    with pytest.raises(ValueError):
        coalesce_security_level(None, None)


def test_determinism_resolve_and_coalesce():
    assert DeterminismLevel.from_string("HIGH") == DeterminismLevel.HIGH
    assert resolve_determinism_level("guaranteed", "high") == DeterminismLevel.HIGH  # least deterministic wins
    assert coalesce_determinism_level("guaranteed", "GUARANTEED") == DeterminismLevel.GUARANTEED
    with pytest.raises(ValueError):
        coalesce_determinism_level(None, None)
