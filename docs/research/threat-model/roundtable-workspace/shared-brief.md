# Semantic Boundary Enforcer — Adversarial Design Roundtable

## Shared Brief for All Participants

### Problem Statement

Design a semantic boundary enforcer for Python that detects when AI-generated code violates trust boundaries in high-assurance systems. The tool must:

1. Use only Python's stdlib `ast` module (zero external dependencies for the core analysis engine)
2. Operate as a CI gate and pre-commit hook
3. Produce SARIF output (Static Analysis Results Interchange Format)
4. Enforce that untrusted external data passes through validated boundaries before entering trusted internal processing

### The Core Challenge

Python's type system doesn't distinguish data by provenance — a `dict` from an API and a `dict` from a database are the same type. The tool must catch violations that are:

- Syntactically valid
- Test-passing
- Look like good defensive Python (`.get()` with defaults, broad `except` blocks, `hasattr()` gates)
- But are semantically dangerous in systems where silent data corruption is worse than a crash

The tool will primarily analyse code written by AI agents, which produce these patterns systematically due to training data bias toward "defensive" programming.

### Existing Production Baseline

The ELSPETH project already runs a pattern-matching tier model enforcer (`scripts/cicd/enforce_tier_model.py`) as a CI gate. It:

- Uses Python's `ast` module to detect defensive anti-patterns (`.get()` with defaults on typed data, broad `except` clauses, `hasattr()` usage)
- Maintains a per-module YAML allowlist with expiry dates, rationales, and reviewer identity
- Generates fingerprints for each finding to track allowlist entries
- Catches 1-2 violations per day in production agentic development
- Has structural limitations: no cross-function data flow tracing, no verification that validator decorators actually validate, no contextual distinction of pattern usage

### Proposed Enhancement (from Discussion Paper Appendix B)

The design upgrades the pattern-matching gate to AST-based taint analysis with:

**Declaration model:**
```python
@external_boundary          # Returns untrusted data
def fetch_api_data(): ...

@validates_external         # Validates external data (must contain control flow)
def validate_response(): ...
```

Plus a built-in heuristic list for common external call sites (`requests.*`, `httpx.*`, `json.loads`, etc.)

**Two-pass analysis:**
1. Symbol collection: AST walk to build boundary/decorator/external-call table
2. Rule evaluation: Trust-relevant rules + intra-function taint tracing

**Structural verification:** `@validates_external` functions must contain control flow (`try/except`, `isinstance()`, `raise`, `if/else`)

**Governance model:**
- `strict.toml` manifest with trust topology, boundary functions, rule config, structured exceptions
- CODEOWNERS-protected manifest; exceptions require separate prior commit (temporal separation)
- Dual enforcement profiles: human code = graduated promotion; agent code = blocking by default
- Rules earn blocking status through measured precision (>95% over 50+ firings)

**Verification properties (assurance argument):**
1. Golden corpus (labelled TP/TN/adversarial samples, 3 TP + 2 TN per rule minimum)
2. Self-hosting gate (tool passes its own rules from first commit)
3. Measured precision with volume floor
4. Deterministic output (byte-identical on identical input)

### Three-Tier Trust Model (from ELSPETH CLAUDE.md)

| Tier | Trust Level | Handling |
|------|------------|----------|
| Tier 1: Audit Database | FULL TRUST | Crash on any anomaly. No coercion ever. |
| Tier 2: Pipeline Data | ELEVATED TRUST | Types trustworthy, values may fail operations. No coercion. |
| Tier 3: External Data | ZERO TRUST | Validate at boundary, coerce where possible, quarantine failures. |

**Key rule:** Coercion is allowed ONLY at Tier 3→Tier 2 boundary (sources) and at external call boundaries within transforms. Everywhere else, wrong data = crash.

### Defensive Programming Patterns to Detect

| Pattern | Why It's Dangerous |
|---------|-------------------|
| `.get("key", default)` on typed data | Fabricates values instead of crashing on corruption |
| `getattr(obj, "attr", default)` on annotated objects | Hides missing attributes that indicate bugs |
| `hasattr(obj, "attr")` | Swallows all exceptions including from `@property` getters |
| Broad `except Exception` on audit paths | Destroys evidence trail |
| `try/except` around Tier 1 reads | Prevents crash-on-corruption |
| Silent `pass` in except blocks | Swallows errors entirely |
| `isinstance()` checks on internal data | Implies uncertainty about types we control |

### ACF Taxonomy (from Discussion Paper)

The tool addresses 13 Agentic Code Failure modes. Key ones:
- **ACF-I1** (Critical): Silent data fabrication via defaults
- **ACF-I2** (Critical): Trust boundary bypass — external data entering internal stores without validation
- **ACF-I3** (High): Audit trail destruction via broad exception handling
- **ACF-S3** (High): Structural identity spoofing via `hasattr()` gate bypass
- **ACF-D1** (High): Review process denial-of-service via finding volume

### Scope Constraints

- v0.1: Intra-function taint analysis only (inter-procedural deferred to v1.0)
- Zero external dependencies for core engine (stdlib `ast` only)
- Must work as: pre-commit hook, CI gate, agent self-check (`--stdin` mode)
- SARIF output format
- Standalone PyPI package delivery

### What This Roundtable Must Decide

1. **Architecture:** How should the two-pass analysis be structured? What data structures? How does taint propagate?
2. **Rule engine:** How are rules defined, composed, and evaluated? Static registry vs. plugin model?
3. **Governance:** Is the dual enforcement profile (human vs. agent) sound? Is temporal separation of manifest changes enforceable?
4. **Allowlist management:** Per-finding fingerprints? Expiry model? What prevents allowlist bloat?
5. **Taint model:** How does taint flow through assignments, function calls, container operations? What are the limits of intra-function analysis?
6. **False positive management:** How do we calibrate precision? What's the promotion protocol for rules?
7. **Self-hosting:** What does it mean concretely for this tool to pass its own rules?
8. **Testing strategy:** Golden corpus structure, adversarial evasion samples, regression testing
9. **Performance:** Budget for pre-commit hook latency? CI gate timeout?
10. **Deployment:** PyPI package structure, CLI interface, configuration format
