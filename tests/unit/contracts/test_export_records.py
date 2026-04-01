"""Smoke tests for export record TypedDicts.

Verifies that each TypedDict can be instantiated with the expected field
types. Full correctness is verified by exporter integration tests.
"""

from elspeth.contracts.export_records import (
    ArtifactExportRecord,
    BatchExportRecord,
    BatchMemberExportRecord,
    CallExportRecord,
    EdgeExportRecord,
    NodeExportRecord,
    NodeStateExportRecord,
    OperationExportRecord,
    RoutingEventExportRecord,
    RowExportRecord,
    RunExportRecord,
    SecretResolutionExportRecord,
    TokenExportRecord,
    TokenOutcomeExportRecord,
    TokenParentExportRecord,
)


def test_run_export_record_construction() -> None:
    record: RunExportRecord = {
        "record_type": "run",
        "run_id": "run-1",
        "status": "COMPLETED",
        "started_at": "2024-01-01T00:00:00+00:00",
        "completed_at": "2024-01-01T00:01:00+00:00",
        "canonical_version": "1",
        "config_hash": "abc123",
        "settings": {"key": "value"},
        "reproducibility_grade": "DETERMINISTIC",
    }
    assert record["record_type"] == "run"
    assert record["reproducibility_grade"] == "DETERMINISTIC"


def test_run_export_record_optional_fields_none() -> None:
    record: RunExportRecord = {
        "record_type": "run",
        "run_id": "run-1",
        "status": "RUNNING",
        "started_at": None,
        "completed_at": None,
        "canonical_version": "1",
        "config_hash": "abc123",
        "settings": None,
        "reproducibility_grade": None,
    }
    assert record["started_at"] is None
    assert record["reproducibility_grade"] is None


def test_secret_resolution_export_record_construction() -> None:
    record: SecretResolutionExportRecord = {
        "record_type": "secret_resolution",
        "run_id": "run-1",
        "resolution_id": "res-1",
        "timestamp": 1704067200.0,  # Epoch seconds (not ISO string)
        "env_var_name": "MY_SECRET",
        "source": "azure_key_vault",
        "vault_url": "https://myvault.vault.azure.net",
        "secret_name": "my-secret",
        "fingerprint": "sha256:abcd",
        "resolution_latency_ms": 42.5,
    }
    assert record["record_type"] == "secret_resolution"
    assert record["resolution_latency_ms"] == 42.5


def test_secret_resolution_export_record_optional_none() -> None:
    record: SecretResolutionExportRecord = {
        "record_type": "secret_resolution",
        "run_id": "run-1",
        "resolution_id": "res-1",
        "timestamp": 1704067200.0,  # Epoch seconds (not ISO string)
        "env_var_name": "MY_SECRET",
        "source": "env",
        "vault_url": None,
        "secret_name": None,
        "fingerprint": None,
        "resolution_latency_ms": None,
    }
    assert record["vault_url"] is None


def test_node_export_record_construction() -> None:
    record: NodeExportRecord = {
        "record_type": "node",
        "run_id": "run-1",
        "node_id": "node-1",
        "plugin_name": "csv_source",
        "node_type": "SOURCE",
        "plugin_version": "1.0.0",
        "determinism": "DETERMINISTIC",
        "config_hash": "abc123",
        "config": {"path": "/data/input.csv"},
        "schema_hash": "def456",
        "schema_mode": "STRICT",
        "schema_fields": [{"name": "id", "type": "int"}],
        "sequence_in_pipeline": 0,
    }
    assert record["record_type"] == "node"
    assert record["schema_fields"] == [{"name": "id", "type": "int"}]


def test_node_export_record_optional_none() -> None:
    record: NodeExportRecord = {
        "record_type": "node",
        "run_id": "run-1",
        "node_id": "node-1",
        "plugin_name": "csv_source",
        "node_type": "SOURCE",
        "plugin_version": None,
        "determinism": "DETERMINISTIC",
        "config_hash": "abc123",
        "config": {},
        "schema_hash": None,
        "schema_mode": None,
        "schema_fields": None,
        "sequence_in_pipeline": None,
    }
    assert record["schema_fields"] is None


def test_edge_export_record_construction() -> None:
    record: EdgeExportRecord = {
        "record_type": "edge",
        "run_id": "run-1",
        "edge_id": "edge-1",
        "from_node_id": "node-1",
        "to_node_id": "node-2",
        "label": "continue",
        "default_mode": "PASS_THROUGH",
    }
    assert record["record_type"] == "edge"
    assert record["label"] == "continue"


def test_edge_export_record_label_none() -> None:
    record: EdgeExportRecord = {
        "record_type": "edge",
        "run_id": "run-1",
        "edge_id": "edge-1",
        "from_node_id": "node-1",
        "to_node_id": "node-2",
        "label": None,
        "default_mode": "PASS_THROUGH",
    }
    assert record["label"] is None


def test_operation_export_record_construction() -> None:
    record: OperationExportRecord = {
        "record_type": "operation",
        "run_id": "run-1",
        "operation_id": "op-1",
        "node_id": "node-1",
        "operation_type": "SOURCE_LOAD",
        "status": "COMPLETED",
        "started_at": "2024-01-01T00:00:00+00:00",
        "completed_at": "2024-01-01T00:00:01+00:00",
        "duration_ms": 1000.0,
        "error_message": None,
        "input_data_ref": None,
        "input_data_hash": None,
        "output_data_ref": "payload://abc",
        "output_data_hash": "sha256:abc",
    }
    assert record["record_type"] == "operation"
    assert record["duration_ms"] == 1000.0


def test_call_export_record_operation_parented() -> None:
    record: CallExportRecord = {
        "record_type": "call",
        "run_id": "run-1",
        "call_id": "call-1",
        "state_id": None,
        "operation_id": "op-1",
        "call_index": 0,
        "call_type": "HTTP",
        "status": "SUCCESS",
        "request_hash": "sha256:req",
        "response_hash": "sha256:res",
        "latency_ms": 250.0,
        "request_ref": "payload://req",
        "response_ref": "payload://res",
        "error_json": None,
        "created_at": "2024-01-01T00:00:00+00:00",
    }
    assert record["state_id"] is None
    assert record["operation_id"] == "op-1"


def test_call_export_record_state_parented() -> None:
    record: CallExportRecord = {
        "record_type": "call",
        "run_id": "run-1",
        "call_id": "call-2",
        "state_id": "state-1",
        "operation_id": None,
        "call_index": 0,
        "call_type": "LLM",
        "status": "SUCCESS",
        "request_hash": "sha256:req",
        "response_hash": "sha256:res",
        "latency_ms": 1500.0,
        "request_ref": None,
        "response_ref": None,
        "error_json": None,
        "created_at": "2024-01-01T00:00:00+00:00",
    }
    assert record["operation_id"] is None
    assert record["state_id"] == "state-1"


def test_row_export_record_construction() -> None:
    record: RowExportRecord = {
        "record_type": "row",
        "run_id": "run-1",
        "row_id": "row-1",
        "row_index": 0,
        "source_node_id": "node-1",
        "source_data_hash": "sha256:abc",
    }
    assert record["record_type"] == "row"
    assert record["row_index"] == 0


def test_token_export_record_construction() -> None:
    record: TokenExportRecord = {
        "record_type": "token",
        "run_id": "run-1",
        "token_id": "token-1",
        "row_id": "row-1",
        "step_in_pipeline": 0,  # int
        "branch_name": None,
        "fork_group_id": None,
        "join_group_id": None,
        "expand_group_id": None,
    }
    assert record["record_type"] == "token"
    assert record["fork_group_id"] is None


def test_token_export_record_step_none() -> None:
    record: TokenExportRecord = {
        "record_type": "token",
        "run_id": "run-1",
        "token_id": "token-2",
        "row_id": "row-1",
        "step_in_pipeline": None,  # int | None
        "branch_name": "left",
        "fork_group_id": "fg-1",
        "join_group_id": None,
        "expand_group_id": None,
    }
    assert record["step_in_pipeline"] is None


def test_token_parent_export_record_construction() -> None:
    record: TokenParentExportRecord = {
        "record_type": "token_parent",
        "run_id": "run-1",
        "token_id": "token-2",
        "parent_token_id": "token-1",
        "ordinal": 0,
    }
    assert record["record_type"] == "token_parent"
    assert record["ordinal"] == 0


def test_token_outcome_export_record_construction() -> None:
    record: TokenOutcomeExportRecord = {
        "record_type": "token_outcome",
        "run_id": "run-1",
        "outcome_id": "outcome-1",
        "token_id": "token-1",
        "outcome": "COMPLETED",
        "is_terminal": True,
        "recorded_at": "2024-01-01T00:00:00+00:00",
        "sink_name": "output",
        "batch_id": None,
        "fork_group_id": None,
        "join_group_id": None,
        "expand_group_id": None,
        "error_hash": None,
        "context_json": None,
        "expected_branches_json": None,
    }
    assert record["record_type"] == "token_outcome"
    assert record["is_terminal"] is True


def test_node_state_export_record_open_variant() -> None:
    record: NodeStateExportRecord = {
        "record_type": "node_state",
        "run_id": "run-1",
        "state_id": "state-1",
        "token_id": "token-1",
        "node_id": "node-1",
        "step_index": 0,
        "attempt": 1,
        "status": "OPEN",
        "input_hash": "sha256:in",
        "output_hash": None,
        "duration_ms": None,
        "started_at": "2024-01-01T00:00:00+00:00",
        "completed_at": None,
        "context_before_json": None,
        "context_after_json": None,
        "error_json": None,
        "success_reason_json": None,
    }
    assert record["status"] == "OPEN"
    assert record["output_hash"] is None


def test_node_state_export_record_completed_variant() -> None:
    record: NodeStateExportRecord = {
        "record_type": "node_state",
        "run_id": "run-1",
        "state_id": "state-1",
        "token_id": "token-1",
        "node_id": "node-1",
        "step_index": 0,
        "attempt": 1,
        "status": "COMPLETED",
        "input_hash": "sha256:in",
        "output_hash": "sha256:out",
        "duration_ms": 5.0,
        "started_at": "2024-01-01T00:00:00+00:00",
        "completed_at": "2024-01-01T00:00:01+00:00",
        "context_before_json": '{"k": "v"}',
        "context_after_json": '{"k": "v2"}',
        "error_json": None,
        "success_reason_json": '{"reason": "ok"}',
    }
    assert record["status"] == "COMPLETED"
    assert record["success_reason_json"] == '{"reason": "ok"}'


def test_routing_event_export_record_construction() -> None:
    record: RoutingEventExportRecord = {
        "record_type": "routing_event",
        "run_id": "run-1",
        "event_id": "event-1",
        "state_id": "state-1",
        "edge_id": "edge-1",
        "routing_group_id": "group-1",
        "ordinal": 0,
        "mode": "CONTINUE",
        "reason_hash": "sha256:reason",
        "reason_ref": "payload://reason",
        "created_at": "2024-01-01T00:00:00+00:00",
    }
    assert record["record_type"] == "routing_event"
    assert record["ordinal"] == 0


def test_batch_export_record_construction() -> None:
    record: BatchExportRecord = {
        "record_type": "batch",
        "run_id": "run-1",
        "batch_id": "batch-1",
        "aggregation_node_id": "node-1",
        "attempt": 1,
        "status": "COMPLETED",
        "trigger_type": "SIZE",
        "trigger_reason": "max_size reached",
        "created_at": "2024-01-01T00:00:00+00:00",
        "completed_at": "2024-01-01T00:00:01+00:00",
    }
    assert record["record_type"] == "batch"
    assert record["attempt"] == 1


def test_batch_export_record_optional_none() -> None:
    record: BatchExportRecord = {
        "record_type": "batch",
        "run_id": "run-1",
        "batch_id": "batch-1",
        "aggregation_node_id": "node-1",
        "attempt": 1,
        "status": "OPEN",
        "trigger_type": None,
        "trigger_reason": None,
        "created_at": None,
        "completed_at": None,
    }
    assert record["trigger_type"] is None


def test_batch_member_export_record_construction() -> None:
    record: BatchMemberExportRecord = {
        "record_type": "batch_member",
        "run_id": "run-1",
        "batch_id": "batch-1",
        "token_id": "token-1",
        "ordinal": 0,
    }
    assert record["record_type"] == "batch_member"
    assert record["ordinal"] == 0


def test_artifact_export_record_construction() -> None:
    record: ArtifactExportRecord = {
        "record_type": "artifact",
        "run_id": "run-1",
        "artifact_id": "artifact-1",
        "sink_node_id": "node-1",
        "produced_by_state_id": "state-1",
        "artifact_type": "FILE",
        "path_or_uri": "/output/result.csv",
        "content_hash": "sha256:abc",
        "size_bytes": 1024,
        "idempotency_key": "retry-key-1",
    }
    assert record["record_type"] == "artifact"
    assert record["size_bytes"] == 1024
    assert record["idempotency_key"] == "retry-key-1"


def test_artifact_export_record_optional_none() -> None:
    record: ArtifactExportRecord = {
        "record_type": "artifact",
        "run_id": "run-1",
        "artifact_id": "artifact-1",
        "sink_node_id": "node-1",
        "produced_by_state_id": None,
        "artifact_type": "FILE",
        "path_or_uri": None,
        "content_hash": None,
        "size_bytes": None,
        "idempotency_key": None,
    }
    assert record["produced_by_state_id"] is None
    assert record["size_bytes"] is None
    assert record["idempotency_key"] is None
