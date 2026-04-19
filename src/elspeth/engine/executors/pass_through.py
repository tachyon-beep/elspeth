"""Runtime verification of ``passes_through_input=True`` declarations.

ADR-008 introduced the runtime cross-check for ``passes_through_input``
transforms; ADR-009 §Clause 2 extracts it here so the single-token executor
and the batch aggregation flush path share one verification implementation.

Two call sites import ``verify_pass_through``:

- ``engine/executors/transform.py::TransformExecutor.execute_transform`` —
  single-token and mixin-based batch-aware transforms.
- ``engine/processor.py::RowProcessor._cross_check_flush_output`` — batch
  aggregation flush path.

The OpenTelemetry violation counter lives at module level so both call sites
increment the same instrument. Cardinality is bounded by the annotated
transform set (short, known at startup), so the ``transform=<name>`` tag is
safe.
"""

from __future__ import annotations

from collections.abc import Sequence

from opentelemetry import metrics

from elspeth.contracts.errors import FrameworkBugError, PassThroughContractViolation
from elspeth.contracts.schema_contract import PipelineRow

# Module-level counter — both call sites import this module and share the
# same instrument. Previously lived on the TransformExecutor instance; moving
# it to module scope removes the need to pass it through the processor's
# constructor when the batch-flush path joins in.
_VIOLATIONS_COUNTER = metrics.get_meter(__name__).create_counter(
    "pass_through_cross_check_violations_total",
    description="Count of passes_through_input=True transforms that dropped input fields at runtime",
)


def verify_pass_through(
    *,
    input_fields: frozenset[str],
    emitted_rows: Sequence[PipelineRow],
    static_contract: frozenset[str],
    transform_name: str,
    transform_node_id: str,
    run_id: str,
    row_id: str,
    token_id: str,
) -> None:
    """Verify every emitted row preserves ``input_fields``.

    A field is "preserved" iff the emitted row's contract declares it AND its
    payload carries it. ``PipelineRow`` treats contract and payload as
    independent references; reading either alone leaves a one-sided blind
    spot, so runtime observation is the intersection of both.

    Raises :class:`PassThroughContractViolation` on the first row that drops
    any input field. The violation is registered in ``TIER_1_ERRORS`` —
    on_error routing cannot absorb it; the orchestrator must propagate.

    Empty ``emitted_rows`` is a no-op under the ADR-009 §Clause 3
    empty-emission carve-out (filter semantics are compatible with
    ``passes_through_input=True``: emitting nothing drops nothing). Track 2
    will introduce a separate ``can_drop_rows`` declaration to tighten this
    case.

    Args:
        input_fields: Fields the input row(s) carry. For batch mode callers,
            this is the intersection of all buffered input contracts
            (ADR-007 table line 53, batch-homogeneous rule).
        emitted_rows: Rows the transform produced.
        static_contract: Fields the static validator computed for the
            transform's output; surfaced in the violation for triage.
        transform_name: Plugin name (for counter tag and message).
        transform_node_id: DAG node identifier.
        run_id: Current pipeline run.
        row_id: Source row identifier (triggering token's row_id in batch
            mode; the single token's row_id in single-token mode).
        token_id: DAG token identifier (triggering token in batch mode).

    Raises:
        FrameworkBugError: Emitted row has no contract (framework invariant
            violation — ``PipelineRow.__init__`` always sets one).
        PassThroughContractViolation: Any emitted row drops a field named
            in ``input_fields``. The violation carries the full divergence
            set; callers are responsible for any audit recording that must
            precede propagation.
    """
    if not emitted_rows:
        return

    for emitted in emitted_rows:
        if emitted.contract is None:
            raise FrameworkBugError(f"Transform {transform_name!r} emitted row with no contract. Framework invariant violated.")
        runtime_contract_fields = frozenset(fc.normalized_name for fc in emitted.contract.fields)
        runtime_payload_fields = frozenset(emitted.keys())
        runtime_observed = runtime_contract_fields & runtime_payload_fields
        divergence = input_fields - runtime_observed
        if divergence:
            # Increment BEFORE raising so the metric captures the event
            # independently of downstream serialization outcome.
            _VIOLATIONS_COUNTER.add(1, {"transform": transform_name})
            raise PassThroughContractViolation(
                transform=transform_name,
                transform_node_id=transform_node_id,
                run_id=run_id,
                row_id=row_id,
                token_id=token_id,
                static_contract=static_contract,
                runtime_observed=runtime_observed,
                divergence_set=frozenset(divergence),
                message=(
                    f"Transform {transform_name!r} (node {transform_node_id!r}) "
                    f"declared passes_through_input=True but dropped fields "
                    f"{sorted(divergence)!r} from row {row_id!r}."
                ),
            )
