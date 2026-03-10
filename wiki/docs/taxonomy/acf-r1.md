---
title: "ACF-R1: Audit Trail Destruction"
---

# ACF-R1: Audit Trail Destruction

!!! info "Provenance"
    Based on Discussion Paper DRAFT v0.3 (March 2026). Status: **v0.3 — DRAFT**

!!! warning "Scope"
    This guidance applies to high-assurance systems where silent data corruption is worse than a crash. For general-purpose software, see [When This Does NOT Apply](../when-this-does-not-apply.md).

| Property | Value |
|----------|-------|
| **STRIDE Category** | Repudiation |
| **Risk Rating** | High |
| **Existing Detection** | None |
| **Detection Feasibility** | Annotation-required |

## Description

Broad exception handlers catch errors from audit-critical operations and log-and-continue rather than propagating the failure to the audit system.

## Why Agents Produce This

"Catch exceptions and log them" is a pervasive pattern in training data. In most applications, it's reasonable — a web server should log errors and keep serving. Agents apply this pattern to audit-critical operations without recognising that some failures must propagate rather than be absorbed.

## Example

=== "Agent-Generated (BAD)"

    ```python
    # Agent-generated — looks like responsible error handling
    try:
        record_decision(case_id, decision, rationale, evidence)
    except Exception as e:
        logger.error(f"Failed to record decision for {case_id}: {e}")
        # Decision was made. Decision was not recorded.
        # The audit trail now has a gap that cannot be reconstructed.
        # The log message may be rotated away. The decision stands, unrecorded.
    ```

=== "Correct"

    ```python
    # Correct — audit failures must propagate
    record_decision(case_id, decision, rationale, evidence)
    # If this fails, the exception propagates up.
    # The caller must handle it — either retry or abort the operation.
    # The decision is NOT made unless it is recorded.
    ```

## Why It's Dangerous

In regulatory contexts, the audit trail is the legal record. A gap in the audit trail is not just a logging failure — it's a compliance failure that may have legal consequences. "We made a decision but can't prove what it was based on" is an unacceptable answer in a formal inquiry.

## Detection Approach

Existing linters flag bare `except:` (no exception type) but not `except Exception:` (which is considered acceptable practice). Semantic detection requires understanding which operations are audit-critical — this is project-specific knowledge encoded in the trust topology (e.g., functions annotated as audit-write operations should not be inside broad exception handlers that continue on failure).

## Related Entries

- [ACF-R2: Partial Completion](acf-r2.md) — related repudiation pattern where partial failure leaves the system in an inconsistent state
- [How Threats Compound](../compounding-effect.md) — audit trail destruction enables repudiation in the compounding scenario

---

[Return to Taxonomy Overview](index.md) | [Full Paper Reference](../paper.md#appendix-a-agentic-code-failure-taxonomy)
