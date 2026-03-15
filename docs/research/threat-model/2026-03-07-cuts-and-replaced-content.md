# Cuts and Replaced Content

Content removed or replaced during v0.1 → v0.2 editing of the discussion paper.
Preserved here for reference and possible reuse.

---

## Original Abstract (replaced in v0.2)

AI coding agents are entering government software development workflows. These agents generate syntactically correct, test-passing code at unprecedented velocity. Current cybersecurity guidance — including the Australian Information Security Manual (ISM), NIST SP 800-218 (SSDF), and the Essential Eight — addresses software supply chain risk for human-authored code. It does not yet provide a vocabulary for the distinct failure modes of AI-generated code.

This paper presents a threat model for agentic code generation grounded in the established STRIDE framework. It identifies six categories of agentic code failure that evade existing review processes, proposes the Agentic Code Failure (ACF) taxonomy for discussing these failures in policy contexts, and examines technical feasibility of automated enforcement as a complementary control. The central finding is that the primary risk of agentic coding is not malicious code generation but *plausible-but-wrong code at volume* — code that passes human review processes designed for human-authored code at human pace.

The paper poses questions for the Australian cybersecurity community regarding accreditation, trust boundaries, and the adequacy of current controls when AI agents become a standard part of the software development lifecycle.

---

## Section 4.2 — Original "practitioners report" paragraph (replaced in v0.2)

This is not theoretical. In compliance-constrained development environments known to the author, agent-generated code with semantic defects has passed human review and entered the codebase. In each observed case, the code was syntactically correct, followed project conventions, and appeared reasonable on inspection. The defects were semantic — violations of trust boundaries and data handling requirements that were not visible at the surface level. They were caught later, by other means (automated enforcement tooling, adjacent code review, downstream test failures), after the review process that was supposed to catch them had signed off.

---

## Section 6.1.1 — Original table format (replaced with definition list in v0.2)

| Control | Current Intent (Dec 2025) | Coverage of Agentic Threats | Gap |
|---------|--------------------------|---------------------------|-----|
| ISM-0401 (Rev 8, Jun-25) | Secure by Design principles and practices throughout the SDLC | Establishes that organisations should follow Secure by Design principles across the entire software development lifecycle. Agentic failure modes (Appendix A) could in principle be addressed as part of an organisation's Secure by Design practices. | The control assumes a human development team that can *internalise* security principles and apply them with judgment. Agents don't internalise principles — they reproduce training data patterns. A Secure by Design practice that says "don't fabricate defaults for missing safety-critical data" is unenforceable against an agent unless encoded as a machine-checkable rule. The control's scope (whole SDLC) is correct, but its enforcement mechanism (human judgment) doesn't transfer to agent-generated code. |
| ISM-1419 (Rev 1, Sep-18) | Development and modification of software only in development environments | Requires segregation of development from operational environments. This is orthogonal to agentic threats — it constrains *where* code is written, not *how* or *by whom*. | The control provides no coverage of agentic code quality or review. Its value is environmental separation, which remains important (agents should not have direct access to production environments) but does not address the semantic correctness of agent-generated code. |
| ISM-2060 (Rev 0, Jun-25) | Code reviews ensure software meets Secure by Design principles and secure programming practices | Directly applicable to agent-generated code — the agent is "the author" and a human is "the reviewer." The control explicitly links code review to Secure by Design principles, not just functional correctness. | The control assumes the reviewer can meaningfully evaluate the code at the rate it is produced. At agent-scale volume, this assumption fails (Section 4). The control does not address review effectiveness degradation, nor does it distinguish between surface-level review (syntax, conventions) and security-focused review (trust boundaries, audit trail integrity). |
| ISM-2061 (Rev 0, Jun-25) | Security-focused peer reviews on critical and security-focused software components | Requires developer-supported, security-focused peer reviews specifically on critical components. This is the strongest existing review control for the agentic context. | The control's limitation is scope: it applies to "critical and security-focused software components," which requires the organisation to correctly identify which agent-generated code touches security-critical paths. Agents generate code across the entire codebase; the security-critical subset must be identified before the review control can be applied. The control also assumes the peer reviewer has the institutional knowledge to evaluate trust boundary maintenance — knowledge that may not be documented in machine-readable form. |
| ISM-0402 (Rev 9, Jun-25) | Comprehensive software testing using SAST, DAST, and SCA | Mandates static application security testing (SAST), dynamic application security testing (DAST), and software composition analysis (SCA). These tools catch known vulnerability patterns and dependency risks. | The failure modes in this threat model are specifically designed to pass existing SAST/DAST tools (Section 2.3). Current SAST catches "does the code contain known vulnerability patterns?" but not "does the code maintain trust boundaries it doesn't know about?" Semantic boundary testing — verifying that data flows respect trust tiers — is a distinct category not addressed by existing SAST tooling. SCA is relevant for agent-introduced dependencies but does not address first-party code quality. |
| ISM-2026/2027/2028 (Jun-25) | Software artefact integrity — malicious code scanning, digital signatures, SAST/DAST/SCA on artefacts | Addresses integrity and security scanning of software artefacts before deployment. These controls cover the supply chain from build to deployment. | Agent-generated first-party code is a novel supply chain input — it's code that appears in-house but was produced by an external system (the AI model). The artefact integrity controls don't have a category for "first-party code generated by a third-party system." The risk properties are also different: third-party components have independent defect distributions, while agent-generated code has correlated defects (Section 2.4). The controls verify artefact integrity but not the semantic correctness of the code within those artefacts. |

## Section 6.1.2 — Original table format (replaced with definition list in v0.2)

| Gap Area | Relevant Threat | Why No Existing Control Applies |
|----------|----------------|-------------------------------|
| **Agent output as trust boundary** | ACF-T1, ACF-E1 | No control addresses the trust classification of AI-generated artifacts... |
| **Review capacity scaling** | ACF-D1, ACF-D2 | ISM-2060 and ISM-2061 mandate code review... |
| **Semantic boundary enforcement** | ACF-S1, ACF-T1, ACF-T2 | No control addresses the gap between syntactic and semantic correctness... |
| **Correlated failure detection** | All ACF categories | No control addresses the distinct risk profile of correlated defects... |
| **Code provenance tracking** | ACF-D2 | No control requires organisations to track which code was generated by AI agents... |

---
