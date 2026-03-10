---
title: "ACF-S2: Hallucinated Field Access"
---

# ACF-S2: Hallucinated Field Access

!!! info "Provenance"
    Based on Discussion Paper DRAFT v0.3 (March 2026). Status: **v0.3 — DRAFT**

!!! warning "Scope"
    This guidance applies to high-assurance systems where silent data corruption is worse than a crash. For general-purpose software, see [When This Does NOT Apply](../when-this-does-not-apply.md).

| Property | Value |
|----------|-------|
| **STRIDE Category** | Spoofing |
| **Risk Rating** | High |
| **Existing Detection** | Partial |
| **Detection Feasibility** | AST-matchable (if typed) |

## Description

Agent accesses a field name that doesn't exist on the target object, masked by `getattr()` with a default. The code operates on fabricated data while appearing to access a real field.

## Why Agents Produce This

Agents occasionally hallucinate field names — predicting a plausible field name that doesn't exist in the actual schema. Without `getattr`, this produces an immediate `AttributeError`. With `getattr(obj, "hallucinated_field", None)`, the error is silently suppressed and the code operates on `None` (or whatever default is provided).

## Example

=== "Agent-Generated (BAD)"

    ```python
    # Agent hallucinated "risk_score" — actual field is "risk_rating"
    threshold = getattr(assessment, "risk_score", 0)
    if threshold > 5:
        escalate(assessment)
    # risk_score is always 0 (the default), so nothing is ever escalated.
    # The code looks correct. Tests pass (they test the escalation path
    # with explicit values).
    # The bug is invisible until someone notices that escalation never triggers.
    ```

=== "Correct"

    ```python
    # Correct — access the real field directly, crash if it doesn't exist
    threshold = assessment.risk_rating
    if threshold > 5:
        escalate(assessment)
    # If the field name is wrong, AttributeError fires immediately.
    # No silent suppression, no fabricated zero threshold.
    ```

## Why It's Dangerous

The code silently does nothing instead of crashing. In a security context, "nothing happens" can mean "threats are not escalated" or "alerts are not raised" — failures of omission that are harder to detect than failures of commission.

## Detection Approach

Type checkers (mypy, pyright) catch this if the object is fully annotated. If the object is `Any` or untyped, type checkers are silent. The semantic boundary enforcer adds a complementary rule: `getattr` with a default on any object that has a declared type annotation is flagged, because the annotation means the field set is known and access should be direct.

## Related Entries

- [ACF-S1: Competence Spoofing](acf-s1.md) — related spoofing pattern using `.get()` with defaults
- [ACF-S3: Structural Identity Spoofing](acf-s3.md) — related spoofing pattern using `hasattr()` as a gate

---

[Return to Taxonomy Overview](index.md) | [Full Paper Reference](../paper.md#appendix-a-agentic-code-failure-taxonomy)
