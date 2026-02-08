from __future__ import annotations

import json

from elspeth.contracts import NodeType
from elspeth.contracts.schema import SchemaConfig
from elspeth.core.canonical import stable_hash
from elspeth.core.landscape import LandscapeDB, LandscapeRecorder

_DYNAMIC_SCHEMA = SchemaConfig.from_dict({"mode": "observed"})


def _setup(*, run_id: str = "run-1") -> tuple[LandscapeDB, LandscapeRecorder]:
    db = LandscapeDB.in_memory()
    recorder = LandscapeRecorder(db)
    recorder.begin_run(config={}, canonical_version="v1", run_id=run_id)
    recorder.register_node(
        run_id=run_id,
        plugin_name="csv",
        node_type=NodeType.SOURCE,
        plugin_version="1.0",
        config={},
        node_id="source-0",
        schema_config=_DYNAMIC_SCHEMA,
    )
    return db, recorder


def _setup_with_token(
    *, run_id: str = "run-1",
) -> tuple[LandscapeDB, LandscapeRecorder]:
    db, recorder = _setup(run_id=run_id)
    recorder.register_node(
        run_id=run_id,
        plugin_name="transform",
        node_type=NodeType.TRANSFORM,
        plugin_version="1.0",
        config={},
        node_id="transform-1",
        schema_config=_DYNAMIC_SCHEMA,
    )
    recorder.create_row(run_id, "source-0", 0, {"name": "test"}, row_id="row-1")
    recorder.create_token("row-1", token_id="tok-1")
    return db, recorder


class TestRecordValidationError:
    """Tests for ErrorRecordingMixin.record_validation_error."""

    def test_returns_error_id_with_verr_prefix(self):
        _db, recorder = _setup()
        error_id = recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data={"name": "alice", "age": 30},
            error="Field 'age' expected str, got int",
            schema_mode="strict",
            destination="quarantine",
        )
        assert error_id.startswith("verr_")

    def test_roundtrip_via_get_validation_errors_for_row(self):
        _db, recorder = _setup()
        row_data = {"name": "alice", "age": 30}
        error_id = recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data=row_data,
            error="Field 'age' expected str, got int",
            schema_mode="strict",
            destination="quarantine",
        )
        row_hash = stable_hash(row_data)
        errors = recorder.get_validation_errors_for_row("run-1", row_hash)
        assert len(errors) == 1
        record = errors[0]
        assert record.error_id == error_id
        assert record.run_id == "run-1"
        assert record.node_id == "source-0"
        assert record.row_hash == row_hash
        assert record.error == "Field 'age' expected str, got int"
        assert record.schema_mode == "strict"
        assert record.destination == "quarantine"
        assert record.created_at is not None

    def test_stores_row_data_as_json(self):
        _db, recorder = _setup()
        row_data = {"x": 1, "y": "hello"}
        recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data=row_data,
            error="bad field",
            schema_mode="observed",
            destination="quarantine",
        )
        row_hash = stable_hash(row_data)
        errors = recorder.get_validation_errors_for_row("run-1", row_hash)
        assert len(errors) == 1
        parsed = json.loads(errors[0].row_data_json)
        assert parsed["x"] == 1
        assert parsed["y"] == "hello"

    def test_multiple_errors_for_same_row(self):
        _db, recorder = _setup()
        row_data = {"name": "bob"}
        recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data=row_data,
            error="error one",
            schema_mode="strict",
            destination="quarantine",
        )
        recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data=row_data,
            error="error two",
            schema_mode="strict",
            destination="quarantine",
        )
        row_hash = stable_hash(row_data)
        errors = recorder.get_validation_errors_for_row("run-1", row_hash)
        assert len(errors) == 2
        error_messages = {e.error for e in errors}
        assert error_messages == {"error one", "error two"}

    def test_unique_error_ids_per_call(self):
        _db, recorder = _setup()
        row_data = {"k": "v"}
        id1 = recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data=row_data,
            error="err a",
            schema_mode="observed",
            destination="quarantine",
        )
        id2 = recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data=row_data,
            error="err b",
            schema_mode="observed",
            destination="quarantine",
        )
        assert id1 != id2
        assert id1.startswith("verr_")
        assert id2.startswith("verr_")

    def test_with_contract_violation_stores_in_db(self):
        from sqlalchemy import select

        from elspeth.contracts.errors import TypeMismatchViolation
        from elspeth.core.landscape.schema import validation_errors_table

        db, recorder = _setup()
        row_data = {"amount": "not_a_number"}
        violation = TypeMismatchViolation(
            normalized_name="amount",
            original_name="Amount",
            expected_type=int,
            actual_type=str,
            actual_value="not_a_number",
        )
        error_id = recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data=row_data,
            error="Type mismatch on 'amount'",
            schema_mode="strict",
            destination="quarantine",
            contract_violation=violation,
        )
        assert error_id.startswith("verr_")
        # Verify contract violation fields are stored in DB
        with db.engine.connect() as conn:
            row = conn.execute(
                select(validation_errors_table).where(
                    validation_errors_table.c.error_id == error_id
                )
            ).one()
        assert row.violation_type == "type_mismatch"
        assert row.normalized_field_name == "amount"
        assert row.original_field_name == "Amount"
        assert row.expected_type == "int"
        assert row.actual_type == "str"

    def test_without_contract_violation_db_fields_are_null(self):
        from sqlalchemy import select

        from elspeth.core.landscape.schema import validation_errors_table

        db, recorder = _setup()
        row_data = {"a": 1}
        error_id = recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data=row_data,
            error="some error",
            schema_mode="observed",
            destination="quarantine",
        )
        with db.engine.connect() as conn:
            row = conn.execute(
                select(validation_errors_table).where(
                    validation_errors_table.c.error_id == error_id
                )
            ).one()
        assert row.violation_type is None
        assert row.normalized_field_name is None
        assert row.original_field_name is None
        assert row.expected_type is None
        assert row.actual_type is None


class TestRecordValidationErrorNonCanonicalData:
    """Tests for record_validation_error with non-canonical row data (repr fallback)."""

    def test_nan_in_row_data(self):
        _db, recorder = _setup()
        row_data = {"value": float("nan")}
        error_id = recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data=row_data,
            error="NaN not allowed",
            schema_mode="strict",
            destination="quarantine",
        )
        assert error_id.startswith("verr_")
        # The row should still be recorded (via repr fallback) — query by run
        errors = recorder.get_validation_errors_for_run("run-1")
        assert len(errors) == 1
        assert errors[0].error_id == error_id
        # row_data_json should contain something (repr fallback)
        assert errors[0].row_data_json is not None
        assert len(errors[0].row_data_json) > 0

    def test_infinity_in_row_data(self):
        _db, recorder = _setup()
        row_data = {"value": float("inf")}
        error_id = recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data=row_data,
            error="Infinity not allowed",
            schema_mode="strict",
            destination="quarantine",
        )
        assert error_id.startswith("verr_")
        errors = recorder.get_validation_errors_for_run("run-1")
        assert len(errors) == 1
        assert errors[0].row_data_json is not None

    def test_negative_infinity_in_row_data(self):
        _db, recorder = _setup()
        row_data = {"value": float("-inf")}
        error_id = recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data=row_data,
            error="Negative infinity not allowed",
            schema_mode="strict",
            destination="quarantine",
        )
        assert error_id.startswith("verr_")
        errors = recorder.get_validation_errors_for_run("run-1")
        assert len(errors) == 1

    def test_list_as_row_data(self):
        _db, recorder = _setup()
        row_data = [1, 2, 3]
        error_id = recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data=row_data,
            error="Expected dict, got list",
            schema_mode="strict",
            destination="quarantine",
        )
        assert error_id.startswith("verr_")
        errors = recorder.get_validation_errors_for_run("run-1")
        assert len(errors) == 1
        assert errors[0].row_data_json is not None

    def test_string_as_row_data(self):
        _db, recorder = _setup()
        row_data = "not a dict at all"
        error_id = recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data=row_data,
            error="Expected dict, got str",
            schema_mode="strict",
            destination="quarantine",
        )
        assert error_id.startswith("verr_")
        errors = recorder.get_validation_errors_for_run("run-1")
        assert len(errors) == 1

    def test_none_as_row_data(self):
        _db, recorder = _setup()
        error_id = recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data=None,
            error="Row data was None",
            schema_mode="strict",
            destination="quarantine",
        )
        assert error_id.startswith("verr_")
        errors = recorder.get_validation_errors_for_run("run-1")
        assert len(errors) == 1


class TestRecordTransformError:
    """Tests for ErrorRecordingMixin.record_transform_error."""

    def test_returns_error_id_with_terr_prefix(self):
        _db, recorder = _setup_with_token()
        error_id = recorder.record_transform_error(
            run_id="run-1",
            token_id="tok-1",
            transform_id="transform-1",
            row_data={"name": "test"},
            error_details={"reason": "division_by_zero", "field": "amount", "error": "ZeroDivisionError"},
            destination="quarantine",
        )
        assert error_id.startswith("terr_")

    def test_roundtrip_via_get_transform_errors_for_token(self):
        _db, recorder = _setup_with_token()
        row_data = {"name": "test"}
        error_details = {
            "reason": "division_by_zero",
            "field": "amount",
            "error": "ZeroDivisionError: division by zero",
        }
        error_id = recorder.record_transform_error(
            run_id="run-1",
            token_id="tok-1",
            transform_id="transform-1",
            row_data=row_data,
            error_details=error_details,
            destination="quarantine",
        )
        errors = recorder.get_transform_errors_for_token("tok-1")
        assert len(errors) == 1
        record = errors[0]
        assert record.error_id == error_id
        assert record.run_id == "run-1"
        assert record.token_id == "tok-1"
        assert record.transform_id == "transform-1"
        assert record.destination == "quarantine"
        assert record.created_at is not None
        parsed_details = json.loads(record.error_details_json)
        assert parsed_details["reason"] == "division_by_zero"
        assert parsed_details["field"] == "amount"

    def test_stores_row_hash(self):
        _db, recorder = _setup_with_token()
        row_data = {"name": "test"}
        recorder.record_transform_error(
            run_id="run-1",
            token_id="tok-1",
            transform_id="transform-1",
            row_data=row_data,
            error_details={"reason": "parse_error", "field": "date", "error": "ValueError"},
            destination="quarantine",
        )
        errors = recorder.get_transform_errors_for_token("tok-1")
        assert len(errors) == 1
        expected_hash = stable_hash(row_data)
        assert errors[0].row_hash == expected_hash

    def test_stores_row_data_json(self):
        _db, recorder = _setup_with_token()
        row_data = {"name": "test", "value": 42}
        recorder.record_transform_error(
            run_id="run-1",
            token_id="tok-1",
            transform_id="transform-1",
            row_data=row_data,
            error_details={"reason": "overflow", "field": "value", "error": "OverflowError"},
            destination="quarantine",
        )
        errors = recorder.get_transform_errors_for_token("tok-1")
        assert len(errors) == 1
        parsed = json.loads(errors[0].row_data_json)
        assert parsed["name"] == "test"
        assert parsed["value"] == 42

    def test_multiple_errors_for_same_token(self):
        _db, recorder = _setup_with_token()
        recorder.record_transform_error(
            run_id="run-1",
            token_id="tok-1",
            transform_id="transform-1",
            row_data={"name": "test"},
            error_details={"reason": "err_a", "field": "f1", "error": "Error A"},
            destination="quarantine",
        )
        recorder.record_transform_error(
            run_id="run-1",
            token_id="tok-1",
            transform_id="transform-1",
            row_data={"name": "test"},
            error_details={"reason": "err_b", "field": "f2", "error": "Error B"},
            destination="quarantine",
        )
        errors = recorder.get_transform_errors_for_token("tok-1")
        assert len(errors) == 2
        reasons = {json.loads(e.error_details_json)["reason"] for e in errors}
        assert reasons == {"err_a", "err_b"}

    def test_unique_error_ids_per_call(self):
        _db, recorder = _setup_with_token()
        id1 = recorder.record_transform_error(
            run_id="run-1",
            token_id="tok-1",
            transform_id="transform-1",
            row_data={"name": "test"},
            error_details={"reason": "a", "field": "x", "error": "A"},
            destination="quarantine",
        )
        id2 = recorder.record_transform_error(
            run_id="run-1",
            token_id="tok-1",
            transform_id="transform-1",
            row_data={"name": "test"},
            error_details={"reason": "b", "field": "y", "error": "B"},
            destination="quarantine",
        )
        assert id1 != id2
        assert id1.startswith("terr_")
        assert id2.startswith("terr_")


class TestGetValidationErrorsForRow:
    """Tests for ErrorRecordingMixin.get_validation_errors_for_row."""

    def test_returns_errors_matching_row_hash(self):
        _db, recorder = _setup()
        row_data = {"id": 1, "name": "alice"}
        recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data=row_data,
            error="bad field",
            schema_mode="strict",
            destination="quarantine",
        )
        row_hash = stable_hash(row_data)
        errors = recorder.get_validation_errors_for_row("run-1", row_hash)
        assert len(errors) == 1
        assert errors[0].row_hash == row_hash

    def test_empty_for_unknown_hash(self):
        _db, recorder = _setup()
        recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data={"exists": True},
            error="some error",
            schema_mode="observed",
            destination="quarantine",
        )
        errors = recorder.get_validation_errors_for_row("run-1", "nonexistent_hash_value")
        assert errors == []

    def test_does_not_cross_runs(self):
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        # Set up run-1
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-1")
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="source-0",
            schema_config=_DYNAMIC_SCHEMA,
        )
        # Set up run-2
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-2")
        recorder.register_node(
            run_id="run-2",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="source-0",
            schema_config=_DYNAMIC_SCHEMA,
        )
        row_data = {"shared": "data"}
        recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data=row_data,
            error="run 1 error",
            schema_mode="strict",
            destination="quarantine",
        )
        recorder.record_validation_error(
            run_id="run-2",
            node_id="source-0",
            row_data=row_data,
            error="run 2 error",
            schema_mode="strict",
            destination="quarantine",
        )
        row_hash = stable_hash(row_data)
        run1_errors = recorder.get_validation_errors_for_row("run-1", row_hash)
        run2_errors = recorder.get_validation_errors_for_row("run-2", row_hash)
        assert len(run1_errors) == 1
        assert run1_errors[0].error == "run 1 error"
        assert len(run2_errors) == 1
        assert run2_errors[0].error == "run 2 error"

    def test_empty_when_no_errors_recorded(self):
        _db, recorder = _setup()
        errors = recorder.get_validation_errors_for_row("run-1", "any_hash")
        assert errors == []


class TestGetValidationErrorsForRun:
    """Tests for ErrorRecordingMixin.get_validation_errors_for_run."""

    def test_returns_all_errors_for_run(self):
        _db, recorder = _setup()
        recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data={"a": 1},
            error="error one",
            schema_mode="strict",
            destination="quarantine",
        )
        recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data={"b": 2},
            error="error two",
            schema_mode="strict",
            destination="quarantine",
        )
        recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data={"c": 3},
            error="error three",
            schema_mode="observed",
            destination="quarantine",
        )
        errors = recorder.get_validation_errors_for_run("run-1")
        assert len(errors) == 3
        error_messages = {e.error for e in errors}
        assert error_messages == {"error one", "error two", "error three"}

    def test_empty_when_no_errors_exist(self):
        _db, recorder = _setup()
        errors = recorder.get_validation_errors_for_run("run-1")
        assert errors == []

    def test_does_not_cross_runs(self):
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-1")
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="source-0",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-2")
        recorder.register_node(
            run_id="run-2",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="source-0",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.record_validation_error(
            run_id="run-1",
            node_id="source-0",
            row_data={"x": 1},
            error="run-1 error",
            schema_mode="strict",
            destination="quarantine",
        )
        recorder.record_validation_error(
            run_id="run-2",
            node_id="source-0",
            row_data={"y": 2},
            error="run-2 error",
            schema_mode="strict",
            destination="quarantine",
        )
        run1_errors = recorder.get_validation_errors_for_run("run-1")
        run2_errors = recorder.get_validation_errors_for_run("run-2")
        assert len(run1_errors) == 1
        assert run1_errors[0].error == "run-1 error"
        assert len(run2_errors) == 1
        assert run2_errors[0].error == "run-2 error"

    def test_ordered_by_created_at(self):
        _db, recorder = _setup()
        for i in range(5):
            recorder.record_validation_error(
                run_id="run-1",
                node_id="source-0",
                row_data={f"field_{i}": i},
                error=f"error {i}",
                schema_mode="observed",
                destination="quarantine",
            )
        errors = recorder.get_validation_errors_for_run("run-1")
        assert len(errors) == 5
        timestamps = [e.created_at for e in errors]
        assert timestamps == sorted(timestamps)


class TestGetTransformErrorsForToken:
    """Tests for ErrorRecordingMixin.get_transform_errors_for_token."""

    def test_returns_errors_for_token(self):
        _db, recorder = _setup_with_token()
        recorder.record_transform_error(
            run_id="run-1",
            token_id="tok-1",
            transform_id="transform-1",
            row_data={"name": "test"},
            error_details={"reason": "parse_error", "field": "date", "error": "ValueError"},
            destination="quarantine",
        )
        errors = recorder.get_transform_errors_for_token("tok-1")
        assert len(errors) == 1
        assert errors[0].token_id == "tok-1"

    def test_empty_for_unknown_token(self):
        _db, recorder = _setup_with_token()
        recorder.record_transform_error(
            run_id="run-1",
            token_id="tok-1",
            transform_id="transform-1",
            row_data={"name": "test"},
            error_details={"reason": "err", "field": "f", "error": "E"},
            destination="quarantine",
        )
        errors = recorder.get_transform_errors_for_token("tok-nonexistent")
        assert errors == []

    def test_does_not_return_other_tokens_errors(self):
        _db, recorder = _setup_with_token()
        # Create a second token
        recorder.create_row("run-1", "source-0", 1, {"name": "other"}, row_id="row-2")
        recorder.create_token("row-2", token_id="tok-2")
        recorder.record_transform_error(
            run_id="run-1",
            token_id="tok-1",
            transform_id="transform-1",
            row_data={"name": "test"},
            error_details={"reason": "err_tok1", "field": "f", "error": "E1"},
            destination="quarantine",
        )
        recorder.record_transform_error(
            run_id="run-1",
            token_id="tok-2",
            transform_id="transform-1",
            row_data={"name": "other"},
            error_details={"reason": "err_tok2", "field": "f", "error": "E2"},
            destination="quarantine",
        )
        tok1_errors = recorder.get_transform_errors_for_token("tok-1")
        tok2_errors = recorder.get_transform_errors_for_token("tok-2")
        assert len(tok1_errors) == 1
        assert json.loads(tok1_errors[0].error_details_json)["reason"] == "err_tok1"
        assert len(tok2_errors) == 1
        assert json.loads(tok2_errors[0].error_details_json)["reason"] == "err_tok2"

    def test_empty_when_no_errors_recorded(self):
        _db, recorder = _setup_with_token()
        errors = recorder.get_transform_errors_for_token("tok-1")
        assert errors == []


class TestGetTransformErrorsForRun:
    """Tests for ErrorRecordingMixin.get_transform_errors_for_run."""

    def test_returns_all_errors_for_run(self):
        _db, recorder = _setup_with_token()
        recorder.create_row("run-1", "source-0", 1, {"name": "other"}, row_id="row-2")
        recorder.create_token("row-2", token_id="tok-2")
        recorder.record_transform_error(
            run_id="run-1",
            token_id="tok-1",
            transform_id="transform-1",
            row_data={"name": "test"},
            error_details={"reason": "err_a", "field": "f1", "error": "A"},
            destination="quarantine",
        )
        recorder.record_transform_error(
            run_id="run-1",
            token_id="tok-2",
            transform_id="transform-1",
            row_data={"name": "other"},
            error_details={"reason": "err_b", "field": "f2", "error": "B"},
            destination="quarantine",
        )
        errors = recorder.get_transform_errors_for_run("run-1")
        assert len(errors) == 2
        reasons = {json.loads(e.error_details_json)["reason"] for e in errors}
        assert reasons == {"err_a", "err_b"}

    def test_empty_when_no_errors_exist(self):
        _db, recorder = _setup_with_token()
        errors = recorder.get_transform_errors_for_run("run-1")
        assert errors == []

    def test_does_not_cross_runs(self):
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        # Set up run-1
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-1")
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="source-0",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="transform",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            node_id="transform-1",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.create_row("run-1", "source-0", 0, {"n": "a"}, row_id="row-r1")
        recorder.create_token("row-r1", token_id="tok-r1")
        # Set up run-2
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-2")
        recorder.register_node(
            run_id="run-2",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="source-0",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-2",
            plugin_name="transform",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            node_id="transform-1",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.create_row("run-2", "source-0", 0, {"n": "b"}, row_id="row-r2")
        recorder.create_token("row-r2", token_id="tok-r2")
        recorder.record_transform_error(
            run_id="run-1",
            token_id="tok-r1",
            transform_id="transform-1",
            row_data={"n": "a"},
            error_details={"reason": "run1_err", "field": "f", "error": "E"},
            destination="quarantine",
        )
        recorder.record_transform_error(
            run_id="run-2",
            token_id="tok-r2",
            transform_id="transform-1",
            row_data={"n": "b"},
            error_details={"reason": "run2_err", "field": "f", "error": "E"},
            destination="quarantine",
        )
        run1_errors = recorder.get_transform_errors_for_run("run-1")
        run2_errors = recorder.get_transform_errors_for_run("run-2")
        assert len(run1_errors) == 1
        assert json.loads(run1_errors[0].error_details_json)["reason"] == "run1_err"
        assert len(run2_errors) == 1
        assert json.loads(run2_errors[0].error_details_json)["reason"] == "run2_err"

    def test_ordered_by_created_at(self):
        _db, recorder = _setup_with_token()
        for i in range(5):
            recorder.record_transform_error(
                run_id="run-1",
                token_id="tok-1",
                transform_id="transform-1",
                row_data={"idx": i},
                error_details={"reason": f"err_{i}", "field": "f", "error": "E"},
                destination="quarantine",
            )
        errors = recorder.get_transform_errors_for_run("run-1")
        assert len(errors) == 5
        timestamps = [e.created_at for e in errors]
        assert timestamps == sorted(timestamps)
