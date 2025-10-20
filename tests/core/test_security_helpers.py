from __future__ import annotations

import pytest

from elspeth.core.security import (
    SECURITY_LEVELS,
    coalesce_determinism_level,
    coalesce_security_level,
    is_security_level_allowed,
    normalize_determinism_level,
    normalize_security_level,
    resolve_determinism_level,
    resolve_security_level,
)


def test_normalize_security_level_aliases_and_canonical_values():
    # Aliases map to PSPF canonical strings
    assert normalize_security_level("internal") == "OFFICIAL"
    assert normalize_security_level("public") == "UNOFFICIAL"
    # Already canonical strings remain unchanged (case-insensitive input)
    assert normalize_security_level("official") == "OFFICIAL"
    assert normalize_security_level("PROTECTED") == "PROTECTED"


def test_is_security_level_allowed_hierarchy():
    # OFFICIAL data is allowed at OFFICIAL and above
    assert is_security_level_allowed("OFFICIAL", "OFFICIAL") is True
    assert is_security_level_allowed("OFFICIAL", "PROTECTED") is True
    # PROTECTED data is not allowed at OFFICIAL
    assert is_security_level_allowed("PROTECTED", "OFFICIAL") is False


def test_resolve_security_level_picks_most_restrictive():
    # Most restrictive wins among provided levels
    assert resolve_security_level("OFFICIAL", "PROTECTED") == "PROTECTED"
    assert resolve_security_level("UNOFFICIAL", "OFFICIAL") == "OFFICIAL"
    # When nothing provided, default to least restrictive entry in SECURITY_LEVELS
    assert resolve_security_level() == SECURITY_LEVELS[0]


def test_coalesce_security_level_agrees_or_raises():
    # Matching inputs -> normalized canonical string
    assert coalesce_security_level("internal", "OFFICIAL") == "OFFICIAL"
    # Conflicting inputs -> error
    with pytest.raises(ValueError):
        coalesce_security_level("OFFICIAL", "PROTECTED")
    # No inputs -> error
    with pytest.raises(ValueError):
        coalesce_security_level(None, None)


def test_determinism_normalize_resolve_and_coalesce():
    assert normalize_determinism_level("HIGH") == "high"
    assert resolve_determinism_level("guaranteed", "high") == "high"  # least deterministic wins
    assert coalesce_determinism_level("guaranteed", "GUARANTEED") == "guaranteed"
    with pytest.raises(ValueError):
        coalesce_determinism_level(None, None)

