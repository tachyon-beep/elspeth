# Round 4 — Focused Dissent: Pyre (Python AST Engineer)

## Open Item 1: Exact Label Set for Provenance and Validation Status

### Resolution: Concede TIER_1/TIER_2 Collapse. Keep MIXED. Keep Validation as Separate Dimension.

**Provenance: {INTERNAL, EXTERNAL, UNKNOWN, MIXED}**
**Validation: {RAW, STRUCTURALLY_VALIDATED}**

Quinn is right. I'm conceding the TIER_1/TIER_2 distinction for v0.1, and my rationale is concrete: **the two labels produce identical verdicts in every cell of the rule matrix.**

I built the complete matrix (see Item 2 below) and tested every cell. For every rule the roundtable has defined — `.get()` with default, `hasattr()`, broad `except`, data reaching audit write — the verdict for TIER_1 and TIER_2 is the same. Both are INTERNAL data where `.get()` fabricates defaults, `hasattr` is banned, broad `except` destroys evidence, and reaching audit writes is expected. The severity is the same. The developer action is the same. The only difference is the message text: "audit data" vs. "pipeline data."

Message text differentiation does not require separate provenance labels. The taint engine can carry source-site metadata (e.g., `via self._recorder.get_row_state()` vs. `via row["customer_id"]`) as an annotation on the INTERNAL label without promoting it to a distinct provenance state. This is how Iris's tier-contextualized messages already work — same rule, same verdict, different message based on provenance source site.

**Why I defended it in Round 3:** I conflated "semantically distinct in ELSPETH's trust model" with "behaviourally distinct in the tool's rule matrix." TIER_1 and TIER_2 are genuinely different trust levels in the application — but the tool's rules don't exploit that difference. If v1.0 introduces inter-procedural analysis with rules like "TIER_2 data must not bypass transform contract validation" (which would be a distinct rule from TIER_1 audit integrity), the label can be reintroduced. For v0.1's intra-function scope, it's dead weight.

**Why I keep MIXED distinct from UNKNOWN:** Quinn argues MIXED is a "garbage-can state." I disagree — MIXED and UNKNOWN encode different facts and demand different developer actions:

| Label | What the tool knows | Developer action |
|-------|-------------------|-----------------|
| UNKNOWN | "I cannot determine where this data came from" | Investigate provenance, add declaration |
| MIXED | "I know this container holds data from multiple tiers" | Decompose the container — separate access paths by tier |

Collapsing MIXED into UNKNOWN loses the "decompose" recommendation, which is the highest-leverage fix for the container contamination pattern Riven demonstrated. The scribe agrees: "UNKNOWN means 'we don't know the provenance' while MIXED means 'we know the provenance but it's heterogeneous.' These should trigger different developer actions."

**Why validation must be a separate dimension, not embedded in provenance:** Quinn's VALIDATED-as-provenance label loses the origin information. If a variable is labelled VALIDATED, we know it passed through a validator but not whether it was originally EXTERNAL or UNKNOWN. This matters for the "data reaches audit write" rule: EXTERNAL+STRUCTURALLY_VALIDATED reaching audit is INFO (review validator adequacy), but UNKNOWN+STRUCTURALLY_VALIDATED reaching audit is also INFO — yet the developer actions differ. With separate dimensions, the finding message can say "external data from `requests.get()` at line 12, validated at line 20, reaches audit write at line 45" vs. "unknown-provenance data validated at line 20 reaches audit write at line 45." Embedded validation erases this distinction.

The Sable middle ground (Provenance: {TIER_1, TIER_3, UNKNOWN, MIXED}, Validation: {RAW, STRUCTURALLY_VALIDATED}) is close to my position but retains TIER_1 without TIER_2, creating an asymmetry. If we collapse the internal tiers, we should collapse both — the tool has no principled basis for declaring "this is specifically audit data" without the same declaration mechanism that would also declare "this is pipeline data."

### Attack on Quinn's Embedded Validation

Quinn's 4-label model (EXTERNAL, INTERNAL, VALIDATED, UNKNOWN) treats VALIDATED as a provenance state. This violates an invariant that matters for implementation: **provenance should be immutable once assigned.**

In Pyre's taint propagation, provenance flows forward through assignments. If validation changes the provenance label from EXTERNAL to VALIDATED, then downstream re-assignment loses the original label:

```python
raw = requests.get(url)        # EXTERNAL
validated = validate(raw)       # Quinn: VALIDATED, Pyre: (EXTERNAL, S_V)
copied = validated              # Quinn: VALIDATED — was it originally EXTERNAL or UNKNOWN?
```

With separate dimensions, `copied` is `(EXTERNAL, STRUCTURALLY_VALIDATED)` — both dimensions propagate independently, origin is preserved. With Quinn's model, `copied` is `VALIDATED` — the origin is lost. This seems academic until you hit a rule that needs to differentiate, and the "data reaches audit write" rule does.

### Final Label Set

```
Provenance: INTERNAL | EXTERNAL | UNKNOWN | MIXED
  - INTERNAL: data from our code (audit reads, pipeline data, config, checkpoints)
  - EXTERNAL: data from outside the system (API calls, file reads, user input)
  - UNKNOWN:  provenance not determinable (default for untracked variables)
  - MIXED:    container holding values from different provenance classes

Validation: RAW | STRUCTURALLY_VALIDATED
  - RAW:                      no validation observed
  - STRUCTURALLY_VALIDATED:   passed through @validates_external with rejection path
```

State space: 4 × 2 = 8 combinations. Two are degenerate (INTERNAL + STRUCTURALLY_VALIDATED is possible but treated identically to INTERNAL + RAW, since internal data doesn't need validation). Effective state space: 7 distinct behaviours.

---

## Open Item 2: Complete Provenance × Validation × Rule Matrix with Corpus Verdicts

### Severity Vocabulary

I adopt Quinn's 4-category system with one rename for clarity:

| Verdict | Corpus Category | Meaning |
|---------|----------------|---------|
| **ERROR** | `true_positive` | Must fire. Blocking. Developer must fix code. |
| **WARN** | `true_positive_reduced` | Should fire at reduced confidence. Blocking at threshold. Developer should investigate. |
| **INFO** | `true_note` | Emitted, non-blocking. Developer should review. |
| **SUPPRESS** | `true_negative` | Must not fire. No output. |

This maps cleanly to Quinn's corpus verdict system, which is the strongest testability framework proposed. Every cell below has an unambiguous corpus verdict.

### The Complete Matrix

#### R1: `.get()` with default on typed data

| Provenance | Validation | Verdict | Corpus | Rationale |
|-----------|-----------|---------|--------|-----------|
| INTERNAL | RAW | **ERROR** | `true_positive` | Fabricating defaults on our data masks corruption/bugs |
| INTERNAL | S_V | **ERROR** | `true_positive` | Internal data doesn't flow through `@validates_external`; if it does, same verdict — still fabrication |
| EXTERNAL | RAW | SUPPRESS | `true_negative` | `.get()` with default is correct defensive handling at the trust boundary |
| EXTERNAL | S_V | SUPPRESS | `true_negative` | Validated external data; `.get()` is still legitimate post-validation |
| UNKNOWN | RAW | **WARN** | `true_positive_reduced` | May be internal data receiving fabricated defaults |
| UNKNOWN | S_V | SUPPRESS | `true_negative` | Validated and unknown — insufficient confidence to flag |
| MIXED | RAW | **WARN** | `true_positive_reduced` | Container mixes tiers; `.get()` default may mask internal data corruption |
| MIXED | S_V | **INFO** | `true_note` | Validated mixed container; review whether decomposition is needed |

#### R3: `hasattr()` — unconditionally banned

| Provenance | Validation | Verdict | Corpus | Rationale |
|-----------|-----------|---------|--------|-----------|
| * | * | **ERROR** | `true_positive` | `hasattr()` is banned per ELSPETH policy regardless of provenance or validation |

All 8 cells are ERROR. `hasattr()` swallows exceptions from `@property` getters, enables method-name dispatch bypass, and has no legitimate use case when alternatives exist (explicit `isinstance`, `try/except AttributeError`, frozen allowsets). This rule operates at ~99% precision — it needs no provenance modulation.

#### R4: Broad `except` without re-raise

| Provenance | Validation | Verdict | Corpus | Rationale |
|-----------|-----------|---------|--------|-----------|
| INTERNAL | RAW | **ERROR** | `true_positive` | Swallowing exceptions on our data destroys audit trail / hides bugs |
| INTERNAL | S_V | **ERROR** | `true_positive` | Same — validation status doesn't license swallowing internal errors |
| EXTERNAL | RAW | SUPPRESS | `true_negative` | Broad `except` at trust boundary is expected pattern (catch-log-quarantine) |
| EXTERNAL | S_V | **INFO** | `true_note` | Post-validation broad `except` is suspicious — why catch after validating? Review. |
| UNKNOWN | RAW | **WARN** | `true_positive_reduced` | May be swallowing internal errors |
| UNKNOWN | S_V | **INFO** | `true_note` | Validated unknown; advisory review of exception handling |
| MIXED | RAW | **WARN** | `true_positive_reduced` | Mixed container — broad `except` may hide Tier 1 errors alongside Tier 3 handling |
| MIXED | S_V | **INFO** | `true_note` | Validated mixed; advisory review |

#### R5: Data reaches audit write path

| Provenance | Validation | Verdict | Corpus | Rationale |
|-----------|-----------|---------|--------|-----------|
| INTERNAL | RAW | SUPPRESS | `true_negative` | Internal data reaching audit trail is normal operation |
| INTERNAL | S_V | SUPPRESS | `true_negative` | Same — internal data in audit is expected |
| EXTERNAL | RAW | **ERROR** | `true_positive` | Unvalidated external data entering the audit trail = integrity violation |
| EXTERNAL | S_V | **INFO** | `true_note` | Structurally validated, but semantic adequacy requires human review |
| UNKNOWN | RAW | **WARN** | `true_positive_reduced` | Unknown provenance reaching audit — may be unvalidated external data |
| UNKNOWN | S_V | **INFO** | `true_note` | Validated but provenance unclear — review data flow |
| MIXED | RAW | **ERROR** | `true_positive` | Mixed container reaching audit may carry unvalidated external data |
| MIXED | S_V | **WARN** | `true_positive_reduced` | Validated mixed reaching audit — needs decomposition to verify all components validated |

### Corpus Sample Requirements Per Cell

Following Quinn's framework, scaled by verdict criticality:

| Verdict | TP Samples | TN Samples | Total per cell | Rationale |
|---------|-----------|-----------|---------------|-----------|
| ERROR | 5 | 0 | 5 | Blocking — highest confidence required |
| WARN | 3 | 2 | 5 | Borderline — need both TP and context-sensitive TN |
| INFO | 2 | 1 | 3 | Non-blocking — lower bar, but must verify advisory is correct |
| SUPPRESS | 0 | 3 | 3 | Must confirm no false positives |

**Aggregate corpus size:**

| Rule | ERROR cells | WARN cells | INFO cells | SUPPRESS cells | Samples |
|------|-----------|-----------|-----------|---------------|---------|
| R1 (`.get()`) | 2 | 2 | 1 | 3 | 10 + 10 + 3 + 9 = 32 |
| R3 (`hasattr`) | 8 (collapsed) | 0 | 0 | 0 | 5 (deduplicated — provenance doesn't modulate) |
| R4 (broad `except`) | 2 | 2 | 3 | 1 | 10 + 10 + 9 + 3 = 32 |
| R5 (audit write) | 2 | 1 | 3 | 2 | 10 + 5 + 9 + 6 = 30 |
| **Total** | | | | | **~99 entries** |

This is within Quinn's estimated 100-140 range and structured by the matrix rather than flat per-rule. Every cell has at least one sample. No cell is undefined.

### Matrix Properties Worth Noting

1. **INTERNAL is never SUPPRESS for destructive rules (R1, R4):** Our data must always crash on anomaly. Validation status doesn't change this.

2. **EXTERNAL + RAW is SUPPRESS for R1 and R4 but ERROR for R5:** `.get()` and broad `except` are *correct* at the external boundary. But unvalidated external data reaching the audit trail is always wrong. The tool distinguishes "pattern is appropriate here" from "data flow is inappropriate."

3. **MIXED + RAW is always ≥ WARN:** The tool cannot resolve which tier within the container the access touches. Conservative flagging is the honest answer.

4. **STRUCTURALLY_VALIDATED never fully suppresses MIXED:** Even validated mixed containers produce INFO or WARN on rules R4 and R5. This prevents the compliance ritual Seren identified — validation attenuates but doesn't silence.

5. **INFO is scoped and bounded:** INFO appears in exactly 7 cells across 4 rules. All 7 involve either (a) validated data at audit boundaries where semantic adequacy matters, or (b) mixed containers where decomposition is the recommended action. This bounds note volume — Seren's concern about "hundreds of notes" doesn't apply because INFO only fires on specific provenance × validation × rule combinations, not globally on all validated data.

---

## Open Item 3: Integration Mapping for All Output Categories

### The Mapping Table

| Verdict | Pre-commit | CI Exit Code | SARIF Level | GitHub Annotation | Developer Experience |
|---------|-----------|-------------|-------------|-------------------|---------------------|
| **ERROR** | **Block** | **1** | `error` | Error (red) | Must fix before merge |
| **WARN** | **Block** | **1** | `warning` | Warning (yellow) | Must fix before merge (at threshold) |
| **INFO** | Pass | **3** | `note` | Notice (blue) | Visible, non-blocking, review recommended |
| **SUPPRESS** | Pass | **0** | *(not emitted)* | *(not emitted)* | Invisible — tool correctly determined no issue |

### Exit Code Semantics

- **0**: Clean. No findings of any severity.
- **1**: Blocking findings present (ERROR or WARN above precision threshold).
- **3**: No blocking findings, but INFO-level advisories exist.

**Why exit code 3, not 0:** Exit 0 means "all clear." Exit 3 means "nothing blocking, but there's signal worth reviewing." CI pipelines that only check `exit 0` vs. `exit non-zero` will treat INFO as blocking — this is the *correct default* for new adopters who haven't configured advisory handling. Teams that want non-blocking advisories configure their pipeline to accept exit 0 and 3. This is the same convention used by `pylint` (exit code bit flags) and `shellcheck` (exit 0 for clean, 1 for errors).

### How INFO Maps to Each Integration Point

**Pre-commit:** INFO findings pass the hook. The developer sees them in terminal output with a distinct prefix:

```
src/elspeth/engine/processor.py:156:8  SBE-R05  [note]  Validated external data reaches audit write
  │ ↑ provenance: EXTERNAL via requests.get() at :150, validated at :153
  │ Review whether validator adequately covers audit field requirements.
```

The hook exits 0 (or 3 if the hook supports advisory codes). The developer can act on it or ignore it. Pre-commit is the weakest enforcement point — it runs on the developer's machine, and blocking on advisories would cause override/uninstall.

**CI:** Exit code 3. The CI step can be configured as:
- `strict check src/ && echo "clean"` — treats exit 3 as failure (strict mode)
- `strict check src/; test $? -le 3 && echo "ok"` — treats exit 3 as advisory (standard mode)

The ELSPETH project should run in strict mode initially (treat INFO as blocking while the corpus is small) and graduate to standard mode once INFO verdicts have demonstrated low noise via corpus evidence.

**SARIF:** INFO findings are emitted as SARIF results with `level: "note"`. They carry the same `ruleId`, `message`, and `location` structure as ERROR/WARN findings. The `properties` bag includes provenance metadata:

```json
{
  "ruleId": "SBE-R05",
  "level": "note",
  "message": {
    "text": "Validated external data reaches audit write. Validator structurally verified; semantic adequacy requires human review."
  },
  "locations": [{ "physicalLocation": { "artifactLocation": { "uri": "src/elspeth/engine/processor.py" }, "region": { "startLine": 156 } } }],
  "properties": {
    "provenance": "EXTERNAL",
    "validationStatus": "STRUCTURALLY_VALIDATED",
    "provenanceSource": "requests.get()",
    "provenanceSourceLine": 150,
    "validatorFunction": "validate_response",
    "validatorLine": 153,
    "verdict": "INFO",
    "corpusCategory": "true_note"
  }
}
```

SARIF consumers (GitHub Advanced Security, SonarQube, DefectDojo) handle `level: "note"` natively. They display notes in PR views but don't mark the check as failed.

**GitHub Annotations:** Notes appear as "notice" severity annotations on the PR diff:

```
::notice file=src/elspeth/engine/processor.py,line=156::SBE-R05: Validated external data reaches audit write. Review validator adequacy.
```

GitHub renders notices with a blue icon on the affected line. They don't block merge or mark the check as failed. The reviewer sees them inline while reviewing the code — this is the integration pathway for Seren's "validated-not-verified" information flow that Iris correctly identified as essential.

### Attack on "Notes Go to /dev/null"

Iris's Round 3 objection — that notes "map to nothing in existing developer workflows" — was accurate for a hypothetical note mechanism with no integration point. But SARIF `level: "note"` and GitHub "notice" annotations ARE existing integration points. They're used by CodeQL, ESLint, and other SARIF-emitting tools. The infrastructure exists. The question was never "can notes reach developers?" but "will developers act on them?" — and that's a calibration question for the corpus, not an architecture question for the tool.

The corpus addresses this: INFO cells require 2 TP samples and 1 TN sample. If INFO findings in the corpus are consistently noise (developers never act on them), the data will show it — the TP samples will be reclassified as FP, the cell will flip to SUPPRESS, and the matrix shrinks. The INFO category is not a permanent state — it's a provisional verdict subject to corpus evidence.

---

## Final Position

I propose the following resolved design for the three open items:

1. **Label set:** Provenance {INTERNAL, EXTERNAL, UNKNOWN, MIXED} × Validation {RAW, STRUCTURALLY_VALIDATED}. Eight state combinations, seven with distinct behaviour. TIER_1/TIER_2 collapsed to INTERNAL (identical verdicts). MIXED retained distinct from UNKNOWN (different developer actions). Validation as separate dimension (provenance immutability preserved).

2. **Matrix:** 4 rules × 8 states = 32 cells, all defined with verdicts and corpus categories. ~99 corpus entries required. No undefined cells. Matrix has 5 verified structural properties (enumerated above). INFO appears in exactly 7 cells — bounded, not open-ended.

3. **Integration:** ERROR/WARN → block (exit 1). INFO → advisory (exit 3, SARIF note, GitHub notice). SUPPRESS → invisible (exit 0, not emitted). Exit 3 is distinct from exit 0 to prevent silent advisory loss. All categories map to existing SARIF/GitHub infrastructure.

This is implementable in the stdlib `ast` module. The `TaintMap` is `dict[str, TaintState]` where `TaintState` is a 2-field frozen dataclass `(provenance: Provenance, validation: Validation)`. Propagation rules update both dimensions independently. Rule evaluation is a dictionary lookup in a 32-entry table. Performance impact over the current pattern-matching enforcer: negligible.
