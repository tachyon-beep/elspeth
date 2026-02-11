"""Unit tests for RecoveryManager resume and row-recovery behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ConfigDict
from sqlalchemy import Connection

from elspeth.contracts import (
    Checkpoint,
    Determinism,
    NodeType,
    PayloadStore,
    PluginSchema,
    RowOutcome,
    RunStatus,
)
from elspeth.contracts.contract_records import ContractAuditRecord
from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.core.checkpoint import CheckpointCorruptionError, CheckpointManager, RecoveryManager
from elspeth.core.checkpoint.manager import IncompatibleCheckpointError
from elspeth.core.dag import ExecutionGraph
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.schema import (
    checkpoints_table,
    nodes_table,
    rows_table,
    runs_table,
    token_outcomes_table,
    tokens_table,
)
from tests.fixtures.landscape import make_landscape_db


@pytest.fixture
def db() -> LandscapeDB:
    return make_landscape_db()


@pytest.fixture
def checkpoint_manager(db: LandscapeDB) -> CheckpointManager:
    return CheckpointManager(db)


@pytest.fixture
def recovery_manager(db: LandscapeDB, checkpoint_manager: CheckpointManager) -> RecoveryManager:
    return RecoveryManager(db, checkpoint_manager)


def _create_contract() -> tuple[str, str]:
    contract = SchemaContract(
        mode="FIXED",
        fields=(
            FieldContract(
                normalized_name="id",
                original_name="id",
                python_type=int,
                required=True,
                source="declared",
            ),
        ),
        locked=True,
    )
    return ContractAuditRecord.from_contract(contract).to_json(), contract.version_hash()


def _create_graph(*, node_id: str = "checkpoint-node", config: dict[str, Any] | None = None) -> ExecutionGraph:
    graph = ExecutionGraph()
    graph.add_node(node_id, node_type=NodeType.TRANSFORM, plugin_name="test", config=config or {})
    return graph


def _insert_run(
    conn: Connection,
    run_id: str,
    *,
    status: RunStatus,
    with_contract: bool = False,
    contract_json_override: str | None = None,
) -> None:
    schema_contract_json: str | None = None
    schema_contract_hash: str | None = None
    if with_contract:
        schema_contract_json, schema_contract_hash = _create_contract()
    if contract_json_override is not None:
        schema_contract_json = contract_json_override
        # Intentionally mismatched when override is used for corruption tests.
        schema_contract_hash = "deadbeefdeadbeef"

    conn.execute(
        runs_table.insert().values(
            run_id=run_id,
            started_at=datetime.now(UTC),
            config_hash="cfg",
            settings_json="{}",
            canonical_version="sha256-rfc8785-v1",
            status=status,
            schema_contract_json=schema_contract_json,
            schema_contract_hash=schema_contract_hash,
        )
    )


def _insert_node(conn: Connection, run_id: str, node_id: str, *, node_type: NodeType = NodeType.TRANSFORM) -> None:
    conn.execute(
        nodes_table.insert().values(
            node_id=node_id,
            run_id=run_id,
            plugin_name="test",
            node_type=node_type,
            plugin_version="1.0.0",
            determinism=Determinism.DETERMINISTIC,
            config_hash="node_cfg",
            config_json="{}",
            registered_at=datetime.now(UTC),
        )
    )


def _insert_row(conn: Connection, run_id: str, row_id: str, *, row_index: int, source_data_ref: str | None) -> None:
    conn.execute(
        rows_table.insert().values(
            row_id=row_id,
            run_id=run_id,
            source_node_id="source-node",
            row_index=row_index,
            source_data_hash=f"hash-{row_id}",
            source_data_ref=source_data_ref,
            created_at=datetime.now(UTC),
        )
    )


def _insert_token(conn: Connection, token_id: str, row_id: str) -> None:
    conn.execute(
        tokens_table.insert().values(
            token_id=token_id,
            row_id=row_id,
            created_at=datetime.now(UTC),
        )
    )


def _insert_terminal_outcome(conn: Connection, run_id: str, token_id: str, *, outcome: RowOutcome = RowOutcome.COMPLETED) -> None:
    conn.execute(
        token_outcomes_table.insert().values(
            outcome_id=f"out-{token_id}",
            run_id=run_id,
            token_id=token_id,
            outcome=outcome.value,
            is_terminal=1,
            recorded_at=datetime.now(UTC),
            sink_name="sink",
        )
    )


def _create_failed_run_with_checkpoint(
    db: LandscapeDB,
    checkpoint_manager: CheckpointManager,
    run_id: str,
    *,
    checkpoint_node_id: str = "checkpoint-node",
    with_contract: bool = True,
    aggregation_state: dict[str, Any] | None = None,
    graph: ExecutionGraph | None = None,
) -> ExecutionGraph:
    active_graph = graph or _create_graph(node_id=checkpoint_node_id)

    with db.connection() as conn:
        _insert_run(conn, run_id, status=RunStatus.FAILED, with_contract=with_contract)
        _insert_node(conn, run_id, "source-node", node_type=NodeType.SOURCE)
        _insert_node(conn, run_id, checkpoint_node_id)
        _insert_row(conn, run_id, "row-0", row_index=0, source_data_ref=None)
        _insert_token(conn, "tok-0", "row-0")

    checkpoint_manager.create_checkpoint(
        run_id=run_id,
        token_id="tok-0",
        node_id=checkpoint_node_id,
        sequence_number=1,
        graph=active_graph,
        aggregation_state=aggregation_state,
    )
    return active_graph


def test_can_resume_returns_false_for_missing_run(recovery_manager: RecoveryManager) -> None:
    check = recovery_manager.can_resume("missing", _create_graph())
    assert check.can_resume is False
    assert check.reason == "Run missing not found"


def test_can_resume_rejects_completed_run(db: LandscapeDB, recovery_manager: RecoveryManager) -> None:
    with db.connection() as conn:
        _insert_run(conn, "run-completed", status=RunStatus.COMPLETED)

    check = recovery_manager.can_resume("run-completed", _create_graph())
    assert check.can_resume is False
    assert check.reason == "Run already completed successfully"


def test_can_resume_rejects_running_run(db: LandscapeDB, recovery_manager: RecoveryManager) -> None:
    with db.connection() as conn:
        _insert_run(conn, "run-running", status=RunStatus.RUNNING)

    check = recovery_manager.can_resume("run-running", _create_graph())
    assert check.can_resume is False
    assert check.reason == "Run is still in progress"


def test_can_resume_rejects_failed_run_without_checkpoint(db: LandscapeDB, recovery_manager: RecoveryManager) -> None:
    with db.connection() as conn:
        _insert_run(conn, "run-no-checkpoint", status=RunStatus.FAILED)

    check = recovery_manager.can_resume("run-no-checkpoint", _create_graph())
    assert check.can_resume is False
    assert check.reason == "No checkpoint found for recovery"


def test_can_resume_returns_reason_when_checkpoint_format_is_incompatible(
    db: LandscapeDB, recovery_manager: RecoveryManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    with db.connection() as conn:
        _insert_run(conn, "run-incompatible", status=RunStatus.FAILED)

    def _raise_incompatible(_run_id: str) -> None:
        raise IncompatibleCheckpointError("bad checkpoint format")

    monkeypatch.setattr(recovery_manager._checkpoint_manager, "get_latest_checkpoint", _raise_incompatible)
    check = recovery_manager.can_resume("run-incompatible", _create_graph())
    assert check.can_resume is False
    assert check.reason == "bad checkpoint format"


def test_can_resume_rejects_topology_mismatch(
    db: LandscapeDB,
    checkpoint_manager: CheckpointManager,
    recovery_manager: RecoveryManager,
) -> None:
    run_id = "run-topology-mismatch"
    original_graph = _create_failed_run_with_checkpoint(
        db,
        checkpoint_manager,
        run_id,
        graph=_create_graph(node_id="checkpoint-node", config={"version": 1}),
    )
    assert original_graph.has_node("checkpoint-node")

    changed_graph = _create_graph(node_id="checkpoint-node", config={"version": 2})
    check = recovery_manager.can_resume(run_id, changed_graph)
    assert check.can_resume is False
    assert check.reason is not None
    assert "configuration has changed" in check.reason


def test_can_resume_true_for_failed_run_with_valid_checkpoint(
    db: LandscapeDB, checkpoint_manager: CheckpointManager, recovery_manager: RecoveryManager
) -> None:
    run_id = "run-resumable"
    graph = _create_failed_run_with_checkpoint(db, checkpoint_manager, run_id)

    check = recovery_manager.can_resume(run_id, graph)
    assert check.can_resume is True
    assert check.reason is None


def test_get_resume_point_returns_none_when_run_cannot_resume(recovery_manager: RecoveryManager) -> None:
    assert recovery_manager.get_resume_point("missing", _create_graph()) is None


def test_get_resume_point_returns_none_if_checkpoint_missing_after_can_resume(
    db: LandscapeDB,
    recovery_manager: RecoveryManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with db.connection() as conn:
        _insert_run(conn, "run-race", status=RunStatus.FAILED, with_contract=True)

    monkeypatch.setattr(recovery_manager, "can_resume", lambda _run_id, _graph: type("Check", (), {"can_resume": True})())
    monkeypatch.setattr(recovery_manager._checkpoint_manager, "get_latest_checkpoint", lambda _run_id: None)

    assert recovery_manager.get_resume_point("run-race", _create_graph()) is None


def test_get_resume_point_restores_aggregation_state(
    db: LandscapeDB,
    checkpoint_manager: CheckpointManager,
    recovery_manager: RecoveryManager,
) -> None:
    run_id = "run-resume-point"
    graph = _create_failed_run_with_checkpoint(
        db,
        checkpoint_manager,
        run_id,
        aggregation_state={
            "_version": 1,
            "agg-node": {
                "tokens": [
                    {
                        "row_id": "row-buffered",
                        "token_id": "tok-buffered",
                        "row_data": {"id": 5},
                    }
                ]
            },
        },
    )

    resume_point = recovery_manager.get_resume_point(run_id, graph)
    assert resume_point is not None
    assert resume_point.token_id == "tok-0"
    assert resume_point.node_id == "checkpoint-node"
    assert resume_point.sequence_number == 1
    assert resume_point.aggregation_state is not None
    assert "agg-node" in resume_point.aggregation_state


def test_get_unprocessed_rows_returns_empty_when_no_checkpoint(recovery_manager: RecoveryManager) -> None:
    assert recovery_manager.get_unprocessed_rows("missing-run") == []


def test_get_unprocessed_rows_handles_fork_and_excludes_buffered_rows(
    db: LandscapeDB,
    checkpoint_manager: CheckpointManager,
    recovery_manager: RecoveryManager,
) -> None:
    run_id = "run-unprocessed-complex"
    graph = _create_graph(node_id="checkpoint-node")
    with db.connection() as conn:
        _insert_run(conn, run_id, status=RunStatus.FAILED, with_contract=True)
        _insert_node(conn, run_id, "source-node", node_type=NodeType.SOURCE)
        _insert_node(conn, run_id, "checkpoint-node")

        # row-completed: one completed token -> should be excluded.
        _insert_row(conn, run_id, "row-completed", row_index=0, source_data_ref=None)
        _insert_token(conn, "tok-completed", "row-completed")
        _insert_terminal_outcome(conn, run_id, "tok-completed", outcome=RowOutcome.COMPLETED)

        # row-delegation-only: FORKED parent only, no child terminal -> should be included.
        _insert_row(conn, run_id, "row-delegation-only", row_index=1, source_data_ref=None)
        _insert_token(conn, "tok-parent", "row-delegation-only")
        _insert_terminal_outcome(conn, run_id, "tok-parent", outcome=RowOutcome.FORKED)

        # row-child-pending: one completed child + one pending child -> should be included.
        _insert_row(conn, run_id, "row-child-pending", row_index=2, source_data_ref=None)
        _insert_token(conn, "tok-child-ok", "row-child-pending")
        _insert_terminal_outcome(conn, run_id, "tok-child-ok", outcome=RowOutcome.COMPLETED)
        _insert_token(conn, "tok-child-pending", "row-child-pending")

        # row-buffered: appears incomplete but is buffered in checkpoint state -> excluded.
        _insert_row(conn, run_id, "row-buffered", row_index=3, source_data_ref=None)
        _insert_token(conn, "tok-buffered", "row-buffered")

    checkpoint_manager.create_checkpoint(
        run_id=run_id,
        token_id="tok-completed",
        node_id="checkpoint-node",
        sequence_number=10,
        graph=graph,
        aggregation_state={
            "_version": 1,
            "agg-node": {"tokens": [{"row_id": "row-buffered"}]},
        },
    )

    unprocessed = recovery_manager.get_unprocessed_rows(run_id)
    assert unprocessed == ["row-delegation-only", "row-child-pending"]


class _SimpleSchema(PluginSchema):
    model_config = ConfigDict(strict=False)
    id: int


class _EmptySchema(PluginSchema):
    model_config = ConfigDict(strict=False)


def test_get_unprocessed_row_data_returns_empty_when_no_rows(
    recovery_manager: RecoveryManager,
    payload_store: PayloadStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(recovery_manager, "get_unprocessed_rows", lambda _run_id: [])
    assert recovery_manager.get_unprocessed_row_data("run", payload_store, source_schema_class=_SimpleSchema) == []


def test_get_unprocessed_row_data_errors_when_row_missing_from_metadata(
    recovery_manager: RecoveryManager,
    payload_store: PayloadStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(recovery_manager, "get_unprocessed_rows", lambda _run_id: ["row-missing"])
    with pytest.raises(ValueError, match="Row row-missing not found in database"):
        recovery_manager.get_unprocessed_row_data("run", payload_store, source_schema_class=_SimpleSchema)


def test_get_unprocessed_row_data_errors_on_missing_source_data_ref(
    db: LandscapeDB,
    recovery_manager: RecoveryManager,
    payload_store: PayloadStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with db.connection() as conn:
        _insert_run(conn, "run-meta", status=RunStatus.FAILED)
        _insert_node(conn, "run-meta", "source-node", node_type=NodeType.SOURCE)
        _insert_row(conn, "run-meta", "row-1", row_index=1, source_data_ref=None)

    monkeypatch.setattr(recovery_manager, "get_unprocessed_rows", lambda _run_id: ["row-1"])
    with pytest.raises(ValueError, match="has no source_data_ref"):
        recovery_manager.get_unprocessed_row_data("run-meta", payload_store, source_schema_class=_SimpleSchema)


def test_get_unprocessed_row_data_errors_when_payload_purged(
    db: LandscapeDB,
    recovery_manager: RecoveryManager,
    payload_store: PayloadStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_ref = "f" * 64
    with db.connection() as conn:
        _insert_run(conn, "run-purged", status=RunStatus.FAILED)
        _insert_node(conn, "run-purged", "source-node", node_type=NodeType.SOURCE)
        _insert_row(conn, "run-purged", "row-1", row_index=1, source_data_ref=missing_ref)

    monkeypatch.setattr(recovery_manager, "get_unprocessed_rows", lambda _run_id: ["row-1"])
    with pytest.raises(ValueError, match="payload has been purged"):
        recovery_manager.get_unprocessed_row_data("run-purged", payload_store, source_schema_class=_SimpleSchema)


def test_get_unprocessed_row_data_errors_when_schema_discards_all_fields(
    db: LandscapeDB,
    recovery_manager: RecoveryManager,
    payload_store: PayloadStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload_ref = payload_store.store(b'{"id": 123}')
    with db.connection() as conn:
        _insert_run(conn, "run-empty-schema", status=RunStatus.FAILED)
        _insert_node(conn, "run-empty-schema", "source-node", node_type=NodeType.SOURCE)
        _insert_row(conn, "run-empty-schema", "row-1", row_index=1, source_data_ref=payload_ref)

    monkeypatch.setattr(recovery_manager, "get_unprocessed_rows", lambda _run_id: ["row-1"])
    with pytest.raises(ValueError, match="Schema validation returned empty data"):
        recovery_manager.get_unprocessed_row_data("run-empty-schema", payload_store, source_schema_class=_EmptySchema)


def test_get_unprocessed_row_data_chunked_lookup_and_type_restoration(
    db: LandscapeDB,
    recovery_manager: RecoveryManager,
    payload_store: PayloadStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload_ref_a = payload_store.store(b'{"id": "1"}')
    payload_ref_b = payload_store.store(b'{"id": "2"}')
    with db.connection() as conn:
        _insert_run(conn, "run-chunked", status=RunStatus.FAILED)
        _insert_node(conn, "run-chunked", "source-node", node_type=NodeType.SOURCE)
        _insert_row(conn, "run-chunked", "row-a", row_index=2, source_data_ref=payload_ref_a)
        _insert_row(conn, "run-chunked", "row-b", row_index=5, source_data_ref=payload_ref_b)

    monkeypatch.setattr(recovery_manager, "get_unprocessed_rows", lambda _run_id: ["row-a", "row-b"])
    monkeypatch.setattr("elspeth.core.checkpoint.recovery._METADATA_CHUNK_SIZE", 1)

    rows = recovery_manager.get_unprocessed_row_data("run-chunked", payload_store, source_schema_class=_SimpleSchema)
    assert rows == [("row-a", 2, {"id": 1}), ("row-b", 5, {"id": 2})]


def test_verify_contract_integrity_returns_contract(
    db: LandscapeDB,
    recovery_manager: RecoveryManager,
) -> None:
    with db.connection() as conn:
        _insert_run(conn, "run-contract-ok", status=RunStatus.FAILED, with_contract=True)

    contract = recovery_manager.verify_contract_integrity("run-contract-ok")
    assert isinstance(contract, SchemaContract)
    assert contract.mode == "FIXED"
    assert len(contract.fields) == 1


def test_verify_contract_integrity_raises_when_contract_missing(
    db: LandscapeDB,
    recovery_manager: RecoveryManager,
) -> None:
    with db.connection() as conn:
        _insert_run(conn, "run-contract-missing", status=RunStatus.FAILED, with_contract=False)

    with pytest.raises(CheckpointCorruptionError, match="Schema contract is missing"):
        recovery_manager.verify_contract_integrity("run-contract-missing")


def test_verify_contract_integrity_raises_on_hash_mismatch(
    db: LandscapeDB,
    recovery_manager: RecoveryManager,
) -> None:
    valid_contract_json, _ = _create_contract()
    tampered = valid_contract_json.replace('"version_hash":"', '"version_hash":"deadbeef')
    with db.connection() as conn:
        _insert_run(
            conn,
            "run-contract-bad-hash",
            status=RunStatus.FAILED,
            contract_json_override=tampered,
        )

    with pytest.raises(CheckpointCorruptionError, match="Contract integrity verification failed"):
        recovery_manager.verify_contract_integrity("run-contract-bad-hash")


def test_get_run_private_helper_returns_none_for_missing_run(recovery_manager: RecoveryManager) -> None:
    assert recovery_manager._get_run("missing-run") is None


def test_get_run_private_helper_returns_row_for_existing_run(
    db: LandscapeDB,
    recovery_manager: RecoveryManager,
) -> None:
    with db.connection() as conn:
        _insert_run(conn, "run-present", status=RunStatus.FAILED)

    row = recovery_manager._get_run("run-present")
    assert row is not None
    assert row.run_id == "run-present"


def test_get_unprocessed_rows_returns_empty_when_checkpoint_manager_returns_none(
    db: LandscapeDB,
    recovery_manager: RecoveryManager,
) -> None:
    with db.connection() as conn:
        _insert_run(conn, "run-without-cp", status=RunStatus.FAILED)

    assert recovery_manager.get_unprocessed_rows("run-without-cp") == []


def test_get_unprocessed_rows_handles_delegation_token_with_completed_leaf(
    db: LandscapeDB,
    checkpoint_manager: CheckpointManager,
    recovery_manager: RecoveryManager,
) -> None:
    run_id = "run-fork-complete"
    graph = _create_graph(node_id="checkpoint-node")
    with db.connection() as conn:
        _insert_run(conn, run_id, status=RunStatus.FAILED, with_contract=True)
        _insert_node(conn, run_id, "source-node", node_type=NodeType.SOURCE)
        _insert_node(conn, run_id, "checkpoint-node")
        _insert_row(conn, run_id, "row-forked-complete", row_index=1, source_data_ref=None)
        _insert_token(conn, "tok-parent", "row-forked-complete")
        _insert_terminal_outcome(conn, run_id, "tok-parent", outcome=RowOutcome.FORKED)
        _insert_token(conn, "tok-child", "row-forked-complete")
        _insert_terminal_outcome(conn, run_id, "tok-child", outcome=RowOutcome.COMPLETED)

    checkpoint_manager.create_checkpoint(
        run_id=run_id,
        token_id="tok-child",
        node_id="checkpoint-node",
        sequence_number=1,
        graph=graph,
    )

    assert recovery_manager.get_unprocessed_rows(run_id) == []


def test_get_resume_point_reads_latest_checkpoint_after_can_resume(
    db: LandscapeDB,
    checkpoint_manager: CheckpointManager,
    recovery_manager: RecoveryManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "run-latest-checkpoint"
    graph = _create_failed_run_with_checkpoint(db, checkpoint_manager, run_id)
    with db.connection() as conn:
        conn.execute(
            checkpoints_table.insert().values(
                checkpoint_id="cp-later",
                run_id=run_id,
                token_id="tok-0",
                node_id="checkpoint-node",
                sequence_number=99,
                aggregation_state_json=None,
                created_at=datetime.now(UTC),
                upstream_topology_hash="x" * 64,
                checkpoint_node_config_hash="y" * 64,
                format_version=Checkpoint.CURRENT_FORMAT_VERSION,
            )
        )

    # Force can_resume to succeed so we exercise the second get_latest_checkpoint call path.
    monkeypatch.setattr(recovery_manager, "can_resume", lambda _run_id, _graph: type("Check", (), {"can_resume": True})())
    point = recovery_manager.get_resume_point(run_id, graph)

    assert point is not None
    assert point.sequence_number == 99
