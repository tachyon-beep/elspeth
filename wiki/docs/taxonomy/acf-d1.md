---
title: "ACF-D1: Finding Flood"
---

# ACF-D1: Finding Flood

!!! info "Provenance"
    Based on Discussion Paper DRAFT v0.3 (March 2026). Status: **v0.3 — DRAFT**

!!! warning "Scope"
    This guidance applies to high-assurance systems where silent data corruption is worse than a crash. For general-purpose software, see [When This Does NOT Apply](../when-this-does-not-apply.md).

| Property | Value |
|----------|-------|
| **STRIDE Category** | Denial of Service |
| **Risk Rating** | High |
| **Existing Detection** | N/A |
| **Detection Feasibility** | Process threat — not a code pattern |

## Description

The volume of static analysis findings on agent-generated code overwhelms reviewers, causing them to rubber-stamp findings without evaluation. The denial of service targets the *review process*, not the system itself.

## Why This Happens

Agents produce code at volume, and if that code triggers many findings, the review queue grows faster than the review capacity. Reviewers under volume pressure shift from evaluating each finding to batch-dismissing them. This is a process failure, not a code pattern — no static analysis tool can detect it because the problem is in the human review workflow, not in the code.

## Process Failure Mode

The finding flood creates a vicious cycle:

1. Agent generates code that triggers many static analysis findings
2. Review queue grows faster than reviewers can process it
3. Reviewers shift from careful evaluation to batch dismissal
4. Suppression rates rise, but the metric is treated as "findings resolved" rather than "findings ignored"
5. Real security issues are dismissed alongside false positives
6. The review process provides a false sense of security — it appears functional but has lost its filtering capability

This is distinct from a code pattern because the individual findings may each be legitimate. The threat is the aggregate volume, not any single finding.

## Mitigation

- Finding caps per rule per file to prevent any single rule from flooding the queue
- Prioritised finding presentation (critical findings first, low-severity findings batched)
- Measured suppression rates as a health metric — rising suppression rates signal review degradation
- Periodic audit of suppressed findings to verify they were genuinely false positives

## Detection Approach

Not a code pattern — requires process controls and metrics. Monitor suppression rates, review throughput, and time-to-review as leading indicators of review capacity exhaustion.

## Related Entries

- [ACF-D2: Review Capacity Exhaustion](acf-d2.md) — the broader capacity problem that finding floods contribute to

---

[Return to Taxonomy Overview](index.md) | [Full Paper Reference](../paper.md#appendix-a-agentic-code-failure-taxonomy)
