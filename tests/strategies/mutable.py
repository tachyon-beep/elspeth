# tests/strategies/mutable.py
"""Mutable nested data strategies for isolation testing.

Used to verify deepcopy isolation in fork_token and similar operations.
"""

from hypothesis import strategies as st

# Mutable nested structures with clean keys
mutable_nested_data = st.dictionaries(
    keys=st.text(
        min_size=1,
        max_size=10,
        alphabet=st.characters(whitelist_categories=["L"]),
    ),
    values=st.one_of(
        st.integers(),
        st.lists(st.integers(), min_size=1, max_size=5),
        st.dictionaries(
            st.text(
                min_size=1,
                max_size=5,
                alphabet=st.characters(whitelist_categories=["L"]),
            ),
            st.integers(),
            min_size=1,
            max_size=3,
        ),
    ),
    min_size=1,
    max_size=5,
)

# Deeply nested mutable data (stress test for deepcopy)
deeply_nested_data = st.recursive(
    st.integers(),
    lambda children: st.one_of(
        st.lists(children, min_size=1, max_size=3),
        st.dictionaries(
            st.text(
                min_size=1,
                max_size=5,
                alphabet=st.characters(whitelist_categories=["L"]),
            ),
            children,
            min_size=1,
            max_size=3,
        ),
    ),
    max_leaves=20,
)
