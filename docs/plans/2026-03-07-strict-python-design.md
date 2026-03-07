# Strict Python — High-Level Design

**Date:** 2026-03-07
**Status:** Design complete, pending Sprint 0 (grammar doc)
**Source:** [Roundtable minutes](strict-python-roundtable-minutes.md) — 8 rounds, 7 specialist agents
**Allocation:** ~20-30% of annual coding time (alongside 60% ELSPETH, 10% Filigree)

---

## 1. Problem Statement

Python's duck typing and permissive defaults make it hostile to secure, auditable code — especially when AI agents generate code at scale. The core threat isn't malicious code; it's **plausible-but-wrong code at volume**. Agents produce code that passes tests, looks correct, and silently violates trust boundaries because their training data is saturated with defensive anti-patterns (`.get()`, `getattr` with defaults, bare `except`).

Existing tools address adjacent problems but not this one:

| Tool | What It Catches | What It Misses |
|------|----------------|----------------|
| **mypy/pyright** | Type shape mismatches | Data provenance (a `str` from an API and a `str` from our DB are the same type but different trust tiers) |
| **ruff/flake8** | Style violations, simple anti-patterns | Semantic boundary crossings, trust tier flow |
| **bandit** | Known vulnerability patterns | Project-specific trust topology, institutional knowledge |
| **semgrep** | Custom pattern rules | Trust tier propagation, promotion governance |

The gap: no tool enforces **"where did this data come from and has it been validated?"** as a static, project-specific, machine-checkable property.

## 2. What This Tool Is (and Isn't)

**Category:** Semantic boundary enforcer — not a linter, not a type checker, not a language fork.

**One paragraph:** A standalone, zero-dependency AST-based analyzer for Python that enforces trust boundaries through developer-declared annotations. It reads a project-level manifest (`strict.toml`) declaring trust topology, layer rules, and boundary functions. It performs intra-function taint analysis, tracing values from external boundary functions through to validation functions, and flags unterminated taint paths. Rules follow a promotion protocol: advisory rules earn blocking status through measured precision; agent-authored code defaults to blocking. Output is SARIF. Valid Python in, valid Python out — no custom syntax, no runtime dependency, full ecosystem compatibility.

**Key principle — "parasitic, not parallel":** The tool extends Python's existing machinery (annotations, decorators, `typing.Annotated`) rather than creating parallel systems. It is an additional analysis pass over standard Python, not a dialect.

## 3. Considered Alternatives

### 3.1 Custom Python Variant (not progressed)

The original thought was whether a Python fork or transpiler could remove the "softness" at the language level — stricter typing, mandatory boundary declarations, etc. This was evaluated and deliberately set aside:

- **Ecosystem orphaning risk:** A Python variant that diverges from CPython becomes unmaintainable as Python evolves. Every PyPI package, every framework, every IDE integration assumes standard Python.
- **Adoption cliff:** Requiring teams to switch languages (even a superset) is a Level 2 intervention (rules/incentives) that meets maximum resistance. The tool needs to work *with* existing Python codebases, not replace them.
- **Maintenance burden:** Tracking CPython's release cadence, grammar changes, and stdlib evolution is a full-time project. The 20-30% allocation can't sustain it.
- **The real insight:** The problems we want to solve (trust boundary enforcement, defensive pattern detection, provenance tracking) are analyzable *over* standard Python. We don't need to change the language — we need to add an analysis layer that Python's existing annotation system already supports.

This option remains available for future evaluation if the analysis-layer approach proves fundamentally insufficient, but current evidence strongly favours the parasitic approach.

### 3.2 Runtime Trust Tagging (rejected, Round 2)

Attaching `__trust_tier__` metadata to values at runtime for zero-false-positive provenance tracking. Killed 4v1 in the roundtable:

- **Coverage gap:** Only catches violations on executed paths — catastrophic false negative rate on untested branches (the exact failure mode we care about most)
- **Serialization erasure:** Tags vanish at `json.dumps()`, `pickle`, database writes, DataFrame operations — creating false confidence
- **Ecosystem friction:** Every library that doesn't preserve tags becomes an unwitting adversary. Thousands of libraries would need patching
- **Scope explosion:** Estimated 400-hour separate project, not a phase of the static tool

**Partial resurrection:** A narrow `TrustEnvelope` wrapper (~40 hours) survives as a **test-mode calibration mechanism** — wrapping external call returns in test suites to discover where the static analyzer has gaps. Lives nanoseconds (call → validation), never reaches serialization boundaries, never deployed to production.

### 3.3 mypy/ruff Plugin (cautious)

Building as a plugin to an existing tool ecosystem risks orphaning if the host tool changes direction or is superseded. The tool uses stdlib `ast` only, with a **type oracle protocol** (abstract interface) that mypy/pyright/future tools can optionally satisfy. The core analysis is never dependent on any external tool.

## 4. Architecture

### 4.1 Analysis Engine

```
┌─────────────────────────────────────────────────────────────┐
│                       strict.toml                           │
│  Trust topology · Layer rules · Boundary declarations       │
│  Structured exceptions (rationale + reviewer + expiry)      │
│  CODEOWNERS protected · Temporal separation (prior commit)  │
│  [context] agent_mode = "default_block"                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────┐                       │
│  │  Pass 1:     │───►│  Pass 2:     │──► SARIF output       │
│  │  Symbol      │    │  Rule        │    (suppressions       │
│  │  Collection  │    │  Evaluation  │     field NEVER        │
│  └──────────────┘    └──────────────┘     populated)         │
│        │                    │                                │
│        ▼                    ▼                                │
│  Reads:                 Checks:                              │
│  · @external_boundary   · Forbidden patterns                │
│  · @validates_external  · Unterminated taint paths           │
│  · Annotated[T, TierN]  · Missing annotations               │
│  · Known call sites     · Trust tier violations              │
│    (heuristic list)     · @validates structural integrity    │
│                                                             │
│  Modes: CLI · pre-commit · CI · --stdin (agent self-check)  │
└─────────────────────────────────────────────────────────────┘
```

**Two-pass design:** Pass 1 (symbol collection) walks the AST to build a table of annotated functions, decorated boundaries, and known external call sites. Pass 2 (rule evaluation) applies rules against the collected symbols. This separation lets rule authors write rules without understanding the collector.

**Zero external dependencies:** Core analysis uses only stdlib `ast`. No mypy, no ruff, no third-party AST libraries. The `ast` module is part of the Python language spec and changes only when the grammar changes — maximum survivability.

**Intra-function taint only (v0.1):** Traces values from `@external_boundary` return points through local assignments within a single function. Flags if tainted values reach non-validator calls without passing through `@validates_external`. Inter-procedural analysis is explicitly v0.2+ scope.

### 4.2 Annotation Vocabulary

Developers declare trust boundaries using standard Python annotations and decorators:

```python
from strict_python import external_boundary, validates_external
from typing import Annotated
from strict_python.tiers import Untrusted, Validated, Trusted

@external_boundary
def fetch_user_data(user_id: str) -> Annotated[dict, Untrusted]:
    """Returns are automatically tainted — must pass through validation."""
    return requests.get(f"/api/users/{user_id}").json()

@validates_external
def validate_user(raw: Annotated[dict, Untrusted]) -> Annotated[UserRecord, Validated]:
    """Must contain control flow (try/except, isinstance, raise)."""
    if not isinstance(raw, dict):
        raise ValidationError("Expected dict")
    try:
        return UserRecord(
            name=str(raw["name"]),
            email=str(raw["email"]),
        )
    except KeyError as e:
        raise ValidationError(f"Missing field: {e}") from e

def process_user(user_id: str) -> None:
    raw = fetch_user_data(user_id)     # raw is tainted (Untrusted)
    user = validate_user(raw)          # user is validated — taint cleared
    save_to_db(user)                   # OK — validated data

    # BAD: direct use of tainted data without validation
    save_to_db(raw)  # ← FINDING: unterminated taint path
```

**Naming is an open design question (ODQ-4).** The vocabulary above uses abstract names (`Untrusted`/`Validated`/`Trusted`) rather than ELSPETH-specific tier numbers, for generalisability. Final naming is resolved in the grammar doc (Sprint 0).

### 4.3 Known External Call Site Heuristic List

A built-in list of known external call patterns for auto-detection without manual annotation:

- `requests.*`, `httpx.*` — HTTP clients
- `sqlalchemy.*.execute` — database queries
- `json.loads` — deserialization boundary
- `subprocess.*`, `os.system` — shell execution
- `open()` (file I/O when reading external data)
- `socket.*` — network I/O

This list is a v0.1 deliverable. It needs a spec home (where the list lives in the package) and a contribution process (how users add project-specific entries via `strict.toml`).

### 4.4 `strict.toml` Manifest

The root configuration artifact declaring the project's trust topology:

```toml
[meta]
schema_version = 1

[context]
agent_mode = "default_block"   # Agents get blocking by default

[trust_topology]
# Declare project-specific trust layers
layers = ["external", "pipeline", "audit"]

[boundaries]
# Project-specific boundary function patterns
external_call_patterns = [
    "elspeth.plugins.infrastructure.clients.*",
    "litellm.*",
]

[rules]
# Per-rule configuration
[rules.unterminated_taint]
severity = "blocking"          # Birth severity (justified in grammar doc)
finding_cap = 10               # Per-file cap

[rules.defensive_get_on_typed]
severity = "advisory"
finding_cap = 25

[allowlist]
# Structured exceptions — blocking rules only
[allowlist.architectural]
# High-scrutiny exceptions for trust boundary rules
[[allowlist.architectural.entries]]
file = "src/elspeth/plugins/sources/csv_source.py"
rule = "unterminated_taint"
lines = [42, 43]
rationale = "CSV reader returns pre-validated rows via pandas schema enforcement"
reviewer = "john"
expires = "2026-06-07"

[promotion]
# Promotion protocol thresholds
min_precision = 0.95
min_firings = 50               # Volume floor (ODQ-3: 20 vs 50, TBD)
```

**CODEOWNERS protection:** `strict.toml` is protected by repository CODEOWNERS. Changes require human approval.

**Temporal separation:** `strict.toml` ratification must occur in a **prior or separate commit** from the source code changes it governs. CI verifies this via git plumbing (~30 lines). This prevents agents from simultaneously generating a violation and its exception in the same commit.

## 5. Enforcement Model

### 5.1 Promotion Protocol

Rules follow a lifecycle from advisory to blocking, earned through measured performance:

```
HUMAN PATH:
  Advisory ──[>95% precision over ≥50 firings]──► Blocking

AGENT PATH:
  Blocking ──[>FP threshold on agent code]──► Advisory (demotion)
```

- **Human-authored code:** Rules start advisory. When a rule achieves >95% true positive rate sustained over a volume floor of firings, the tool **proposes** promotion by writing a `pending_promotions` entry. A human merges the PR (CODEOWNERS-gated).
- **Agent-authored code:** Rules start blocking (agents have no cross-session memory — advisory warnings they'll never see again are useless). Rules that prove too noisy on agent-authored code get demoted to advisory for agents via the same PR workflow.

The volume floor prevents promotion on small samples (a rule that fired 3 times with 100% precision has proven nothing).

### 5.2 Suppression Model

| Rule Severity | Exception Mechanism | Governance |
|---------------|--------------------|----|
| **Blocking** | Manifest-only (`strict.toml` allowlist entry) | Requires rationale, reviewer, expiry date. CODEOWNERS-gated PR. |
| **Advisory** | Structured inline: `# strict-ok: rule=X, rationale="Y"` | 90-day auto-expiry. Self-sufficient — no manifest entry needed. |

**No `# noqa`-style suppression — ever.** The inline annotation format is structured (machine-parseable fields), not a bare comment. Agent-generated suppress comments are detectable because they must follow the structured format, and blocking-severity rules can't be suppressed inline at all.

**Design principle (quality engineer's reframe):** If a rule belongs in this tool, it targets trust violations that warrant manifest governance. Rules that would be fine with bare inline suppression belong in ruff, not here. This scope constraint dissolves the suppression friction debate.

### 5.3 `@validates` Structural Verification

A function decorated with `@validates_external` must contain **control flow** in its body — at least one of: `try/except`, `isinstance()` check, `raise` statement, or `if/else` branching. A function that just returns its input doesn't qualify as validation.

This prevents agents from satisfying the taint checker by adding `@validates_external` to a pass-through function — the decorator is a claim that the function validates, and the AST verifies the claim structurally.

## 6. Quality Model

### 6.1 Golden Corpus

A collection of labeled Python snippets — the calibration instrument for the promotion protocol:

- **Minimum per rule:** 3 true positives + 2 true negatives
- **Adversarial evasion samples:** Code that looks compliant but isn't — tests the tool's resilience to gaming (e.g., a function named `validate_and_parse()` that does no validation)
- **Expected `violation_explanation` values** as labels (corpus must be built after semantic finding fields are specified)
- **Source material:** ELSPETH's 191 documented bugs for true positive specimens; ELSPETH's signed-off code for true negative specimens

The corpus is a first-class artifact, version-controlled, and a v0.1 ship gate.

### 6.2 Self-Hosting Gate

The tool's own source code must pass its own rules from commit one. If we can't write the tool to its own standards, we don't understand the standards. This is a CI gate, not a nice-to-have.

### 6.3 Output Format

**SARIF** (Static Analysis Results Interchange Format) from day one. Standard format consumed by GitHub Code Scanning, Filigree dashboard, and arbitrary CI systems.

Critical constraint: the SARIF `suppressions` field is **never populated**. Suppression state lives in the manifest only. If SARIF includes suppression data, downstream consumers (including agents) learn which findings are "ignorable."

Each finding includes semantic fields:

- `violation_explanation` — human-readable trust model explanation (e.g., "Value from `requests.get()` reaches `save_to_db()` without passing through a validation function")
- `grammar_rule` — reference to the annotation vocabulary spec rule

These fields serve double duty: they teach agents the trust model through the CI feedback loop, and they provide the expected-value labels for the golden corpus.

## 7. Threat Model (Tool's Own)

The tool itself is an attack surface. STRIDE analysis:

| Threat | Attack | Mitigation |
|--------|--------|------------|
| **Tampering** | Agent modifies `strict.toml` alongside source changes to suppress its own violations | CODEOWNERS on `strict.toml` + temporal separation (ratification in prior commit, CI-verified) |
| **Spoofing** | Agent adds `@validates_external` to a non-validating function | AST structural check: function body must contain control flow (try/except, isinstance, raise) |
| **DoS** | Finding flood causes reviewers to rubber-stamp | Per-rule finding cap per file (threshold 5-25, set empirically in Sprint 1) |
| **Spoofing competence** | Agent hides hallucinated fields behind `getattr(obj, "field", default)` | Core detection rule: `.get()`/`getattr` with defaults on typed objects |

## 8. Resolved Design Decisions (13)

All confirmed with zero objections in Round 8 of the roundtable.

| # | Decision | Support |
|---|----------|---------|
| 1 | `strict.toml` is root artifact with CODEOWNERS protection | 7/7 |
| 2 | Annotation vocabulary/grammar doc ships before enforcement code | 7/7 |
| 3 | Tool proposes promotions, human approves via PR merge | 7/7 |
| 4 | Agent mode: `default_block`, inverse of human graduated path | 7/7 |
| 5 | Golden corpus is first-class artifact and v0.1 ship gate | 7/7 |
| 6 | Self-hosting gate from first commit | 6/7 |
| 7 | Temporal separation: `strict.toml` ratification in prior commit, CI-enforced | 6/7 |
| 8 | `@validates` structural verification — must contain control flow | 6/7 |
| 9 | SARIF output; never populate suppressions field | 6/7 |
| 10 | Intra-function taint only in v0.1 — no inter-procedural | 7/7 |
| 11 | Zero external dependencies in core (stdlib `ast` only) | 7/7 |
| 12 | Rule inclusion criterion: trust-relevant only; style/idiom belongs in ruff | 5/7 |
| 13 | Suppression: blocking = manifest-only; advisory = structured inline with 90-day expiry | 6/7 |

## 9. Open Design Questions

### Priority (resolve before implementation)

**ODQ-2: Per-rule birth severity**
Should v0.1 rules ship blocking or advisory from birth? Three positions:

- Ship blocking for trust boundary rules (they're authoritative by definition)
- Ship all advisory until Sprint 1 data proves precision (consistent with promotion protocol)
- Decide per-rule in the grammar doc with one-line justification (process answer)

**Resolution venue:** The grammar doc (Sprint 0). Each rule gets a birth severity with written justification. This is the #1 priority — 5/7 agents voted it most important.

**ODQ-4: Annotation vocabulary naming**
Three naming styles under consideration:

- Abstract: `Trusted` / `Validated` / `Untrusted`
- Tier-numbered: `Tier1` / `Tier2` / `Tier3`
- Semantic: `@external_call` / `@validates_tier3`

**Resolution venue:** First implementation-phase task.

### Deferred (resolve during Sprint 1 / implementation)

| Question | Range | Resolution Path |
|----------|-------|-----------------|
| ODQ-1: Finding cap scope/value | 5-25 per-rule per-file, or 200 per-run | Sprint 1 measurement against ELSPETH |
| ODQ-3: Promotion `min_firings` default | 20 vs. 50 | Configurable; set default after Sprint 1 data |
| ODQ-5: Semantic finding fields spec | `violation_explanation` + `grammar_rule` | Resolve before corpus (corpus needs expected values) |
| ODQ-6: `--stdin` mode | ~10 lines wrapping core analyzer | Implement alongside core checker |

## 10. Delivery Plan

### v0.1 Deliverables

| Deliverable | Description |
|------------|-------------|
| Grammar doc | Annotation vocabulary + per-rule birth severity with justification |
| `strict.toml` manifest schema (v1) | Trust topology, boundaries, rules, allowlist, promotion config |
| AST-based checker | Two-pass analyzer, ~X00 [TBD] lines core, intra-function taint |
| Golden corpus | 3 TP + 2 TN per rule + adversarial evasion samples |
| SARIF output | With `violation_explanation` and `grammar_rule` semantic fields |
| Known external call heuristic list | Built-in auto-detection for `requests.*`, `httpx.*`, etc. |
| `--stdin` mode | Sub-200ms pre-generation agent self-check |
| Governance CI | `strict.toml` CODEOWNERS + temporal separation check |
| Self-hosting | Tool passes its own rules in CI |
| PyPI package | Standalone distribution, not an ELSPETH-internal script |

### v0.1 Process

| Phase | Scope | Hours |
|-------|-------|-------|
| **Sprint 0** | Grammar doc: annotation vocabulary, 8 initial rules with birth severity | ~20 |
| **Sprint 1** | Measurement: run candidate rules against ELSPETH, count external calls, measure FP rates, build initial corpus | ~40 |
| **Sprint 2** | Build: checker, strict.toml reader, SARIF output, --stdin, heuristic list | ~80 |
| **Sprint 3** | Calibrate: corpus expansion, adversarial samples, promotion threshold tuning, self-hosting validation | ~40 |
| **Sprint 4** | Ship: PyPI package, CI integration, CODEOWNERS + temporal check, documentation | ~40 |
| **Dogfood** | 4-6 weeks on ELSPETH before locking v1.0 scope | — |

**Total v0.1 estimate:** ~220 hours + dogfooding period

### v1.0 (post-dogfood, scope locked after 4-6 weeks)

Candidate scope (not committed):

- Inter-procedural taint analysis (function-to-function boundary tracking)
- Type oracle protocol (optional mypy/pyright enrichment)
- Narrow test-mode `TrustEnvelope` runtime calibration (~40 hours)
- LSP integration for editor-time feedback

### Architectural Dead-Ends (explicitly excluded)

| Approach | Why It's Excluded |
|----------|-------------------|
| Inter-procedural analysis in v0.1 | Compiler research territory — unbounded scope |
| Runtime tagging as core mechanism | Serialization erasure, ecosystem friction, coverage gaps, scope explosion |
| mypy/ruff plugin as primary delivery | Coupling risk to ecosystem that may change |
| Full Python dynamism support | Metaclasses, `__getattr__`, `exec`/`eval` — define a safe subset instead |

## 11. Relationship to ELSPETH

This tool generalises patterns that ELSPETH currently enforces manually via CLAUDE.md:

| ELSPETH CLAUDE.md Pattern | Strict Python Rule |
|--------------------------|-------------------|
| Three-tier trust model (Tier 1/2/3) | Trust topology in `strict.toml` + `Annotated[T, TierN]` |
| "Crash on Tier 1 anomaly" | Blocking rule: no defensive `.get()` on audit data |
| "Validate at boundary, coerce where possible" | Taint analysis: `@external_boundary` → `@validates_external` |
| `enforce_tier_model.py` allowlist | `strict.toml` allowlist (same pattern, generalised) |
| "No `.get()` on dataclasses" | Pattern rule: defensive access on typed objects |
| Layer dependency rules (L0-L3) | Trust topology layer enforcement |
| "Let it crash" for plugin bugs | Rule: no bare except in system-owned code |

ELSPETH is the first dogfooding target and the source of the golden corpus. The tool ships as a separate PyPI package — its value is general, not ELSPETH-specific.

---

*Design derived from roundtable minutes (2026-03-07, 8 rounds, 7 specialist agents). See [strict-python-roundtable-minutes.md](strict-python-roundtable-minutes.md) for full deliberation record including rejected alternatives, position evolution, and 17 novel concepts.*
