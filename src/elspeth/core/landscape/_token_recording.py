# src/elspeth/core/landscape/_token_recording.py
"""Token lifecycle methods for LandscapeRecorder."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from elspeth.contracts import (
    Row,
    RowOutcome,
    Token,
    TokenOutcome,
)
from elspeth.contracts.errors import AuditIntegrityError
from elspeth.core.canonical import canonical_json, repr_hash, stable_hash
from elspeth.core.landscape._helpers import generate_id, now
from elspeth.core.landscape.schema import (
    rows_table,
    token_outcomes_table,
    token_parents_table,
    tokens_table,
)

if TYPE_CHECKING:
    from elspeth.contracts.payload_store import PayloadStore
    from elspeth.core.landscape._database_ops import DatabaseOps
    from elspeth.core.landscape.database import LandscapeDB
    from elspeth.core.landscape.repositories import (
        RowRepository,
        TokenOutcomeRepository,
        TokenRepository,
    )


class TokenRecordingMixin:
    """Token lifecycle methods. Mixed into LandscapeRecorder."""

    # Shared state annotations (set by LandscapeRecorder.__init__)
    _db: LandscapeDB
    _ops: DatabaseOps
    _row_repo: RowRepository
    _token_repo: TokenRepository
    _token_outcome_repo: TokenOutcomeRepository
    _payload_store: PayloadStore | None

    def _resolve_run_id_for_row(self, row_id: str) -> str:
        """Resolve the run_id that owns a given row_id.

        This is Tier 1 (our data). If the row doesn't exist, it's a bug
        in our code or database corruption -- crash immediately.

        Args:
            row_id: Row ID to look up

        Returns:
            run_id that owns the row

        Raises:
            AuditIntegrityError: If row_id not found (Tier 1 corruption)
        """
        query = select(rows_table.c.run_id).where(rows_table.c.row_id == row_id)
        result = self._ops.execute_fetchone(query)
        if result is None:
            raise AuditIntegrityError(
                f"Token references row_id={row_id!r} which does not exist in the rows table. "
                f"This is Tier 1 data corruption -- the row should have been created before any token."
            )
        run_id: str = result.run_id
        return run_id

    def _resolve_token_ownership(self, token_id: str) -> tuple[str, str]:
        """Resolve the (row_id, run_id) that owns a given token_id.

        Looks up token -> row_id, then row -> run_id. This is Tier 1 (our data).
        If the token or its row doesn't exist, it's a bug or database corruption.

        Args:
            token_id: Token ID to look up

        Returns:
            Tuple of (row_id, run_id) that own the token

        Raises:
            AuditIntegrityError: If token or its row not found (Tier 1 corruption)
        """
        query = select(tokens_table.c.row_id, tokens_table.c.run_id).where(tokens_table.c.token_id == token_id)
        result = self._ops.execute_fetchone(query)
        if result is None:
            raise AuditIntegrityError(
                f"Token {token_id!r} does not exist in the tokens table. "
                f"This is Tier 1 data corruption -- the token should have been created before recording outcomes."
            )
        return result.row_id, result.run_id

    def _validate_token_run_ownership(self, token_id: str, run_id: str) -> None:
        """Validate that a token belongs to the specified run.

        Per Tier 1 trust model: cross-run contamination of audit records is
        evidence tampering. Crash immediately if the invariant is violated.

        Args:
            token_id: Token to validate
            run_id: Expected run ID

        Raises:
            AuditIntegrityError: If token does not belong to the specified run
        """
        _row_id, actual_run_id = self._resolve_token_ownership(token_id)
        if actual_run_id != run_id:
            raise AuditIntegrityError(
                f"Cross-run contamination prevented: token {token_id!r} belongs to "
                f"run {actual_run_id!r}, but caller supplied run_id={run_id!r}. "
                f"This would corrupt the audit trail by attributing records to the wrong run."
            )

    def _validate_token_row_ownership(self, token_id: str, row_id: str) -> None:
        """Validate that a token belongs to the specified row.

        Per Tier 1 trust model: cross-row lineage corruption makes the audit
        trail unreliable. Crash immediately if the invariant is violated.

        Args:
            token_id: Token to validate
            row_id: Expected row ID

        Raises:
            AuditIntegrityError: If token does not belong to the specified row
        """
        actual_row_id, _run_id = self._resolve_token_ownership(token_id)
        if actual_row_id != row_id:
            raise AuditIntegrityError(
                f"Cross-row lineage corruption prevented: token {token_id!r} belongs to "
                f"row {actual_row_id!r}, but caller supplied row_id={row_id!r}. "
                f"This would create invalid parent-child lineage across different rows."
            )

    def create_row(
        self,
        run_id: str,
        source_node_id: str,
        row_index: int,
        data: dict[str, Any],
        *,
        row_id: str | None = None,
        quarantined: bool = False,
    ) -> Row:
        """Create a source row record.

        Args:
            run_id: Run this row belongs to
            source_node_id: Source node that loaded this row
            row_index: Position in source (0-indexed)
            data: Row data for hashing and optional storage
            row_id: Optional row ID (generated if not provided)
            quarantined: If True, data is Tier-3 external data that may contain
                non-canonical values (NaN, Infinity). Uses repr_hash fallback.

        Returns:
            Row model

        Note:
            Payload persistence is handled by LandscapeRecorder, not callers.
            If self._payload_store is configured, the method will:
            1. Serialize data using canonical_json (handles pandas/numpy/datetime/Decimal)
            2. Store in payload store
            3. Record reference in audit trail

            This ensures Landscape owns its audit format end-to-end.
        """
        from elspeth.core.canonical import canonical_json

        row_id = row_id or generate_id()

        # Quarantined rows are Tier-3 external data that may contain non-canonical
        # values (NaN, Infinity). Use repr_hash as a fallback per canonical.py docs.
        if quarantined:
            try:
                data_hash = stable_hash(data)
            except (ValueError, TypeError):
                data_hash = repr_hash(data)
        else:
            data_hash = stable_hash(data)

        timestamp = now()

        # Landscape owns payload persistence - serialize and store if configured
        final_payload_ref: str | None = None
        if self._payload_store is not None:
            # Canonical JSON handles pandas/numpy/Decimal/datetime types.
            # For quarantined data, fall back to json.dumps(repr()) if
            # canonical serialization fails on non-canonical values.
            if quarantined:
                try:
                    payload_bytes = canonical_json(data).encode("utf-8")
                except (ValueError, TypeError):
                    payload_bytes = json.dumps({"_repr": repr(data)}).encode("utf-8")
            else:
                payload_bytes = canonical_json(data).encode("utf-8")
            final_payload_ref = self._payload_store.store(payload_bytes)

        row = Row(
            row_id=row_id,
            run_id=run_id,
            source_node_id=source_node_id,
            row_index=row_index,
            source_data_hash=data_hash,
            source_data_ref=final_payload_ref,
            created_at=timestamp,
        )

        self._ops.execute_insert(
            rows_table.insert().values(
                row_id=row.row_id,
                run_id=row.run_id,
                source_node_id=row.source_node_id,
                row_index=row.row_index,
                source_data_hash=row.source_data_hash,
                source_data_ref=row.source_data_ref,
                created_at=row.created_at,
            )
        )

        return row

    def create_token(
        self,
        row_id: str,
        *,
        token_id: str | None = None,
        branch_name: str | None = None,
        fork_group_id: str | None = None,
        join_group_id: str | None = None,
    ) -> Token:
        """Create a token (row instance in DAG path).

        Derives run_id from the row record to guarantee run ownership
        consistency. The tokens table stores run_id to enable composite
        FK enforcement on downstream tables.

        Args:
            row_id: Source row this token represents
            token_id: Optional token ID (generated if not provided)
            branch_name: Optional branch name (for forked tokens)
            fork_group_id: Optional fork group (links siblings)
            join_group_id: Optional join group (links merged tokens)

        Returns:
            Token model

        Raises:
            AuditIntegrityError: If row_id does not exist (Tier 1 corruption)
        """
        token_id = token_id or generate_id()
        timestamp = now()

        # Derive run_id from the row record (Tier 1 -- our data, must exist)
        run_id = self._resolve_run_id_for_row(row_id)

        token = Token(
            token_id=token_id,
            row_id=row_id,
            fork_group_id=fork_group_id,
            join_group_id=join_group_id,
            branch_name=branch_name,
            created_at=timestamp,
            run_id=run_id,
        )

        self._ops.execute_insert(
            tokens_table.insert().values(
                token_id=token.token_id,
                row_id=token.row_id,
                run_id=run_id,
                fork_group_id=token.fork_group_id,
                join_group_id=token.join_group_id,
                branch_name=token.branch_name,
                created_at=token.created_at,
            )
        )

        return token

    def fork_token(
        self,
        parent_token_id: str,
        row_id: str,
        branches: list[str],
        *,
        run_id: str,
        step_in_pipeline: int | None = None,
    ) -> tuple[list[Token], str]:
        """Fork a token to multiple branches.

        ATOMIC: Creates children AND records parent FORKED outcome in single transaction.
        Stores branch contract for recovery validation.

        Validates that parent_token_id belongs to the specified row_id and run_id
        before any writes. Cross-run/cross-row contamination crashes immediately
        per Tier 1 trust model.

        Args:
            parent_token_id: Token being forked
            row_id: Row ID (same for all children)
            branches: List of branch names (must have at least one)
            run_id: Run ID (required for outcome recording)
            step_in_pipeline: Step in the DAG where the fork occurs

        Returns:
            Tuple of (child Token models, fork_group_id)

        Raises:
            ValueError: If branches is empty (defense-in-depth for audit integrity)
            AuditIntegrityError: If parent token does not belong to specified run/row
        """
        # Defense-in-depth: validate even though RoutingAction.fork_to_paths()
        # already validates. Per CLAUDE.md "no silent drops" - empty forks
        # would cause tokens to disappear without audit trail.
        if not branches:
            raise ValueError("fork_token requires at least one branch")

        # Validate parent token ownership before any writes (Tier 1 invariant)
        self._validate_token_run_ownership(parent_token_id, run_id)
        self._validate_token_row_ownership(parent_token_id, row_id)

        fork_group_id = generate_id()
        children = []

        with self._db.connection() as conn:
            # 1. Create child tokens
            for ordinal, branch_name in enumerate(branches):
                child_id = generate_id()
                timestamp = now()

                # Create child token (run_id derived from parent -- already validated)
                conn.execute(
                    tokens_table.insert().values(
                        token_id=child_id,
                        row_id=row_id,
                        run_id=run_id,
                        fork_group_id=fork_group_id,
                        branch_name=branch_name,
                        step_in_pipeline=step_in_pipeline,
                        created_at=timestamp,
                    )
                )

                # Record parent relationship
                conn.execute(
                    token_parents_table.insert().values(
                        token_id=child_id,
                        parent_token_id=parent_token_id,
                        ordinal=ordinal,
                    )
                )

                children.append(
                    Token(
                        token_id=child_id,
                        row_id=row_id,
                        fork_group_id=fork_group_id,
                        branch_name=branch_name,
                        step_in_pipeline=step_in_pipeline,
                        created_at=timestamp,
                        run_id=run_id,
                    )
                )

            # 2. Record parent FORKED outcome in SAME transaction (atomic)
            outcome_id = f"out_{generate_id()[:12]}"
            conn.execute(
                token_outcomes_table.insert().values(
                    outcome_id=outcome_id,
                    run_id=run_id,
                    token_id=parent_token_id,
                    outcome=RowOutcome.FORKED.value,
                    is_terminal=1,
                    recorded_at=now(),
                    fork_group_id=fork_group_id,
                    expected_branches_json=json.dumps(branches),
                )
            )

        return children, fork_group_id

    def coalesce_tokens(
        self,
        parent_token_ids: list[str],
        row_id: str,
        *,
        step_in_pipeline: int | None = None,
    ) -> Token:
        """Coalesce multiple tokens into one (join operation).

        Creates a new token representing the merged result.
        Records all parent relationships.

        Validates that all parent tokens belong to the specified row_id and
        that they all share the same run_id. Cross-run/cross-row contamination
        crashes immediately per Tier 1 trust model.

        Args:
            parent_token_ids: Tokens being merged
            row_id: Row ID for the merged token
            step_in_pipeline: Step in the DAG where the coalesce occurs

        Returns:
            Merged Token model

        Raises:
            AuditIntegrityError: If parent tokens do not belong to specified row
                or if parent tokens span multiple runs
        """
        # Validate all parent tokens belong to the same row and run (Tier 1 invariant)
        run_id: str | None = None
        for parent_id in parent_token_ids:
            self._validate_token_row_ownership(parent_id, row_id)
            _row_id, parent_run_id = self._resolve_token_ownership(parent_id)
            if run_id is None:
                run_id = parent_run_id
            elif parent_run_id != run_id:
                raise AuditIntegrityError(
                    f"Cross-run contamination prevented in coalesce: parent token {parent_id!r} "
                    f"belongs to run {parent_run_id!r}, but other parents belong to run {run_id!r}. "
                    f"All parent tokens in a coalesce must belong to the same run."
                )

        # Derive run_id from row if no parents (edge case: shouldn't happen in practice)
        if run_id is None:
            run_id = self._resolve_run_id_for_row(row_id)

        join_group_id = generate_id()
        token_id = generate_id()
        timestamp = now()

        with self._db.connection() as conn:
            # Create merged token
            conn.execute(
                tokens_table.insert().values(
                    token_id=token_id,
                    row_id=row_id,
                    run_id=run_id,
                    join_group_id=join_group_id,
                    step_in_pipeline=step_in_pipeline,
                    created_at=timestamp,
                )
            )

            # Record all parent relationships
            for ordinal, parent_id in enumerate(parent_token_ids):
                conn.execute(
                    token_parents_table.insert().values(
                        token_id=token_id,
                        parent_token_id=parent_id,
                        ordinal=ordinal,
                    )
                )

        return Token(
            token_id=token_id,
            row_id=row_id,
            join_group_id=join_group_id,
            step_in_pipeline=step_in_pipeline,
            created_at=timestamp,
            run_id=run_id,
        )

    def expand_token(
        self,
        parent_token_id: str,
        row_id: str,
        count: int,
        *,
        run_id: str,
        step_in_pipeline: int | None = None,
        record_parent_outcome: bool = True,
    ) -> tuple[list[Token], str]:
        """Expand a token into multiple child tokens (deaggregation).

        ATOMIC: Creates children AND optionally records parent EXPANDED outcome
        in single transaction.

        Validates that parent_token_id belongs to the specified row_id and run_id
        before any writes. Cross-run/cross-row contamination crashes immediately
        per Tier 1 trust model.

        Creates N child tokens from a single parent for 1->N expansion.
        All children share the same row_id (same source row) and are
        linked to the parent via token_parents table.

        Unlike fork_token (parallel DAG paths with branch names), expand_token
        creates sequential children for deaggregation transforms.

        Args:
            parent_token_id: Token being expanded
            row_id: Row ID (same for all children)
            count: Number of child tokens to create (must be >= 1)
            run_id: Run ID (required for atomic outcome recording)
            step_in_pipeline: Step where expansion occurs (optional)
            record_parent_outcome: If True (default), record EXPANDED outcome for parent.
                Set to False for batch aggregation where parent gets CONSUMED_IN_BATCH.

        Returns:
            Tuple of (child Token list, expand_group_id)

        Raises:
            ValueError: If count < 1
            AuditIntegrityError: If parent token does not belong to specified run/row
        """
        if count < 1:
            raise ValueError("expand_token requires at least 1 child")

        # Validate parent token ownership before any writes (Tier 1 invariant)
        self._validate_token_run_ownership(parent_token_id, run_id)
        self._validate_token_row_ownership(parent_token_id, row_id)

        expand_group_id = generate_id()
        children = []

        with self._db.connection() as conn:
            for ordinal in range(count):
                child_id = generate_id()
                timestamp = now()

                # Create child token with expand_group_id (run_id from parent -- already validated)
                conn.execute(
                    tokens_table.insert().values(
                        token_id=child_id,
                        row_id=row_id,
                        run_id=run_id,
                        expand_group_id=expand_group_id,
                        step_in_pipeline=step_in_pipeline,
                        created_at=timestamp,
                    )
                )

                # Record parent relationship
                conn.execute(
                    token_parents_table.insert().values(
                        token_id=child_id,
                        parent_token_id=parent_token_id,
                        ordinal=ordinal,
                    )
                )

                children.append(
                    Token(
                        token_id=child_id,
                        row_id=row_id,
                        expand_group_id=expand_group_id,
                        step_in_pipeline=step_in_pipeline,
                        created_at=timestamp,
                        run_id=run_id,
                    )
                )

            # Optionally record parent EXPANDED outcome in SAME transaction (atomic)
            # This eliminates the crash window where children exist but parent
            # outcome is not yet recorded.
            #
            # Set record_parent_outcome=False for batch aggregation where the
            # parent token gets CONSUMED_IN_BATCH instead of EXPANDED.
            if record_parent_outcome:
                outcome_id = f"out_{generate_id()[:12]}"
                conn.execute(
                    token_outcomes_table.insert().values(
                        outcome_id=outcome_id,
                        run_id=run_id,
                        token_id=parent_token_id,
                        outcome=RowOutcome.EXPANDED.value,
                        is_terminal=1,
                        recorded_at=now(),
                        expand_group_id=expand_group_id,
                        # Store expected count for recovery validation
                        expected_branches_json=json.dumps({"count": count}),
                    )
                )

        return children, expand_group_id

    def _validate_outcome_fields(
        self,
        outcome: RowOutcome,
        *,
        sink_name: str | None,
        batch_id: str | None,
        fork_group_id: str | None,
        join_group_id: str | None,
        expand_group_id: str | None,
        error_hash: str | None,
    ) -> None:
        """Validate required fields are present for each outcome type.

        Enforces the token outcome contract from docs/contracts/token-outcomes/00-token-outcome-contract.md.
        This is defense-in-depth: callers SHOULD pass correct fields, but this catches bugs.

        Raises:
            ValueError: If a required field is missing for the outcome type
        """
        # Map outcome to required field(s)
        # Contract: Each outcome type has specific required fields
        if outcome == RowOutcome.COMPLETED:
            if sink_name is None:
                raise ValueError(
                    "COMPLETED outcome requires sink_name but got None. "
                    "Contract violation - see docs/contracts/token-outcomes/00-token-outcome-contract.md"
                )
        elif outcome == RowOutcome.ROUTED:
            if sink_name is None:
                raise ValueError(
                    "ROUTED outcome requires sink_name but got None. "
                    "Contract violation - see docs/contracts/token-outcomes/00-token-outcome-contract.md"
                )
        elif outcome == RowOutcome.FORKED:
            if fork_group_id is None:
                raise ValueError(
                    "FORKED outcome requires fork_group_id but got None. "
                    "Contract violation - see docs/contracts/token-outcomes/00-token-outcome-contract.md"
                )
        elif outcome == RowOutcome.FAILED:
            if error_hash is None:
                raise ValueError(
                    "FAILED outcome requires error_hash but got None. "
                    "Contract violation - see docs/contracts/token-outcomes/00-token-outcome-contract.md"
                )
        elif outcome == RowOutcome.QUARANTINED:
            if error_hash is None:
                raise ValueError(
                    "QUARANTINED outcome requires error_hash but got None. "
                    "Contract violation - see docs/contracts/token-outcomes/00-token-outcome-contract.md"
                )
        elif outcome == RowOutcome.CONSUMED_IN_BATCH:
            if batch_id is None:
                raise ValueError(
                    "CONSUMED_IN_BATCH outcome requires batch_id but got None. "
                    "Contract violation - see docs/contracts/token-outcomes/00-token-outcome-contract.md"
                )
        elif outcome == RowOutcome.COALESCED:
            if join_group_id is None:
                raise ValueError(
                    "COALESCED outcome requires join_group_id but got None. "
                    "Contract violation - see docs/contracts/token-outcomes/00-token-outcome-contract.md"
                )
        elif outcome == RowOutcome.EXPANDED:
            if expand_group_id is None:
                raise ValueError(
                    "EXPANDED outcome requires expand_group_id but got None. "
                    "Contract violation - see docs/contracts/token-outcomes/00-token-outcome-contract.md"
                )
        elif outcome == RowOutcome.BUFFERED and batch_id is None:
            raise ValueError(
                "BUFFERED outcome requires batch_id but got None. Contract violation - see docs/contracts/token-outcomes/00-token-outcome-contract.md"
            )
        # No else needed - exhaustive enum handling above

    def record_token_outcome(
        self,
        run_id: str,
        token_id: str,
        outcome: RowOutcome,
        *,
        sink_name: str | None = None,
        batch_id: str | None = None,
        fork_group_id: str | None = None,
        join_group_id: str | None = None,
        expand_group_id: str | None = None,
        error_hash: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Record a token's outcome in the audit trail.

        Called at the moment the outcome is determined in processor.py.
        For BUFFERED tokens, a second call records the terminal outcome
        when the batch flushes.

        Validates that the token belongs to the specified run_id before recording.
        Cross-run contamination crashes immediately per Tier 1 trust model.

        Args:
            run_id: Current run ID
            token_id: Token that reached this outcome
            outcome: The RowOutcome enum value
            sink_name: For ROUTED/COMPLETED - which sink (REQUIRED)
            batch_id: For CONSUMED_IN_BATCH/BUFFERED - which batch (REQUIRED)
            fork_group_id: For FORKED - the fork group (REQUIRED)
            join_group_id: For COALESCED - the join group (REQUIRED)
            expand_group_id: For EXPANDED - the expand group (REQUIRED)
            error_hash: For FAILED/QUARANTINED - hash of error details (REQUIRED)
            context: Optional additional context (stored as JSON)

        Returns:
            outcome_id for tracking

        Raises:
            ValueError: If required fields for outcome type are missing
            AuditIntegrityError: If token does not belong to the specified run
            IntegrityError: If terminal outcome already exists for token
        """
        # Validate required fields per outcome type (contract enforcement)
        # See docs/contracts/token-outcomes/00-token-outcome-contract.md
        self._validate_outcome_fields(
            outcome=outcome,
            sink_name=sink_name,
            batch_id=batch_id,
            fork_group_id=fork_group_id,
            join_group_id=join_group_id,
            expand_group_id=expand_group_id,
            error_hash=error_hash,
        )

        # Validate token belongs to the specified run (Tier 1 invariant)
        self._validate_token_run_ownership(token_id, run_id)

        outcome_id = f"out_{generate_id()[:12]}"
        is_terminal = outcome.is_terminal
        context_json = canonical_json(context) if context is not None else None

        self._ops.execute_insert(
            token_outcomes_table.insert().values(
                outcome_id=outcome_id,
                run_id=run_id,
                token_id=token_id,
                outcome=outcome.value,
                is_terminal=1 if is_terminal else 0,
                recorded_at=now(),
                sink_name=sink_name,
                batch_id=batch_id,
                fork_group_id=fork_group_id,
                join_group_id=join_group_id,
                expand_group_id=expand_group_id,
                error_hash=error_hash,
                context_json=context_json,
            )
        )

        return outcome_id

    def get_token_outcome(self, token_id: str) -> TokenOutcome | None:
        """Get the terminal outcome for a token.

        Returns the terminal outcome if one exists, otherwise the most
        recent non-terminal outcome (BUFFERED).

        Args:
            token_id: Token to look up

        Returns:
            TokenOutcome dataclass or None if no outcome recorded
        """
        # Get most recent outcome (terminal preferred)
        query = (
            select(token_outcomes_table)
            .where(token_outcomes_table.c.token_id == token_id)
            .order_by(
                token_outcomes_table.c.is_terminal.desc(),  # Terminal first
                token_outcomes_table.c.recorded_at.desc(),  # Then by time
            )
            .limit(1)
        )
        result = self._ops.execute_fetchone(query)
        if result is None:
            return None
        return self._token_outcome_repo.load(result)

    def get_token_outcomes_for_row(self, run_id: str, row_id: str) -> list[TokenOutcome]:
        """Get all token outcomes for a row in a single query.

        Uses JOIN to avoid N+1 query pattern when resolving row_id to tokens.
        Critical for explain() disambiguation with forks/expands.

        Args:
            run_id: Run ID to filter by (prevents cross-run contamination)
            row_id: Row ID

        Returns:
            List of TokenOutcome objects, empty if no outcomes recorded.
            Ordered by recorded_at for deterministic behavior.
        """
        # Single JOIN query: tokens + outcomes
        query = (
            select(
                token_outcomes_table.c.outcome_id,
                token_outcomes_table.c.run_id,
                token_outcomes_table.c.token_id,
                token_outcomes_table.c.outcome,
                token_outcomes_table.c.is_terminal,
                token_outcomes_table.c.recorded_at,
                token_outcomes_table.c.sink_name,
                token_outcomes_table.c.batch_id,
                token_outcomes_table.c.fork_group_id,
                token_outcomes_table.c.join_group_id,
                token_outcomes_table.c.expand_group_id,
                token_outcomes_table.c.error_hash,
                token_outcomes_table.c.context_json,
                token_outcomes_table.c.expected_branches_json,
            )
            .join(
                tokens_table,
                token_outcomes_table.c.token_id == tokens_table.c.token_id,
            )
            .where(tokens_table.c.row_id == row_id)
            .where(token_outcomes_table.c.run_id == run_id)
            .order_by(token_outcomes_table.c.recorded_at)
        )
        rows = self._ops.execute_fetchall(query)
        return [self._token_outcome_repo.load(r) for r in rows]
