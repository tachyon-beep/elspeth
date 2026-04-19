"""NFR gate for the pass-through runtime cross-check (ADR-008 / ADR-009).

Measures the per-row overhead of the live
``engine.executors.pass_through.verify_pass_through`` function on a 200-field
input row. Budget: median ≤ 25 µs, P99 (mean+3*stddev proxy) ≤ 50 µs.

A second benchmark covers the batch-flush path (ADR-009 §Clause 2) —
``RowProcessor._cross_check_flush_output`` calls ``verify_pass_through`` once
per emitted row with a batch-homogeneous ``input_fields``. The budget scales
with batch size: median ≤ 1500 µs, P99 ≤ 3000 µs for a 64-row batch.

Both benchmarks import and invoke the real function, not an inlined copy. An
inlined benchmark could pass while the live function regresses — the whole
point of this gate is to catch drift in the live code path.
"""

from __future__ import annotations

import pytest

# Importing pass_through ensures PassThroughDeclarationContract registers
# itself via its module-level side-effect before any benchmark runs.
import elspeth.engine.executors.pass_through  # noqa: F401
from elspeth.contracts.declaration_contracts import (
    RuntimeCheckInputs,
    RuntimeCheckOutputs,
)
from elspeth.contracts.errors import PassThroughContractViolation
from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
from elspeth.engine.executors.declaration_dispatch import run_runtime_checks
from elspeth.engine.executors.pass_through import verify_pass_through
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
    """Median ≤ 25 µs, P99 ≤ 50 µs on a 200-field row — single-token path.

    Calls the live ``verify_pass_through`` function (not an inlined copy) so
    the gate actually guards the code executed in production. Inputs are
    constructed so the contract holds and the function returns None —
    measuring the happy path, which is the dominant case under
    ``passes_through_input=True`` transforms that honour their contract.
    """
    input_contract = _build_wide_contract(200)
    output_contract = _build_wide_contract(200)

    input_row = PipelineRow({f"field_{i}": f"v{i}" for i in range(200)}, input_contract)
    output_row = PipelineRow({f"field_{i}": f"v{i}" for i in range(200)}, output_contract)
    input_fields = frozenset(fc.normalized_name for fc in input_row.contract.fields)
    emitted_rows = [output_row]

    def run_cross_check() -> None:
        verify_pass_through(
            input_fields=input_fields,
            emitted_rows=emitted_rows,
            static_contract=input_fields,
            transform_name="bench",
            transform_node_id="bench_node",
            run_id="bench_run",
            row_id="bench_row",
            token_id="bench_token",
        )

    benchmark(run_cross_check)

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
    """Sanity: the live function detects a dropped field.

    Exercises the payload-drop vector (contract reused, payload shrunk by one
    field). The buggy-plugin vector — contract still declares field_199 but
    payload omits it. ``verify_pass_through`` raises
    ``PassThroughContractViolation``; the benchmark catches it to include the
    raise path in the timing. The assertion confirms the violation's
    ``divergence_set`` is exactly the dropped field.
    """
    input_contract = _build_wide_contract(200)
    input_row = PipelineRow({f"field_{i}": f"v{i}" for i in range(200)}, input_contract)
    # Output reuses the contract but drops field_199 from payload.
    output_row = PipelineRow({f"field_{i}": f"v{i}" for i in range(199)}, input_contract)
    input_fields = frozenset(fc.normalized_name for fc in input_row.contract.fields)
    emitted_rows = [output_row]

    captured: dict[str, frozenset[str]] = {}

    def run_cross_check() -> None:
        try:
            verify_pass_through(
                input_fields=input_fields,
                emitted_rows=emitted_rows,
                static_contract=input_fields,
                transform_name="bench",
                transform_node_id="bench_node",
                run_id="bench_run",
                row_id="bench_row",
                token_id="bench_token",
            )
        except PassThroughContractViolation as violation:
            captured["divergence"] = violation.divergence_set

    benchmark(run_cross_check)
    assert captured.get("divergence") == frozenset({"field_199"})


@pytest.mark.performance
def test_batch_flush_cross_check_within_budget(benchmark: pytest.FixtureRequest) -> None:
    """Batch-flush path: median ≤ 1500 µs, P99 ≤ 3000 µs for 64-row batch.

    Models the ADR-009 §Clause 2 batch-aware path: ``verify_pass_through`` is
    invoked once per emitted row with ``input_fields`` computed as the
    intersection of all buffered input contracts (batch-homogeneous). The
    benchmark includes the intersection computation plus the per-row
    verification — the full flush-path cross-check cost for the operator.

    Budget rationale: single-token happy path ≤ 25 µs median; 64 rows ≈
    1600 µs upper bound with small intersection cost on top. Setting the
    budget at 1500 µs median / 3000 µs P99 gives headroom for the
    intersection (cheap) and any scheduler noise.
    """
    input_contract = _build_wide_contract(200)
    output_contract = _build_wide_contract(200)

    batch_size = 64
    buffered_rows = [PipelineRow({f"field_{i}": f"v{i}" for i in range(200)}, input_contract) for _ in range(batch_size)]
    emitted_rows = [PipelineRow({f"field_{i}": f"v{i}" for i in range(200)}, output_contract) for _ in range(batch_size)]
    static_contract = frozenset(fc.normalized_name for fc in input_contract.fields)

    def run_batch_cross_check() -> None:
        # Batch-homogeneous input_fields — intersection across every
        # buffered input contract. Identical to ``_cross_check_flush_output``.
        per_input_field_sets = [frozenset(fc.normalized_name for fc in row.contract.fields) for row in buffered_rows]
        input_fields = frozenset.intersection(*per_input_field_sets)
        verify_pass_through(
            input_fields=input_fields,
            emitted_rows=emitted_rows,
            static_contract=static_contract,
            transform_name="bench_batch",
            transform_node_id="bench_batch_node",
            run_id="bench_run",
            row_id="bench_row",
            token_id="bench_token",
        )

    benchmark(run_batch_cross_check)

    stats = benchmark.stats
    median_sec = stats["median"]
    mean_sec = stats["mean"]
    stddev_sec = stats["stddev"]
    p99_bound = mean_sec + 3 * stddev_sec
    assert median_sec < 1500e-6, f"Batch-flush median {median_sec * 1e6:.1f}us exceeds 1500us budget"
    assert p99_bound < 3000e-6, (
        f"Batch-flush mean+3*stddev {p99_bound * 1e6:.1f}us exceeds 3000us budget "
        f"(mean={mean_sec * 1e6:.1f}us, stddev={stddev_sec * 1e6:.1f}us)"
    )


@pytest.mark.performance
@pytest.mark.benchmark(group="dispatcher-overhead")
def test_dispatcher_overhead_vs_direct_verify_pass_through(benchmark: pytest.FixtureRequest) -> None:
    """Reviewer O2/O7: quantify the per-row dispatcher overhead vs direct
    verify_pass_through call. Budget: median ≤ 2 µs per registered contract
    for applies_to short-circuit + one invoked contract.

    The dispatcher adds one ``registered_declaration_contracts()`` call + one
    ``applies_to()`` short-circuit + one ``runtime_check()`` invocation on top
    of the direct ``verify_pass_through`` call. Total budget: median ≤ 27 µs
    (25 µs ADR-008 baseline + 2 µs dispatcher overhead budget per ADR-010
    §NFR).

    Setup mirrors the direct-call benchmark: a 200-field input row with a
    matching 200-field output row so the pass-through contract holds and the
    happy path is exercised. The plugin stub has ``passes_through_input=True``
    so ``PassThroughDeclarationContract.applies_to`` returns True and
    ``runtime_check`` is invoked.
    """

    class _PassThroughPlugin:
        """Minimal plugin stub satisfying PassThroughDeclarationContract.applies_to."""

        name = "bench_dispatcher"
        node_id = "bench_dispatcher_node"
        passes_through_input = True
        _output_schema_config = None

    input_contract = _build_wide_contract(200)
    output_contract = _build_wide_contract(200)

    input_row = PipelineRow({f"field_{i}": f"v{i}" for i in range(200)}, input_contract)
    output_row = PipelineRow({f"field_{i}": f"v{i}" for i in range(200)}, output_contract)
    static_contract = frozenset(fc.normalized_name for fc in input_contract.fields)

    plugin = _PassThroughPlugin()
    inputs = RuntimeCheckInputs(
        plugin=plugin,
        node_id=plugin.node_id,
        run_id="bench_run",
        row_id="bench_row",
        token_id="bench_token",
        input_row=input_row,
        static_contract=static_contract,
    )
    outputs = RuntimeCheckOutputs(emitted_rows=(output_row,))

    def run_dispatcher() -> None:
        run_runtime_checks(inputs=inputs, outputs=outputs)

    benchmark(run_dispatcher)

    stats = benchmark.stats
    median_sec = stats["median"]
    mean_sec = stats["mean"]
    stddev_sec = stats["stddev"]
    p99_bound = mean_sec + 3 * stddev_sec
    assert median_sec < 27e-6, (
        f"Dispatcher median {median_sec * 1e6:.1f}us exceeds 27us budget (25us direct + 2us dispatcher overhead per ADR-010 §NFR)"
    )
    assert p99_bound < 54e-6, (
        f"Dispatcher mean+3*stddev {p99_bound * 1e6:.1f}us exceeds 54us budget "
        f"(mean={mean_sec * 1e6:.1f}us, stddev={stddev_sec * 1e6:.1f}us)"
    )
