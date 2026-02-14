# src/elspeth/engine/executors/state_guard.py
"""NodeStateGuard — structural guarantee that node states reach terminal status.

The invariant "every token reaches exactly one terminal state" is central to
ELSPETH's audit integrity.  Before this guard, the invariant was enforced by
manually-scoped try/except blocks in each executor.  The problem: post-processing
code (output hashing, contract evolution) lived OUTSIDE those blocks, so failures
there left node_states permanently OPEN — violating the audit trail.

NodeStateGuard encodes the invariant structurally: any unhandled exception within
the ``with`` block automatically completes the state as FAILED before propagating.
"""

import logging
import time
from types import TracebackType
from typing import Any

from elspeth.contracts import ExecutionError, NodeStateOpen
from elspeth.contracts.enums import NodeStateStatus
from elspeth.contracts.errors import OrchestrationInvariantError
from elspeth.core.landscape import LandscapeRecorder

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

    # -- context manager protocol ------------------------------------------

    def __enter__(self) -> "NodeStateGuard":
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
        if self._completed or exc_type is None:
            # State was explicitly completed, or the block exited normally.
            # In the normal-exit case the caller MUST have called complete();
            # if they didn't, that's a programming error we don't mask.
            return

        # An exception occurred and the state was never completed.
        # Auto-complete as FAILED so the audit trail has a terminal record.
        duration_ms = (time.perf_counter() - self._enter_time) * 1000
        error: ExecutionError = {
            "exception": str(exc_val),
            "type": exc_type.__name__,
            "phase": "executor_post_process",
        }
        try:
            self._recorder.complete_node_state(
                state_id=self.state_id,
                status=NodeStateStatus.FAILED,
                duration_ms=duration_ms,
                error=error,
            )
        except Exception:
            # If we cannot record the failure (e.g. DB is down), log but don't
            # mask the original exception — the caller needs to see it.
            logger.error(
                "NodeStateGuard: failed to auto-complete state %s as FAILED while handling %s",
                self.state_id,
                exc_type.__name__,
                exc_info=True,
            )

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

    def complete(self, status: NodeStateStatus, **kwargs: Any) -> None:
        """Complete the node state.  Guard will not intervene after this.

        Passes through to ``recorder.complete_node_state()`` with the
        guard's ``state_id`` prepended.  All keyword arguments are forwarded
        verbatim (``duration_ms``, ``output_data``, ``error``,
        ``success_reason``, ``context_after``).
        """
        self._recorder.complete_node_state(  # type: ignore[call-overload]
            state_id=self.state_id,
            status=status,
            **kwargs,
        )
        self._completed = True
