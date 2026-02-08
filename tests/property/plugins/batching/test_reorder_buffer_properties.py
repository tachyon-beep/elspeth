# tests/property/plugins/batching/test_reorder_buffer_properties.py
"""Property-based tests for RowReorderBuffer FIFO ordering and conservation laws.

The RowReorderBuffer accepts rows out-of-order (as workers complete) and
releases them in strict submission order (FIFO). It provides backpressure
when max_pending is reached.

Key invariants:
- Release order always matches submit order (FIFO)
- next_release_seq <= next_submit_seq
- total_submitted == total_released + pending
- Backpressure: can't have more than max_pending in flight
- Eviction advances release pointer correctly
- Shutdown prevents new operations
- Double-complete raises ValueError
- Invalid ticket raises KeyError

Testing approach:
- Hypothesis generates random completion orders to verify FIFO property
- Single-threaded tests probe invariants without concurrency complexity
- Sequential submit→complete→release cycles verify conservation laws
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.plugins.batching.row_reorder_buffer import (
    RowReorderBuffer,
    ShutdownError,
)

# =============================================================================
# Strategies
# =============================================================================

# Number of rows to process
row_counts = st.integers(min_value=1, max_value=50)

# Max pending limits
max_pending_values = st.integers(min_value=1, max_value=100)

# Row IDs
row_ids = st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789")


# =============================================================================
# FIFO Ordering Properties
# =============================================================================


class TestFIFOOrderingProperties:
    """Released rows must always be in submission order, regardless of completion order."""

    @given(n=st.integers(min_value=1, max_value=30))
    @settings(max_examples=100)
    def test_sequential_complete_releases_in_order(self, n: int) -> None:
        """Property: When completed in order, release order matches submit order."""
        buffer: RowReorderBuffer[str] = RowReorderBuffer(max_pending=n + 1)

        tickets = [buffer.submit(f"row-{i}") for i in range(n)]

        released_ids = []
        for ticket in tickets:
            buffer.complete(ticket, f"result-{ticket.sequence}")
            entry = buffer.wait_for_next_release(timeout=1.0)
            released_ids.append(entry.row_id)

        expected = [f"row-{i}" for i in range(n)]
        assert released_ids == expected

    @given(
        n=st.integers(min_value=2, max_value=20),
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_random_completion_order_still_releases_fifo(self, n: int, data: st.DataObject) -> None:
        """Property: Random completion order still produces FIFO release order.

        This is THE core invariant of the reorder buffer.
        """
        buffer: RowReorderBuffer[str] = RowReorderBuffer(max_pending=n + 1)

        # Submit all rows in order
        tickets = [buffer.submit(f"row-{i}") for i in range(n)]

        # Complete in a random order
        completion_order = data.draw(st.permutations(list(range(n))))
        for idx in completion_order:
            buffer.complete(tickets[idx], f"result-{idx}")

        # Release all — must be in original submit order
        released_seqs = []
        for _ in range(n):
            entry = buffer.wait_for_next_release(timeout=1.0)
            released_seqs.append(entry.sequence)

        assert released_seqs == list(range(n))

    @given(n=st.integers(min_value=2, max_value=15))
    @settings(max_examples=50)
    def test_reverse_completion_releases_fifo(self, n: int) -> None:
        """Property: Completing in reverse order still releases FIFO."""
        buffer: RowReorderBuffer[str] = RowReorderBuffer(max_pending=n + 1)

        tickets = [buffer.submit(f"row-{i}") for i in range(n)]

        # Complete in reverse order
        for ticket in reversed(tickets):
            buffer.complete(ticket, f"result-{ticket.sequence}")

        # Release — must still be in submission order
        released_ids = []
        for _ in range(n):
            entry = buffer.wait_for_next_release(timeout=1.0)
            released_ids.append(entry.row_id)

        expected = [f"row-{i}" for i in range(n)]
        assert released_ids == expected


# =============================================================================
# Conservation Law Properties
# =============================================================================


class TestConservationProperties:
    """submitted == released + pending must hold at all times."""

    @given(n=st.integers(min_value=1, max_value=30))
    @settings(max_examples=100)
    def test_total_conservation_after_full_cycle(self, n: int) -> None:
        """Property: After all releases, total_submitted == total_released."""
        buffer: RowReorderBuffer[str] = RowReorderBuffer(max_pending=n + 1)

        tickets = [buffer.submit(f"row-{i}") for i in range(n)]
        for ticket in tickets:
            buffer.complete(ticket, "result")

        for _ in range(n):
            buffer.wait_for_next_release(timeout=1.0)

        metrics = buffer.get_metrics()
        assert metrics["total_submitted"] == n
        assert metrics["total_released"] == n
        assert metrics["current_pending"] == 0

    @given(n=st.integers(min_value=1, max_value=20))
    @settings(max_examples=50)
    def test_pending_count_tracks_in_flight(self, n: int) -> None:
        """Property: pending_count increases with submit, decreases with release."""
        buffer: RowReorderBuffer[str] = RowReorderBuffer(max_pending=n + 1)

        # After submitting, pending should equal submitted count
        tickets = []
        for i in range(n):
            ticket = buffer.submit(f"row-{i}")
            tickets.append(ticket)
            assert buffer.pending_count == i + 1

        # Complete and release each — pending decreases
        for i, ticket in enumerate(tickets):
            buffer.complete(ticket, "result")
            buffer.wait_for_next_release(timeout=1.0)
            assert buffer.pending_count == n - i - 1


# =============================================================================
# Result Integrity Properties
# =============================================================================


class TestResultIntegrityProperties:
    """Released entries must carry the correct result and metadata."""

    @given(n=st.integers(min_value=1, max_value=20))
    @settings(max_examples=50)
    def test_result_matches_completed_value(self, n: int) -> None:
        """Property: Released entry.result matches the value passed to complete()."""
        buffer: RowReorderBuffer[str] = RowReorderBuffer(max_pending=n + 1)

        tickets = [buffer.submit(f"row-{i}") for i in range(n)]
        for ticket in tickets:
            buffer.complete(ticket, f"result-for-{ticket.row_id}")

        for i in range(n):
            entry = buffer.wait_for_next_release(timeout=1.0)
            assert entry.result == f"result-for-row-{i}"
            assert entry.row_id == f"row-{i}"
            assert entry.sequence == i

    @given(n=st.integers(min_value=1, max_value=20))
    @settings(max_examples=50)
    def test_buffer_wait_ms_is_non_negative(self, n: int) -> None:
        """Property: buffer_wait_ms is always >= 0."""
        buffer: RowReorderBuffer[str] = RowReorderBuffer(max_pending=n + 1)

        tickets = [buffer.submit(f"row-{i}") for i in range(n)]
        for ticket in tickets:
            buffer.complete(ticket, "result")

        for _ in range(n):
            entry = buffer.wait_for_next_release(timeout=1.0)
            assert entry.buffer_wait_ms >= 0.0


# =============================================================================
# Eviction Properties
# =============================================================================


class TestEvictionProperties:
    """Eviction must advance release pointer and free slots."""

    def test_evict_allows_skipping_sequence(self) -> None:
        """Property: Evicting a sequence allows later sequences to release."""
        buffer: RowReorderBuffer[str] = RowReorderBuffer(max_pending=10)

        t0 = buffer.submit("row-0")
        t1 = buffer.submit("row-1")
        t2 = buffer.submit("row-2")

        # Complete t1 and t2, but evict t0 (simulating timeout/retry)
        buffer.complete(t1, "result-1")
        buffer.complete(t2, "result-2")

        assert buffer.evict(t0)

        # Now t1 should be releasable
        entry = buffer.wait_for_next_release(timeout=1.0)
        assert entry.row_id == "row-1"

        entry = buffer.wait_for_next_release(timeout=1.0)
        assert entry.row_id == "row-2"

    def test_evict_returns_false_for_completed(self) -> None:
        """Property: Cannot evict an already-completed entry."""
        buffer: RowReorderBuffer[str] = RowReorderBuffer(max_pending=10)
        ticket = buffer.submit("row-0")
        buffer.complete(ticket, "result")

        assert not buffer.evict(ticket)

    def test_evict_returns_false_for_unknown(self) -> None:
        """Property: Evicting unknown ticket returns False."""
        buffer: RowReorderBuffer[str] = RowReorderBuffer(max_pending=10)
        ticket = buffer.submit("row-0")
        buffer.complete(ticket, "result")
        buffer.wait_for_next_release(timeout=1.0)

        # ticket is now released, evict returns False
        assert not buffer.evict(ticket)

    @given(n=st.integers(min_value=2, max_value=10))
    @settings(max_examples=30)
    def test_evict_frees_slot_for_backpressure(self, n: int) -> None:
        """Property: Evicting frees a slot, reducing pending count."""
        buffer: RowReorderBuffer[str] = RowReorderBuffer(max_pending=n)

        # Fill to capacity
        tickets = [buffer.submit(f"row-{i}") for i in range(n)]
        assert buffer.pending_count == n

        # Evict first entry
        assert buffer.evict(tickets[0])
        assert buffer.pending_count == n - 1


# =============================================================================
# Error Handling Properties
# =============================================================================


class TestErrorHandlingProperties:
    """Error conditions must be detected and raised correctly."""

    def test_double_complete_raises_valueerror(self) -> None:
        """Property: Completing the same ticket twice raises ValueError."""
        buffer: RowReorderBuffer[str] = RowReorderBuffer(max_pending=10)
        ticket = buffer.submit("row-0")

        buffer.complete(ticket, "result-1")

        with pytest.raises(ValueError, match="already completed"):
            buffer.complete(ticket, "result-2")

    def test_max_pending_less_than_one_raises(self) -> None:
        """Property: max_pending < 1 raises ValueError."""
        with pytest.raises(ValueError, match="max_pending must be >= 1"):
            RowReorderBuffer(max_pending=0)

        with pytest.raises(ValueError, match="max_pending must be >= 1"):
            RowReorderBuffer(max_pending=-1)


# =============================================================================
# Shutdown Properties
# =============================================================================


class TestShutdownProperties:
    """Shutdown must prevent new operations and wake waiters."""

    def test_submit_after_shutdown_raises(self) -> None:
        """Property: submit() after shutdown raises ShutdownError."""
        buffer: RowReorderBuffer[str] = RowReorderBuffer(max_pending=10)
        buffer.shutdown()

        with pytest.raises(ShutdownError):
            buffer.submit("row-0")

    def test_wait_after_shutdown_raises(self) -> None:
        """Property: wait_for_next_release() after shutdown raises ShutdownError."""
        buffer: RowReorderBuffer[str] = RowReorderBuffer(max_pending=10)
        buffer.shutdown()

        with pytest.raises(ShutdownError):
            buffer.wait_for_next_release(timeout=1.0)

    def test_is_shutdown_flag(self) -> None:
        """Property: is_shutdown reflects shutdown state."""
        buffer: RowReorderBuffer[str] = RowReorderBuffer(max_pending=10)
        assert not buffer.is_shutdown

        buffer.shutdown()
        assert buffer.is_shutdown


# =============================================================================
# Metrics Properties
# =============================================================================


class TestMetricsProperties:
    """Metrics must accurately reflect buffer state."""

    @given(n=st.integers(min_value=1, max_value=20))
    @settings(max_examples=50)
    def test_max_observed_pending_never_exceeds_limit(self, n: int) -> None:
        """Property: max_observed_pending never exceeds max_pending."""
        limit = max(n, 5)
        buffer: RowReorderBuffer[str] = RowReorderBuffer(max_pending=limit)

        tickets = [buffer.submit(f"row-{i}") for i in range(n)]
        for ticket in tickets:
            buffer.complete(ticket, "result")
        for _ in range(n):
            buffer.wait_for_next_release(timeout=1.0)

        metrics = buffer.get_metrics()
        assert metrics["max_observed_pending"] <= limit

    @given(n=st.integers(min_value=1, max_value=20))
    @settings(max_examples=50)
    def test_avg_buffer_wait_ms_non_negative(self, n: int) -> None:
        """Property: Average buffer wait time is always non-negative."""
        buffer: RowReorderBuffer[str] = RowReorderBuffer(max_pending=n + 1)

        tickets = [buffer.submit(f"row-{i}") for i in range(n)]
        for ticket in tickets:
            buffer.complete(ticket, "result")
        for _ in range(n):
            buffer.wait_for_next_release(timeout=1.0)

        metrics = buffer.get_metrics()
        assert metrics["avg_buffer_wait_ms"] >= 0.0
