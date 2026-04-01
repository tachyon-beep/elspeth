"""NodeStateGuard — structural guarantee that node states reach terminal status.

The invariant "every token reaches exactly one terminal state" is central to
ELSPETH's audit integrity.  Before this guard, the invariant was enforced by
manually-scoped try/except blocks in each executor.  The problem: post-processing
code (output hashing, contract evolution) lived OUTSIDE those blocks, so failures
there left node_states permanently OPEN — violating the audit trail.

NodeStateGuard encodes the invariant structurally: any unhandled exception within
the ``with`` block automatically completes the state as FAILED before propagating.
"""

from __future__ import annotations

import logging
import time
from types import TracebackType
from typing import TYPE_CHECKING, Any

from elspeth.contracts import ExecutionError, NodeStateOpen
from elspeth.contracts.enums import NodeStateStatus
from elspeth.contracts.errors import AuditIntegrityError, FrameworkBugError, OrchestrationInvariantError
from elspeth.core.landscape import LandscapeRecorder

if TYPE_CHECKING:
    from elspeth.contracts.errors import CoalesceFailureReason, TransformErrorReason, TransformSuccessReason
    from elspeth.contracts.node_state_context import NodeStateContext

logger = logging.getLogger(__name__)


class NodeStateGuard:
    """Context manager that guarantees a node state reaches terminal status.

    Opens a node state in ``__enter__`` and, if the caller has not explicitly
    completed it before an exception triggers ``__exit__``, auto-completes the
    state as FAILED with the exception details.

    Usage::

        with NodeStateGuard(recorder, token_id=..., node_id=..., ...) as guard:
            ctx.state_id = guard.state_id
            # ... processing ...
            guard.complete(NodeStateStatus.COMPLETED, output_data=..., ...)

    If an exception is raised before ``guard.complete()`` is called, the state
    is automatically completed as FAILED.  If ``guard.complete()`` was already
    called, ``__exit__`` is a no-op (the state is already terminal).
    """

    __slots__ = (
        "_attempt",
        "_completed",
        "_completion_attempted",
        "_enter_time",
        "_input_data",
        "_node_id",
        "_recorder",
        "_run_id",
        "_state",
        "_step_index",
        "_token_id",
    )

    def __init__(
        self,
        recorder: LandscapeRecorder,
        *,
        token_id: str,
        node_id: str,
        run_id: str,
        step_index: int,
        input_data: dict[str, Any],  # Row data (Tier 2 pipeline data)
        attempt: int = 0,
    ) -> None:
        self._recorder = recorder
        self._token_id = token_id
        self._node_id = node_id
        self._run_id = run_id
        self._step_index = step_index
        self._input_data = input_data
        self._attempt = attempt
        self._enter_time: float = 0.0
        self._state: NodeStateOpen | None = None
        self._completed = False
        self._completion_attempted = False

    # -- context manager protocol ------------------------------------------

    def __enter__(self) -> NodeStateGuard:
        self._enter_time = time.perf_counter()
        self._state = self._recorder.begin_node_state(
            token_id=self._token_id,
            node_id=self._node_id,
            run_id=self._run_id,
            step_index=self._step_index,
            input_data=self._input_data,
            attempt=self._attempt,
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._completed:
            return

        if self._completion_attempted:
            # complete() was called but the recorder raised after committing.
            # The DB state is (probably) already terminal — writing FAILED on top
            # would corrupt the audit trail. Let the original exception propagate.
            return

        duration_ms = (time.perf_counter() - self._enter_time) * 1000

        if exc_type is None:
            # Clean exit without calling complete() — programming error.
            # Record FAILED first (preserve audit invariant), then crash.
            error = ExecutionError(
                exception="NodeStateGuard exited normally without complete()",
                exception_type="OrchestrationInvariantError",
                phase="executor_guard_missing_complete",
            )
            try:
                self._recorder.complete_node_state(
                    state_id=self.state_id,
                    status=NodeStateStatus.FAILED,
                    duration_ms=duration_ms,
                    error=error,
                )
            except (FrameworkBugError, AuditIntegrityError):
                raise  # System bugs and audit corruption must crash immediately
            except Exception as db_err:
                raise AuditIntegrityError(
                    f"Cannot record FAILED for state {self.state_id} after missing complete() — "
                    f"audit trail has permanent OPEN state (Tier 1 violation). "
                    f"DB error: {type(db_err).__name__}: {db_err}"
                ) from db_err
            raise OrchestrationInvariantError(
                f"NodeStateGuard for state {self.state_id} exited without complete(). "
                f"This is a bug in the calling executor — every code path must call "
                f"guard.complete() before the with-block exits normally."
            )

        # An exception occurred and the state was never completed.
        # Auto-complete as FAILED so the audit trail has a terminal record.
        exc_error = ExecutionError(
            exception=str(exc_val),
            exception_type=exc_type.__name__,
            phase="executor_post_process",
        )
        try:
            self._recorder.complete_node_state(
                state_id=self.state_id,
                status=NodeStateStatus.FAILED,
                duration_ms=duration_ms,
                error=exc_error,
            )
        except (FrameworkBugError, AuditIntegrityError):
            raise  # System bugs and audit corruption must crash immediately
        except (TypeError, AttributeError, KeyError, NameError):
            raise  # Programming errors in recorder — crash to surface the bug
        except Exception as db_err:
            # Audit trail corruption (permanent OPEN state) is MORE critical than
            # the original exception. Raise AuditIntegrityError with both contexts.
            raise AuditIntegrityError(
                f"Cannot record FAILED for state {self.state_id} while handling "
                f"{exc_type.__name__}: {exc_val} — audit trail has permanent OPEN state "
                f"(Tier 1 violation). DB error: {type(db_err).__name__}: {db_err}"
            ) from db_err

    # -- public API --------------------------------------------------------

    @property
    def state(self) -> NodeStateOpen:
        """The opened node state.  Only valid after ``__enter__``."""
        if self._state is None:
            raise OrchestrationInvariantError("NodeStateGuard.state accessed before __enter__")
        return self._state

    @property
    def state_id(self) -> str:
        """Shorthand for ``guard.state.state_id``."""
        return self.state.state_id

    @property
    def completed(self) -> bool:
        """Whether the caller has explicitly completed this state."""
        return self._completed

    def complete(
        self,
        status: NodeStateStatus,
        *,
        output_data: dict[str, Any] | list[dict[str, Any]] | None = None,
        duration_ms: float | None = None,
        error: ExecutionError | TransformErrorReason | CoalesceFailureReason | None = None,
        success_reason: TransformSuccessReason | None = None,
        context_after: NodeStateContext | None = None,
    ) -> None:
        """Complete the node state.  Guard will not intervene after this.

        Sets ``_completion_attempted`` BEFORE the recorder call so that if
        ``complete_node_state()`` commits but then raises (post-commit
        validation), ``__exit__`` will not overwrite the already-persisted
        terminal state with FAILED.
        """
        self._completion_attempted = True
        self._recorder.complete_node_state(  # type: ignore[call-overload,misc]  # generic NodeStateStatus vs Literal overloads
            state_id=self.state_id,
            status=status,
            output_data=output_data,
            duration_ms=duration_ms,
            error=error,
            success_reason=success_reason,
            context_after=context_after,
        )
        self._completed = True
