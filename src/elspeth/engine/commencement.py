"""Commencement gate evaluation — pre-flight go/no-go checks."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from elspeth.contracts.errors import CommencementGateFailedError
from elspeth.contracts.freeze import deep_freeze
from elspeth.core.dependency_config import CommencementGateConfig, CommencementGateResult
from elspeth.core.expression_parser import ExpressionParser

_GATE_ALLOWED_NAMES = ["collections", "dependency_runs", "env"]


def build_preflight_context(
    *,
    dependency_results: dict[str, Any],
    collection_probes: dict[str, Any],
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Assemble the pre-flight context dict for gate expression evaluation.

    Returns a namespace dict with three keys accessible in gate expressions:
    - ``dependency_runs``: {name: {run_id, duration_ms, indexed_at}} for each dependency
    - ``collections``: {name: {reachable, count}} for each probed collection
    - ``env``: operator environment variables (Tier 3 — defaults to os.environ)
    """
    return {
        "dependency_runs": dependency_results,
        "collections": collection_probes,
        "env": env if env is not None else dict(os.environ),
    }


def _build_audit_snapshot(context: dict[str, Any]) -> Mapping[str, Any]:
    """Build a frozen context snapshot for audit, excluding env.

    Env is excluded because it may contain secrets (API keys, tokens).
    The audit snapshot records what the gate saw for traceability,
    but env values are operator-controlled Tier 3 data that shouldn't
    be persisted in the audit trail.
    """
    snapshot = {
        "dependency_runs": context["dependency_runs"],
        "collections": context["collections"],
    }
    frozen: Mapping[str, Any] = deep_freeze(snapshot)
    return frozen


def evaluate_commencement_gates(
    gates: list[CommencementGateConfig],
    context: dict[str, Any],
) -> list[CommencementGateResult]:
    """Evaluate gates sequentially. Raises CommencementGateFailedError on failure.

    Context must be a namespace dict with keys matching _GATE_ALLOWED_NAMES.
    The env dict is deep-frozen before passing to ExpressionParser (Tier 3 boundary).
    """
    # Deep-freeze entire context for expression evaluation (Tier 3 boundary for env)
    frozen_context = deep_freeze(context)
    # Build audit snapshot from frozen context — not mutable original (TOCTOU)
    audit_snapshot = _build_audit_snapshot(frozen_context)

    results: list[CommencementGateResult] = []
    for gate in gates:
        try:
            parser = ExpressionParser(
                gate.condition,
                allowed_names=_GATE_ALLOWED_NAMES,
            )
            passed = bool(parser.evaluate(frozen_context))
        except CommencementGateFailedError:
            raise
        except Exception as exc:
            raise CommencementGateFailedError(
                gate_name=gate.name,
                condition=gate.condition,
                reason=f"Expression raised {type(exc).__name__}: {exc}",
                context_snapshot=audit_snapshot,
            ) from exc

        if not passed:
            raise CommencementGateFailedError(
                gate_name=gate.name,
                condition=gate.condition,
                reason="Condition evaluated to falsy",
                context_snapshot=audit_snapshot,
            )

        results.append(
            CommencementGateResult(
                name=gate.name,
                condition=gate.condition,
                result=True,
                context_snapshot=audit_snapshot,
            )
        )
    return results
