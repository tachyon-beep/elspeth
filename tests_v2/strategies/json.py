# tests_v2/strategies/json.py
"""JSON-compatible Hypothesis strategies.

RFC 8785 (JCS) uses JavaScript-safe integers: -(2^53-1) to (2^53-1).
NaN/Infinity are strictly rejected by ELSPETH's canonical JSON.
"""

from hypothesis import strategies as st

MAX_SAFE_INT = 2**53 - 1
MIN_SAFE_INT = -(2**53 - 1)

# JSON-safe primitives (excluding NaN/Infinity which ELSPETH strictly rejects)
json_primitives = (
    st.none()
    | st.booleans()
    | st.integers(min_value=MIN_SAFE_INT, max_value=MAX_SAFE_INT)
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(max_size=100)
)

# Recursive strategy for nested JSON structures
json_values = st.recursive(
    json_primitives,
    lambda children: (
        st.lists(children, max_size=10)
        | st.dictionaries(st.text(max_size=20), children, max_size=10)
    ),
    max_leaves=50,
)

# Valid dict keys (non-empty strings)
dict_keys = st.text(min_size=1, max_size=50)

# Row-like data matching ELSPETH pipeline shape
row_data = st.dictionaries(
    keys=dict_keys,
    values=json_primitives,
    min_size=1,
    max_size=20,
)
