# tests/strategies/ids.py
"""Strategies for IDs, names, and labels used in ELSPETH pipelines."""

from hypothesis import strategies as st

# UUID-like hex strings
id_strings = st.text(
    min_size=8,
    max_size=40,
    alphabet="0123456789abcdef",
)

# Sink/node names (lowercase with underscores)
sink_names = st.text(
    min_size=1,
    max_size=30,
    alphabet="abcdefghijklmnopqrstuvwxyz_",
)

# Valid branch names for fork/coalesce
branch_names = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
)

# List of unique branch names (for fork operations)
unique_branches = st.lists(branch_names, min_size=1, max_size=5, unique=True)

# Multiple branches (at least 2, for testing fork behavior)
multiple_branches = st.lists(branch_names, min_size=2, max_size=5, unique=True)

# Path/label names (for routing)
path_names = st.text(
    min_size=1,
    max_size=30,
    alphabet="abcdefghijklmnopqrstuvwxyz_0123456789",
).filter(lambda s: s[0].isalpha())
