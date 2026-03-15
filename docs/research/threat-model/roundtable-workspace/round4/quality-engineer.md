# Round 4 — Final Convergence: Quinn (Quality Engineer)

## 1. Exact Label Set

### Concession: TIER_1/TIER_2 Distinction via Decorators

The scribe is right. My Round 3 objection was "Tier 1/Tier 2 is not AST-observable," but the scribe correctly identified that the tool already requires `@external_boundary` and `@validates_external` decorators — adding `@tier1_data` and `@tier2_data` (or a single `@internal_data(tier=1)`) is architecturally consistent. The AST can observe decorators. I was conflating "not inferrable from syntax" with "not observable" — decorators make it observable by declaration, the same mechanism we use for everything else.

**Concession accepted.** Split INTERNAL into TIER_1 and TIER_2.

**Corpus impact:** The matrix grows from 4×7=28 cells to 6×7=42 cells. At the sample rates I proposed (5 for ERROR, 3 for TN, 3+2 for WARN, 2 for INFO), this adds roughly 40-60 corpus entries, bringing the total to ~140-200. This is manageable — the new cells are not independent concepts, they're severity refinements of the same pattern. Many TIER_1/TIER_2 cells will have identical verdicts (e.g., `hasattr()` is ERROR on both), so the incremental authoring cost is lower than the cell count suggests.

**Where the split matters for severity:**

| Pattern | TIER_1 (Audit Trail) | TIER_2 (Pipeline Data) |
|---------|---------------------|----------------------|
| `.get()` with default | ERROR — fabricating audit data | ERROR — upstream contract violation |
| Broad `except` without re-raise | ERROR — destroying evidence | WARN — hiding upstream bug |
| Data reaching audit write | SUPPRESS — expected path | WARN — pipeline data reaching audit without explicit recording |
| `isinstance()` type guard | ERROR — implies distrust of our schema | WARN — may be legitimate dispatch |

The severity differences are meaningful: `.get()` is ERROR on both but for different reasons (the SARIF message changes), while broad `except` and `isinstance()` genuinely differ in severity between tiers. This justifies the split.

### Concession: MIXED as Distinct from UNKNOWN

The scribe's argument is correct: UNKNOWN means "we failed to determine provenance" while MIXED means "we successfully determined that the container holds heterogeneous-provenance data." These are different epistemic states requiring different developer actions:

- **UNKNOWN** → "Annotate this code so the tool can determine provenance" (action: add decorator)
- **MIXED** → "Refactor this container to separate data by provenance, or document why mixing is safe" (action: restructure or justify)

I withdraw my objection that MIXED is a garbage-can state. It has clear corpus verdicts (defined below in the matrix) and triggers a distinct developer action.

**Corpus verdicts for MIXED:**

| Pattern on MIXED data | Severity | Corpus verdict | Rationale |
|----------------------|----------|---------------|-----------|
| `.get()` with default | WARN | `true_positive_reduced` | Conservative — might be legitimate coercion on the external component, might be fabrication on the internal component. Flag for human review. |
| `getattr()` with default | WARN | `true_positive_reduced` | Same rationale as `.get()`. |
| `hasattr()` | ERROR | `true_positive` | Banned unconditionally — provenance doesn't change this. |
| Broad `except` without re-raise | WARN | `true_positive_reduced` | Mixed container in a try block — might be boundary handling, might be evidence destruction. |
| Data reaching audit write | ERROR | `true_positive` | Mixed-provenance data reaching Tier 1 means unvalidated external data may be entering the audit trail. Conservative: treat as violation. |
| `isinstance()` type guard | WARN | `true_positive_reduced` | On mixed data, `isinstance()` might be legitimate dispatch to handle the different-provenance components. |
| Defensive `try/except` on internal data | WARN | `true_positive_reduced` | "Internal data" in a MIXED container is uncertain — flag for review. |

The key distinction from UNKNOWN: MIXED findings carry higher confidence than UNKNOWN because we *know* there's a provenance boundary in the container. UNKNOWN findings carry lower confidence because the tool may simply be missing context.

### Final Label Set (Advocated)

**Provenance (6 labels):**

| Label | Meaning | Assignment Mechanism |
|-------|---------|---------------------|
| `TIER_1` | Audit trail / Landscape data | `@tier1_data` decorator, landscape/recorder API calls |
| `TIER_2` | Pipeline data (post-source) | `@tier2_data` decorator, transform context data |
| `TIER_3` | External data (zero trust) | `@external_boundary` returns, heuristic list matches |
| `VALIDATED` | External data that passed structural validation | `@validates_external` return values |
| `MIXED` | Container with values from multiple provenance tiers | Taint engine: assignment from multiple differently-labelled sources |
| `UNKNOWN` | Provenance not determinable | Default for unannotated code |

**Validation status:** I now concede this should be a separate dimension, not embedded in provenance. However, for v0.1 I propose collapsing it: `VALIDATED` as a provenance label is operationally equivalent to `TIER_3 × STRUCTURALLY_VALIDATED` in the 2D model. The 2D model is cleaner in principle, but for v0.1 with intra-function analysis only, the distinction between "TIER_3 validated" and "TIER_2 validated" doesn't arise — validation only applies to external data entering the system. If v1.0 introduces inter-procedural analysis and internal data can be "re-validated," then splitting into two dimensions is the correct refactoring.

**Pragmatic position:** I'll work with the 6-label provenance model for the matrix below. If the roundtable converges on a full 2D model (provenance × validation), the matrix structure is the same — just expand VALIDATED into its component cells.

## 2. Complete Matrix with Corpus Verdicts

### Rules

| ID | Pattern | Detection |
|----|---------|-----------|
| R1 | `.get()` with default value | `ast.Call` on `.get` with ≥2 args |
| R2 | `getattr()` with default | `ast.Call` on `getattr` with 3 args |
| R3 | `hasattr()` | `ast.Call` on `hasattr` — banned unconditionally |
| R4 | Broad `except` without re-raise | `except Exception` / bare `except` with no `raise` in body |
| R5 | Data reaches audit write path | Tainted variable flows to landscape/recorder API call |
| R6 | `isinstance()` as type guard | `ast.Call` on `isinstance` used as conditional guard |
| R7 | Defensive `try/except` on internal data | `try/except` wrapping access to `TIER_1` or `TIER_2` attributed data |

### The Matrix

#### R1: `.get()` with default value

| Provenance | Severity | Corpus Verdict | Sample Count | Rationale |
|-----------|----------|---------------|-------------|-----------|
| TIER_1 | ERROR | `true_positive` | 5 TP | Fabricating defaults on audit data — evidence tampering |
| TIER_2 | ERROR | `true_positive` | 5 TP | Upstream contract violation — fix the source, don't mask |
| TIER_3 | SUPPRESS | `true_negative` | 3 TN | Legitimate boundary coercion |
| VALIDATED | SUPPRESS | `true_negative` | 3 TN | Already validated; `.get()` with default is safe normalization |
| MIXED | WARN | `true_positive_reduced` | 3 TP + 2 TN | May be coercion on external part or fabrication on internal part |
| UNKNOWN | WARN | `true_positive_reduced` | 3 TP + 2 TN | Possibly legitimate, but provenance unclear — annotate |

#### R2: `getattr()` with default

| Provenance | Severity | Corpus Verdict | Sample Count | Rationale |
|-----------|----------|---------------|-------------|-----------|
| TIER_1 | ERROR | `true_positive` | 5 TP | Hiding missing attributes on audit objects = corruption |
| TIER_2 | ERROR | `true_positive` | 5 TP | Missing attribute on pipeline data = upstream bug |
| TIER_3 | SUPPRESS | `true_negative` | 3 TN | External objects may lack expected attributes — defensive access OK |
| VALIDATED | WARN | `true_positive_reduced` | 3 TP + 2 TN | Post-validation, attributes should be known — why are you guessing? |
| MIXED | WARN | `true_positive_reduced` | 3 TP + 2 TN | Same ambiguity as R1 |
| UNKNOWN | WARN | `true_positive_reduced` | 3 TP + 2 TN | Annotate to resolve |

#### R3: `hasattr()` — banned unconditionally

| Provenance | Severity | Corpus Verdict | Sample Count | Rationale |
|-----------|----------|---------------|-------------|-----------|
| TIER_1 | ERROR | `true_positive` | 5 TP | Banned — swallows @property exceptions |
| TIER_2 | ERROR | `true_positive` | 5 TP | Banned |
| TIER_3 | ERROR | `true_positive` | 5 TP | Banned — use try/except AttributeError or isinstance |
| VALIDATED | ERROR | `true_positive` | 5 TP | Banned |
| MIXED | ERROR | `true_positive` | 5 TP | Banned |
| UNKNOWN | ERROR | `true_positive` | 5 TP | Banned |

**Note:** `hasattr()` is the simplest rule — provenance-independent, always ERROR. This makes it an excellent corpus calibration rule. If precision on R3 drops below 99%, something is structurally wrong with the engine.

#### R4: Broad `except` without re-raise

| Provenance | Severity | Corpus Verdict | Sample Count | Rationale |
|-----------|----------|---------------|-------------|-----------|
| TIER_1 | ERROR | `true_positive` | 5 TP | Destroying audit evidence — the primary threat |
| TIER_2 | WARN | `true_positive_reduced` | 3 TP + 2 TN | Hiding upstream bugs, but less catastrophic than Tier 1 |
| TIER_3 | SUPPRESS | `true_negative` | 3 TN | Boundary handling — external calls are expected to fail |
| VALIDATED | INFO | `true_note` | 2 | Post-validation broad except is suspicious — review validator adequacy |
| MIXED | WARN | `true_positive_reduced` | 3 TP + 2 TN | Might be boundary handling, might be evidence destruction |
| UNKNOWN | WARN | `true_positive_reduced` | 3 TP + 2 TN | Annotate to resolve |

#### R5: Data reaches audit write path

| Provenance | Severity | Corpus Verdict | Sample Count | Rationale |
|-----------|----------|---------------|-------------|-----------|
| TIER_1 | SUPPRESS | `true_negative` | 3 TN | Our data reaching our database — expected |
| TIER_2 | INFO | `true_note` | 2 | Pipeline data reaching audit — normal but worth noting for lineage |
| TIER_3 | ERROR | `true_positive` | 5 TP | Unvalidated external data in audit trail — trust boundary violation |
| VALIDATED | INFO | `true_note` | 2 | Validated data reaching audit — normal path, note for traceability |
| MIXED | ERROR | `true_positive` | 5 TP | Mixed-provenance data reaching audit — may contain unvalidated external |
| UNKNOWN | WARN | `true_positive_reduced` | 3 TP + 2 TN | Unknown provenance reaching audit — annotate to prove safety |

#### R6: `isinstance()` as type guard

| Provenance | Severity | Corpus Verdict | Sample Count | Rationale |
|-----------|----------|---------------|-------------|-----------|
| TIER_1 | ERROR | `true_positive` | 5 TP | Implies distrust of our own schema — we defined these types |
| TIER_2 | WARN | `true_positive_reduced` | 3 TP + 2 TN | May be legitimate polymorphic dispatch on pipeline data |
| TIER_3 | SUPPRESS | `true_negative` | 3 TN | Type-checking external data is expected validation |
| VALIDATED | SUPPRESS | `true_negative` | 3 TN | Post-validation isinstance for dispatch is fine |
| MIXED | WARN | `true_positive_reduced` | 3 TP + 2 TN | Might be dispatch, might be distrust — review |
| UNKNOWN | WARN | `true_positive_reduced` | 3 TP + 2 TN | Annotate to resolve |

#### R7: Defensive `try/except` on internal data

| Provenance | Severity | Corpus Verdict | Sample Count | Rationale |
|-----------|----------|---------------|-------------|-----------|
| TIER_1 | ERROR | `true_positive` | 5 TP | Wrapping audit reads prevents crash-on-corruption |
| TIER_2 | WARN | `true_positive_reduced` | 3 TP + 2 TN | Wrapping pipeline data ops — may be operation safety (div by zero) |
| TIER_3 | SUPPRESS | `true_negative` | 3 TN | External calls expected to fail — wrapping is required |
| VALIDATED | SUPPRESS | `true_negative` | 3 TN | Validated but operations on values can still fail — wrapping OK |
| MIXED | WARN | `true_positive_reduced` | 3 TP + 2 TN | Uncertain whether the try protects internal or external component |
| UNKNOWN | WARN | `true_positive_reduced` | 3 TP + 2 TN | Annotate to resolve |

### Summary Statistics

| Severity | Cell Count | Sample Formula | Total Samples |
|----------|-----------|---------------|---------------|
| ERROR | 14 | 5 TP each | 70 |
| WARN | 16 | 3 TP + 2 TN each | 80 |
| INFO | 3 | 2 each | 6 |
| SUPPRESS | 9 | 3 TN each | 27 |
| **Total** | **42** | | **183** |

**Corpus size: 183 entries.** This is larger than my Round 3 estimate of 100-140 because:
1. The label set grew from 4 to 6 (TIER_1/TIER_2 split + MIXED added)
2. The 42-cell matrix has more ERROR cells than expected (the TIER_1/TIER_2 split creates meaningful severity differences)

183 is manageable. The entries are structured by the matrix — authoring follows the grid, not a flat list. Each entry is a short code snippet (5-15 lines) with a provenance annotation and an expected verdict. I estimate 2-3 hours of authoring time for the initial corpus, with the R3 (`hasattr`) row taking the least time (all identical: ERROR) and the R5 (audit write) column taking the most (requires realistic audit path code).

### Edge Cases the Matrix Does Not Cover

Three patterns fall outside the 7 rules above but are worth noting for future rule additions:

1. **`json.loads()` on checkpoint data** — This is Tier 1 data (we wrote the checkpoint), so wrapping the parse in try/except is R7 with TIER_1 provenance → ERROR. The matrix handles this correctly.

2. **`yaml.safe_load()` on pipeline config** — Config is Tier 2 (user-provided, validated at load time). If the load is wrapped defensively, R7 with TIER_2 → WARN. Correct.

3. **`dict()` constructor on external API response** — This is R5-adjacent (data provenance assignment) but not a defensive pattern per se. The taint engine handles this through propagation, not through a rule firing.

## 3. Integration Mapping

### Complete Severity-to-Integration Mapping

| Severity | Pre-commit | CI exit code | SARIF level | GitHub annotation | Corpus verdict |
|----------|-----------|-------------|-------------|-------------------|----------------|
| ERROR | **Block** | `1` (failure) | `error` | Error (red) | `true_positive` |
| WARN | **Block** | `1` (failure) | `warning` | Warning (yellow) | `true_positive_reduced` |
| INFO | **Pass** | `0` (success) | `note` | Notice (blue) | `true_note` |
| SUPPRESS | — (no output) | — | — | — | `true_negative` |

### Does INFO Block Anything?

**No.** INFO findings never block pre-commit or CI. This is deliberate: INFO captures the "validated-not-verified" middle ground that Seren correctly identified as important but that cannot be mechanically adjudicated. An INFO finding says "the tool sees a structural pattern that may warrant human review" — it does not say "this code is wrong."

### How Do We Measure Whether INFO Findings Are Useful?

This is the question I raised as Problem 1 against Seren's notes. I owe a concrete answer for my own INFO category. Here is how INFO avoids being unmeasurable:

**Measurement 1: Action rate.** INFO findings appear as GitHub "Notice" annotations and in SARIF output. We can measure what percentage of INFO findings result in a code change within the same PR or in the subsequent 3 commits. An INFO finding that never triggers action is noise; an INFO finding that triggers action at >10% rate is providing signal.

**Measurement 2: Graduation rate.** INFO findings exist because the tool lacks confidence for WARN. If a specific provenance × pattern cell consistently shows action rates above 30%, that cell should be promoted to WARN in the matrix. The INFO→WARN graduation mechanism means INFO is not a permanent category — it's a probationary holding pen for patterns that haven't yet earned blocking status.

**Measurement 3: Suppression request rate.** If developers consistently add allowlist entries to suppress specific INFO findings, those findings are noise and the cell should be reclassified to SUPPRESS. This is the inverse of graduation.

**How this differs from Seren's notes (my Problem 1):** Seren's notes are emitted globally for all validated data flows — every `@validates_external` produces perpetual notes. My INFO findings are emitted only for 3 specific cells in the 42-cell matrix:

1. R4 (broad except) × VALIDATED — "Post-validation broad except is suspicious"
2. R5 (audit write) × TIER_2 — "Pipeline data reaching audit write"
3. R5 (audit write) × VALIDATED — "Validated data reaching audit write"

Three cells, not a blanket emission. The volume is bounded by the matrix, not by the number of validators in the codebase. This directly addresses my Problem 3 (absorbing state / note fatigue).

**The measurability test:** If after 6 months of production use, all 3 INFO cells show <5% action rate, they should all be reclassified to SUPPRESS. If the tool can't demonstrate that INFO findings change developer behaviour, the findings are noise and should be eliminated. This gives INFO a concrete survival criterion that Seren's notes lacked.

### Pre-commit Performance Note

Pre-commit blocks on ERROR and WARN only. Since R3 (`hasattr`) is ERROR across all provenances, it serves as a fast-path: `hasattr()` detection requires no taint analysis, just an AST pattern match. The pre-commit hook can run R3 first as a sanity check (sub-100ms), then run the full taint analysis for remaining rules. This means the pre-commit hook's worst case is the taint engine's full analysis time; the best case (no `hasattr()`, no taint-dependent violations) is a fast pass.

### SARIF Integration Details

Each finding includes provenance metadata in the SARIF `properties` bag (Iris's Round 3 proposal, which I endorse):

```json
{
  "ruleId": "R1",
  "level": "error",
  "message": {
    "text": "`.get()` with default on TIER_1 data fabricates audit values — use direct key access and crash on corruption"
  },
  "properties": {
    "provenance": "TIER_1",
    "trustTier": 1,
    "provenanceSource": "landscape.get_row_state",
    "provenanceSourceLine": 42,
    "corpusVerdict": "true_positive"
  }
}
```

The `corpusVerdict` field in SARIF output is a debugging aid — it tells the developer (and the corpus maintenance pipeline) which verdict category this finding belongs to. This closes the loop between production findings and corpus evolution: if a finding tagged `true_positive` is consistently allowlisted, the corpus is wrong and needs updating.

## Summary of Concessions and Final Positions

| Item | Round 3 Position | Round 4 Position | Change |
|------|-----------------|-----------------|--------|
| TIER_1/TIER_2 split | Collapsed to INTERNAL | Split via decorators | **CONCESSION** — scribe's decorator argument is sound |
| MIXED label | "Garbage-can state" | Distinct from UNKNOWN with clear verdicts | **CONCESSION** — MIXED and UNKNOWN trigger different actions |
| Label count | 4 (EXTERNAL, INTERNAL, VALIDATED, UNKNOWN) | 6 (TIER_1, TIER_2, TIER_3, VALIDATED, MIXED, UNKNOWN) | Extension from concessions |
| Provenance × validation dimensionality | Embedded (VALIDATED as provenance) | Embedded for v0.1, separate for v1.0 | **HELD** — pragmatic for intra-function scope |
| Severity grades | 4 (ERROR, WARN, INFO, SUPPRESS) | Same 4 | **HELD** |
| Corpus verdicts | 4 categories | Same 4 categories | **HELD** |
| Matrix size | 28 cells (~100-140 samples) | 42 cells (183 samples) | Growth from label set expansion |
| INFO measurability | "Notes are unmeasurable" (attack on Seren) | INFO is measurable via action rate, graduation rate, suppression rate | **REFINED** — addressed my own criticism |
