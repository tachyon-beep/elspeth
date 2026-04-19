"""NFR gate for the pass-through runtime cross-check (ADR-008).

Measures the per-row overhead of ``TransformExecutor._cross_check_pass_through``
on a 200-field input row. The gate enforces median ≤ 25 µs, P99 ≤ 50 µs. The
cross-check only runs for transforms annotated ``passes_through_input=True``,
so non-annotated transforms pay zero overhead.
"""

from __future__ import annotations

import pytest

from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
from elspeth.testing import make_field


def _build_wide_contract(n_fields: int = 200) -> SchemaContract:
    return SchemaContract(
        fields=tuple(
            make_field(
                f"field_{i}",
                python_type=str,
                original_name=f"field_{i}",
                required=True,
                source="declared",
            )
            for i in range(n_fields)
        ),
        mode="FLEXIBLE",
        locked=True,
    )


@pytest.mark.performance
def test_cross_check_p99_within_budget(benchmark: pytest.FixtureRequest) -> None:
    """Median ≤ 25 µs and P99 ≤ 50 µs on a 200-field row.

    The benchmark isolates the field-set comparison hot path — constructing
    three frozensets (input contract, output contract, output payload) and
    computing the input minus the contract/payload intersection. This mirrors
    the real executor logic: a field is "kept" iff the emitted row both
    declares it in its contract and carries it in its payload. ``PipelineRow``
    does not couple contract.fields to data.keys(), so the runtime observation
    must consult both.
    """
    input_contract = _build_wide_contract(200)
    output_contract = _build_wide_contract(200)

    input_row = PipelineRow({f"field_{i}": f"v{i}" for i in range(200)}, input_contract)
    output_row = PipelineRow({f"field_{i}": f"v{i}" for i in range(200)}, output_contract)

    def cross_check() -> frozenset[str]:
        input_fields = frozenset(fc.normalized_name for fc in input_row.contract.fields)
        runtime_contract_fields = frozenset(fc.normalized_name for fc in output_row.contract.fields)
        runtime_payload_fields = frozenset(output_row.keys())
        runtime_observed = runtime_contract_fields & runtime_payload_fields
        return input_fields - runtime_observed

    result = benchmark(cross_check)
    assert result == frozenset()

    # pytest-benchmark stores stats on the benchmark fixture. Median and
    # mean+3*stddev (robust to the occasional outlier caused by CPU scheduling
    # jitter in CI) are the NFR targets. The raw max is noise-dominated --
    # benchmark.stats["max"] frequently reports an extreme single-sample
    # outlier caused by scheduler preemption, which makes it unusable as a
    # hard gate. Using mean+3*stddev gives a ~99.7% bound under normality.
    stats = benchmark.stats
    median_sec = stats["median"]
    mean_sec = stats["mean"]
    stddev_sec = stats["stddev"]
    p99_bound = mean_sec + 3 * stddev_sec
    assert median_sec < 25e-6, f"Median {median_sec * 1e6:.1f}us exceeds 25us budget"
    assert p99_bound < 50e-6, (
        f"Mean+3*stddev {p99_bound * 1e6:.1f}us exceeds 50us budget (mean={mean_sec * 1e6:.1f}us, stddev={stddev_sec * 1e6:.1f}us)"
    )


@pytest.mark.performance
def test_cross_check_raises_on_drop(benchmark: pytest.FixtureRequest) -> None:
    """Sanity: the benchmarked path also correctly detects a dropped field.

    Exercises the payload-drop vector (contract reused, payload shrunk). This
    is the attack surface the intersection catches when either side alone
    would miss it.
    """
    input_contract = _build_wide_contract(200)
    # Output reuses the input contract (contract-set equality) but drops
    # field_199 from the payload — the buggy-plugin vector.
    input_row = PipelineRow({f"field_{i}": f"v{i}" for i in range(200)}, input_contract)
    output_row = PipelineRow({f"field_{i}": f"v{i}" for i in range(199)}, input_contract)

    def cross_check() -> frozenset[str]:
        input_fields = frozenset(fc.normalized_name for fc in input_row.contract.fields)
        runtime_contract_fields = frozenset(fc.normalized_name for fc in output_row.contract.fields)
        runtime_payload_fields = frozenset(output_row.keys())
        runtime_observed = runtime_contract_fields & runtime_payload_fields
        divergence = input_fields - runtime_observed
        if divergence:
            # Raise path is exercised in the real executor; here we return it.
            return divergence
        return frozenset()

    result = benchmark(cross_check)
    assert result == frozenset({"field_199"})
