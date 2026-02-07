# src/elspeth/core/landscape/_error_recording.py
"""Error recording methods for LandscapeRecorder."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from elspeth.contracts import (
    NonCanonicalMetadata,
    TransformErrorReason,
    TransformErrorRecord,
    ValidationErrorRecord,
    ValidationErrorWithContract,
)
from elspeth.core.canonical import canonical_json, repr_hash, stable_hash
from elspeth.core.landscape._helpers import generate_id, now
from elspeth.core.landscape.schema import (
    transform_errors_table,
    validation_errors_table,
)

if TYPE_CHECKING:
    from elspeth.contracts.errors import ContractViolation
    from elspeth.contracts.schema_contract import PipelineRow
    from elspeth.core.landscape._database_ops import DatabaseOps
    from elspeth.core.landscape.database import LandscapeDB
    from elspeth.core.landscape.repositories import (
        TransformErrorRepository,
        ValidationErrorRepository,
    )


class ErrorRecordingMixin:
    """Error recording and query methods. Mixed into LandscapeRecorder."""

    # Shared state annotations (set by LandscapeRecorder.__init__)
    _db: LandscapeDB
    _ops: DatabaseOps
    _validation_error_repo: ValidationErrorRepository
    _transform_error_repo: TransformErrorRepository

    def record_validation_error(
        self,
        run_id: str,
        node_id: str | None,
        row_data: Any,
        error: str,
        schema_mode: str,
        destination: str,
        *,
        contract_violation: ContractViolation | None = None,
    ) -> str:
        """Record a validation error in the audit trail.

        Called when a source row fails schema validation. The row is
        quarantined (not processed further) but we record what we saw
        for complete audit coverage.

        Args:
            run_id: Current run ID
            node_id: Node where validation failed
            row_data: The row that failed validation (may be non-dict or contain non-finite values)
            error: Error description
            schema_mode: Schema mode that caught the error ("fixed", "flexible", "observed")
            destination: Where row was routed ("discard" or sink name)
            contract_violation: Optional contract violation details for structured auditing

        Returns:
            error_id for tracking
        """
        logger = logging.getLogger(__name__)
        error_id = f"verr_{generate_id()[:12]}"

        # Tier-3 (external data) trust boundary: row_data may be non-canonical
        # Try canonical hash/JSON first, fall back to safe representations
        try:
            row_hash = stable_hash(row_data)
            row_data_json = canonical_json(row_data)
        except (ValueError, TypeError) as e:
            # Non-canonical data (NaN, Infinity, non-dict, etc.)
            # Use repr() fallback to preserve audit trail
            row_preview = repr(row_data)[:200] + "..." if len(repr(row_data)) > 200 else repr(row_data)
            logger.warning(
                "Validation error row not canonically serializable (using repr fallback): %s | Row preview: %s",
                str(e),
                row_preview,
            )
            row_hash = repr_hash(row_data)
            # Store non-canonical representation with type metadata
            metadata = NonCanonicalMetadata.from_error(row_data, e)
            row_data_json = json.dumps(metadata.to_dict())

        # Extract contract violation details if provided
        violation_type: str | None = None
        normalized_field_name: str | None = None
        original_field_name: str | None = None
        expected_type: str | None = None
        actual_type: str | None = None

        if contract_violation is not None:
            violation_record = ValidationErrorWithContract.from_violation(contract_violation)
            violation_type = violation_record.violation_type
            normalized_field_name = violation_record.normalized_field_name
            original_field_name = violation_record.original_field_name
            expected_type = violation_record.expected_type
            actual_type = violation_record.actual_type

        self._ops.execute_insert(
            validation_errors_table.insert().values(
                error_id=error_id,
                run_id=run_id,
                node_id=node_id,
                row_hash=row_hash,
                row_data_json=row_data_json,
                error=error,
                schema_mode=schema_mode,
                destination=destination,
                created_at=now(),
                violation_type=violation_type,
                normalized_field_name=normalized_field_name,
                original_field_name=original_field_name,
                expected_type=expected_type,
                actual_type=actual_type,
            )
        )

        return error_id

    def record_transform_error(
        self,
        run_id: str,
        token_id: str,
        transform_id: str,
        row_data: dict[str, Any] | PipelineRow,
        error_details: TransformErrorReason,
        destination: str,
    ) -> str:
        """Record a transform processing error in the audit trail.

        Called when a transform returns TransformResult.error().
        This is for legitimate errors, NOT transform bugs.

        Args:
            run_id: Current run ID
            token_id: Token ID for the row
            transform_id: Transform that returned the error
            row_data: The row that could not be processed
            error_details: Error details from TransformResult (TransformErrorReason TypedDict)
            destination: Where row was routed ("discard" or sink name)

        Returns:
            error_id for tracking
        """
        error_id = f"terr_{generate_id()[:12]}"

        self._ops.execute_insert(
            transform_errors_table.insert().values(
                error_id=error_id,
                run_id=run_id,
                token_id=token_id,
                transform_id=transform_id,
                row_hash=stable_hash(row_data),
                row_data_json=canonical_json(row_data),
                error_details_json=canonical_json(error_details),
                destination=destination,
                created_at=now(),
            )
        )

        return error_id

    def get_validation_errors_for_row(self, run_id: str, row_hash: str) -> list[ValidationErrorRecord]:
        """Get validation errors for a row by its hash.

        Validation errors are keyed by row_hash since quarantined rows
        never get row_ids (they're rejected before entering the pipeline).

        Args:
            run_id: Run ID to query
            row_hash: Hash of the row data

        Returns:
            List of ValidationErrorRecord models
        """
        query = select(validation_errors_table).where(
            validation_errors_table.c.run_id == run_id,
            validation_errors_table.c.row_hash == row_hash,
        )
        rows = self._ops.execute_fetchall(query)
        return [self._validation_error_repo.load(r) for r in rows]

    def get_validation_errors_for_run(self, run_id: str) -> list[ValidationErrorRecord]:
        """Get all validation errors for a run.

        Args:
            run_id: Run ID to query

        Returns:
            List of ValidationErrorRecord models, ordered by created_at
        """
        query = (
            select(validation_errors_table).where(validation_errors_table.c.run_id == run_id).order_by(validation_errors_table.c.created_at)
        )
        rows = self._ops.execute_fetchall(query)
        return [self._validation_error_repo.load(r) for r in rows]

    def get_transform_errors_for_token(self, token_id: str) -> list[TransformErrorRecord]:
        """Get transform errors for a specific token.

        Args:
            token_id: Token ID to query

        Returns:
            List of TransformErrorRecord models
        """
        query = select(transform_errors_table).where(
            transform_errors_table.c.token_id == token_id,
        )
        rows = self._ops.execute_fetchall(query)
        return [self._transform_error_repo.load(r) for r in rows]

    def get_transform_errors_for_run(self, run_id: str) -> list[TransformErrorRecord]:
        """Get all transform errors for a run.

        Args:
            run_id: Run ID to query

        Returns:
            List of TransformErrorRecord models, ordered by created_at
        """
        query = (
            select(transform_errors_table).where(transform_errors_table.c.run_id == run_id).order_by(transform_errors_table.c.created_at)
        )
        rows = self._ops.execute_fetchall(query)
        return [self._transform_error_repo.load(r) for r in rows]
