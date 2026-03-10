# tests/unit/core/landscape/test_where_exactness_run_lifecycle.py
"""WHERE clause exactness tests for RunLifecycleRepository query methods.

These tests verify that SQL queries use ``==`` (exact match) rather than
``>=`` / ``<=`` (range) operators.  The multi-run fixture creates three
runs with lexicographically ordered IDs (run-A < run-B < run-C) so that
an inequality operator would silently include data from adjacent runs.

The fixture lives in ``tests/fixtures/multi_run.py`` and is imported as
a pytest fixture via the ``multi_run_landscape`` name.
"""

from __future__ import annotations

import time

from elspeth.contracts import ExportStatus, RunStatus, SecretResolutionInput
from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from tests.fixtures.multi_run import MultiRunFixture

pytest_plugins = ["tests.fixtures.multi_run"]


def _make_secret_resolution(env_var: str, fingerprint_byte: str = "a") -> SecretResolutionInput:
    """Build a minimal valid SecretResolutionInput."""
    return SecretResolutionInput(
        env_var_name=env_var,
        source="keyvault",
        vault_url="https://test.vault.azure.net",
        secret_name=f"secret-{env_var}",
        timestamp=time.time(),
        resolution_latency_ms=1.0,
        fingerprint=fingerprint_byte * 64,
    )


def _make_schema_contract() -> SchemaContract:
    """Build a minimal valid SchemaContract for testing."""
    return SchemaContract(
        mode="OBSERVED",
        fields=(
            FieldContract(
                normalized_name="val",
                original_name="val",
                python_type=str,
                required=True,
                source="inferred",
            ),
        ),
        locked=True,
    )


class TestGetRunWhereExactness:
    """get_run must return exactly the target run, not adjacent ones."""

    def test_returns_exact_run(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        run = fix.recorder.get_run("run-B")

        assert run is not None
        assert run.run_id == "run-B"

    def test_excludes_adjacent_runs(self, multi_run_landscape: MultiRunFixture) -> None:
        """If == were mutated to >=, querying run-B would also match run-C."""
        fix = multi_run_landscape
        run = fix.recorder.get_run("run-B")

        assert run is not None
        assert run.run_id == "run-B"
        # Verify the other runs still exist independently
        run_a = fix.recorder.get_run("run-A")
        run_c = fix.recorder.get_run("run-C")
        assert run_a is not None and run_a.run_id == "run-A"
        assert run_c is not None and run_c.run_id == "run-C"


class TestCompleteRunWhereExactness:
    """complete_run must update only the target run's status."""

    def test_completes_only_target_run(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape

        # Complete run-B
        fix.recorder.complete_run("run-B", RunStatus.COMPLETED)

        # run-B should be COMPLETED
        run_b = fix.recorder.get_run("run-B")
        assert run_b is not None
        assert run_b.status == RunStatus.COMPLETED

        # run-A and run-C must still be RUNNING (unaffected)
        run_a = fix.recorder.get_run("run-A")
        run_c = fix.recorder.get_run("run-C")
        assert run_a is not None and run_a.status == RunStatus.RUNNING
        assert run_c is not None and run_c.status == RunStatus.RUNNING


class TestUpdateRunStatusWhereExactness:
    """update_run_status must transition only the target run."""

    def test_updates_only_target_run(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape

        # All runs start RUNNING. Transition run-B to INTERRUPTED first
        # (update_run_status refuses COMPLETED transitions, but RUNNING->INTERRUPTED is fine)
        fix.recorder.update_run_status("run-B", RunStatus.INTERRUPTED)

        # run-B should be INTERRUPTED
        run_b = fix.recorder.get_run("run-B")
        assert run_b is not None
        assert run_b.status == RunStatus.INTERRUPTED

        # run-A and run-C must still be RUNNING
        run_a = fix.recorder.get_run("run-A")
        run_c = fix.recorder.get_run("run-C")
        assert run_a is not None and run_a.status == RunStatus.RUNNING
        assert run_c is not None and run_c.status == RunStatus.RUNNING


class TestUpdateRunContractWhereExactness:
    """update_run_contract must set contract only on the target run."""

    def test_updates_only_target_run(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape
        contract = _make_schema_contract()

        # Set contract on run-B only
        fix.recorder.update_run_contract("run-B", contract)

        # run-B should have the contract
        contract_b = fix.recorder.get_run_contract("run-B")
        assert contract_b is not None
        assert contract_b.mode == "OBSERVED"

        # run-A and run-C must have no contract
        contract_a = fix.recorder.get_run_contract("run-A")
        contract_c = fix.recorder.get_run_contract("run-C")
        assert contract_a is None
        assert contract_c is None


class TestGetSourceFieldResolutionWhereExactness:
    """get_source_field_resolution must return resolution for the target run only."""

    def test_returns_only_target_run_resolution(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape

        # Record resolution on run-B only
        fix.recorder.record_source_field_resolution(
            "run-B",
            {"Original Header": "original_header"},
            "v1",
        )

        # run-B should have the resolution
        resolution = fix.recorder.get_source_field_resolution("run-B")
        assert resolution is not None
        assert resolution == {"Original Header": "original_header"}

        # run-A and run-C must have no resolution
        resolution_a = fix.recorder.get_source_field_resolution("run-A")
        resolution_c = fix.recorder.get_source_field_resolution("run-C")
        assert resolution_a is None
        assert resolution_c is None


class TestSetExportStatusWhereExactness:
    """set_export_status must update only the target run."""

    def test_updates_only_target_run(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape

        # Set export status on run-B only
        fix.recorder.set_export_status("run-B", ExportStatus.COMPLETED)

        # run-B should have COMPLETED export status
        run_b = fix.recorder.get_run("run-B")
        assert run_b is not None
        assert run_b.export_status == ExportStatus.COMPLETED

        # run-A and run-C must still have default export status (PENDING or None)
        run_a = fix.recorder.get_run("run-A")
        run_c = fix.recorder.get_run("run-C")
        assert run_a is not None and run_a.export_status != ExportStatus.COMPLETED
        assert run_c is not None and run_c.export_status != ExportStatus.COMPLETED


class TestGetSecretResolutionsForRunWhereExactness:
    """get_secret_resolutions_for_run must return resolutions for the target run only."""

    def test_returns_only_target_run_resolutions(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape

        # Record secret resolutions on all three runs with distinct fingerprints
        fix.recorder.record_secret_resolutions("run-A", [_make_secret_resolution("KEY_A", "a")])
        fix.recorder.record_secret_resolutions("run-B", [_make_secret_resolution("KEY_B", "b")])
        fix.recorder.record_secret_resolutions("run-C", [_make_secret_resolution("KEY_C", "c")])

        # Query run-B only
        resolutions = fix.recorder.get_secret_resolutions_for_run("run-B")

        assert len(resolutions) == 1
        assert resolutions[0].env_var_name == "KEY_B"
        assert resolutions[0].run_id == "run-B"

    def test_excludes_adjacent_run_resolutions(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape

        fix.recorder.record_secret_resolutions("run-A", [_make_secret_resolution("KEY_A", "a")])
        fix.recorder.record_secret_resolutions("run-B", [_make_secret_resolution("KEY_B", "b")])
        fix.recorder.record_secret_resolutions("run-C", [_make_secret_resolution("KEY_C", "c")])

        res_a = fix.recorder.get_secret_resolutions_for_run("run-A")
        res_c = fix.recorder.get_secret_resolutions_for_run("run-C")

        assert len(res_a) == 1
        assert res_a[0].env_var_name == "KEY_A"
        assert len(res_c) == 1
        assert res_c[0].env_var_name == "KEY_C"


class TestListRunsWhereExactness:
    """list_runs with status filter must return only runs matching that status."""

    def test_filters_by_exact_status(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape

        # Complete run-B so it has a different status from A and C
        fix.recorder.complete_run("run-B", RunStatus.COMPLETED)

        # Filter for COMPLETED — should return only run-B
        completed_runs = fix.recorder.list_runs(status=RunStatus.COMPLETED)
        assert len(completed_runs) == 1
        assert completed_runs[0].run_id == "run-B"

        # Filter for RUNNING — should return run-A and run-C only
        running_runs = fix.recorder.list_runs(status=RunStatus.RUNNING)
        assert len(running_runs) == 2
        running_ids = {r.run_id for r in running_runs}
        assert running_ids == {"run-A", "run-C"}

    def test_unfiltered_returns_all(self, multi_run_landscape: MultiRunFixture) -> None:
        fix = multi_run_landscape

        all_runs = fix.recorder.list_runs()
        assert len(all_runs) == 3
        assert {r.run_id for r in all_runs} == {"run-A", "run-B", "run-C"}
