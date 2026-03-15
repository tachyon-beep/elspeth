---
title: "ACF-R2: Partial Completion"
---

# ACF-R2: Partial Completion

!!! info "Provenance"
    Based on Discussion Paper DRAFT v0.3 (March 2026). Status: **v0.3 — DRAFT**

!!! warning "Scope"
    This guidance applies to high-assurance systems where silent data corruption is worse than a crash. For general-purpose software, see [When This Does NOT Apply](../when-this-does-not-apply.md).

| Property | Value |
|----------|-------|
| **STRIDE Category** | Repudiation |
| **Risk Rating** | High |
| **Existing Detection** | None |
| **Detection Feasibility** | Human-judgment |

## Description

A sequence of operations that should be atomic (all-or-nothing) is implemented without rollback, so partial failure leaves the system in an inconsistent state.

## Why Agents Produce This

Agents implement operations sequentially and add error handling per-step. They don't naturally recognise that a group of operations should be treated as a transaction unless explicitly prompted. The concept of "these three operations must all succeed or all fail" is a design decision, not a language feature.

## Example

=== "Agent-Generated (BAD)"

    ```python
    # Agent-generated — each step has error handling, but no atomicity
    def reclassify_document(doc_id, new_classification):
        update_classification(doc_id, new_classification)  # Step 1: succeeds
        notify_stakeholders(doc_id, new_classification)     # Step 2: fails (network error)
        record_reclassification(doc_id, old, new)           # Step 3: never runs
        # Document is reclassified, stakeholders don't know,
        # audit trail is incomplete.
        # If step 2 is wrapped in try/except and continues, step 3 records
        # a reclassification that stakeholders were never notified about.
    ```

=== "Correct"

    ```python
    # Correct — treat the sequence as a transaction
    def reclassify_document(doc_id, new_classification):
        old_classification = get_classification(doc_id)
        try:
            update_classification(doc_id, new_classification)
            notify_stakeholders(doc_id, new_classification)
            record_reclassification(doc_id, old_classification, new_classification)
        except Exception:
            rollback_classification(doc_id, old_classification)
            raise  # Propagate — the operation failed atomically
    ```

## Why It's Dangerous

Partial completion creates inconsistent system state that is difficult to detect and correct. The system appears to have completed an operation, but some side effects are missing. In audit-critical contexts, this means the audit trail records an incomplete picture of what actually happened — some operations were performed but not all were recorded, or vice versa.

## Detection Approach

No existing tool detects this — it requires understanding which operations form a logical transaction. A semantic boundary enforcer could flag functions that contain multiple audit-write operations without a transaction context, but this requires project-specific annotation of which operations are audit-critical.

## Related Entries

- [ACF-R1: Audit Trail Destruction](acf-r1.md) — related repudiation pattern where audit writes are swallowed by exception handlers

---

[Return to Taxonomy Overview](index.md) | [Full Paper Reference](../paper.md#appendix-a-agentic-code-failure-taxonomy)
