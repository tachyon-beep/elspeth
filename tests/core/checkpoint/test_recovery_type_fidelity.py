# tests/core/checkpoint/test_recovery_type_fidelity.py
"""Test type fidelity preservation in RecoveryManager.get_unprocessed_row_data().

CRITICAL BUG: When payloads contain canonical JSON with normalized types
(datetime → ISO string, Decimal → string), json.loads() restores them as
plain str instead of the original coerced types.

This causes resumed runs to see different types than initial runs.
"""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from elspeth.core.canonical import canonical_json
from elspeth.core.checkpoint import CheckpointManager, RecoveryManager
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.schema import nodes_table, rows_table, runs_table, tokens_table
from elspeth.core.payload_store import FilesystemPayloadStore


@pytest.fixture
def landscape_db(tmp_path: Path) -> LandscapeDB:
    """Create test database."""
    return LandscapeDB(f"sqlite:///{tmp_path}/test.db")


@pytest.fixture
def payload_store(tmp_path: Path) -> FilesystemPayloadStore:
    """Create test payload store."""
    return FilesystemPayloadStore(tmp_path / "payloads")


@pytest.fixture
def checkpoint_manager(landscape_db: LandscapeDB) -> CheckpointManager:
    """Create checkpoint manager."""
    return CheckpointManager(landscape_db)


@pytest.fixture
def recovery_manager(landscape_db: LandscapeDB, checkpoint_manager: CheckpointManager) -> RecoveryManager:
    """Create recovery manager."""
    return RecoveryManager(landscape_db, checkpoint_manager)


def test_get_unprocessed_row_data_loses_type_fidelity(
    landscape_db: LandscapeDB,
    payload_store: FilesystemPayloadStore,
    checkpoint_manager: CheckpointManager,
    recovery_manager: RecoveryManager,
):
    """Demonstrate that get_unprocessed_row_data() loses type fidelity.

    BUG REPRODUCTION:
    1. Store row with datetime and Decimal fields via canonical_json()
    2. Call get_unprocessed_row_data() to retrieve row
    3. Observe that datetime becomes str, Decimal becomes str

    EXPECTED: Types are restored (datetime, Decimal)
    ACTUAL: Types are degraded (str, str)
    """
    run_id = "test-type-fidelity"
    now = datetime.now(UTC)

    # Step 1: Create a run with nodes
    with landscape_db.engine.begin() as conn:
        conn.execute(
            runs_table.insert().values(
                run_id=run_id,
                started_at=now,
                config_hash="test",
                settings_json="{}",
                canonical_version="v1",
                status="failed",
            )
        )

        # Create source node
        conn.execute(
            nodes_table.insert().values(
                node_id="source",
                run_id=run_id,
                plugin_name="test_source",
                node_type="source",
                plugin_version="1.0",
                determinism="deterministic",
                config_hash="test",
                config_json="{}",
                registered_at=now,
            )
        )

    # Step 2: Create rows with typed data (datetime, Decimal)
    original_rows = [
        {"id": 1, "timestamp": datetime(2024, 1, 1, 12, 0, tzinfo=UTC), "amount": Decimal("100.50")},
        {"id": 2, "timestamp": datetime(2024, 1, 2, 12, 0, tzinfo=UTC), "amount": Decimal("200.75")},
        {"id": 3, "timestamp": datetime(2024, 1, 3, 12, 0, tzinfo=UTC), "amount": Decimal("300.25")},
    ]

    row_ids = []
    with landscape_db.engine.begin() as conn:
        for idx, row_data in enumerate(original_rows):
            # Store payload via canonical_json (this is what TokenManager does)
            payload_bytes = canonical_json(row_data).encode("utf-8")
            payload_ref = payload_store.store(payload_bytes)

            # Create row record
            row_id = f"row_{idx}"
            conn.execute(
                rows_table.insert().values(
                    row_id=row_id,
                    run_id=run_id,
                    source_node_id="source",
                    row_index=idx,
                    source_data_hash="hash",
                    source_data_ref=payload_ref,
                    created_at=now,
                )
            )
            row_ids.append(row_id)

            # Create token for each row
            token_id = f"token_{idx}"
            conn.execute(
                tokens_table.insert().values(
                    token_id=token_id,
                    row_id=row_id,
                    created_at=now,
                )
            )

    # Step 3: Create checkpoint at row 0 (rows 1, 2 are "unprocessed")
    from elspeth.core.landscape.schema import checkpoints_table

    with landscape_db.engine.begin() as conn:
        conn.execute(
            checkpoints_table.insert().values(
                checkpoint_id="checkpoint_0",
                run_id=run_id,
                token_id="token_0",
                node_id="source",
                sequence_number=0,
                created_at=now,
            )
        )

    # Step 4a: WITHOUT schema - types are degraded (demonstrating the bug)
    unprocessed_no_schema = recovery_manager.get_unprocessed_row_data(run_id, payload_store)

    assert len(unprocessed_no_schema) == 2  # Rows 1 and 2 are unprocessed

    # Unpack first unprocessed row
    row_id, row_index, row_data_degraded = unprocessed_no_schema[0]

    assert row_index == 1
    assert row_data_degraded["id"] == 2

    # BUG DEMONSTRATION: These should be datetime and Decimal, but they are str!
    timestamp_degraded = row_data_degraded["timestamp"]
    amount_degraded = row_data_degraded["amount"]

    print("\n=== WITHOUT SCHEMA (degraded types) ===")
    print(f"Type of timestamp: {type(timestamp_degraded)}")
    print(f"Value of timestamp: {timestamp_degraded}")
    print(f"Type of amount: {type(amount_degraded)}")
    print(f"Value of amount: {amount_degraded}")

    # Confirm degradation
    assert isinstance(timestamp_degraded, str), "Without schema, timestamp should be str"
    assert isinstance(amount_degraded, str), "Without schema, amount should be str"

    # Step 4b: WITH schema - types are restored (the fix!)
    # Create a Pydantic schema directly (sources with datetime/Decimal do this)
    from pydantic import ConfigDict

    from elspeth.contracts import PluginSchema

    class RestoredSchema(PluginSchema):
        """Schema for restoring types during resume."""

        model_config = ConfigDict(strict=False)  # allow_coercion=True means strict=False

        id: int
        timestamp: datetime
        amount: Decimal

    source_schema_class = RestoredSchema

    unprocessed_with_schema = recovery_manager.get_unprocessed_row_data(run_id, payload_store, source_schema_class=source_schema_class)

    row_id, row_index, row_data_restored = unprocessed_with_schema[0]

    timestamp_restored = row_data_restored["timestamp"]
    amount_restored = row_data_restored["amount"]

    print("\n=== WITH SCHEMA (restored types) ===")
    print(f"Type of timestamp: {type(timestamp_restored)}")
    print(f"Value of timestamp: {timestamp_restored}")
    print(f"Type of amount: {type(amount_restored)}")
    print(f"Value of amount: {amount_restored}")

    # THIS SHOULD PASS - types are restored!
    assert isinstance(timestamp_restored, datetime), f"Expected datetime, got {type(timestamp_restored).__name__}. Type restoration failed!"

    assert isinstance(amount_restored, Decimal), f"Expected Decimal, got {type(amount_restored).__name__}. Type restoration failed!"

    # Verify values are correct
    assert timestamp_restored == datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
    assert amount_restored == Decimal("200.75")
