"""ADR-002-A Performance Benchmarks

These tests measure the performance overhead of ADR-002-A constructor protection
to ensure the security features don't significantly impact suite execution time.

Benchmarking Strategy:
- Measure SecureDataFrame creation time
- Compare with/without frame inspection overhead
- Verify overhead is acceptable (<10μs per creation)

Expected Performance:
- Frame inspection: ~1-5μs (stack walking cost)
- Frames per suite: 3-5 (datasource + transforms)
- Total overhead: <25μs per suite (negligible)

Context: Typical experiment suites run for minutes (LLM API calls dominate),
so even 100μs constructor overhead is <0.0001% of total execution time.
"""

import timeit
import pandas as pd
import pytest

from elspeth.core.base.types import SecurityLevel
from elspeth.core.security.secure_data import SecureDataFrame


class TestADR002APerformance:
    """Performance benchmarks for ADR-002-A constructor protection."""

    def test_constructor_overhead_acceptable(self):
        """Verify SecureDataFrame creation overhead is <10μs.

        Requirement from code review: Constructor protection should add
        minimal overhead (<10μs per frame creation).

        Methodology:
        - Create 10,000 frames via create_from_datasource()
        - Measure average time per creation
        - Assert average < 10μs (10e-6 seconds)

        Why 10μs threshold:
        - Typical suite creates 3-5 frames
        - 10μs × 5 frames = 50μs total overhead
        - LLM API call = ~500ms
        - Overhead ratio: 50μs / 500ms = 0.01% (negligible)
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

        # Assert: Average creation time < 10μs
        assert avg_time_per_creation < 10e-6, (
            f"Constructor overhead too high: {avg_time_per_creation*1e6:.2f}μs "
            f"(threshold: 10μs)"
        )

        # Print benchmark results for visibility
        print("\n✅ Constructor Performance Benchmark:")
        print(f"   Total time (10,000 creations): {total_time:.4f}s")
        print(f"   Average per creation: {avg_time_per_creation*1e6:.2f}μs")
        print("   Threshold: 10μs")
        print(f"   Status: {'PASS' if avg_time_per_creation < 10e-6 else 'FAIL'}")

    def test_uplifting_overhead_acceptable(self):
        """Verify with_uplifted_security_level() overhead is <5μs.

        Uplifting is more common than creation (happens at every transform),
        so we use a tighter threshold (<5μs).

        Methodology:
        - Create one frame
        - Uplift 10,000 times
        - Measure average time per uplift
        - Assert average < 5μs
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

        # Assert: Average uplift time < 5μs
        assert avg_time_per_uplift < 5e-6, (
            f"Uplifting overhead too high: {avg_time_per_uplift*1e6:.2f}μs "
            f"(threshold: 5μs)"
        )

        # Print benchmark results
        print("\n✅ Uplifting Performance Benchmark:")
        print(f"   Total time (10,000 uplifts): {total_time:.4f}s")
        print(f"   Average per uplift: {avg_time_per_uplift*1e6:.2f}μs")
        print("   Threshold: 5μs")
        print(f"   Status: {'PASS' if avg_time_per_uplift < 5e-6 else 'FAIL'}")

    def test_with_new_data_overhead_acceptable(self):
        """Verify with_new_data() overhead is <10μs.

        This is used by LLM/aggregation plugins that generate new DataFrames.

        Methodology:
        - Create initial frame
        - Replace data 10,000 times
        - Measure average time per replacement
        - Assert average < 10μs
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

        # Assert: Average replacement time < 10μs
        assert avg_time_per_replacement < 10e-6, (
            f"with_new_data overhead too high: {avg_time_per_replacement*1e6:.2f}μs "
            f"(threshold: 10μs)"
        )

        # Print benchmark results
        print("\n✅ Data Replacement Performance Benchmark:")
        print(f"   Total time (10,000 replacements): {total_time:.4f}s")
        print(f"   Average per replacement: {avg_time_per_replacement*1e6:.2f}μs")
        print("   Threshold: 10μs")
        print(f"   Status: {'PASS' if avg_time_per_replacement < 10e-6 else 'FAIL'}")

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

✅ test_constructor_overhead_acceptable
   - Measures: create_from_datasource() time
   - Threshold: <10μs per creation
   - Rationale: Frame inspection (5-frame stack walk) overhead

✅ test_uplifting_overhead_acceptable
   - Measures: with_uplifted_security_level() time
   - Threshold: <5μs per uplift
   - Rationale: Most common operation, needs tighter bound

✅ test_with_new_data_overhead_acceptable
   - Measures: with_new_data() time
   - Threshold: <10μs per replacement
   - Rationale: LLM/aggregation pattern overhead

✅ test_suite_level_overhead_negligible (marked @slow)
   - Measures: Complete suite simulation (6 operations)
   - Threshold: <100μs per suite
   - Rationale: Real-world usage pattern
   - Context: 0.00003% of 5-minute suite execution

Performance Validation Strategy:
1. Microbenchmarks verify individual operations meet thresholds
2. Suite-level benchmark verifies combined overhead negligible
3. @slow mark prevents CI slowdown (run during nightly builds)

Expected Results (on modern hardware):
- Constructor: ~2-3μs (well under 10μs threshold)
- Uplifting: ~1-2μs (well under 5μs threshold)
- Data replacement: ~2-3μs (well under 10μs threshold)
- Suite overhead: ~15-20μs (well under 100μs threshold)

If tests fail:
- Check if running on slow hardware (CI runner, virtualized environment)
- Profile with cProfile to find bottleneck
- Consider caching validated callers (see ADR002A_EVALUATION.md)
"""
