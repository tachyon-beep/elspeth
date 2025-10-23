from __future__ import annotations

import time

import numpy as np
import pytest

from elspeth.plugins.experiments._stats_helpers import krippendorff_alpha


@pytest.mark.slow
def test_krippendorff_alpha_performance_interval():
    """Perf smoke: interval alpha on a moderately sized matrix runs quickly.

    This is a coarse baseline to catch accidental O(n^3) regressions. It runs in
    the isolated perf workflow; marked slow so it is skipped in the main CI.
    """
    rng = np.random.default_rng(42)
    # 200 items rated by 20 raters
    arr = rng.random((200, 20))
    start = time.monotonic()
    alpha = krippendorff_alpha(arr, level="interval")
    elapsed_ms = (time.monotonic() - start) * 1000
    assert alpha is not None
    # Generous threshold: O(n²) pairwise comparisons for 200×20 matrix
    # Expected: ~2-3s locally, may be slower on CI runners
    assert elapsed_ms < 5000, f"took {elapsed_ms:.1f} ms (threshold: 5s)"

