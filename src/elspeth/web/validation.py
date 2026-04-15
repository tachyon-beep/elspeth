"""Shared input validation utilities for the web layer.

Unicode visibility checks are used by both auth models (identity validation)
and secret schemas (invisible-value rejection).  Keeping them in one place
prevents the two definitions from drifting apart.
"""

from __future__ import annotations

import unicodedata

# Major Unicode categories that produce visible glyphs.  A string composed
# entirely of characters outside these categories (whitespace, control chars,
# zero-width joiners, format chars, etc.) is "invisible" and rejected.
#
# "M" (Mark/combining) is excluded — combining marks modify a base character
# but a string of only combining marks has no visible base and should be
# rejected.
_VISIBLE_CATEGORIES = frozenset({"L", "N", "P", "S"})


def has_visible_content(s: str) -> bool:
    """Return True if *s* contains at least one visible character.

    Catches zero-width spaces (U+200B), BOM (U+FEFF), soft hyphens,
    and other invisible characters that ``str.strip()`` does not remove.
    """
    return any(unicodedata.category(c)[0] in _VISIBLE_CATEGORIES for c in s)
