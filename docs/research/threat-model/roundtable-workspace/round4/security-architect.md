# Round 4 — Focused Dissent: Sable (Security Architect)

## Open Item 1: Exact Label Set — TIER_1/TIER_2 Collapse Reversed

In Round 3, I collapsed TIER_1 and TIER_2 into a single provenance. I'm reversing that position. Here's why.

### The Collapse Was Wrong

Quinn argues TIER_1/TIER_2 is "not AST-observable." This is technically correct and completely irrelevant. TIER_3 is also not AST-observable without decorators — we use `@external_boundary` to declare it. The tool already requires developer declarations for provenance. Adding `@tier1_data` (or `@audit_boundary`) is the same architectural pattern, not a new burden.

The security argument for keeping them distinct is not about precision tuning — it's about **severity separation for the same violation pattern**. Consider:

```python
# Both are .get() on "our data" — but the consequences differ by orders of magnitude

# Tier 1: audit database read
state = recorder.get_state(token_id)
value = state.get("classification", "unknown")  # Evidence tampering. Legal exposure.

# Tier 2: pipeline data
row = transform_input.to_dict()
value = row.get("amount", 0)                    # Bug masking. Upstream contract violation.
```

Same AST pattern. Same rule fires. But:
- **Tier 1 `.get()` with default:** ACF-I1 (Critical) — fabricating audit evidence. The developer action is "crash immediately, this is corruption."
- **Tier 2 `.get()` with default:** ACF-I1 (High) — masking an upstream bug. The developer action is "fix the upstream transform or remove the default."

If we collapse these, every `.get()` finding on "internal data" gets the same severity. Either we set it to Critical (over-alerting on Tier 2, governance fatigue) or High (under-alerting on Tier 1, false assurance on audit paths). Neither is acceptable.

### Declaration Cost Is Minimal

The burden argument doesn't hold. In practice:
- **Tier 1 declarations are rare.** Only Landscape recorder access, checkpoint reads, and deserialized audit JSON. Maybe 10-15 functions in the entire ELSPETH codebase.
- **Tier 2 is the default for undeclared internal data.** If the tool sees data from a function call without a Tier 1 or Tier 3 declaration, it's TIER_2 (pipeline data) — the elevated-trust middle ground.
- **Tier 3 declarations already exist** via `@external_boundary`.

The asymmetry is correct: Tier 1 is the smallest, most critical category. Requiring explicit declaration for the most critical data tier is defence-in-depth — the developer must consciously assert "this is audit data" for the tool to apply the highest severity rules.

### Advocated Label Set

**Provenance:** `{TIER_1, TIER_2, TIER_3, UNKNOWN, MIXED}`

| Label | Meaning | Declaration | Default? |
|-------|---------|-------------|----------|
| `TIER_1` | Audit trail data (Landscape, checkpoints, deserialized audit JSON) | `@audit_boundary` or manifest entry | No — must be declared |
| `TIER_2` | Pipeline data (validated, schema-conformant) | Implicit — default for undeclared internal data | Yes |
| `TIER_3` | External data (APIs, user input, file reads) | `@external_boundary` or heuristic match | No — declared or heuristic |
| `UNKNOWN` | Cannot determine provenance | Automatic — function returns in v0.1 | Yes (v0.1 limitation) |
| `MIXED` | Container with heterogeneous provenance | Automatic — derived from container contents | Yes (computed) |

**Validation status:** `{RAW, STRUCTURALLY_VALIDATED}`

| Label | Meaning | Transition |
|-------|---------|------------|
| `RAW` | No validation observed | Initial state for TIER_3 and UNKNOWN |
| `STRUCTURALLY_VALIDATED` | Passed through validator with rejection path | `@validates_external` with reachable `raise` |

VERIFIED is deferred to v1.0 (requires inter-procedural analysis). I agree with Pyre here.

**Why not UNTRACKED?** My Round 3 model had three validation states including UNTRACKED for internal data. This was overcomplication. TIER_1 and TIER_2 data doesn't need validation status tracking — it's our data. Validation status is only meaningful for TIER_3 and UNKNOWN data (did external data pass through a validator?). For TIER_1 and TIER_2, the validation dimension is implicitly N/A — the provenance label alone drives rule evaluation. This means the effective state space is smaller than 5×2=10:

| Provenance | Validation States Used | Effective States |
|------------|----------------------|------------------|
| TIER_1 | N/A (provenance drives rules) | 1 |
| TIER_2 | N/A (provenance drives rules) | 1 |
| TIER_3 | RAW, STRUCTURALLY_VALIDATED | 2 |
| UNKNOWN | RAW, STRUCTURALLY_VALIDATED | 2 |
| MIXED | RAW (always — cannot validate mixed container) | 1 |

**Total effective states: 7**, not 10. This is a manageable corpus requirement.

---

## Open Item 2: Complete Provenance × Validation × Rule Matrix

### Matrix Structure

I use Quinn's 4-category system for corpus verdicts. Rules are abbreviated:
- **R1:** `.get()` with default value
- **R2:** `getattr()` with default value
- **R3:** `hasattr()` (unconditional ban)
- **R4:** Broad `except` (bare except, `except Exception`)
- **R5:** Silent exception swallowing (`except: pass`, `except: return default`)
- **R6:** `isinstance()` as guard before access (defensive type checking)

### R1: `.get()` with Default Value

The canonical ACF-I1 pattern. Context determines everything.

| Provenance | Validation | Severity | Corpus Verdict | Rationale |
|------------|-----------|----------|----------------|-----------|
| TIER_1 | N/A | **ERROR** | `true_positive` | Fabricating audit evidence. Legal exposure. Crash-on-anomaly mandate. |
| TIER_2 | N/A | **ERROR** | `true_positive` | Masking upstream contract violation. Wrong types = upstream bug per CLAUDE.md. |
| TIER_3 + RAW | — | **SUPPRESS** | `true_negative` | Legitimate — coercion at source boundary is allowed. |
| TIER_3 + STRUCTURALLY_VALIDATED | — | **SUPPRESS** | `true_negative` | Validated data — `.get()` may be accessing optional fields legitimately. |
| UNKNOWN + RAW | — | **WARN** | `true_positive_reduced` | Can't determine provenance. Flag at reduced confidence — may be internal or external. |
| UNKNOWN + STRUCTURALLY_VALIDATED | — | **SUPPRESS** | `true_negative` | Validated data from unknown source — developer has taken responsibility. |
| MIXED | RAW | **ERROR** | `true_positive` | Mixed-provenance container — decompose access. `.get()` on mixed data risks Tier 1 fabrication. |

**Security rationale for TIER_2 as ERROR not WARN:** ELSPETH's data manifesto is explicit — "No coercion at transform/sink level. Wrong types = upstream bug." A `.get()` with default on pipeline data isn't a reduced-confidence finding, it's a clear violation of the project's own rules. The developer action is unambiguous: remove the default, let the KeyError surface, fix the upstream plugin.

### R2: `getattr()` with Default Value

Structurally identical to R1 — same matrix applies. `getattr(obj, "field", default)` is `.get()` for attribute access.

| Provenance | Validation | Severity | Corpus Verdict |
|------------|-----------|----------|----------------|
| TIER_1 | N/A | **ERROR** | `true_positive` |
| TIER_2 | N/A | **ERROR** | `true_positive` |
| TIER_3 + RAW | — | **SUPPRESS** | `true_negative` |
| TIER_3 + SV | — | **SUPPRESS** | `true_negative` |
| UNKNOWN + RAW | — | **WARN** | `true_positive_reduced` |
| UNKNOWN + SV | — | **SUPPRESS** | `true_negative` |
| MIXED | RAW | **ERROR** | `true_positive` |

### R3: `hasattr()` — Unconditional Ban

`hasattr()` is unconditionally banned per CLAUDE.md. Provenance doesn't matter — it's always wrong.

| Provenance | Validation | Severity | Corpus Verdict | Rationale |
|------------|-----------|----------|----------------|-----------|
| TIER_1 | N/A | **ERROR** | `true_positive` | Unconditional ban. `hasattr` swallows `@property` exceptions. |
| TIER_2 | N/A | **ERROR** | `true_positive` | Unconditional ban. |
| TIER_3 + RAW | — | **ERROR** | `true_positive` | Unconditional ban — even at boundary, use `isinstance` or try/except. |
| TIER_3 + SV | — | **ERROR** | `true_positive` | Unconditional ban. |
| UNKNOWN + RAW | — | **ERROR** | `true_positive` | Unconditional ban. |
| UNKNOWN + SV | — | **ERROR** | `true_positive` | Unconditional ban. |
| MIXED | RAW | **ERROR** | `true_positive` | Unconditional ban. |

**Note:** R3 doesn't need provenance for its verdict, but provenance enriches the *message*. `hasattr()` on TIER_1 gets: "hasattr on audit data — swallows @property exceptions, use direct access (Tier 1 crash-on-anomaly)." On TIER_3: "hasattr at boundary — use isinstance() check or try/except AttributeError."

### R4: Broad `except` (bare except, `except Exception`)

This is where provenance creates the most divergent verdicts.

| Provenance | Validation | Severity | Corpus Verdict | Rationale |
|------------|-----------|----------|----------------|-----------|
| TIER_1 | N/A | **ERROR** | `true_positive` | Swallowing audit data errors = evidence destruction (ACF-I3). |
| TIER_2 | N/A | **ERROR** | `true_positive` | Swallowing pipeline errors = hiding upstream bugs. |
| TIER_3 + RAW | — | **WARN** | `true_positive_reduced` | Broad catch at boundary is *almost* legitimate — should use specific exception types. |
| TIER_3 + SV | — | **WARN** | `true_positive_reduced` | Validated data ops shouldn't need broad catch. Reduced confidence — may be wrapping legitimate external call. |
| UNKNOWN + RAW | — | **WARN** | `true_positive_reduced` | Can't determine provenance. Broad catch is suspicious. |
| UNKNOWN + SV | — | **INFO** | `true_note` | Validated unknown data — broad catch may be wrapping complex validated pipeline. |
| MIXED | RAW | **ERROR** | `true_positive` | Mixed-provenance in broad catch — cannot distinguish Tier 1 errors from Tier 3 errors. |

**Security rationale for TIER_3 + RAW as WARN not SUPPRESS:** ELSPETH's trust model says to wrap external calls in try/except — but with *specific* exception types, not bare `except`. `except requests.RequestException` is legitimate boundary handling. `except Exception` at a boundary swallows `KeyboardInterrupt`, `SystemExit`, and any Tier 1 errors that happen to occur in the same block. WARN, not SUPPRESS, because the pattern is approximately correct but the implementation is dangerously broad.

### R5: Silent Exception Swallowing

`except: pass`, `except Exception: return default_value`, `except: continue` — the error is caught and discarded.

| Provenance | Validation | Severity | Corpus Verdict | Rationale |
|------------|-----------|----------|----------------|-----------|
| TIER_1 | N/A | **ERROR** | `true_positive` | Silently swallowing audit errors = evidence destruction. |
| TIER_2 | N/A | **ERROR** | `true_positive` | Silently swallowing pipeline errors = bug hiding. |
| TIER_3 + RAW | — | **WARN** | `true_positive_reduced` | Swallowing boundary errors — should quarantine, not discard. |
| TIER_3 + SV | — | **WARN** | `true_positive_reduced` | Swallowing validated data errors — should surface, not discard. |
| UNKNOWN + RAW | — | **WARN** | `true_positive_reduced` | Unknown provenance, silent swallow is suspicious. |
| UNKNOWN + SV | — | **WARN** | `true_positive_reduced` | Even validated — silent discard loses information. |
| MIXED | RAW | **ERROR** | `true_positive` | Mixed-provenance silent swallow — may discard Tier 1 errors. |

### R6: Defensive `isinstance()` Guard

`isinstance()` used as a type guard before accessing data — defensive programming pattern.

| Provenance | Validation | Severity | Corpus Verdict | Rationale |
|------------|-----------|----------|----------------|-----------|
| TIER_1 | N/A | **ERROR** | `true_positive` | Tier 1 data should be correct type. `isinstance` guard hides corruption. |
| TIER_2 | N/A | **WARN** | `true_positive_reduced` | Pipeline data types guaranteed by source validation. Guard suggests distrust of contract. |
| TIER_3 + RAW | — | **SUPPRESS** | `true_negative` | Legitimate — type checking at boundary is correct practice. |
| TIER_3 + SV | — | **SUPPRESS** | `true_negative` | Validated data — additional type check is belt-and-suspenders, not harmful. |
| UNKNOWN + RAW | — | **INFO** | `true_note` | Unknown provenance type guard — note for human review. |
| UNKNOWN + SV | — | **SUPPRESS** | `true_negative` | Validated unknown — type guard is reasonable caution. |
| MIXED | RAW | **WARN** | `true_positive_reduced` | Mixed-provenance type guard — decompose the container instead. |

### Severity Distribution Summary

Across all 6 rules × 7 effective states = 42 matrix cells:

| Severity | Count | Percentage |
|----------|-------|------------|
| ERROR | 19 | 45% |
| WARN | 12 | 29% |
| INFO | 2 | 5% |
| SUPPRESS | 9 | 21% |

**Security assessment:** This distribution is healthy. The tool is not trigger-happy (21% suppress rate shows provenance-aware context). The ERROR-heavy bias reflects ELSPETH's trust model — most defensive patterns on internal data are genuine violations. The low INFO count (2 cells) means almost no findings land in the ambiguous "note but don't block" category, which reduces the compliance ritual surface.

---

## Open Item 3: Integration Mapping — INFO/NOTE Must Be Non-Blocking But Visible

### The Compliance Ritual Displacement Question

The scribe asks: if INFO findings are non-blocking (exit 3), does the compliance ritual simply shift from "tool says clean" to "tool says note, developer ignores note"?

**Yes, partially. And that's acceptable.** Here's the security argument:

The compliance ritual we eliminated (binary taint cleansing) was dangerous because it claimed certainty: "this data is clean." The tool's green light *replaced* human judgment. A developer seeing "0 findings" reasonably concludes "no issues."

An INFO finding is structurally different. It says: "I found something that *might* matter. Here's the provenance chain. You decide." The tool explicitly declines to claim certainty. The compliance ritual displacement is:

| Binary Model | 2D Model |
|-------------|----------|
| Tool says "clean" → developer trusts tool → nobody reviews | Tool says "1 note" → developer *may* ignore → but the note is *in the SARIF output* |

The key difference: **the note persists in the artifact**. Even if the immediate developer ignores it, the SARIF output is available to:
1. Code reviewers (GitHub "notice" annotations are visible in PR diffs)
2. Security auditors (SARIF is the interchange format)
3. Trend analysis (Seren's diagnostic layer tracks note volume over time)
4. Post-incident investigation ("the tool flagged this 3 months ago as INFO")

This is defence-in-depth applied to the governance layer: the immediate gate may not catch it, but the information exists in multiple downstream systems.

### The Two INFO Cells

Looking at my matrix, only 2 of 42 cells produce INFO:
1. **R4 (broad except) on UNKNOWN + STRUCTURALLY_VALIDATED:** Broad catch around validated data from unknown source.
2. **R6 (isinstance guard) on UNKNOWN + RAW:** Type guard on data of unknown provenance.

Both are genuinely ambiguous. The tool doesn't know where the data came from (UNKNOWN), so it can't determine if the pattern is a violation (internal data) or legitimate (external data). INFO is the honest answer: "I can't tell. Here's what I see."

### Severity-to-Integration Mapping

| Severity | Exit Code | Pre-commit | CI Gate | SARIF Level | GitHub Annotation | Blocks Merge? |
|----------|-----------|-----------|---------|-------------|-------------------|---------------|
| **ERROR** | 1 | Block | Block | `error` | Error | Yes |
| **WARN** | 1 | Block | Block | `warning` | Warning | Yes |
| **INFO** | 3 | Pass | Pass (advisory) | `note` | Notice | No |
| **SUPPRESS** | 0 | — | — | — | — | No |

### Exit Code Semantics

| Code | Meaning | Developer Action |
|------|---------|-----------------|
| 0 | No findings (or all suppressed) | Proceed |
| 1 | Blocking findings (ERROR or WARN) | Fix violations before merge |
| 2 | Tool error (parse failure, config error) | Fix tool configuration — never silently pass |
| 3 | Advisory findings only (INFO) | Review notes, proceed at discretion |

**Security-critical: exit 2 must NEVER be treated as pass.** If the tool can't run, the gate is open. CI should treat exit 2 as a blocking failure. This is Iris's proposal and I endorse it without reservation — a tool that silently passes when broken provides worse-than-no assurance.

### Pre-commit vs CI Asymmetry

One integration nuance: pre-commit should treat exit 3 as pass (developer flow must not block on ambiguous findings during rapid iteration). CI should *display* exit 3 findings but not block. This asymmetry is acceptable because:

1. **Pre-commit is the fast-feedback loop.** Blocking on INFO disrupts flow and breeds `--no-verify`.
2. **CI is the authoritative gate.** INFO findings appear in the PR as "notice" annotations, visible to reviewers.
3. **The compliance ritual risk is managed by visibility**, not by blocking. A reviewer who sees 15 "notice" annotations will investigate. A reviewer who sees 0 annotations (because INFO was suppressed at pre-commit) won't.

### The "Validated-Not-Verified" Case Specifically

The scribe called out TIER_3 + STRUCTURALLY_VALIDATED reaching an audit write. In my matrix this doesn't appear as INFO — it appears as follows:

- **TIER_3 + STRUCTURALLY_VALIDATED** data reaching an audit write path isn't covered by R1-R6 directly. It would be a separate rule: **R7 (provenance-at-sink)** — external-origin data reaching Tier 1 write operations.

For completeness, here's R7's matrix:

| Provenance | Validation | Severity | Corpus Verdict | Rationale |
|------------|-----------|----------|----------------|-----------|
| TIER_1 | N/A | **SUPPRESS** | `true_negative` | Audit data reaching audit write — correct flow. |
| TIER_2 | N/A | **SUPPRESS** | `true_negative` | Pipeline data recorded in audit — correct flow. |
| TIER_3 + RAW | — | **ERROR** | `true_positive` | Unvalidated external data reaching audit write — ACF-I2 trust boundary bypass. |
| TIER_3 + SV | — | **INFO** | `true_note` | Validated external data reaching audit write — structurally validated but semantic adequacy unknown. Human review required. |
| UNKNOWN + RAW | — | **WARN** | `true_positive_reduced` | Unknown-provenance unvalidated data reaching audit write. |
| UNKNOWN + SV | — | **INFO** | `true_note` | Unknown validated data reaching audit — note for review. |
| MIXED | RAW | **ERROR** | `true_positive` | Mixed-provenance data reaching audit write — decompose first. |

**This is where the compliance ritual question bites hardest.** TIER_3 + STRUCTURALLY_VALIDATED → audit write is INFO, not ERROR. The tool says "structurally validated, human review required" as a non-blocking note. Is this a compliance ritual?

**My answer: no, because the tool is being honest about its epistemic limits.** The tool cannot verify that `validate_response()` adequately checks all fields needed for audit integrity. Blocking on this cell means *every* external data flow to audit requires a allowlist entry, which is exactly the exception inflation that kills governance. INFO is the right severity because:

1. The developer *did* validate (STRUCTURALLY_VALIDATED confirms control flow with rejection path)
2. The tool *cannot* verify adequacy (static analysis limit)
3. The note preserves the information for reviewers
4. Trend analysis catches patterns (if 50 flows are INFO, that's a systemic gap signal)

If we made this ERROR, every LLM transform that validates API responses and records results would require an allowlist entry. That's not security — that's bureaucracy.

### Updated Severity Distribution (with R7)

Adding R7's 7 cells to the matrix: 49 total cells.

| Severity | Count | Percentage |
|----------|-------|------------|
| ERROR | 21 | 43% |
| WARN | 13 | 27% |
| INFO | 4 | 8% |
| SUPPRESS | 11 | 22% |

The INFO proportion remains low (4/49 = 8%), confirming that the "ambiguous advisory" category is narrow. The tool takes a clear position in 92% of cases.

---

## Summary of Positions

| Item | My Position | Changed from Round 3? |
|------|-------------|----------------------|
| TIER_1/TIER_2 collapse | **Reversed — keep distinct.** Severity separation justifies declaration cost. | Yes — reversed |
| Provenance labels | `{TIER_1, TIER_2, TIER_3, UNKNOWN, MIXED}` — 5 labels | Extended from 4 |
| Validation labels | `{RAW, STRUCTURALLY_VALIDATED}` — 2 states, applicable only to TIER_3/UNKNOWN | Simplified from 3 |
| Effective state space | 7 states (not 10) due to validation N/A on internal data | New refinement |
| INFO non-blocking | Yes — defence-in-depth via persistence and visibility, not blocking | Consistent |
| Exit 2 (tool error) | Must block — open gate is worse than no tool | Consistent |
| TIER_3 + SV → audit write | INFO, not ERROR — honest about epistemic limits | New position |

### Where I Expect Pushback

1. **Quinn** will challenge whether 7 effective states produces a tractable corpus. My answer: 7 × 7 rules = 49 cells. At Quinn's 18 samples per rule, that's corpus design per rule, not per cell. The matrix determines *what* each sample should produce, not *how many* samples exist.

2. **Riven** will probe the TIER_2 ERROR severity for R1 (`.get()`). "Isn't pipeline data `.get()` sometimes legitimate for optional fields?" My answer: ELSPETH's data manifesto says no. Optional fields should use explicit `None` checks, not `.get()` with fabricated defaults. If a field is optional, the schema declares it optional and the code checks `if field is not None`. `.get("field", default)` fabricates a value — that's the distinction.

3. **Seren** will note that the 43% ERROR rate creates governance pressure. My answer: ERROR means "this fires and blocks." The 80% precision floor means up to 20% of those firings may be false positives. Per-rule thresholds earned via corpus evidence will tune this. The matrix defines *what should happen* given correct provenance labelling — the precision question is orthogonal.
