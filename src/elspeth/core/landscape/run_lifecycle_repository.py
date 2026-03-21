"""Run lifecycle repository for Landscape audit records.

Owns all run lifecycle operations: begin, complete, finalize, status updates,
schema contracts, secret resolutions, export status, and reproducibility grading.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from elspeth.contracts import (
    ContractAuditRecord,
    ExportStatus,
    ReproducibilityGrade,
    Run,
    RunStatus,
    SecretResolution,
    SecretResolutionInput,
)
from elspeth.contracts.errors import AuditIntegrityError
from elspeth.core.canonical import canonical_json, stable_hash
from elspeth.core.landscape._database_ops import DatabaseOps
from elspeth.core.landscape._helpers import generate_id, now
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.model_loaders import RunLoader
from elspeth.core.landscape.reproducibility import compute_grade
from elspeth.core.landscape.schema import (
    runs_table,
    secret_resolutions_table,
)

if TYPE_CHECKING:
    from elspeth.contracts.schema_contract import SchemaContract


_TERMINAL_RUN_STATUSES = frozenset({RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.INTERRUPTED})


class RunLifecycleRepository:
    """Run lifecycle operations for the Landscape audit trail.

    Handles: begin, complete, finalize, status updates, schema contracts,
    secret resolutions, export status, and reproducibility grading.
    """

    def __init__(self, db: LandscapeDB, ops: DatabaseOps, run_loader: RunLoader) -> None:
        self._db = db
        self._ops = ops
        self._run_loader = run_loader

    def begin_run(
        self,
        config: Mapping[str, Any],
        canonical_version: str,
        *,
        run_id: str | None = None,
        reproducibility_grade: ReproducibilityGrade | None = None,
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
        reproducibility_grade: ReproducibilityGrade | None = None,
    ) -> Run:
        """Complete a pipeline run.

        Args:
            run_id: Run to complete
            status: Final RunStatus (COMPLETED, FAILED, or INTERRUPTED)
            reproducibility_grade: Optional final grade. When None, preserves
                any grade already stored on the run (e.g., from begin_run).

        Returns:
            Updated Run model

        Raises:
            AuditIntegrityError: If status is not a terminal run status
            AuditIntegrityError: If run_id not found (via execute_update zero-rows check)
        """
        if status not in _TERMINAL_RUN_STATUSES:
            raise AuditIntegrityError(
                f"complete_run() requires terminal status, got {status.value!r}. "
                f"Valid terminal statuses: {sorted(s.value for s in _TERMINAL_RUN_STATUSES)}"
            )

        timestamp = now()

        # Only include reproducibility_grade in UPDATE when explicitly provided.
        # Passing None would overwrite an existing grade with NULL (Bug 318f74).
        values: dict[str, Any] = {
            "status": status,
            "completed_at": timestamp,
        }
        if reproducibility_grade is not None:
            values["reproducibility_grade"] = reproducibility_grade

        self._ops.execute_update(runs_table.update().where(runs_table.c.run_id == run_id).values(**values))

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
        return self._run_loader.load(row)

    def get_source_schema(self, run_id: str) -> str:
        """Get source schema JSON for a run (for resume/type restoration).

        Args:
            run_id: Run to query

        Returns:
            Source schema JSON string

        Raises:
            AuditIntegrityError: If run not found or has no source schema

        Note:
            This encapsulates Landscape schema access for Orchestrator resume.
            Schema is required for type fidelity when restoring rows from payloads.
        """
        query = select(runs_table.c.source_schema_json).where(runs_table.c.run_id == run_id)
        run_row = self._ops.execute_fetchone(query)

        if run_row is None:
            raise AuditIntegrityError(f"Run {run_id} not found in database")

        source_schema_json = run_row.source_schema_json
        if source_schema_json is None:
            raise AuditIntegrityError(
                f"Run {run_id} has no source schema stored. "
                f"This run was created before source schema storage was implemented. "
                f"Cannot resume without schema - type fidelity would be violated."
            )

        if type(source_schema_json) is not str:
            raise AuditIntegrityError(
                f"Run {run_id} source_schema_json is {type(source_schema_json).__name__}, "
                f"expected str — audit data corruption (Tier 1 violation)"
            )
        return source_schema_json

    def record_source_field_resolution(
        self,
        run_id: str,
        resolution_mapping: Mapping[str, str],
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

        try:
            self._ops.execute_update(
                runs_table.update().where(runs_table.c.run_id == run_id).values(source_field_resolution_json=resolution_json)
            )
        except AuditIntegrityError as exc:
            raise AuditIntegrityError(f"Cannot record source field resolution: run {run_id} not found") from exc

    def get_source_field_resolution(self, run_id: str) -> dict[str, str] | None:
        """Get source field resolution mapping for a run.

        Returns the mapping from original header names to final (normalized) field names.
        Used by sinks with headers: original to restore original headers.

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
            raise AuditIntegrityError(f"Run {run_id} not found in database")

        resolution_json = result.source_field_resolution_json
        if resolution_json is None:
            return None

        # Parse the stored JSON structure
        # This is Tier 1 (our data) — crash on any anomaly
        try:
            resolution_data = json.loads(resolution_json)
        except json.JSONDecodeError as exc:
            raise AuditIntegrityError(
                f"Corrupt field resolution JSON for run {run_id}: "
                f"failed to parse stored JSON — database corruption (Tier 1 violation). "
                f"Parse error: {exc}"
            ) from exc
        if not isinstance(resolution_data, dict):
            raise AuditIntegrityError(
                f"Corrupt field resolution data for run {run_id}: expected dict, got {type(resolution_data).__name__}"
            )

        # Tier 1: resolution_mapping MUST exist if JSON is stored
        # record_source_field_resolution() always stores this key, so missing = corruption
        if "resolution_mapping" not in resolution_data:
            raise AuditIntegrityError(
                f"Corrupt field resolution data for run {run_id}: "
                f"missing required key 'resolution_mapping'. "
                f"This indicates database corruption — record_source_field_resolution() always stores this key."
            )

        resolution_mapping = resolution_data["resolution_mapping"]
        if not isinstance(resolution_mapping, dict):
            raise AuditIntegrityError(
                f"Corrupt resolution_mapping for run {run_id}: expected dict, got {type(resolution_mapping).__name__}"
            )

        # Verify all keys and values are strings (Tier 1 — crash on corruption)
        # Key type check is defense-in-depth: JSON keys are always strings after json.loads(),
        # but guards against hypothetical non-JSON deserialization paths.
        validated_mapping: dict[str, str] = {}
        for key, value in resolution_mapping.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise AuditIntegrityError(
                    f"Corrupt resolution_mapping entry for run {run_id}: "
                    f"expected str->str, got {type(key).__name__}->{type(value).__name__}"
                )
            validated_mapping[key] = value

        return validated_mapping

    def update_run_status(self, run_id: str, status: RunStatus) -> None:
        """Update run status without setting completed_at.

        Used for intermediate status changes (e.g., RUNNING during resume).
        For final completion, use complete_run() instead.

        Args:
            run_id: Run to update
            status: New RunStatus

        Raises:
            AuditIntegrityError: If run_id not found or current status is COMPLETED (immutable)

        Note:
            This encapsulates run status updates for Orchestrator recovery.
            Only updates status field — does not set completed_at or reproducibility_grade.

            COMPLETED runs are immutable — a completed run succeeded and its audit
            record is final. FAILED and INTERRUPTED runs CAN be transitioned back
            to RUNNING during resume (orchestrator recovery path).
        """
        with self._db.connection() as conn:
            result = conn.execute(
                runs_table.update()
                .where(runs_table.c.run_id == run_id)
                .where(runs_table.c.status != RunStatus.COMPLETED.value)
                .values(status=status)
            )
            if result.rowcount == 0:
                existing = conn.execute(select(runs_table.c.status).where(runs_table.c.run_id == run_id)).fetchone()
                if existing is not None and existing.status == RunStatus.COMPLETED.value:
                    raise AuditIntegrityError(
                        f"Cannot transition run {run_id} from COMPLETED to {status.value!r}. "
                        f"Completed runs are immutable. "
                        f"FAILED/INTERRUPTED runs can be resumed via update_run_status."
                    )
                raise AuditIntegrityError(f"Cannot update run status to {status.value!r}: run {run_id} not found")

    def update_run_contract(self, run_id: str, contract: SchemaContract) -> None:
        """Update run with schema contract after first-row inference.

        Called when a source infers schema from the first row during OBSERVED mode.
        The contract is then locked and stored for all subsequent rows.

        Args:
            run_id: Run to update
            contract: SchemaContract with inferred fields (should be locked)

        Raises:
            AuditIntegrityError: If run already has a contract (overwrite = evidence loss)

        Note:
            This is the only way to add a contract after begin_run().
            Used for sources that discover schema during load() rather than from config.
        """
        audit_record = ContractAuditRecord.from_contract(contract)
        schema_contract_json = audit_record.to_json()
        schema_contract_hash = contract.version_hash()

        # Atomic guard: conditional UPDATE only sets contract when column is NULL.
        # This prevents TOCTOU races where a concurrent thread could set the contract
        # between a check-then-write pair. The WHERE clause makes overwrite impossible.
        with self._db.connection() as conn:
            result = conn.execute(
                runs_table.update()
                .where(runs_table.c.run_id == run_id)
                .where(runs_table.c.schema_contract_json.is_(None))
                .values(
                    schema_contract_json=schema_contract_json,
                    schema_contract_hash=schema_contract_hash,
                )
            )
            if result.rowcount == 0:
                # Zero rows updated — either run doesn't exist or contract already set.
                # Distinguish the two cases for a clear error message.
                existing = conn.execute(select(runs_table.c.schema_contract_json).where(runs_table.c.run_id == run_id)).fetchone()
                if existing is not None and existing.schema_contract_json is not None:
                    raise AuditIntegrityError(
                        f"Cannot update schema contract for run {run_id}: "
                        f"contract already exists. update_run_contract is only valid "
                        f"when no contract was set at begin_run()."
                    )
                raise AuditIntegrityError(f"Cannot update schema contract: run {run_id} not found")

    def get_run_contract(self, run_id: str) -> SchemaContract | None:
        """Get schema contract for a run.

        Retrieves the stored schema contract and verifies integrity via hash.

        Args:
            run_id: Run to query

        Returns:
            SchemaContract if stored, None if run exists but no contract was stored

        Raises:
            AuditIntegrityError: If run_id not found, stored contract hash doesn't match
                recomputed hash, or hash is NULL while JSON is present
        """
        query = select(
            runs_table.c.run_id,
            runs_table.c.schema_contract_json,
            runs_table.c.schema_contract_hash,
        ).where(runs_table.c.run_id == run_id)
        row = self._ops.execute_fetchone(query)

        if row is None:
            raise AuditIntegrityError(f"Run {run_id} not found in database")

        schema_contract_json = row.schema_contract_json
        if schema_contract_json is None:
            return None

        # Restore via audit record (includes hash verification)
        audit_record = ContractAuditRecord.from_json(schema_contract_json)
        contract = audit_record.to_schema_contract()

        # Verify stored hash matches recomputed hash (Tier 1 integrity)
        # Both begin_run() and update_run_contract() always set JSON and hash together.
        # NULL hash with non-NULL JSON is itself a corruption signal.
        stored_hash = row.schema_contract_hash
        if stored_hash is None:
            raise AuditIntegrityError(
                f"Schema contract JSON is present but hash is NULL for run {run_id}. "
                f"Both fields must be set together — database corruption or tampering."
            )
        recomputed_hash = contract.version_hash()
        if recomputed_hash != stored_hash:
            raise AuditIntegrityError(
                f"Schema contract hash mismatch for run {run_id}: "
                f"stored={stored_hash}, recomputed={recomputed_hash}. "
                f"This indicates database corruption or tampering."
            )

        return contract

    def record_secret_resolutions(
        self,
        run_id: str,
        resolutions: list[SecretResolutionInput],
    ) -> None:
        """Record secret resolution events from deferred records.

        Called by orchestrator after run is created. The resolution records
        were captured during load_secrets_from_config() before the run existed.

        All inserts are batched in a single transaction for atomicity —
        either all resolutions are recorded or none are.

        Args:
            run_id: The run ID to associate resolutions with
            resolutions: Typed resolution records from load_secrets_from_config().
        """
        if not resolutions:
            return
        with self._db.connection() as conn:
            for rec in resolutions:
                result = conn.execute(
                    secret_resolutions_table.insert().values(
                        resolution_id=generate_id(),
                        run_id=run_id,
                        timestamp=rec.timestamp,
                        env_var_name=rec.env_var_name,
                        source=rec.source,
                        vault_url=rec.vault_url,
                        secret_name=rec.secret_name,
                        fingerprint=rec.fingerprint,
                        resolution_latency_ms=rec.resolution_latency_ms,
                    )
                )
                if result.rowcount == 0:
                    raise AuditIntegrityError(
                        f"Secret resolution insert failed for run {run_id} — zero rows affected (audit write failure)"
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
            query = query.where(runs_table.c.status == status)

        rows = self._ops.execute_fetchall(query)
        return [self._run_loader.load(row) for row in rows]

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
        # Validate error/status consistency — error is only meaningful with FAILED
        if error is not None and status != ExportStatus.FAILED:
            raise AuditIntegrityError(
                f"Cannot set export_error with status={status.value}. Error messages are only valid with FAILED status."
            )

        updates: dict[str, Any] = {"export_status": status}

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

        try:
            self._ops.execute_update(runs_table.update().where(runs_table.c.run_id == run_id).values(**updates))
        except AuditIntegrityError as exc:
            raise AuditIntegrityError(f"Cannot set export status to {status.value!r}: run {run_id} not found") from exc

    def finalize_run(self, run_id: str, status: RunStatus) -> Run:
        """Finalize a run by computing grade and completing it.

        Convenience method that:
        1. Computes the reproducibility grade based on node determinism
        2. Completes the run with the specified status and computed grade

        Args:
            run_id: Run to finalize
            status: Final RunStatus (COMPLETED, FAILED, or INTERRUPTED)

        Returns:
            Updated Run model

        Note:
            Grade computation and run completion execute in separate transactions.
            This is an accepted limitation — the invariant that all nodes are registered
            before finalize_run is called ensures the grade is stable between reads.
            A single-transaction approach would require refactoring compute_grade's
            database access (tracked for future consideration).
        """
        grade = self.compute_reproducibility_grade(run_id)
        return self.complete_run(run_id, status, reproducibility_grade=grade)

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

        Note:
            Uses self._db directly (bypassing DatabaseOps) because compute_grade()
            needs raw connection access for multi-statement reads within a single
            connection. This dual access pattern (self._ops + self._db) is accepted:
            future repositories (B2/B3) will also need self._db for atomic
            multi-table transactions. Both are injected via __init__.
        """
        return compute_grade(self._db, run_id)
