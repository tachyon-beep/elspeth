# When Agents Write Code

A threat model for AI-assisted software development in government systems.

**Classification:** OFFICIAL | **Status:** DRAFT v0.3 | **Date:** March 2026

## The Risk

AI coding agents produce code that looks professional. It passes tests, follows conventions, and reads like something a careful developer would write. The problem is what it gets wrong: silent data fabrication where a crash would be safer, trust boundaries ignored because the agent doesn't know they exist, and error handling that quietly destroys the evidence an auditor would need. This is not hypothetical — these are patterns observed in practice, in compliance-constrained development, at production quality.

Current Australian cybersecurity guidance — the ISM, the Essential Eight, NIST SSDF — was written for code produced by human developers working within established processes. It does not yet address what happens when an AI agent generates plausible-but-wrong code faster than human reviewers can meaningfully examine it. The review process itself becomes the vulnerability: volume degrades active verification into passive scanning, precisely when the code's failure modes demand closer scrutiny.

This paper identifies thirteen distinct failure patterns in agent-generated code, mapped to the STRIDE threat model. Five of those thirteen have no existing detection mechanism at all — no linter, no SAST tool, no code review checklist catches them. Both of the Critical-rated entries fall into that undetected category. The governance perimeter is also widening: agentic tools now enable non-developers to produce executable logic outside traditional development teams and SDLC controls, bypassing existing safeguards entirely.

!!! danger "Three Priority Actions"
    1. **Issue guidance on treating agent output as a trust boundary.** Agent-generated code should be treated as external input requiring validation, not as a developer's own work product. This provides the conceptual foundation for all other controls. [Recommendation 2](paper.md#101-for-security-policy-bodies-asd-acsc)

    2. **Extend ISM controls for agent-generated code.** The June 2025 ISM overhaul provides strong foundations that need only targeted extensions for agentic code — controls for correlated failures, review effectiveness under volume, and semantic boundary verification. [Recommendation 3](paper.md#101-for-security-policy-bodies-asd-acsc)

    3. **Document institutional security knowledge in machine-readable form.** Agents lack institutional context — they don't know your trust boundaries, your data classifications, or which fields are security-critical. Making this knowledge explicit and machine-readable is the most direct defence, and requires no new tooling. [Recommendation 11](paper.md#103-for-organisations-using-agentic-coding)

## Where to Start

!!! tip "Executive / SES"
    Need the two-page version? Start with the [Executive Brief](executive-brief.md) — risk framing, key findings, and priority actions without technical detail.

!!! tip "CISO / IRAP Assessor"
    For assessment and accreditation context, see the [Reading Guides](reading-guides.md) — structured paths through the paper for security practitioners.

!!! tip "Developer / Architect"
    The [ACF Taxonomy](taxonomy/index.md) catalogues all thirteen failure modes with STRIDE mappings, risk ratings, code examples, and detection approaches.

!!! tip "Tool Builder"
    Start with the [ACF Taxonomy](taxonomy/index.md) — the detection capability summary identifies which failure modes have no existing tooling and where new detection is needed most.

!!! example "I Use AI to Build Things at Work"
    Not a developer by trade but using AI tools to write code? The [Citizen Programmer](citizen-programmer/index.md) guide is written for you — no jargon, practical guidance on what to watch for.

## Full Paper

The complete discussion paper, including the threat model, gap analysis, case study, and all sixteen recommendations, is available as the [full paper reference](paper.md).
