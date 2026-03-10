---
title: "How Threats Compound"
---

# How Threats Compound

!!! info "Provenance"
    Based on Discussion Paper DRAFT v0.3 (March 2026). Status: **v0.3 — DRAFT**

Individual failure patterns are concerning but containable. The compound effect is what makes agent-generated code a systemic risk. Each individual pattern looks like ordinary defensive coding. The compound effect is a system that silently produces wrong results, can't explain why, and passed every review gate.

## The 5-step compounding scenario

These six threat categories do not operate independently. In practice, they compound. Consider the following scenario, where each step enables the next:

1. **An agent generates code with trust tier conflation** — external API data is used directly without boundary validation. The agent treats untrusted external input with the same confidence as internally validated data.
    <br/>→ [ACF-T1: Trust Tier Conflation](taxonomy/acf-t1.md) · [ACF-E1: Trust Boundary Elevation](taxonomy/acf-e1.md)

2. **The missing validation means errors in that data are caught by a broad `except` block** — instead of being detected at the trust boundary, malformed external data propagates until it causes an exception somewhere downstream. A broad exception handler catches it and discards the diagnostic context that would have revealed the root cause.
    <br/>→ [ACF-R1: Audit Trail Destruction](taxonomy/acf-r1.md)

3. **The `except` block returns a default value** — rather than propagating the failure, the handler silently substitutes a plausible-looking default. The system continues operating as if nothing went wrong. From the outside, the code appears to be handling errors gracefully.
    <br/>→ [ACF-S1: Competence Spoofing](taxonomy/acf-s1.md)

4. **The default value is treated as authoritative data downstream** — the fabricated default is now indistinguishable from real data. Downstream components consume it, make decisions based on it, and record it in the audit trail as if it were a genuine value derived from the source system.
    <br/>→ [ACF-T1: Trust Tier Conflation](taxonomy/acf-t1.md) · [ACF-T2: Silent Trust Tier Coercion](taxonomy/acf-t2.md)

5. **The volume of agent-generated code means the reviewer doesn't catch any of this** — each individual line of code looks reasonable in isolation. The `.get()` with a default looks defensive. The `except` block looks robust. The downstream usage looks normal. At the velocity of agent-generated code, no reviewer examines the five-step chain end to end.
    <br/>→ [ACF-D1: Finding Flood](taxonomy/acf-d1.md) · [ACF-D2: Review Capacity Exhaustion](taxonomy/acf-d2.md)

## Why the interaction matters

The compound effect is dangerous precisely because it is invisible to the controls organisations rely on. Each individual decision — use `.get()` for safety, catch exceptions for robustness, return defaults for graceful degradation — is reasonable in isolation. Code review examines individual decisions, not multi-step causal chains across functions and modules.

The result is a system where:

- **Bad data enters** because there is no boundary validation (step 1)
- **The evidence is destroyed** because broad exception handling discards the context (step 2)
- **The failure is hidden** because a default value masks it (step 3)
- **The fabrication is trusted** because nothing distinguishes it from real data (step 4)
- **Nobody notices** because the review process cannot keep pace (step 5)

No single code review finding would flag this. The `.get()` in step 3 is a style choice. The `except` block in step 2 is error handling. The missing validation in step 1 is an omission, not a defect. It is only when the five steps are considered as a chain that the systemic failure becomes visible — and individual code reviews are not designed to see chains.

[Full Paper Reference](paper.md#33-the-compounding-effect)
