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

from typing import Any, TypedDict

import pytest

# Importing pass_through ensures PassThroughDeclarationContract registers
# itself via its module-level side-effect before any benchmark runs.
import elspeth.engine.executors.pass_through  # noqa: F401
from elspeth.contracts.declaration_contracts import (
    DeclarationContract,
    ExampleBundle,
    PostEmissionInputs,
    PostEmissionOutputs,
    _clear_registry_for_tests,
    _restore_registry_snapshot_for_tests,
    _snapshot_registry_for_tests,
    implements_dispatch_site,
    register_declaration_contract,
)
from elspeth.contracts.errors import PassThroughContractViolation
from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
from elspeth.engine.executors.declaration_dispatch import run_post_emission_checks
from elspeth.engine.executors.pass_through import (
    PassThroughDeclarationContract,
    verify_pass_through,
)
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
        # buffered input contract. Measures the primitive cost; the live
        # ``_cross_check_flush_output`` path additionally routes through
        # ``run_runtime_checks`` and ``PassThroughDeclarationContract`` (ADR-010
        # §Decision 3), which adds the dispatcher-overhead benchmark's
        # measured overhead (~15 µs median) on top — well within the 1500 µs
        # budget for a 64-row batch.
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
    verify_pass_through call. Budget: median ≤ 27 µs at N=1
    (25 µs ADR-008 direct baseline + 2 µs ADR-010 §NFR dispatcher overhead).

    The dispatcher adds one ``registered_declaration_contracts()`` call + one
    ``applies_to()`` short-circuit + one ``runtime_check()`` invocation on top
    of the direct ``verify_pass_through`` call.

    This is the N=1 baseline fixed against the production registry at the
    time of writing. The paramterised ``test_dispatcher_overhead_scales_with_n``
    companion below tracks how the budget scales as 2B/2C adopters land
    (issue elspeth-5dae105959 / H1 — benchmark no longer degrades to
    theatre when N > 1).

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
    effective_input_fields = frozenset(fc.normalized_name for fc in input_row.contract.fields)
    inputs = PostEmissionInputs(
        plugin=plugin,
        node_id=plugin.node_id,
        run_id="bench_run",
        row_id="bench_row",
        token_id="bench_token",
        input_row=input_row,
        static_contract=static_contract,
        effective_input_fields=effective_input_fields,
    )
    outputs = PostEmissionOutputs(emitted_rows=(output_row,))

    def run_dispatcher() -> None:
        run_post_emission_checks(inputs=inputs, outputs=outputs)

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


# =============================================================================
# H1 — dispatcher-overhead scales with N (issue elspeth-5dae105959)
# =============================================================================
#
# The original dispatcher-overhead benchmark measures the live registry
# (N=1 today). As Phase 2B/2C adopters land, the registered set grows but a
# single-N benchmark would pass forever while production-N diverges — the
# NFR would degrade to theatre.
#
# The parametrised test below registers N-1 no-op contracts (applies_to
# always returns False, so runtime_check is never invoked) plus the real
# PassThroughDeclarationContract (the one contract that DOES apply) and
# measures the dispatcher under increasing N. The budget scales with N per
# the derivation in ADR-010 §Consequences (NFR derivation) and fails the
# CI gate when the scaling law drifts.


class _NoopPayload(TypedDict):
    reason: str


class _NoopContract(DeclarationContract):
    """applies_to-returns-False stub for dispatcher scaling benchmarks.

    Ties up one registry slot without contributing any post_emission_check
    cost so the benchmark isolates the per-registered-contract dispatch-loop
    cost (tuple iteration + applies_to attribute read) from
    verify_pass_through's O(fields) work.
    """

    payload_schema: type = _NoopPayload

    def __init__(self, name: str) -> None:
        self.name = name

    def applies_to(self, plugin: Any) -> bool:
        return False

    @implements_dispatch_site("post_emission_check")
    def post_emission_check(
        self,
        inputs: PostEmissionInputs,
        outputs: PostEmissionOutputs,
    ) -> None:
        # Unreachable because applies_to is always False; kept for ABC
        # compliance.
        raise NotImplementedError

    @classmethod
    def negative_example(cls) -> ExampleBundle:
        raise NotImplementedError

    @classmethod
    def positive_example_does_not_apply(cls) -> ExampleBundle:
        raise NotImplementedError


@pytest.mark.performance
@pytest.mark.benchmark(group="dispatcher-overhead-scaling")
@pytest.mark.parametrize("n_contracts", [1, 2, 4, 8, 16])
def test_dispatcher_overhead_scales_with_n(
    benchmark: pytest.FixtureRequest,
    n_contracts: int,
) -> None:
    """NFR derivation (ADR-010 §Consequences, issue elspeth-5dae105959 / H1):

    per-row dispatcher overhead at N registered contracts is bounded by

        budget_median(N) = 27 us (N=1 baseline) + (N - 1) * 1.5 us

    where 1.5 us is the applies_to short-circuit cost per skipped contract
    with generous headroom for CI jitter on CPython 3.13 / Linux x86-64. The
    P99 proxy (mean + 3 * stddev) gets 2x the median budget. This is a
    deliberate over-estimate: the applies_to stub here is a plain attribute
    read and returns constant ``False``, so real-world contracts with a cheap
    guard (e.g. ``plugin.creates_tokens``) should hit well below 1.5 us.

    The fixed 2 µs at N=1 is the dispatcher's own structural cost —
    ``registered_declaration_contracts()`` tuple materialisation + loop
    enter — and does not scale with N.

    The benchmark registers N-1 no-op contracts + the real
    PassThroughDeclarationContract. N-1 contracts return False from
    applies_to (pure short-circuit), exactly one contract runs
    ``verify_pass_through`` on the 200-field row.

    Registry state is snapshot/restored so the benchmark does not leak into
    sibling tests.
    """

    class _PassThroughPlugin:
        name = "bench_dispatcher_scaling"
        node_id = "bench_dispatcher_scaling_node"
        passes_through_input = True
        _output_schema_config = None

    input_contract = _build_wide_contract(200)
    output_contract = _build_wide_contract(200)

    input_row = PipelineRow({f"field_{i}": f"v{i}" for i in range(200)}, input_contract)
    output_row = PipelineRow({f"field_{i}": f"v{i}" for i in range(200)}, output_contract)
    static_contract = frozenset(fc.normalized_name for fc in input_contract.fields)

    plugin = _PassThroughPlugin()
    effective_input_fields = frozenset(fc.normalized_name for fc in input_row.contract.fields)
    inputs = PostEmissionInputs(
        plugin=plugin,
        node_id=plugin.node_id,
        run_id="bench_run",
        row_id="bench_row",
        token_id="bench_token",
        input_row=input_row,
        static_contract=static_contract,
        effective_input_fields=effective_input_fields,
    )
    outputs = PostEmissionOutputs(emitted_rows=(output_row,))

    snapshot = _snapshot_registry_for_tests()
    try:
        _clear_registry_for_tests()
        # Real pass-through contract — the one that applies + invokes
        # post_emission_check. The 200-field verify_pass_through dominates
        # the measurement and anchors the N=1 baseline.
        register_declaration_contract(PassThroughDeclarationContract())
        # N-1 no-op contracts — exercise only the applies_to short-circuit
        # path. Names are distinct to satisfy registry uniqueness.
        for i in range(n_contracts - 1):
            register_declaration_contract(_NoopContract(name=f"noop_scaling_{i}"))

        def run_dispatcher() -> None:
            run_post_emission_checks(inputs=inputs, outputs=outputs)

        benchmark(run_dispatcher)
    finally:
        _restore_registry_snapshot_for_tests(snapshot)

    stats = benchmark.stats
    median_sec = stats["median"]
    mean_sec = stats["mean"]
    stddev_sec = stats["stddev"]
    p99_bound = mean_sec + 3 * stddev_sec

    # Scaling formula (see docstring). 1.5 µs per skipped contract is a
    # generous bound — a regression that halves the applies_to cost is
    # still captured by the P99 proxy.
    median_budget_us = 27.0 + (n_contracts - 1) * 1.5
    p99_budget_us = median_budget_us * 2.0
    assert median_sec * 1e6 < median_budget_us, (
        f"Dispatcher median {median_sec * 1e6:.1f}us exceeds {median_budget_us:.1f}us "
        f"budget at N={n_contracts} (27us N=1 baseline + {n_contracts - 1} * 1.5us per-skip; "
        f"ADR-010 §NFR derivation)"
    )
    assert p99_bound * 1e6 < p99_budget_us, (
        f"Dispatcher mean+3*stddev {p99_bound * 1e6:.1f}us exceeds {p99_budget_us:.1f}us "
        f"P99 budget at N={n_contracts} "
        f"(mean={mean_sec * 1e6:.1f}us, stddev={stddev_sec * 1e6:.1f}us)"
    )
