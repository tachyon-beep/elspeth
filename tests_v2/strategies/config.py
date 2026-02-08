# tests_v2/strategies/config.py
"""Strategies for configuration values (retry, settings)."""

from hypothesis import strategies as st

# Valid retry attempt counts
valid_max_attempts = st.integers(min_value=1, max_value=100)

# Valid delay values (positive floats, reasonable bounds)
valid_delays = st.floats(
    min_value=0.001, max_value=3600.0, allow_nan=False, allow_infinity=False
)

# Valid jitter values (non-negative)
valid_jitter = st.floats(
    min_value=0.0, max_value=60.0, allow_nan=False, allow_infinity=False
)
