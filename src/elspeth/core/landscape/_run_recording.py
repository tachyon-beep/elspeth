# src/elspeth/core/landscape/_run_recording.py
"""Run lifecycle recording methods for LandscapeRecorder."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from elspeth.contracts import (
    ContractAuditRecord,
    ExportStatus,
    Run,
    RunStatus,
    SecretResolution,
)
from elspeth.contracts.errors import AuditIntegrityError
from elspeth.core.canonical import canonical_json, stable_hash
from elspeth.core.landscape._helpers import generate_id, now
from elspeth.core.landscape.schema import (
    runs_table,
    secret_resolutions_table,
)

if TYPE_CHECKING:
    from elspeth.contracts.payload_store import PayloadStore
    from elspeth.contracts.schema_contract import SchemaContract
    from elspeth.core.landscape._database_ops import DatabaseOps
    from elspeth.core.landscape.database import LandscapeDB
    from elspeth.core.landscape.repositories import RunRepository
    from elspeth.core.landscape.reproducibility import ReproducibilityGrade


_TERMINAL_RUN_STATUSES = frozenset({RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.INTERRUPTED})


class RunRecordingMixin:
    """Run lifecycle methods. Mixed into LandscapeRecorder."""

    # Shared state annotations (set by LandscapeRecorder.__init__)
    _db: LandscapeDB
    _ops: DatabaseOps
    _run_repo: RunRepository
    _payload_store: PayloadStore | None

    def begin_run(
        self,
        config: dict[str, Any],
        canonical_version: str,
        *,
        run_id: str | None = None,
        reproducibility_grade: str | None = None,
        status: RunStatus = RunStatus.RUNNING,
        source_schema_json: str | None = None,
        schema_contract: SchemaContract | None = None,
    ) -> Run:
        """Begin a new pipeline run.

        Args:
            config: Resolved configuration dictionary
            canonical_version: Version of canonical hash algorithm
            run_id: Optional run ID (generated if not provided)
            reproducibility_grade: Optional grade (FULL_REPRODUCIBLE, etc.)
            status: Initial RunStatus (defaults to RUNNING)
            source_schema_json: Optional serialized source schema for resume type restoration.
                Should be Pydantic model_json_schema() output. Required for proper resume
                type fidelity (datetime/Decimal restoration from payload JSON strings).
            schema_contract: Optional schema contract for audit trail field resolution.
                Stored via ContractAuditRecord for complete field mapping traceability.

        Returns:
            Run model with generated run_id
        """
        run_id = run_id or generate_id()
        settings_json = canonical_json(config)
        config_hash = stable_hash(config)
        timestamp = now()

        # Convert schema contract to audit record if provided
        schema_contract_json: str | None = None
        schema_contract_hash: str | None = None
        if schema_contract is not None:
            audit_record = ContractAuditRecord.from_contract(schema_contract)
            schema_contract_json = audit_record.to_json()
            schema_contract_hash = schema_contract.version_hash()

        run = Run(
            run_id=run_id,
            started_at=timestamp,
            config_hash=config_hash,
            settings_json=settings_json,
            canonical_version=canonical_version,
            status=status,
            reproducibility_grade=reproducibility_grade,
        )

        self._ops.execute_insert(
            runs_table.insert().values(
                run_id=run.run_id,
                started_at=run.started_at,
                config_hash=run.config_hash,
                settings_json=run.settings_json,
                canonical_version=run.canonical_version,
                status=run.status,
                reproducibility_grade=run.reproducibility_grade,
                source_schema_json=source_schema_json,
                schema_contract_json=schema_contract_json,
                schema_contract_hash=schema_contract_hash,
            )
        )

        return run

    def complete_run(
        self,
        run_id: str,
        status: RunStatus,
        *,
        reproducibility_grade: str | None = None,
    ) -> Run:
        """Complete a pipeline run.

        Args:
            run_id: Run to complete
            status: Final RunStatus (COMPLETED or FAILED)
            reproducibility_grade: Optional final grade

        Returns:
            Updated Run model

        Raises:
            AuditIntegrityError: If status is not a terminal run status
        """
        if status not in _TERMINAL_RUN_STATUSES:
            raise AuditIntegrityError(
                f"complete_run() requires terminal status, got {status.value!r}. "
                f"Valid terminal statuses: {sorted(s.value for s in _TERMINAL_RUN_STATUSES)}"
            )

        timestamp = now()

        self._ops.execute_update(
            runs_table.update()
            .where(runs_table.c.run_id == run_id)
            .values(
                status=status.value,
                completed_at=timestamp,
                reproducibility_grade=reproducibility_grade,
            )
        )

        result = self.get_run(run_id)
        if result is None:
            raise AuditIntegrityError(f"Run {run_id} not found after INSERT/UPDATE - database corruption or transaction failure")
        return result

    def get_run(self, run_id: str) -> Run | None:
        """Get a run by ID.

        Args:
            run_id: Run ID to retrieve

        Returns:
            Run model or None if not found
        """
        query = select(runs_table).where(runs_table.c.run_id == run_id)
        row = self._ops.execute_fetchone(query)
        if row is None:
            return None
        return self._run_repo.load(row)

    def get_source_schema(self, run_id: str) -> str:
        """Get source schema JSON for a run (for resume/type restoration).

        Args:
            run_id: Run to query

        Returns:
            Source schema JSON string

        Raises:
            ValueError: If run not found or has no source schema

        Note:
            This encapsulates Landscape schema access for Orchestrator resume.
            Schema is required for type fidelity when restoring rows from payloads.
        """
        query = select(runs_table.c.source_schema_json).where(runs_table.c.run_id == run_id)
        run_row = self._ops.execute_fetchone(query)

        if run_row is None:
            raise ValueError(f"Run {run_id} not found in database")

        source_schema_json = run_row.source_schema_json
        if source_schema_json is None:
            raise ValueError(
                f"Run {run_id} has no source schema stored. "
                f"This run was created before source schema storage was implemented. "
                f"Cannot resume without schema - type fidelity would be violated."
            )

        return str(source_schema_json)

    def record_source_field_resolution(
        self,
        run_id: str,
        resolution_mapping: dict[str, str],
        normalization_version: str | None,
    ) -> None:
        """Record field resolution mapping computed during source.load().

        This captures the mapping from original header names (as read from the file)
        to final field names (after normalization and/or field_mapping applied).
        Must be called after source.load() completes but before processing begins.

        Args:
            run_id: Run to update
            resolution_mapping: Dict mapping original header name → final field name
            normalization_version: Algorithm version used for normalization, or None if
                                   no normalization was applied (passthrough or explicit columns)

        Note:
            This is necessary because field resolution depends on actual file headers
            which are only known after load() runs, but node config is registered
            before load(). Without this, audit trail cannot recover original headers.
        """
        resolution_data = {
            "resolution_mapping": resolution_mapping,
            "normalization_version": normalization_version,
        }
        resolution_json = canonical_json(resolution_data)

        self._ops.execute_update(
            runs_table.update().where(runs_table.c.run_id == run_id).values(source_field_resolution_json=resolution_json)
        )

    def get_source_field_resolution(self, run_id: str) -> dict[str, str] | None:
        """Get source field resolution mapping for a run.

        Returns the mapping from original header names to final (normalized) field names.
        Used by sinks with restore_source_headers=True to restore original headers.

        Args:
            run_id: Run to query

        Returns:
            Dict mapping original header name -> final field name, or None if no
            field resolution was recorded (source didn't use normalize_fields).

        Note:
            For reverse lookup (final -> original), callers should invert this dict:
            `{v: k for k, v in mapping.items()}`
        """
        query = select(runs_table.c.source_field_resolution_json).where(runs_table.c.run_id == run_id)
        result = self._ops.execute_fetchone(query)

        if result is None:
            raise ValueError(f"Run {run_id} not found in database")

        resolution_json = result.source_field_resolution_json
        if resolution_json is None:
            return None

        # Parse the stored JSON structure
        # This is Tier 1 (our data) - crash on any anomaly
        resolution_data = json.loads(resolution_json)
        if not isinstance(resolution_data, dict):
            raise ValueError(f"Corrupt field resolution data for run {run_id}: expected dict, got {type(resolution_data).__name__}")

        # Tier 1: resolution_mapping MUST exist if JSON is stored
        # record_source_field_resolution() always stores this key, so missing = corruption
        if "resolution_mapping" not in resolution_data:
            raise ValueError(
                f"Corrupt field resolution data for run {run_id}: "
                f"missing required key 'resolution_mapping'. "
                f"This indicates database corruption - record_source_field_resolution() always stores this key."
            )

        resolution_mapping = resolution_data["resolution_mapping"]
        if not isinstance(resolution_mapping, dict):
            raise ValueError(f"Corrupt resolution_mapping for run {run_id}: expected dict, got {type(resolution_mapping).__name__}")

        # Verify all keys and values are strings (Tier 1 - crash on corruption)
        validated_mapping: dict[str, str] = {}
        for key, value in resolution_mapping.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError(
                    f"Corrupt resolution_mapping entry for run {run_id}: "
                    f"expected str->str, got {type(key).__name__}->{type(value).__name__}"
                )
            validated_mapping[key] = value

        return validated_mapping

    def update_run_status(self, run_id: str, status: RunStatus) -> None:
        """Update run status without setting completed_at.

        Used for intermediate status changes (e.g., paused → running during resume).
        For final completion, use complete_run() instead.

        Args:
            run_id: Run to update
            status: New RunStatus

        Note:
            This encapsulates run status updates for Orchestrator recovery.
            Only updates status field - does not set completed_at or reproducibility_grade.
        """
        self._ops.execute_update(runs_table.update().where(runs_table.c.run_id == run_id).values(status=status.value))

    def update_run_contract(self, run_id: str, contract: SchemaContract) -> None:
        """Update run with schema contract after first-row inference.

        Called when a source infers schema from the first row during OBSERVED mode.
        The contract is then locked and stored for all subsequent rows.

        Args:
            run_id: Run to update
            contract: SchemaContract with inferred fields (should be locked)

        Note:
            This is the only way to add a contract after begin_run().
            Used for sources that discover schema during load() rather than from config.
        """
        audit_record = ContractAuditRecord.from_contract(contract)
        schema_contract_json = audit_record.to_json()
        schema_contract_hash = contract.version_hash()

        self._ops.execute_update(
            runs_table.update()
            .where(runs_table.c.run_id == run_id)
            .values(
                schema_contract_json=schema_contract_json,
                schema_contract_hash=schema_contract_hash,
            )
        )

    def get_run_contract(self, run_id: str) -> SchemaContract | None:
        """Get schema contract for a run.

        Retrieves the stored schema contract and verifies integrity via hash.

        Args:
            run_id: Run to query

        Returns:
            SchemaContract if stored, None if no contract was stored

        Raises:
            ValueError: If stored contract fails integrity verification
        """
        query = select(runs_table.c.schema_contract_json).where(runs_table.c.run_id == run_id)
        row = self._ops.execute_fetchone(query)

        if row is None:
            return None

        schema_contract_json = row.schema_contract_json
        if schema_contract_json is None:
            return None

        # Restore via audit record (includes hash verification)
        audit_record = ContractAuditRecord.from_json(schema_contract_json)
        return audit_record.to_schema_contract()

    def record_secret_resolutions(
        self,
        run_id: str,
        resolutions: list[dict[str, Any]],
    ) -> None:
        """Record secret resolution events from deferred records.

        Called by orchestrator after run is created. The resolution records
        were captured during load_secrets_from_config() before the run existed.

        Args:
            run_id: The run ID to associate resolutions with
            resolutions: List of resolution records from load_secrets_from_config().
                Each record contains: env_var_name, source, vault_url, secret_name,
                timestamp, latency_ms, fingerprint (pre-computed HMAC-SHA256).
        """
        for rec in resolutions:
            self._ops.execute_insert(
                secret_resolutions_table.insert().values(
                    resolution_id=generate_id(),
                    run_id=run_id,
                    timestamp=rec["timestamp"],
                    env_var_name=rec["env_var_name"],
                    source=rec["source"],
                    vault_url=rec["vault_url"],
                    secret_name=rec["secret_name"],
                    fingerprint=rec["fingerprint"],
                    resolution_latency_ms=rec["latency_ms"],
                )
            )

    def get_secret_resolutions_for_run(self, run_id: str) -> list[SecretResolution]:
        """Get all secret resolution records for a run.

        These records document which secrets were loaded from Key Vault
        for this run, including their HMAC fingerprints (not values).

        Args:
            run_id: Run ID to query

        Returns:
            List of SecretResolution models, ordered by timestamp
        """
        query = (
            select(secret_resolutions_table)
            .where(secret_resolutions_table.c.run_id == run_id)
            .order_by(secret_resolutions_table.c.timestamp)
        )
        db_rows = self._ops.execute_fetchall(query)
        return [
            SecretResolution(
                resolution_id=row.resolution_id,
                run_id=row.run_id,
                timestamp=row.timestamp,
                env_var_name=row.env_var_name,
                source=row.source,
                vault_url=row.vault_url,
                secret_name=row.secret_name,
                fingerprint=row.fingerprint,
                resolution_latency_ms=row.resolution_latency_ms,
            )
            for row in db_rows
        ]

    def list_runs(self, *, status: RunStatus | None = None) -> list[Run]:
        """List all runs in the database.

        Args:
            status: Optional RunStatus filter

        Returns:
            List of Run models, ordered by started_at (newest first)
        """
        query = select(runs_table).order_by(runs_table.c.started_at.desc())

        if status is not None:
            query = query.where(runs_table.c.status == status.value)

        rows = self._ops.execute_fetchall(query)
        return [self._run_repo.load(row) for row in rows]

    def set_export_status(
        self,
        run_id: str,
        status: ExportStatus,
        *,
        error: str | None = None,
        export_format: str | None = None,
        export_sink: str | None = None,
    ) -> None:
        """Set export status for a run.

        This is separate from run status so export failures don't mask
        successful pipeline completion.

        Args:
            run_id: Run to update
            status: ExportStatus (PENDING, COMPLETED, or FAILED)
            error: Error message if status is FAILED
            export_format: Format used (csv, json)
            export_sink: Sink name used for export
        """
        updates: dict[str, Any] = {"export_status": status.value}

        if status == ExportStatus.COMPLETED:
            updates["exported_at"] = now()
            # Clear stale error when transitioning to completed
            updates["export_error"] = None
        elif status == ExportStatus.PENDING:
            # Clear stale error when transitioning to pending
            updates["export_error"] = None

        # Only set error if explicitly provided (for FAILED status)
        if error is not None:
            updates["export_error"] = error

        if export_format is not None:
            updates["export_format"] = export_format
        if export_sink is not None:
            updates["export_sink"] = export_sink

        self._ops.execute_update(runs_table.update().where(runs_table.c.run_id == run_id).values(**updates))

    def finalize_run(self, run_id: str, status: RunStatus) -> Run:
        """Finalize a run by computing grade and completing it.

        Convenience method that:
        1. Computes the reproducibility grade based on node determinism
        2. Completes the run with the specified status and computed grade

        Args:
            run_id: Run to finalize
            status: Final RunStatus (COMPLETED or FAILED)

        Returns:
            Updated Run model
        """
        grade = self.compute_reproducibility_grade(run_id)
        return self.complete_run(run_id, status, reproducibility_grade=grade.value)

    def compute_reproducibility_grade(self, run_id: str) -> ReproducibilityGrade:
        """Compute reproducibility grade for a run based on node determinism.

        Logic:
        - If any node has determinism='nondeterministic', returns REPLAY_REPRODUCIBLE
        - Otherwise returns FULL_REPRODUCIBLE
        - 'seeded' counts as reproducible

        Args:
            run_id: Run ID to compute grade for

        Returns:
            ReproducibilityGrade enum value
        """
        from elspeth.core.landscape.reproducibility import compute_grade

        return compute_grade(self._db, run_id)
