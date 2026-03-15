---
title: "Executive Brief"
---

# Executive Brief

!!! info "Provenance"
    Based on Discussion Paper DRAFT v0.3 (March 2026). Status: **v0.3 — DRAFT**

## The Risk

AI coding agents produce code that is syntactically correct, passes automated tests, follows project conventions, and is difficult to distinguish from human-authored code on casual inspection. The novel risk is not that agents write malicious code — it is that they produce plausible-but-wrong code at volume. These are not obvious errors. They are subtle, context-dependent failures that look like careful, professional work. For example: a login function that looks up the current user from the session and, when the session data is incomplete, defaults to administrator access — a single line that is syntactically valid, passes tests, and looks like responsible error handling, but silently grants the highest level of access whenever something goes wrong. At scale, agents produce this class of error — silent data fabrication, security boundary violations, audit trail destruction — systematically, not occasionally. The failures are invisible to existing automated checks and difficult to catch when reviewers are absorbing agent-generated code at volume.

## The Gap

Current cybersecurity guidance — including the Australian Information Security Manual (ISM), the NIST Secure Software Development Framework, and the Essential Eight — addresses software supply chain risk for human-authored code. It does not yet provide controls for the distinct risk profile of agent-generated code. Agent code fails differently from human code: failures are correlated across the codebase because agents draw on the same training data, the consistent surface quality defeats reviewer calibration, and the errors are semantic rather than syntactic — invisible to existing static analysis tools.

Of the thirteen failure modes identified in the [full analysis](paper.md#66-detection-coverage-is-worst-where-risk-is-highest), five have no detection by any existing tool, and five more are only partially detected. Both of the Critical-rated failure modes — trust boundary violations and implicit privilege grants — fall in the category with zero detection capability. The highest-risk failures are precisely the ones current tooling misses entirely.

## The Expanding Perimeter

The risk is compounded by a shift in who produces code. Agentic tools are enabling business analysts, data engineers, operations staff, and other domain specialists to produce executable logic — plugins, automations, integrations, dashboards — without regarding themselves as software developers. These individuals typically hold more data access permissions than professional developers, precisely because they are trusted to work directly with the systems they understand. The governance models examined in the paper — the ISM's software development controls, NIST practice groups, IRAP assessment scoping — all assume that consequential code enters systems through recognised development channels: repositories, pull requests, code review gates, CI/CD pipelines. When executable logic is produced outside those channels, it bypasses the controls entirely — not through evasion, but because the governance perimeter was drawn around "software development" and this new production does not cross that line in any way the organisation recognises.

The problem is therefore two-fold: engineering teams can generate reviewable code faster than assurance processes can absorb it (a volume problem inside the development lifecycle), and organisations increasingly contain more software producers than their assurance processes recognise (a perimeter problem around the development lifecycle). Together, they are materially worse than either alone.

## Three Priority Actions

The full paper contains sixteen recommendations across three audiences. Three have the highest leverage and are achievable in the near term:

**1. Issue guidance on treating agent output as a trust boundary** ([Recommendation 2](paper.md#101-for-security-policy-bodies-asd-acsc)). Clarify how agent-generated code should be classified in the trust model and what validation is required before integration into assessed systems — whether it requires different review criteria, whether provenance must be tracked, and what constitutes sufficient validation. This provides the conceptual foundation that all other controls build on. *Requires policy development; no new tooling needed.*

**2. Extend ISM controls for agent-generated code** ([Recommendation 3](paper.md#101-for-security-policy-bodies-asd-acsc)). The June 2025 ISM overhaul added strong foundations for code review, comprehensive testing, and artefact integrity, but these controls assume human-paced development. Targeted extensions are needed to address review capacity under agent-generated volume, semantic boundary analysis beyond known-vulnerability scanning, and supply chain treatment of agent-generated first-party code. *Extends existing controls; leverages the June 2025 ISM foundations.*

**3. Document institutional security knowledge in machine-readable form** ([Recommendation 11](paper.md#103-for-organisations-using-agentic-coding)). The gap between what a programming language permits and what a specific system requires is institutional knowledge that currently lives in documentation, team culture, and individual expertise. Agents do not share that knowledge. Encoding it in machine-checkable rules — whether through project-specific linter rules, a purpose-built enforcement tool, or structured review checklists — is the most direct defence against agents that lack institutional context. *Requires no new tooling — encodes existing knowledge in checkable form.*

## Where to Read More

- [Full discussion paper](paper.md) — the complete threat model, taxonomy, and recommendations
- [Gap analysis](paper.md#6-current-guidance-gap-analysis) — detailed assessment of ISM, NIST SSDF, Essential Eight, and OWASP coverage
- [Case study](paper.md#8-case-study-agentic-development-under-compliance-constraints) — real-world experience with automated semantic boundary enforcement
- [All sixteen recommendations](paper.md#10-recommendations) — grouped by audience: policy bodies, IRAP assessors, and organisations
