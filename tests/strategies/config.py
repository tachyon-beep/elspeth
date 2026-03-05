# tests/strategies/config.py
"""Strategies for configuration values (retry, settings)."""

from hypothesis import strategies as st

# Valid retry attempt counts
valid_max_attempts = st.integers(min_value=1, max_value=100)

# Valid base_delay values (>= 0.01 per RuntimeRetryConfig.__post_init__)
valid_base_delays = st.floats(min_value=0.01, max_value=3600.0, allow_nan=False, allow_infinity=False)

# Valid max_delay values (>= 0.1 per RuntimeRetryConfig.__post_init__)
valid_max_delays = st.floats(min_value=0.1, max_value=3600.0, allow_nan=False, allow_infinity=False)

# Legacy alias — prefer the specific strategies above
valid_delays = valid_base_delays

# Valid jitter values (non-negative)
valid_jitter = st.floats(min_value=0.0, max_value=60.0, allow_nan=False, allow_infinity=False)
