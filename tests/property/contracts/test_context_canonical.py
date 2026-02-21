"""Property tests for NodeStateContext canonical JSON determinism.

Verifies that canonical_json(context.to_dict()) is deterministic
for any valid context instance.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.contracts.coalesce_metadata import ArrivalOrderEntry, CoalesceMetadata
from elspeth.contracts.node_state_context import (
    PoolConfigSnapshot,
    PoolExecutionContext,
    PoolStatsSnapshot,
    QueryOrderEntry,
)
from elspeth.core.canonical import canonical_json

# -- Strategies ---------------------------------------------------------------

_safe_floats = st.floats(
    min_value=0.0,
    max_value=1e9,
    allow_nan=False,
    allow_infinity=False,
)

_safe_positive_ints = st.integers(min_value=0, max_value=10000)

_pool_config = st.builds(
    PoolConfigSnapshot,
    pool_size=st.integers(min_value=1, max_value=64),
    max_capacity_retry_seconds=_safe_floats,
    dispatch_delay_at_completion_ms=_safe_floats,
)

_pool_stats = st.builds(
    PoolStatsSnapshot,
    capacity_retries=_safe_positive_ints,
    successes=_safe_positive_ints,
    peak_delay_ms=_safe_floats,
    current_delay_ms=_safe_floats,
    total_throttle_time_ms=_safe_floats,
    max_concurrent_reached=_safe_positive_ints,
)

_query_order_entry = st.builds(
    QueryOrderEntry,
    submit_index=_safe_positive_ints,
    complete_index=_safe_positive_ints,
    buffer_wait_ms=_safe_floats,
)

_pool_execution_context = st.builds(
    PoolExecutionContext,
    pool_config=_pool_config,
    pool_stats=_pool_stats,
    query_ordering=st.tuples(*[_query_order_entry] * 2).map(tuple),  # 2 entries
)

_branch_names = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_"),
    min_size=1,
    max_size=20,
)


@st.composite
def _coalesce_metadata(draw: st.DrawFn) -> CoalesceMetadata:
    """Strategy for CoalesceMetadata.for_merge() with valid params."""
    branches = draw(st.lists(_branch_names, min_size=1, max_size=5, unique=True))
    arrived = branches  # All branches arrived for merge
    arrival_order = [
        ArrivalOrderEntry(
            branch=b,
            arrival_offset_ms=draw(_safe_floats),
        )
        for b in arrived
    ]
    return CoalesceMetadata.for_merge(
        policy=draw(st.sampled_from(["require_all", "first", "quorum", "best_effort"])),
        merge_strategy=draw(st.sampled_from(["union", "nested", "select"])),
        expected_branches=branches,
        branches_arrived=arrived,
        branches_lost={},
        arrival_order=arrival_order,
        wait_duration_ms=draw(_safe_floats),
    )


# -- Tests --------------------------------------------------------------------


class TestPoolExecutionContextCanonical:
    @given(ctx=_pool_execution_context)
    @settings(max_examples=50)
    def test_canonical_json_deterministic(self, ctx: PoolExecutionContext) -> None:
        """canonical_json(ctx.to_dict()) is deterministic for any valid PoolExecutionContext."""
        json1 = canonical_json(ctx.to_dict())
        json2 = canonical_json(ctx.to_dict())
        assert json1 == json2

    @given(ctx=_pool_execution_context)
    @settings(max_examples=50)
    def test_to_dict_round_trips(self, ctx: PoolExecutionContext) -> None:
        """to_dict() produces a dict that can be serialized and deserialized."""
        import json

        d = ctx.to_dict()
        json_str = canonical_json(d)
        parsed = json.loads(json_str)
        assert parsed == d


class TestCoalesceMetadataCanonical:
    @given(meta=_coalesce_metadata())
    @settings(max_examples=50)
    def test_canonical_json_deterministic(self, meta: CoalesceMetadata) -> None:
        """canonical_json(meta.to_dict()) is deterministic for any valid CoalesceMetadata."""
        json1 = canonical_json(meta.to_dict())
        json2 = canonical_json(meta.to_dict())
        assert json1 == json2

    @given(meta=_coalesce_metadata())
    @settings(max_examples=50)
    def test_to_dict_round_trips(self, meta: CoalesceMetadata) -> None:
        """to_dict() produces a dict that can be serialized and deserialized."""
        import json

        d = meta.to_dict()
        json_str = canonical_json(d)
        parsed = json.loads(json_str)
        assert parsed == d
