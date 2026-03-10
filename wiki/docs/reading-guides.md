---
title: "Reading Guides"
---

# Reading Guides

!!! info "Provenance"
    Based on Discussion Paper DRAFT v0.3 (March 2026). Status: **v0.3 — DRAFT**

Five curated paths through the paper for different audiences. Each path is an ordered sequence of links with one-sentence context — not separate content.

---

## SES / Executive

A focused path for senior executives who need the strategic picture without implementation detail.

1. [A Concrete Example](paper.md#23-a-concrete-example) — A walkthrough of how agent-generated code can silently undermine audit integrity, illustrating why this threat is different from traditional software defects.
2. [Executive Brief](executive-brief.md) — A standalone two-page summary covering the core threat, why current controls miss it, and what actions are needed.
3. [Agent Autonomy Self-Assessment](paper.md#appendix-c-agent-autonomy-self-assessment) — A diagnostic for identifying where your organisation sits on the autonomy spectrum and whether controls are proportionate.
4. [Recommendations for Security Policy Bodies](paper.md#101-for-security-policy-bodies-asd-acsc) — Five candidate policy actions including treating agent output as a trust boundary and establishing detection baselines.

---

## CISO / IRAP Assessor

A deeper path for security professionals responsible for risk assessment and compliance evaluation.

1. [The Insidious Threat Model](paper.md#22-the-insidious-threat-model) — Why the real danger is not malicious code injection but code that is syntactically correct, test-passing, and contextually wrong.
2. [Current Guidance Gap Analysis](paper.md#6-current-guidance-gap-analysis) — A systematic review of ISM, NIST SSDF, Essential Eight, and OWASP against agentic code failure modes.
3. [Detection Coverage Is Worst Where Risk Is Highest](paper.md#66-detection-coverage-is-worst-where-risk-is-highest) — The inverse relationship between detection capability and risk severity across failure categories.
4. [The Review Process as Attack Surface](paper.md#4-the-review-process-as-attack-surface) — How code review itself becomes a vulnerability when generation velocity overwhelms review capacity.
5. [Recommendations for IRAP Assessors](paper.md#102-for-irap-assessors) — Specific guidance on including agentic development practices in assessment scope.
6. [ACF Taxonomy](taxonomy/index.md) — The complete failure taxonomy with STRIDE mappings, detection levels, and cross-references.
7. [Open Questions for the Community](paper.md#9-open-questions-for-the-community) — Unresolved research and policy questions including trust classification, accreditation burden, and correlated failure.

---

## Developer / Architect

A technical path for practitioners building or securing systems that use agentic coding tools.

1. [The Insidious Threat Model](paper.md#22-the-insidious-threat-model) — The core argument: agents produce code that is plausible, conventional, and dangerous in high-assurance contexts.
2. [A Concrete Example](paper.md#23-a-concrete-example) — A side-by-side comparison of offensive, acceptable, and agent-authored code handling a security classification lookup.
3. [Agent Output as a Trust Boundary](paper.md#5-agent-output-as-a-trust-boundary) — Why agent-generated code should be treated as Tier 3 (external, zero-trust) data regardless of how correct it looks.
4. [ACF Taxonomy](taxonomy/index.md) — Detailed failure patterns with code examples, detection approaches, and STRIDE mappings.
5. [Technical Controls (What's Buildable)](paper.md#72-technical-controls-whats-buildable) — What automated enforcement looks like in practice, including the argument that scope is the wrong metric for assurance.
6. [Case Study: Agentic Development Under Compliance Constraints](paper.md#8-case-study-agentic-development-under-compliance-constraints) — A de-identified account of running agentic development inside a compliance-constrained environment.
7. [Recommendations for Organisations Using Agentic Coding](paper.md#103-for-organisations-using-agentic-coding) — Practical steps including treating agent code as external input and implementing semantic enforcement.

---

## Tool Builder

A path for teams building static analysis, linting, or enforcement tooling for agentic code output.

1. [ACF Taxonomy](taxonomy/index.md) — The failure patterns your tooling needs to detect, with detection approaches and difficulty ratings per entry.
2. [Detection Capability Summary](paper.md#detection-capability-summary) — A table mapping each failure mode to its current detection level, showing where tooling gaps are widest.
3. [Technical Feasibility of Automated Enforcement](paper.md#appendix-b-technical-feasibility-of-automated-enforcement) — Design history, core properties, and verification arguments for a working enforcement tool.
4. [Technical Controls (What's Buildable)](paper.md#72-technical-controls-whats-buildable) — The broader landscape of technical controls and why small, focused tools can provide meaningful assurance.
5. [Where the Current Process Fails](paper.md#84-where-the-current-process-fails) — Real-world observations of agent-generated code passing human review, motivating automated detection.

---

## Citizen Programmer

A minimal path for non-developers who use agentic tools to build automations, plugins, or internal tools.

1. [Coding Is No Longer Confined to Developers](paper.md#128-coding-is-no-longer-confined-to-developers) — Why this paper applies to you: if you generate executable logic with agent assistance, you are in scope.
2. [Citizen Programmer Guide](citizen-programmer/index.md) — A standalone guide covering what to watch for, what questions to ask, and when to escalate.
3. [Agent Autonomy Self-Assessment](paper.md#appendix-c-agent-autonomy-self-assessment) — A diagnostic to check whether your current agent usage has appropriate controls.
4. [Recommendations for Security Policy Bodies, Rec 5](paper.md#101-for-security-policy-bodies-asd-acsc) — The specific recommendation that governance frameworks should extend to citizen programmers producing executable logic.
