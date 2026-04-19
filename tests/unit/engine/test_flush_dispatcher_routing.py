"""Regression test for filigree issue elspeth-ef8d5d92ff (C1 dispatcher bypass).

ADR-010 §Decision 3 makes ``run_runtime_checks`` the single source of truth
for per-row declaration-contract enforcement. This file probes the wiring:
a synthetic ``_CountingContract`` is registered for the duration of the
test, and every per-row verification path must invoke it.

Covered paths (all must fire the dispatcher):

- Single-token transform (``TransformExecutor``) — already routed pre-fix.
- Batch-flush PASSTHROUGH mode (``RowProcessor._cross_check_flush_output``) —
  already routed pre-fix.
- Batch-flush TRANSFORM mode (same method) — **the gap** this test
  proves closed. Pre-fix the counter will stay at zero for this path.

The test also asserts that the TRANSFORM-flush branch passes the batch-wide
field intersection via ``RuntimeCheckInputs.override_input_fields`` (ADR-009
§Clause 2 batch-homogeneous semantics) — that field is the vehicle the fix
uses to express "use these fields, not the single input_row's contract."
"""

from __future__ import annotations

from typing import Any, ClassVar, TypedDict
from unittest.mock import Mock

import pytest

from elspeth.contracts import TokenInfo, TransformProtocol, TransformResult
from elspeth.contracts.declaration_contracts import (
    RuntimeCheckInputs,
    RuntimeCheckOutputs,
    _clear_registry_for_tests,
    _restore_registry_snapshot_for_tests,
    _snapshot_registry_for_tests,
    register_declaration_contract,
)
from elspeth.contracts.enums import OutputMode
from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
from elspeth.contracts.types import NodeID
from elspeth.core.config import AggregationSettings, TriggerConfig
from elspeth.engine.processor import _FlushContext
from elspeth.testing import make_contract, make_token_info
from tests.fixtures.landscape import make_recorder_with_run

# ---------------------------------------------------------------------------
# Counting contract: records each invocation's (token_id, override_input_fields)
# ---------------------------------------------------------------------------


class _CountingPayload(TypedDict):
    token_id: str


class _CountingContract:
    """Minimal contract that records every dispatcher invocation.

    Always applies. Never raises. Captures ``token_id`` and
    ``override_input_fields`` so tests can assert both that the dispatcher
    fired AND that the batch-flush TRANSFORM path passes the intersection
    via the override channel.
    """

    name = "counting_test_contract"
    payload_schema: type = _CountingPayload
    # Shared class-level bucket — the ``_isolate_registry`` fixture resets it
    # per test, so mutable class state here is intentional, not a leak.
    invocations: ClassVar[list[tuple[str, frozenset[str] | None]]] = []

    def applies_to(self, plugin: Any) -> bool:
        return True

    def runtime_check(self, inputs: RuntimeCheckInputs, outputs: RuntimeCheckOutputs) -> None:
        _CountingContract.invocations.append((inputs.token_id, inputs.override_input_fields))

    @classmethod
    def negative_example(cls) -> tuple[RuntimeCheckInputs, RuntimeCheckOutputs]:
        # Required by the DeclarationContract protocol. The registry validator
        # checks that ``negative_example`` is callable; the invariant harness
        # (tests/invariants/) verifies it triggers a violation for contracts
        # registered at harness start. This counting contract is registered
        # *inside* the isolation fixture and torn down before any invariant
        # harness runs, so this trivial implementation is never executed by
        # the invariant harness. We still return a well-formed pair.
        return (
            RuntimeCheckInputs(
                plugin=object(),
                node_id="n",
                run_id="r",
                row_id="rw",
                token_id="t",
                input_row=object(),
                static_contract=frozenset(),
            ),
            RuntimeCheckOutputs(emitted_rows=(object(),)),
        )


# ---------------------------------------------------------------------------
# Processor / flush-context builders (mirror existing test file conventions)
# ---------------------------------------------------------------------------


def _make_contract(fields: dict[str, type]) -> SchemaContract:
    return make_contract(fields=fields, mode="OBSERVED")


def _make_token(
    token_id: str,
    data: dict[str, Any],
    contract: SchemaContract,
    *,
    row_id: str | None = None,
) -> TokenInfo:
    row = PipelineRow(data, contract)
    token = make_token_info(token_id=token_id, row_id=row_id or f"row-{token_id}")
    return token.with_updated_data(row)


def _make_flush_transform(*, passes_through_input: bool = True) -> Mock:
    transform = Mock(spec=TransformProtocol)
    transform.node_id = "agg-node"
    transform.name = "test-transform"
    transform.on_error = "discard"
    transform.on_success = None
    transform.is_batch_aware = True
    transform.creates_tokens = False
    transform.passes_through_input = passes_through_input
    transform._output_schema_config = None
    return transform


def _make_fctx(
    *,
    transform: Any,
    tokens: list[TokenInfo],
    output_mode: OutputMode,
) -> _FlushContext:
    settings = AggregationSettings(
        name="agg",
        plugin="batch_transform",
        input="source-0",
        on_success="output",
        on_error="discard",
        trigger=TriggerConfig(count=len(tokens)),
        output_mode=output_mode,
    )
    return _FlushContext(
        node_id=NodeID("agg-node"),
        transform=transform,
        settings=settings,
        buffered_tokens=tuple(tokens),
        batch_id="batch-1",
        error_msg="batch failed",
        expand_parent_token=tokens[0],
        triggering_token=tokens[-1],
        coalesce_node_id=None,
        coalesce_name=None,
    )


def _make_processor() -> Any:
    """Minimal processor capable of driving ``_cross_check_flush_output``."""
    from elspeth.engine.processor import DAGTraversalContext, RowProcessor
    from elspeth.engine.spans import SpanFactory

    setup = make_recorder_with_run(
        run_id="test-run",
        source_node_id="source-0",
        source_plugin_name="test-source",
    )
    traversal = DAGTraversalContext(
        node_step_map={NodeID("source-0"): 0, NodeID("agg-node"): 1},
        node_to_plugin={},
        first_transform_node_id=None,
        node_to_next={NodeID("source-0"): None, NodeID("agg-node"): None},
        coalesce_node_map={},
    )
    return RowProcessor(
        execution=setup.factory.execution,
        data_flow=setup.factory.data_flow,
        span_factory=SpanFactory(),
        run_id="test-run",
        source_node_id=NodeID("source-0"),
        source_on_success="default",
        traversal=traversal,
    )


# ---------------------------------------------------------------------------
# Registry isolation (snapshot + clear + restore)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_registry():
    """Snapshot the registry so the test can register the counting contract
    without leaking into sibling tests and without losing
    PassThroughDeclarationContract's module-level self-registration."""
    snapshot = _snapshot_registry_for_tests()
    _clear_registry_for_tests()
    _CountingContract.invocations = []
    # Register ONLY the counting contract for this test. We intentionally do
    # not re-register PassThroughDeclarationContract — the dispatcher must
    # fire the counting contract regardless of what else is registered, and
    # keeping the registry minimal isolates the test's signal from
    # pass-through's semantics.
    register_declaration_contract(_CountingContract())
    yield
    _restore_registry_snapshot_for_tests(snapshot)


# ---------------------------------------------------------------------------
# Tests — batch-flush routing
# ---------------------------------------------------------------------------


class TestBatchFlushDispatcherRouting:
    """All four batch-flush scenarios must invoke the registered dispatcher."""

    def test_passthrough_mode_fires_dispatcher_per_token(self) -> None:
        """PASSTHROUGH flush already routes through the dispatcher (regression guard)."""
        processor = _make_processor()
        contract = _make_contract({"x": int})
        tokens = [_make_token(f"t{i}", {"x": i}, contract) for i in range(3)]
        transform = _make_flush_transform()
        fctx = _make_fctx(transform=transform, tokens=tokens, output_mode=OutputMode.PASSTHROUGH)
        rows = [PipelineRow({"x": i}, contract) for i in range(3)]
        result = TransformResult.success_multi(rows, success_reason={"action": "pt"})

        processor._cross_check_flush_output(fctx, result)

        # Dispatcher fired once per token pair.
        assert len(_CountingContract.invocations) == 3
        seen_token_ids = {inv[0] for inv in _CountingContract.invocations}
        assert seen_token_ids == {"t0", "t1", "t2"}
        # PASSTHROUGH mode uses the single input_row's contract, so override is None.
        for _token_id, override in _CountingContract.invocations:
            assert override is None, f"PASSTHROUGH must not set override, got {override!r}"

    def test_transform_mode_fires_dispatcher_per_emitted_row(self) -> None:
        """TRANSFORM-flush must route through the dispatcher (the C1 gap).

        Pre-fix: ``_cross_check_flush_output`` calls ``verify_pass_through``
        directly on this branch, so the counting contract never fires and
        ``invocations`` stays empty. This assertion is the red/green marker
        for the fix.
        """
        processor = _make_processor()
        contract = _make_contract({"x": int, "y": int})
        tokens = [_make_token(f"t{i}", {"x": i, "y": i * 10}, contract) for i in range(3)]
        transform = _make_flush_transform()
        fctx = _make_fctx(transform=transform, tokens=tokens, output_mode=OutputMode.TRANSFORM)
        # 6 emitted rows (N:M expansion) all carrying the full input fields.
        rows = [PipelineRow({"x": i, "y": i * 10}, contract) for i in range(6)]
        result = TransformResult.success_multi(rows, success_reason={"action": "expand"})

        processor._cross_check_flush_output(fctx, result)

        # Pre-fix: 0. Post-fix: 1 (TRANSFORM emits one dispatcher call per flush,
        # batch-homogeneous semantics mean one check covers all emitted rows).
        assert len(_CountingContract.invocations) >= 1, "TRANSFORM-flush bypassed dispatcher (C1 regression)"

    def test_transform_mode_passes_batch_intersection_as_override(self) -> None:
        """Batch intersection must reach the dispatcher via override_input_fields.

        Heterogeneous batch: token t0 has {x, y}, token t1 has {x, z}.
        The intersection is {x}; that is what every emitted row must preserve
        under ADR-009 §Clause 2, so the dispatcher must receive it.
        """
        processor = _make_processor()
        contract_xy = _make_contract({"x": int, "y": int})
        contract_xz = _make_contract({"x": int, "z": int})
        tokens = [
            _make_token("t0", {"x": 1, "y": 10}, contract_xy),
            _make_token("t1", {"x": 2, "z": 20}, contract_xz),
        ]
        transform = _make_flush_transform()
        fctx = _make_fctx(transform=transform, tokens=tokens, output_mode=OutputMode.TRANSFORM)
        # Rows carry full input fields; intersection check is about what the
        # dispatcher receives, not about producing a violation.
        reduced = _make_contract({"x": int})
        rows = [PipelineRow({"x": 1}, reduced), PipelineRow({"x": 2}, reduced)]
        result = TransformResult.success_multi(rows, success_reason={"action": "intersect"})

        processor._cross_check_flush_output(fctx, result)

        assert len(_CountingContract.invocations) >= 1, "TRANSFORM-flush bypassed dispatcher (C1 regression)"
        # Every invocation on the TRANSFORM-flush branch must carry the batch
        # intersection as override_input_fields.
        for token_id, override in _CountingContract.invocations:
            assert override == frozenset({"x"}), f"Expected override_input_fields=frozenset({{'x'}}) for {token_id!r}, got {override!r}"

    def test_passes_through_false_still_skips_all_contracts(self) -> None:
        """When ``passes_through_input=False``, the flush path short-circuits
        before any dispatcher call. This preserves the existing semantics —
        non-pass-through transforms don't trigger pass-through verification,
        and other contracts would be invoked only if they apply to the
        non-pass-through path (which is separate routing, not this method).
        """
        processor = _make_processor()
        contract = _make_contract({"x": int})
        tokens = [_make_token(f"t{i}", {"x": i}, contract) for i in range(2)]
        transform = _make_flush_transform(passes_through_input=False)
        fctx = _make_fctx(transform=transform, tokens=tokens, output_mode=OutputMode.TRANSFORM)
        rows = [PipelineRow({}, _make_contract({}))] * 2
        result = TransformResult.success_multi(rows, success_reason={"action": "noop"})

        processor._cross_check_flush_output(fctx, result)

        assert _CountingContract.invocations == [], "Flush dispatcher fired despite passes_through_input=False"
