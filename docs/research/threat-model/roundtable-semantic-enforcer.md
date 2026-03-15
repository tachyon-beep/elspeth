# Semantic Boundary Enforcer — Adversarial Design Roundtable Synthesis

## 1. Executive Summary

This document specifies the design of a **semantic boundary enforcer** for Python — a static analysis tool that detects when code violates trust boundaries in high-assurance systems. The design was produced through five rounds of adversarial deliberation by seven specialist agents, each bringing a distinct competency to the problem. The tool replaces ELSPETH's existing pattern-matching tier model enforcer (`enforce_tier_model.py`) with AST-based taint analysis that tracks data provenance and validation status as independent dimensions, producing provenance-aware severity grading for every finding.

### Participants

| Agent | Role | Primary Contribution |
|-------|------|---------------------|
| **Pyre** | Python AST Engineer | Taint engine architecture, AST edge case analysis, two-phase analysis design |
| **Sable** | Security Architect | Defence-in-depth, UNCONDITIONAL cell hardening, TIER_1/TIER_2 severity separation |
| **Seren** | Systems Thinker | Enforcement-Diagnostic Stack, system dynamics risks, feedback loop design |
| **Riven** | Adversarial Red-Teamer | Evasion vector taxonomy, decorator abuse attacks, compliance laundering analysis |
| **Quinn** | Quality Engineer | Corpus verdict system, testability framework, INFO action-rate metric |
| **Gideon** | Governance Designer | Exceptionability matrix, 4-phase expiry lifecycle, grouped fingerprint governance |
| **Iris** | Integration Engineer | CLI modes, SARIF output specification, manifest schema, performance budgets |
| **Morgan** | Scribe | Roundtable orchestration, convergence tracking, contested decision resolution |

### Deliberation Structure

| Round | Purpose | Key Outcome |
|-------|---------|-------------|
| **Round 1** | Opening positions | 7 independent proposals; binary taint model proposed by Pyre |
| **Round 2** | Adversarial challenges | Cross-agent attacks; binary taint weaknesses exposed |
| **Round 3** | Convergence | Binary taint rejected 7/7; two-dimensional taint model converged; gatekeeper-first framing accepted |
| **Round 4** | Design decisions | Label set decided (5 provenance x 2 validation); 49-cell rule matrix completed; integration spec and governance model specified |
| **Round 5** | Final commitment | 7/7 commitment (6 unconditional, 1 conditional); 5 minority reports filed; known limitations documented |

### Final Commitment Status

All seven agents committed to the decided design. Six commitments are unconditional. Riven's commitment is conditional on the INFO action-rate metric shipping in v0.1 — a concrete implementation commitment resolved by Quinn's operational definition in Round 5.

---

## 2. Problem Statement

### The Core Challenge

Python's type system does not distinguish data by provenance. A `dict` from an external API and a `dict` from the audit database are the same type. In high-assurance systems like ELSPETH, where silent data corruption is worse than a crash, this type-system blindness creates a class of defects that are:

- Syntactically valid Python
- Test-passing
- Look like good defensive programming (`.get()` with defaults, broad `except` blocks, `hasattr()` gates)
- But are semantically dangerous because they fabricate data, destroy evidence, or bypass trust boundaries

These patterns are produced systematically by AI agents due to training data bias toward "defensive" programming. The tool must catch violations that human review would miss at scale.

### Existing Baseline

ELSPETH's `enforce_tier_model.py` is a pattern-matching CI gate that:

- Uses Python's `ast` module to detect defensive anti-patterns
- Maintains a per-module YAML allowlist with expiry dates and rationales
- Catches 1-2 violations per day in production agentic development

**Structural limitations** of the existing tool:

1. No cross-function data flow tracing
2. No verification that validator decorators actually validate
3. No contextual distinction — every `.get()` finding has the same severity regardless of whether the data is audit trail or external API response
4. Binary allowlist (suppress or block) with no expiry lifecycle

### What This Tool Replaces and Why

The semantic boundary enforcer replaces the pattern-matching gate with provenance-aware severity grading. The improvement is categorical, not incremental (Riven, Round 5):

| Limitation | `enforce_tier_model.py` | Semantic Boundary Enforcer |
|-----------|------------------------|---------------------------|
| Provenance awareness | None — all findings equal | 7 effective states determine severity |
| False positive management | Binary allowlist, no expiry | 4-class governance with expiry lifecycle |
| Validated data handling | No concept of validation | 2D model tracks validation independently |

---

## 3. Decided Architecture

### 3.1 Two-Dimensional Taint Model

The tool tracks two independent dimensions for every variable in scope:

**Dimension 1: Provenance** — where the data came from. Immutable once assigned.

| Label | Meaning | Assignment Mechanism |
|-------|---------|---------------------|
| `TIER_1` | Audit trail data — Landscape database, checkpoints, deserialized audit JSON | `@audit_data` decorator or manifest topology entry |
| `TIER_2` | Pipeline data — post-source, schema-conformant row data | `@pipeline_data` decorator; default for undeclared internal data |
| `TIER_3` | External data — API responses, user input, file reads | `@external_boundary` decorator or heuristic list match |
| `UNKNOWN` | Provenance not determinable | Default for untracked variables, unannotated function returns |
| `MIXED` | Container holding values from different provenance tiers | Computed: container with values from 2+ distinct provenance labels |

**Dimension 2: Validation Status** — what processing the data received. Monotonically increases from RAW to STRUCTURALLY_VALIDATED.

| Status | Meaning | Transition |
|--------|---------|-----------|
| `RAW` | No validation observed | Initial state for TIER_3 and UNKNOWN |
| `STRUCTURALLY_VALIDATED` | Passed through `@validates_external` with rejection path | Validator return value with reachable `raise` |

`VERIFIED` (per-field coverage tracking) is deferred to v1.0. It requires inter-procedural analysis beyond v0.1 scope.

#### 7 Effective States

Validation status is only meaningful for TIER_3 and UNKNOWN data. TIER_1 and TIER_2 are inherently trusted — they do not pass through `@validates_external`. MIXED takes the minimum validation status of its constituents (Seren: "weakest link"). This reduces the 5x2=10 theoretical matrix to 7 effective states:

| # | Provenance | Validation | Notes |
|---|-----------|-----------|-------|
| 1 | TIER_1 | N/A | Internal audit data — validation not applicable |
| 2 | TIER_2 | N/A | Internal pipeline data — validation not applicable |
| 3 | TIER_3 | RAW | Unvalidated external data |
| 4 | TIER_3 | STRUCTURALLY_VALIDATED | Validated external data |
| 5 | UNKNOWN | RAW | Unknown provenance, unvalidated |
| 6 | UNKNOWN | STRUCTURALLY_VALIDATED | Unknown provenance, validated |
| 7 | MIXED | N/A | Heterogeneous container |

#### Rationale for TIER_1/TIER_2 Split

The split was contested across Rounds 3-5. Pyre collapsed them in Round 4; Quinn collapsed them in Round 3. Both ultimately conceded.

The decisive arguments (Round 4):

1. **Severity separation** (Sable): `.get()` on TIER_1 is UNCONDITIONAL ERROR (audit corruption, legal exposure). `.get()` on TIER_2 is STANDARD ERROR (contract violation, exceptions sometimes permitted). Collapsing forces a false choice between over-alerting and under-alerting.

2. **Developer experience** (Iris): The INTERNAL message tells developers *what* is wrong; TIER_1/TIER_2 messages tell them *why* and *what to do*. "Evidence tampering risk — crash immediately" vs. "upstream contract violation — fix the bug, don't mask it." These are different developer actions.

3. **Governance** (Gideon): TIER_1 `.get()` is UNCONDITIONAL — no exception pathway. TIER_2 `.get()` is STANDARD — exceptions permitted with review. The governance model requires the distinction.

4. **Rule divergence**: Broad `except` (R4) is ERROR on TIER_1 but WARN on TIER_2. `isinstance()` (R7) is ERROR on TIER_1 but WARN on TIER_2. Data reaching audit (R5) is SUPPRESS on both but for different documented reasons.

#### Rationale for MIXED as Distinct from UNKNOWN

Unanimous (7/7) after Round 4. Seren provided the system dynamics argument:

| Property | MIXED | UNKNOWN |
|----------|-------|---------|
| What tool knows | "This container holds data from multiple tiers" | "I cannot determine where this data came from" |
| Developer action | Decompose the container — separate access paths by tier | Add provenance annotation |
| Finding confidence | Higher (known composition) | Lower (missing information) |
| System dynamics | Explicit MIXED creates resolution pressure (destructure) | Collapsing to UNKNOWN eliminates resolution pressure, creating a garbage-can category |

Seren: "Collapsing MIXED into UNKNOWN eliminates the resolution pressure that keeps MIXED bounded. Without it, UNKNOWN becomes a garbage-can category that drives allowlisting rather than improvement."

### 3.2 Rule Set

Seven rules detect defensive programming patterns that are dangerous in high-assurance systems:

| Rule ID | Pattern | Detection | ACF Mapping | Why Dangerous |
|---------|---------|-----------|-------------|---------------|
| **R1** | `.get("key", default)` | `ast.Call` on `.get` with >= 2 args | ACF-I1 (Critical) | Fabricates values instead of crashing on corruption |
| **R2** | `getattr(obj, "attr", default)` | `ast.Call` on `getattr` with 3 args | ACF-I1 (Critical) | Hides missing attributes that indicate bugs |
| **R3** | `hasattr(obj, "attr")` | `ast.Call` on `hasattr` | ACF-S3 (High) | Unconditionally banned — swallows all exceptions from `@property` getters |
| **R4** | Broad `except Exception` | `except Exception`/bare `except` without re-raise | ACF-I3 (High) | Destroys audit trail by catching operational exceptions |
| **R5** | Data reaches audit write | Tainted variable flows to landscape/recorder API call | ACF-I2 (Critical) | Unvalidated external data entering audit trail = integrity violation |
| **R6** | `except: pass` | `except` with bare `pass`, `return default`, `continue` | ACF-I3 (High) | Silent exception swallowing — evidence destruction |
| **R7** | `isinstance()` on internal data | `ast.Call` on `isinstance` as conditional guard | ACF-S3 (High) | Implies uncertainty about types we control |

### 3.3 Rule Evaluation Matrix

The complete 49-cell matrix maps each (rule, effective-state) combination to a severity level. Every cell is defined — no gaps.

| Rule | TIER_1 | TIER_2 | T3+RAW | T3+SV | UNK+RAW | UNK+SV | MIXED |
|------|--------|--------|--------|-------|---------|--------|-------|
| **R1** `.get()` | ERROR | ERROR | SUPPRESS | SUPPRESS | WARN | INFO | WARN |
| **R2** `getattr()` | ERROR | ERROR | SUPPRESS | SUPPRESS | WARN | INFO | WARN |
| **R3** `hasattr()` | ERROR | ERROR | ERROR | ERROR | ERROR | ERROR | ERROR |
| **R4** Broad `except` | ERROR | WARN | SUPPRESS | INFO | WARN | INFO | WARN |
| **R5** Data->audit | SUPPRESS | SUPPRESS | ERROR | INFO | WARN | INFO | WARN |
| **R6** `except: pass` | ERROR | ERROR | WARN | WARN | ERROR | WARN | ERROR |
| **R7** `isinstance()` | ERROR | WARN | SUPPRESS | SUPPRESS | WARN | SUPPRESS | WARN |

**Distribution:** ERROR 19 (39%), WARN 14 (29%), INFO 5 (10%), SUPPRESS 11 (22%).

#### Contested Cell Resolutions

Four cells had productive disagreement in Round 4. The scribe resolved each:

**1. `.get()` on TIER_3+SV (R1/R2):** Riven argued INFO (cannot verify validator covers accessed field). Others argued SUPPRESS. **Resolution: SUPPRESS for v0.1.** The volume concern is real — every validated `.get()` would become an INFO finding. Riven's per-field coverage check is a v1.0 enhancement via VERIFIED status. Documented as Known Limitation KL-1.

**2. Broad `except` on TIER_3+RAW (R4):** Sable argued WARN (broad catch should use specific types). Others argued SUPPRESS. **Resolution: SUPPRESS for v0.1.** The distinction between `except requests.RequestException` (specific, good) and `except Exception` (broad, bad) requires syntactic analysis of the exception type, which is a rule refinement for v0.2 (R4b: broad vs. specific exception).

**3. Broad `except` on TIER_2 (R4):** Split between ERROR (Sable, Iris) and WARN (Quinn, Seren). **Resolution: WARN.** ELSPETH's manifesto says "let plugin bugs crash" (supporting ERROR), but transforms legitimately catch row-level operation failures — arithmetic, parsing on Tier 2 data values, not types. ERROR would create false positives on the most common transform pattern.

**4. Data->audit on MIXED+SV (R5):** Quinn argued ERROR (conservative). Pyre/Sable argued WARN. **Resolution: WARN.** MIXED+SV means at least some validation occurred. ERROR should be reserved for cases where NO validation occurred on data reaching audit.

### 3.4 Severity System

#### 4-Level Severity (Quinn, adopted unanimously)

| Severity | Corpus Verdict | CI Behaviour | Pre-commit | SARIF Level | Exit Code |
|----------|---------------|-------------|-----------|-------------|-----------|
| **ERROR** | `true_positive` | Block | Block | `error` | 1 |
| **WARN** | `true_positive_reduced` | Block | Block | `warning` | 1 |
| **INFO** | `true_note` | Advisory | Pass | `note` | 3 |
| **SUPPRESS** | `true_negative` | No output | Pass | -- | 0 |

#### Exit Code Mapping

| Code | Meaning | Condition |
|------|---------|-----------|
| 0 | Clean | No findings at any severity |
| 1 | Blocking | ERROR or WARN findings present (not covered by valid exception) |
| 2 | Tool error | Parse failure, config error, analysis could not run |
| 3 | Advisory | INFO findings only |

Exit 2 MUST block CI (Sable, Iris: "an open gate is worse than no tool"). Unanimous.

Exit code precedence: tool error (2) > blocking (1) > advisory (3) > clean (0).

---

## 4. Provenance Assignment

### 4.1 Declaration Model

Provenance is assigned through three mechanisms, applied in priority order:

#### Decorators

| Decorator | Provenance | Usage |
|-----------|-----------|-------|
| `@audit_data` | TIER_1 | Functions returning Landscape/checkpoint data |
| `@pipeline_data` | TIER_2 | Functions returning pipeline row data (rarely needed — TIER_2 is the default) |
| `@external_boundary` | TIER_3 | Functions returning data from external systems |
| `@validates_external` | Transitions TIER_3/UNKNOWN from RAW to STRUCTURALLY_VALIDATED | Validators with structural verification (must contain rejection path) |

#### Topology (strict.toml)

Module-level glob patterns assign default provenance to all data originating from matched modules:

```toml
[tool.strict.topology]
tier_1 = [
    "src/elspeth/core/landscape/**",
    "src/elspeth/core/checkpoint/**",
]
tier_2 = [
    "src/elspeth/engine/**",
    "src/elspeth/plugins/**",
]
```

#### Heuristic List

Built-in detection of common external call sites:

```toml
[tool.strict.heuristics]
external_calls = [
    "requests.*",
    "httpx.*",
    "aiohttp.*",
    "urllib.request.*",
    "json.loads",
    "yaml.safe_load",
    "yaml.unsafe_load",
    "subprocess.*",
]
```

Return values from heuristic-matched calls receive TIER_3 provenance.

**Priority:** Decorator > Topology > Heuristic > Default (TIER_2 for internal, UNKNOWN for unresolvable).

### 4.2 Taint Propagation

#### Scope

v0.1 implements **intra-function taint propagation only**. Inter-procedural analysis is deferred to v1.0.

#### Assignment Propagation

```python
x = external_call()    # x is (TIER_3, RAW) via heuristic
y = x                  # y inherits (TIER_3, RAW)
z = y["field"]         # z inherits (TIER_3, RAW) from y
```

Both dimensions propagate independently through assignments. Provenance is immutable — it never changes. Validation status monotonically increases (RAW -> STRUCTURALLY_VALIDATED).

#### Container Contamination

When a container holds values from different provenance tiers, it receives MIXED provenance:

```python
combined = {
    "audit": recorder.get_state(),    # TIER_1
    "external": api_response,          # TIER_3
}
# combined is MIXED
```

MIXED validation status is the minimum of its constituents (Seren: "weakest link"):

| Constituent statuses | Container status |
|---------------------|-----------------|
| All RAW | RAW |
| All STRUCTURALLY_VALIDATED | STRUCTURALLY_VALIDATED |
| Mix of RAW and VALIDATED | RAW |

#### Structural Validation Detection

`@validates_external` functions must contain a **rejection path** — reachable control flow that can reject invalid data:

- `raise` statement (including within `if` branches)
- `isinstance()` check with conditional
- `try/except` with validation logic

A validator without a rejection path is structurally unsound — it attests to validation without the ability to reject. The tool verifies this at declaration time (first-pass symbol collection).

#### AST Edge Cases (Pyre, Round 5)

Five implementation challenges identified with mitigations:

| # | Edge Case | Risk | Mitigation | Effort |
|---|-----------|------|-----------|--------|
| 1 | **Walrus operator** (`:=`) in comprehensions | `:=` targets leak to enclosing scope; comprehension variables don't | Shadow scope for comprehension variables; walrus targets write to enclosing scope | ~20 lines |
| 2 | **Method decorator resolution** — `self.fetch()` must link to `@external_boundary` on class method | Breaks for aliased self, passed-in instances, inherited methods | Restrict to direct `self` references in v0.1 (zero aliased-self instances in ELSPETH) | Bounded |
| 3 | **MIXED unpacking** — `a, b = mixed_container[k1], mixed_container[k2]` | Cannot determine per-element provenance from AST | All unpacked variables from MIXED inherit MIXED (conservative, sound) | Trivial |
| 4 | **f-string interpolation** — `f"{tier3_var}"` produces MIXED string | Not consumed by v0.1 rules but positions for v0.2 injection rules | Implement propagation as infrastructure (~15 lines), no rules consume it yet | ~15 lines |
| 5 | **try/except/else** — `else` block is not covered by `try`'s handlers | R4 (broad except) may false-positive on code in `else` | Track AST subtree membership when evaluating R4 | Moderate |

None require design changes. All are implementable within v0.1.

### 4.3 Decorator-Consistency Checker

A mandatory first-pass rule that cross-references decorator declarations against known external boundaries (Riven, Round 4).

#### What It Catches

**Scenario A — External mislabelled as internal:**
```python
@audit_data  # LIE — calls external API
def get_enrichment(row_id):
    return requests.get(f"https://api.enrichment.io/{row_id}").json()
```
The checker detects `@audit_data` on a function calling `requests.get()` (heuristic list match) and emits an ERROR: "Function decorated as @audit_data but calls known external boundary at line N."

**Scenario B — Internal mislabelled as external:**
```python
@external_boundary  # LIE — reads from Landscape
def get_state(recorder, token_id):
    return recorder.get_row_state(token_id)
```
The checker detects `@external_boundary` on a function whose body accesses known internal objects and emits an ERROR.

#### What It Does Not Catch

**Scenario C — Correct decorator, mixed-provenance return:**
```python
@external_boundary  # Technically true — HTTP call
def get_or_create(api_client, data):
    return {
        "api_response": api_client.post("/x", json=data).json(),  # TIER_3
        "tracking_id": generate_audit_id(),                         # TIER_1
    }
```
The decorator is honest — the function does call an external system. But the return mixes tiers. The consistency checker sees `@external_boundary` + `api_client.post()` and says "consistent." The TIER_1 tracking field loses its provenance.

**Decorator omission:** Functions with no decorator default to TIER_2. An undecorated function calling an external API returns TIER_2 data — defensive patterns become ERROR findings instead of SUPPRESS.

#### Known Limitations

| ID | Gap | Detection | Remediation |
|----|-----|-----------|-------------|
| **KL-2a** | Scenario C (mixed-provenance returns) | Requires inter-procedural return-value analysis | v1.0+ |
| **KL-2b** | Decorator omission | Detectable via coverage metrics ("N functions make external calls without decorators") | v0.2 — Layer 3 coverage report |

---

## 5. Governance Model

### 5.1 Exceptionability Classification

Each of the 49 matrix cells is assigned to one of four governance classes (Gideon, Round 4):

| Class | Count | Policy | Description |
|-------|-------|--------|-------------|
| **UNCONDITIONAL** | 24 | No exceptions — tool rejects creation at parse time | Project invariants encoded in the tool |
| **STANDARD** | 22 | `decision_group` with rationale, 90-day expiry, divergence detection | Medium governance cost — active exception management |
| **LIBERAL** | 10 | Single-line rationale, 180-day expiry | Low governance cost — minimal review |
| **TRANSPARENT** | 8 | Advisory/suppress — below governance threshold | Zero governance cost — no exception mechanism |

**24 of 49 cells (49%) are UNCONDITIONAL** — no governance mechanism can override them. This is the design's strongest security property.

#### UNCONDITIONAL Breakdown

| Source | Count | Justification |
|--------|-------|---------------|
| `hasattr()` — all 7 states | 7 | CLAUDE.md unconditional ban |
| `except: pass` — TIER_1, TIER_2, UNKNOWN+RAW, MIXED | 4 | Silent swallowing destroys crash guarantees |
| `.get()`/`getattr()` on TIER_1 (2 rules x 1 state) | 4 | Audit trail fabrication |
| Broad `except` on TIER_1 | 2 | Audit trail destruction |
| `isinstance()` on TIER_1 | 2 | Type distrust on data we defined |
| Data->audit from TIER_3+RAW | 1 | Core trust boundary violation |
| Data->audit from MIXED+RAW | 1 | Unvalidated component contaminates audit |
| `except: pass` on TIER_1 (overlap with above) | 2 | Audit trail destruction |
| `except: pass` on MIXED | 1 | Heterogeneous data with swallowed exceptions |
| **Total** | **24** | |

#### Cross-Tier Grouping Constraint

A `decision_group` may not span findings across TIER_1 and TIER_2 boundaries (Gideon). The rationale for exceptions on audit data is fundamentally different from the rationale on pipeline data. This prevents governance shortcuts where a single broad rationale covers both critical and non-critical patterns.

### 5.2 Exception Lifecycle

#### Grouped Fingerprint Governance

Exceptions are managed through `decision_group` metadata that groups related findings under a single architectural rationale:

- **Matching:** Per-finding fingerprints (deterministic hash of normalized AST context). Refactoring-resilient.
- **Governance:** `decision_group` tag groups findings that share an architectural rationale.
- **Review:** Group-level review with divergence detection. Digest shows stale fingerprints, new unassigned findings, group health percentage.

#### 4-Phase Expiry Lifecycle (Gideon)

| Phase | Duration | Exit Code | Developer Action |
|-------|----------|-----------|-----------------|
| **Active** | Until 14 days before expiry | 3 (if excepted) | None required |
| **Warning** | 14 days before expiry | 3 (still advisory) | Review and renew proactively |
| **Grace** | 7 days after expiry | 1 (blocking) | Renew (re-review) or fix code |
| **Hard-expired** | After grace period | 1 (blocking) | Fresh rationale required — not just timestamp bump |

The warning phase uses the Enforcement-Diagnostic Stack: information starts as a diagnostic signal (Layer 3) and escalates to enforcement (Layer 1) when ignored. The hard-expired phase prevents rubber-stamp renewal by requiring fresh `decision_rationale`, not just confirmation.

#### Review Fields

| Field | Required? | Purpose |
|-------|-----------|---------|
| `decision_rationale` | **Required** | The justification for the exception — the governance point |
| `reviewer` | Optional | Who reviewed the exception |
| `trust_tier` | Optional | Which tier the exception covers |

For UNCONDITIONAL cells: the tool rejects exception creation at parse time with error: `"strict.toml: exception for {rule} on {provenance} is UNCONDITIONAL — no exceptions permitted"`.

#### Orphaned Exception Cleanup (Gideon, Round 5)

Fingerprints matching zero findings for 3 consecutive CI runs are flagged as `orphaned`. After 30 days of orphan status, they are auto-removed from the exception file with a comment in CI output. This prevents `strict.toml` from accumulating dead entries.

#### Exception Audit Trail Fields (Gideon, Round 5)

Each exception entry includes:

| Field | Purpose |
|-------|---------|
| `created_by` | Who created the exception |
| `created_at` | When it was created |
| `last_renewed_by` | Who last renewed it |
| `last_renewed_at` | When it was last renewed |

Populated by the `strict review` command. Git blame provides a backup, but explicit fields are more reliable when multiple changes are committed together.

### 5.3 Security Hardening

Four recommendations from Sable, accepted unanimously:

#### SH-1: UNCONDITIONAL Cells Hardcoded in Source

The 24 UNCONDITIONAL cells must be encoded as constants in the rule engine source code, not in `strict.toml` or any editable configuration. If the exceptionability matrix lives in config, a single-line change downgrades `hasattr()` from UNCONDITIONAL to STANDARD.

STANDARD and LIBERAL classifications may live in configuration — they represent policy choices that may evolve. UNCONDITIONAL is a project invariant.

#### SH-2: CI Count-Decrease Test

```python
assert len(UNCONDITIONAL_CELLS) >= 24, \
    "UNCONDITIONAL cell count decreased — requires security review"
```

Monotonically non-decreasing guard. If new rules add UNCONDITIONAL cells, the threshold increases. If a cell is proposed for downgrade, the test forces explicit review.

#### SH-3: Exit 2 Self-Test

On first run in a CI environment, `strict` intentionally emits exit 2 and verifies the pipeline treats it as failure. If the pipeline continues (e.g., `continue-on-error: true`), emit a WARN-level finding: "CI pipeline does not block on tool errors (exit 2). Security gate is ineffective."

One-time setup verification, not per-run.

#### SH-4: Warning Phase Prominence

The 14-day exception expiry warning appears in Seren's Layer 3 diagnostics as a first-class signal, not just in the governance output block. "3 exceptions expiring in 14 days" should be as prominent as "2 new violations this sprint" in the `strict health` display.

---

## 6. Integration Specification

### 6.1 CLI Modes

#### `strict check <path>` — CI Gate

Primary mode. Analyses all Python files under the path. Human-readable output by default, SARIF with `--sarif` flag.

**Performance budget:** < 5 seconds for ~100 files.

#### `strict check --stdin --file-path <path>` — Agent Self-Check

Reads a single file from stdin. `--file-path` required for manifest lookup. SARIF output by default (structured data for agent consumption).

**Performance budget:** < 100 milliseconds.

#### Pre-commit Hook

```yaml
repos:
  - repo: https://github.com/elspeth-project/strict
    rev: v0.1.0
    hooks:
      - id: strict
        name: Semantic boundary check
        entry: strict check
        language: python
        types: [python]
```

**Performance budget:** < 200 milliseconds per file.

#### `--changed-only` File Discovery

Defaults to `git diff --name-only HEAD~1` for CI, `git diff --cached --name-only` for pre-commit. `--base-ref <ref>` override for PR-based workflows.

### 6.2 SARIF Output

#### Format

SARIF 2.1.0 compliant. Example finding:

```json
{
  "ruleId": "SBE-R01",
  "level": "error",
  "message": {
    "text": ".get() with default on audit data (Tier 1) — fabricates values on corruption. Audit data must crash on missing key."
  },
  "locations": [{
    "physicalLocation": {
      "artifactLocation": { "uri": "src/elspeth/core/landscape/exporter.py" },
      "region": { "startLine": 142 }
    }
  }],
  "properties": {
    "sbe.provenance": "TIER_1",
    "sbe.provenanceSource": "self._recorder.get_row_state()",
    "sbe.provenanceSourceLine": 138,
    "sbe.validationStatus": "RAW",
    "sbe.corpusVerdict": "true_positive"
  }
}
```

#### Custom Properties

| Property | Type | Description |
|----------|------|-------------|
| `sbe.provenance` | enum | One of: TIER_1, TIER_2, TIER_3, UNKNOWN, MIXED |
| `sbe.provenanceSource` | string | Human-readable provenance source (see format reference) |
| `sbe.provenanceSourceLine` | int or null | Line where provenance was assigned (`null` for topology/parameter) |
| `sbe.validationStatus` | enum | RAW or STRUCTURALLY_VALIDATED |
| `sbe.corpusVerdict` | enum | true_positive, true_positive_reduced, true_note, true_negative |

#### provenanceSource Format (Iris, Round 5)

6 source types with stable formats:

| Source Type | Format | Example |
|-------------|--------|---------|
| Method call | `"{receiver}.{method}()"` | `"self._recorder.get_row_state()"` |
| Parameter | `"{param} parameter"` | `"row parameter"` |
| Decorator | `"@{decorator} on {function}"` | `"@external_boundary on fetch_data"` |
| Heuristic | `"heuristic: {pattern}"` | `"heuristic: requests.get"` |
| Topology | `"topology: {tier}"` | `"topology: tier_1"` |
| Default | `"unknown"` | `"unknown"` |

`sbe.provenanceSourceLine` is `null` when provenance comes from topology or parameter context. Emit the field with `null` value, not omit it — SARIF consumers benefit from a stable schema.

#### Determinism Guarantee

**Byte-identical output for byte-identical input** (Iris). The tool's output is deterministic:

- Same source file + same manifest + same tool version = identical output
- No timestamps in SARIF output
- Finding order: sorted by file path, then line number, then column, then rule ID
- Exception matching: deterministic fingerprint algorithm
- No randomness anywhere in the analysis pipeline

#### Invocations Array

Include `invocations` with `executionSuccessful` and `exitCode`; omit `startTimeUtc`/`endTimeUtc`. This satisfies SARIF validators without breaking determinism.

### 6.3 Manifest (strict.toml)

#### Schema

```toml
[tool.strict]
version = "0.1"

# Trust topology — module-level provenance defaults
[tool.strict.topology]
tier_1 = [
    "src/elspeth/core/landscape/**",
    "src/elspeth/core/checkpoint/**",
]
tier_2 = [
    "src/elspeth/engine/**",
    "src/elspeth/plugins/**",
]

# Rule configuration
[tool.strict.rules.SBE-R01]
blocking = true
precision_threshold = 0.88

[tool.strict.rules.SBE-R03]
blocking = true
precision_threshold = 0.99

# Heuristic list for external boundary detection
[tool.strict.heuristics]
external_calls = [
    "requests.*",
    "httpx.*",
    "aiohttp.*",
    "urllib.request.*",
    "json.loads",
    "yaml.safe_load",
    "subprocess.*",
]

# Optional coverage tracking mode
# coverage_mode = "tracked"

# Exception entries
[[tool.strict.exceptions]]
fingerprint = "a1b2c3d4e5f6"
rule = "SBE-R01"
file = "src/elspeth/core/landscape/exporter.py"
decision_group = "sparse-token-lookup"
expires = "2026-09-01"
created_by = "john"
created_at = "2026-03-01"
last_renewed_by = "john"
last_renewed_at = "2026-03-01"

[tool.strict.exceptions.review]
decision_rationale = "Sparse token lookup — not all rows have tokens in batch export"
reviewer = "john"
trust_tier = "tier2"
```

#### Topology Glob Semantics

- `*` matches files in directory only (single-level)
- `**` matches recursively
- Follows `.gitignore`/`ruff` conventions

#### Overlap Resolution

If a file matches both `tier_1` and `tier_2` globs: **exit 2 (tool error)**. Overlapping topology is a manifest error. Error message: `"strict.toml: file {path} matches both tier_1 and tier_2 topology — resolve overlap"`.

#### Coverage Mode

Optional `coverage_mode = "tracked"` emits a single summary line: "N files analysed without provenance information. Consider adding manifest entries for improved precision." Informational only — does not affect exit codes.

#### Configuration Precedence

1. `--config <path>` CLI flag (explicit)
2. `strict.toml` in current directory
3. `pyproject.toml` `[tool.strict]` section
4. Walk up directory tree for `strict.toml` (monorepo support)

First match wins. No merging across sources.

### 6.4 Enforcement-Diagnostic Stack (Seren)

Three-layer architecture separating enforcement from diagnostics:

#### Layer 1: Enforcement Gate

Blocks CI on findings from rules above precision threshold. Exit code determined by enforcement findings only. This is the tool's primary function and identity.

#### Layer 2: Taint Attenuation

Provenance x validation status tracking per variable. Rule evaluation against the 49-cell matrix. This layer powers both the gate (Layer 1) and the diagnostics (Layer 3).

#### Layer 3: Diagnostics

Three output channels, none of which affect exit codes:

**Channel 1: CI Summary Block** — appended to finding output in every `strict check` run.

```
--- Enforcement Health ---------------------------------------------------
  Suppression rate:       12% (18 allowed / 152 total)    down from 18%
  Violation velocity:     1.4/day (7-day avg)             stable
  INFO findings:          3 (external->audit flows via validators)
  Validator concentration: validate_response() -> 8 flows  ! review
  Allowlist hygiene:      4 entries expire within 14 days  ! renew
----------------------------------------------------------------------
```

In pre-commit mode (terse): `Health: 12% suppressed | 1.4/day | 3 INFO | 4 expiring`

**Channel 2: `strict-health.json` Sidecar** — machine-readable JSON written alongside SARIF output.

```json
{
  "schema_version": "0.1.0",
  "metrics": {
    "suppression_rate": { "value": 0.12, "numerator": 18, "denominator": 152, "trend": "decreasing" },
    "violation_velocity": { "value": 1.4, "unit": "findings_per_day", "window_days": 7, "trend": "stable" },
    "info_findings": { "count": 3, "rule_breakdown": {"R5": 3} },
    "validator_concentration": [
      { "validator": "validate_response", "flows": 8, "threshold_exceeded": true }
    ],
    "allowlist_hygiene": { "total_entries": 18, "expiring_within_14d": 4, "oldest_entry_days": 89 },
    "attenuation_ratio": { "structurally_validated": 14, "raw": 138, "ratio": 0.10 }
  }
}
```

**Channel 3: `strict health` Command** — on-demand rich text with trends for tech leads and quarterly reviews.

**Diagnostic metrics:**

| Metric | Signal | Source |
|--------|--------|--------|
| **Suppression rate** | Rule calibration health; >20% healthy, >30% investigate | Allowlist entries / total firings |
| **Violation velocity** | Generation-time control effectiveness; rising = agent instructions need updating | Findings per week, trended |
| **Validator concentration** | Single-point-of-failure risk | Distinct data flows per validator |
| **Allowlist hygiene** | Governance timeliness | Exception age distribution, expiry clustering |
| **Attenuation ratio** | Proportion of data in validated-but-unverified state | STRUCTURALLY_VALIDATED / total |

---

## 7. Testing Strategy

### 7.1 Golden Corpus

~208 entries structured by the 49-cell matrix. Each entry is a short code snippet (5-15 lines) with provenance annotation and expected verdict.

#### Corpus Verdicts per Cell

| Verdict | Cells | Samples/cell | Total |
|---------|-------|-------------|-------|
| ERROR (`true_positive`) | 19 | 5 TP | 95 |
| WARN (`true_positive_reduced`) | 14 | 3 TP + 2 TN | 70 |
| INFO (`true_note`) | 5 | 2 | 10 |
| SUPPRESS (`true_negative`) | 11 | 3 TN | 33 |
| **Total** | **49** | | **~208** |

The `hasattr()` row (7 ERROR cells) shares samples across provenance (~5 unique samples, not 35). Effective unique corpus entries: ~180.

#### Authoring Estimate (Quinn, Round 5)

| Category | Cells | Entries | Hours |
|----------|-------|---------|-------|
| R3 `hasattr()` | 7 | ~7 | 1 |
| R1/R2 `.get()`/`getattr()` | 14 | ~56 | 4-5 |
| R4 Broad `except` | 7 | ~28 | 3-4 |
| R5 Data->audit | 7 | ~30 | 4-5 |
| R6 `except: pass` | 7 | ~28 | 2-3 |
| R7 `isinstance()` | 7 | ~24 | 2-3 |
| Cross-cutting review | -- | -- | 2-3 |
| **Total** | **49** | **~208** | **16-24** |

**Maintenance cost:** ~2 entries/quarter from red-team evolution. New rules add 7 cells each (~28-35 entries, ~4-5 hours). The corpus is append-mostly.

#### Performance Target

< 5 seconds for full corpus. Estimated ~2 seconds based on current `enforce_tier_model.py` performance (~10ms per file).

### 7.2 Additional Test Surfaces

| Gap | Scope | Test Type | Entries | Hours |
|-----|-------|-----------|---------|-------|
| **Taint propagation depth** | Multi-step assignment chains (2-step, 3-step, cross-function) | Integration tests | ~15-20 | 4-6 |
| **Decorator consistency** | Correct vs. inconsistent decorator usage | Separate test suite | ~20 | 2-3 |
| **MIXED construction** | How containers become MIXED via mixed-tier assignments | Taint engine tests | ~8-10 | 1-2 |
| **Total additional** | | | **~43-50** | **7-11** |

### 7.3 Determinism Testing

Run each corpus entry twice and diff the output. Catches non-determinism from dict ordering, set iteration, or timestamp injection. Mandatory property of the test suite, not optional (Quinn).

**Total test surface:** ~251-258 entries, 23-35 hours total authoring time.

---

## 8. Measurement and Metrics

### 8.1 Per-Rule Precision Thresholds

**80% immutable floor** — hardcoded in the tool's source code, not configurable. Below 80% precision, a rule does not earn blocking status.

**Per-rule earned thresholds** via corpus evidence:

| Rule | Estimated Precision | Notes |
|------|-------------------|-------|
| R3 (`hasattr`) | ~99% | Can block immediately |
| R1 (`.get()`) | ~88% | Blocks above earned threshold |
| R4 (broad `except`) | ~85% | Blocks above earned threshold |

Thresholds are **monotonically non-decreasing** (Riven). Once a rule earns a higher threshold, it cannot be lowered — only raised further. Stored in CODEOWNERS-protected manifest.

### 8.2 INFO Action-Rate Metric

The only conditional commitment in the roundtable (Riven). Operational definition provided by Quinn (Round 5):

#### Definition

| Component | Definition |
|-----------|-----------|
| **What counts as "action"** | Code change within the same PR or subsequent 3 commits that modifies the code region identified by an INFO finding |
| **What doesn't count** | Allowlist suppression without code change, merging without addressing, modifying unrelated code in same file |
| **Measurement mechanism** | SARIF finding fingerprints + git diff correlation (file:line-range +/- 5 lines tolerance) |

#### Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| Action rate > 30% after 20+ observations | Promote cell to WARN | Developers treating findings as actionable — earned blocking status |
| Action rate < 5% after 50+ observations | Reclassify cell to SUPPRESS | Findings are noise — remove them |
| Action rate 5-30% | Hold at INFO | Insufficient evidence to reclassify |

**Observation minimums** prevent premature reclassification. 20+ observations for promotion, 50+ for suppression. For a team of 5-10 developers, 50 observations on a single cell may take 3-6 months.

---

## 9. Known Limitations and Future Work

### 9.1 Documented Known Limitations

| ID | Limitation | Identified By | Severity | Remediation | Timeline |
|----|-----------|--------------|----------|-------------|----------|
| **KL-1** | Validator field-coverage gap — SUPPRESS cells assume validator covers accessed field without verification | Riven | Medium | VERIFIED validation status with per-field coverage tracking | v1.0 |
| **KL-2a** | Decorator-consistency: Scenario C — mixed-provenance returns from correctly-decorated functions | Sable | Low | Inter-procedural return-value analysis | v1.0+ |
| **KL-2b** | Decorator-consistency: decorator omission — undecorated functions default to TIER_2 regardless of actual behaviour | Sable | Low | Layer 3 coverage report ("N functions make external calls without decorators") | v0.2 |
| **KL-3** | MIXED provenance underdetection — functions mixing tier provenance in return values produce single-tier labels | Riven | Low | Intra-procedural data flow analysis on dict value assignments | v1.0 |

**KL-1 is the most dangerous** (Riven, Round 5): "The field-coverage gap produces a SUPPRESS — no finding at all. Zero signal. The false negative is invisible to every channel in the integration stack."

### 9.2 System Dynamics Risks (12-24 Month)

| Risk | Identified By | Likelihood | Mechanism | Mitigation |
|------|--------------|-----------|-----------|-----------|
| **Validator monoculture** | Seren | High (6-12 months) | Developers clone working validators -> shared semantic inadequacy propagates across all flows. Concentration metric shows healthy distribution but structural similarity is high. | `strict health` reports validator structural similarity metric (>80% shared AST = warning). v0.2+ enhancement. |
| **Exception governance coordination** | Seren | Medium (12+ months) | Exceptions cluster around same expiry dates (created in same sprint) -> batch-renewal burden displaces feature work -> bulk renewal without review or reactive CI disruption. | Staggered expiry — new exceptions assigned dates that distribute evenly across renewal calendar. Governance policy, not tool change. |
| **Annotation treadmill** | Seren | High (inevitable) | Annotation correctness at creation degrades as implementations evolve. Decorator-consistency checker catches some cases but not indirect external dependencies. | Inter-procedural taint analysis (v1.0) is the structural fix. Until then, staleness rate depends on codebase churn and review discipline. |

### 9.3 Enhancement Path

#### v0.2

- Decorator omission coverage report (KL-2b remediation)
- Validator structural similarity metric (monoculture detection)
- Staggered exception expiry dates
- R4b: broad vs. specific exception type distinction
- INFO threshold gate on accumulation (Riven's Option 2)

#### v1.0

- `VERIFIED` validation status with per-field coverage tracking (KL-1 remediation)
- Inter-procedural taint analysis (KL-2a, KL-3 remediation)
- Annotation verification against actual data flow
- Mandatory review lifecycle for INFO findings (Riven's Option 3)

---

## 10. Minority Reports

Five minority reports filed across three agents. All non-blocking — they identify enhancement paths, not design flaws.

### MR-1: @internal_data Alias (Pyre)

**Position:** The public API should offer `@internal_data` as syntactic sugar resolving to TIER_2 at parse time.

**Argument:** Most transform authors will never need TIER_1. Forcing a choice between `@pipeline_data` and `@audit_data` when developers mean "this isn't external" creates friction that pushes toward UNKNOWN (no annotation at all).

**Status:** Non-blocking. UX convenience implementable as a post-v0.1 alias without design changes. Risk: the alias could mask genuine TIER_1 data behind a TIER_2 default. Resolution is documentation, not tool change.

### MR-2: INFO Boundary Conditions (Sable)

**Position:** INFO is advisory (exit 3) for v0.1, with three measurable thresholds for revisiting:

| Condition | Threshold | Effect |
|-----------|-----------|--------|
| INFO action-rate | < 5% after 6 months | Reclassify affected cells to SUPPRESS |
| Team size | > 15 engineers | "Someone reads notices" assumption fails — implement threshold gate |
| Agent-generated code share | > 50% of new data flows | Compliance laundering surface becomes majority case — revisit blocking |

**Status:** Non-blocking. The INFO surface is narrow (5 cells, 10% of matrix). Defence-in-depth via SARIF persistence and trend analysis provides multiple catch points.

### MR-3: Decorator-Consistency Gaps (Sable)

**Position:** The decorator-consistency checker ships in v0.1 with two documented gaps:

| Gap | Description | Remediation |
|-----|-------------|-------------|
| Scenario C | Mixed-provenance returns from correctly-decorated functions | v1.0+ inter-procedural analysis |
| Decorator omission | Functions with no decorator default to TIER_2 | v0.2 coverage report |

**Status:** Non-blocking. The checker catches mechanical mislabelling — the high-volume case agents produce.

### MR-4: ERROR Rate Erosion (Seren)

**Position:** The 39% ERROR rate is correct for current context. Residual risk: the 25 governable cells (51% of matrix) may suffer exception proliferation rather than cell reclassification. The suppression rate metric is the right sensor; the missing piece is the actuator.

**What Seren would change:** A suppression rate threshold that auto-elevates from Layer 3 diagnostic to Layer 1 concern (SARIF finding: "suppression rate on R4/TIER_2 exceeds 30%"). Accepts this is over-engineering for v0.1.

**Status:** Non-blocking. Three structural defences exist: 24 UNCONDITIONAL cells, precision ratchet, suppression rate visibility.

### MR-5: Embedded Validation (Quinn)

**Position:** For v0.1's intra-function scope, `VALIDATED` as a provenance label is operationally equivalent to `TIER_3 x STRUCTURALLY_VALIDATED`.

**Self-closed:** Quinn concedes the 2D model is structurally correct (provenance immutable; validation status evolves). "The roundtable optimized for conceptual integrity. They were right."

**Residual note:** Expanding validation to TIER_1/TIER_2/MIXED requires roundtable review because it expands effective states from 7 to 10.

---

## 11. Roundtable Process

### 11.1 Deliberation Summary

| Round | Focus | Key Outcomes |
|-------|-------|-------------|
| **Round 1** | Opening positions | 7 independent proposals. Pyre proposed binary taint model. Seren framed as "feedback instrument, not gatekeeper." Quinn proposed 18 samples/rule with dual precision threshold. Gideon proposed decision-scoped exceptions. Iris proposed dual enforcement profiles. |
| **Round 2** | Adversarial challenges | Cross-agent attacks exposed binary taint weaknesses. Seren's framing challenged by Sable. Container contamination demonstrated by Riven. Dual enforcement profiles questioned. |
| **Round 3** | Convergence | **Binary taint rejected 7/7.** Two-dimensional taint model converged (provenance x validation). Gatekeeper-first framing accepted 7/7. Per-rule precision thresholds accepted 6/7. Decision-scope matching replaced with grouped fingerprint governance. Three major concessions: Pyre (binary taint), Seren (gatekeeper framing + threshold), Gideon (decision-scoping implementation). |
| **Round 4** | Design decisions | **Label set decided** (5 provenance x 2 validation, 7 effective states, 6/7). **49-cell rule matrix completed** with corpus verdicts for every cell. **Integration mapping decided** (4 exit codes, SARIF 2.1.0). **Governance model specified** (4-class exceptionability, 4-phase expiry). Key position swaps: Quinn conceded TIER_1/TIER_2 split; Sable reversed Round 3 collapse; Pyre collapsed (minority position). |
| **Round 5** | Final commitment | **7/7 commitment** (6 unconditional, 1 conditional). 5 minority reports filed. 4 known limitations documented. 5 AST edge cases identified. Corpus authoring estimate: 16-24 hours. INFO action-rate metric operationally defined. 3 system dynamics risks documented. |

### 11.2 Position Shift Summary

| Agent | Round 1 | Round 2 | Round 3 | Round 4 | Round 5 |
|-------|---------|---------|---------|---------|---------|
| **Pyre** | Binary taint, 5-level hierarchy | Added alias tracker | **Conceded binary taint.** Proposed 2D: provenance x validation | Collapsed TIER_1/TIER_2 to INTERNAL | **Conceded collapse was wrong.** Committed to 5-label model. Filed MR-1 (@internal_data alias). |
| **Sable** | Default-deny heuristic list, defence-in-depth | Attacked Seren's framing | Conceded binary taint is SPOF. Proposed full 2D model with MIXED. | **Reversed Round 3 collapse** — kept TIER_1/TIER_2 split. Full severity matrix. | Committed. Filed MR-2 (INFO boundaries) and MR-3 (decorator gaps). Security hardening recommendations. |
| **Seren** | Feedback instrument, immutable 95% threshold | Clarified "block on governance, trends on code" | **Double concession**: gatekeeper-first AND per-rule thresholds. Proposed 3-layer Enforcement-Diagnostic Stack. | Reconciled notes with testability. Full matrix. Layer 3 diagnostic spec. | Committed. Filed MR-4 (ERROR rate erosion). Identified 3 system dynamics risks. |
| **Riven** | Structural validation insufficient, evasion taxonomy | Tier-labelled provenance (5 labels) | Conceded to Quinn on nirvana fallacy. Proposed 6-label provenance. | **Conceded to 2D model.** Attacked INFO as compliance laundering. Proposed decorator-consistency checker. | **Conditional commit** on INFO action-rate metric. Withdrew --stdin proposal. |
| **Quinn** | 18 samples/rule, dual precision threshold | Rejection-path requirement | Proposed 4-label provenance with 4-severity grading. | **Double concession**: split TIER_1/TIER_2, added MIXED. Full matrix with corpus estimates. | Committed. Filed and self-closed MR-5 (embedded validation). Provided operational definitions. |
| **Gideon** | Decision-scoped exceptions in matching layer | (Owed response to Iris) | **Conceded** matching layer to Iris. Proposed grouped fingerprint governance. | Exceptionability matrix (4-class). 4-phase expiry lifecycle. Cross-tier grouping constraint. | Committed. Self-critiqued 24 UNCONDITIONAL count (affirmed). Identified 2 governance gaps. |
| **Iris** | Dual enforcement profiles, SARIF-native design | Conceded dual profiles | Conceded binary cleansing overclaims. Mapped provenance to tier-contextualized SARIF. | Complete integration spec: CLI, SARIF, exit codes, manifest, performance budgets. | Committed unconditionally. 5 implementer clarifications. |

### 11.3 Decided vs. Rejected

| Proposal | Proposer | Outcome | Rejection Rationale |
|----------|----------|---------|-------------------|
| Binary taint (tainted/clean) | Pyre (Round 1) | **Rejected 7/7** (Round 3) | Creates compliance ritual; once "clean," all detection disabled for that flow |
| Single immutable 95% precision threshold | Seren (Round 1) | **Rejected** | Permanently excludes .get() (~88%) and broad except (~85%) — the two most valuable rules |
| "Feedback instrument, not gatekeeper" framing | Seren (Round 1) | **Rejected** | Advisory tools without enforcement accumulate backlogs; gatekeeper must be first priority |
| Dual enforcement profiles (human vs. agent) | Iris (Round 1) | **Rejected 7/7** (Round 2) | Same code should get same result; differential enforcement destroys trust |
| Decision-scoped exception matching | Gideon (Round 1) | **Replaced** (Round 3) | Implementation moved to metadata layer (grouped fingerprint governance) |
| TIER_3_VALIDATED as provenance label | Riven (Round 3) | **Rejected** | Violates "provenance never changes" invariant; compound state masquerading as provenance |
| Embedded validation (VALIDATED as provenance) | Quinn (Rounds 3-4) | **Rejected** | Loses origin information; provenance is immutable, validation status evolves |
| TIER_1/TIER_2 collapse to INTERNAL | Pyre (Round 4) | **Rejected 6/1** | Rules diverge on severity (R4: ERROR vs WARN; R7: ERROR vs WARN); governance needs the distinction |
| MIXED collapsed to UNKNOWN | Quinn (Round 3) | **Rejected 7/7** (Round 4) | Eliminates resolution pressure; different developer actions needed |
| INFO blocks in agent mode (--stdin) | Riven (Round 4) | **Rejected** | Reintroduces dual enforcement under different name; UX damage outweighs theoretical distinction |
| UNTRACKED validation status for internal data | Sable (Round 3) | **Dropped** | Overcomplication; validation N/A for internal data is cleaner |

---

## Appendix A: Complete Exceptionability Matrix

Each cell shows Severity / Exceptionability Class.

| Rule | TIER_1 | TIER_2 | T3+RAW | T3+SV | UNK+RAW | UNK+SV | MIXED |
|------|--------|--------|--------|-------|---------|--------|-------|
| **R1** `.get()` | ERROR / UNCONDITIONAL | ERROR / STANDARD | SUPPRESS / TRANSPARENT | SUPPRESS / TRANSPARENT | WARN / LIBERAL | INFO / TRANSPARENT | WARN / STANDARD |
| **R2** `getattr()` | ERROR / UNCONDITIONAL | ERROR / STANDARD | SUPPRESS / TRANSPARENT | SUPPRESS / TRANSPARENT | WARN / LIBERAL | INFO / TRANSPARENT | WARN / STANDARD |
| **R3** `hasattr()` | ERROR / UNCONDITIONAL | ERROR / UNCONDITIONAL | ERROR / UNCONDITIONAL | ERROR / UNCONDITIONAL | ERROR / UNCONDITIONAL | ERROR / UNCONDITIONAL | ERROR / UNCONDITIONAL |
| **R4** Broad `except` | ERROR / UNCONDITIONAL | WARN / STANDARD | SUPPRESS / TRANSPARENT | INFO / TRANSPARENT | WARN / STANDARD | INFO / TRANSPARENT | WARN / STANDARD |
| **R5** Data->audit | SUPPRESS / TRANSPARENT | SUPPRESS / TRANSPARENT | ERROR / UNCONDITIONAL | INFO / TRANSPARENT | WARN / STANDARD | INFO / TRANSPARENT | WARN / STANDARD |
| **R6** `except: pass` | ERROR / UNCONDITIONAL | ERROR / STANDARD | WARN / LIBERAL | WARN / LIBERAL | ERROR / UNCONDITIONAL | WARN / LIBERAL | ERROR / UNCONDITIONAL |
| **R7** `isinstance()` | ERROR / UNCONDITIONAL | WARN / STANDARD | SUPPRESS / TRANSPARENT | SUPPRESS / TRANSPARENT | WARN / LIBERAL | SUPPRESS / TRANSPARENT | WARN / LIBERAL |

**Distribution by exceptionability class:**

| Class | Count | Cells |
|-------|-------|-------|
| UNCONDITIONAL | 24 | R3 (all 7), R1/TIER_1 (1), R2/TIER_1 (1), R4/TIER_1 (1), R5/T3+RAW (1), R5/MIXED (1 — via scribe resolution at WARN, but MIXED+RAW reaches audit is UNCONDITIONAL per Gideon), R6/TIER_1 (1), R6/TIER_2 (1), R6/UNK+RAW (1), R6/MIXED (1), R7/TIER_1 (1) |
| STANDARD | 14 | R1/TIER_2, R1/MIXED, R2/TIER_2, R2/MIXED, R4/TIER_2, R4/UNK+RAW, R4/MIXED, R5/UNK+RAW, R5/MIXED, R6/TIER_2, R7/TIER_2 |
| LIBERAL | 10 | R1/UNK+RAW, R2/UNK+RAW, R6/T3+RAW, R6/T3+SV, R6/UNK+SV, R7/UNK+RAW, R7/MIXED |
| TRANSPARENT | 8 | All SUPPRESS cells (R1/T3+RAW, R1/T3+SV, R2/T3+RAW, R2/T3+SV, R4/T3+RAW, R5/TIER_1, R5/TIER_2, R7/T3+RAW, R7/T3+SV, R7/UNK+SV) plus all INFO cells |

---

## Appendix B: provenanceSource Format Reference

The `sbe.provenanceSource` SARIF property uses one of six stable formats:

| # | Source Type | Format Pattern | Example | When Used |
|---|------------|---------------|---------|-----------|
| 1 | Method call | `"{receiver}.{method}()"` | `"self._recorder.get_row_state()"` | Heuristic list match or decorated method call |
| 2 | Parameter | `"{param} parameter"` | `"row parameter"` | Transform `row` parameter, function arguments with provenance |
| 3 | Decorator | `"@{decorator} on {function}"` | `"@external_boundary on fetch_data"` | Function return value with provenance decorator |
| 4 | Heuristic | `"heuristic: {pattern}"` | `"heuristic: requests.get"` | Matched against heuristic external_calls list |
| 5 | Topology | `"topology: {tier}"` | `"topology: tier_1"` | Module matched by topology glob pattern |
| 6 | Default | `"unknown"` | `"unknown"` | No provenance source determinable |

`sbe.provenanceSourceLine` is `null` for types 2, 5, and 6 (no specific line). Emit the field with `null` value — do not omit it.

---

## Appendix C: strict.toml Schema Reference

### Top-Level

```toml
[tool.strict]
version = "0.1"                    # Required. Schema version.
# coverage_mode = "tracked"        # Optional. Emits summary of unmanifested files.
```

### Topology Section

```toml
[tool.strict.topology]
tier_1 = ["glob/pattern/**"]       # Module globs for TIER_1 provenance.
tier_2 = ["glob/pattern/**"]       # Module globs for TIER_2 provenance.
# TIER_3 identified by decorators + heuristic list — no manifest entry needed.
# UNKNOWN is the default for unmatched files.
```

- `*` matches single directory level. `**` matches recursively.
- Overlap between `tier_1` and `tier_2` globs is a tool error (exit 2).

### Rules Section

```toml
[tool.strict.rules.SBE-R01]
blocking = true                    # Whether this rule blocks CI at its precision threshold.
precision_threshold = 0.88         # Per-rule earned threshold (>= 0.80 floor). Monotonically non-decreasing.
```

One `[tool.strict.rules.<ID>]` section per rule. Absent rules use defaults (blocking = true, threshold = 0.80).

### Heuristics Section

```toml
[tool.strict.heuristics]
external_calls = [                 # Glob-style patterns for external call detection.
    "requests.*",
    "httpx.*",
    "json.loads",
    # ...
]
```

Return values from matched calls receive TIER_3 provenance.

### Exceptions Section

```toml
[[tool.strict.exceptions]]
fingerprint = "a1b2c3d4e5f6"      # Required. SHA-256 truncated to 12 hex chars.
rule = "SBE-R01"                   # Required. Rule ID.
file = "src/path/to/file.py"      # Required. File path.
decision_group = "group-name"      # Optional. Groups findings with shared rationale.
expires = "2026-09-01"             # Required for STANDARD (90 days) and LIBERAL (180 days).
created_by = "author"              # Optional. Populated by `strict review`.
created_at = "2026-03-01"          # Optional.
last_renewed_by = "author"         # Optional.
last_renewed_at = "2026-03-01"     # Optional.

[tool.strict.exceptions.review]
decision_rationale = "..."         # Required. The justification.
reviewer = "name"                  # Optional.
trust_tier = "tier2"               # Optional. Which tier the exception covers.
```

**Constraints:**
- UNCONDITIONAL cells (24 of 49): tool rejects exception creation at parse time.
- `decision_group` may not span TIER_1 and TIER_2 findings.
- Fingerprint algorithm: SHA-256 of `"{rule_id}:{file_path}:{normalized_ast_node}"`, truncated to 12 hex chars.
- STANDARD expiry: 90 days. LIBERAL expiry: 180 days. TRANSPARENT/SUPPRESS: no exceptions.

---

*Compiled by Morgan (Roundtable Scribe) from five rounds of adversarial deliberation, 8 March 2026.*
