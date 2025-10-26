from __future__ import annotations

import pytest

from elspeth.core.base.types import DeterminismLevel, SecurityLevel, SecurityLevel
from elspeth.core.security import ensure_determinism_level, ensure_security_level
from elspeth.core.security import (
    coalesce_determinism_level,
    coalesce_security_level,
    is_security_level_allowed,
    resolve_determinism_level,
    resolve_security_level,
)


def test_security_level_aliases_and_canonical_values():
    # Aliases map to PSPF canonical enums/strings
    assert ensure_security_level("internal") == SecurityLevel.OFFICIAL
    assert ensure_security_level("public") == SecurityLevel.UNOFFICIAL
    # Already canonical strings remain unchanged (case-insensitive input)
    assert ensure_security_level("official") == SecurityLevel.OFFICIAL
    assert ensure_security_level("PROTECTED") == SecurityLevel.PROTECTED


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
    assert ensure_determinism_level("HIGH") == DeterminismLevel.HIGH
    assert resolve_determinism_level("guaranteed", "high") == DeterminismLevel.HIGH  # least deterministic wins
    assert coalesce_determinism_level("guaranteed", "GUARANTEED") == DeterminismLevel.GUARANTEED
    with pytest.raises(ValueError):
        coalesce_determinism_level(None, None)
