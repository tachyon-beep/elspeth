"""
VULN-011 Phase 0: Baseline Characterization Tests

These tests capture CURRENT behavior of SecureDataFrame before hardening.
Purpose: Document "known good" baseline for regression detection.

Tests run against EXISTING stack inspection implementation.
No production code changes in Phase 0.
"""

import timeit

import pandas as pd
import pytest

from elspeth.core.base.types import SecurityLevel
from elspeth.core.security.secure_data import SecureDataFrame
from elspeth.core.validation.base import SecurityValidationError


def test_baseline_factory_methods_work():
    """BASELINE: Document current factory method behavior before hardening."""
    # create_from_datasource
    frame1 = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"a": [1, 2, 3]}), SecurityLevel.OFFICIAL
    )
    assert frame1.security_level == SecurityLevel.OFFICIAL
    assert len(frame1.data) == 3

    # with_uplifted_security_level
    frame2 = frame1.with_uplifted_security_level(SecurityLevel.SECRET)
    assert frame2.security_level == SecurityLevel.SECRET
    assert len(frame2.data) == 3  # Data unchanged

    # with_new_data
    frame3 = frame1.with_new_data(pd.DataFrame({"b": [4, 5]}))
    assert frame3.security_level == SecurityLevel.OFFICIAL  # Classification preserved
    assert "b" in frame3.data.columns
    assert len(frame3.data) == 2


def test_baseline_direct_construction_blocked():
    """BASELINE: Verify current stack inspection blocks direct construction."""
    with pytest.raises(SecurityValidationError):
        SecureDataFrame(
            data=pd.DataFrame({"col": [1]}), security_level=SecurityLevel.SECRET
        )


def test_baseline_stack_inspection_performance():
    """BASELINE: Measure current stack inspection overhead (for comparison)."""

    def create_frame():
        return SecureDataFrame.create_from_datasource(
            pd.DataFrame({"col": [1]}), SecurityLevel.OFFICIAL
        )

    # Run 10k iterations (smaller than Phase 4 for quick baseline)
    time = timeit.timeit(create_frame, number=10000)
    avg_per_call = (time / 10000) * 1_000_000  # Microseconds

    # Document baseline (expected ~5µs with stack inspection)
    print(f"\n📊 BASELINE Construction: {avg_per_call:.3f}µs per call")

    # No assertion - just document current performance
    # Phase 4 will compare against this baseline


def test_baseline_integration_with_orchestrator():
    """BASELINE: Verify containers work in suite runner context."""
    # Simulate orchestrator pattern: create → uplift → validate
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2, 3]}), SecurityLevel.OFFICIAL
    )

    uplifted = frame.with_uplifted_security_level(SecurityLevel.SECRET)

    # Validate compatibility (used by sinks)
    # SECRET data requires SECRET clearance - should pass
    uplifted.validate_compatible_with(SecurityLevel.SECRET)

    # SECRET data with OFFICIAL clearance should FAIL (insufficient clearance)
    with pytest.raises(SecurityValidationError):
        uplifted.validate_compatible_with(SecurityLevel.OFFICIAL)
