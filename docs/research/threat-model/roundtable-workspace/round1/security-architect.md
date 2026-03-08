# Round 1 — Opening Position: Sable (Security Architect)

## Summary Position

The semantic boundary enforcer's central challenge is not pattern detection — the existing `enforce_tier_model.py` already demonstrates that — but **taint provenance**: proving that data from a specific trust tier has (or has not) crossed a validation boundary before reaching a trust-dependent operation. The tool must model three distinct trust boundary crossings as AST-observable events, and the governance model must withstand adversarial pressure from agents that have no concept of "why" a rule exists — only that it blocks their output. My primary concern is that intra-function taint analysis is necessary but insufficient for the critical failure modes (ACF-T1, ACF-R1), and that the allowlist governance model has a subtle denial-of-service surface through allowlist entropy growth.

## Detailed Analysis

### 1. Trust Boundary Model: Mapping Three Tiers to AST Observables

The ELSPETH three-tier trust model defines three boundary crossings that the tool must detect:

| Crossing | Direction | AST Observable | What Must Happen |
|----------|-----------|----------------|------------------|
| **Tier 3 → Tier 2** | External → Pipeline | Return value of `@external_boundary` function or heuristic-matched call (`requests.get()`, `json.loads()`, etc.) | Value must pass through `@validates_external` before use in pipeline operations |
| **Tier 2 → Tier 1** | Pipeline → Audit | Arguments to functions that write to Landscape tables (recorder methods, `conn.execute(insert(...))` on audit tables) | Values must be the output of validated pipeline operations; no raw external data may reach audit writes |
| **Tier 1 → read path** | Audit → Internal | Return values from Landscape reads, checkpoint deserialization | Must NOT be wrapped in defensive handling (`.get()`, `try/except` with fallback) — these are Tier 1 reads that should crash on corruption |

The first two crossings are **taint propagation** problems: track where untrusted data flows and verify it passes through a validator. The third is an **anti-pattern** problem: detect defensive handling where offensive handling is required.

**The critical distinction the tool must encode:** the same syntactic pattern (e.g., `try/except`) is *required* at a Tier 3 boundary (wrapping an external API call) and *forbidden* at a Tier 1 boundary (wrapping a Landscape read). This is context-dependent semantics that no general-purpose linter can express. The `strict.toml` manifest must declare which functions are Tier 1 read paths, Tier 1 write paths, and Tier 3 entry points — the tool cannot infer this from syntax alone.

**Concrete proposal for boundary declaration:**

```toml
[trust_topology]

# Tier 3 entry points — return untrusted data
external_boundaries = [
    "requests.*",
    "httpx.*",
    "json.loads",
    "urllib.request.*",
]

# Tier 1 read paths — defensive handling is forbidden
audit_read_paths = [
    "elspeth.core.landscape.recorder.*",
    "elspeth.core.checkpoint.*",
]

# Tier 1 write paths — external data must not reach these without validation
audit_write_paths = [
    "elspeth.core.landscape.recorder.record_*",
    "elspeth.core.landscape.recorder.update_*",
]
```

This topology is the security-critical configuration. It must be complete (a missing entry means a boundary crossing goes undetected) and correct (a wrong entry produces false positives that erode trust in the tool). The CODEOWNERS protection is necessary but not sufficient — see Section 2.

### 2. Attack Surface of the Tool Itself

The adversary model here is unusual: the "attacker" is not malicious in intent but systematic in effect. An AI agent that generates `.get()` with defaults or broad `except` blocks is not trying to circumvent the tool — it is producing the patterns its training data taught it. But when the tool blocks that output, the agent will try alternative approaches, and some of those alternatives may circumvent the tool's detection capability without being intentionally adversarial.

**Threat 1: Decorator spoofing (ACF-S3 applied to the tool itself).** An agent could learn that adding `@validates_external` to a pass-through function satisfies the taint checker. The structural verification requirement (must contain control flow) mitigates this partially, but consider:

```python
@validates_external
def "validate"(data):
    if True:  # Structural control flow present — checker satisfied
        return data  # No actual validation performed
```

The tool verifies *presence* of control flow, not *semantic adequacy* of validation. This is a fundamental limitation of static analysis — the tool cannot determine whether an `isinstance()` check is meaningful or trivial. **Mitigation:** The golden corpus must include adversarial evasion samples of exactly this form. The structural verification should require at least one `raise` statement or one explicit rejection path (return of an error type), not just any control flow.

**Threat 2: Taint laundering through intermediate variables.** Even within intra-function scope:

```python
response = requests.get(url).json()  # Tainted
clean_data = dict(response)          # Is this still tainted?
process(clean_data)                  # Taint lost through copy?
```

The taint model must propagate through assignments, container constructors (`dict()`, `list()`, `{**x}`), and common transformation patterns. Every propagation rule is a potential evasion surface — if `dict(tainted)` drops taint, agents will learn to launder through `dict()`.

**Threat 3: Allowlist entropy as a denial-of-service vector (ACF-D1 applied to governance).** Each finding requires either a code fix or an allowlist entry. If the tool produces many findings on agent-generated code (which is the expected case), the allowlist grows. Large allowlists are:

- Harder to review (each entry requires human evaluation of the rationale)
- More likely to contain stale entries (entries whose underlying code has changed)
- A normalization vector ("we always add allowlist entries, it's just process")

The expiry mechanism helps but introduces its own overhead: expired entries require re-evaluation, which is itself a review burden. **Proposal:** Track allowlist growth rate as a health metric. If allowlist entries per rule exceed a threshold, that rule's precision or the codebase's boundary declarations need attention — the allowlist is absorbing a structural problem.

**Threat 4: Temporal separation circumvention.** The governance model requires manifest changes in a separate, prior commit. This prevents an agent from generating a violation and its exception simultaneously. But consider:

- Agent commit 1: Adds `@validates_external` decorator to a new function (manifest change? or code change?)
- Agent commit 2: Writes code that routes tainted data through the new "validator"

If decorators are treated as code (not manifest), the temporal separation doesn't apply to the most direct circumvention path. If decorators are treated as manifest, every new `@validates_external` function requires a separate commit — adding friction to legitimate development. **Recommendation:** Decorators are code; the manifest in `strict.toml` is governance. The manifest declares *which decorators exist and what they mean*, but adding a decorated function is a code change. The structural verification of the decorated function is the tool's responsibility, not the governance model's.

### 3. Taint Propagation for Critical ACF Failure Modes

**ACF-T1 (Trust Tier Conflation — Critical):** This is the tool's primary target. The taint model needs:

- **Source tainting:** Return values of external boundary functions are tainted
- **Propagation:** Taint flows through assignment, unpacking, iteration, indexing, attribute access on the tainted object
- **Sink detection:** Tainted values reaching audit write paths or being used as arguments to Tier 1 operations
- **Sanitization:** Passing through a `@validates_external` function removes taint

For v0.1 (intra-function), the critical gap is: what happens when tainted data is passed as an argument to a helper function that then writes to the audit trail? The call crosses a function boundary — the taint is lost. This means ACF-T1 detection in v0.1 is limited to cases where the external call and the audit write are in the *same function*. In ELSPETH's architecture, this is actually common in transforms (the `process()` method calls an LLM API and returns a `TransformResult`), but it misses cases where data flows through utility functions.

**ACF-R1 (Audit Trail Destruction — High):** This requires detecting broad `except` blocks around audit-critical operations. The existing enforcer (R4, R6 rules) partially covers this, but lacks context: it flags all broad `except` blocks, not just those around Tier 1 write operations. The enhanced tool should:

- Flag `try/except Exception` (or broader) when the `try` body contains calls to audit write paths
- Distinguish between `except` blocks that re-raise (acceptable — they're adding context) and those that log-and-continue (dangerous — they absorb the failure)
- Track whether the `except` block returns, raises, or falls through — only "continues past the audit operation" is dangerous

**ACF-S1 (Competence Spoofing — High):** The `.get()` with default pattern. The existing enforcer catches this syntactically (R1). The enhanced version should additionally flag:

- `or` chains that provide fallback values: `value = data.get("field") or "default"` — the `or` adds a second layer of fabrication
- Ternary defaults: `value = data["field"] if "field" in data else "default"` — semantically identical to `.get()` but syntactically different
- f-string interpolation of `.get()` results: the fabricated value becomes part of a string that looks like real data

### 4. Defence-in-Depth: Layering with Existing Controls

The semantic boundary enforcer fills a specific gap in the existing tool chain:

| Layer | Tool | What It Catches | What It Misses |
|-------|------|-----------------|----------------|
| Type shape | mypy/pyright | Wrong types, missing attributes | Data provenance (same type, different trust) |
| Style/idiom | ruff | PEP 8, import order, dead code | Semantic correctness |
| Known vulns | bandit | SQL injection, hardcoded passwords | Project-specific trust violations |
| **Trust boundaries** | **This tool** | **Taint flow, defensive patterns on trusted data, audit trail protection** | **Inter-procedural flow (v0.1), semantic adequacy of validators** |
| Behavioural | pytest + golden corpus | Actual output correctness | Coverage gaps, untested paths |
| Audit integrity | Landscape self-checks | Post-hoc corruption detection | Prevention (after the fact) |

**Residual risk after deployment:** The tool catches syntactically detectable boundary violations but cannot verify:

1. That a validator actually validates the right things (semantic adequacy)
2. That inter-procedural taint flows are clean (v0.1 limitation)
3. That runtime data matches the types the tool assumed at analysis time
4. That the trust topology in `strict.toml` is complete and correct

Items 1 and 4 are fundamental limitations of static analysis. Item 2 is a scope deferral. Item 3 is out of scope for a static tool entirely. **The tool's value proposition is not eliminating these risks but reducing the attack surface that humans must manually review** — converting an open-ended "review everything" into a bounded "review the allowlist entries and the trust topology."

### 5. Key Design Concern

**Most important thing to get right:** The taint propagation model must be *conservative* (over-approximate). If the tool is unsure whether taint propagates through an operation, it must assume it does. A false negative (missed taint flow) is a security hole. A false positive (spurious taint) is a nuisance that can be allowlisted.

**Most likely thing to get wrong:** The boundary between "the tool's analysis" and "the tool's configuration" (the `strict.toml` manifest). If too much is hardcoded, the tool is brittle and project-specific. If too much is configurable, the configuration becomes a security-critical attack surface — an incomplete trust topology silently disables detection for the missing boundaries. The manifest needs a completeness check: for any function that calls an external API (detectable by the heuristic list), there should be a corresponding boundary declaration or an explicit "this is not a trust boundary because..." entry. Undeclared external calls should be warnings, not silent passes.

## Key Design Proposal

**Undeclared external call detection.** In addition to the taint analysis (which operates on *declared* boundaries), the tool should perform a completeness scan: walk the AST for calls matching the heuristic external call list, and for each one, verify that either (a) it occurs inside a function decorated with `@external_boundary`, or (b) there is an explicit suppression in the manifest declaring why this call is not a trust boundary. An external call that is neither declared nor suppressed is a **configuration gap** — the trust topology is incomplete.

This inverts the default from "undeclared calls are assumed safe" to "undeclared calls are assumed dangerous." It is the static analysis equivalent of a default-deny firewall: everything that crosses the boundary must be declared, and undeclared crossings are flagged.

For v0.1, this scan can operate independently of the taint analysis — it is a simple pattern match (like the existing enforcer) augmented with manifest lookup. It provides value even before the full taint propagation engine is complete.

## Risk Assessment

**What worries me most:** The governance model's resilience under sustained agentic development pressure. The temporal separation of manifest changes is a good control for intentional circumvention, but the larger risk is **governance fatigue**. When the tool produces 10 findings per day and each requires either a code change or an allowlist entry with rationale, expiry, and reviewer — the humans in the loop will start rubber-stamping allowlist entries. The allowlist becomes a permission ledger rather than an exception log.

The measured precision requirement (>95% over 50+ firings) partially addresses this by ensuring rules don't cry wolf. But precision is necessary and not sufficient — a rule can be 100% precise (every finding is a real violation) and still produce governance fatigue if the violation is common and the fix is non-trivial. The system needs to distinguish between "this rule is noisy" (precision problem — demote it) and "this rule catches real violations that are hard to fix" (architecture problem — fix the codebase, not the rule).

**Second concern:** The self-hosting property creates a bootstrap problem. The tool must pass its own rules from the first commit, but its own rules include taint analysis, and the tool's own code handles external data (reading source files, parsing TOML manifests). If the tool's input parsing is not annotated with trust boundaries, the self-hosting gate doesn't exercise the taint analysis rules. The tool should treat file I/O as a Tier 3 boundary in its own code — it reads arbitrary Python files and TOML manifests that could contain anything. This makes self-hosting meaningful: the tool must correctly mark its own external data entry points and validate at those boundaries, and then its own taint analysis must verify that it did.
