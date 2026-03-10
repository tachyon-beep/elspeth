---
title: "ACF-T2: Silent Coercion"
---

# ACF-T2: Silent Coercion

!!! info "Provenance"
    Based on Discussion Paper DRAFT v0.3 (March 2026). Status: **v0.3 — DRAFT**

!!! warning "Scope"
    This guidance applies to high-assurance systems where silent data corruption is worse than a crash. For general-purpose software, see [When This Does NOT Apply](../when-this-does-not-apply.md).

| Property | Value |
|----------|-------|
| **STRIDE Category** | Tampering |
| **Risk Rating** | Medium |
| **Existing Detection** | None |
| **Detection Feasibility** | Annotation-required |

## Description

Type coercion across trust boundaries hides data quality issues. Values are silently converted to a compatible type rather than being flagged as invalid.

## Why Agents Produce This

Python's `or` operator and conditional expressions make coercion easy and idiomatic. `value = input_value or "default"` is a common pattern. Agents apply it broadly without distinguishing between contexts where coercion is appropriate (Tier 3 to Tier 2 at a validated boundary) and contexts where it's dangerous (Tier 1 internal data that should never need coercion).

## Example

=== "Agent-Generated (BAD)"

    ```python
    # Silent coercion hides data quality problem
    amount = float(row.get("transaction_amount", 0))
    # Missing transaction amount is silently zero — not "unknown" or "error."
    # A zero-value transaction passes every downstream check.
    # An audit query for "transactions over $1000" won't find it,
    # but neither will "transactions with missing amounts."
    ```

=== "Correct"

    ```python
    # Better — make the absence explicit
    if "transaction_amount" not in row:
        return TransformResult.error(
            {"reason": "missing_amount", "row_id": row_id}
        )
    amount = float(row["transaction_amount"])
    ```

## Why It's Dangerous

Silent coercion converts "unknown" into a concrete value that passes all downstream checks. The distinction between "this transaction was for $0" and "we don't know the transaction amount" is lost permanently. Audit queries cannot distinguish real data from fabricated defaults, compromising the integrity of any analysis or compliance report built on the data.

## Detection Approach

Flag coercion patterns (`.get()` with non-None defaults, `or` chains with fallback values, ternary expressions with defaults) on fields from Tier 1 or Tier 2 data. The distinction from ACF-S1 is that this involves type conversion, not just default substitution. Requires trust tier annotations to distinguish contexts where coercion is appropriate from contexts where it is dangerous.

## Related Entries

- [ACF-T1: Trust Tier Conflation](acf-t1.md) — related tampering pattern involving unvalidated boundary crossing
- [ACF-S1: Competence Spoofing](acf-s1.md) — related pattern using defaults without type conversion

---

[Return to Taxonomy Overview](index.md) | [Full Paper Reference](../paper.md#appendix-a-agentic-code-failure-taxonomy)
