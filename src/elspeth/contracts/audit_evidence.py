"""AuditEvidence nominal base class (ADR-010 §Decision 1).

Violation classes that contribute structured context to ExecutionError.context
via NodeStateGuard.__exit__ MUST inherit AuditEvidenceBase explicitly. A
structural Protocol was rejected (see ADR-010 §Alternative 3) because
single-method @runtime_checkable Protocols admit accidental duck-type matches
from unrelated classes, which would let stray to_audit_dict methods (e.g.,
in test helpers or third-party exceptions) populate the audit record with
attacker-chosen or accidental shapes.

This is L0 contracts — no imports from core, engine, or plugins.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any


class AuditEvidenceBase(ABC):
    """Nominal abstract base for audit-contributing exceptions.

    Inheriting this class is an explicit author declaration: "this exception
    contributes a structured payload to the Landscape audit trail." Subclasses
    MUST implement ``to_audit_dict()`` returning a JSON-serializable mapping.

    Any non-serializable value will surface as AuditIntegrityError at write
    time (Tier-1) — the canonical-JSON serializer crashes on non-primitive
    values.

    Implementation note: ``__init__`` explicitly re-enforces abstract-method
    rejection. CPython 3.13 routes ``BaseException.__new__`` through a C-level
    fast-path that bypasses the ``ABCMeta.__call__`` abstract-method guard, so
    without this guard a subclass that inherits both ``AuditEvidenceBase`` and
    any exception class can be instantiated without implementing
    ``to_audit_dict``. The guard restores the invariant that ABC promises.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        # Re-enforce ABC abstract-method rejection for exception subclasses.
        # CPython 3.13 routes BaseException.__new__ through a C-level fast-path
        # that bypasses ABCMeta.__call__'s abstract-method guard, so a subclass
        # that inherits both AuditEvidenceBase and any exception class can be
        # instantiated without this explicit check.
        # Direct attribute access is safe: ABCMeta always sets __abstractmethods__
        # on every class in the hierarchy (empty frozenset when all are implemented).
        abstract_methods: frozenset[str] = type(self).__abstractmethods__
        if abstract_methods:
            names = ", ".join(sorted(abstract_methods))
            raise TypeError(
                f"Can't instantiate abstract class {type(self).__name__} without an implementation for abstract method(s) {names}"
            )
        super().__init__(*args, **kwargs)

    @abstractmethod
    def to_audit_dict(self) -> Mapping[str, Any]:
        """Return a JSON-serializable mapping for the audit record."""
        raise NotImplementedError
