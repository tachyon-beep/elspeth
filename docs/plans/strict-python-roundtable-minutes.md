# Strict Python Roundtable — Minutes

**Date:** 2026-03-07
**Scribe:** Claude (scribe agent)
**Topic:** Building a "strict Python" tool for safer agentic coding

## Context

Exploring a tool/layer that makes Python safer for agentic coding — enforcing trust boundaries, eliminating defensive anti-patterns, catching sloppy typing.

**Hard constraints:**
1. Must stay paired with mainline Python — valid Python in, valid Python out, full ecosystem compatibility
2. Cautious about coupling to any single tool ecosystem (mypy, ruff, etc.)
3. Consider what ELSPETH's CLAUDE.md does manually and what could be automated
4. Go beyond ELSPETH — what else would make agentic/secure Python coding easier?

## Participants

| Role | Agent | Focus |
|------|-------|-------|
| Systems Thinker | yzmir | Causal loops, leverage points, system dynamics |
| Security Architect | ordis | Threat modeling, trust boundaries, security controls |
| Python Engineer | axiom | Python internals, AST, type system, tooling feasibility |
| System Architect | axiom | Tool architecture, where it fits in the toolchain |
| Tech Writer | muna | Proposal framing, documentation, communication |
| SDLC Engineer | axiom | Requirements, quality gates, MVP scoping |
| Quality Engineer | ordis | Testing the tool itself, quality metrics |

---

## Round 1: Opening Positions

### Security Architect (ordis)

**Central thesis:** The core threat isn't malicious code — it's "plausible-but-wrong code at scale." Agents produce code that looks correct, passes tests, and silently violates trust boundaries.

**STRIDE threat analysis applied to agentic code:**
- **Tampering:** Silent coercion across trust tiers (e.g., Tier 1 data quietly coerced instead of crashing)
- **Information Disclosure:** Defensive `.get()` patterns swallowing errors, hiding data integrity failures
- **Elevation of Privilege:** Conflating trust tiers — treating external data with internal-data trust
- **"Spoofing competence"** (novel framing): Hiding hallucinated field names behind `getattr` defaults — code *appears* to work but is operating on fabricated data

**Key insight:** Agent output is itself Tier 3 (untrusted) until verified. This is a meta-trust-boundary. Agents default to defensive patterns because their training data is saturated with `try/except/default`.

**Three proposed control categories:**
1. Trust-tier-aware data flow analysis
2. Anti-pattern detection tuned specifically to agentic failure modes
3. Validation-at-boundary enforcement (validate within N statements of an external call)

**Beyond ELSPETH:**
- State mutation across async boundaries
- Implicit trust escalation through deserialization
- Dependency confusion / typosquatting

**Overarching principle:** "Make the safe thing easy and the unsafe thing loud" — explicit opt-in for trust boundary crossings.

### Systems Thinker (yzmir)

**Central thesis:** The problem is a "Shifting the Burden" archetype — defensive code suppresses the pain signal (crashes) that would drive developers toward correct typing. Each `.get()` that "saves" a crash reinforces the bad pattern.

**System dynamics identified:**
- **"Shifting the Burden":** Defensive patterns are the symptomatic fix that weakens the fundamental fix (proper typing and crash-on-corruption). The longer you rely on `.get()`, the harder it gets to stop.
- **"Limits to Growth":** Shallow tools (ruff, black) win adoption because they operate at low-resistance levels. Deeper tools get labeled "too strict" and abandoned.
- **"Success to the Successful":** Shallow tools absorb adoption energy, starving deeper tools of oxygen. Network effects lock in the shallow solution.

**Leverage point analysis:**
- Highest leverage: **Level 6 — Information Flows.** Make trust violations visible at write time.
- This is NOT a type checker — it's a "trust-flow analyzer." Types tell you *what data is*; trust tiers tell you *how much you should believe it*.

**Survival strategy:** Tool must be "parasitic, not parallel" — extend Python's existing machinery (annotations, decorators) rather than requiring new syntax, custom runtime, or non-standard imports. Stay at Level 6 implementation to avoid the resistance that kills Level 2 (rules/incentives) interventions.

### System Architect (axiom)

**Central thesis:** Architecture should be a standalone AST-based rule engine with thin adapters for multiple emission points. Analysis decoupled from delivery mechanism.

**Architecture proposal:**
1. **AST-only analysis is the survivable foundation** — Python's `ast` module is part of the language spec, changes only when grammar changes. Linter ecosystems reshuffle every few years (pylint → flake8 → ruff).
2. **Type oracle protocol:** For type-aware checks, define an interface that mypy/pyright/future tools can satisfy, rather than importing their internals directly. Decouple from any single type checker.
3. **Per-project rule manifests** (`strict.toml`): Encode trust boundaries and layer rules as machine-readable architectural contracts. Domain-specific, not global.
4. **Thin adapters** for delivery: pre-commit hook, CI check, LSP integration, CLI — all consuming the same core analysis output.

**Generalizable wins (beyond ELSPETH):**
- Trust boundary enforcement
- Layer dependency policing
- Crash-or-handle auditing
- Agentic guardrails (constraining what generated code can do)

### Python Engineer (axiom)

**Central thesis:** Pure AST analysis can catch a substantial class of problems, with runtime enforcement as the complement for what static analysis can't reach.

**Static analysis capabilities (AST-only, stdlib `ast`):**
- `.get()` on dataclasses
- Bare `except:` clauses
- `getattr` with defaults on typed objects
- `json.loads` without `try/except`
- Ceiling: cannot determine types without annotations

**Recommended architecture:**
- Standalone AST pass (stdlib `ast` only) + optional import hook for runtime
- Output: SARIF/JSON — standard format, no plugin dependency to orphan

**Runtime enforcement for trust tiers:**
- Tag data at boundaries (`__trust_tier__` attribute or typed envelope)
- Catch "Tier 3 data crossed into Tier 2 without validation" with zero false positives at runtime

**Hard Python problems (acknowledged limitations):**
- Metaclasses, `__getattr__`, `exec`/`eval`, monkey-patching
- Practical answer: define a narrower "safe subset" for agent-generated code rather than fighting full Python dynamism

**Key coupling:** Tool is most useful when paired with a code generation policy that constrains what agents can produce.

---

### Tech Writer (muna)

**Central thesis:** The biggest trap is category confusion. If this tool gets filed under "linter" or "type checker," it loses — it will be compared unfavorably to mature tools in those categories. Proposes a new category: **"semantic boundary enforcer."**

**Target audience:** Engineering teams shipping AI-powered systems where correctness is load-bearing — LLM pipelines, compliance systems, agentic workflows.

**Elevator pitch:** *"When AI agents write bugs at 10× speed, they ship at 10× speed too. This tool is the semantic seatbelt."*

**Framing strategy:**
- "Paired with mainline Python" is the **value proposition**, not a limitation. Zero friction, full compatibility = anti-orphan story.
- Proposal arc: problem of agentic velocity → why existing tools miss it → encoding institutional knowledge as machine-checkable rules.
- Frame as **capability argument** ("makes AI-assisted development auditably safe"), not tooling argument ("here's another checker").

### Quality Engineer (ordis)

**Central thesis:** Two correctness dimensions require different test strategies — rule logic correctness AND finding usefulness. Both must be measured.

**Testing strategy (test pyramid):**
1. **Wide base:** Per-rule golden snippet corpus — labeled true positives and true negatives
2. **Mid layer:** Rule interaction integration tests
3. **Narrow top:** E2E against known codebases with committed expected-findings manifests

**Critical metric insight:** False negatives are categorically worse than false positives, BUT if FP rate exceeds ~15%, developers disable the tool — making the effective FN rate 100%. Must track suppression rate as a leading indicator. Target <5% FP on ELSPETH codebase.

**Corpus strategy:**
- Mine real bug databases (ELSPETH's 191 bugs) for true positive specimens
- Run against LLM-generated code for feedback loop
- Mutation-test the corpus itself to ensure tests are actually sensitive

**Self-hosting as hard quality gate in CI** — the tool must pass its own checks.

### SDLC Engineer (axiom)

**Central thesis:** Scope discipline is the survival requirement. Three phases with hard gates between them.

**MVP (v0.1, ~200-300 hours):**
- Configurable AST enforcement layer, zero external dependencies
- Detect forbidden patterns, enforce trust-tier annotations
- Run as pre-commit + CI
- Stdlib `ast` only

**v1.0 (post-dogfooding):**
- Intra-procedural dataflow analysis
- Optional mypy plugin, LSP stub
- **Hard gate:** Must dogfood v0.1 for 4-6 weeks before locking v1.0 scope

**Three architectural dead-ends to avoid:**
1. Inter-procedural analysis (compiler research territory — unbounded scope)
2. Ecosystem coupling creep (mypy plugin becoming core dependency)
3. Self-hosting as infinite scope sink

**Definition of "done":**
- Runs on ELSPETH CI with zero false positives on signed-off code
- Catches all documented forbidden patterns from CLAUDE.md
- YAML allowlist mechanism
- >90% coverage with Hypothesis property tests
- Passes its own rules

**Self-hosting from commit one** — if we can't write the tool to its own standards, we don't understand the standards.

---

### Round 1 — Complete Summary (Scribe Notes)

**Areas of strong consensus (5+ participants agree):**
- AST-based static analysis as the core foundation (system architect, python engineer, SDLC engineer, quality engineer all explicit)
- Zero external dependencies for core analysis — stdlib `ast` only (system architect, python engineer, SDLC engineer)
- Trust tiers as a first-class concept distinct from types (systems thinker, security architect, python engineer)
- "Parasitic" integration with existing Python — annotations, decorators, not new syntax (systems thinker, system architect, python engineer)
- Self-hosting as both quality gate and dogfooding mechanism (quality engineer, SDLC engineer)
- SARIF/JSON output for ecosystem independence (python engineer, system architect)

**Areas of productive tension:**
- **Static vs. runtime enforcement:** Python engineer sees runtime tagging as essential complement; system architect and SDLC engineer focus on static-only core. Unresolved: is runtime in MVP or deferred?
- **Scope ambition vs. feasibility:** Security architect's "validation-at-boundary enforcement" (N-statement proximity analysis) requires intra-procedural dataflow — SDLC engineer puts this in v1.0, not MVP.
- **"Safe subset" vs. full Python:** Python engineer suggests constraining agent output; systems thinker warns this could be a Level 2 intervention that meets adoption resistance.
- **FP tolerance:** Quality engineer says >15% FP kills adoption; security architect's comprehensive threat model could push FP higher. Where's the calibration point?

**Novel concepts introduced:**
- "Spoofing competence" (security architect) — STRIDE-adjacent threat category for agentic code
- "Trust-flow analyzer" (systems thinker) — reframing: types = what data is; trust tiers = how much to believe it
- "Parasitic, not parallel" (systems thinker) — adoption strategy principle
- "Type oracle protocol" (system architect) — abstract interface for type checker backends
- "Semantic boundary enforcer" (tech writer) — proposed product category to avoid linter/type-checker comparisons
- "Semantic seatbelt" (tech writer) — elevator pitch framing
- "Shifting the Burden" applied to defensive coding (systems thinker) — `.get()` as symptomatic fix
- Self-hosting from commit one as understanding proof (SDLC engineer)

**Open questions for Round 2:**
1. Is runtime enforcement in scope for MVP, or strictly v1.0?
2. How do you calibrate FP rate against security completeness?
3. Can "safe subset" constraints be enforced without becoming a new language?
4. Is intra-procedural dataflow achievable without importing type checker internals?
5. Who actually runs this tool — human developers, CI bots, or the agents themselves?

---

## Round 2: Challenge Round

> **Scribe observation:** Three agents independently chose to challenge the Python Engineer's runtime tagging proposal. This convergent challenge is a strong consensus signal that runtime tagging is the most controversial idea from Round 1.

### Security Architect (ordis) challenges Python Engineer (axiom)

**Steelman:** Runtime tags are unforgeable provenance evidence with zero false positives. They work *with* Python's dynamic nature rather than fighting it. If a value carries a `__trust_tier__` attribute, you know exactly where it came from at the moment of use.

**Challenge:**
- Zero FP but **catastrophic false negative rate** — runtime enforcement only catches violations on *executed* paths. Agent bugs disproportionately hide in untested error paths, edge cases, and rare branches. A silent FN on an untested path is invisible until production.
- Static analysis with a 15% FP rate is vastly preferable to silent FN on untested paths. You can triage false positives; you can't triage bugs you never see.
- The "narrower safe subset" should be enforced **statically**, not at runtime — prevent unsafe code from *existing*, don't detect it after it runs.
- Runtime tags can be **accidentally overwritten or spoofed** by agents. Trust tier should be a property of the analysis (external to the code), not a property of the data (embedded in the code).

### Systems Thinker (yzmir) challenges Python Engineer (axiom)

**Steelman:** The most technically honest position in Round 1. Correctly identifies AST's fundamental limitation (no type resolution without annotations) and proposes a genuine complement rather than hand-waving past the gap.

**Challenge:**
- Runtime tagging is a **Level 10 (structure) intervention** disguised as Level 6 (information flow). It creates a shadow type system — every serialization, copy, and third-party library call must preserve tags. This is the **"Fixes that Fail"** archetype: the fix introduces new failure modes that eventually overwhelm the original problem.
- The "safe subset" is the right idea but the **wrong framing** — the subset definition IS the product, not a workaround for Python's dynamism. Should be framed as a Level 5 rule ("here is what agent-generated Python looks like") combined with a Level 6 validator ("and here's how we verify it").
- **"Accidental Adversaries" archetype:** Runtime tag requirements create friction with every library and framework in the ecosystem. Libraries that don't preserve `__trust_tier__` become unwitting adversaries — and there are thousands of them. The tool would be fighting the ecosystem, not riding it.

### System Architect (axiom) challenges Python Engineer (axiom)

**Steelman:** Runtime tagging honestly solves AST's blind spot. By attaching trust metadata to values at runtime, you get zero false positives through indirection — you're observing actual data flow, not inferring it.

**Challenge:**
- Tags **disappear at serialization boundaries** — `json.dumps()`, `pickle`, database writes, API calls all strip metadata. This creates a Tier 1 invariant (trust metadata) that behaves like Tier 3 data (silently lost). This is **worse than no tag** — it creates false confidence.
- Key principle: **"Analysis tooling should not modify the artifacts it analyzes."** Runtime tagging crosses the line from development aid to runtime dependency. If the tags are load-bearing, the tool isn't optional anymore — it's infrastructure.
- **Alternative:** The type oracle protocol enriches the analyzer without instrumenting the subject. The safe subset can be enforced as AST patterns. Both achieve the same goals without modifying the code being analyzed.

---

### SDLC Engineer (axiom) challenges Python Engineer (axiom)

**Steelman:** AST is fundamentally blind to data provenance at runtime. Runtime tagging achieves a precision that no static tool can match — it observes actual data flow, not inferred flow.

**Challenge:**
- Import hook creates **two versions of the codebase** — dev with enforcement, prod without. False confidence from dev-only enforcement is worse than no enforcement at all. If violations only surface in dev, they're test-time assertions, not safety guarantees.
- Trust tier is a property of the **data flow path**, not the object itself. Tags are stripped by `json.dumps()`, `pickle`, `deepcopy()`, DataFrame operations, SQLAlchemy — every serialization boundary.
- **Budget argument:** A runtime layer is a separate 400-hour project, not a phase of the static tool. Should be treated as a v2.0 investigation with a requirements spike, not bundled into the MVP or v1.0 roadmap.

### Tech Writer (muna) challenges Quality Engineer (ordis)

**Steelman:** The 15% FP threshold is empirically grounded and actionable. Suppression rate as a health metric is sharp — it turns a qualitative complaint ("too many false alarms") into a measurable signal.

**Challenge:**
- In a trust boundary enforcer, a **suppression comment is a security event**, not an annoyance. If agents can generate violations, they can generate `# noqa: trust-boundary` suppress comments too. Inline suppression is an attack surface.
- **Missing third dimension:** "Pattern dangerousness regardless of instance safety." A `.get()` on Tier 1 data might be safe in this specific instance, but the pattern is dangerous when replicated by agents across the codebase. Instance-level FP/FN misses pattern-level risk.
- **Resolution:** Use project-level allowlist manifests (`strict.toml`) instead of inline suppress comments. Shifts FP resolution to a human-reviewed, version-controlled workflow that agents can't circumvent.

### Quality Engineer (ordis) challenges Systems Thinker (yzmir)

**Steelman:** "Shifting the Burden" archetype is exactly right — defensive patterns are the symptomatic fix weakening the fundamental solution. "Parasitic" is brilliant survivability thinking. Level 6 (information flows) is the correct abstraction level.

**Challenge:**
- **Parasitic semantics are untestable.** If annotations borrow meaning from other tools (`typing.Annotated`), behavior changes when those tools evolve. A golden snippet corpus breaks when the host's semantics shift underneath. Testing becomes fragile.
- **Level 6 leverage isn't measurable.** Can't distinguish "developers understood trust boundaries" from "developers learned to satisfy the linter without understanding." Information flow is high leverage in theory, but you can't tell if it's working without outcome metrics that take months to accumulate.
- **Informational-only mode gets ignored, then disabled.** Need at least one blocking enforcement mode with tool-owned semantics — not borrowed meaning from another tool's annotation system.

### Python Engineer (axiom) challenges Systems Thinker (yzmir)

**Steelman:** The adoption analysis is the sharpest strategic thinking in Round 1. "Shifting the Burden" and "Limits to Growth" are correct diagnoses of why deeper tools fail. The "parasitic, not parallel" principle is actionable.

**Challenge:**
- Python's type system is **structural and advisory**, not semantic and provenance-aware. `Annotated[dict, Tier3]` says nothing about whether the dict actually came from an external boundary — it's a label, not evidence. The annotation can lie.
- "Parasitic" implementation lands you in **AST pattern detection** (~40% of failure modes), not the trust-flow analysis claimed as the high-leverage target. There's a gap between the strategy (Level 6 trust-flow) and what parasitic implementation can actually deliver.
- **Better framing:** Acknowledge a two-tier design honestly. The static layer IS parasitic — AST patterns on standard Python. But reaching trust-flow analysis MUST introduce at least one non-parasitic primitive (e.g., `TrustEnvelope` wrapper type). Be honest about the cost rather than claiming pure parasitism can reach Level 6.

---

### Round 2 — Complete Summary (Scribe Notes)

#### Challenge Graph

```
Security Architect ──────► Python Engineer (runtime tagging)
Systems Thinker ─────────► Python Engineer (runtime tagging)
System Architect ────────► Python Engineer (runtime tagging)
SDLC Engineer ───────────► Python Engineer (runtime tagging)  ← 4v1!
Tech Writer ─────────────► Quality Engineer (FP/suppression model)
Quality Engineer ────────► Systems Thinker (parasitic testability)
Python Engineer ─────────► Systems Thinker (parasitic ceiling)
```

#### The 4v1 Verdict: Runtime Tagging

Four agents independently challenged the Python Engineer's runtime tagging proposal. The combined attack surface:

| Challenger | Fatal Flaw | Category |
|-----------|-----------|----------|
| Security Architect | Only catches executed paths — catastrophic FN rate | Coverage |
| Systems Thinker | Ecosystem friction — "Fixes that Fail" / "Accidental Adversaries" | System dynamics |
| System Architect | Tags vanish at serialization — worse than no tag | Architecture |
| SDLC Engineer | Two codebases (dev/prod) — false confidence; separate 400hr project | Scope/budget |

**Consensus: Runtime tagging is dead as a core mechanism.** May survive as a v2.0 investigation topic, but it's out of MVP and v1.0.

#### Secondary Debates

**Tech Writer vs. Quality Engineer — Suppression as attack surface:**
- Tech writer reframes inline suppression as a security event that agents can generate
- Proposes project-level allowlists (`strict.toml`) instead of inline comments
- Introduces "pattern dangerousness" as a third dimension beyond instance-level FP/FN

**Quality Engineer + Python Engineer vs. Systems Thinker — Parasitic ceiling:**
- Both challengers agree "parasitic" is brilliant strategy but question its reach
- Quality engineer: parasitic semantics are untestable when host tool evolves
- Python engineer: parasitic implementation caps out at ~40% of failure modes; honest design requires at least one non-parasitic primitive
- **This tension is unresolved** and is the most important open question entering Round 3

#### Emerging Design Decisions

| Decision | Round 1 Status | Round 2 Status |
|----------|---------------|----------------|
| AST-based core | Consensus | Reinforced |
| Runtime tagging | Debated | **Rejected** (4v1) |
| Safe subset definition | Proposed | Gaining support as THE product |
| Parasitic integration | Consensus | **Challenged** — ceiling ~40% |
| Inline suppression | Assumed | **Challenged** — security risk |
| Project-level allowlists | Mentioned | **Promoted** (tech writer) |
| Type oracle protocol | Proposed | Unchallenged (implicit support) |

#### Open Questions for Round 3

1. **The parasitic ceiling:** If pure parasitism caps at ~40%, what's the minimum non-parasitic cost to reach trust-flow analysis? Is one primitive (`TrustEnvelope`) enough?
2. **Pattern vs. instance:** How do you flag "this pattern is dangerous even when this instance is safe" without drowning in FP?
3. **Suppression model:** Project-level allowlists vs. inline comments — can both coexist, or must you pick one?
4. **Testability of borrowed semantics:** If annotations use `typing.Annotated`, how do you test rules when `typing` evolves?
5. **Where does "safe subset" live?** Is it a linter rule set, a code generation constraint, or both?

---

## Round 3: Steelman Round

> Each agent steelmans the argument they most disagree with, then proposes a synthesis neither side would reach alone.

### Systems Thinker (yzmir) steelmans Quality Engineer (ordis)

**Opponent steelmanned:** The quality engineer's challenge that parasitic/advisory-only tools are untestable and get ignored.

**Concession:** Admits the **"Eroding Goals" archetype** applies to advisory-only tools — deadline pressure degrades informational visibility over time. Should have flagged this himself in Round 1. The quality engineer is right that measurability requires tool-owned semantics and a testable corpus. Pure parasitism without blocking enforcement is a slow fade to irrelevance.

**Synthesis — "Promotion Protocol":**
- Advisory and blocking aren't alternatives — they're **phases**. Tool launches as Level 6 (advisory) but is architecturally designed to become Level 5 (blocking).
- **Key innovation:** Rules that achieve >95% true positive rate over N evaluations automatically **graduate from advisory to blocking**. The enforcement posture is self-organizing, earned through measured performance rather than imposed from day one.
- **Compromise formula:** "Parasitic expression, tool-owned measurement" — the host (Python annotations/decorators) provides syntax; the tool provides judgment about correctness.
- **Requires:** Golden corpus as first-class artifact, per-rule precision tracking that persists across runs, and the promotion protocol as a core mechanism.

> **Scribe note:** This is a significant move. The systems thinker accepts blocking enforcement as necessary (conceding to quality engineer) but proposes it emerge organically from data rather than be mandated upfront. This bridges the advisory-vs-blocking divide.

### System Architect (axiom) steelmans Python Engineer (axiom)

**Opponent steelmanned:** The gap in AST-only analysis is worse than 40% for high-value rules. Trust tier violations are *semantic*, not syntactic — the same AST node (`dict.get()`) appears whether it's correct usage or a trust boundary violation. Without type/provenance information, the analyzer can't distinguish them.

**Concession:** Also admits the type oracle protocol requires inter-procedural analysis to be useful — exactly the scope trap he warned against in Round 1. The oracle has to resolve types across function boundaries to know what `.get()` is being called on, which is the compiler-research dead-end the SDLC engineer flagged.

**Synthesis — Annotated Metadata as Developer-Declared Intent:**
- Use `typing.Annotated` metadata (`Tier1`, `Tier2`, `Tier3`) as **developer-declared intent**. The AST analyzer reads annotations directly — no type inference engine, no runtime instrumentation, no external tool dependency.
- Add a **lightweight annotation resolver** (not a full type checker) to propagate `Annotated` metadata through local assignments within a single function. This is intra-procedural only — stays within the SDLC engineer's scope boundary.
- Agent-generated code **MUST include trust tier annotations** on boundary-crossing function parameters. This makes the safe subset enforceable: the agent declares trust tiers, the tool verifies consistency.

> **Scribe note:** This sidesteps the type oracle entirely. Instead of asking "what type is this?" (requires type checker), it asks "what did the developer declare this to be?" (requires only AST + annotation reading). The trade-off: annotations can lie, but they're auditable lies.

### Security Architect (ordis) steelmans Runtime Tagging

**Opponent steelmanned (better than the python engineer made it):** Static analysis of provenance is fundamentally approximation. A `str` from an API and a `str` from a database are the same type but different trust tiers. Any heuristic to distinguish them will produce adoption-killing false positives. Runtime tagging was an honest attempt to solve a real problem.

**Additional concession:** His own "FN on untested paths" critique from Round 2 applies equally to static analysis through dynamic dispatch. `getattr()`, plugin systems, and factory patterns all defeat static provenance tracking.

**Synthesis — Three-Layer Design:**
1. **Static provenance tracking** as primary gate (60-70% coverage). Pattern matching + annotation reading.
2. **Provenance assertions** — not runtime tags, but `assert_tier(value, TIER_2)` statements that the static analyzer uses as **hints**. Advisory for the tool, zero runtime cost. Analogous to type annotations — developer declares, tool verifies consistency.
3. **Runtime verification in TEST MODE ONLY** — `TrustEnvelope` as a **calibration mechanism** for static analysis, not production enforcement. Run tests with envelopes enabled to discover where static analyzer has gaps. Catches static analysis FN during testing, not in production.

**Suppression resolution:** Provenance assertions are **positive claims** ("I assert Tier 2 because validated on line N"), not suppressions ("ignore this warning"). The static analyzer verifies plausibility of the assertion. A false assertion caught by the runtime test oracle = hard failure. This eliminates the "agents generate suppress comments" attack vector because assertions must be *consistent*, not just *present*.

> **Scribe note:** This resurrects runtime enforcement in a drastically reduced role — calibration of static analysis during testing, not production enforcement. The three-layer design is the most architecturally complete proposal so far.

### Tech Writer (muna) steelmans Inline Suppression

**Opponent steelmanned (better than quality engineer made it):** Inline suppression provides **information locality** — the context for "why this is safe here" lives next to the code, not in a separate manifest. During code review, a reviewer sees the violation and the justification in the same screen. Manifest entries require cross-referencing, which reviewers skip under time pressure.

**Additional concession:** The agent-circumvention threat is weaker than claimed in Round 2. An incorrect inline justification is actually MORE visible to human reviewers than a manifest entry buried in a config file.

**Synthesis — Structured Inline Annotation + External Ratification:**
- Format: `# strict-ok: pattern=tier1_read, rationale="validated at line 42", approved_in=strict.toml@v3`
- **Inline** for authoring and discoverability — the developer writes the annotation next to the code.
- **Inert until manifest entry exists** — the annotation has no effect until a corresponding entry in `strict.toml` is committed (human-initiated, separate commit).
- **Two-artifact, two-commit requirement** blocks agent circumvention: agent can write the inline annotation, but a human must ratify it in the manifest.

> **Scribe note:** This is elegant — preserves the locality benefit of inline comments while requiring out-of-band human approval. The "inert until ratified" mechanism is novel.

---

### Round 3 — Partial Observations (Scribe Notes)

**Convergence pattern: "Declare intent explicitly, verify with tooling."** All three new syntheses are variations of the same idea:

| Synthesis | Declaration Mechanism | Verification | Source |
|-----------|----------------------|-------------|--------|
| Annotated metadata | `Annotated[str, Tier3]` on parameters | AST annotation resolver | System Architect |
| Provenance assertions | `assert_tier(value, TIER_2)` in code | Static plausibility check + test-time runtime oracle | Security Architect |
| Structured inline annotation | `# strict-ok: pattern=..., rationale=...` | Manifest ratification (`strict.toml`) | Tech Writer |

**These three could be unified:** Annotations declare trust tiers on types. Assertions declare trust tiers on values mid-function. Structured comments declare "I know this looks wrong but here's why." All three are auditable, all three are statically verifiable, none require runtime instrumentation in production.

**Runtime tagging partially resurrected:** The security architect's "test-mode-only TrustEnvelope" gives runtime enforcement a limited, bounded role — calibrating static analysis, not replacing it. This may satisfy the python engineer's concern that static-only misses ~40% while avoiding the 4v1 objections from Round 2.

### Python Engineer (axiom) steelmans "No Runtime Tagging" (system architect + SDLC engineer)

**Opponent steelmanned (stronger than original):** Opt-in safety systems fail at the failure modes you care about most. "No tag present" is ambiguous between "this data is safe" and "nobody remembered to tag it." The system has a blind spot shaped exactly like "code the agent wrote without thinking about trust" — which is the entire threat model.

**Synthesis — Boundary-Function-Anchored Static Taint Analysis:**
- Tag **function signatures**, not data objects. `@external_boundary` on functions like `json.loads`, `requests.get`, DB query methods. `@validates_external` on validation functions.
- Static checker enforces: any value returned from an `@external_boundary` function must pass through a `@validates_external` function before reaching unmarked functions.
- **Key advantage — failure mode is flipped:** Forgetting to mark a boundary function = overly strict (loud, blocks the build), not silently permissive. The unsafe thing is noisy; the safe thing is easy.
- This is what CodeQL/Semgrep taint mode does, applied specifically to trust tier boundaries.

> **Scribe note:** The python engineer has effectively abandoned runtime tagging in favor of static taint analysis with decorator-based boundary markers. This is a full concession on mechanism, but the underlying concern (AST can't track provenance) is addressed by shifting from "tag data at runtime" to "tag functions at declaration time and trace statically."

### Quality Engineer (ordis) steelmans Tech Writer's Suppression Challenge (muna)

**Concession:** Admits the suppression rate metric is **fundamentally invalidated for agentic code**. Agent-generated `# noqa` is pattern completion, not deliberate override. The metric that was supposed to measure developer pain is actually an attack surface.

**Synthesis — Suppression Manifest IS the Test Corpus:**
- The project-level manifest and the golden test corpus are **the same artifact**. Each manifest entry includes: file path, rule ID, reviewer identity, justification text, and expiry date.
- This single artifact serves three roles simultaneously:
  1. **Agent-proof suppression governance** — structured fields, human sign-off required
  2. **Living corpus for FP/FN measurement** — each entry is a labeled data point
  3. **Security event log** — reviewable, diffable, auditable

**Operational mechanics:**
- Manifest diff = quality gate. New entries require human sign-off.
- Expiring entries trigger re-review.
- Growth rate = true suppression rate (measured from a source agents can't inflate).

**Key observation:** ELSPETH's `config/cicd/enforce_tier_model/` directory is already this pattern. Not a new design — **recognizing and generalizing an existing pattern**.

> **Scribe note:** The quality engineer connecting this back to ELSPETH's existing allowlist mechanism is powerful validation. The pattern already works in practice; the synthesis is formalizing and generalizing it.

### SDLC Engineer (axiom) steelmans Python Engineer's Runtime Primitive

**Opponent steelmanned (stronger than original):** 40% static enforcement on a load-bearing audit boundary gives 100% false confidence, not 40% safety. This is "Shifting the Burden" at the tooling layer — the tool becomes the symptomatic fix that prevents the team from building real provenance tracking.

**Concession:** The serialization objection from Round 2 was overgeneralized. It proves the right **scoping**, not impossibility. Tags that live for nanoseconds between function call and validation never hit serialization boundaries.

**Synthesis — Narrow TrustEnvelope (~40 hours, not 400):**
- `TrustEnvelope` wraps `@external_call` returns. Stripped exactly once by `validate_tier3()`. Lives nanoseconds — never reaches serialization, never enters data structures, never crosses library boundaries.
- **Two-layer tool:**
  - **Layer 1:** AST structural enforcement (pattern detection, annotation reading)
  - **Layer 2:** Narrow runtime where AST ALSO enforces statically — verifies every `@external_call` return goes through `validate_tier3()`. The runtime layer is belt-and-suspenders, not the primary mechanism.
- Scope: ~40-hour addition, not the 400-hour project he warned against in Round 2.
- **Open measurement question for sprint 1:** What % of external call sites can be auto-detected by AST heuristics? (Answers whether the annotation burden is acceptable.)

> **Scribe note:** The SDLC engineer rescopes runtime from "impossible project" to "40-hour bounded addition" by limiting TrustEnvelope's lifetime to nanoseconds between call and validation. This neutralizes all four Round 2 objections (serialization, ecosystem friction, two codebases, scope).

---

### Round 3 — Complete Summary (Scribe Notes)

#### The Grand Convergence

All seven agents have independently converged on variations of the same core design. The table below shows how each synthesis maps to a unified architecture:

| Agent | Mechanism | Scope | Maps To |
|-------|-----------|-------|---------|
| System Architect | `Annotated[str, Tier3]` on parameters | Type declarations | **Trust tier annotations** |
| Python Engineer | `@external_boundary` / `@validates_external` | Function declarations | **Boundary markers** |
| Security Architect | `assert_tier(value, TIER_2)` | Mid-function assertions | **Provenance assertions** |
| SDLC Engineer | `TrustEnvelope` + `validate_tier3()` | Call-site wrapping | **Narrow runtime verification** |
| Tech Writer | `# strict-ok: pattern=..., approved_in=...` | Exception justification | **Structured exemptions** |
| Quality Engineer | Manifest = corpus = event log | Suppression governance | **Unified allowlist artifact** |
| Systems Thinker | Rules earn blocking status via precision | Enforcement posture | **Promotion protocol** |

#### Design Crystallizing Around Three Layers

```
Layer 1: STATIC STRUCTURAL (MVP)
  AST pattern detection + annotation/decorator reading
  @external_boundary, @validates_external, Annotated[T, TierN]
  Catches: forbidden patterns, missing annotations, unterminated taint paths

Layer 2: STATIC SEMANTIC (v1.0)
  Intra-procedural taint analysis
  Traces values from @external_boundary through to @validates_external
  Catches: trust tier violations across assignments within a function

Layer 3: RUNTIME CALIBRATION (test-mode only)
  Narrow TrustEnvelope wrapping external call returns
  Validates static analyzer's coverage — catches gaps, not violations
  Catches: static analyzer blind spots (dynamic dispatch, etc.)
```

#### Resolved Tensions

| Tension | Resolution | Round |
|---------|-----------|-------|
| Runtime tagging as core | **Dead** — replaced by static taint + test-mode calibration | R2→R3 |
| Advisory vs. blocking | **Phased** — promotion protocol, rules earn blocking status | R3 |
| Inline vs. manifest suppression | **Unified** — inline annotation inert until manifest ratification | R3 |
| Parasitic ceiling (~40%) | **Extended** — boundary decorators + taint analysis push static coverage to 60-70% | R3 |
| Type oracle dependency | **Avoided** — Annotated metadata read by AST, no type checker needed | R3 |
| Suppression metrics for agentic code | **Manifest IS corpus** — single artifact for governance, testing, and audit | R3 |

#### Remaining Open Questions for Round 4

1. **Auto-detection rate:** What % of external call sites can AST heuristics detect without manual `@external_boundary` annotation?
2. **Annotation burden:** Is requiring trust tier annotations on every boundary-crossing parameter practical for real codebases?
3. **MVP rule set:** Which specific patterns from ELSPETH's CLAUDE.md become v0.1 rules?
4. **Naming:** "Semantic boundary enforcer," "trust-flow analyzer," or something else?
5. **Self-hosting bootstrapping:** How do you write the first version of a tool that must pass its own rules when the rules don't exist yet?

---

## Round 4: Convergence — Concrete Recommendations

> Each agent provides their top 2-3 actionable items for the v0.1 spec.

### Unanimous Recommendations (7/7 agents)

These three items appeared in every single agent's recommendation set:

**1. `strict.toml` manifest is a v0.1 day-one artifact.**
Declares trust topology, layer rules, boundary functions, and structured exceptions with rationale + reviewer + expiry. Schema versioned from the first commit. This is the project-level contract that everything else references.

**2. Golden corpus calibrated against ELSPETH before shipping any rule.**
Labeled true positives and true negatives drawn from the real ELSPETH codebase. The corpus IS the calibration instrument for the promotion protocol — no rule ships without empirical evidence. Mine ELSPETH's 191 documented bugs for TP specimens.

**3. Annotation vocabulary specified before enforcement code is written.**
`@external_boundary`, `@validates_external` (or equivalent), `Annotated[x, TierN]`. A spec document defining the vocabulary, semantics, and usage patterns ships before the first line of checker code. Implementation follows specification, not the reverse.

### Strong Consensus Recommendations (5-6/7 agents)

**4. Rules ship advisory, promote to blocking via measured precision.**
The systems thinker's promotion protocol adopted by the group. Threshold: >95% true positive rate sustained over N evaluations. Per-rule precision tracking persists across runs.

**5. No inline suppression (`# noqa`) — ever.**
Two-artifact exception mechanism only: structured inline annotation (`# strict-ok: ...`) is inert until a corresponding entry in `strict.toml` is ratified by a human in a separate commit. Agents cannot self-suppress.

**6. Intra-function taint analysis in v0.1 scope.**
Track `@external_boundary` return values through local assignments within a single function. Flag if they reach non-validator calls without passing through `@validates_external`. Estimated ~200 lines of checker code. Inter-procedural analysis is v0.2+.

**7. SARIF output from day one.**
Standard output format that feeds GitHub Code Scanning, Filigree dashboard, and arbitrary CI systems. No custom output formats.

**8. Self-hosting gate.**
The tool's own source code must pass its own checks before any rule earns promotion to blocking status. Dogfooding is a prerequisite, not a nice-to-have.

### Notable Agent-Specific Recommendations

| Agent | Recommendation | Rationale |
|-------|---------------|-----------|
| **SDLC Engineer** | Sprint 1 is MEASUREMENT, not build. 40 hours answering: how many external calls in ELSPETH? Raw FP count? Genuine bugs found? | Data before code — don't build what you can't calibrate |
| **Security Architect** | Exactly 8 initial rules mapped to STRIDE threat categories | Bounded scope with security-theoretic justification |
| **Tech Writer** | Proposal must open with a working run against ELSPETH showing concrete numbers | "Show, don't tell" — the demo IS the pitch |
| **Quality Engineer** | 3 TP + 2 TN minimum per rule as merge gate | No rule ships without calibration evidence |
| **Python Engineer** | Checker is ~200 lines, intra-function only, SARIF output | Scope constraint as architectural discipline |
| **System Architect** | Two-pass analyzer: symbol collection pass → rule evaluation pass | Clean separation enables rule authoring without understanding the collector |

---

### Round 4 — Scribe Analysis

#### What's Decided

The group has converged on a remarkably specific v0.1 specification:

**Architecture:**
- Standalone AST-based analyzer (~200 lines core)
- Two-pass design: symbol collection → rule evaluation
- SARIF/JSON output
- Zero external dependencies (stdlib `ast` only)

**Annotation vocabulary:**
- `@external_boundary` — marks functions that return untrusted data
- `@validates_external` — marks functions that validate/coerce external data
- `Annotated[T, TierN]` — trust tier metadata on type annotations

**Enforcement model:**
- Rules start advisory, promote to blocking at >95% precision
- Per-rule precision tracking persists across runs
- Project-level `strict.toml` manifest (trust topology + exceptions + corpus)
- No inline `# noqa` — structured two-artifact exception mechanism only

**Quality gates:**
- Golden corpus with 3 TP + 2 TN per rule minimum
- Self-hosting from commit one
- Manifest = corpus = security event log (single artifact, three purposes)

**Process:**
- Sprint 1: measurement run against ELSPETH (40 hours, data before code)
- 8 initial rules mapped to STRIDE threats
- Dogfood 4-6 weeks before locking v1.0 scope

#### What's Still Open

1. **Exact annotation vocabulary** — `@external_boundary` vs. `@trust_boundary` vs. other naming
2. **The 8 initial rules** — security architect proposed the count, but the specific rules need definition
3. **Product name** — "semantic boundary enforcer" (tech writer) vs. "trust-flow analyzer" (systems thinker) vs. something else
4. **Runtime calibration layer** — consensus on concept but not on whether it's in v0.1 or v0.2
5. **Promotion protocol thresholds** — 95% precision over how many evaluations? What sample size?

---

## Round 5: Minority Report and Final Positions

### Stray Thoughts (New Ideas Not Previously Discussed)

**1. Adversarial evasion by agents (Security Architect):**
Agents will learn to pattern-match around rules. A function named `validate_and_parse()` that does no validation but satisfies the AST checker. The golden corpus needs **adversarial evasion samples** — code that looks compliant but isn't. Additionally: agents can add `@trust_boundary` annotations to suppress findings. The manifest PR workflow must be **human-gated** (CODEOWNERS on `strict.toml`).

**2. Generated code exclusions (System Architect):**
ORMs, protobuf stubs, Pydantic-generated code need a `[generated]` exclusion section in the manifest. Also: annotation naming matters for adoption — use **abstract names** (`Trusted`/`Validated`/`Untrusted`) rather than ELSPETH-specific terminology (`Tier1`/`Tier2`/`Tier3`). The tool must be generalizable.

**3. Agent vs. human enforcement asymmetry (Systems Thinker):**
Agents have no memory across sessions — the advisory phase of the promotion protocol is useless for them. They can't learn from warnings they'll never see again. May need **two enforcement profiles**: human (promotion protocol with advisory→blocking) vs. agent (default-block with demotion for rules that prove too noisy). Also: **cross-project composition** with different `strict.toml` manifests is entirely unexplored.

**4. Determinism and volume floor (Quality Engineer):**
**Determinism requirement:** Identical input must produce byte-identical output. Verify by running twice and diffing. The promotion protocol needs a **volume floor** (≥50 firings), not just a time threshold — rare rules promoted on small samples are promoted on noise.

**5. SARIF for agent consumers (Tech Writer):**
SARIF consumers might be other AI agents, not humans. Findings should reference **grammar rules in trust-model terms**, not just line numbers — this teaches agents the trust model through the feedback loop. Also: **grammar drift** (the annotation vocabulary evolving incompatibly) is now the primary risk, not product framing.

**6. Pre-generation mode (Python Engineer):**
`strict check --stdin` for agents to self-check before submitting code. Must run in **sub-200ms per file**. Closes the feedback loop at generation time rather than at CI time. This is the "semantic seatbelt" operating at the point of maximum leverage — before the code exists in the repo.

**7. Known external call heuristic list (SDLC Engineer):**
Ship a built-in heuristic list of known external call sites (`requests.*`, `httpx.*`, `sqlalchemy.*.execute`, `json.loads`, etc.) for auto-detection without manual annotation. Also: ship as **standalone PyPI package** from day one, not an ELSPETH-internal script. The tool's value is general.

### Position Shifts

Every agent shifted position during the discussion. The table below tracks the movement:

| Agent | Round 1 Position | Round 5 Position | What Changed Them |
|-------|-----------------|-----------------|-------------------|
| **Security Architect** | Block everything day one | Promotion protocol with advisory phase | Systems thinker's adoption dynamics argument |
| **System Architect** | AST-only is sufficient | AST-only gap worse than claimed; Annotated synthesis is genuinely better | Python engineer's 40% coverage challenge |
| **Systems Thinker** | Level 6 (information flows) is the leverage point | Level 4 (self-organization) via promotion protocol | Quality engineer's "advisory gets ignored" challenge |
| **Python Engineer** | Runtime tagging is essential complement | **"I was wrong in Round 1."** Fully abandons runtime tagging | 4v1 challenge (serialization, coverage, ecosystem, scope) |
| **Quality Engineer** | Suppression rate is the key health metric | Suppression rate metric is wrong for agentic context | Tech writer's "agents generate noqa" argument |
| **SDLC Engineer** | Zero runtime, period | Accepts narrow test-mode runtime calibration (~40 hours) | Python engineer's 40% false confidence argument |
| **Tech Writer** | Primary risk is category framing | Primary risk is grammar drift (annotation vocabulary evolution) | Rounds 2-3 showed framing was solved; vocabulary stability wasn't |

### Minority Dissent

#### "No Inline Suppression Ever" Is Cracking (4/7 dissent)

The Round 4 consensus on "no inline suppression ever" did not survive Round 5. Four agents filed dissent proposing nuanced alternatives:

| Agent | Proposed Model | Key Argument |
|-------|---------------|-------------|
| **System Architect** | Tiered: manifest-only for architectural rules, structured inline for syntactic rules | Not all rules carry the same risk — syntactic patterns don't need the same governance as trust boundary exceptions |
| **Systems Thinker** | Structured inline with auto-expiry, logged as security events | "The alternative isn't no suppression — it's suppression via removing the tool." If the mechanism is too rigid, teams disable the tool entirely |
| **Python Engineer** | Inline with mandatory rationale + auto-generated draft manifest entry for human ratification within N days | Bridge mechanism: agent writes inline, tool auto-generates manifest PR, human ratifies within deadline or it reverts |
| **Tech Writer** | Advisory rules allow inline-sufficient; blocking rules require manifest | Match governance overhead to rule severity — promoted rules get stricter suppression requirements |

> **Scribe note:** The 4-way dissent on suppression is the only consensus item from Round 4 that fractured. The underlying concern is identical across all four: if the suppression mechanism is too burdensome, teams will disable the tool rather than comply. The compromise emerging is a tiered model where governance scales with rule severity.

#### Other Dissents

**Security Architect — Tool needs its own STRIDE threat model:**
The tool itself is an attack surface. Threats: tampering with manifest, spoofing `@validates_external` annotations, DoS via finding volume. Mitigation: `CODEOWNERS` on `strict.toml`, adversarial corpus samples, finding rate limiting.

**Quality Engineer — SARIF must never populate suppressions field:**
Suppression state lives in the manifest only, never in SARIF output. If SARIF includes suppression data, downstream consumers (including agents) learn which findings are "ignorable."

**SDLC Engineer — Promotion protocol needs governance:**
A named governance OWNER and explicit rollback workflow, not just an automated threshold. Someone must be accountable when a promoted rule starts producing false positives at scale.

---

## Round 6: Focused Debate — Three Open Questions

> Three dissents from Round 5 require resolution before the spec is ready. Each agent addresses the question they feel most strongly about.

### The Three Questions

**Q1 — Suppression Model (4 dissenters vs. 3 holding):**
Current consensus: "No inline suppression ever" — manifest-only ratification.
Dissent: Tiered model — manifest-only for blocking rules, structured inline for advisory/syntactic rules.
Core tension: adoption friction (manifest bottleneck) vs. agent circumvention (inline is gameable).

**Q2 — Promotion Protocol Governance (SDLC engineer dissent):**
Current consensus: Automated promotion at 95% precision / 50+ firings.
Dissent: Who owns the decision? Automated promotion surprises teams. Also: advisory is useless for agents (no cross-session memory) — should agents get default-block with demotion?

**Q3 — Tool's Own Threat Model (security architect dissent):**
Current consensus: None — nobody applied STRIDE to the tool itself.
Dissent: Tampering (agent modifies strict.toml alongside violation), Spoofing (agent adds @validates to non-validating function), DoS (finding flood causes rubber-stamping).

### Q1 Responses — Suppression Model

**System Architect:** All suppressions in manifest, but with **separate sections** — `[allowlist.architectural]` (high scrutiny, trust boundary exceptions) and `[allowlist.syntactic]` (lower scrutiny, pattern exceptions). No inline comments of any kind. Governance scales via section, not mechanism.

**Systems Thinker:** Blocking rules = manifest-only. Advisory rules = structured inline with auto-expiry + auto-harvested into manifest audit trail. Two mechanisms, but the inline path feeds into the manifest automatically.

**Python Engineer:** Inline allowed only for advisory rules, structured rationale required, 90-day auto-expiry. Blocking rules = manifest-only. Clear boundary between rule tiers.

**Quality Engineer — REFRAMES THE DEBATE:** *"If a rule belongs in this tool, it targets trust violations that warrant manifest governance. Rules that would be fine with inline suppression belong in ruff, not here."* Narrows the tool's scope to eliminate the question entirely.

> **Scribe note:** The quality engineer's reframe is the sharpest move in Q1. If the tool only contains trust-boundary rules (not general structural patterns), then manifest-only governance is proportionate. The tension only exists if the tool also polices `.get()` on dataclasses, bare `except`, etc. — patterns that might belong in ruff instead. **This is a scope decision masquerading as a suppression design decision.**

**Emerging resolution:** Two viable paths:
1. **Narrow scope** (quality engineer): Tool covers trust boundaries only → manifest-only is defensible → no suppression debate.
2. **Broad scope** (system architect): Tool also covers structural patterns → tiered manifest sections with different scrutiny levels → still manifest-only, but with graduated governance.

### Q2 Responses — Promotion Protocol Governance

**Systems Thinker:** Tool **proposes** promotions by writing `pending_promotions` entries to `strict.toml`. Human merges the PR. Git-native workflow, no named owner needed — the PR reviewer is the owner.

**Security Architect:** Semi-automated. Two enforcement profiles: `[enforcement.human]` (graduated promotion protocol) and `[enforcement.agent]` (default-block with demotion path). Profile detected by commit author identity.

**Quality Engineer:** Same pattern — automate the clock (precision tracking), human flips the switch (PR merge). Agent-authored code paths start blocking with a demotion path for rules that prove too noisy.

**SDLC Engineer:** Tool proposes via **draft PR**. Merge gated by `CODEOWNERS`. One configuration field: `strict.toml` gets `[context] agent_mode = "default_block"`.

> **Scribe note:** Strong convergence — all four agree on **"tool proposes, human approves via PR."** The agent asymmetry is also converging: **default-block for agents, graduated promotion for humans.** The only variation is implementation detail (pending_promotions section vs. draft PR vs. config field).

**Resolution forming:**
- Promotion: tool writes proposal → human merges PR → CODEOWNERS-gated
- Agent mode: `agent_mode = "default_block"` in `strict.toml` `[context]` section
- Demotion: rules that exceed FP threshold on agent-authored code get demoted back to advisory for agents

### Q3 Responses — Tool's Own Threat Model

**Security Architect:**
- **Tampering:** `strict.toml` must not be modified in the same PR as source code changes. Separation of concerns at the PR level.
- **Spoofing:** `@validates_external` requires structural validation logic — function body must contain `try/except`, `isinstance`, or `raise`. AST verifiable.
- **DoS:** Finding cap of 25 per rule per run to prevent rubber-stamping.

**System Architect:**
- Content hash on manifest sections for tamper evidence.
- `@validates` structural check (must contain control flow).
- Finding cap of 20 per rule per file, with summary of suppressed findings.

**Python Engineer:**
- `@validates` must contain **control flow branching** (if/else, try/except) — a function that just returns its input doesn't qualify.
- `CODEOWNERS` is the right answer for manifest protection.

**SDLC Engineer:**
- All three threats resolve via **existing governance architecture**: CODEOWNERS + manifest PR workflow + finding cap (proposes 5 per rule per file).
- Not separate security features — the governance design already handles these threats.

> **Scribe note:** Strong convergence on all three mitigations. The only disagreement is finding cap granularity (per-run vs. per-file) and threshold (5 vs. 20 vs. 25). Summary:

| Threat | Mitigation | Consensus Level |
|--------|-----------|----------------|
| Tampering (manifest modification) | CODEOWNERS on `strict.toml` + separate PR requirement | 4/4 agree |
| Spoofing (`@validates` on non-validators) | AST structural check: function must contain control flow / error handling | 4/4 agree |
| DoS (finding flood) | Per-rule finding cap (exact threshold TBD: 5-25) | 4/4 agree on mechanism, threshold varies |

### Tech Writer (muna) — Late Arrival

**On Q1 (Suppression):** Holds tiered dissent but with a refined framing. Blocking findings and advisory findings are **different epistemic categories**, not different severities. Blocking = the tool's claim is authoritative (the tool knows better than the developer). Advisory = the developer's contextual knowledge is legitimate (the tool is flagging a pattern, not asserting a violation). **Spec language:** `severity: blocking` → manifest-only. `severity: advisory` → structured inline, self-sufficient.

**On Q3 (Threat Model):** **Temporal separation** is the real protection, not just CODEOWNERS. `strict.toml` ratification must occur in a **prior commit**, not the same one. CI verifies commit timestamps. ~30 lines of git plumbing. The tiered suppression model makes the temporal check tractable — it only needs to apply to blocking-severity rules.

---

### Round 6 — Complete Resolution Summary

#### Q1: Suppression Model — CONVERGING (two compatible resolutions merged)

The quality engineer's scope reframe and the tiered model are **compatible, not competing**:
- This tool only contains trust-relevant rules (quality engineer's scope constraint)
- Blocking rules use manifest-only governance (unanimous)
- Advisory rules (few in number) allow structured inline with auto-expiry (5/7)

The remaining question reduces to: **which v0.1 rules are blocking vs. advisory?** This is a rule-by-rule design decision, not an architectural one.

**Tech writer's epistemic framing adds precision:** Blocking = tool is authoritative (trust boundary violation). Advisory = developer context may override (structural pattern). This gives a principled criterion for classifying each rule.

#### Q2: Promotion Governance — RESOLVED (unanimous)

| Spec Decision | Detail |
|--------------|--------|
| Proposal mechanism | Tool writes `pending_promotions` entries / draft PR |
| Approval mechanism | Human merges PR, CODEOWNERS-gated |
| Agent asymmetry | `[context] agent_mode = "default_block"` in `strict.toml` |
| Agent demotion | Rules exceeding FP threshold on agent-authored code demote to advisory for agents |
| Human graduation | Advisory → blocking at >95% precision, ≥50 firings |

#### Q3: Tool's Own Threat Model — RESOLVED (strong consensus)

| Threat | Mitigation | Consensus |
|--------|-----------|-----------|
| Tampering (manifest) | CODEOWNERS + temporal separation (ratification in prior commit, CI-verified) | 5/5 |
| Spoofing (@validates) | AST structural check: function body must contain control-flow (try/except, isinstance, raise, if/else) | 5/5 |
| DoS (finding flood) | Per-rule finding cap per file (threshold 5-25, TBD in sprint 1 measurement) | 5/5 on mechanism |

---

## Round 7: Final Convergence — Spec Decisions

> Each agent provides their final v0.1 spec position as concrete spec language, plus any remaining disagreements.

### Unanimous / Near-Unanimous Spec Decisions

Twelve decisions have reached consensus. These are the spec:

| # | Decision | Support | Notes |
|---|----------|---------|-------|
| 1 | `strict.toml` is root artifact with CODEOWNERS protection | 7/7 | |
| 2 | Annotation vocabulary/grammar doc ships before enforcement code | 7/7 | |
| 3 | Tool proposes promotions, human approves via PR merge | 7/7 | |
| 4 | Agent mode: `default_block` config, inverse of human graduated path | 7/7 | |
| 5 | Golden corpus is first-class artifact and v0.1 ship gate | 7/7 | |
| 6 | Self-hosting gate from first commit | 6/7 | |
| 7 | Temporal separation: `strict.toml` ratification in separate/prior commit, CI-enforced | 6/7 | |
| 8 | `@validates` structural verification — must contain control flow | 6/7 | |
| 9 | SARIF output; never populate suppressions field | 6/7 | |
| 10 | Intra-function taint only in v0.1 — no inter-procedural | 7/7 | |
| 11 | Zero external dependencies in core | 7/7 | |
| 12 | Rule inclusion criterion: trust-relevant only; style/idiom belongs in ruff | 5/7 explicit, others compatible | Quality engineer's scope reframe adopted |

### Suppression Model — RESOLVED

**Consensus formula:** Blocking rules = manifest-only governance. Advisory rules = structured inline with auto-expiry (90-day default).

**v0.1 variant (minor, compatible):**
- Security architect: 6 blocking + 2 advisory in v0.1
- System architect: ALL blocking in v0.1 (no advisory rules at all)
- Both are valid instantiations of the same model — the suppression mechanism supports both; it's the rule classification that varies.

### Open Design Questions (Documented Disagreements — Not Blockers)

These six questions have multiple defensible positions. They are flagged for resolution during Sprint 1 measurement or first implementation phase.

**ODQ-1: Finding cap scope and value**

| Agent | Proposal |
|-------|----------|
| SDLC Engineer | Per-rule per-file, default 10 |
| Security Architect | Per-rule per-file, default 25 |
| Python Engineer | Per-run total, 200 |
| Tech Writer | No cap — informational annotation only |
| Quality Engineer | Rule-author-specified, default 10, max 25 |

**Resolution path:** Sprint 1 measurement against ELSPETH will show actual finding density. Set threshold empirically.

**ODQ-2: v0.1 rules — blocking from birth or all advisory?**

| Position | Agents | Argument |
|----------|--------|----------|
| 6 blocking + 2 advisory | Security Architect | Trust boundary rules are authoritative from day one |
| All blocking, no advisory | System Architect | v0.1 is narrow enough that every rule is trust-critical |
| All advisory until corpus proves precision | SDLC Engineer | "Shipping blocking before corpus exists contradicts the promotion protocol" |

> **Scribe note:** This is the promotion protocol's **chicken-and-egg problem**. You need data to promote, but you need rules running to get data. The SDLC engineer's position is most consistent with the promotion protocol design; the security architect's position is most consistent with the "trust-relevant only" scope constraint (if rules are trust-relevant, they should block).

**Resolution path:** Sprint 1 corpus building will provide the precision data needed to justify initial blocking status.

**ODQ-3: Promotion protocol `min_firings` threshold**

| Agent | Proposed Default |
|-------|-----------------|
| Systems Thinker | 20 (argues 50 is too high for greenfield projects) |
| Others | 50 (Round 3 consensus) |

Configurable per-project, but the default matters for out-of-box behavior.

**ODQ-4: Annotation vocabulary naming**

| Style | Example | Proponents |
|-------|---------|-----------|
| Abstract | `Trusted` / `Validated` / `Untrusted` | System Architect |
| Tier-numbered | `Tier1` / `Tier2` / `Tier3` | (ELSPETH-native) |
| Semantic | `@external_call` / `@validates_tier3` | Python Engineer |

System architect flagged this as the first implementation-phase task. No consensus — needs a design decision before code.

**ODQ-5: Finding semantic fields**

Tech writer proposes every SARIF finding include `violation_explanation` (human-readable trust model explanation) and `grammar_rule` (reference to the annotation vocabulary spec). Other agents didn't address. High value for agent consumers (teaches the trust model through feedback) but adds implementation surface.

**ODQ-6: Pre-generation mode (`--stdin`)**

Python engineer proposed sub-200ms per-file agent self-check mode. Closes the feedback loop at generation time. Other agents didn't address. High value but scope question for v0.1 vs. v0.2.

---

## Round 8: Final Minority Check

> Last round. Each agent confirms satisfaction with the 12 resolved decisions, identifies the most important open question, and captures any final thoughts.

### Consensus Confirmation

**All 7 agents confirmed satisfaction with the 12 resolved decisions. Zero objections on any resolved item.**

### Priority Open Question Vote

| Question | Votes | Voters |
|----------|-------|--------|
| **Q2: Blocking vs. advisory from birth** | **5** | Security Architect, Systems Thinker, Tech Writer, Quality Engineer, SDLC Engineer |
| Q4: Annotation naming | 2 | System Architect, Python Engineer |

**Q2 is the #1 priority** — must be resolved before implementation starts.

### Final Positions on Q2 (Blocking vs. Advisory From Birth)

| Position | Agents | Argument |
|----------|--------|----------|
| Ships BLOCKING (unvalidated-flow rules), corpus includes known FP patterns | Security Architect | Trust boundary rules are authoritative; include FP patterns in corpus rather than deferring |
| Ships BLOCKING in both profiles, strict-then-demote | Systems Thinker | Better to start strict and relax than start permissive and tighten |
| ALL ADVISORY until Sprint 1 data proves precision | SDLC Engineer | Consistent with promotion protocol — no data, no blocking |
| Resolve in grammar doc — each rule gets birth severity with one-line justification | Tech Writer, Quality Engineer | Process answer: make the decision per-rule in the grammar doc, not as a blanket policy |

> **Scribe note:** The 3v1 split (blocking vs. advisory) is bridged by the tech writer / quality engineer process proposal: don't make a blanket decision — decide per-rule in the grammar doc with justification. This lets some rules ship blocking (where the team has high confidence from ELSPETH experience) and others ship advisory (where precision is uncertain). The grammar doc becomes the venue for the decision, not a policy debate.

### Items Promoted to v0.1 Deliverables

Three items originally flagged as "open questions" or "future" were promoted to v0.1 scope in Round 8:

| Item | Promoted By | Rationale |
|------|------------|-----------|
| `--stdin` pre-generation mode | Python Engineer | ~10 lines of code, closes agent feedback loop at generation time |
| "Known external call site" heuristic list | SDLC Engineer | Essential for auto-detection without manual annotation; needs spec home and contribution process |
| Semantic finding fields (`violation_explanation`, `grammar_rule`) | Tech Writer | Must be resolved before corpus is built — corpus needs expected explanation values as labels |

### Final Stray Thoughts

**Tech Writer:** Semantic findings fields should be resolved **before** the corpus is built, not after. The corpus needs expected `violation_explanation` values as labeled data — if you build the corpus first and add explanations later, you rebuild the corpus.

**SDLC Engineer:** The "known external call site" heuristic list is a **v0.1 deliverable**, not a nice-to-have. It needs a spec home (where does the list live?) and a contribution process (how do users add entries?).

**Python Engineer:** `--stdin` mode is approximately 10 lines of code wrapping the existing analyzer. It should be v0.1, not deferred.

---

## Final Synthesis (Post-Round 8)

### What This Roundtable Produced

Over eight rounds, seven agents with distinct expertise converged from divergent opening positions to a concrete, actionable tool specification. The discussion resolved seven major tensions, killed one proposal (runtime tagging, Round 2), resurrected it in bounded form (test-mode calibration, Round 3), resolved three focused dissents (suppression model, promotion governance, threat model — Round 6), and confirmed unanimous satisfaction with all resolved decisions (Round 8). The final spec includes 13 resolved decisions, 2 priority open questions requiring pre-implementation resolution, and 4 deferred parameter-level questions.

### The Tool in One Paragraph

A **standalone, zero-dependency AST-based semantic boundary enforcer** for Python that enforces trust boundaries through developer-declared annotations (`@external_boundary`, `@validates_external`, `Annotated[T, TierN]`). It reads a project-level `strict.toml` manifest (CODEOWNERS-protected, temporally separated from source changes) declaring trust topology, layer rules, and structured exceptions with rationale, reviewer, and expiry. Rules ship with per-rule birth severity (blocking or advisory, justified in the grammar doc) and follow a promotion protocol: advisory rules earn blocking status at >95% precision over a volume floor of firings; agent-authored code defaults to blocking with a demotion path. Output is SARIF with semantic fields (`violation_explanation`, `grammar_rule`). The checker performs intra-function taint analysis (~200 lines core), tracing values from external boundary functions through to validation functions, supplemented by a built-in heuristic list of known external call sites. A narrow test-mode runtime layer (`TrustEnvelope`, ~40 hours) calibrates the static analyzer's coverage. Blocking-severity exceptions require manifest-only governance; advisory-severity exceptions allow structured inline annotation with 90-day auto-expiry. A `--stdin` mode enables sub-200ms pre-generation self-checking by agents.

### Architecture Summary

```
┌──────────────────────────────────────────────────────────────┐
│                        strict.toml                            │
│  CODEOWNERS protected · Temporal separation (prior commit)    │
│  Trust topology · Layer rules · Boundary declarations         │
│  Structured exceptions (rationale + reviewer + expiry)        │
│  Schema versioned · [context] agent_mode = "default_block"    │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐    ┌──────────────┐                        │
│  │  Pass 1:     │───►│  Pass 2:     │──► SARIF output        │
│  │  Symbol      │    │  Rule        │    (no suppressions     │
│  │  Collection  │    │  Evaluation  │     field populated)    │
│  └──────────────┘    └──────────────┘                        │
│        │                    │                                 │
│        ▼                    ▼                                 │
│  Reads:                 Checks:                               │
│  @external_boundary     Forbidden patterns                    │
│  @validates_external    Unterminated taint paths              │
│  Annotated[T,TierN]    Missing annotations                   │
│  Known call heuristics  Trust tier violations                 │
│                         @validates structural integrity       │
│                                                               │
│  Modes: CLI · pre-commit · CI · --stdin (agent self-check)    │
│                                                               │
├──────────────────────────────────────────────────────────────┤
│  Golden Corpus (3 TP + 2 TN per rule minimum)                │
│  = Calibration instrument for promotion protocol              │
│  = Suppression manifest (structured exceptions)               │
│  = Security event log (auditable)                            │
│  + Adversarial evasion samples                               │
│  + Expected violation_explanation labels                      │
├──────────────────────────────────────────────────────────────┤
│  Promotion Protocol                                           │
│  Human: Advisory ──[>95% precision, volume floor]──► Blocking │
│  Agent: Blocking ──[>FP threshold]──► Advisory (demotion)     │
│  Tool proposes · Human approves via PR · CODEOWNERS-gated     │
├──────────────────────────────────────────────────────────────┤
│  Threat Mitigations                                           │
│  Tampering:  CODEOWNERS + temporal separation                 │
│  Spoofing:   @validates structural check (control flow req'd) │
│  DoS:        Per-rule finding cap per file                    │
└──────────────────────────────────────────────────────────────┘
```

### Resolved Decisions (13)

All confirmed with zero objections in Round 8.

| # | Decision | Support | Resolved In |
|---|----------|---------|-------------|
| 1 | `strict.toml` is root artifact with CODEOWNERS protection | 7/7 | R4 |
| 2 | Annotation vocabulary/grammar doc ships before enforcement code | 7/7 | R4 |
| 3 | Tool proposes promotions, human approves via PR merge | 7/7 | R6 |
| 4 | Agent mode: `default_block` config, inverse of human graduated path | 7/7 | R6 |
| 5 | Golden corpus is first-class artifact and v0.1 ship gate | 7/7 | R4 |
| 6 | Self-hosting gate from first commit | 6/7 | R4 |
| 7 | Temporal separation: `strict.toml` ratification in prior commit, CI-enforced | 6/7 | R6 |
| 8 | `@validates` structural verification — must contain control flow | 6/7 | R6 |
| 9 | SARIF output; never populate suppressions field | 6/7 | R7 |
| 10 | Intra-function taint only in v0.1 — no inter-procedural | 7/7 | R4 |
| 11 | Zero external dependencies in core | 7/7 | R4 |
| 12 | Rule inclusion: trust-relevant only; style/idiom belongs in ruff | 5/7 | R6 |
| 13 | Suppression: blocking = manifest-only; advisory = structured inline with 90-day expiry | 6/7 | R6-R7 |

### Priority Open Questions (Resolve Before Implementation)

**ODQ-2: Per-rule birth severity (blocking vs. advisory)**
- 5/7 voted this the #1 priority
- Resolution venue: the grammar doc — each rule gets a birth severity with one-line justification
- Positions: 3 agents favor blocking-from-birth for trust rules, 1 favors all-advisory until data, 2 favor per-rule decision in grammar doc

**ODQ-4: Annotation vocabulary naming**
- 2/7 voted this #2 priority
- Options: abstract (`Trusted`/`Untrusted`), tier-numbered (`Tier1`/`Tier3`), semantic (`@external_call`/`@validates_tier3`)
- Resolution venue: first implementation-phase task

### Deferred Open Questions (Resolve During Sprint 1 / Implementation)

| Question | Range of Proposals | Resolution Path |
|----------|-------------------|-----------------|
| ODQ-1: Finding cap scope/value | 5-25 per-rule per-file, or 200 per-run, or rule-author-specified | Sprint 1 measurement against ELSPETH |
| ODQ-3: Promotion `min_firings` default | 20 (systems thinker) vs. 50 (others) | Configurable; set default after Sprint 1 data |
| ODQ-5: Semantic finding fields | `violation_explanation` + `grammar_rule` in SARIF | Resolve before corpus (corpus needs expected values) |
| ODQ-6: `--stdin` mode timing | Promoted to v0.1 by python engineer (Round 8) | ~10 lines, implement with core checker |

### v0.1 Deliverables (Complete List)

| Deliverable | Scope | Source |
|------------|-------|--------|
| Grammar doc (annotation vocabulary + per-rule birth severity) | Spec document | R4 unanimous + R8 resolution |
| `strict.toml` manifest schema (v1) | Config format | R4 unanimous |
| AST-based checker (~200 lines core) | Two-pass analyzer | R4 consensus |
| Golden corpus (3 TP + 2 TN per rule, + adversarial samples) | Test artifact | R4 unanimous + R5 addition |
| SARIF output with semantic fields | Output format | R7 consensus + R8 promotion |
| Known external call site heuristic list | Built-in data | R8 promotion |
| `--stdin` pre-generation mode | CLI interface | R8 promotion |
| `strict.toml` CODEOWNERS + CI temporal check | Governance | R6 consensus |
| Self-hosting: tool passes its own rules | Quality gate | R4 consensus |
| Standalone PyPI package | Distribution | R5 consensus |

### v0.1 Process

| Phase | Scope | Hours (est.) |
|-------|-------|-------------|
| **Sprint 0:** Grammar doc | Annotation vocabulary, 8 initial rules with birth severity, per-rule justification | 20 |
| **Sprint 1:** Measurement | Run candidate rules against ELSPETH. Count external calls, measure FP rates, build initial corpus | 40 |
| **Sprint 2:** Build | ~200-line checker, strict.toml reader, SARIF output, --stdin mode, heuristic list | 80 |
| **Sprint 3:** Calibrate | Corpus expansion, adversarial samples, promotion threshold tuning, self-hosting validation | 40 |
| **Sprint 4:** Ship | PyPI package, CI integration, CODEOWNERS + temporal check, documentation | 40 |
| **Dogfood:** 4-6 weeks on ELSPETH before locking v1.0 scope | | |

### Novel Concepts Invented During Discussion

| Concept | Author | Round | Description |
|---------|--------|-------|-------------|
| Spoofing competence | Security Architect | R1 | STRIDE-adjacent threat: agents hiding hallucinated fields behind defensive defaults |
| Trust-flow analyzer | Systems Thinker | R1 | Reframing: types = what data is; trust tiers = how much to believe it |
| Parasitic, not parallel | Systems Thinker | R1 | Adoption strategy: extend existing Python machinery, don't create parallel systems |
| Type oracle protocol | System Architect | R1 | Abstract interface decoupling from specific type checkers |
| Semantic boundary enforcer | Tech Writer | R1 | Product category positioning to avoid linter/type-checker comparisons |
| Promotion protocol | Systems Thinker | R3 | Rules earn blocking status through measured precision over sustained evaluation |
| Provenance assertions | Security Architect | R3 | Positive claims ("I assert Tier 2") vs. negative suppressions ("ignore this") |
| Two-artifact ratification | Tech Writer | R3 | Inline annotation inert until manifest entry committed by human |
| Manifest = corpus = event log | Quality Engineer | R3 | Single artifact serving three purposes |
| Boundary-anchored taint | Python Engineer | R3 | Tag functions not data; static taint from `@external_boundary` to `@validates_external` |
| Narrow TrustEnvelope | SDLC Engineer | R3 | Nanosecond-lifetime runtime wrapper for test-mode calibration |
| Adversarial evasion corpus | Security Architect | R5 | Code that looks compliant but isn't — tests the tool's resilience to gaming |
| Agent vs. human profiles | Systems Thinker | R5 | Default-block for agents (no memory), promotion protocol for humans |
| Pre-generation self-check | Python Engineer | R5 | `--stdin` mode for agents to validate before submitting |
| Volume floor for promotion | Quality Engineer | R5 | ≥50 firings required before precision calculation is meaningful |
| Epistemic severity categories | Tech Writer | R6 | Blocking = tool authoritative; advisory = developer context legitimate |
| Scope-dissolves-tension | Quality Engineer | R6 | Narrowing tool scope to trust-only rules eliminates suppression debate |

### Position Evolution Map

Every agent shifted position during the 8-round discussion:

| Agent | Round 1 | Round 8 | Key Inflection |
|-------|---------|---------|---------------|
| Security Architect | Block everything day one | Promotion protocol + per-rule birth severity | Systems thinker's adoption dynamics (R2) |
| System Architect | AST-only is sufficient | AST + Annotated metadata + structural @validates verification | Python engineer's 40% gap challenge (R2) |
| Systems Thinker | Level 6 (advisory information) | Level 4 (self-organizing promotion protocol) with blocking enforcement | Quality engineer's "advisory gets ignored" (R2) |
| Python Engineer | Runtime tagging essential | **"I was wrong."** Fully static with boundary-anchored taint | 4v1 challenge: serialization, coverage, ecosystem, scope (R2) |
| Quality Engineer | Suppression rate is key metric | Suppression rate invalid for agentic code; manifest IS corpus | Tech writer's "agents generate noqa" (R2) |
| SDLC Engineer | Zero runtime, period | Accepts narrow test-mode calibration (~40hrs) | Python engineer's 40% false confidence argument (R3) |
| Tech Writer | Primary risk is category framing | Primary risk is grammar drift + semantic field design | Rounds 2-3 showed framing was solved; vocabulary stability wasn't |

### Scribe's Closing Note

The most remarkable outcome of this discussion was the **convergence velocity**. Seven agents with genuinely different priors (security-first, adoption-first, feasibility-first, quality-first, framing-first, scope-first, systems-first) arrived at a unified design through structured adversarial debate. The steelman round (Round 3) was the inflection point — forcing agents to inhabit their opponents' positions produced syntheses that pure debate couldn't reach. Runtime tagging died (4v1 in Round 2), was reborn as test-mode calibration (Round 3), and the suppression model cracked open (Round 5) then resolved through scope narrowing (Round 6).

Three design moves deserve special recognition:
1. **Quality engineer's scope reframe** (Round 6): "If a rule belongs in this tool, it warrants manifest governance; rules fine with inline belong in ruff." This dissolved the suppression tension by redefining what the tool is.
2. **Systems thinker's promotion protocol** (Round 3): Rules earn blocking status through measured precision. This bridged the advisory-vs-blocking divide with a self-organizing mechanism.
3. **Python engineer's "I was wrong"** (Round 5): Runtime tagging was a reasonable Round 1 proposal that didn't survive four independent critiques. The replacement — boundary-anchored static taint — is strictly better by the group's own criteria.

The discussion produced 17 novel concepts, resolved 7 major tensions, and left only 2 priority questions requiring pre-implementation resolution (per-rule birth severity and annotation naming) — both with clear resolution venues (the grammar doc). The spec is ready for Sprint 0.

---

*Minutes concluded. 2026-03-07. Eight rounds, seven agents, one spec.*
