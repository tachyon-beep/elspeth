# tests/performance/stress/test_call_index_concurrency.py
"""Concurrent stress tests for allocate_call_index thread safety.

Validates that LandscapeRecorder.allocate_call_index() correctly serializes
concurrent access via threading.Lock, producing contiguous gap-free index
sequences with no duplicates.

Target code: src/elspeth/core/landscape/_call_recording.py:46-83
"""

from __future__ import annotations

import threading

import pytest

from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder

pytestmark = pytest.mark.stress

NUM_THREADS = 8
CALLS_PER_THREAD = 500


@pytest.fixture
def recorder() -> LandscapeRecorder:
    """Create a LandscapeRecorder with in-memory database."""
    db = LandscapeDB.in_memory()
    return LandscapeRecorder(db)


class TestAllocateCallIndexConcurrency:
    """Thread-safety stress tests for allocate_call_index."""

    def test_concurrent_same_state_id(self, recorder: LandscapeRecorder) -> None:
        """8 threads allocating indices for the same state_id produce contiguous set.

        All threads call allocate_call_index("state_1") 500 times each.
        The returned indices must form {0, 1, ..., 3999} with no gaps or duplicates.
        This validates the lock correctly serializes access for a shared state_id.
        """
        barrier = threading.Barrier(NUM_THREADS)
        all_indices: list[list[int]] = [[] for _ in range(NUM_THREADS)]

        def worker(thread_idx: int) -> None:
            barrier.wait()
            local: list[int] = []
            for _ in range(CALLS_PER_THREAD):
                idx = recorder.allocate_call_index("state_1")
                local.append(idx)
            all_indices[thread_idx] = local

        threads = [threading.Thread(target=worker, args=(i,), name=f"ci-same-{i}") for i in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # Flatten and verify contiguous set with no gaps or duplicates
        flat = [idx for batch in all_indices for idx in batch]
        expected_total = NUM_THREADS * CALLS_PER_THREAD
        assert len(flat) == expected_total
        assert set(flat) == set(range(expected_total))

    def test_concurrent_independent_state_ids(self, recorder: LandscapeRecorder) -> None:
        """8 threads with unique state_ids produce independent contiguous sequences.

        Each thread calls allocate_call_index with its own state_id 500 times.
        Each state_id's indices must independently form {0, 1, ..., 499}.
        This validates per-state-id counters don't interfere across threads.
        """
        barrier = threading.Barrier(NUM_THREADS)
        all_indices: list[list[int]] = [[] for _ in range(NUM_THREADS)]

        def worker(thread_idx: int) -> None:
            barrier.wait()
            state_id = f"state_{thread_idx}"
            local: list[int] = []
            for _ in range(CALLS_PER_THREAD):
                idx = recorder.allocate_call_index(state_id)
                local.append(idx)
            all_indices[thread_idx] = local

        threads = [threading.Thread(target=worker, args=(i,), name=f"ci-indep-{i}") for i in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # Each thread's state_id should have an independent {0..499} sequence
        for thread_idx in range(NUM_THREADS):
            indices = all_indices[thread_idx]
            assert len(indices) == CALLS_PER_THREAD
            assert set(indices) == set(range(CALLS_PER_THREAD)), (
                f"Thread {thread_idx} (state_{thread_idx}): expected {{0..{CALLS_PER_THREAD - 1}}}, got {len(set(indices))} unique values"
            )
