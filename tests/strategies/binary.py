# tests/strategies/binary.py
"""Binary data strategies for payload store testing."""

from hypothesis import strategies as st

# Arbitrary binary content
binary_content = st.binary(min_size=0, max_size=10_000)

# Non-empty binary (most realistic for actual payloads)
nonempty_binary = st.binary(min_size=1, max_size=10_000)

# Small binary for fast tests
small_binary = st.binary(min_size=1, max_size=1000)
