# ACF Taxonomy

!!! info "Provenance"
    Based on Discussion Paper DRAFT v0.3 (March 2026). Status: **v0.3 — DRAFT**

The Agentic Code Failure (ACF) taxonomy is a structured vocabulary for failure modes introduced by AI coding agents. It catalogues thirteen patterns of plausible-but-wrong code, mapped to STRIDE threat categories, that evade existing review and detection processes. This taxonomy is provisional — developed from a single project's experience and intended as a starting point for community refinement, not a definitive standard.

## Summary Table

| ID | Name | STRIDE Category | Risk Rating | Existing Detection |
|----|------|-----------------|-------------|-------------------|
| [ACF-S1](acf-s1.md) | Competence Spoofing | Spoofing | High | None |
| [ACF-S2](acf-s2.md) | Hallucinated Field Access | Spoofing | High | Partial |
| [ACF-S3](acf-s3.md) | Structural Identity Spoofing | Spoofing | High | Partial |
| [ACF-T1](acf-t1.md) | Trust Tier Conflation | Tampering | Critical | None |
| [ACF-T2](acf-t2.md) | Silent Coercion | Tampering | Medium | None |
| [ACF-R1](acf-r1.md) | Audit Trail Destruction | Repudiation | High | Partial |
| [ACF-R2](acf-r2.md) | Partial Completion | Repudiation | High | None |
| [ACF-I1](acf-i1.md) | Verbose Error Response | Info Disclosure | Medium | Partial |
| [ACF-I2](acf-i2.md) | Stack Trace Exposure | Info Disclosure | Low | Good |
| [ACF-D1](acf-d1.md) | Finding Flood | Denial of Service | High | N/A |
| [ACF-D2](acf-d2.md) | Review Capacity Exhaustion | Denial of Service | High | N/A |
| [ACF-E1](acf-e1.md) | Implicit Privilege Grant | Elevation | Critical | None |
| [ACF-E2](acf-e2.md) | Unvalidated Delegation | Elevation | High | Partial |

## Detection Capability Summary

| Detection Level | Count | Entries |
|----------------|-------|---------|
| **None** — no existing tool detects it | 5 | ACF-S1, ACF-T1, ACF-T2, ACF-R2, ACF-E1 |
| **Partial** — some tools catch some cases | 5 | ACF-S2, ACF-S3, ACF-R1, ACF-I1, ACF-E2 |
| **Good** — existing tools generally catch it | 1 | ACF-I2 |
| **N/A** — process threat, not code pattern | 2 | ACF-D1, ACF-D2 |

!!! danger "Critical Gap"
    Both Critical-rated entries — ACF-T1 (Trust Tier Conflation) and ACF-E1 (Implicit Privilege Grant) — have **zero existing detection**. The most dangerous failure modes are the ones we currently cannot detect.

Five of thirteen failure modes are completely undetectable by existing tools, and five more are only partially detected. The five undetectable modes include both Critical-rated entries, meaning the highest-risk failures are precisely the ones that current tooling misses entirely.

## Related

- [When This Does NOT Apply](../when-this-does-not-apply.md) — scope boundaries and exclusions for this taxonomy
- [Full Paper Reference](../paper.md#appendix-a-agentic-code-failure-taxonomy)
