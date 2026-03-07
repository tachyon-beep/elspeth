# When Agents Write Code: A Threat Model for AI-Assisted Software Development in Government Systems

**Discussion Paper — DRAFT v0.1**
**Date:** 7 March 2026
**Classification:** OFFICIAL
**Prepared by:** John Morrissey, Digital Transformation Agency

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 7 March 2026 | Initial draft for community discussion |

---

## Abstract

AI coding agents are entering government software development workflows. These agents generate syntactically correct, test-passing code at unprecedented velocity. Current cybersecurity guidance — including the Australian Information Security Manual (ISM), NIST SP 800-218 (SSDF), and the Essential Eight — addresses software supply chain risk for human-authored code. It does not yet provide a vocabulary for the distinct failure modes of AI-generated code.

This paper presents a threat model for agentic code generation grounded in the established STRIDE framework. It identifies six categories of agentic code failure that evade existing review processes, proposes a taxonomy for discussing these failures in policy contexts, and examines technical feasibility of automated enforcement as a complementary control. The central finding is that the primary risk of agentic coding is not malicious code generation but *plausible-but-wrong code at volume* — code that passes human review processes designed for human-authored code at human pace.

The paper poses questions for the Australian cybersecurity community regarding accreditation, trust boundaries, and the adequacy of current controls when AI agents become a standard part of the software development lifecycle.

---

## Table of Contents

1. [Introduction and Scope](#1-introduction-and-scope)
2. [The Threat Is Not What You Think](#2-the-threat-is-not-what-you-think)
3. [STRIDE Applied to Agentic Code Output](#3-stride-applied-to-agentic-code-output)
4. [The Review Process as Attack Surface](#4-the-review-process-as-attack-surface)
5. [Agent Output as a Trust Boundary](#5-agent-output-as-a-trust-boundary)
6. [Current Guidance Gap Analysis](#6-current-guidance-gap-analysis)
7. [The Response Landscape](#7-the-response-landscape)
8. [Case Study: Agentic Development Under Compliance Constraints](#8-case-study-agentic-development-under-compliance-constraints)
9. [Open Questions for the Community](#9-open-questions-for-the-community)
10. [Recommendations](#10-recommendations)
11. [Appendix A: Agentic Code Failure Taxonomy](#appendix-a-agentic-code-failure-taxonomy)
12. [Appendix B: Technical Feasibility of Automated Enforcement](#appendix-b-technical-feasibility-of-automated-enforcement)

---

## 1. Introduction and Scope

### 1.1 What This Paper Addresses

The use of AI agents — large language models operating as autonomous or semi-autonomous code generators — in software development for government systems. Specifically: the security properties of code produced by agents, the adequacy of existing review and accreditation processes, and the gap in current cybersecurity guidance.

The underlying dynamics identified here — correlated patterns, consistent surface quality, review capacity exhaustion — generalise beyond code to any agent-assisted production pipeline (policy documents, security assessments, risk registers). This paper addresses the code case as the most concrete and technically tractable instance.

This paper does not address:
- AI as an *attack tool* (adversarial prompt injection, model poisoning)
- AI-generated content beyond source code (documents, communications) — though the threat dynamics identified here apply by analogy
- The procurement or accreditation of AI platforms themselves
- Privacy implications of training data

### 1.2 Why Now

Several converging factors make this urgent:

**Velocity vs. productivity — the distinction that matters.** Two claims about AI coding agents are often conflated, and this conflation obscures the threat:

- **Generation velocity** — how fast agents produce code — is unambiguously 5-20x faster than human developers. This is not speculative. Organisations are already shipping agent-generated code to production. The volume of code entering review pipelines has increased by an order of magnitude while the review capacity has not.

- **End-to-end development productivity** — how fast teams ship working, compliant, production-ready software — is contested. It depends on the system's compliance burden, the maturity of automated enforcement, the institutional knowledge gap between what the language permits and what the system requires, and the cost of post-generation review and rework (see Section 8 for a case study). In compliance-constrained environments, generation velocity gains are partially offset by the review, validation, and rework overhead that agent-generated code demands.

**The threat model in this paper is driven by generation velocity, not end-to-end productivity.** Whether agentic development delivers a net productivity gain is an interesting question, but it is irrelevant to the security argument. The threat is the volume of code entering the review pipeline — code that may contain the subtle semantic failures described in Section 3. That volume is determined by generation velocity, and generation velocity is unambiguously high and increasing. Even if the overall development cycle is only modestly faster (or, in some compliance contexts, no faster at all), the *review process* faces 5-20x the volume of code per unit time. The review bottleneck is a function of generation speed, not delivery speed.

**Trajectory.** These trends are accelerating, not plateauing. Agent capability improves with each model generation; review capacity does not. The attention gap between what agents produce and what humans can meaningfully verify is widening — and unlike previous productivity tools, the failure modes of agent-generated output are specifically the kind that require *more* attention per unit of output, not less. The problem is not that review is hard today; it is that the ratio of generation velocity to review capacity will be worse in twelve months than it is now.

**Capability.** Current-generation agents (2025-2026) produce code that is syntactically correct, passes unit tests, follows project conventions, and is difficult to distinguish from human-authored code on casual inspection. This makes traditional code review — which relies on surface-level pattern recognition under time pressure — significantly less effective as a security control.

**Precedent.** This is not a hypothetical threat model. In 2017, a single character error (`==` instead of `>=`) in a Cloudflare HTML parser leaked sensitive data — cookies, authentication tokens, HTTPS POST bodies — from millions of websites for months. The code was not malicious. It was plausible-but-wrong: it passed review, passed testing, and functioned normally until a Google researcher noticed anomalous data in search results. The bug was patched in hours, but the output — data cached by search engines worldwide — could not be fully recalled, and the true scope of exposure may never be known.

Cloudbleed was one developer, one function, at human velocity. The threat this paper addresses is what happens when the conditions that produced Cloudbleed — semantic errors invisible to review, amplified by infrastructure scale — become systematic rather than occasional, driven by agents replicating context-inappropriate patterns across entire codebases.

**Adoption pressure.** Government agencies face simultaneous pressure to modernise legacy systems, deliver digital services faster, and do more with constrained budgets. Agentic coding is an obvious productivity lever. Some agencies are already using it. Guidance that arrives after widespread adoption is guidance that arrives too late.

**The case against prohibition.** The response to these risks is not to ban agentic coding. Beyond the velocity gains, agents fundamentally change what is *tractable* for a development team. Complex refactoring across large codebases, systematic security remediation, architectural migrations, and comprehensive test coverage campaigns — tasks that previously required coordinating large teams over weeks — become feasible for a skilled developer who can hold the entire problem in their head. This is not just faster; it is qualitatively better. A single developer directing agents through a codebase-wide refactor maintains one coherent architectural vision. The same refactor distributed across a dozen human developers produces a dozen slightly different interpretations of the target state, with integration friction and inconsistency at every seam. Prohibition would sacrifice this capability benefit — the ability to undertake more complex, more voluminous work with greater coherence — not just the velocity benefit. The goal of this paper is not to argue against adoption but to ensure that the controls surrounding adoption are adequate for the risk profile — which is distinct from, and more subtle than, the risks that current guidance addresses.

**Legacy modernisation risk.** Legacy systems often encode implicit trust boundaries in their rigidity — a COBOL program that crashes on a NULL field is enforcing, accidentally, the same crash-on-corruption principle that high-assurance systems require deliberately. When agents are tasked with "translating" or refactoring legacy code into modern languages, they will seamlessly replace that rigidity with modern defensive patterns (null coalescing, optional chaining, default values), permanently destroying the institutional knowledge that was baked into the old code's behaviour. The legacy system's implicit security properties are paved over with idiomatic, test-passing, wrong code.

### 1.3 Terminology

| Term | Definition |
|------|-----------|
| **Agent** | An AI system (typically an LLM) that generates, modifies, or reviews source code with limited or no human intervention per output. This paper focuses on autonomous and semi-autonomous agents that operate across multiple files and decisions (e.g., building a feature end-to-end), not inline autocomplete tools that suggest single-line completions. While both introduce volume, agents produce *correlated* errors across a module or feature, whereas autocomplete errors are typically isolated to individual expressions. |
| **Agentic code** | Source code generated or substantially modified by an agent |
| **Autocomplete** | Inline code suggestion tools (e.g., standard GitHub Copilot) that complete individual lines or expressions within a human-directed editing session. Distinct from agents in that the human maintains architectural control and errors are uncorrelated. |
| **Trust boundary** | A point in a system where data crosses between different levels of trust (e.g., external input entering internal processing) |
| **Trust tier** | A classification of data based on its provenance and the degree to which it can be trusted (see Section 5) |
| **Defensive anti-pattern** | A coding pattern that silently suppresses errors rather than making them visible — also referred to as "defensive programming" or "defensive patterns" throughout this paper (e.g., catching all exceptions and returning a default value) |

---

## 2. The Threat Is Not What You Think

### 2.1 The Intuitive Threat Model (Incomplete)

When organisations evaluate the risk of AI-generated code, the intuitive threat model is straightforward:

> *"The AI might write malicious code — backdoors, data exfiltration, supply chain attacks."*

This threat is real but well-understood. It maps directly to the existing software supply chain threat model with a faster generator. Existing controls — code review, static analysis, dependency scanning, penetration testing — address it, albeit with increased volume pressure.

### 2.2 The Actual Threat Model (Novel)

The novel and more dangerous threat is:

> *"The AI writes plausible-but-wrong code at scale — code that passes tests, passes review, and silently violates security boundaries through patterns that are normal in the programming language but catastrophic in high-assurance contexts."*

This threat is distinct from the supply chain model in three critical ways:

**It is not adversarial.** The agent is not trying to compromise the system. It is producing its best output based on training data that is overwhelmingly composed of open-source code with no security classification requirements, no audit trail obligations, and no trust boundary enforcement. The agent reproduces the patterns it learned — which are the patterns of code that doesn't need to be secure.

**It is invisible to existing detection.** The generated code is syntactically valid. It passes type checkers, linters, and unit tests. It follows project conventions (agents are good at pattern-matching the surrounding codebase). It is, by every automated measure currently in common use, "correct code." The failure is semantic — the code does the wrong thing in the security context while doing the right thing in every other context.

**It scales with the benefit.** The faster agents generate code, the more plausible-but-wrong code enters the review pipeline. The same velocity that makes agents productive makes them dangerous — and you cannot capture the benefit without accepting the risk, because they are the same mechanism.

### 2.3 A Concrete Example

Consider a government system that processes security classifications:

```python
# Best: offensive programming — crash with maximum diagnostic context
def get_document_classification(record):
    if "security_classification" not in record:
        raise DataIntegrityError(
            f"Missing security_classification for document {record.get('id', '?')}. "
            f"This is a data integrity failure — investigate the source system. "
            f"Fields present: {sorted(record.keys())}"
        )
    return record["security_classification"]
    # If the field is missing, the operator knows exactly which document,
    # exactly what fields were present, and exactly what to investigate.
    # The error message is the incident response runbook.

# Acceptable: bare access — crashes, but with a generic KeyError
def get_document_classification(record):
    classification = record["security_classification"]
    # If the field is missing, this crashes — which is correct.
    # A missing classification is a data integrity failure,
    # not a scenario to handle gracefully.
    # But the operator gets "KeyError: 'security_classification'" with
    # no context about which document or why.
    return classification

# Agent-authored (plausible, test-passing, catastrophically wrong)
def get_document_classification(record):
    classification = record.get("security_classification", "OFFICIAL")
    # If the field is missing, silently defaults to lowest classification.
    # This "works" — no crash, no error, tests pass.
    # But a PROTECTED document with a missing classification field
    # is now labelled OFFICIAL and treated accordingly.
    return classification
```

The three versions illustrate a spectrum. The offensive version turns a crash into an actionable incident — the operator knows which document, what data was present, and what to investigate. The bare access version at least crashes, which is correct behaviour for a data integrity failure, but the operator gets a generic `KeyError` with no diagnostic context. The agent-generated version is the worst outcome: it doesn't crash at all, silently fabricating a classification that downstream access control decisions will treat as authoritative.

The agent-generated version:
- Is syntactically valid Python
- Passes every unit test (tests probably don't include "field missing" cases, because why would they?)
- Follows the `.get()` pattern that appears in millions of Python files in the agent's training data
- Would pass casual code review (it looks like defensive, robust coding)
- Silently downgrades document classifications when data integrity failures occur

This is not a hypothetical. This is the pattern that defensive programming produces *by default* in Python, and agents are trained on defensive Python.

### 2.4 What Is Fundamentally Different About Agentic Code

The threat model for agent-generated code is not simply "human-authored code but more of it." Several properties are qualitatively different:

**Limited persistent learning.** A human developer who receives review feedback on a trust boundary violation learns from it and is less likely to repeat the mistake. Agents have limited or no persistent memory across sessions. Some agent frameworks now support project-level instructions (system prompts, documentation files, memory stores) that provide partial mitigation. An agent can be told "don't use `.get()` on audit data" and will follow that instruction within a session. But these are explicit rules, not internalised judgment. The agent cannot generalise from "don't use `.get()` on audit data" to "don't fabricate defaults anywhere that data absence is meaningful" unless that generalisation is also spelled out. Every correction must be encoded as a rule; the agent does not learn the *principle* behind the correction. This means that *review feedback improves the generator only to the extent that it is captured as machine-readable rules* — and the coverage of those rules is always trailing the set of possible failure modes.

**Consistent surface quality.** Human code has variable surface quality — hasty code looks hasty, careful code looks careful. Reviewers use surface quality as a signal for where to focus attention. Agent code has uniformly high surface quality regardless of semantic correctness. A function with a critical trust boundary violation looks exactly as polished as a function without one. The reviewer's natural calibration signal — "this code looks sloppy, I should look more carefully" — is absent.

**Pattern completion, not intent.** A human developer writing `record.get("classification", "OFFICIAL")` has either made a deliberate design decision (the default is intentional) or made an error (they didn't think about the missing-field case). The distinction is visible in context — comments, commit messages, design docs. An agent writing the same code is completing a pattern from training data. It has no design intent. There is no commit message that explains why the default is correct, because the agent didn't decide it was correct — it predicted it was the next likely token. This means **intent-based review ("why did you write it this way?") is meaningless for agent code.** The review must be entirely outcome-based ("is the behaviour correct for this context?").

**Correlated failure modes.** When ten human developers write code for a system, their errors are largely independent — different people make different mistakes. When an agent generates ten functions, its errors are *correlated* — the same training data biases produce the same failure modes repeatedly. A single systematic bias (e.g., "always use `.get()` with a default") produces correlated vulnerabilities across the entire codebase. This is not the independent-error model that code review and testing strategies are designed for.

**No fatigue, no shortcuts — but also no judgment.** Agents don't get tired, don't take shortcuts under deadline pressure, and don't introduce bugs from distraction. But they also don't exercise judgment about which patterns are appropriate in which contexts. A human developer who is tired might introduce a bug in one function; an agent that lacks context will introduce the same incorrect pattern in every function it generates. The failure mode is not degradation under pressure — it is *systematic misapplication of context-inappropriate patterns*.

### 2.5 Why Training Data Is the Root Cause

The vast majority of open-source Python code uses defensive patterns: `.get()` with defaults, `getattr()` with fallbacks, broad `try/except` blocks, `or` chains that silently substitute values. These patterns are appropriate for applications where graceful degradation is preferable to crashing — which is most applications.

They are catastrophically inappropriate for applications where:
- Silent data corruption is worse than a crash
- Every decision must be traceable to its source
- The absence of data is itself evidence (not an invitation to fabricate a default)
- Error paths must be as auditable as success paths

Government systems handling classified information, financial records, health data, or law enforcement evidence fall squarely into this category. The agent doesn't know this. It can't know this from the code alone — the security context is institutional knowledge, not syntactic structure.

---

## 3. STRIDE Applied to Agentic Code Output

### 3.1 Framework Selection

STRIDE (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege) is the established threat modelling framework used in Australian government security assessments. Applying it to agentic code output provides a structured vocabulary that policy audiences already understand, rather than inventing new terminology.

The application below extends STRIDE to treat **agent-generated code as an input** to the system — analogous to treating user input as untrusted. The agent is not an adversary, but its output has the same trust properties as any external input: it may be well-formed, it may be reasonable, but it has not been validated against the system's security requirements.

### 3.2 Threat Categories

#### S — Spoofing: Competence Spoofing

**Traditional:** An entity impersonates another entity.
**Agentic variant:** Code *appears* to handle data correctly but operates on fabricated or default values, presenting a false picture of data integrity.

**Mechanism:** Agents default to defensive patterns that substitute values rather than failing. The code "works" — it produces output, it doesn't crash — but the output is based on fabricated data rather than actual data. The code spoofs the competence of correct data handling.

**Examples:**

```python
# Fabricates a default rather than surfacing missing data
user_role = getattr(session, "role", "readonly")
# If session.role doesn't exist (bug, tampering, schema change),
# user silently gets "readonly" — which might be WRONG in either direction.
# If they should have been "admin", they can't work.
# If "readonly" still has access to sensitive data, it's a privilege grant.

# Presents fabricated confidence
confidence = result.get("confidence_score", 0.5)
# A missing confidence score defaults to "medium confidence"
# rather than "unknown" — downstream decisions treat this as real data.
```

**Why existing controls miss it:** The code is syntactically valid, follows common patterns, and passes tests. A human reviewer under time pressure sees "defensive coding" — a positive signal. The fabrication is invisible without understanding the security semantics of each field.

**Risk in government context:** Classification decisions, access control, evidentiary integrity — any domain where "I don't know" and "the default" are different answers with different consequences.

#### T — Tampering: Silent Trust Tier Coercion

**Traditional:** Unauthorized modification of data.
**Agentic variant:** External (untrusted) data is treated as internal (trusted) data without validation, effectively tampering with the trust level rather than the data itself.

**Mechanism:** Agents don't distinguish between data from different trust levels because the programming language doesn't enforce it. A `dict` from a validated database query and a `dict` from an unvalidated API response are the same type. The agent treats them interchangeably.

**Examples:**

```python
# API response used directly without validation boundary
api_response = requests.get(external_url).json()
save_to_internal_database(api_response["records"])
# External data enters the trusted internal store without validation.
# The data might be malformed, might contain injection payloads,
# might be missing required fields.
# The agent doesn't see a trust boundary — it sees a dict going into a function.

# Deserialized data assumed trustworthy
config = json.loads(uploaded_config_file.read())
apply_system_settings(config)
# User-uploaded JSON treated as trusted configuration.
# No schema validation, no field allowlisting, no type checking.
```

**Why existing controls miss it:** Type checkers verify shape (`dict`), not provenance (where the dict came from). Linters check syntax, not data flow. The code has no detectable defect at any analysis level short of semantic boundary tracking.

**Risk in government context:** Injection attacks through unvalidated external data, data corruption of authoritative records, compliance failures when data provenance cannot be demonstrated.

#### R — Repudiation: Audit Trail Destruction Through Error Handling

**Traditional:** A user denies performing an action, and the system cannot prove otherwise.
**Agentic variant:** Error handling patterns destroy the audit trail by catching, logging, and continuing rather than failing in a way that preserves the error as a first-class audit event.

**Mechanism:** Agents generate broad exception handlers that prevent crashes but also prevent errors from being recorded in audit systems. The error is "handled" in the sense that the program continues, but the event that caused the error is lost to the audit trail.

**Examples:**

```python
# Error swallowed — audit trail has a gap
try:
    record_decision(case_id, decision, evidence)
except Exception as e:
    logger.warning(f"Failed to record decision: {e}")
    # Decision was made but not recorded.
    # If this is a legal/regulatory decision, the audit trail
    # now has a gap that cannot be reconstructed.
    # The log message may be rotated, compressed, or lost.
    # The audit database — the authoritative record — shows nothing.

# Partial completion without rollback
try:
    update_classification(document_id, new_level)
    notify_stakeholders(document_id, new_level)
    record_classification_change(document_id, old_level, new_level)
except NotificationError:
    pass  # "Notification is non-critical"
    # Classification changed, stakeholders not notified, change not recorded.
    # Three operations that should be atomic are silently partial.
```

**Why existing controls miss it:** The code handles exceptions — which is generally considered good practice. The distinction between "handle the error and continue safely" and "swallow the error and destroy evidence" requires understanding which operations are audit-critical. The agent doesn't know.

**Risk in government context:** Regulatory compliance (failure to maintain complete audit trails), legal proceedings (gaps in evidence chains), IRAP assessment failures (inability to demonstrate complete traceability).

#### I — Information Disclosure: Verbose Error Responses

**Traditional:** Exposing information to unauthorized users.
**Agentic variant:** Agent-generated error handling exposes internal system details in error responses, log messages, or API returns.

**Mechanism:** Agents produce "helpful" error messages that include internal state, query parameters, file paths, or stack traces. This is good practice for development but dangerous in production, and agents don't distinguish between the two contexts.

**Examples:**

```python
# Agent-generated "helpful" error handler
except DatabaseError as e:
    return {
        "error": str(e),
        "query": sql_query,         # Exposes database schema
        "connection": str(db_url),  # May contain credentials
        "params": query_params,     # Exposes internal identifiers
    }

# Stack trace in API response
except Exception as e:
    import traceback
    return {"error": traceback.format_exc()}
    # Full stack trace including file paths, function names,
    # library versions — a reconnaissance goldmine.
```

**Why existing controls miss it:** The error handling is syntactically correct and genuinely helpful during development. Detecting that internal details should not appear in production error responses requires understanding the deployment context, not the code structure.

**Risk in government context:** Reconnaissance information for attackers, credential exposure, violation of need-to-know principles.

#### D — Denial of Service: Finding Flood (Meta-Threat)

**Traditional:** Making a system unavailable.
**Agentic variant:** The volume of agent-generated code overwhelms the review process, degrading review quality to the point where the review is no longer an effective security control.

**Mechanism:** This is not a code pattern — it is a *process* threat. When agents generate code at 10x velocity, the review queue grows 10x. Reviewers under volume pressure shift from careful semantic review to surface-level scanning. The review process — which is a security control — degrades to a rubber stamp.

A secondary mechanism: when automated analysis tools produce too many findings on agent-generated code, reviewers habituate to dismissing findings, and genuine security issues are lost in the noise.

**Why existing controls miss it:** Existing controls assume review capacity scales with code generation rate. It doesn't. The control's effectiveness is inversely proportional to the volume it processes, which is the opposite of every other scaling assumption in the process.

**Risk in government context:** Security review as a compliance checkbox rather than an effective control, accreditation based on a process that no longer provides the assurance it claims to provide.

#### E — Elevation of Privilege: Trust Tier Conflation

**Traditional:** Gaining capabilities beyond what is authorized.
**Agentic variant:** Data from a lower trust level is used in a higher-trust context without explicit validation, effectively elevating the data's privilege level.

**Mechanism:** Closely related to Tampering (Section 3.2, T), but focused on the *consequence* rather than the *mechanism*. When external data enters internal processing without validation, any actions taken based on that data inherit a trust level they haven't earned.

**Examples:**

```python
# User-supplied filter used in internal query without validation
def search_records(user_query: dict):
    # user_query comes from an API request (untrusted)
    results = db.query(Record).filter_by(**user_query)
    # **user_query unpacks arbitrary keys into the query filter.
    # User can filter on internal fields (is_deleted, internal_score)
    # that should not be exposed.
    return results

# External system's assertion accepted without verification
partner_response = partner_api.verify_identity(applicant_id)
if partner_response.get("verified", False):
    grant_access(applicant_id)
    # Partner system's assertion of identity is accepted at face value.
    # No independent verification, no recording of the basis for the decision.
    # The partner's trust level is silently elevated to our trust level.
```

**Why existing controls miss it:** The code follows common integration patterns. The privilege elevation is implicit — no explicit `setRole()` or `grantPermission()` call that a scanner could detect. The elevation happens through data flow, not code structure.

**Risk in government context:** Unauthorized access to classified information, acceptance of unverified identity assertions in federated systems, compliance failures in inter-agency data sharing.

### 3.3 The Compounding Effect

These six threat categories do not operate independently. In practice, they compound:

1. An agent generates code with **trust tier conflation** (E) — external API data used directly
2. The missing validation means errors in that data are caught by a broad `except` block — **audit trail destruction** (R)
3. The `except` block returns a default value — **competence spoofing** (S)
4. The default value is treated as authoritative data downstream — **silent trust tier coercion** (T)
5. The volume of agent-generated code means the reviewer doesn't catch any of this — **finding flood** (D)

Each individual pattern looks like ordinary defensive coding. The compound effect is a system that silently produces wrong results, can't explain why, and passed every review gate.

---

## 4. The Review Process as Attack Surface

### 4.1 The Asymmetry Problem

Human code review evolved as a control for human-authored code at human pace. It relies on several assumptions that agentic coding violates:

| Assumption | Human Code | Agent Code |
|-----------|---------------|----------------|
| **Volume** | Reviewers can read most of the code | Volume makes comprehensive reading impossible |
| **Familiarity** | The author can explain their intent | The agent's "intent" is pattern completion from training data |
| **Conventions** | Unusual patterns are suspicious | Agents follow conventions precisely — the dangerous code looks normal |
| **Error rate** | Human error rate is ~1-5% per function | Agent error rate for *semantic* correctness is unknown and context-dependent |
| **Feedback** | Reviewer feedback improves the author | Agent has no persistent memory across review cycles |

### 4.2 The Habituation Effect

When agents generate code that consistently passes tests and follows conventions, reviewers develop trust in the agent's output. This trust is not earned — it is a cognitive shortcut driven by volume pressure. In human factors engineering, this phenomenon is known as **automation bias**: the tendency to over-rely on automated systems and under-scrutinise their output. The effect is well-documented in aviation safety, medical decision support, and industrial automation — domains where humans routinely accept machine output without independent verification once the machine has established a track record of being "usually right."

The reviewer's mental model shifts from "verify this code is correct" to "check this code isn't obviously wrong." The difference is enormous: the first is an active search for defects; the second is a passive scan that catches only gross errors.

This is not theoretical. Practitioners report that agent-generated code of questionable quality has already passed human review in production development workflows. The code was syntactically correct, followed project conventions, and appeared reasonable on inspection. The defects were semantic — violations of trust boundaries and data handling requirements that were not visible at the surface level. They were caught later, by other means, after the review process that was supposed to catch them had signed off.

This is the "Shifting the Burden" systems archetype: the agent's consistent surface-quality output becomes the symptomatic fix that weakens the fundamental solution (thorough human review). The more the agent produces acceptable-looking code, the less carefully humans review it, and the more dependent the process becomes on the agent being correct — which is exactly the assumption the review process exists to check.

A related but distinct mechanism compounds this effect. Agent-assisted velocity increases the *parallelisation* of work, not just its speed. When an agent assists in producing multiple interdependent artifacts simultaneously — a design specification, an implementation, and a policy document — semantic inconsistencies *between* artifacts become invisible because no single review pass covers all of them. The review window for cross-document consistency shrinks in proportion to the velocity gain. The reviewer is not only less careful per artifact, but also unable to hold the full production context in working memory at the rate artifacts are produced.

The availability of parallel agent generation creates a structural pressure that procedural and behavioural controls may mitigate but are unlikely to eliminate, because the same incentives driving adoption also reward bypassing throughput-constraining review practices. An organisation can prohibit developers from running multiple agents concurrently, but the prohibition runs directly against the productivity incentive that justified adopting agentic development. Controls that depend on sustained human restraint in the face of convenience are inherently fragile — a principle well-established in security engineering but easy to overlook when the convenience is "write code five times faster." The implications for control selection are examined in Section 7.

### 4.3 The Wrong Question

When organisations evaluate the feasibility of security tooling for agentic code (as examined in Appendix B), the instinctive question is: *"How big is it? How many lines of code? How many hours to build?"*

This is the wrong question. It inherits the assumption that scope correlates with assurance — that a 200-line tool provides less assurance than a 2000-line tool, or that 220 hours of development is insufficient for a security-critical control.

The right question is: **"How do you know it's correct?"**

This question applies recursively. If the security enforcement tool is itself built by an agent (which is increasingly likely for any new tool), then the tool's correctness is subject to the same threat model it exists to address. The verification mechanism — not the implementation size — is the assurance argument.

This reframing has direct implications for policy:
- **Accreditation should evaluate the verification story**, not the implementation scope. A small tool with a rigorous golden corpus, self-hosting gate, and measured precision is stronger than a large tool without these properties.
- **"How do you know the agent wrote it correctly?"** is the question that applies to all agent-generated code, including the tools that check agent-generated code. The answer must be grounded in independent verification (test corpus, self-hosting, measured false positive/negative rates), not in the development process used to produce it.
- **The line between "tool" and "assurance argument" blurs.** The design of a semantic boundary enforcer (Appendix B) is essentially a structured answer to "how do you know the code is correct?" — and that answer is valuable independent of whether the specific tool gets built.

This reframing directly informs Recommendations 1 and 5 — accreditation should evaluate the verification story, and IRAP assessors should assess review quality, not just review process.

### 4.4 The Advisory Fatigue Problem

Static analysis tools that flag agent-generated code patterns as warnings face a paradox:
- If agents produce many warnings, reviewers habituate to dismissing them
- If agents learn to avoid warning-triggering patterns, they may produce code that satisfies the tool but still violates the semantic intent
- Advisory-only tools have no enforcement mechanism for agents, which have no memory across sessions — a warning shown to an agent in one session is forgotten in the next

This means the traditional "warn first, enforce later" adoption strategy for security tooling is ineffective for agent-generated code. Agents require enforcement at the boundary (before code enters the repository), not feedback over time (which requires learning).

---

## 5. Agent Output as a Trust Boundary

### 5.1 The Trust Tier Model

Data in high-assurance systems can be classified by provenance into trust tiers:

| Tier | Description | Handling Rule | Example |
|------|-------------|---------------|---------|
| **Tier 1: Internal data** | Data authored by the system itself — audit records, internal state, configuration | Full trust. Any anomaly indicates corruption or tampering — fail immediately, do not attempt recovery | Database audit trail, system configuration, internal state machines |
| **Tier 2: Validated data** | Data that entered the system from outside but has been validated at the boundary | Elevated trust. Types are reliable; values may still cause operational failures | API response after schema validation, CSV row after type coercion |
| **Tier 3: External data** | Data from outside the system boundary, not yet validated | Zero trust. May be malformed, malicious, or missing. Validate at boundary, quarantine failures | Raw API responses, user uploads, message queue payloads |

### 5.2 Agent Code as Tier 3

The central proposal of this paper: **agent-generated code should be treated as Tier 3 (external, untrusted) data until validated.**

This is not a statement about agent quality — agents produce excellent code much of the time. It is a statement about *provenance*. The agent is an external system. Its output has not been validated against the system's security requirements. The fact that the output is source code rather than JSON or CSV does not change its trust properties.

Treating agent code as Tier 3 has specific implications:

| Principle | Application |
|-----------|------------|
| **Validate at the boundary** | Agent output must pass security-aware validation before entering the codebase |
| **Quarantine failures** | Code that fails validation is rejected, not silently corrected |
| **Record what we got** | The original agent output is preserved for audit, even if modified during review |
| **No silent coercion** | Agent code is not silently "fixed up" by reviewers — changes are explicit and recorded |

### 5.3 Implications for the Development Workflow

If agent output is Tier 3, the development workflow must include a **validation boundary** between agent generation and code integration:

```
Agent generates code
        │
        ▼
┌─────────────────────┐
│  VALIDATION BOUNDARY │  ← This is the trust boundary
│                      │
│  • Automated semantic│     Not just syntax/type checking —
│    boundary checking │     trust tier flow, defensive pattern
│  • Human review of   │     detection, audit trail completeness
│    semantic intent   │
│  • Attestation       │     Reviewer attests validation was
│                      │     meaningful, not rubber-stamped
└─────────────────────┘
        │
        ▼
Code enters repository
(now Tier 2 — validated)
```

The key difference from current practice: **the validation is security-aware, not just correctness-aware.** Current code review asks "does this code work?" Security-aware validation asks "does this code maintain the system's trust boundaries?"

---

## 6. Current Guidance Gap Analysis

### 6.1 Australian Information Security Manual (ISM)

The ISM provides controls for software development security (primarily in the Software Development and Web Application Development chapters). The analysis below maps relevant controls to the agentic code threat model, identifying where existing controls provide partial coverage, where they assume conditions that agentic coding invalidates, and where gaps exist.

*Note: The ISM underwent a significant expansion in June 2025, adding approximately 24 new controls to the Software Development guidelines. The analysis below references the December 2025 revision of the ISM. Organisations using earlier versions should verify control numbers against the current release.*

#### 6.1.1 Controls with Partial Coverage

| Control | Current Intent (Dec 2025) | Coverage of Agentic Threats | Gap |
|---------|--------------------------|---------------------------|-----|
| ISM-0401 (Rev 8, Jun-25) | Secure by Design principles and practices throughout the SDLC | Establishes that organisations should follow Secure by Design principles across the entire software development lifecycle. Agentic failure modes (Appendix A) could in principle be addressed as part of an organisation's Secure by Design practices. | The control assumes a human development team that can *internalise* security principles and apply them with judgment. Agents don't internalise principles — they reproduce training data patterns. A Secure by Design practice that says "don't fabricate defaults for missing safety-critical data" is unenforceable against an agent unless encoded as a machine-checkable rule. The control's scope (whole SDLC) is correct, but its enforcement mechanism (human judgment) doesn't transfer to agent-generated code. |
| ISM-1419 (Rev 1, Sep-18) | Development and modification of software only in development environments | Requires segregation of development from operational environments. This is orthogonal to agentic threats — it constrains *where* code is written, not *how* or *by whom*. | The control provides no coverage of agentic code quality or review. Its value is environmental separation, which remains important (agents should not have direct access to production environments) but does not address the semantic correctness of agent-generated code. |
| ISM-2060 (Rev 0, Jun-25) | Code reviews ensure software meets Secure by Design principles and secure programming practices | Directly applicable to agent-generated code — the agent is "the author" and a human is "the reviewer." The control explicitly links code review to Secure by Design principles, not just functional correctness. | The control assumes the reviewer can meaningfully evaluate the code at the rate it is produced. At agent-scale volume, this assumption fails (Section 4). The control does not address review effectiveness degradation, nor does it distinguish between surface-level review (syntax, conventions) and security-focused review (trust boundaries, audit trail integrity). |
| ISM-2061 (Rev 0, Jun-25) | Security-focused peer reviews on critical and security-focused software components | Requires developer-supported, security-focused peer reviews specifically on critical components. This is the strongest existing review control for the agentic context. | The control's limitation is scope: it applies to "critical and security-focused software components," which requires the organisation to correctly identify which agent-generated code touches security-critical paths. Agents generate code across the entire codebase; the security-critical subset must be identified before the review control can be applied. The control also assumes the peer reviewer has the institutional knowledge to evaluate trust boundary maintenance — knowledge that may not be documented in machine-readable form. |
| ISM-0402 (Rev 9, Jun-25) | Comprehensive software testing using SAST, DAST, and SCA | Mandates static application security testing (SAST), dynamic application security testing (DAST), and software composition analysis (SCA). These tools catch known vulnerability patterns and dependency risks. | The failure modes in this threat model are specifically designed to pass existing SAST/DAST tools (Section 2.3). Current SAST catches "does the code contain known vulnerability patterns?" but not "does the code maintain trust boundaries it doesn't know about?" Semantic boundary testing — verifying that data flows respect trust tiers — is a distinct category not addressed by existing SAST tooling. SCA is relevant for agent-introduced dependencies but does not address first-party code quality. |
| ISM-2026/2027/2028 (Jun-25) | Software artefact integrity — malicious code scanning, digital signatures, SAST/DAST/SCA on artefacts | Addresses integrity and security scanning of software artefacts before deployment. These controls cover the supply chain from build to deployment. | Agent-generated first-party code is a novel supply chain input — it's code that appears in-house but was produced by an external system (the AI model). The artefact integrity controls don't have a category for "first-party code generated by a third-party system." The risk properties are also different: third-party components have independent defect distributions, while agent-generated code has correlated defects (Section 2.4). The controls verify artefact integrity but not the semantic correctness of the code within those artefacts. |

#### 6.1.2 Controls with No Coverage

| Gap Area | Relevant Threat | Why No Existing Control Applies |
|----------|----------------|-------------------------------|
| **Agent output as trust boundary** | ACF-T1 (trust tier conflation), ACF-E1 (implicit privilege grant) | No control addresses the trust classification of AI-generated artifacts. Agent code is neither "in-house" (human-authored) nor "third-party" (external component) — it's a new category. ISM-2074 (Dec-25) requires organisations to notify ASD of AI use in ICT, but this is a governance/notification control, not a technical trust boundary control. |
| **Review capacity scaling** | ACF-D1 (finding flood), ACF-D2 (review capacity exhaustion) | ISM-2060 and ISM-2061 mandate code review and security-focused peer review, but neither addresses what happens when code generation velocity exceeds review capacity. No control requires organisations to demonstrate that review remains effective under volume pressure. |
| **Semantic boundary enforcement** | ACF-S1 (competence spoofing), ACF-T1 (trust tier conflation), ACF-T2 (silent coercion) | No control addresses the gap between syntactic correctness and semantic correctness in the context of trust boundaries. ISM-0402's SAST/DAST/SCA requirement covers known vulnerability patterns but not context-dependent semantic correctness. Existing controls assume that if code passes review and testing, it is adequate. |
| **Correlated failure detection** | All ACF categories | No control addresses the distinct risk profile of correlated defects. Testing and review strategies are designed for independent failure distributions. |
| **Code provenance tracking** | ACF-D2 (review capacity exhaustion) | No control requires organisations to track which code was generated by AI agents vs. authored by humans. ISM-2074 requires notification of AI use but not per-artifact provenance. Without provenance, risk assessment cannot distinguish between code populations with different failure characteristics. |

#### 6.1.3 Candidate ISM Extensions

The following are illustrative extensions, not formal proposals. They are included to demonstrate that the gaps are addressable within the ISM's existing structure. The use of SHOULD below follows the ISM's existing convention for conditional controls — it is illustrative wording to show how these extensions might read, not normative language.

**Extension to ISM-0401 (Secure by Design):**
> *When AI agents are used to generate code for assessed systems, the organisation's Secure by Design practices SHOULD include machine-enforceable rules for trust boundary maintenance, defensive pattern restrictions appropriate to the system's data sensitivity, and audit trail preservation requirements. Secure by Design principles that exist only as human-readable documentation are insufficient controls against AI-generated code, which does not read documentation.*

**Extension to ISM-2060/2061 (Code Review and Security-Focused Peer Review):**
> *When AI agents generate a significant proportion of code changes, the organisation SHOULD demonstrate that its code review process (ISM-2060) and security-focused peer review process (ISM-2061) remain effective at detecting semantic defects — not merely syntactic or conventional defects — under the volume of changes produced. Evidence may include measured defect escape rates, review depth audits, or demonstrated use of automated semantic pre-screening that reduces the burden on human reviewers.*

**New control (Agent Output Trust Boundary):**
> *Code generated by AI agents SHOULD be treated as external input requiring validation at the boundary before integration into assessed systems. The organisation SHOULD define and document the validation boundary, including what properties are verified (trust boundary maintenance, audit trail integrity, error handling appropriateness) and what evidence demonstrates the validation is effective.*

**New control (Code Provenance):**
> *When AI agents are used in the development of assessed systems, the organisation SHOULD maintain records of which code was generated by AI agents, which was human-authored, and which was agent-generated then human-modified. This provenance metadata supports risk assessment, incident response, and targeted remediation when systematic agent-introduced defects are discovered.*

### 6.2 NIST Secure Software Development Framework (SSDF)

SP 800-218 defines practices for secure software development organised into four groups. The analysis below maps each group to agentic code concerns:

| Practice Group | SSDF Practices | Agentic Code Coverage |
|---------------|----------------|----------------------|
| **Prepare the Organization (PO)** | Define security requirements, roles, training | Does not address training requirements for reviewing agent output (which requires different skills than reviewing human output) or organisational capacity planning for agent-scale review volume |
| **Protect the Software (PS)** | Protect code, integrity verification | Addresses integrity of code artifacts but not the trust classification of code based on its generation method. An agent-generated commit and a human-authored commit are indistinguishable in the VCS |
| **Produce Well-Secured Software (PW)** | Design, code review, testing | The most relevant group. PW.5 (code review), PW.7 (testing), and PW.8 (verification) all partially apply. However, PW assumes a human developer who can be trained, who learns from feedback, and whose error rate is independent across functions — none of which hold for agents |
| **Respond to Vulnerabilities (RV)** | Vulnerability response, disclosure | Does not address the correlated nature of agent-introduced defects. Standard vulnerability response treats each finding independently; agent defects require pattern-wide remediation (Section 9.7) |

**Key SSDF gap:** PW.1.1 recommends "using forms of risk-based analysis to determine how much effort is adequate" for security practices. This implicitly assumes that risk is assessable per-component. Agent-generated code introduces *systematic* risk across many components from a single source — the analysis framework needs to account for correlation, not just per-component risk.

### 6.3 Essential Eight

The Essential Eight maturity model does not directly address software development practices. However, two strategies are relevant by analogy:

**Application Control** establishes that not all software should be trusted equally based on its source. The maturity levels (ML1: prevent execution of unapproved programs; ML2: restrict to approved directories; ML3: comprehensive control) provide a model for graduated trust that could be extended to code generation sources. Analogy: agent-generated code is "unapproved software" until it passes through a validation boundary — similar to how an unsigned binary is untrusted until it meets the application control policy.

**Restrict Administrative Privileges** establishes the principle of least privilege. Applied to agentic coding: agents should not have the ability to modify security-critical configuration (e.g., allowlists, audit configuration, access control rules) without human approval. This maps directly to the `CODEOWNERS` protection and temporal separation mechanisms described in Appendix B.

### 6.4 OWASP and Industry Guidance

**OWASP Top 10 for LLM Applications (2025)** addresses threats *to* LLM systems — prompt injection, training data poisoning, model denial of service, insecure output handling. The last category ("Insecure Output Handling") comes closest to the concerns in this paper, but it addresses LLM output used as *data* (e.g., inserting LLM-generated text into a web page without sanitisation), not LLM output used as *source code* that becomes part of the system itself.

**OWASP Secure Coding Practices** provides a checklist of defensive coding practices. Ironically, several "secure" practices in the OWASP checklist are precisely the anti-patterns that the agentic threat model identifies as dangerous in high-assurance contexts. For example, "validate all input" is correct, but "provide a default value when input is missing" is context-dependent — in audit-critical systems, a missing value should crash, not default. This illustrates the gap between generic secure coding guidance and domain-specific trust boundary requirements.

**MITRE ATT&CK and CWE** provide taxonomies for attack techniques and code weaknesses respectively. The agentic code failure modes in Appendix A do not map cleanly to existing CWE entries because they are not individual weaknesses — they are *patterns* that are correct in most contexts and dangerous in specific ones. A `.get()` with a default value is not a weakness; it is a weakness *when applied to audit-critical data in a system that requires crash-on-corruption*. Context-dependent weaknesses are not well-served by context-free taxonomies.

### 6.5 The Gap Between "Securing AI" and "Securing What AI Builds"

Across all current frameworks, there is a consistent structural gap: substantial guidance exists for securing AI systems themselves (the model, the training pipeline, the inference infrastructure), but almost no guidance exists for securing systems that AI systems build or modify.

This gap is not surprising — agentic coding is a recent capability and guidance takes time to develop. But the gap is widening faster than it is closing, because:
- Agent adoption is accelerating (driven by generation velocity gains and expanded capability — Section 1.2, Section 8)
- The failure modes are subtle (they pass all existing automated checks — Section 2.2)
- The vocabulary for discussing these failures doesn't exist yet in policy contexts (this paper's taxonomy is a first attempt)

### 6.6 Summary of Gaps

No current framework provides:
1. **A taxonomy of agentic code failure modes** grounded in established threat modelling (STRIDE or equivalent)
2. **Controls for semantic correctness** beyond syntactic and functional correctness — trust boundary maintenance, audit trail integrity, context-appropriate error handling
3. **Controls for review effectiveness at scale** — not just "is code reviewed?" but "does the review process remain effective at agent-generated volume?"
4. **Trust classification for agent output** — how should agent-generated code be treated in the system's trust model?
5. **Accreditation criteria for agentic development workflows** — what evidence must organisations provide to demonstrate that agentic coding maintains the required security posture?
6. **Vocabulary for context-dependent code weaknesses** — patterns that are correct in general but dangerous in specific security contexts
7. **Correlated failure risk models** — testing and remediation strategies that account for the non-independent failure distribution of agent-generated code

---

## 7. The Response Landscape

The responses available to organisations fall into three categories of increasing assurance strength:

| Control Type | Mechanism | Strength | Example |
|-------------|-----------|----------|---------|
| **Behavioural** | Relies on individual compliance | Weakest — requires sustained restraint against incentives | "Developers should not run more than one agent concurrently" |
| **Procedural** | Relies on organisational process | Moderate — requires consistent enforcement and audit | "Parallel agent-generated changes require separate review queues and staged approval" |
| **Technical** | Constrains the environment | Strongest — operates regardless of individual behaviour | "The CI/CD pipeline enforces concurrency limits, sequencing rules, or protected-branch gates for agent-originated changes" |

Most organisations will implement behavioural controls, aspire to procedural controls, and underinvest in technical controls — because technical controls constrain the velocity that motivated adoption. The key insight from security engineering applies here: **controls that shape the environment are stronger than controls that depend on restraint.** A rule that developers must not bypass review is an aspiration; a pipeline that physically prevents unreviewed code from reaching protected branches is a control.

The sections below are ordered from weakest to strongest assurance, not from least to most important. All three have a role, but assurance should not rest primarily on behavioural or procedural controls where technical enforcement is feasible. Organisations that rely on behavioural and procedural controls without technical enforcement should understand that their assurance argument rests on sustained human compliance with rules that run directly against the productivity incentive that makes agentic development attractive.

### 7.1 Process Controls (Strengthening Existing Practices)

**What government already does, adapted for agentic velocity:**

**Enhanced code review protocols.** Mandate security-focused review (not just correctness review) for agent-generated code. Require reviewers to attest that trust boundaries were verified, not just that the code "looks right." This is a process change, not a technology change, but it requires explicit recognition that agent code needs different review criteria than human code.

Specifically, review checklists for agent-generated code should include:
- Were trust boundaries maintained? (Does external data pass through validation before internal use?)
- Are error handlers audit-preserving? (Do `except` blocks propagate to the audit system, or swallow and continue?)
- Are default values justified? (Does every `.get()` or `getattr` with a default represent a legitimate design decision, or a fabrication of missing data?)
- Is the code's failure mode correct for the context? (Should this code crash, quarantine, or continue on error?)

**Separation of generation and review.** The person (or agent) who generates the code must not be the sole reviewer. This already applies to human-authored code in most government contexts; extending it to agent-generated code means ensuring that agent self-review (e.g., an agent checking its own output) does not count as an independent review. This has a subtlety: multi-agent workflows where one agent generates code and another reviews it are also not independent review — both agents share the same training data biases and failure modes.

**Volume-aware review capacity planning.** If agents increase code generation by 10x, review capacity must be addressed — either through additional reviewers, automated pre-screening that reduces the human review burden, or rate-limiting agent output to match review capacity. Ignoring the volume mismatch means the review control degrades silently.

**Provenance tracking for agent output.** Organisations should maintain records of which code was generated by agents, which was human-authored, and which was agent-generated then human-modified. This metadata is relevant for both security assessment (understanding the trust profile of different code regions) and for incident response (when a defect is found, knowing whether it originated from agent generation helps diagnose the failure mode).

### 7.2 Technical Controls (What's Buildable)

**Automated semantic boundary enforcement.** Static analysis tools that verify data provenance and trust tier flow — not just type shape — at the code level. These tools check that external data passes through validation boundaries before reaching internal processing, that error handling preserves audit trails, and that defensive patterns are not used on data that should crash on anomaly.

**Technical feasibility finding:** A proof-of-concept semantic boundary enforcer for Python has been designed (see Appendix B) with the following properties:
- Zero external dependencies (uses only Python's standard library AST module)
- Works with standard Python — no language modifications, no runtime dependencies
- Produces findings in SARIF format (industry standard for static analysis results)
- Can operate as a pre-commit check, CI gate, or agent self-check before code submission
- Verification properties (golden corpus, self-hosting gate, measured precision) are independently auditable — see Appendix B, Section B.5

This is not the only possible technical control, but it demonstrates that the problem is tractable. Similar tools could be built for other languages or integrated into existing static analysis platforms.

**Key architectural principle — "parasitic, not parallel":** Effective tools for this space must extend existing programming language machinery (annotations, type hints, decorators) rather than creating parallel systems that require adoption of new syntax or tools. Tools that require developers to learn a new language or adopt a new framework face adoption resistance that undermines their security value. Critically, enforcement must live inside the existing CI/CD pipeline — pre-commit hooks, CI gates, pull request checks — not in a separate workflow. If a security tool slows down the very velocity the organisation bought the AI agent to achieve, the tool will be bypassed. The enforcement mechanism succeeds by being invisible to the fast path and blocking only on genuine violations.

### 7.3 Policy Controls (What Doesn't Exist Yet)

**Standardised vocabulary.** The taxonomy in this paper (Section 3 and Appendix A) provides a starting point. Government cybersecurity guidance needs terminology for agentic code failure modes — "competence spoofing," "trust tier conflation," "audit trail destruction through defensive patterns" — that practitioners can use in security assessments, risk registers, and accreditation documentation.

**Accreditation criteria for agentic development workflows.** IRAP assessments and similar accreditation processes need criteria for evaluating whether an organisation's use of AI coding agents maintains the security posture required by the system's classification. This includes:
- How agent output is validated before integration
- How review effectiveness is maintained under volume pressure
- How trust boundaries are verified in agent-generated code
- What attestation is required from human reviewers

**Agent output classification.** A formal determination of how agent-generated code should be treated in the trust model — as external input (Tier 3), as tool output (requiring specific validation), or as a new category requiring its own controls.

---

## 8. Case Study: Agentic Development Under Compliance Constraints

*This section presents a composite, de-identified account drawn from experience with agentic development in compliance-constrained environments. Specific implementation details have been generalised.*

### 8.1 Context

An engineering team developing an auditable data processing platform — a system where every decision must be traceable to its source data, configuration, and code version. The system processes sensitive data under compliance requirements that mandate complete audit trails, data integrity verification, and defence-in-depth security controls.

The team adopted AI coding agents as a primary development tool, with agents generating the majority of new code. The codebase enforces strict architectural rules: a tiered trust model for data handling, mandatory crash-on-corruption for internal data, quarantine-and-continue for external data, and no defensive programming patterns (no `.get()` on typed objects, no bare `except`, no silent error swallowing).

These rules are documented extensively but are **institutional knowledge** — they exist in project documentation, not in the programming language. Python permits all of the patterns the project forbids.

### 8.2 The Compliance Tax

Compliance requirements impose substantial overhead on the development workflow:

**Hash integrity verification.** Every data operation produces cryptographic hashes for audit trail integrity. Changes to hashing logic, serialisation formats, or data structures require recompilation and verification of hash chains. This is mechanical work that agents handle well, but the *verification* that the agent produced correct hashes requires human review — or automated checking.

**Audit trail completeness.** Every code path must produce audit records. Missing audit records are treated as evidence tampering, not as bugs. This means error handlers cannot swallow exceptions, partial operations must roll back, and "log and continue" is not an acceptable failure mode. Agents consistently produce error handlers that violate these requirements because their training data overwhelmingly models "log and continue" as best practice.

**Trust boundary enforcement.** The team maintains a static analysis tool (manually built, project-specific) that detects defensive coding patterns in contexts where crash-on-corruption is required. This tool has an allowlist mechanism for legitimate exceptions. Maintaining the allowlist, reviewing new findings, and ensuring agents don't introduce violations that the tool doesn't yet detect is a recurring cost.

**The overhead is real — the team estimates the aggregate compliance overhead at 15-25% of total development time** — but its distribution is uneven and reveals something about how agents experience unfamiliar workflows. On large changes (new features, multi-file refactors), compliance overhead is trivially small relative to the work — even if the agent spends 10 minutes recalculating 500 allowlist hashes after a major refactor, that is a reasonable investment against hours of productive generation. But on small changes, the ratio inverts dramatically. An agent fixing a one-line bug spends 30 seconds on the fix and 60 seconds grappling with the CI pipeline: discovering that an enforcement gate is blocking the commit, parsing the error to understand what the tool expects, calculating a new allowlist hash, and editing the configuration. The compliance work takes twice as long as the actual work. The agent still completes the entire cycle faster than a human would, but the unfamiliar workflow — one the agent has never seen in training data and must rediscover each session — imposes an outsized cost on small tasks, and this skew toward small-change cases is where the bulk of the overhead concentrates.

This is not new overhead introduced by agentic coding. It is the *same compliance overhead* that existed before agents, redistributed. Before agents, humans spent that time writing compliant code slowly. With agents, humans spend it reviewing agent code for compliance quickly. The total compliance cost is similar; the development velocity is dramatically higher.

### 8.3 Productivity Gains Despite Friction

Despite the compliance overhead, the team reports substantial productivity gains from agentic coding:

- **Mechanical refactoring** (renaming, restructuring, pattern application across files) is handled almost entirely by agents. This work is tedious for humans but trivial for agents, and the compliance requirements don't make it harder — the agent produces the refactoring, the existing test suite and CI pipeline verify it.
- **Boilerplate generation** (new plugins, test scaffolding, configuration structures) is dramatically accelerated. The agent follows the project's existing patterns, and the structural correctness is verifiable by tests.
- **Bug investigation and test writing** benefit from agents' ability to rapidly explore code paths and generate test cases. The agent's lack of institutional knowledge is less of a liability when the task is "write a test that exercises this code path" rather than "write code that maintains trust boundaries."

The pattern is clear: **agents excel at tasks where correctness is structurally verifiable** (tests pass, types check, linter is clean) and struggle at tasks where **correctness requires institutional knowledge** (trust boundary maintenance, audit trail completeness, appropriate error handling in compliance contexts).

### 8.4 Where the Current Process Fails

The team has observed agent-generated code of questionable quality passing human review. In each case, the code was:
- Syntactically correct
- Consistent with project conventions
- Passing all existing tests
- Semantically wrong in the compliance context

The failure modes map directly to the taxonomy in Section 3:

**Competence spoofing (ACF-S1).** Agent generates `.get()` with a default value on a data structure that should crash on missing fields. The code appears defensive and robust. A reviewer under time pressure sees "handles the missing case" rather than "fabricates data where absence should crash."

**Audit trail destruction (ACF-R1).** Agent wraps an audit-critical operation in a `try/except` that logs the error and continues. The code appears to handle errors gracefully. The reviewer doesn't recognise that the caught exception should propagate to the audit system rather than being logged and swallowed.

**Trust tier conflation (ACF-T1).** Agent deserialises data from an external API and passes it directly to an internal processing function. The code appears clean — no obvious security issues. The reviewer doesn't see the missing validation boundary because both the external data and internal data are the same Python type (`dict`).

In each case, the defect was caught later — by the project's existing static analysis tool, by a different reviewer examining adjacent code, or by a test failure in a downstream component that received malformed data. The initial review process, which was supposed to catch these issues, had signed off.

### 8.5 The Redirection Insight

The team's experience reveals that automated semantic enforcement doesn't *add* tedium — it **redirects existing tedium** toward higher-value activities.

Without automated enforcement, humans manually review every agent output for trust boundary violations. This is:
- **Error-prone:** The failure modes look like correct code (Section 3)
- **Fatigue-inducing:** Reviewing dozens of agent-generated functions per day for subtle semantic violations degrades review quality (Section 4.2)
- **Unscalable:** As agent velocity increases, review capacity doesn't

With automated enforcement, the machine catches structural trust boundary violations (unterminated taint paths, defensive patterns on typed objects, missing validation boundaries). Humans focus on **semantic issues that require institutional knowledge** — whether the trust topology is correctly declared, whether the validation logic is actually correct (not just structurally present), whether the audit trail captures the right information.

This is a genuine improvement in security posture, not just efficiency:

| Review Focus | Without Automation | With Automation |
|-------------|-------------------|-----------------|
| "Is `.get()` used on typed objects?" | Human scans for pattern (error-prone) | Machine catches structurally (reliable) |
| "Does this error handler preserve the audit trail?" | Human evaluates (moderate difficulty) | Machine flags broad `except` blocks; human evaluates the specific cases |
| "Is the trust topology correctly declared for this new module?" | Human evaluates (requires institutional knowledge) | Human evaluates (no change — this is irreducibly human) |
| "Is this validation function actually validating?" | Human evaluates (requires domain knowledge) | Machine checks structural presence of control flow; human evaluates semantic adequacy |

The total review burden may be similar, but the **distribution of human attention shifts** from low-value pattern scanning to high-value semantic evaluation. The compliance tax is the same; the assurance yield is higher.

---

## 9. Open Questions for the Community

This paper does not attempt to answer these questions definitively. They are posed for discussion and community input.

### 9.1 Trust Classification

**Should agent-generated code be treated as a distinct trust tier in security assessments?**

The Tier 3 (external/untrusted) classification proposed in Section 5 is a starting point, but it may be too coarse. Agent code that has been reviewed and modified by a human developer exists in an intermediate state — it originated externally but has been validated. Does this validation elevate it to Tier 2? What constitutes sufficient validation?

A related question: does the trust classification of agent code change over time? Code generated by an agent 12 months ago that has been in production, passed multiple review cycles, and survived real-world use arguably has a different trust profile than code generated 5 minutes ago. Should the trust tier be static (based on origin) or dynamic (based on accumulated evidence)?

### 9.2 Accreditation Burden

**What is the appropriate accreditation burden for organisations using agentic coding in PROTECTED or higher systems?**

Current IRAP assessment criteria do not specifically address AI code generation. Should they? If so, what evidence should an organisation provide to demonstrate that its use of agents maintains the required security posture?

Candidate evidence requirements (for discussion):
- Demonstration that agent output passes through a defined validation boundary (Section 5.3)
- Measured review effectiveness metrics (not just "we have a review process" but "here is evidence the process catches the failure modes in Appendix A")
- Provenance records showing which code was agent-generated (Section 7.1)
- Evidence that automated semantic enforcement tools are in use and their precision is measured (Appendix B, Section B.5)

Must the validation boundary itself be assessed? If an organisation builds or adopts automated enforcement tooling, does that tooling become part of the assessed system?

### 9.3 Static vs. Runtime Assurance

**Can static analysis tools provide sufficient assurance for agent-generated code, or is runtime verification necessary?**

Static analysis can detect structural patterns (Section 7.2) but cannot verify semantic correctness in all cases. Runtime verification (monitoring trust tier flow at execution time) provides stronger guarantees but introduces performance overhead and operational complexity. Where is the appropriate trade-off for government systems?

The design work in Appendix B suggests a middle ground: static analysis as the primary enforcement mechanism with narrow runtime verification in test mode only — calibrating the static analyzer's coverage without introducing production runtime dependencies. Whether this trade-off is acceptable for a given classification level is a policy question, not a technical one.

### 9.4 Review Quality Measurement

**How do you measure the effectiveness of human review when the volume of agent output makes comprehensive review impractical?**

Current accreditation processes assume that code review provides a certain level of assurance. If review quality degrades under volume pressure (Section 4), the assurance claim is no longer valid. How should organisations measure and demonstrate that their review process remains effective?

Possible metrics (all have limitations):
- **Defect escape rate:** How many agent-introduced defects are found post-review? Requires knowing the total defect count, which requires a detection mechanism independent of the review process.
- **Review depth sampling:** Periodically audit review decisions for thoroughness. Resource-intensive but directly measures quality.
- **Automated pre-screening coverage:** What percentage of the failure modes in Appendix A are caught by automated tools before reaching human review? This doesn't measure review quality directly but measures how much the review process is being supplemented.
- **Time-per-change metrics:** Review duration per lines changed. A leading indicator — if review time per change is declining while change volume increases, review quality is likely degrading.

### 9.5 Agent Self-Regulation

**Should agents be required to self-check their output against security rules before submitting it?**

Many agent workflows already include self-checking loops — agents run linters, type checkers, and test suites against their own output before submission, often triggered by pre-commit hooks or CI integration. This is current practice, not a future possibility. The question is whether this practice should be *required* and whether it should extend to semantic security checks.

Pre-generation self-checking (where the agent validates its own output against security rules before submission) closes the feedback loop at the point of maximum leverage — before the code enters the repository. This is technically feasible (Appendix B describes a `--stdin` mode for exactly this purpose).

But current practice and the proposal both raise questions:
- Does self-checking constitute validation, or must validation be independent? The agent checking its own output against structural rules is different from the agent evaluating whether its output is semantically correct — the first is a mechanical verification, the second is the same judgment that produced the code.
- Can an agent meaningfully check for the failure modes it is predisposed to produce? If the agent's training data biases it toward `.get()` with defaults, will it also generate code that satisfies a rule against that pattern, or will it generate code that evades the rule while preserving the same semantic flaw?
- If self-checking catches 80% of structural violations before human review, does this improve or degrade human review quality? It might improve it (reviewers focus on harder problems) or degrade it (reviewers assume the pre-check caught everything and reduce scrutiny).

### 9.6 Cross-Organisational Standards

**Should there be a common agentic code security standard across Australian Government?**

Individual organisations developing their own agentic code policies will produce inconsistent and potentially conflicting approaches. A common standard — even a lightweight one — would provide:
- A shared vocabulary for discussing agentic code risks (the taxonomy in Appendix A is a candidate starting point)
- A minimum bar for controls that all agencies using agentic coding must implement
- A basis for mutual recognition of agentic development practices across agencies
- Consistency in IRAP assessment criteria for agentic workflows

The counterargument: standardisation too early may lock in controls that prove inappropriate as the technology evolves rapidly. A vocabulary standard and minimum control set may be more durable than detailed prescriptive requirements.

### 9.7 The Correlated Failure Problem

**How should risk models account for correlated failures in agent-generated code?**

Traditional software risk models assume that defects are approximately independent — a bug in one function doesn't predict a bug in another. Agent-generated code violates this assumption (Section 2.4). A single training data bias produces the same failure mode across every function the agent generates.

This has implications for:
- **Testing strategy:** Independent sampling (testing a random subset of functions) underestimates defect rates when failures are correlated. If you find a trust boundary violation in one agent-generated function, the probability that the same violation exists in other agent-generated functions is much higher than if a human had written them.
- **Risk assessment:** The risk of a single agent-generated defect may be low, but the risk of a *systematic* defect affecting dozens or hundreds of functions is qualitatively different. How should risk registers capture correlated agent failure risk?
- **Remediation scope:** When a defect pattern is found in agent code, remediation should not be limited to the specific instance. The entire codebase should be scanned for the same pattern — because correlated failures mean the pattern is likely repeated.
- **Triage model:** Correlated failures mean 50 firings of the same rule across a codebase is one systematic issue requiring a systematic fix, not 50 independent tickets. Organisations that triage agent-generated defects as independent findings will overwhelm their remediation capacity on what is, operationally, a single root cause.

---

## 10. Recommendations

### 10.1 For Security Policy Bodies (ASD, ACSC)

1. **Develop a taxonomy of agentic code failure modes** based on established frameworks (STRIDE or equivalent). This paper's taxonomy (Appendix A) is a starting point, not a final product. The taxonomy should be developed in consultation with organisations that are already using agentic coding in assessed systems, to ground it in observed failure modes rather than theoretical concerns.

2. **Issue guidance on treating agent output as a trust boundary.** Clarify how agent-generated code should be classified in the trust model and what validation is required before integration into assessed systems. At minimum, guidance should address:
   - Whether agent-generated code requires different review criteria than human-authored code
   - Whether organisations must track which code was agent-generated (provenance)
   - What constitutes "sufficient validation" at the agent output boundary

3. **Extend ISM controls for software development** to address the distinct risk profile of agent-generated code. The June 2025 ISM overhaul added strong foundations (ISM-2060/2061 for code review, ISM-0402 for comprehensive testing, ISM-2026–2028 for artefact integrity), but these controls assume human-paced development. Candidate extensions:
   - ISM-0401 (Secure by Design): Require that Secure by Design practices include machine-enforceable rules when AI agents are used, since agents cannot internalise design principles from documentation.
   - ISM-2060/2061 (code review / security-focused peer review): Address review capacity scaling and the habituation effect under agent-volume code generation. Consider requiring measured review effectiveness, not just documented process.
   - ISM-0402 (testing with SAST/DAST/SCA): Extend SAST requirements to include semantic boundary analysis — trust tier flow verification, defensive pattern detection in audit-critical contexts — beyond current known-vulnerability-pattern scanning.
   - ISM-2026–2028 (artefact integrity): Extend supply chain controls to cover agent-generated first-party code as a supply chain input with distinct risk properties (correlated failures, no persistent learning).
   - New control: Require organisations using agentic coding to demonstrate that their review and validation processes remain effective under the volume of agent-generated code they produce.

4. **Commission research into automated semantic boundary enforcement** as a complementary control to human review. The technical feasibility finding (Appendix B) suggests this is tractable — the core analysis uses only Python's standard library AST module and the verification properties are independently auditable (Section B.5). Research priorities:
   - Validate the feasibility finding against a broader set of codebases and programming languages
   - Evaluate whether automated enforcement meaningfully reduces defect escape rates in practice
   - Develop criteria for assessing the assurance properties of enforcement tools themselves (Appendix B, Section B.5)

### 10.2 For IRAP Assessors

5. **Include agentic development practices in assessment scope** when organisations use AI coding agents in assessed systems. Evaluate:
   - The validation boundary between agent output and code integration (Section 5.3)
   - Evidence of review effectiveness under volume, not just existence of review process
   - Provenance tracking for agent-generated code
   - Whether the organisation has identified and addressed the failure modes relevant to their system's classification and data sensitivity

6. **Assess review quality, not just review process.** A documented code review process that is overwhelmed by volume provides less assurance than a smaller, more thorough review supported by automated pre-screening. Ask for evidence: defect escape rates, review depth audits, or automated pre-screening coverage metrics (Section 9.4).

7. **Consider correlated failure risk.** Traditional defect models assume independent failures. Agent-generated code produces correlated failures (Section 9.7). When assessing test coverage and defect rates, verify that the organisation's testing strategy accounts for correlation — finding one instance of a failure pattern should trigger codebase-wide scanning for the same pattern.

### 10.3 For Organisations Using Agentic Coding

8. **Treat agent-generated code as external input** requiring validation at the boundary. Do not assume agent output is correct because it passes tests and follows conventions. The failure modes in Appendix A are specifically designed to pass tests and look correct — that is what makes them dangerous.

9. **Document your institutional security knowledge in machine-readable form.** The gap between "what Python permits" and "what our system requires" is institutional knowledge that currently lives in documentation, team culture, and individual expertise. Encoding it in machine-checkable rules — whether through a purpose-built tool (Appendix B), project-specific linter rules, or structured review checklists — is the most direct defence against agents that don't share that knowledge.

10. **Invest in automated semantic boundary enforcement** as a complement to human review. The human review budget is finite; automated tools that handle structural trust boundary violations free human reviewers to focus on semantic issues that require institutional knowledge. The case study (Section 8.5) demonstrates that this is a redirection of existing effort, not additional overhead.

11. **Measure and monitor review effectiveness** under agentic volume. If review quality is degrading, address it — through tooling, capacity, or rate-limiting — before it becomes a compliance gap. Don't wait for an incident to discover that the review process is no longer providing the assurance it claims.

12. **When an agent-generated defect is found, scan for the pattern, not just the instance.** Correlated failures mean the same defect likely exists in other agent-generated code. Treating each defect as isolated underestimates the actual risk.

13. **Contribute to the community vocabulary.** Document your organisation's experience with agentic code failure modes and share (at an appropriate classification) to build the collective understanding. The taxonomy in this paper was developed from a single project's experience; it needs validation and extension from diverse government contexts.

---

## Appendix A: Agentic Code Failure Taxonomy

A structured catalogue of failure modes, mapped to STRIDE categories, with detection characteristics, code examples, and risk ratings. Each entry includes the *reason agents produce this pattern* — understanding why helps calibrate both detection tools and review processes.

### Summary Table

| ID | Name | STRIDE | Risk | Existing Detection |
|----|------|--------|------|-------------------|
| ACF-S1 | Competence spoofing | Spoofing | High | None |
| ACF-S2 | Hallucinated field access | Spoofing | High | Partial |
| ACF-T1 | Trust tier conflation | Tampering | Critical | None |
| ACF-T2 | Silent coercion | Tampering | Medium | None |
| ACF-R1 | Audit trail destruction | Repudiation | High | Partial |
| ACF-R2 | Partial completion | Repudiation | High | None |
| ACF-I1 | Verbose error response | Info Disclosure | Medium | Partial |
| ACF-I2 | Stack trace exposure | Info Disclosure | Low | Good |
| ACF-D1 | Finding flood | DoS | High | N/A |
| ACF-D2 | Review capacity exhaustion | DoS | High | N/A |
| ACF-E1 | Implicit privilege grant | Elevation | Critical | None |
| ACF-E2 | Unvalidated delegation | Elevation | High | Partial |

### Detailed Entries

*Policy readers: the Summary Table above and the Detection Capability Summary at the end of this appendix provide a complete overview without requiring code fluency. The detailed entries below, which include Python code examples, are provided for technical practitioners, tool builders, and organisations implementing detection capabilities. Non-Python readers may rely on the Description, Why it's dangerous, and Detection approach fields for each entry.*

#### ACF-S1: Competence Spoofing

**STRIDE:** Spoofing | **Risk:** High | **Detection:** None

**Description:** Default values fabricate data where the absence of data should be surfaced as a failure, error, or explicit "unknown." The code presents a confident result that is actually based on fabricated input.

**Why agents produce this:** The `.get(key, default)` pattern appears in millions of Python files. In most contexts, providing a default for missing keys is genuinely good practice — a web application displaying "Unknown" for a missing user name is fine. Agents learn this as a universal pattern and apply it in contexts where the default fabricates safety-critical data.

**Example:**
```python
# Agent-generated — looks defensive and robust
def assess_risk_level(record):
    classification = record.get("security_classification", "OFFICIAL")
    clearance = record.get("required_clearance", "baseline")
    return classification, clearance

# Correct for high-assurance context — absence is a failure
def assess_risk_level(record):
    classification = record["security_classification"]  # KeyError = data integrity failure
    clearance = record["required_clearance"]            # Missing = investigate, don't assume
    return classification, clearance
```

**Why it's dangerous:** The first version silently downgrades security classifications when data is missing. A PROTECTED document with a corrupted or missing `security_classification` field is treated as OFFICIAL. Downstream access control decisions are based on the fabricated classification.

**Detection approach:** Flag `.get()` and `getattr()` with defaults on objects whose type is annotated with a trust tier of Tier 1 (internal/audit) or Tier 2 (validated pipeline data). Requires trust tier annotations (not available in existing tools).

---

#### ACF-S2: Hallucinated Field Access

**STRIDE:** Spoofing | **Risk:** High | **Detection:** Partial

**Description:** Agent accesses a field name that doesn't exist on the target object, masked by `getattr()` with a default. The code operates on fabricated data while appearing to access a real field.

**Why agents produce this:** Agents occasionally hallucinate field names — predicting a plausible field name that doesn't exist in the actual schema. Without `getattr`, this produces an immediate `AttributeError`. With `getattr(obj, "hallucinated_field", None)`, the error is silently suppressed and the code operates on `None` (or whatever default is provided).

**Example:**
```python
# Agent hallucinated "risk_score" — actual field is "risk_rating"
threshold = getattr(assessment, "risk_score", 0)
if threshold > 5:
    escalate(assessment)
# risk_score is always 0 (the default), so nothing is ever escalated.
# The code looks correct. Tests pass (they test the escalation path with explicit values).
# The bug is invisible until someone notices that escalation never triggers.
```

**Why it's dangerous:** The code silently does nothing instead of crashing. In a security context, "nothing happens" can mean "threats are not escalated" or "alerts are not raised" — failures of omission that are harder to detect than failures of commission.

**Detection approach:** Type checkers (mypy, pyright) catch this *if the object is fully annotated*. If the object is `Any` or untyped, type checkers are silent. The semantic boundary enforcer (Appendix B) adds a complementary rule: `getattr` with a default on any object that has a declared type annotation is flagged, because the annotation means the field set is known and access should be direct.

---

#### ACF-T1: Trust Tier Conflation

**STRIDE:** Tampering | **Risk:** Critical | **Detection:** None

**Description:** Data from an external (untrusted) source is used in an internal (trusted) context without passing through a validation boundary. The data's effective trust level is silently elevated.

**Why agents produce this:** Python's type system doesn't distinguish between data from different sources. A `dict` from `requests.get().json()` and a `dict` from a validated internal query are the same type. Agents see both as "a dict" and treat them interchangeably because nothing in the language tells them otherwise.

**Example:**
```python
# Agent-generated — clean, readable, catastrophically wrong
def sync_partner_records(partner_api_url):
    response = requests.get(f"{partner_api_url}/records")
    records = response.json()
    for record in records:
        db.execute(
            insert(internal_records).values(**record)
        )
    # External data inserted directly into internal database.
    # No schema validation, no field allowlisting, no type checking.
    # Partner could send arbitrary fields, wrong types, injection payloads.

# Correct — validate at the boundary
def sync_partner_records(partner_api_url):
    response = requests.get(f"{partner_api_url}/records")
    raw_records = response.json()
    for raw in raw_records:
        try:
            validated = PartnerRecordSchema.validate(raw)
        except ValidationError as e:
            quarantine(raw, reason=str(e))
            continue
        db.execute(
            insert(internal_records).values(
                name=validated.name,
                status=validated.status,
            )
        )
```

**Why it's dangerous:** This is the most critical failure mode because it compromises the integrity of the internal data store — the system's source of truth. Once external data enters the internal store without validation, every downstream consumer trusts it as internal data. Corruption propagates invisibly.

**Detection approach:** Taint analysis — trace the return values of functions marked `@external_boundary` (or matched by the known external call heuristic list) and flag if they reach data store operations without passing through a function marked `@validates_external`. This is the core capability of the tool described in Appendix B.

---

#### ACF-T2: Silent Coercion

**STRIDE:** Tampering | **Risk:** Medium | **Detection:** None

**Description:** Type coercion across trust boundaries hides data quality issues. Values are silently converted to a compatible type rather than being flagged as invalid.

**Why agents produce this:** Python's `or` operator and conditional expressions make coercion easy and idiomatic. `value = input_value or "default"` is a common pattern. Agents apply it broadly without distinguishing between contexts where coercion is appropriate (Tier 3 → Tier 2 at a validated boundary) and contexts where it's dangerous (Tier 1 internal data that should never need coercion).

**Example:**
```python
# Silent coercion hides data quality problem
amount = float(row.get("transaction_amount", 0))
# Missing transaction amount is silently zero — not "unknown" or "error."
# A zero-value transaction passes every downstream check.
# An audit query for "transactions over $1000" won't find it,
# but neither will "transactions with missing amounts."

# Better — make the absence explicit
if "transaction_amount" not in row:
    return TransformResult.error({"reason": "missing_amount", "row_id": row_id})
amount = float(row["transaction_amount"])
```

**Detection approach:** Flag coercion patterns (`.get()` with non-None defaults, `or` chains with fallback values, ternary expressions with defaults) on fields from Tier 1 or Tier 2 data. The distinction from ACF-S1 is that this involves type conversion, not just default substitution.

---

#### ACF-R1: Audit Trail Destruction

**STRIDE:** Repudiation | **Risk:** High | **Detection:** Partial

**Description:** Broad exception handlers catch errors from audit-critical operations and log-and-continue rather than propagating the failure to the audit system.

**Why agents produce this:** "Catch exceptions and log them" is a pervasive pattern in training data. In most applications, it's reasonable — a web server should log errors and keep serving. Agents apply this pattern to audit-critical operations without recognising that some failures must propagate rather than be absorbed.

**Example:**
```python
# Agent-generated — looks like responsible error handling
try:
    record_decision(case_id, decision, rationale, evidence)
except Exception as e:
    logger.error(f"Failed to record decision for {case_id}: {e}")
    # Decision was made. Decision was not recorded.
    # The audit trail now has a gap that cannot be reconstructed.
    # The log message may be rotated away. The decision stands, unrecorded.
```

**Why it's dangerous:** In regulatory contexts, the audit trail is the legal record. A gap in the audit trail is not just a logging failure — it's a compliance failure that may have legal consequences. "We made a decision but can't prove what it was based on" is an unacceptable answer in a formal inquiry.

**Detection approach:** Existing linters flag bare `except:` (no exception type) but not `except Exception:` (which is considered acceptable practice). Semantic detection requires understanding which operations are audit-critical — this is project-specific knowledge encoded in the trust topology (e.g., functions annotated as audit-write operations should not be inside broad exception handlers that continue on failure).

---

#### ACF-R2: Partial Completion

**STRIDE:** Repudiation | **Risk:** High | **Detection:** None

**Description:** A sequence of operations that should be atomic (all-or-nothing) is implemented without rollback, so partial failure leaves the system in an inconsistent state.

**Why agents produce this:** Agents implement operations sequentially and add error handling per-step. They don't naturally recognise that a group of operations should be treated as a transaction unless explicitly prompted. The concept of "these three operations must all succeed or all fail" is a design decision, not a language feature.

**Example:**
```python
# Agent-generated — each step has error handling, but no atomicity
def reclassify_document(doc_id, new_classification):
    update_classification(doc_id, new_classification)  # Step 1: succeeds
    notify_stakeholders(doc_id, new_classification)     # Step 2: fails (network error)
    record_reclassification(doc_id, old, new)           # Step 3: never runs
    # Document is reclassified, stakeholders don't know, audit trail is incomplete.
    # If step 2 is wrapped in try/except and continues, step 3 records a
    # reclassification that stakeholders were never notified about.
```

**Detection approach:** No existing tool detects this — it requires understanding which operations form a logical transaction. A semantic boundary enforcer could flag functions that contain multiple audit-write operations without a transaction context, but this requires project-specific annotation of which operations are audit-critical.

---

#### ACF-I1: Verbose Error Response

**STRIDE:** Information Disclosure | **Risk:** Medium | **Detection:** Partial

**Description:** Error handlers expose internal system details (database schemas, file paths, query parameters, library versions) in error responses.

**Why agents produce this:** Agents produce "helpful" error messages that include full context. During development, this is valuable. In production, it's reconnaissance information. Agents don't distinguish between development and production error handling because the distinction is contextual, not syntactic.

**Example:**
```python
except DatabaseError as e:
    return {"error": str(e), "query": sql, "connection": str(db_url)}
```

**Detection approach:** Existing scanners detect some cases (credential patterns, known sensitive variable names). Comprehensive detection requires understanding which variables contain sensitive information — a context-dependent judgment.

---

#### ACF-I2: Stack Trace Exposure

**STRIDE:** Information Disclosure | **Risk:** Low | **Detection:** Good

*Note: This entry is included for taxonomy completeness. It is well-covered by existing tooling and is lower risk than other entries. It could reasonably be treated as a sub-variant of ACF-I1.*

**Description:** Full Python tracebacks returned in API responses or user-facing error messages.

**Why agents produce this:** `traceback.format_exc()` is a common debugging pattern. Agents include it in error handlers without considering the deployment context.

**Detection approach:** Well-covered by existing tools. Most security scanners and web framework linters detect traceback exposure.

---

#### ACF-D1: Finding Flood

**STRIDE:** Denial of Service | **Risk:** High | **Detection:** N/A (process threat)

**Description:** The volume of static analysis findings on agent-generated code overwhelms reviewers, causing them to rubber-stamp findings without evaluation.

**Why this happens:** Agents produce code at volume, and if that code triggers many findings, the review queue grows faster than the review capacity. Reviewers under volume pressure shift from evaluating each finding to batch-dismissing them. The DoS is against the *review process*, not the system.

**Mitigation:** Finding caps per rule per file (Appendix B), prioritised finding presentation (critical first), and measured suppression rates as a health metric.

---

#### ACF-D2: Review Capacity Exhaustion

**STRIDE:** Denial of Service | **Risk:** High | **Detection:** N/A (process threat)

**Description:** Agent code generation velocity exceeds the organisation's capacity for security-focused review, degrading review from active verification to passive scanning.

**Why this happens:** Agents produce code 5-20x faster than humans. Review capacity doesn't scale at the same rate. The review process becomes a bottleneck, and the organisational response is often to lower the review bar rather than reduce the generation rate.

**Mitigation:** Automated pre-screening to reduce the human review burden, volume-aware capacity planning, and measured review effectiveness metrics (Section 9.4).

---

#### ACF-E1: Implicit Privilege Grant

**STRIDE:** Elevation of Privilege | **Risk:** Critical | **Detection:** None

**Description:** External system assertions are accepted without independent verification, granting privileges based on unvalidated claims.

**Why agents produce this:** Agents implement integration patterns by calling external APIs and acting on the response. The concept that the external system's response must be independently verified — that the response itself is untrusted — is not visible in the code structure. The code looks like a normal API call and response handling.

**Example:**
```python
partner_verification = partner_api.verify_identity(applicant_id)
if partner_verification.get("verified", False):
    grant_system_access(applicant_id, level="standard")
# Partner says "verified" → access granted.
# No independent check. No recording of the basis for the decision.
# If the partner system is compromised, every applicant is "verified."
```

**Detection approach:** Taint analysis — the return value of an `@external_boundary` function is used as a predicate in an access control decision without passing through validation. Requires both boundary annotation and understanding of which operations are access-control-relevant.

---

#### ACF-E2: Unvalidated Delegation

**STRIDE:** Elevation of Privilege | **Risk:** High | **Detection:** Partial

**Description:** User-supplied parameters are used directly in privileged operations (database queries, file access, system commands) without validation or restriction.

**Why agents produce this:** The pattern `db.query(Model).filter_by(**user_params)` is concise and idiomatic. Agents produce it because it's the shortest path from input to query. The concept that user parameters must be restricted to an allowlist of permitted fields is a security requirement, not a language requirement.

**Example:**
```python
def search_records(user_query: dict):
    return db.query(Record).filter_by(**user_query)
    # User can filter on internal fields: is_deleted, internal_score,
    # admin_notes — fields that should not be queryable.
```

**Detection approach:** SQL injection scanners catch some cases (especially string interpolation into SQL). Parameter delegation via `**kwargs` unpacking into ORM queries is less consistently detected. Semantic detection requires understanding which operations are privileged and which parameters are user-controlled.

---

### Detection Capability Summary

| Detection Level | Count | Failure IDs | Implication |
|----------------|-------|-------------|-------------|
| **None** (no existing tool detects it) | 5 | ACF-S1, ACF-T1, ACF-T2, ACF-R2, ACF-E1 | These require new tooling or new review practices |
| **Partial** (some tools catch some cases) | 4 | ACF-S2, ACF-R1, ACF-I1, ACF-E2 | Existing tools provide incomplete coverage; augmentation needed |
| **Good** (existing tools generally catch it) | 1 | ACF-I2 | Already addressed by current tooling |
| **N/A** (process threat, not code pattern) | 2 | ACF-D1, ACF-D2 | Requires process controls, not technical controls |

This distribution — 5 of 12 failure modes completely undetectable by existing tools, and 4 more only partially detected — is the gap this paper identifies. The 5 undetectable failure modes include both Critical-rated entries (ACF-T1, ACF-E1), meaning the highest-risk failures are precisely the ones that current tooling misses entirely.

---

## Appendix B: Technical Feasibility of Automated Enforcement

### B.1 The Feasibility Question

The threat model in this paper identifies failure modes that existing tools don't detect (Appendix A: 5 of 12 failure modes have no existing tool coverage). The natural question is: can these be detected automatically?

A detailed design for a proof-of-concept tool has been produced through a structured adversarial design process (7 specialist perspectives, 8 rounds of challenge and synthesis). The design demonstrates that automated detection of the most critical agentic code failure modes is technically feasible, buildable at modest cost, and compatible with existing Python development workflows.

### B.2 Core Properties

| Property | Detail |
|----------|--------|
| **Dependencies** | Zero — Python standard library `ast` module only |
| **Language compatibility** | Analyses standard Python; no custom syntax or runtime modifications |
| **Output format** | SARIF (Static Analysis Results Interchange Format) |
| **Delivery** | Standalone PyPI package |
| **Analysis scope** | Intra-function taint analysis (v0.1); inter-procedural deferred to v1.0 |

Note: the relevant measure of this tool is not its implementation size but its **verification properties** — see Section B.5.

### B.3 How It Works

**Declaration.** Developers declare trust boundaries using standard Python annotations and decorators — no custom syntax, no new imports beyond the tool's own library:

```python
@external_boundary          # Returns untrusted data
def fetch_api_data(): ...

@validates_external         # Validates external data (must contain control flow)
def validate_response(): ...
```

A built-in heuristic list recognises common external call sites (`requests.*`, `httpx.*`, `sqlalchemy.*.execute`, `json.loads`, etc.) without requiring explicit annotation — reducing the annotation burden for common patterns while allowing project-specific declarations for uncommon ones.

**Analysis.** The tool performs two-pass analysis:
1. **Symbol collection:** Walks the AST to build a table of annotated boundaries, decorated functions, and known external call sites
2. **Rule evaluation:** Applies trust-relevant rules against the collected symbols, including intra-function taint tracing (flagging values from external boundaries that reach non-validator calls without passing through validation)

**Structural verification.** Functions decorated with `@validates_external` must contain control flow in their body — at least one of `try/except`, `isinstance()`, `raise`, or `if/else`. This prevents agents from satisfying the taint checker by slapping a decorator on a pass-through function.

### B.4 Governance Model

The tool addresses the agent circumvention problem (Section 7 of the threat model) through three mechanisms:

**Project-level manifest.** A `strict.toml` file declares trust topology, boundary functions, rule configuration, and structured exceptions. Exceptions require a rationale, reviewer identity, and expiry date.

**Human-gated governance.** The manifest is protected by repository CODEOWNERS. Ratification of new exceptions must occur in a **separate, prior commit** from the source code changes — CI verifies the temporal separation via git commit history. This prevents agents from simultaneously generating a trust boundary violation and its exception in the same commit.

**Dual enforcement profiles.** Human-authored code follows a graduated promotion protocol (rules start advisory, earn blocking status through measured precision). Agent-authored code defaults to blocking (agents have no cross-session memory, so advisory warnings are useless for them). Rules that prove too noisy on agent code can be demoted via the same human-gated PR workflow.

### B.5 Verification Properties (The Assurance Argument)

For a policy audience, the relevant question about this tool is not "how big is it?" but **"how do you know it's correct?"** This is especially pertinent if the tool is itself built with agent assistance — the tool's own development is subject to the threat model it exists to address.

The design includes four independent verification mechanisms:

**1. Golden corpus.** A collection of labeled Python snippets — true positives (code that should trigger findings) and true negatives (code that should not) — plus adversarial evasion samples (code that looks compliant but isn't). Minimum: 3 true positives + 2 true negatives per rule. The corpus is a first-class artifact, version-controlled, and a ship gate.

**2. Self-hosting gate.** The tool's own source code must pass its own rules in CI from the first commit. If the tool cannot be written to its own standards, the standards are not understood.

**3. Measured precision with volume floor.** Rules track their true positive rate across runs. A rule cannot earn blocking status until it demonstrates >95% precision over a minimum volume of firings (proposed: 50). This prevents promotion based on small samples.

**4. Deterministic output.** Identical input must produce byte-identical output. Verified by running the tool twice and diffing. Non-determinism in a security tool is a defect.

These properties are **independently evaluable by an assessor.** An IRAP assessor (or equivalent) can verify:
- The corpus exists and covers the claimed rules
- The self-hosting gate is enforced in CI
- Precision tracking data is available and shows the claimed rates
- Output is deterministic

This is a stronger assurance argument than "the implementation is N lines" or "the development took M hours." It answers the question *"how do you know the tool catches what it claims to catch?"* with measurable, auditable evidence.

### B.6 Relationship to Existing Tools

| Existing Tool | What It Does | What It Misses | Relationship |
|--------------|-------------|----------------|-------------|
| **mypy/pyright** | Verifies type shape | Data provenance (a `str` from an API and a `str` from a DB are the same type) | Complementary — this tool verifies provenance |
| **ruff/flake8** | Enforces style/idiom | Trust boundary semantics | Complementary — this tool handles trust boundaries; style belongs in ruff |
| **bandit** | Detects known vulnerability patterns | Project-specific trust violations | Complementary — bandit is generic; this tool is project-configured |
| **semgrep** | Custom pattern matching with taint analysis | Promotion governance, manifest-based exception governance, agent-specific enforcement profiles | Closest existing tool — but lacks the governance model |

**Why not extend an existing tool?** The governance model (promotion protocol, dual enforcement profiles, temporal separation of manifest changes) is the differentiating capability. These are not features that can be added to existing tools as plugins — they require control over the finding lifecycle, which existing tools' architectures don't expose. The analysis engine is deliberately simple; the governance model is the novel contribution.

### B.7 The Meta-Observation

If this tool is built with agent assistance — which is the natural development approach given the domain — its own development becomes the first test case for its thesis. If the design specification is tight enough that an agent can implement it, and the self-hosting gate and golden corpus catch the problems the agent introduces, the tool has demonstrated its value proposition through its own creation.

This recursive property is unusual for security tools and is worth noting for the policy audience: **the tool's development process is itself evidence for or against its claims.** An assessor can evaluate not just the tool's output but the conditions under which it was built — did the self-hosting gate catch agent-generated defects? Did the golden corpus reveal false positives or negatives? The development history is part of the assurance argument.

The full design specification is available as a companion document.

---

## References

- Australian Signals Directorate. *Information Security Manual.* Commonwealth of Australia. Updated periodically. https://www.cyber.gov.au/resources-business-and-government/essential-cyber-security/ism — Controls referenced: ISM-0401 (code review), ISM-1419 (secure coding practices), ISM-1620 (automated testing tools), ISM-1804 (software supply chain risk). Individual controls are searchable by number on the ASD website.
- Australian Signals Directorate. *Essential Eight Maturity Model.* Commonwealth of Australia. Updated periodically. https://www.cyber.gov.au/resources-business-and-government/essential-cyber-security/essential-eight
- NIST. *SP 800-218: Secure Software Development Framework (SSDF), Version 1.1.* February 2022. https://csrc.nist.gov/publications/detail/sp/800-218/final
- Microsoft. *The STRIDE Threat Model.* Microsoft Security Development Lifecycle. https://learn.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats
- OASIS. *Static Analysis Results Interchange Format (SARIF), Version 2.1.0.* March 2020. https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html — (Output format referenced in Appendix B)
- OWASP. *Top 10 for LLM Applications.* 2025. https://owasp.org/www-project-top-10-for-large-language-model-applications/
- OWASP. *Secure Coding Practices — Quick Reference Guide.* 2010. https://owasp.org/www-project-secure-coding-practices-quick-reference-guide/
- MITRE. *Common Weakness Enumeration (CWE).* The MITRE Corporation. https://cwe.mitre.org/ — (Taxonomy comparison in Section 6.4)
- Meadows, D. *Thinking in Systems: A Primer.* Chelsea Green Publishing, 2008. (Systems archetypes referenced in Section 4.2)
- Parasuraman, R. & Manzey, D. "Complacency and Bias in Human Use of Automation: An Attentional Integration." *Human Factors*, 52(3), 381-410, 2010. (Automation bias referenced in Section 4.2)
- Graham-Cumming, J. "Incident report on memory leak caused by Cloudflare parser bug." Cloudflare Blog, 23 February 2017. https://blog.cloudflare.com/incident-report-on-memory-leak-caused-by-cloudflare-parser-bug/ — (Precedent referenced in Section 1.2)

---

*This is a discussion paper. It presents a threat model and preliminary analysis, not final guidance. Comments and contributions are welcome.*
