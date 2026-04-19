"""Tier-1 exception registry (ADR-010 §Decision 2).

Replaces the hand-maintained TIER_1_ERRORS tuple. Three safety mechanisms
beyond the v0 design (see plan Revision History — Review v1):

1. ``@tier_1_error(reason=...)`` is a factory — it requires a justification
   string. Auditors reviewing Tier-1 additions can grep for the reason.
2. Module-prefix allowlist: only callers in ``elspeth.contracts.*``,
   ``elspeth.engine.*``, or ``elspeth.core.*`` may register. Plugin modules
   cannot elevate their own exceptions (reviewer B6/F-6).
3. ``freeze_tier_registry()`` is called at end of bootstrap. Registration
   after freeze raises ``FrameworkBugError`` (reviewer B5/F-2).

``FrameworkBugError`` is re-exported from this module because Task 4 will
re-export it from ``errors.py``; this module cannot import ``errors`` (circular).
"""

from __future__ import annotations

import inspect
import sys
from collections.abc import Iterator
from typing import TypeVar


# Intentional forward-declaration: FrameworkBugError is defined here first so
# ``errors.py`` can apply ``@tier_1_error`` to it without circular import.
class FrameworkBugError(Exception):
    """Raised when the framework encounters an internal inconsistency.

    This indicates a bug in ELSPETH itself, not user error or external failure.
    Unlike OrchestrationInvariantError (specific to orchestration flow), this
    is a general-purpose exception for any framework-level bug.

    Examples of conditions that trigger this:
    - Double-completing an operation (already completed, trying to complete again)
    - Missing required context (record_call with neither state_id nor operation_id)
    - Completing a non-existent operation

    Recovery: These errors indicate bugs in framework code that must be fixed.
    They should never occur in correct operation.

    Moved here from errors.py for the circular-import break; errors.py
    re-exports it for back-compat (Task 4).
    """


_REGISTRY: list[type[BaseException]] = []
_REASONS: dict[type[BaseException], str] = {}
_FROZEN: bool = False

_ALLOWED_MODULE_PREFIXES: tuple[str, ...] = (
    "elspeth.contracts.",
    "elspeth.engine.",
    "elspeth.core.",
    *(("tests.",) if "pytest" in sys.modules else ()),
)

_ExcT = TypeVar("_ExcT", bound=BaseException)


def tier_1_error(_cls: type | None = None, *, reason: str):  # type: ignore[no-untyped-def]
    """Factory returning a decorator that registers ``cls`` as Tier-1.

    Usage:
        @tier_1_error(reason="ADR-008: annotation lie corrupts audit trail")
        class AuditIntegrityError(Exception): ...

    Args:
        reason: Non-empty justification string. Recorded in the registry
            and queryable via ``tier_1_reason(cls)``.

    Raises:
        TypeError: applied without ``reason`` (positional-class usage like
            ``@tier_1_error`` instead of ``@tier_1_error(reason=...)``).
        ValueError: ``reason`` is empty.
        PermissionError: caller module is outside the allowlist.
        FrameworkBugError: registry is frozen.
    """
    if _cls is not None:
        raise TypeError("@tier_1_error requires a reason kwarg — use @tier_1_error(reason=...) not @tier_1_error")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("@tier_1_error(reason=...) requires non-empty reason string")

    def _decorator(cls: type[_ExcT]) -> type[_ExcT]:
        caller_module = _inspect_caller_module()
        return _register_with_module_prefix(cls=cls, reason=reason, caller_module=caller_module)

    return _decorator


def _inspect_caller_module() -> str:
    # Frame 0 = this function; frame 1 = _decorator; frame 2 = decoration site.
    frame = inspect.stack()[2]
    module: str = frame.frame.f_globals.get("__name__", "")
    return module


def _register_with_module_prefix[ExcT: BaseException](*, cls: type[ExcT], reason: str, caller_module: str) -> type[ExcT]:
    if _FROZEN:
        raise FrameworkBugError(
            f"Cannot register {cls.__name__!r}: TIER_1_ERRORS registry is frozen. "
            f"Bootstrap is complete; new Tier-1 classes must be added before plugin discovery finishes."
        )
    if not (isinstance(cls, type) and issubclass(cls, BaseException)):
        raise TypeError(f"@tier_1_error applied to {cls!r} — must be a BaseException subclass")
    if not any(caller_module.startswith(p) or caller_module == p.rstrip(".") for p in _ALLOWED_MODULE_PREFIXES):
        raise PermissionError(
            f"@tier_1_error used from {caller_module!r}; only allowed from "
            f"{_ALLOWED_MODULE_PREFIXES!r}. Plugin modules cannot elevate their "
            f"own exceptions to Tier-1 — request ADR review instead."
        )
    if cls in _REGISTRY:
        if _REASONS[cls] != reason:
            raise ValueError(
                f"{cls.__name__} already registered with reason {_REASONS[cls]!r}; double-registration with conflicting reason {reason!r}"
            )
        return cls
    _REGISTRY.append(cls)
    _REASONS[cls] = reason
    return cls


def tier_1_reason(cls: type[BaseException]) -> str:
    """Return the registered reason for ``cls``, or raise KeyError."""
    return _REASONS[cls]


def freeze_tier_registry() -> None:
    """Seal the registry. Subsequent registrations raise ``FrameworkBugError``.

    Called at end of orchestrator bootstrap (see Task 5b)."""
    global _FROZEN
    _FROZEN = True


class _Tier1ErrorsView:
    """Live view of the Tier-1 error registry.

    Live view over ``_REGISTRY``. Unlike a snapshot tuple, membership tests
    (``__contains__``), iteration, and ``count`` always see the current registry
    contents. Not a drop-in tuple replacement: ``len()``, indexing, and use in
    ``except`` clauses are intentionally unsupported — use the ``errors.TIER_1_ERRORS``
    module attribute (PEP 562 re-export added in Task 4) when tuple semantics
    are required.
    """

    def __contains__(self, item: object) -> bool:
        return item in _REGISTRY

    def __iter__(self) -> Iterator[type[BaseException]]:
        return iter(list(_REGISTRY))

    def __len__(self) -> int:
        return len(_REGISTRY)

    def __repr__(self) -> str:
        names = [cls.__name__ for cls in _REGISTRY]
        return f"TIER_1_ERRORS({names})"

    def count(self, item: object) -> int:
        return _REGISTRY.count(item)  # type: ignore[arg-type]  # list[type[BaseException]].count(object) is safe


TIER_1_ERRORS = _Tier1ErrorsView()
