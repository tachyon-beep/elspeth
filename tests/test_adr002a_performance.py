"""ADR-002-A Performance Benchmarks

These tests measure the performance overhead of ADR-002-A constructor protection
to ensure the security features don't significantly impact suite execution time.

⚠️ IMPORTANT: All tests marked @slow to prevent flaky failures on busy CI runners.
   Run with: pytest -m slow
   Expected to run in nightly builds or before releases.

Benchmarking Strategy:
- Measure SecureDataFrame creation time
- Verify overhead is acceptable (<50μs per creation, CI-safe threshold)
- Thresholds set to 10x expected performance to account for CI variance

Expected Performance (Modern Hardware):
- Constructor: ~2-5μs (token gating overhead)
- Uplifting: ~1-5μs (most common operation)
- Data replacement: ~2-5μs (LLM/aggregation pattern)
- Frames per suite: 3-5 (datasource + transforms)
- Total overhead: ~15-25μs per suite (negligible)

CI-Safe Thresholds:
- Individual operations: <50μs (10x expected, accounts for busy runners)
- Suite simulation: <100μs (catches major regressions without flakiness)

Context: Typical experiment suites run for minutes (LLM API calls dominate),
so even 250μs constructor overhead is <0.05% of total execution time.

Observed Variance:
- Modern hardware: 2-5μs per operation
- Busy CI runner: 10-20μs per operation (3-4x variance)
- Threshold: 50μs (catches regressions, tolerates variance)
"""

import timeit
import pandas as pd
import pytest

from elspeth.core.base.types import SecurityLevel
from elspeth.core.security.secure_data import SecureDataFrame


class TestADR002APerformance:
    """Performance benchmarks for ADR-002-A constructor protection.

    NOTE: All performance tests marked @slow to prevent flaky failures on busy CI runners.
    Run locally or in nightly builds with: pytest -m slow
    """

    @pytest.mark.slow
    def test_constructor_overhead_acceptable(self):
        """Verify SecureDataFrame creation overhead is <50μs.

        Requirement from code review: Constructor protection should add
        minimal overhead.

        Methodology:
        - Create 10,000 frames via create_from_datasource()
        - Measure average time per creation
        - Assert average < 50μs (10x expected to account for busy CI runners)

        ADR-002-A expected: 2-5μs on modern hardware
        CI threshold: 50μs (accounts for system variance, busy runners)

        Why overhead is negligible:
        - Typical suite creates 3-5 frames
        - 50μs × 5 frames = 250μs total overhead
        - LLM API call = ~500ms
        - Overhead ratio: 250μs / 500ms = 0.05% (negligible)
        """
        # Setup: Create sample DataFrame
        df = pd.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})

        # Benchmark: Measure creation time (10,000 iterations)
        total_time = timeit.timeit(
            "SecureDataFrame.create_from_datasource(df, SecurityLevel.SECRET)",
            setup="from elspeth.core.security.secure_data import SecureDataFrame\n"
                  "from elspeth.core.base.types import SecurityLevel\n"
                  "import pandas as pd\n"
                  "df = pd.DataFrame({'col1': [1, 2, 3], 'col2': ['a', 'b', 'c']})",
            number=10000,
            globals={"df": df, "SecurityLevel": SecurityLevel}
        )

        # Calculate average time per creation
        avg_time_per_creation = total_time / 10000

        # Assert: Average creation time < 50μs
        assert avg_time_per_creation < 50e-6, (
            f"Constructor overhead too high: {avg_time_per_creation*1e6:.2f}μs "
            f"(threshold: 50μs, ADR-002-A expected: 2-5μs on modern hardware)"
        )

        # Print benchmark results for visibility
        print("\n✅ Constructor Performance Benchmark:")
        print(f"   Total time (10,000 creations): {total_time:.4f}s")
        print(f"   Average per creation: {avg_time_per_creation*1e6:.2f}μs")
        print("   Threshold: 50μs (ADR-002-A: 2-5μs expected on modern hardware)")
        print(f"   Status: {'PASS' if avg_time_per_creation < 50e-6 else 'FAIL'}")

    @pytest.mark.slow
    def test_uplifting_overhead_acceptable(self):
        """Verify with_uplifted_security_level() overhead is <50μs.

        Uplifting is more common than creation (happens at every transform).

        Methodology:
        - Create one frame
        - Uplift 10,000 times
        - Measure average time per uplift
        - Assert average < 50μs (10x expected to account for busy CI runners)

        ADR-002-A expected: 1-5μs on modern hardware
        CI threshold: 50μs (accounts for system variance, busy runners)
        """
        # Setup: Create initial frame
        df = pd.DataFrame({"col1": [1, 2, 3]})
        frame = SecureDataFrame.create_from_datasource(df, SecurityLevel.OFFICIAL)

        # Benchmark: Measure uplifting time (10,000 iterations)
        total_time = timeit.timeit(
            "frame.with_uplifted_security_level(SecurityLevel.SECRET)",
            setup="from elspeth.core.base.types import SecurityLevel",
            number=10000,
            globals={"frame": frame, "SecurityLevel": SecurityLevel}
        )

        # Calculate average time per uplift
        avg_time_per_uplift = total_time / 10000

        # Assert: Average uplift time < 50μs (ADR-002-A: expected 1-5μs on modern hardware)
        # Threshold set to 10x upper bound to avoid flaky failures on busy CI runners
        assert avg_time_per_uplift < 50e-6, (
            f"Uplifting overhead too high: {avg_time_per_uplift*1e6:.2f}μs "
            f"(threshold: 50μs, ADR-002-A expected range: 1-5μs on modern hardware)"
        )

        # Print benchmark results
        print("\n✅ Uplifting Performance Benchmark:")
        print(f"   Total time (10,000 uplifts): {total_time:.4f}s")
        print(f"   Average per uplift: {avg_time_per_uplift*1e6:.2f}μs")
        print("   Threshold: 50μs (ADR-002-A: 1-5μs expected on modern hardware)")
        print(f"   Status: {'PASS' if avg_time_per_uplift < 50e-6 else 'FAIL'}")

    @pytest.mark.slow
    def test_with_new_data_overhead_acceptable(self):
        """Verify with_new_data() overhead is <50μs.

        This is used by LLM/aggregation plugins that generate new DataFrames.

        Methodology:
        - Create initial frame
        - Replace data 10,000 times
        - Measure average time per replacement
        - Assert average < 50μs (10x expected to account for busy CI runners)

        ADR-002-A expected: 2-5μs on modern hardware
        CI threshold: 50μs (accounts for system variance, busy runners)
        """
        # Setup: Create initial frame and replacement data
        df1 = pd.DataFrame({"input": [1, 2, 3]})
        df2 = pd.DataFrame({"output": [4, 5, 6]})
        frame = SecureDataFrame.create_from_datasource(df1, SecurityLevel.SECRET)

        # Benchmark: Measure with_new_data time (10,000 iterations)
        total_time = timeit.timeit(
            "frame.with_new_data(df2)",
            number=10000,
            globals={"frame": frame, "df2": df2}
        )

        # Calculate average time per replacement
        avg_time_per_replacement = total_time / 10000

        # Assert: Average replacement time < 50μs
        assert avg_time_per_replacement < 50e-6, (
            f"with_new_data overhead too high: {avg_time_per_replacement*1e6:.2f}μs "
            f"(threshold: 50μs, ADR-002-A expected: 2-5μs on modern hardware)"
        )

        # Print benchmark results
        print("\n✅ Data Replacement Performance Benchmark:")
        print(f"   Total time (10,000 replacements): {total_time:.4f}s")
        print(f"   Average per replacement: {avg_time_per_replacement*1e6:.2f}μs")
        print("   Threshold: 50μs (ADR-002-A: 2-5μs expected on modern hardware)")
        print(f"   Status: {'PASS' if avg_time_per_replacement < 50e-6 else 'FAIL'}")

    @pytest.mark.slow
    def test_suite_level_overhead_negligible(self):
        """Verify total ADR-002-A overhead per suite is <0.1ms.

        Simulates a typical suite execution:
        - 1 datasource creation (create_from_datasource)
        - 3 plugin transforms (with_uplifted_security_level)
        - 1 LLM data generation (with_new_data)
        - 1 sink write (with_uplifted_security_level)

        Total: 6 SecureDataFrame operations per suite
        Threshold: <100μs (0.1ms) for all operations

        Context: Typical suite runs ~5 minutes (300,000ms)
        → 0.1ms overhead = 0.00003% of total time
        """
        # Setup: Create components
        df_source = pd.DataFrame({"input": [1, 2, 3]})
        df_llm_output = pd.DataFrame({"output": ["a", "b", "c"]})

        # Benchmark: Simulate suite execution (1,000 iterations)
        def simulate_suite_execution():
            # Step 1: Datasource creates frame
            frame1 = SecureDataFrame.create_from_datasource(
                df_source, SecurityLevel.SECRET
            )

            # Step 2-4: Three plugin transforms
            frame2 = frame1.with_uplifted_security_level(SecurityLevel.SECRET)
            frame3 = frame2.with_uplifted_security_level(SecurityLevel.SECRET)
            frame4 = frame3.with_uplifted_security_level(SecurityLevel.SECRET)

            # Step 5: LLM generates new data
            frame5 = frame4.with_new_data(df_llm_output)

            # Step 6: Sink uplift
            frame6 = frame5.with_uplifted_security_level(SecurityLevel.SECRET)

            return frame6

        total_time = timeit.timeit(
            "simulate_suite_execution()",
            number=1000,
            globals={"simulate_suite_execution": simulate_suite_execution}
        )

        # Calculate average time per suite simulation
        avg_time_per_suite = total_time / 1000

        # Assert: Average suite overhead < 100μs (0.1ms)
        assert avg_time_per_suite < 100e-6, (
            f"Suite overhead too high: {avg_time_per_suite*1e6:.2f}μs "
            f"(threshold: 100μs)"
        )

        # Print benchmark results
        print("\n✅ Full Suite Overhead Benchmark:")
        print(f"   Total time (1,000 simulated suites): {total_time:.4f}s")
        print(f"   Average per suite: {avg_time_per_suite*1e6:.2f}μs")
        print("   Operations per suite: 6")
        print("   Threshold: 100μs")
        print(f"   Overhead ratio (vs 5min suite): {(avg_time_per_suite/300):.6f}%")
        print(f"   Status: {'PASS' if avg_time_per_suite < 100e-6 else 'FAIL'}")


# ============================================================================
# Benchmark Summary
# ============================================================================


"""
ADR-002-A Performance Benchmark Coverage:

✅ test_constructor_overhead_acceptable (marked @slow)
   - Measures: create_from_datasource() time
   - Threshold: <50μs per creation (CI-safe, 10x expected)
   - Expected on modern hardware: ~2-5μs
   - Rationale: Token gating overhead (capability validation)

✅ test_uplifting_overhead_acceptable (marked @slow)
   - Measures: with_uplifted_security_level() time
   - Threshold: <50μs per uplift (CI-safe, 10x expected)
   - Expected on modern hardware: ~1-5μs
   - Rationale: Most common operation, critical for performance

✅ test_with_new_data_overhead_acceptable (marked @slow)
   - Measures: with_new_data() time
   - Threshold: <50μs per replacement (CI-safe, 10x expected)
   - Expected on modern hardware: ~2-5μs
   - Rationale: LLM/aggregation pattern overhead

✅ test_suite_level_overhead_negligible (marked @slow)
   - Measures: Complete suite simulation (6 operations)
   - Threshold: <100μs per suite
   - Expected on modern hardware: ~15-20μs
   - Rationale: Real-world usage pattern
   - Context: 0.00003% of 5-minute suite execution

Performance Validation Strategy:
1. All tests marked @slow to prevent flaky failures on busy CI runners
2. Run locally with: pytest -m slow
3. Run in nightly builds or before releases
4. Thresholds set to 10x expected performance to account for system variance
5. Actual overhead on modern hardware: 2-5μs per operation (well under thresholds)

Why CI-Safe Thresholds (50μs vs 5μs expected):
- CI runners can have 3-10x variance due to system load
- 16.24μs observed on busy runner (vs 2-5μs expected)
- 50μs threshold = 10x expected, catches major regressions without flakiness
- Still validates overhead is negligible (<0.1% of LLM API call time)

If tests fail:
- Likely indicates major performance regression (not system variance)
- Profile with cProfile to find bottleneck
- Check if running on extremely slow/overloaded hardware
- Consider caching validated callers (see ADR002A_EVALUATION.md)
"""
