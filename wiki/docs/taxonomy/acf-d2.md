---
title: "ACF-D2: Review Capacity Exhaustion"
---

# ACF-D2: Review Capacity Exhaustion

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

Agent code generation velocity exceeds the organisation's capacity for security-focused review, degrading review from active verification to passive scanning.

## Why This Happens

Agents can generate plausible, convention-conforming code faster than review processes were designed to absorb. Review capacity doesn't scale at the same rate as generation capacity. The review process becomes a bottleneck, and the organisational response is often to lower the review bar rather than reduce the generation rate.

## Process Failure Mode

Review capacity exhaustion manifests as a gradual degradation:

1. Code generation velocity increases as agents are adopted more broadly
2. Review queue depth grows — reviewers fall behind
3. Organisational pressure to "keep up" leads to shorter review times per change
4. Review shifts from active verification ("is this correct and secure?") to passive scanning ("does this look roughly right?")
5. Subtle security issues that require careful analysis pass through undetected
6. The organisation believes it has code review coverage, but the review has lost its security assurance value

Unlike ACF-D1 (finding flood), which overwhelms the static analysis review process, ACF-D2 overwhelms the human code review process itself. Both are process threats, but ACF-D2 is broader — it affects all review, not just finding triage.

## Mitigation

- Automated pre-screening to reduce the human review burden — automated checks handle the mechanical verification, freeing reviewers for semantic analysis
- Volume-aware capacity planning — track the ratio of generated code to review capacity and flag when it exceeds sustainable levels
- Measured review effectiveness metrics — track not just "reviews completed" but "issues found per review" as a quality indicator
- Review scope boundaries — define which generated code requires full security review vs. which can be covered by automated checks alone

## Detection Approach

Not a code pattern — requires process controls and organisational metrics. Monitor code generation velocity, review queue depth, average review time, and issues-found-per-review as indicators of review quality degradation.

## Related Entries

- [ACF-D1: Finding Flood](acf-d1.md) — the specific case where static analysis findings overwhelm the review queue

---

[Return to Taxonomy Overview](index.md) | [Full Paper Reference](../paper.md#appendix-a-agentic-code-failure-taxonomy)
