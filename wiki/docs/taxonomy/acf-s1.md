---
title: "ACF-S1: Competence Spoofing"
---

# ACF-S1: Competence Spoofing

!!! info "Provenance"
    Based on Discussion Paper DRAFT v0.3 (March 2026). Status: **v0.3 — DRAFT**

!!! warning "Scope"
    This guidance applies to high-assurance systems where silent data corruption is worse than a crash. For general-purpose software, see [When This Does NOT Apply](../when-this-does-not-apply.md).

| Property | Value |
|----------|-------|
| **STRIDE Category** | Spoofing |
| **Risk Rating** | High |
| **Existing Detection** | None |
| **Detection Feasibility** | Annotation-required |

## Description

Default values fabricate data where the absence of data should be surfaced as a failure, error, or explicit "unknown." The code presents a confident result that is actually based on fabricated input.

## Why Agents Produce This

The `.get(key, default)` pattern appears in millions of Python files. In most contexts, providing a default for missing keys is genuinely good practice — a web application displaying "Unknown" for a missing user name is fine. Agents learn this as a universal pattern and apply it in contexts where the default fabricates safety-critical data.

## Example

=== "Agent-Generated (BAD)"

    ```python
    # Agent-generated — looks defensive and robust
    def assess_risk_level(record):
        classification = record.get("security_classification", "OFFICIAL")
        clearance = record.get("required_clearance", "baseline")
        return classification, clearance
    ```

=== "Correct"

    ```python
    # Correct for high-assurance context — absence is a failure
    def assess_risk_level(record):
        if "security_classification" not in record:
            raise MissingSecurityClassification(
                f"Record {record['id']}: security_classification absent — "
                f"upstream data integrity failure, cannot assess risk"
            )
        if "required_clearance" not in record:
            raise MissingSecurityClearance(
                f"Record {record['id']}: required_clearance absent — "
                f"cannot determine access level, refusing to default"
            )
        return record["security_classification"], record["required_clearance"]
    ```

## Why It's Dangerous

The first version silently downgrades security classifications when data is missing. A PROTECTED document with a corrupted or missing `security_classification` field is treated as OFFICIAL. Downstream access control decisions are based on the fabricated classification.

## Detection Approach

Flag `.get()` and `getattr()` with defaults on objects whose type is annotated with a trust tier of Tier 1 (internal/audit) or Tier 2 (validated pipeline data). Requires trust tier annotations (not available in existing tools).

## Related Entries

- [ACF-S2: Hallucinated Field Access](acf-s2.md) — related spoofing pattern using `getattr()` with defaults
- [ACF-S3: Structural Identity Spoofing](acf-s3.md) — fabricates identity rather than data
- [ACF-T2: Silent Coercion](acf-t2.md) — related pattern involving type coercion with defaults
- [How Threats Compound](../compounding-effect.md) — competence spoofing contributes to the compounding scenario

---

[Return to Taxonomy Overview](index.md) | [Full Paper Reference](../paper.md#appendix-a-agentic-code-failure-taxonomy)
