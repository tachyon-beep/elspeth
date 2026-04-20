"""Runtime-VAL manifest builder (ADR-010 M3, issue elspeth-1c8185dfec).

Extended under the ADR-010 §Semantics amendment (2026-04-20, N1 per-site
manifest, issue elspeth-10dc0b747f): the serialized manifest now carries
per-contract dispatch-site claims so the runs-row records not just *which*
contracts were active during run X but *which dispatch sites* each
contract implemented.

At orchestrator bootstrap the declaration-contract registry
(``EXPECTED_CONTRACT_SITES`` / ``registered_declaration_contracts``) and
the Tier-1 error registry (``TIER_1_ERRORS``) are both frozen. The M3
finding requires these to be serialized into the Landscape run-header so
an auditor can answer:

- "Which VAL contracts were in force during run X?"
- "Which dispatch sites did contract Y implement during run X?" (N1)
- "Was the ``can_drop_rows`` contract active during run X?" (time-series audit)
- "Are the TIER_1_ERRORS the same across runs X and Y?" (regression detection)

Shape:

    {
      "declaration_contracts": [
        {"name": "passes_through_input",
         "class_name": "PassThroughDeclarationContract",
         "class_module": "elspeth.engine.executors.pass_through",
         "dispatch_sites": ["batch_flush_check", "post_emission_check"]},
        ...
      ],
      "expected_contract_sites": {
         "passes_through_input": ["batch_flush_check", "post_emission_check"],
         ...
      },
      "tier_1_errors": [...],
    }

Ordering is deterministic (name / class_name / site sort) so the
serialised form is stable and hashable for cross-run regression comparisons.
"""

from __future__ import annotations

from typing import Any

from elspeth.contracts.declaration_contracts import (
    EXPECTED_CONTRACT_SITES,
    contract_sites,
    registered_declaration_contracts,
)
from elspeth.contracts.tier_registry import TIER_1_ERRORS, tier_1_reason


def build_runtime_val_manifest() -> dict[str, Any]:
    """Return a dict describing the runtime-VAL registries at call time."""
    declarations = [
        {
            "name": contract.name,
            "class_name": type(contract).__name__,
            "class_module": type(contract).__module__,
            "dispatch_sites": sorted(contract_sites(contract)),
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
    expected_contract_sites_serialized: dict[str, list[str]] = {name: sorted(sites) for name, sites in EXPECTED_CONTRACT_SITES.items()}
    return {
        "declaration_contracts": declarations,
        "expected_contract_sites": expected_contract_sites_serialized,
        "tier_1_errors": tier_1_entries,
    }
