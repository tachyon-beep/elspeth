# Round 3 — Steelman Synthesis: Quinn (Quality Engineer)

## Steelman: Seren's Taint Attenuation Model

Seren's argument is the most structurally sophisticated in the roundtable. The claim is not merely that binary taint is imprecise — it's that binary taint creates a **system dynamics pathology** where the tool's success at structural verification displaces the human review that was providing the actual safety guarantee. The compliance ritual loop is concrete and well-specified: tool requires structural control flow → validators are written to minimum structure → taint cleansed → tool reports GREEN → team concludes boundaries are enforced → actual validation quality degrades → no selective pressure to improve validators.

The strongest part of Seren's position is the comparison to the status quo. The current `enforce_tier_model.py` flags *every* `.get()` — noisy, but never produces false confidence about validation adequacy. Pyre's binary cleansing makes a stronger claim ("this data is clean") that can be wrong. Seren argues that trading false positives for false confidence is a net negative in a system where false confidence is the primary threat (the discussion paper's §4.2 thesis). This is genuinely persuasive — false positives waste developer time, but false confidence enables the exact category of silent data corruption that ELSPETH's audit model is designed to prevent.

The three-state model (tainted → validated-not-verified → clean) is elegant because it makes the tool's epistemic limits visible in its output. The tool says "I saw structural validation, but I can't vouch for semantic adequacy — human, please evaluate." This is more honest than binary cleansing, and the note emission ("external data from X reaches audit write at Y via validator Z") converts an invisible pass into a visible information flow.

## Concession

Seren is right about the system dynamics. Binary cleansing will create a compliance ritual. The evidence is already visible in ELSPETH's own codebase: the existing enforcer's allowlist has entries where the "reason" field reads like post-hoc rationalization rather than genuine safety analysis. When tools demand structured justification, people generate structured justification — the form fills but the thinking doesn't happen. A taint engine that says "clean" when it means "structurally present" will accelerate this dynamic.

Seren is also right that validator concentration is a real risk. A single `validate_response()` that cleanses 15 data flows is a single point of failure for trust boundary integrity. Surfacing this as a metric is genuinely high-leverage.

## Attack on the Testing Implications

Where Seren's model breaks down is in **verifiability of the tool itself**. The three-state model introduces a middle state — "validated-not-verified" — that emits *notes* rather than *findings*. From a testing and measurement perspective, this creates three problems:

**Problem 1: Notes have no precision metric.** Findings are classified as TP/FP through developer response (fix code = TP, add allowlist = FP candidate). Notes are informational — there's no action to observe. How do we know if a note is *useful*? How do we know if the validator concentration metric is *actionable*? Seren's model optimises for epistemic honesty at the cost of measurability. A tool whose primary output can't be measured can't be improved.

**Problem 2: The golden corpus can't test note quality.** My corpus design has crisp verdicts: `true_positive` (tool should fire), `true_negative` (tool should not fire). What's the corpus verdict for a note? `true_note`? The corpus would need a third verdict category — "tool should emit a note here" — with its own adequacy criteria. How many notes per rule? What constitutes a correct note vs. a noisy note? The corpus design becomes substantially more complex without a clear improvement in detection capability.

**Problem 3: "Validated-not-verified" is an absorbing state in practice.** Once a validator exists and is decorated, every data flow through it enters the middle state forever. There's no mechanism for a data flow to graduate from "validated-not-verified" to "clean" — that would require the tool to verify semantic adequacy, which Seren correctly says is undecidable. So the middle state accumulates. After a year, the tool emits hundreds of notes saying "human please review validator adequacy." Note fatigue replaces finding fatigue — the same system dynamic Seren warned about, shifted to a different output channel.

## Synthesis: Provenance Labels with Testable Severity Grades

Neither binary taint (Pyre) nor three-state attenuation (Seren) nor five-label provenance (Riven) solves the testing problem alone. My synthesis takes Riven's provenance labels as the taint model (because provenance is testable — every variable gets a concrete label the corpus can assert on), Seren's insight that validator passage should not produce "clean" status (because the compliance ritual is real), and adds **a severity grading system that maps provenance × pattern to testable finding categories**.

### The Taint Model: Three Provenance Labels (Not Five)

Riven proposes TIER_1, TIER_2, TIER_3, UNKNOWN, MIXED. I argue MIXED is a testing problem — it's a garbage-can state that will accumulate without clear corpus verdicts. And UNKNOWN is operationally indistinct from "flag it." Collapse to three actionable labels plus one fallback:

| Label | Meaning | Assignment |
|-------|---------|-----------|
| `EXTERNAL` | Data from outside the system (Tier 3) | `@external_boundary` returns, heuristic list matches |
| `INTERNAL` | Data from our own code/database (Tier 1/2) | `@internal_data` annotation, landscape/recorder calls |
| `VALIDATED` | External data that passed through `@validates_external` | Validator return values |
| `UNKNOWN` | Provenance not determinable | Everything else (the default) |

**Why three, not five:** The Tier 1/Tier 2 distinction is not AST-observable. Both are "our data" — the difference is whether it's the audit trail or pipeline data, and that's a semantic distinction the AST can't make. Collapsing them to `INTERNAL` is honest about the tool's resolution limit. The corpus can test every label because each has a clear, concrete definition.

**Why VALIDATED, not "clean":** This is Seren's key insight preserved. Data that passes through a validator gets a distinct label — not collapsed into INTERNAL. The provenance is "external, structurally validated." This is a factual statement the tool can verify, not a safety claim it can't.

### Severity Grading: Provenance × Pattern → Testable Outcome

Instead of Seren's notes (unmeasurable) or Pyre's suppress/flag binary (too coarse), map each provenance × pattern combination to a **severity grade with a defined corpus verdict**:

| Provenance | `.get()` with default | Broad `except` | `hasattr()` | Reaching audit write |
|-----------|----------------------|---------------|-------------|---------------------|
| `EXTERNAL` | SUPPRESS (legitimate coercion) | SUPPRESS (boundary handling) | FLAG (banned unconditionally) | ERROR (Tier 3 → Tier 1 without validation) |
| `VALIDATED` | SUPPRESS | INFO (note: review validator adequacy) | FLAG | WARN (validated, review adequacy) |
| `INTERNAL` | ERROR (fabricating defaults on our data) | ERROR (destroying audit trail) | FLAG | SUPPRESS (our data, expected) |
| `UNKNOWN` | WARN (possibly legitimate) | WARN | FLAG | WARN (provenance unclear) |

The severity grades (ERROR, WARN, INFO, SUPPRESS) are each testable:

- **ERROR**: Corpus verdict `true_positive`. Must fire. Blocking.
- **WARN**: Corpus verdict `true_positive_reduced`. Fires at reduced confidence. Blocking at threshold.
- **INFO**: Corpus verdict `true_note`. Emitted but not blocking. Measurable via "did human act on it?" tracking.
- **SUPPRESS**: Corpus verdict `true_negative`. Must not fire.

This gives the corpus a **4-category verdict system** instead of binary TP/TN, but each category has a clear operational definition and a measurable outcome. The INFO category is Seren's "validated-not-verified" note — but it's scoped to specific provenance × pattern combinations rather than applied globally to all validated data. This bounds the note volume.

### Corpus Implications

The matrix has 4 provenances × N patterns. For 7 rules, that's 28 cells. Not every cell needs the full 18 samples — many are straightforward (e.g., `hasattr()` is always FLAG regardless of provenance). My proposal:

- **ERROR cells:** 5 TP samples each (these are blocking — need highest confidence)
- **SUPPRESS cells:** 3 TN samples each (confirm no false positives)
- **WARN cells:** 3 TP + 2 TN samples each (borderline cases need both)
- **INFO cells:** 2 samples each (non-blocking, lower bar)

This yields roughly 100-140 corpus entries — close to my original 126 estimate, but now structured by the provenance × pattern matrix rather than flat per-rule. The matrix structure is self-documenting: an empty cell in the matrix means "we haven't decided what this combination means," which is a design gap, not a testing gap.

### Where This Addresses Riven's Container Contamination

Riven's key example: a dict containing both external and internal data gets conservative taint → all `.get()` calls suppressed, including on audit paths. With provenance labels, the container gets `UNKNOWN` provenance (mixed sources, can't determine), and `.get()` on UNKNOWN is WARN — not suppressed, not an error. The human reviews it. This is strictly better than binary taint's SUPPRESS and more actionable than Seren's perpetual note emission.

### Self-Hosting Implication

The tool's own code uses `ast.parse()` (external boundary — `EXTERNAL` provenance), `yaml.safe_load()` (external boundary), and accesses its own dataclass fields (INTERNAL). The provenance × pattern matrix tells us exactly what the tool should do for its own code, and the corpus can include the tool's own patterns as test cases. This makes self-hosting concrete and testable.
