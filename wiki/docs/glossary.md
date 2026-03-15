---
title: "Glossary"
---

# Glossary

!!! info "Provenance"
    Based on Discussion Paper DRAFT v0.3 (March 2026). Status: **v0.3 — DRAFT**

## Key Terms

These definitions are drawn from Section 1.3 of the discussion paper.

| Term | Definition |
|------|-----------|
| **Agent** | An AI system (typically an LLM) that generates, modifies, or reviews source code with limited or no human intervention per output. This paper focuses on autonomous and semi-autonomous agents that operate across multiple files and decisions (e.g., building a feature end-to-end), not inline autocomplete tools that suggest single-line completions. While both introduce volume, agents produce *correlated* errors across a module or feature, whereas autocomplete errors are typically isolated to individual expressions. |
| **Agentic code** | Source code generated or substantially modified by an agent. |
| **Autocomplete** | Inline code suggestion tools (e.g., standard GitHub Copilot) that complete individual lines or expressions within a human-directed editing session. Distinct from agents in that the human maintains architectural control and errors are uncorrelated. |
| **Agent deployment spectrum** | Agent risk profiles vary significantly by deployment model. At one end: a developer pasting chat output into an editor, where the human maintains full architectural context and reviews each fragment before integration. At the other: a CI-integrated autonomous agent that generates multi-file changes against a project-level instruction set, where the human reviews a completed changeset after generation. The paper's threat model applies primarily to the latter — agents operating with enough autonomy and context to produce *correlated* changes across a module or feature. |
| **Trust boundary** | A point in a system where data crosses between different levels of trust (e.g., external input entering internal processing). Refers to the *boundary itself* — the crossing point. |
| **Trust tier** | A classification of data based on its provenance and the degree to which it can be trusted. Refers to the *classification level* — Tier 1 (internal), Tier 2 (validated), Tier 3 (external). See [Trust Model](paper.md#5-agent-output-as-a-trust-boundary). |
| **Validation boundary** | The specific mechanism (code, process, or tool) that enforces a trust boundary — the control that data must pass through to cross from a lower to a higher trust tier. |
| **Defensive anti-pattern** | Context-inappropriate defensive patterns — coding patterns (`.get()` with defaults, broad exception handling, graceful degradation) that silently suppress errors. These patterns are appropriate in most software; the paper addresses their misapplication in high-assurance contexts where silent data corruption is worse than a crash. |

## ACF Taxonomy Quick Reference

The Agentic Code Failure (ACF) taxonomy catalogues 13 failure modes observed in agent-generated code, mapped to STRIDE threat categories. Each entry links to its full taxonomy page.

### Spoofing

**ACF-S1 (Competence Spoofing):** Default values fabricate data where the absence of data should be surfaced as a failure, error, or explicit "unknown." The code presents a confident result based on fabricated input. [Details &rarr;](taxonomy/acf-s1.md)

**ACF-S2 (Hallucinated Field Access):** Agent accesses a field name that doesn't exist on the target object, masked by `getattr()` with a default. The code operates on fabricated data while appearing to access a real field. [Details &rarr;](taxonomy/acf-s2.md)

**ACF-S3 (Structural Identity Spoofing):** A `hasattr()` check is used as a capability or privilege gate, allowing any object that declares the expected attribute to pass — regardless of whether the object is of the correct type. [Details &rarr;](taxonomy/acf-s3.md)

### Tampering

**ACF-T1 (Trust Tier Conflation):** Data from an external (untrusted) source is used in an internal (trusted) context without passing through a validation boundary. The data's effective trust level is silently elevated. [Details &rarr;](taxonomy/acf-t1.md)

**ACF-T2 (Silent Coercion):** Type coercion across trust boundaries hides data quality issues. Values are silently converted to a compatible type rather than being flagged as invalid. [Details &rarr;](taxonomy/acf-t2.md)

### Repudiation

**ACF-R1 (Audit Trail Destruction):** Broad exception handlers catch errors from audit-critical operations and log-and-continue rather than propagating the failure to the audit system. [Details &rarr;](taxonomy/acf-r1.md)

**ACF-R2 (Partial Completion):** A sequence of operations that should be atomic (all-or-nothing) is implemented without rollback, so partial failure leaves the system in an inconsistent state. [Details &rarr;](taxonomy/acf-r2.md)

### Information Disclosure

**ACF-I1 (Verbose Error Response):** Error handlers expose internal system details (database schemas, file paths, query parameters, library versions) in error responses. [Details &rarr;](taxonomy/acf-i1.md)

**ACF-I2 (Stack Trace Exposure):** Full tracebacks returned in API responses or user-facing error messages. Well-covered by existing tooling; included for taxonomy completeness. [Details &rarr;](taxonomy/acf-i2.md)

### Denial of Service

**ACF-D1 (Finding Flood):** The volume of static analysis findings on agent-generated code overwhelms reviewers, causing them to rubber-stamp findings without evaluation. A process threat, not a code pattern. [Details &rarr;](taxonomy/acf-d1.md)

**ACF-D2 (Review Capacity Exhaustion):** Agent code generation velocity exceeds the organisation's capacity for security-focused review, degrading review from active verification to passive scanning. A process threat, not a code pattern. [Details &rarr;](taxonomy/acf-d2.md)

### Elevation of Privilege

**ACF-E1 (Implicit Privilege Grant):** External system assertions are accepted without independent verification, granting privileges based on unvalidated claims. [Details &rarr;](taxonomy/acf-e1.md)

**ACF-E2 (Unvalidated Delegation):** User-supplied parameters are used directly in privileged operations (database queries, file access, system commands) without validation or restriction. [Details &rarr;](taxonomy/acf-e2.md)
