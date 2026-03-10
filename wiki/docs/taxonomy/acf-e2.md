---
title: "ACF-E2: Unvalidated Delegation"
---

# ACF-E2: Unvalidated Delegation

!!! info "Provenance"
    Based on Discussion Paper DRAFT v0.3 (March 2026). Status: **v0.3 — DRAFT**

!!! warning "Scope"
    This guidance applies to high-assurance systems where silent data corruption is worse than a crash. For general-purpose software, see [When This Does NOT Apply](../when-this-does-not-apply.md).

| Property | Value |
|----------|-------|
| **STRIDE Category** | Elevation of Privilege |
| **Risk Rating** | Medium |
| **Existing Detection** | None |
| **Detection Feasibility** | Taint-required (partial) |

## Description

User-supplied parameters are used directly in privileged operations (database queries, file access, system commands) without validation or restriction.

## Why Agents Produce This

The pattern `db.query(Model).filter_by(**user_params)` is concise and idiomatic. Agents produce it because it's the shortest path from input to query. The concept that user parameters must be restricted to an allowlist of permitted fields is a security requirement, not a language requirement.

## Example

=== "Agent-Generated (BAD)"

    ```python
    # Agent-generated — concise, idiomatic, insecure
    def search_records(user_query: dict):
        return db.query(Record).filter_by(**user_query)
    # User can filter on internal fields: is_deleted, internal_score,
    # admin_notes — fields that should not be queryable.
    ```

=== "Correct"

    ```python
    # Correct — restrict to allowed fields
    ALLOWED_SEARCH_FIELDS = frozenset({"name", "status", "created_date"})

    def search_records(user_query: dict):
        filtered = {
            k: v for k, v in user_query.items()
            if k in ALLOWED_SEARCH_FIELDS
        }
        return db.query(Record).filter_by(**filtered)
    ```

## Why It's Dangerous

Unvalidated delegation allows users to access data or operations they should not have access to. By passing arbitrary parameters to a privileged operation, a user can filter on internal fields (exposing hidden data), modify fields that should be read-only, or access records that should be restricted. The delegation effectively grants the user the same privilege level as the database query itself.

## Detection Approach

SQL injection scanners catch some cases (especially string interpolation into SQL). Parameter delegation via `**kwargs` unpacking into ORM queries is less consistently detected. Semantic detection requires understanding which operations are privileged and which parameters are user-controlled. Taint analysis can trace user input to privileged operations, but distinguishing validated from unvalidated parameters requires annotation of validation boundaries.

## Related Entries

- [ACF-E1: Implicit Privilege Grant](acf-e1.md) — related elevation pattern where external assertions control privilege decisions
- [ACF-T1: Trust Tier Conflation](acf-t1.md) — the underlying trust boundary violation that enables unvalidated delegation

---

[Return to Taxonomy Overview](index.md) | [Full Paper Reference](../paper.md#appendix-a-agentic-code-failure-taxonomy)
