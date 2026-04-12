# src/elspeth/core/dag/coalesce_merge.py
"""Coalesce merge logic for schema computation.

Extracted from builder.py to enable direct testing without reimplementation.
This module contains the core logic for merging schemas at coalesce points.

Two operations are provided:

1. merge_guaranteed_fields: Combines effective guarantees from branch schemas
   using union (require_all) or intersection (other policies).

2. merge_union_fields: Combines typed field definitions with policy-aware
   required/optional semantics for union merge strategy.

Both functions are called by builder.py during graph construction and can
be called directly by tests to verify semantics without reimplementing logic.
"""

from __future__ import annotations

from collections.abc import Mapping

from elspeth.contracts.schema import FieldDefinition, SchemaConfig
from elspeth.core.dag.models import GraphValidationError


def merge_guaranteed_fields(
    branch_schemas: Mapping[str, SchemaConfig],
    *,
    require_all: bool,
) -> tuple[str, ...] | None:
    """Merge guaranteed fields from branch schemas.

    Computes the merged guaranteed_fields tuple for a coalesce node based on
    the effective guarantees from each branch and the coalesce policy.

    Args:
        branch_schemas: Map of branch name to SchemaConfig
        require_all: If True, use union semantics (all branches always arrive,
            so any branch's guarantee survives). If False, use intersection
            semantics (some branches may be lost, so only shared guarantees
            survive).

    Returns:
        Merged guaranteed fields tuple, or None if no branch has effective
        guarantees (abstention semantics — the coalesce makes no claim).

    Note:
        The None-vs-empty-tuple distinction is semantic:
        - None = no branch has effective guarantees (abstain from vote)
        - () = branches have guarantees but merge is empty set (explicit zero)
    """
    guaranteed_sets: list[set[str]] = []
    for schema_cfg in branch_schemas.values():
        if schema_cfg.has_effective_guarantees:
            guaranteed_sets.append(set(schema_cfg.get_effective_guaranteed_fields()))

    if not guaranteed_sets:
        return None

    if require_all:
        merged = set.union(*guaranteed_sets)
    else:
        merged = set.intersection(*guaranteed_sets)

    return tuple(sorted(merged)) if merged else ()


def merge_union_fields(
    branch_schemas: Mapping[str, SchemaConfig],
    *,
    require_all: bool,
    coalesce_id: str | None = None,
    guaranteed_fields: tuple[str, ...] | None = None,
    audit_fields: tuple[str, ...] | None = None,
) -> SchemaConfig:
    """Merge typed fields from branch schemas using union merge strategy.

    Combines field definitions from all branches with policy-aware handling
    of required/optional semantics:

    - require_all (OR semantics): A field is required if required in ANY
      branch. Since all branches always arrive under require_all, any branch's
      guarantee is honored in the merged output.

    - other policies (AND semantics): A field is required only if required in
      ALL branches. Since some branches may be lost, only shared guarantees
      survive.

    Branch-exclusive fields (present in only one branch) are handled specially:
    - require_all: Preserve source branch's required flag (branch always arrives)
    - other policies: Force optional (branch may not arrive)

    Args:
        branch_schemas: Map of branch name to SchemaConfig
        require_all: If True, use OR semantics for required; if False, use AND
        coalesce_id: Optional node ID for error messages (default: generic)
        guaranteed_fields: Pre-computed guaranteed_fields to include in result
        audit_fields: Pre-computed audit_fields to include in result

    Returns:
        Merged SchemaConfig. If all branches are observed-mode or no branches
        contribute fields, returns an observed-mode schema. Otherwise returns
        a flexible-mode schema with merged field definitions.

    Raises:
        GraphValidationError: If branches have incompatible types for the same
            field name.
    """
    # Track (type, required, nullable, branch) for each field.
    # The nullable flag is critical for require_all+last_wins: if ANY branch can
    # produce None for a field, the merged field is nullable even if "required"
    # (because that branch's None value can win the collision).
    seen_types: dict[str, tuple[str, bool, bool, str]] = {}
    branches_with_field: dict[str, set[str]] = {}
    contributing_branches: set[str] = set()
    all_observed = False

    for branch_name, schema_cfg in branch_schemas.items():
        if schema_cfg.is_observed:
            all_observed = True
            break
        if schema_cfg.fields is None:
            continue
        contributing_branches.add(branch_name)
        for fd in schema_cfg.fields:
            if fd.name not in branches_with_field:
                branches_with_field[fd.name] = set()
            branches_with_field[fd.name].add(branch_name)

            fd_nullable = fd.nullable

            if fd.name in seen_types:
                prior_type, prior_req, prior_nullable, prior_branch = seen_types[fd.name]
                if prior_type != fd.field_type:
                    node_desc = f"'{coalesce_id}'" if coalesce_id else "coalesce node"
                    raise GraphValidationError(
                        f"Coalesce node {node_desc} receives incompatible "
                        f"types for field '{fd.name}' in union merge: "
                        f"branch '{prior_branch}' has {prior_type!r}, "
                        f"branch '{branch_name}' has {fd.field_type!r}. "
                        "Union merge requires compatible types on shared fields."
                    )
                if require_all:
                    # OR for required: required if required in ANY branch.
                    merged_req = prior_req or fd.required
                    # BUT: nullable if ANY branch allows None. With last_wins (default),
                    # any branch can win the collision, so if ANY is nullable, merged is.
                    merged_nullable = prior_nullable or fd_nullable
                    seen_types[fd.name] = (prior_type, merged_req, merged_nullable, prior_branch)
                else:
                    # AND: optional if optional in ANY branch.
                    merged_req = prior_req and fd.required
                    # nullable if ANY is nullable (same rule)
                    merged_nullable = prior_nullable or fd_nullable
                    seen_types[fd.name] = (prior_type, merged_req, merged_nullable, prior_branch)
            else:
                seen_types[fd.name] = (fd.field_type, fd.required, fd_nullable, branch_name)

    # Branch-exclusive field handling (post-loop pass):
    # - require_all: keep the source-branch required flag (branch always arrives)
    # - other policies: force optional (branch may not arrive)
    if not require_all:
        for field_name in list(seen_types):
            if branches_with_field[field_name] != contributing_branches:
                ftype, _, _, first_branch = seen_types[field_name]
                # Force optional, and nullable (since branch may not arrive)
                seen_types[field_name] = (ftype, False, True, first_branch)

    if all_observed or not seen_types:
        return SchemaConfig(
            mode="observed",
            fields=None,
            guaranteed_fields=guaranteed_fields,
            audit_fields=audit_fields,
        )

    merged_fields = tuple(
        FieldDefinition(name=name, field_type=ftype, required=req, nullable=is_nullable)  # type: ignore[arg-type]
        for name, (ftype, req, is_nullable, _) in seen_types.items()
    )
    return SchemaConfig(
        mode="flexible",
        fields=merged_fields,
        guaranteed_fields=guaranteed_fields,
        audit_fields=audit_fields,
    )
