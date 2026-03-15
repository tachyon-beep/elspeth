# Round 4 — Scribe Minutes

**Scribe: Morgan (Roundtable Orchestrator)**

## Convergence Status

Round 4 was tasked with resolving three open items. Two are now decided. One has a productive remaining tension.

| Item | Status | Resolution |
|------|--------|-----------|
| **Label set** | **DECIDED (6/7)** | 5 provenance × 2 validation, 7 effective states |
| **Rule evaluation matrix** | **DECIDED (consensus)** | 4-level severity (ERROR/WARN/INFO/SUPPRESS) with corpus verdicts for every cell |
| **Integration mapping** | **DECIDED with minority position** | ERROR/WARN → exit 1, INFO → exit 3, SUPPRESS → exit 0. Riven dissents on INFO non-blocking. |

## DECIDED: Label Set — 5 Provenance × 2 Validation (6/7)

### The TIER_1/TIER_2 Question Resolved

Round 4 produced a dramatic position swap. Quinn (who collapsed TIER_1/TIER_2 in Round 3) conceded to keeping them split. Pyre (who kept them split in Round 3) conceded to collapsing them. The net result: **6 agents keep the split, 1 collapses**.

| Agent | Round 3 | Round 4 | Shift |
|-------|---------|---------|-------|
| Sable | Split | **Split** (reversed Round 3 collapse) | REVERSAL |
| Quinn | Collapsed | **Split** (conceded to scribe's decorator argument) | CONCESSION |
| Pyre | Split | **Collapsed** (verdicts identical in every cell) | CONCESSION |
| Seren | Split | **Split** | HELD |
| Riven | Split | **Split** | HELD |
| Iris | Split | **Split** | HELD |
| Gideon | Split | **Split** (governance requires the distinction) | HELD |

**The decisive arguments:**

1. **Iris (developer experience):** The INTERNAL message tells developers *what* is wrong; TIER_1/TIER_2 messages tell them *why* and *what to do*. "Evidence tampering risk — crash immediately" vs. "upstream contract violation — fix the bug, don't mask it." These are different developer actions.

2. **Sable (severity separation):** `.get()` on TIER_1 is UNCONDITIONAL ERROR (audit corruption, legal exposure). `.get()` on TIER_2 is STANDARD ERROR (contract violation, exceptions sometimes permitted). Collapsing forces a false choice between over-alerting and under-alerting.

3. **Gideon (governance):** TIER_1 `.get()` is UNCONDITIONAL — no exception pathway. TIER_2 `.get()` is STANDARD — exceptions permitted with review. The governance model *requires* the distinction.

4. **Quinn (concession):** "The scribe's decorator argument is sound — architecturally consistent with existing `@external_boundary`." Also: broad `except` and `isinstance()` genuinely differ in severity between tiers.

**Pyre's counter-argument:** The verdicts are identical in every matrix cell for the 4 rules Pyre analysed. Message differentiation doesn't require separate labels — source-site metadata as annotation achieves the same UX. This is the minority position.

**Scribe assessment:** Pyre's argument is technically valid for a 4-rule matrix but breaks when Iris, Sable, and Quinn demonstrate rules where TIER_1 and TIER_2 produce *different severities* (R4 broad except: ERROR vs WARN; R6/R7 isinstance: ERROR vs WARN; R5 data reaching audit: SUPPRESS vs INFO). The split earns its keep. Pyre's 4-rule matrix was too narrow to show the divergence.

**Scribe verdict: DECIDED.** Provenance: {TIER_1, TIER_2, TIER_3, UNKNOWN, MIXED}. Five labels.

### The MIXED vs UNKNOWN Question Resolved

Unanimous. Quinn conceded MIXED is distinct from UNKNOWN. All 7 agents agree.

| Property | MIXED | UNKNOWN |
|----------|-------|---------|
| What tool knows | "This container holds data from multiple tiers" | "I cannot determine where this data came from" |
| Developer action | Decompose the container — separate access paths by tier | Add provenance annotation |
| Finding confidence | Higher (known composition) | Lower (missing information) |
| Corpus verdict | `true_positive_reduced` (WARN) for most rules | `true_positive_reduced` (WARN) for most rules |

Seren provided the system dynamics argument: collapsing MIXED into UNKNOWN eliminates the resolution pressure (destructure your containers) that keeps MIXED bounded. Without it, UNKNOWN becomes a garbage-can category that drives allowlisting rather than improvement.

**Scribe verdict: DECIDED.** MIXED is a distinct label.

### The Validation Dimension

| Agent | Position | Model |
|-------|----------|-------|
| Pyre | Separate dimension (RAW, STRUCTURALLY_VALIDATED) | 2D |
| Sable | Separate dimension (same labels) | 2D |
| Seren | Separate dimension (same labels) | 2D |
| Iris | Separate dimension (same labels) | 2D |
| Riven | Conceded to 2D model | 2D |
| Gideon | Adopted 2D model for rule evaluation | 2D |
| Quinn | Embedded for v0.1, separate for v1.0 | Pragmatic 1D→2D |

**Effective consensus:** 6/7 for explicit 2D. Quinn accepts the 2D model is correct in principle but proposes embedded VALIDATED as pragmatic shortcut for v0.1. This is a soft dissent — Quinn will work with the 2D model.

**Scribe verdict: DECIDED.** Two explicit dimensions. Provenance: {TIER_1, TIER_2, TIER_3, UNKNOWN, MIXED}. Validation: {RAW, STRUCTURALLY_VALIDATED}. VERIFIED deferred to v1.0 (unanimous).

### Effective State Space

Multiple agents independently converged on **7 effective states**, not 10:

| State | Provenance | Validation | Notes |
|-------|-----------|-----------|-------|
| 1 | TIER_1 | N/A | Internal data — validation not applicable |
| 2 | TIER_2 | N/A | Internal data — validation not applicable |
| 3 | TIER_3 | RAW | Unvalidated external data |
| 4 | TIER_3 | STRUCTURALLY_VALIDATED | Validated external data |
| 5 | UNKNOWN | RAW | Unknown provenance, unvalidated |
| 6 | UNKNOWN | STRUCTURALLY_VALIDATED | Unknown provenance, validated |
| 7 | MIXED | N/A | Heterogeneous container |

Validation status is only meaningful for TIER_3 and UNKNOWN data (external or unknown data that may pass through a validator). TIER_1 and TIER_2 are inherently trusted — they don't pass through `@validates_external`. MIXED takes the minimum validation status of its constituents (Seren: "weakest link").

## DECIDED: Rule Evaluation Matrix — 4-Level Severity with Corpus Verdicts

### Severity System (unanimous)

| Severity | Corpus Verdict | CI Behaviour | Pre-commit | SARIF Level |
|----------|---------------|-------------|-----------|-------------|
| **ERROR** | `true_positive` | Block (exit 1) | Block | `error` |
| **WARN** | `true_positive_reduced` | Block (exit 1) | Block | `warning` |
| **INFO** | `true_note` | Advisory (exit 3) | Pass | `note` |
| **SUPPRESS** | `true_negative` | No output (exit 0) | Pass | — |

Quinn's 4-category system adopted by all agents. Every cell in the matrix has exactly one verdict. The corpus tests severity assignment: "for this code pattern at this provenance, the tool should emit at *this* severity." Testable, measurable, falsifiable.

### Matrix Convergence

All seven agents provided matrices. Cross-referencing reveals strong convergence on most cells, with a few productive disagreements:

**Cells with full agreement (all agents identical):**

| Rule | Provenance | Severity | Rationale |
|------|-----------|----------|-----------|
| `hasattr()` | ANY | ERROR | Unconditionally banned |
| `.get()` | TIER_1 | ERROR | Fabricating audit evidence |
| `.get()` | TIER_2 | ERROR | Masking contract violations |
| `.get()` | TIER_3+RAW | SUPPRESS | Legitimate boundary handling |
| `.get()` | TIER_3+SV | SUPPRESS | Validated, legitimate use |
| Broad `except` | TIER_1 | ERROR | Audit trail destruction |
| Data→audit | TIER_3+RAW | ERROR | Unvalidated external in audit |
| Data→audit | TIER_1 | SUPPRESS | Internal data in audit — expected |
| Data→audit | TIER_2 | SUPPRESS | Pipeline data in audit — expected |

**Cells with productive disagreement:**

| Rule | Provenance | Agent | Severity | Notes |
|------|-----------|-------|----------|-------|
| `.get()` | TIER_3+SV | **Riven** | **INFO** | Cannot verify validator covers accessed field |
| `.get()` | TIER_3+SV | Others | SUPPRESS | Validated — `.get()` is acceptable |
| Broad `except` | TIER_3+RAW | **Sable** | **WARN** | Broad catch should use specific types |
| Broad `except` | TIER_3+RAW | Others | SUPPRESS | Expected boundary handling |
| Broad `except` | TIER_2 | **Quinn/Seren** | **WARN** | Less catastrophic than Tier 1 |
| Broad `except` | TIER_2 | **Sable/Iris** | **ERROR** | Contract violation — masks bugs |
| Data→audit | TIER_3+SV | All | INFO | Validated but semantic adequacy unknown |
| Data→audit | MIXED+SV | **Sable/Pyre** | WARN | Even validated, may carry unvalidated components |
| Data→audit | MIXED+SV | **Quinn** | ERROR | Conservative — treat as violation |

**Scribe resolution on the disagreements:**

1. **`.get()` on TIER_3+SV:** Riven's INFO attack is technically sound (tool can't verify validator covers the accessed field), but the volume concern is real — every validated `.get()` in every transform becomes an INFO finding. **Recommendation: SUPPRESS for v0.1, with Riven's per-field coverage check as a v1.0 enhancement.** The golden corpus should include an adversarial entry testing this cell.

2. **Broad `except` on TIER_3+RAW:** Sable's WARN is more cautious. The ELSPETH trust model says to wrap external calls, but with *specific* exception types. **Recommendation: SUPPRESS for v0.1.** The distinction between `except requests.RequestException` (specific, good) and `except Exception` (broad, bad) requires syntactic analysis of the exception type, which is a rule refinement, not a provenance question. A separate rule (R4b: broad vs. specific exception) should handle this in v0.2.

3. **Broad `except` on TIER_2:** Split between ERROR (Sable/Iris) and WARN (Quinn/Seren). The CLAUDE.md manifesto says "let plugin bugs crash" which supports ERROR. But transforms do wrap *operations on row values* (arithmetic, parsing) in try/except, which is correct per the trust model. **Recommendation: WARN.** Transforms legitimately catch row-level operation failures (Tier 2 data values, not Tier 2 types). ERROR would create false positives on the most common transform pattern.

4. **Data→audit MIXED+SV:** Quinn's ERROR is more conservative. Pyre/Sable's WARN acknowledges the validation passed but questions whether all components are covered. **Recommendation: WARN.** MIXED+SV means at least some validation occurred. ERROR should be reserved for cases where NO validation occurred on data reaching audit.

### Consolidated Reference Matrix

Based on the consensus positions and scribe resolutions above, the reference matrix for the 7 effective states across core rules:

| Rule | TIER_1 | TIER_2 | T3+RAW | T3+SV | UNK+RAW | UNK+SV | MIXED |
|------|--------|--------|--------|-------|---------|--------|-------|
| R1 `.get()` | ERROR | ERROR | SUPPRESS | SUPPRESS | WARN | INFO | WARN |
| R2 `getattr()` | ERROR | ERROR | SUPPRESS | SUPPRESS | WARN | INFO | WARN |
| R3 `hasattr()` | ERROR | ERROR | ERROR | ERROR | ERROR | ERROR | ERROR |
| R4 Broad `except` | ERROR | WARN | SUPPRESS | INFO | WARN | INFO | WARN |
| R5 Data→audit | SUPPRESS | SUPPRESS | ERROR | INFO | WARN | INFO | WARN |
| R6 `except: pass` | ERROR | ERROR | WARN | WARN | ERROR | WARN | ERROR |
| R7 `isinstance()` | ERROR | WARN | SUPPRESS | SUPPRESS | WARN | SUPPRESS | WARN |

**49 cells. All defined. No gaps.**

Distribution: ERROR 19 (39%), WARN 14 (29%), INFO 5 (10%), SUPPRESS 11 (22%).

### Corpus Size

Using Quinn's sample counts per verdict:

| Verdict | Cells | Samples/cell | Total |
|---------|-------|-------------|-------|
| ERROR | 19 | 5 TP | 95 |
| WARN | 14 | 3 TP + 2 TN | 70 |
| INFO | 5 | 2 | 10 |
| SUPPRESS | 11 | 3 TN | 33 |
| **Total** | **49** | | **~208** |

Within Quinn's estimated range after adjusting for the expanded label set. The `hasattr()` row (7 ERROR cells) shares samples across provenance — ~5 unique samples, not 35. Effective unique corpus entries: ~180.

## DECIDED (with minority position): Integration Mapping

### Exit Codes (unanimous)

| Code | Meaning | Condition |
|------|---------|-----------|
| 0 | Clean | No findings at any severity |
| 1 | Blocking | ERROR or WARN findings present (not covered by exception) |
| 2 | Tool error | Parse failure, config error, analysis couldn't run |
| 3 | Advisory | INFO findings only |

**Exit 2 MUST block CI** (Sable, Iris: "an open gate is worse than no tool"). Unanimous.

### Severity-to-Integration Mapping (6/7 consensus)

| Severity | Pre-commit | CI exit | SARIF level | GitHub annotation | Exception eligible |
|----------|-----------|---------|-------------|-------------------|--------------------|
| ERROR | Block | 1 | error | Error (red) | Yes (STANDARD/LIBERAL per Gideon) |
| WARN | Block | 1 | warning | Warning (yellow) | Yes (STANDARD/LIBERAL) |
| INFO | Pass | 3 | note | Notice (blue) | No (below governance threshold) |
| SUPPRESS | — | 0 | — | — | No |
| UNCONDITIONAL ERROR | Block | 1 | error | Error (red) | No (tool rejects exception) |

### Riven's Minority Position: INFO Should Block in Agent Mode

Riven attacks advisory INFO as "compliance laundering" — the same binary cleansing problem shifted from taint engine to output layer. The argument:

1. Agent generates validator stub satisfying structural check
2. Data becomes TIER_3+STRUCTURALLY_VALIDATED
3. Data reaching audit write → INFO finding
4. CI exits 3 → green build → merged
5. GitHub notice annotation → collapsed, unread
6. Identical to binary cleansing compliance ritual, shifted one level up

**Riven's proposed resolution:** INFO blocks in `--stdin` mode (agent self-check) but remains advisory for human CI. This creates differential enforcement — agents are held to a higher standard because they won't read notices.

**Scribe assessment:** Riven's attack is structurally valid. The advisory INFO path does create a potential compliance gap on agent-generated code. However:

1. Differential enforcement (agent vs. human) was explicitly rejected in Round 2 (dual enforcement profiles, 7/7 rejection, Iris concession). Riven's Option 1 reintroduces this under a different name.
2. The rejected argument was about authorship-based severity, not mode-based severity. `--stdin` mode is an invocation context, not an authorship claim. The distinction is subtle but real: the tool isn't saying "agent code is less trusted" — it's saying "agent self-check mode has different defaults."
3. Sable's counter-argument is strong: INFO only covers 4-5 cells out of 49 (8-10%). The compliance ritual surface is narrow. Defence-in-depth via SARIF artifact persistence, trend analysis, and review annotations provides multiple catch points beyond the immediate gate.

**Scribe verdict: INFO is advisory (exit 3) for v0.1.** Riven's concern is documented as a known risk. The INFO action-rate metric (Quinn's proposal) provides a measurement mechanism: if after 6 months INFO findings show <5% developer action rate, the cell should be reclassified. Riven's Option 2 (threshold gate on INFO accumulation) is a viable v0.2 enhancement that doesn't require differential enforcement.

### Layer 3 Diagnostics Integration (Seren)

Seren specified three channels, none of which affect exit codes:

| Channel | Format | When | Audience |
|---------|--------|------|----------|
| CI summary block | Plain text after findings | Every `strict check` | Developer reading CI output |
| `strict-health.json` sidecar | JSON with schema version | Every CI run with `--output` | Dashboards, alerting pipelines |
| `strict health` command | Rich text with trends | On-demand | Tech leads, quarterly reviews |

**Scribe assessment:** Clean separation. Diagnostics are *about* the gate, not *part of* the gate. No agent objected. The sidecar format is well-specified (suppression rate, violation velocity, validator concentration, allowlist hygiene, attenuation ratio). **Accepted.**

### Governance Integration (Gideon)

Gideon added governance-specific output between the gate and diagnostics:

```
GATE: 2 blocking findings...
GOVERNANCE: 4 active groups, 1 warning (expires 9 days)...
HEALTH: suppression rate 14%...
```

The 4-phase expiry lifecycle (active → 14-day warning → 7-day grace with blocking → hard-expired requiring fresh rationale) prevents cliff-edge failures on exception expiry. **Accepted.**

### Gideon's Exceptionability Matrix

Gideon classified each matrix cell into governance classes:

| Class | Count | Policy |
|-------|-------|--------|
| UNCONDITIONAL | 24 | No exceptions — tool rejects creation |
| STANDARD | 22 | Decision_group, 90-day expiry, divergence detection |
| LIBERAL | 10 | Single-line rationale, 180-day expiry |
| TRANSPARENT | 8 | Advisory/suppress — below governance threshold |

**Key insight:** 24 of 49 cells (49%) are UNCONDITIONAL — no governance mechanism can override them. `hasattr()` everywhere. `.get()` on TIER_1. Broad `except` on TIER_1. `except: pass` on TIER_1/TIER_2. These are project invariants encoded in the tool. The governance model manages the remaining 32 cells through 2 pathways (STANDARD and LIBERAL).

**Cross-tier grouping constraint:** `decision_group` may not span findings across TIER_1 and TIER_2 boundaries. The rationale for exceptions on audit data is fundamentally different from the rationale on pipeline data. This prevents governance shortcuts.

## Novel Concepts Introduced in Round 4

| Concept | Introduced by | Description |
|---------|--------------|-------------|
| **7 effective states** | Sable (independently: Pyre, Iris) | Validation status N/A for internal data → 5×2 matrix reduces to 7 distinct behaviours |
| **Decorator-consistency checker** | Riven | Mandatory first-pass rule: verify `@internal_data` doesn't decorate functions calling known external boundaries |
| **Compliance laundering attack** | Riven | INFO findings via exit 3 reproduce the compliance ritual, shifted from taint engine to output layer |
| **INFO action-rate metric** | Quinn | Measure % of INFO findings that trigger developer action; <5% after 6 months → reclassify to SUPPRESS |
| **4-phase expiry lifecycle** | Gideon | Active → 14-day warning → 7-day grace (blocking) → hard-expired (fresh rationale required) |
| **Exceptionability matrix** | Gideon | 4-class governance overlay: UNCONDITIONAL/STANDARD/LIBERAL/TRANSPARENT |
| **Cross-tier grouping constraint** | Gideon | Decision_groups may not span TIER_1 and TIER_2 findings |
| **Layer 3 sidecar format** | Seren | `strict-health.json` with schema-versioned diagnostic metrics separate from SARIF |
| **Determinism guarantee** | Iris | Byte-identical output for byte-identical input; finding order deterministic |
| **Performance budget** | Iris | <200ms pre-commit, <5s CI, <100ms agent mode |

## Position Shift Tracking (Round 4)

| Agent | Round 3 Position | Round 4 Position | Shift |
|-------|-----------------|-----------------|-------|
| **Pyre** | 5 provenance × 3 validation, TIER_1/TIER_2 split | 4 provenance × 2 validation, TIER_1/TIER_2 collapsed | CONCESSION on tiers |
| **Sable** | 4 provenance (collapsed TIER_1/TIER_2) | **5 provenance (reversed collapse)** | REVERSAL |
| **Quinn** | 4 provenance (collapsed, embedded validation) | **6 labels (split tiers, MIXED added), still embedded validation** | DOUBLE CONCESSION |
| **Seren** | 3-layer stack, attenuation model | 5×2 model, reconciled notes with testability | REFINEMENT |
| **Riven** | 6 flat labels | Conceded to 2D model. Attacked INFO as compliance laundering. | CONCESSION + NEW ATTACK |
| **Gideon** | Grouped fingerprint governance | Added exceptionability matrix and 4-phase expiry | EXTENSION |
| **Iris** | Provenance in engine, tier-contextualized output | Complete integration spec (CLI, SARIF, exit codes, manifest, performance) | EXTENSION |

## Scribe Observations

### Observation 1: The Design Is Substantially Complete

Round 4 resolved the three open items. The tool's architecture is now specified:

- **Taint model:** 5 provenance × 2 validation, 7 effective states
- **Rule evaluation:** 49-cell matrix, every cell defined, 4-level severity
- **Corpus:** ~208 entries structured by the matrix
- **Integration:** 4 exit codes, SARIF 2.1.0, provenance-contextualized messages
- **Governance:** 4-class exceptionability, grouped fingerprints, 4-phase expiry
- **Diagnostics:** 3-channel Layer 3, sidecar format, independent from findings
- **Manifest:** `strict.toml` with topology, rules, heuristics, exceptions

### Observation 2: Riven's Decorator Abuse Attack Is Unaddressed

Riven identified decorator-based label assignment as a self-declaration vulnerability. Mislabelling `@internal_data` on an external call or `@external_boundary` on an internal function produces wrong provenance → wrong severity → wrong developer action. The proposed decorator-consistency checker (cross-reference decorators against heuristic list) is a partial mitigation but doesn't cover all cases (Scenario C: legitimate decorator on function with mixed-provenance returns).

**This is a known limitation, not a blocking concern.** The tool already trusts `@external_boundary` declarations. Adding `@audit_data` declarations uses the same trust model. The decorator-consistency checker catches the mechanical mislabelling that agents will produce. The residual risk (intentional or scope-mismatched declarations) is a code review concern, not a tool concern.

### Observation 3: Round 5 Should Focus on Final Dissent and Minority Reports

The design is substantially complete. Round 5 should:
1. Give each agent one final opportunity to register disagreement with any decided position
2. Produce minority reports for positions that were rejected or modified
3. Confirm that no agent has an unaddressed concern that would undermine the design
4. Surface any remaining implementation concerns (e.g., Pyre on AST edge cases)

The goal is **closure, not further design iteration.** Agents should state whether they can commit to the design as decided, and if not, what specific change would resolve their concern.
