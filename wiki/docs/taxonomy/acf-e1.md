---
title: "ACF-E1: Implicit Privilege Grant"
---

# ACF-E1: Implicit Privilege Grant

!!! info "Provenance"
    Based on Discussion Paper DRAFT v0.3 (March 2026). Status: **v0.3 — DRAFT**

!!! warning "Scope"
    This guidance applies to high-assurance systems where silent data corruption is worse than a crash. For general-purpose software, see [When This Does NOT Apply](../when-this-does-not-apply.md).

| Property | Value |
|----------|-------|
| **STRIDE Category** | Elevation of Privilege |
| **Risk Rating** | Critical |
| **Existing Detection** | None |
| **Detection Feasibility** | Taint-required |

## Description

External system assertions are accepted without independent verification, granting privileges based on unvalidated claims.

## Why Agents Produce This

Agents implement integration patterns by calling external APIs and acting on the response. The concept that the external system's response must be independently verified — that the response itself is untrusted — is not visible in the code structure. The code looks like a normal API call and response handling.

## Example

=== "Agent-Generated (BAD)"

    ```python
    # Agent-generated — looks like normal API integration
    partner_verification = partner_api.verify_identity(applicant_id)
    if partner_verification.get("verified", False):
        grant_system_access(applicant_id, level="standard")
    # Partner says "verified" → access granted.
    # No independent check. No recording of the basis for the decision.
    # If the partner system is compromised, every applicant is "verified."
    ```

=== "Correct"

    ```python
    # Correct — verify independently, record the basis
    partner_verification = partner_api.verify_identity(applicant_id)

    # Validate the external claim at the boundary
    try:
        validated = PartnerVerificationSchema.validate(
            partner_verification
        )
    except ValidationError as e:
        record_verification_failure(applicant_id, reason=str(e))
        raise

    # Independent verification — don't trust the partner's assertion alone
    internal_check = verify_against_internal_records(
        applicant_id, validated.claimed_identity
    )
    if not internal_check.confirmed:
        record_verification_failure(
            applicant_id, reason="internal_check_failed"
        )
        raise VerificationError("Independent verification failed")

    # Record the basis for the decision before granting access
    record_verification(
        applicant_id,
        partner_result=validated,
        internal_result=internal_check,
    )
    grant_system_access(applicant_id, level="standard")
    ```

## Why It's Dangerous

This is a Critical-rated failure mode because it allows an external system to control internal privilege decisions. If the partner API is compromised, misconfigured, or simply buggy, every identity verification succeeds. The system has outsourced its access control decision to an external party without any independent verification. Combined with ACF-T1 (trust tier conflation), this creates a path from external data to internal privilege — the most dangerous compound failure in the taxonomy.

## Detection Approach

Taint analysis — the return value of an `@external_boundary` function is used as a predicate in an access control decision without passing through validation. Requires both boundary annotation and understanding of which operations are access-control-relevant.

## Related Entries

- [ACF-T1: Trust Tier Conflation](acf-t1.md) — the underlying trust boundary violation that enables implicit privilege grants
- [ACF-S3: Structural Identity Spoofing](acf-s3.md) — complementary elevation mechanism where the gate itself is structurally unsound
- [ACF-E2: Unvalidated Delegation](acf-e2.md) — related elevation pattern where user parameters reach privileged operations
- [How Threats Compound](../compounding-effect.md) — implicit privilege grant is the elevation step in the 5-step compounding scenario

---

[Return to Taxonomy Overview](index.md) | [Full Paper Reference](../paper.md#appendix-a-agentic-code-failure-taxonomy)
