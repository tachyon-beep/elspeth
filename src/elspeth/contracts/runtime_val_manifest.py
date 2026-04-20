"""Runtime-VAL manifest builder (ADR-010 M3, issue elspeth-1c8185dfec).

At orchestrator bootstrap the declaration-contract registry
(``EXPECTED_CONTRACTS`` / ``registered_declaration_contracts``) and the
Tier-1 error registry (``TIER_1_ERRORS``) are both frozen. The M3 finding
requires these to be serialized into the Landscape run-header so an
auditor can answer:

- "Which VAL contracts were in force during run X?"
- "Was the ``can_drop_rows`` contract active during run X?" (time-series audit)
- "Are the TIER_1_ERRORS the same across runs X and Y?" (regression detection)

This module owns the serialization contract. The shape is:

    {
      "declaration_contracts": [
        {"name": "passes_through_input",
         "class_name": "PassThroughDeclarationContract",
         "class_module": "elspeth.engine.executors.pass_through"},
        ...
      ],
      "expected_contract_manifest": ["passes_through_input", ...],  # closed-set manifest (C2)
      "tier_1_errors": [
        {"class_name": "AuditIntegrityError",
         "class_module": "elspeth.contracts.errors",
         "reason": "ADR-008: annotation lie corrupts audit trail"},
        ...
      ],
    }

Ordering is deterministic (name / class_name sort) so the serialised form
is stable and hashable for cross-run regression comparisons.
"""

from __future__ import annotations

from typing import Any

from elspeth.contracts.declaration_contracts import (
    EXPECTED_CONTRACTS,
    registered_declaration_contracts,
)
from elspeth.contracts.tier_registry import TIER_1_ERRORS, tier_1_reason


def build_runtime_val_manifest() -> dict[str, Any]:
    """Return a dict describing the runtime-VAL registries at call time.

    Both registries are expected to be frozen by the time this is called
    (orchestrator bootstrap completes ``freeze_declaration_registry()`` and
    ``freeze_tier_registry()`` before ``begin_run`` runs). Freeze is not
    asserted here — the caller's bootstrap sequence is authoritative.

    The return value is a plain dict so the caller can serialize it with
    whatever canonicaliser is appropriate (``canonical_json`` in the
    Landscape path gives deterministic output suited for hashing).
    """
    declarations = [
        {
            "name": contract.name,
            "class_name": type(contract).__name__,
            "class_module": type(contract).__module__,
        }
        for contract in sorted(registered_declaration_contracts(), key=lambda c: c.name)
    ]
    tier_1_entries = [
        {
            "class_name": cls.__name__,
            "class_module": cls.__module__,
            "reason": tier_1_reason(cls),
        }
        for cls in sorted(TIER_1_ERRORS, key=lambda c: (c.__module__, c.__name__))
    ]
    return {
        "declaration_contracts": declarations,
        "expected_contract_manifest": sorted(EXPECTED_CONTRACTS),
        "tier_1_errors": tier_1_entries,
    }
