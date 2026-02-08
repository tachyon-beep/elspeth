# tests_v2/strategies/external.py
"""Strategies for simulating external (Tier 3) data.

Generates messy headers, normalizable strings, and Python keywords
for testing ELSPETH's schema normalization at trust boundaries.
"""

import keyword

from hypothesis import strategies as st

# Messy headers from external systems (unicode, special chars, whitespace)
messy_headers = st.text(
    min_size=1,
    max_size=100,
    alphabet=st.characters(
        whitelist_categories=["L", "N", "P", "S", "Z"],
        blacklist_categories=["Cc"],
    ),
).filter(lambda s: any(c.isalnum() for c in s))

# Headers guaranteed to normalize to valid identifiers
normalizable_headers = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(whitelist_categories=["L", "N"]),
).filter(lambda s: s[0].isalpha() if s else False)

# Python keywords for collision handling tests
python_keywords = st.sampled_from(list(keyword.kwlist))
