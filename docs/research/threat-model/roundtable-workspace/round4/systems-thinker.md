# Round 4 — Focused Dissent: Seren (Systems Thinker)

## 1. Exact Label Set — Does MIXED Accumulate?

### The Monotonic Growth Hypothesis

The question asks whether MIXED-provenance variables grow monotonically as codebases mature. The short answer is yes — *without counterpressure*. The longer answer is that the counterpressure is designable, and the label set determines whether it exists.

The accumulation mechanism is straightforward. Functions that combine data from multiple sources produce MIXED containers. As codebases grow, more functions aggregate: a response object picks up audit metadata; a logging context combines user input with system state; a pipeline row accumulates fields from source, transform, and external call. Each aggregation site is a MIXED-provenance variable. The number of aggregation sites grows monotonically with codebase size because code is added more often than removed.

But accumulation is only half the dynamic. The other half is **resolution pressure** — do developers have a reason and a mechanism to resolve MIXED into its constituent tiers? This is where label set design becomes a leverage point.

### Why MIXED Must Be Explicit (Not Collapsed to UNKNOWN)

Quinn proposes collapsing MIXED into UNKNOWN. This is the single most dangerous simplification on the table, because it eliminates the resolution pressure that keeps MIXED bounded.

The feedback loop with explicit MIXED:

```
Container mixes tiers → Tool labels it MIXED → Finding emitted
  → Developer destructures container → Separate variables, separate tiers
  → MIXED population decreases → Findings decrease
```

The feedback loop with MIXED collapsed to UNKNOWN:

```
Container mixes tiers → Tool labels it UNKNOWN → Same finding as "can't tell"
  → Developer can't distinguish "mixed tiers" from "untracked variable"
  → No specific guidance (destructure vs. add declaration)
  → Developer adds broad allowlist entry or ignores → UNKNOWN population grows
  → Tool value erodes on all UNKNOWN findings (noise)
```

The critical difference: MIXED is *actionable* ("separate your tiers"), UNKNOWN is *ambiguous* ("I don't know — maybe add a declaration?"). Distinct labels produce distinct developer actions. Collapsing them produces a garbage-can category where two different root causes receive the same diagnosis, and neither gets the right treatment.

**The accumulation dynamic I warned about in Round 1 — too many findings → noise → erosion — applies to UNKNOWN far more aggressively than to MIXED**, precisely because UNKNOWN has no specific resolution mechanism. MIXED says "you combined things you shouldn't have"; UNKNOWN says "I can't help you." One drives improvement; the other drives allowlisting.

### Does MIXED Become the Dominant Label?

Not if the tool provides actionable resolution guidance. The system dynamics depend on the ratio of MIXED-creation rate to MIXED-resolution rate:

| Factor | Increases MIXED | Decreases MIXED |
|--------|----------------|-----------------|
| Codebase growth | More aggregation sites | — |
| Dict-heavy patterns | More containers | — |
| Tool guidance on findings | — | Developers destructure |
| Code review habits | — | Reviewers flag mixed containers |
| Agent instructions | — | Agents avoid mixing tiers |

If MIXED findings include the message "Container mixes TIER_1 (from `recorder.get()` at :38) and TIER_3 (from `api_response` at :35). Separate access paths to enable per-tier enforcement" — and this message appears in PR annotations — the resolution rate stays proportional to the creation rate. MIXED doesn't dominate because developers learn to avoid creating it.

The critical design requirement: **every MIXED finding must name the constituent tiers and their source lines.** A finding that says only "MIXED provenance" is useless; a finding that says "MIXED: TIER_1 from line 38 + TIER_3 from line 35" is a refactoring instruction.

### The Label Set I Advocate

Five provenance labels, two validation states:

**Provenance (immutable — where data came from):**

| Label | Meaning | Assignment Mechanism |
|-------|---------|---------------------|
| `TIER_1` | Audit data — our database, our checkpoints | `@internal_audit` decorator or manifest entry |
| `TIER_2` | Pipeline data — row fields, config, plugin state | `@internal_pipeline` decorator or manifest entry |
| `TIER_3` | External data — API responses, user input, file reads | `@external_boundary` decorator or heuristic list |
| `UNKNOWN` | Provenance not determinable | Default for untracked variables |
| `MIXED` | Container holding data from multiple tiers | Computed: container with values from 2+ distinct provenance labels |

**Validation status (mutable — what processing it received):**

| Status | Meaning | Transition |
|--------|---------|------------|
| `RAW` | No validation observed | Default state |
| `STRUCTURALLY_VALIDATED` | Passed through `@validates_external` with rejection path | Validator return value |

This gives a 5 × 2 = 10 state matrix. VERIFIED is deferred to v1.0 per Pyre's proposal.

**Why TIER_1 and TIER_2 must be distinct:** Quinn correctly observes the AST cannot distinguish them by inspection. But the same is true of TIER_3 — we use decorators and heuristic lists, not AST magic. The TIER_1/TIER_2 distinction uses the same mechanism (decorators or manifest entries) and produces meaningfully different rule outcomes: `.get()` on TIER_1 is catastrophic (audit corruption), `.get()` on TIER_2 is a bug (contract violation). These have different developer actions, different SARIF severities, and different messages. Collapsing them to INTERNAL loses the severity distinction that makes findings actionable.

**Quinn's testability objection is answered by the declaration mechanism, not by collapsing labels.** The corpus tests whether the tool correctly evaluates rules against each label. Whether the label was correctly *assigned* is a separate concern — and it's the same concern for TIER_3 (heuristic accuracy) as for TIER_1/TIER_2 (declaration accuracy). If we trust heuristics for TIER_3 assignment, we can trust declarations for TIER_1/TIER_2 assignment.

### MIXED + Validation Status

A MIXED container's validation status is the *minimum* of its constituents:

| Constituent statuses | Container status | Rationale |
|---------------------|-----------------|-----------|
| All RAW | RAW | Nothing validated |
| All STRUCTURALLY_VALIDATED | STRUCTURALLY_VALIDATED | All paths validated |
| Mix of RAW and VALIDATED | RAW | Conservative — weakest link |

This prevents a validated external response from "laundering" the validation status of an unvalidated component in the same container.

## 2. Complete Matrix with Corpus Verdicts

### Reconciling Notes with Testability

Quinn identified three problems with my "notes" proposal. I accept two and reject one.

**Problem 1 (no precision metric):** Accepted in part. Quinn is right that notes-as-informational-output have no natural precision metric — there's no developer action to observe. But this problem dissolves when notes are reframed as **INFO-severity findings** rather than a separate output category. An INFO finding has a corpus verdict (`true_note`): the corpus asserts "for this provenance × validation × rule combination, the tool should emit at INFO severity, not ERROR, not WARN, not SUPPRESS." The precision question becomes: "did the tool emit the correct severity?" — which is testable.

**Problem 2 (corpus can't test note quality):** Rejected. This applies a standard to INFO that it doesn't apply to ERROR. The corpus doesn't test whether an ERROR finding's *message text* is helpful — it tests whether the finding *fires at the right severity*. The same standard applies to INFO: the corpus tests that the tool emits INFO (not ERROR, not SUPPRESS) for the specified code pattern. Whether the INFO message is well-written is a UX concern, not a corpus concern.

**Problem 3 (absorbing state):** Accepted as a real dynamic, rejected as fatal. Yes, STRUCTURALLY_VALIDATED is absorbing in v0.1 — nothing graduates to VERIFIED. But this doesn't produce the note fatigue Quinn predicts, because INFO findings are **bounded by the number of TIER_3 + STRUCTURALLY_VALIDATED data flows that reach audit write paths.** This is a small number in any well-structured codebase — the trust model *wants* few external-to-audit flows, and each one is architecturally significant. If a codebase has 200 such flows, the problem isn't note fatigue — it's architecture.

The absorbing-state concern is further mitigated by the validator concentration metric (Layer 3). If one validator covers 15 flows, the developer sees one metric ("validator concentration: 15") rather than 15 individual INFO findings. The Layer 3 diagnostic collapses the redundancy that Quinn fears.

### The Complete Matrix

Every cell specifies: severity, corpus verdict, and whether the finding blocks CI.

**Rule R1: `.get()` with default on typed field**

| Provenance | RAW | STRUCTURALLY_VALIDATED |
|-----------|-----|----------------------|
| TIER_1 | ERROR / `true_positive` / blocks | ERROR / `true_positive` / blocks |
| TIER_2 | ERROR / `true_positive` / blocks | ERROR / `true_positive` / blocks |
| TIER_3 | SUPPRESS / `true_negative` | SUPPRESS / `true_negative` |
| UNKNOWN | WARN / `true_positive_reduced` / blocks | INFO / `true_note` / advisory |
| MIXED | WARN / `true_positive_reduced` / blocks | WARN / `true_positive_reduced` / blocks |

Rationale: `.get()` on TIER_1/TIER_2 is always wrong regardless of validation — these are our typed data, never external. TIER_3 is always correct — `.get()` with default is the right pattern for untrusted data. UNKNOWN gets WARN (we can't tell, flag it). MIXED gets WARN even when validated because the container holds TIER_1/TIER_2 components where `.get()` is dangerous, and validation of the TIER_3 component doesn't make `.get()` safe on the TIER_1 component.

**Rule R3: `hasattr()` (unconditionally banned)**

| Provenance | RAW | STRUCTURALLY_VALIDATED |
|-----------|-----|----------------------|
| TIER_1 | ERROR / `true_positive` / blocks | ERROR / `true_positive` / blocks |
| TIER_2 | ERROR / `true_positive` / blocks | ERROR / `true_positive` / blocks |
| TIER_3 | ERROR / `true_positive` / blocks | ERROR / `true_positive` / blocks |
| UNKNOWN | ERROR / `true_positive` / blocks | ERROR / `true_positive` / blocks |
| MIXED | ERROR / `true_positive` / blocks | ERROR / `true_positive` / blocks |

Rationale: `hasattr` is unconditionally banned per CLAUDE.md. Provenance and validation are irrelevant. Every cell is ERROR. This rule has the simplest corpus requirement: 5 TP samples across representative provenances.

**Rule R4: Broad `except` without re-raise**

| Provenance | RAW | STRUCTURALLY_VALIDATED |
|-----------|-----|----------------------|
| TIER_1 | ERROR / `true_positive` / blocks | ERROR / `true_positive` / blocks |
| TIER_2 | WARN / `true_positive_reduced` / blocks | WARN / `true_positive_reduced` / blocks |
| TIER_3 | SUPPRESS / `true_negative` | SUPPRESS / `true_negative` |
| UNKNOWN | WARN / `true_positive_reduced` / blocks | INFO / `true_note` / advisory |
| MIXED | WARN / `true_positive_reduced` / blocks | WARN / `true_positive_reduced` / blocks |

Rationale: Broad except on TIER_1 destroys audit trail evidence — always ERROR. TIER_2 is a contract violation — WARN (might be intentional error boundary, but suspicious). TIER_3 is expected — external boundaries legitimately catch broad exceptions. UNKNOWN and MIXED follow the conservative pattern. Validation attenuates UNKNOWN to INFO (the except might be protecting a validated boundary) but not MIXED (the except might swallow a TIER_1 crash).

**Rule R5: Unvalidated data reaches audit write path**

| Provenance | RAW | STRUCTURALLY_VALIDATED |
|-----------|-----|----------------------|
| TIER_1 | SUPPRESS / `true_negative` | SUPPRESS / `true_negative` |
| TIER_2 | SUPPRESS / `true_negative` | SUPPRESS / `true_negative` |
| TIER_3 | ERROR / `true_positive` / blocks | INFO / `true_note` / advisory |
| UNKNOWN | WARN / `true_positive_reduced` / blocks | INFO / `true_note` / advisory |
| MIXED | ERROR / `true_positive` / blocks | WARN / `true_positive_reduced` / blocks |

Rationale: TIER_1/TIER_2 reaching audit writes is expected — it's our data. TIER_3 + RAW reaching audit is the tool's primary catch — unvalidated external data in the audit trail. TIER_3 + STRUCTURALLY_VALIDATED gets INFO: the tool has seen validation but cannot vouch for semantic adequacy. The human reviewer evaluates whether the validator is sufficient for this specific audit write. MIXED + STRUCTURALLY_VALIDATED stays WARN because even with validation, the mixed container may carry unvalidated TIER_1/TIER_2 components into the audit path via a route the validator didn't cover.

**Rule R2: `getattr()` with default**

| Provenance | RAW | STRUCTURALLY_VALIDATED |
|-----------|-----|----------------------|
| TIER_1 | ERROR / `true_positive` / blocks | ERROR / `true_positive` / blocks |
| TIER_2 | ERROR / `true_positive` / blocks | ERROR / `true_positive` / blocks |
| TIER_3 | SUPPRESS / `true_negative` | SUPPRESS / `true_negative` |
| UNKNOWN | WARN / `true_positive_reduced` / blocks | INFO / `true_note` / advisory |
| MIXED | WARN / `true_positive_reduced` / blocks | WARN / `true_positive_reduced` / blocks |

Rationale: Same structure as R1 — `getattr` with default is the attribute-access equivalent of `.get()` with default.

### Corpus Size Estimate

| Cell Type | Count | Samples per cell | Total |
|-----------|-------|-----------------|-------|
| ERROR | 18 | 5 TP | 90 |
| WARN | 12 | 3 TP + 2 TN | 60 |
| INFO | 6 | 2 samples | 12 |
| SUPPRESS | 14 | 3 TN | 42 |
| **Total** | **50 cells** | | **204 entries** |

This is larger than Quinn's 126 estimate but within the same order of magnitude, and the matrix structure means each entry tests a *specific* provenance × validation × rule combination rather than a rule in isolation. The additional entries buy per-cell precision measurement, which enables per-cell threshold calibration — the mechanism that prevents any individual cell from degrading undetected.

### The Testability Guarantee

Every cell in the matrix has exactly one of four corpus verdicts. Every corpus verdict maps to a measurable outcome:

| Corpus Verdict | Assertion | Measurable? |
|---------------|-----------|-------------|
| `true_positive` | Tool emits ERROR for this pattern | Yes — fire/not-fire at ERROR |
| `true_positive_reduced` | Tool emits WARN for this pattern | Yes — fire/not-fire at WARN |
| `true_note` | Tool emits INFO for this pattern | Yes — fire/not-fire at INFO |
| `true_negative` | Tool does NOT emit for this pattern | Yes — no finding produced |

Quinn's Problem 1 is resolved: every cell has a precision metric (correct severity / total firings for that cell). Quinn's Problem 2 is resolved: the corpus tests severity assignment, not message quality. Quinn's Problem 3 (absorbing state) is bounded by architecture — INFO findings on R5 are proportional to external-to-audit flows, not to codebase size.

## 3. Integration Mapping for Layer 3 Diagnostics

### The Problem

Layer 3 metrics — suppression rate, violation velocity, validator concentration, attenuation-to-clean ratio, exception age distribution — are **system health signals**, not findings. They describe the gate's operational state, not individual code violations. They cannot be:

- **SARIF findings** — they don't have a source location, rule ID, or fix action
- **Exit code modifiers** — the gate's exit code is determined by Layer 1 findings only (Round 3 consensus)
- **Log lines** — invisible in practice, piped to `/dev/null` (Iris's correct observation)

They must be visible, always present, and never blocking. The question is: what output format, and how does the developer encounter them?

### The Three Output Channels

Layer 3 diagnostics appear in three channels, each serving a different audience at a different timescale:

#### Channel 1: CI Summary Block (Every Run)

Appended to the finding output in every `strict check` invocation. Always present. Never affects exit code.

```
─── Enforcement Health ───────────────────────────────────────
  Suppression rate:       12% (18 allowed / 152 total)    ↓ from 18%
  Violation velocity:     1.4/day (7-day avg)             stable
  INFO findings:          3 (external→audit flows via validators)
  Validator concentration: validate_response() → 8 flows  ⚠ review
  Allowlist hygiene:      4 entries expire within 14 days  ⚠ renew
──────────────────────────────────────────────────────────────
```

**Format:** Plain text, not SARIF. This block is a summary *of* the SARIF findings, not findings itself. It appears after the finding list and before the exit code line. In pre-commit mode (where output must be terse), it collapses to a single line:

```
Health: 12% suppressed | 1.4/day | 3 INFO | 4 expiring
```

**Why the developer sees it:** It's printed to stderr alongside the findings. Developers already read the finding output to understand what failed. The health block is 5 lines of context that appears every time. They don't need to seek it out.

#### Channel 2: Machine-Readable Sidecar (CI Integration)

Written alongside the SARIF output as a separate JSON file (`strict-health.json`):

```json
{
  "schema_version": "0.1.0",
  "timestamp": "2026-03-08T14:22:00Z",
  "run_id": "abc123",
  "metrics": {
    "suppression_rate": {
      "value": 0.12,
      "numerator": 18,
      "denominator": 152,
      "trend": "decreasing",
      "previous": 0.18
    },
    "violation_velocity": {
      "value": 1.4,
      "unit": "findings_per_day",
      "window_days": 7,
      "trend": "stable"
    },
    "info_findings": {
      "count": 3,
      "rule_breakdown": {"R5": 3}
    },
    "validator_concentration": [
      {"validator": "validate_response", "flows": 8, "threshold_exceeded": true},
      {"validator": "validate_config", "flows": 2, "threshold_exceeded": false}
    ],
    "allowlist_hygiene": {
      "total_entries": 18,
      "expiring_within_14d": 4,
      "oldest_entry_days": 89
    },
    "attenuation_ratio": {
      "structurally_validated": 14,
      "raw": 138,
      "ratio": 0.10
    }
  }
}
```

**Why a sidecar, not embedded in SARIF:** SARIF is a findings format — it has `results`, `rules`, `locations`. Health metrics have none of these. Embedding them as SARIF `properties` on the run object is technically possible but semantically wrong: it tells SARIF consumers "here's a property bag of stuff" with no schema contract. A dedicated sidecar with its own schema version is honest about what it is and enables independent evolution.

**CI integration:** The sidecar is consumed by dashboard pipelines, trend databases, and alerting systems. A CI step can read `strict-health.json` and post a PR comment with trend graphs, or trigger an alert if suppression rate exceeds a threshold. This is **not the tool's responsibility** — the tool produces the data; CI pipelines interpret it. The tool should not have opinions about dashboards.

#### Channel 3: Dedicated Command (On-Demand)

`strict health` runs Layer 3 analysis without Layer 1 enforcement:

```
$ strict health --since 30d

Enforcement Health Report (last 30 days)
────────────────────────────────────────

SUPPRESSION RATE
  Current: 12% (18/152)
  30d trend: 18% → 15% → 12% (improving)
  Threshold: <20% healthy, >30% investigate

VIOLATION VELOCITY
  Current: 1.4 findings/day (7-day rolling)
  30d trend: 2.1 → 1.8 → 1.4 (improving)
  By rule: R1=0.8/day, R4=0.4/day, R3=0.2/day

VALIDATOR CONCENTRATION
  validate_response()     8 flows  ⚠ Single-point-of-failure risk
  validate_api_result()   4 flows
  validate_config()       2 flows

ATTENUATION RATIO
  14 STRUCTURALLY_VALIDATED / 152 total = 9.2%
  Interpretation: 9% of findings attenuated by validators.
  Healthy range: 5-25%. Below 5% = validators unused. Above 25% = over-reliance.

ALLOWLIST HYGIENE
  18 entries total, 4 expiring within 14 days
  Oldest: engine/retry.py:89 (89 days, rule R4) — review or renew
  Batch renewal risk: 4 entries expire in same 7-day window
```

This command reads historical data from a local metrics store (SQLite file alongside the SARIF output). The metrics store is append-only — each `strict check` run appends a row. The `health` command queries it for trends.

### How the Developer Encounters Each Channel

| Channel | When | Who | Action |
|---------|------|-----|--------|
| CI Summary Block | Every `strict check` run | Developer reading CI output | Passive awareness — notice trends without seeking them |
| Machine-Readable Sidecar | Every CI run with `--output` | CI pipeline / dashboard | Automated trending, alerting, PR comments |
| `strict health` command | On-demand | Tech lead, quarterly review | Deliberate assessment of enforcement system health |

### Why This Mapping Works (System Dynamics)

The design addresses three feedback loops:

**Loop 1: Suppression rate visibility prevents allowlist bloat.** The suppression rate appears in every CI run. When it rises, it's visible to every developer who reads CI output. This creates social pressure: "why is our suppression rate 35%?" is a question that gets asked in standup, which triggers investigation, which produces either rule fixes or codebase fixes. Without visibility, the allowlist grows silently — the Eroding Goals archetype from Round 1.

**Loop 2: Violation velocity surfaces generation-time failures.** Rising violation velocity means agents are producing more violations per unit time. This is a signal to update agent instructions, not to fix individual findings. The metric appears in the CI summary block and the sidecar, enabling both human awareness (developer reads the trend) and automated alerting (CI pipeline detects rising velocity). Without this metric, the team treats each violation as an individual event rather than a systemic pattern — the "Fixes that Fail" archetype.

**Loop 3: Validator concentration prevents single-point-of-failure accumulation.** When one validator covers 8+ data flows, a bug in that validator compromises 8 trust boundaries simultaneously. The concentration metric surfaces this risk before it materialises. The developer encounters it in the CI summary (with a warning icon) and can investigate via `strict health`. Without this metric, validator quality is invisible — the "Shifting the Burden" archetype, where the tool's taint attenuation depends on validators it cannot verify.

### What Layer 3 Is NOT

Layer 3 metrics are **not a second gate**. They never produce exit codes. They never block CI. They never create SARIF findings. They are health signals about the *enforcement system itself*, reported through channels that ensure visibility without conflating them with code-level findings.

The distinction matters because mixing health metrics into findings output would create two problems: (a) developers would perceive the tool as noisy ("it blocked me for... a suppression rate?"), and (b) health metrics would be subject to the same allowlist/suppression mechanism as findings, creating a recursive governance problem where you suppress the signal that tells you suppression is too high.

Layer 3 lives *alongside* findings, visible in the same output stream, but structurally separate — a diagnostic panel on the gate, not an additional gate.
