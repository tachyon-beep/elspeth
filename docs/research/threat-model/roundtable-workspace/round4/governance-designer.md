# Round 4 — Governance Designer: Gideon

## 1. The Label Set — Governance Granularity Analysis

The question is not "which labels are theoretically correct?" but "which label set produces a governable exception matrix?" Every provenance × validation × rule combination is a potential exception category with its own review requirements, expiry norms, and escalation paths. Governance complexity scales with the *product* of these dimensions, not their sum.

### The Arithmetic of Governability

| Model | Provenance | Validation | Rules (v0.1) | Exception Categories | Governable? |
|-------|-----------|-----------|-------------|---------------------|-------------|
| Full (Pyre/Riven/Iris) | 5 | 2 | 7 | 70 | No |
| Middle (Sable) | 4 | 3 | 7 | 84 | No |
| Reduced (Quinn) | 4 | (embedded) | 7 | 28 | Yes |
| Recommended | 5 | 2 | 7 | 70 → ~24 effective | Yes (with grouping) |

70 cells is too many for individual governance treatment, but the matrix is *sparse*. Most cells don't need exception pathways because they're either unconditional (no exceptions permitted) or the exception pattern is identical to adjacent cells. The right approach: define the full 5×2 provenance × validation matrix for *rule evaluation* (precision matters), but collapse the *governance model* into equivalence classes where exception review, expiry, and escalation follow the same process.

### Governance Equivalence Classes

After analysing the rule evaluation matrices from Pyre, Sable, Quinn, and Iris, the cells collapse into four governance classes:

| Governance Class | Rule Evaluation Outcomes | Exception Policy | Example Cells |
|-----------------|------------------------|-----------------|---------------|
| **UNCONDITIONAL** | ERROR — no exceptions ever | Blocked; tool rejects exception creation | `hasattr()` (all provenances); `.get()` on TIER_1 |
| **STANDARD** | ERROR — exceptions permitted with review | `decision_group` with rationale, 90-day expiry, divergence detection | `.get()` on TIER_2; broad except on TIER_2; UNKNOWN + RAW reaching audit write |
| **LIBERAL** | WARN — exceptions with minimal review | Single-line rationale, 180-day expiry | `.get()` on UNKNOWN; MIXED provenance findings |
| **TRANSPARENT** | INFO/NOTE — no exceptions (below threshold) | N/A — findings are advisory, not blocking | TIER_3 + VALIDATED reaching audit write (note); UNKNOWN + VALIDATED `.get()` (note) |

This reduces 70 theoretical cells to 4 governance pathways. A developer creating an exception doesn't need to know which of 70 cells their finding falls into — they need to know which of 4 pathways applies, and the tool determines that from the finding's severity.

### Why 5 Provenance Labels, Not Quinn's 4

Quinn's argument that TIER_1/TIER_2 isn't AST-observable is technically correct but governance-irrelevant. The distinction doesn't need to be AST-inferred — it's *declared* via manifest or decorator, the same mechanism already accepted for `@external_boundary`. From a governance perspective, the TIER_1/TIER_2 distinction matters enormously:

- `.get()` on TIER_1 data is **UNCONDITIONAL** — no exception pathway exists. The audit trail cannot tolerate fabricated defaults. Period.
- `.get()` on TIER_2 data is **STANDARD** — exceptions are permitted because pipeline transforms occasionally have legitimate `.get()` patterns on row data that has undergone partial schema evolution.

Collapsing TIER_1 and TIER_2 into INTERNAL forces either: (a) making all INTERNAL `.get()` unconditional (too strict — blocks legitimate TIER_2 patterns), or (b) making all INTERNAL `.get()` standard-exception (too loose — allows exceptions on audit trail access). The governance model needs the distinction even if the AST needs help to provide it.

MIXED vs UNKNOWN: both are needed for governance. MIXED means "we know the composition and it's heterogeneous" — the developer action is to decompose the container. UNKNOWN means "we don't know" — the developer action is to add a provenance annotation. Different actions require different governance guidance in the exception rationale.

### `decision_group` and Provenance Tiers

**Yes, the `decision_group` must record the provenance tier(s) it covers.** A decision group covering "sparse token lookup" findings across both TIER_1 and TIER_2 is governmentally suspect — the rationale for `.get()` on audit data is fundamentally different from the rationale for `.get()` on pipeline data. The review prompt *must* distinguish them.

Concrete rule: a `decision_group` may span multiple findings on the *same* provenance tier but may NOT span findings across TIER_1 and TIER_2 boundaries. Cross-tier grouping requires two separate decision groups with independent rationales and expiry dates. This is a governance constraint, not a tool limitation — the tool can enforce it by rejecting `decision_group` assignments where the grouped findings span UNCONDITIONAL and STANDARD exception classes.

```toml
# VALID: same provenance tier, same rationale
[[tool.strict.exceptions]]
fingerprint = "a1b2c3d4"
rule = "SBE-T02"
decision_group = "sparse-token-lookup"
# provenance_tier = "TIER_2" — inferred from finding, validated by tool

# INVALID: tool rejects this grouping
[[tool.strict.exceptions]]
fingerprint = "e5f6g7h8"  # This finding is on TIER_1 data
rule = "SBE-T02"
decision_group = "sparse-token-lookup"  # ERROR: group contains TIER_2 findings
```

The divergence detection mechanism from Round 3 gains a new check: when a grouped fingerprint's provenance tier changes (because the underlying code changed which data source it accesses), the tool flags the group for mandatory re-review, not just advisory notification.

## 2. Exceptionability Classification — The Complete Matrix

The question "which cells allow exceptions?" is really "which cells represent irreducible design decisions vs. which represent violations that must always be fixed?" The answer depends on whether the finding reflects a *trust tier property* (invariant — never exception-worthy) or a *code pattern choice* (decision — sometimes exception-worthy).

### The Exceptionability Matrix

Using the scribe's recommended dimensions: Provenance {TIER_1, TIER_2, TIER_3, UNKNOWN, MIXED} × Validation {RAW, STRUCTURALLY_VALIDATED} × the 7 rules.

I present the matrix rule-by-rule, since exceptionability is rule-specific:

#### R1: `.get()` with default

| Provenance | RAW | STRUCTURALLY_VALIDATED |
|-----------|-----|----------------------|
| TIER_1 | **UNCONDITIONAL** ERROR | **UNCONDITIONAL** ERROR |
| TIER_2 | STANDARD ERROR | STANDARD ERROR |
| TIER_3 | SUPPRESS | SUPPRESS |
| UNKNOWN | LIBERAL WARN | LIBERAL WARN |
| MIXED | STANDARD WARN | STANDARD WARN |

**Rationale:** TIER_1 `.get()` is unconditional because the audit trail integrity principle ("crash on any anomaly") is a project invariant, not a design choice. No "but in this case the default is safe" rationale can override it — if the data is TIER_1, missing keys are corruption, and corruption must crash. TIER_2 allows exceptions because pipeline data sometimes has legitimate optional fields during schema evolution. Validation status is irrelevant for `.get()` — the issue is fabricating defaults, not whether the data was validated.

#### R2: `getattr()` with default

| Provenance | RAW | STRUCTURALLY_VALIDATED |
|-----------|-----|----------------------|
| TIER_1 | **UNCONDITIONAL** ERROR | **UNCONDITIONAL** ERROR |
| TIER_2 | STANDARD ERROR | STANDARD ERROR |
| TIER_3 | SUPPRESS | SUPPRESS |
| UNKNOWN | LIBERAL WARN | LIBERAL WARN |
| MIXED | STANDARD WARN | STANDARD WARN |

Mirrors R1 — same trust-tier logic applies.

#### R3: `hasattr()`

| Provenance | RAW | STRUCTURALLY_VALIDATED |
|-----------|-----|----------------------|
| ALL | **UNCONDITIONAL** ERROR | **UNCONDITIONAL** ERROR |

**Rationale:** `hasattr()` is unconditionally banned per CLAUDE.md. No governance pathway exists. The tool should refuse to create exceptions for R3 findings entirely. This is the simplest governance cell — zero ambiguity, zero exception management overhead.

#### R4: Broad `except` without re-raise

| Provenance | RAW | STRUCTURALLY_VALIDATED |
|-----------|-----|----------------------|
| TIER_1 | **UNCONDITIONAL** ERROR | **UNCONDITIONAL** ERROR |
| TIER_2 | STANDARD ERROR | STANDARD ERROR |
| TIER_3 | SUPPRESS | SUPPRESS |
| UNKNOWN | STANDARD WARN | STANDARD WARN |
| MIXED | STANDARD WARN | STANDARD WARN |

**Rationale:** Broad except on TIER_1 context destroys the audit trail crash guarantee — unconditional. On TIER_2, there are legitimate cases (e.g., operation wrapping on row values) where broad except with quarantine-and-continue is architecturally correct — standard exceptions with rationale. UNKNOWN gets standard rather than liberal because swallowing exceptions on unknown-provenance data is higher-risk than `.get()` defaults.

#### R5: `isinstance()` for type narrowing (on typed data)

| Provenance | RAW | STRUCTURALLY_VALIDATED |
|-----------|-----|----------------------|
| TIER_1 | **UNCONDITIONAL** ERROR | **UNCONDITIONAL** ERROR |
| TIER_2 | STANDARD ERROR | STANDARD ERROR |
| TIER_3 | SUPPRESS | SUPPRESS |
| UNKNOWN | LIBERAL WARN | LIBERAL WARN |
| MIXED | LIBERAL WARN | LIBERAL WARN |

**Rationale:** `isinstance()` on typed dataclass fields indicates distrust of the type system. Unconditional on TIER_1 (our schema, our types). TIER_3 suppress because external data legitimately needs type narrowing.

#### R6: Silent exception handling (catch-and-log without re-raise or error propagation)

| Provenance | RAW | STRUCTURALLY_VALIDATED |
|-----------|-----|----------------------|
| TIER_1 | **UNCONDITIONAL** ERROR | **UNCONDITIONAL** ERROR |
| TIER_2 | STANDARD ERROR | STANDARD ERROR |
| TIER_3 | LIBERAL WARN | SUPPRESS |
| UNKNOWN | STANDARD WARN | STANDARD WARN |
| MIXED | STANDARD WARN | STANDARD WARN |

**Rationale:** Silent exception handling on external data is sometimes legitimate at boundaries (log the failure, return error result). Validated external data has less reason for silent catch — the validation should have surfaced the error. TIER_1 is unconditional because silent exception handling on audit operations is audit trail destruction.

#### R7: Data flow — external data reaching audit write path

| Provenance | RAW | STRUCTURALLY_VALIDATED |
|-----------|-----|----------------------|
| TIER_1 | TRANSPARENT (SUPPRESS — this is reading, not writing external data) | TRANSPARENT (SUPPRESS) |
| TIER_2 | TRANSPARENT (SUPPRESS — pipeline data legitimately reaches audit) | TRANSPARENT (SUPPRESS) |
| TIER_3 | **UNCONDITIONAL** ERROR | STANDARD WARN |
| UNKNOWN | STANDARD ERROR | STANDARD WARN |
| MIXED | **UNCONDITIONAL** ERROR | STANDARD WARN |

**Rationale:** Unvalidated external data reaching audit writes is unconditional — no exception can justify writing unvalidated external data to the Landscape. Validated external data reaching audit writes is standard-exception — there are legitimate flows where validated external data is recorded (e.g., recording an LLM response after JSON parsing and schema validation). MIXED + RAW is unconditional because *any* unvalidated component in a mixed container contaminates the audit write.

### Summary Counts

| Class | Cell Count | Governance Cost |
|-------|-----------|----------------|
| UNCONDITIONAL | 24 | Zero — no exceptions to manage |
| STANDARD | 22 | Medium — decision_group, 90-day expiry, divergence detection |
| LIBERAL | 10 | Low — single-line rationale, 180-day expiry |
| TRANSPARENT | 8 | Zero — advisory output, no exception mechanism |
| SUPPRESS | 6 | Zero — no finding emitted |

**24 cells are ungovernable** (UNCONDITIONAL + TRANSPARENT + SUPPRESS = 38 cells with zero governance cost). Only **32 cells** require active governance, and those collapse into 2 pathways (STANDARD and LIBERAL). This is manageable.

## 3. Integration Mapping — Governance Lifecycle in CI

### Exception-Covered ERRORs and Exit Codes

**Yes, an ERROR finding with a valid exception changes the exit code contribution.** The finding is still emitted in output (transparency), but it does not contribute to exit code 1.

The mechanism:

```
Finding emitted → Exception lookup → Match found?
  ├─ No match  → Finding is ACTIVE  → contributes to exit code
  └─ Yes match → Exception valid?
       ├─ Valid (not expired, fingerprint matches) → Finding is EXCEPTED → exit 3 (advisory)
       └─ Expired or stale → Finding is ACTIVE → contributes to exit code
```

Exit code semantics:

| Condition | Exit Code | Meaning |
|-----------|-----------|---------|
| Active ERROR or WARN findings | 1 | Block — violations present |
| Only EXCEPTED findings + INFO/NOTE | 3 | Advisory — all violations have valid exceptions |
| No findings (or only SUPPRESS) | 0 | Clean |

The critical invariant: **an expired exception never silently passes.** When an exception expires, the finding transitions from EXCEPTED to ACTIVE in the very next CI run. The exit code changes from 3 to 1. The build breaks.

### Exception Expiry Transition — The Grace Period Problem

This is the most governance-critical integration question. When a `decision_group` expires, its N covered findings simultaneously become active. If N is large (8-15 findings for a significant architectural decision), the developer faces a wall of "new" violations that are actually old decisions requiring renewal.

**The governance model needs a grace period, not a cliff edge.**

Proposed expiry lifecycle:

| Phase | Duration | Exit Code | CI Behaviour | Developer Action |
|-------|----------|-----------|-------------|-----------------|
| **Active** | Until 14 days before expiry | 3 (if excepted) | Normal — exception covers findings | None required |
| **Warning** | 14 days before expiry | 3 (still advisory) | `HEALTH: ⚠ decision_group "sparse-token-lookup" (8 findings) expires in 12 days` | Review and renew proactively |
| **Grace** | 7 days after expiry | 1 (blocking) | `GATE: decision_group "sparse-token-lookup" EXPIRED — 8 findings now active. Run 'strict review sparse-token-lookup' to renew.` | Renew (re-review) or fix |
| **Hard expired** | After grace period | 1 (blocking) | Same as grace but `strict review` requires fresh rationale, not just confirmation | Full re-review required |

The warning phase appears in Seren's Layer 3 diagnostics (the health summary line). The grace phase promotes to Layer 1 (the gate). This progression uses the Enforcement-Diagnostic Stack architecture: information starts as a diagnostic signal and escalates to enforcement when ignored.

**Why a grace period, not an immediate cliff?** Without it, a team that misses a renewal deadline faces a sudden CI break with N findings. The rational response is to batch-renew all exceptions without genuine review — exactly the compliance ritual Seren warned about. The grace period with escalating severity (advisory → blocking → blocking-with-fresh-review) creates pressure to act *before* the cliff, when review quality is highest.

**Why a hard-expired state?** After the grace period, simple confirmation isn't sufficient — the exception has been expired long enough that the underlying code may have changed significantly. The `strict review` command in hard-expired mode regenerates the review digest (group health, stale fingerprints, divergent findings) and requires a fresh `decision_rationale`, not just a timestamp bump. This prevents the "renew without reading" anti-pattern.

### INFO Findings and the Governance Threshold

**INFO findings should NOT have exceptions.** They are below the governance threshold.

The reasoning:

1. **INFO findings don't block CI** (exit code 3, advisory). Exceptions exist to prevent blocking — you can't "unblock" something that doesn't block.
2. **INFO exceptions would create governance overhead for no enforcement benefit.** Managing expiry, review, and divergence detection for findings that don't affect the build is pure overhead.
3. **If an INFO finding is so noisy that developers want to suppress it, the correct action is to re-evaluate the rule's severity classification for that provenance × validation cell** — not to create an exception. Persistent INFO noise is a signal that the cell should be SUPPRESS, not that exceptions should absorb it.

The one exception (no pun intended): if a future version introduces configurable severity — where teams can promote INFO to WARN — then INFO-promoted-to-WARN findings would enter the exception system through their new severity class. But the governance threshold tracks *effective severity*, not *base severity*.

### Full Integration Mapping

| Output Category | Pre-commit | CI Exit Code | SARIF Level | GitHub Annotation | Exception Eligible? |
|----------------|-----------|-------------|-------------|-------------------|-------------------|
| ACTIVE ERROR | Block | 1 | error | Error | Yes (STANDARD/LIBERAL per matrix) |
| ACTIVE WARN | Block | 1 | warning | Warning | Yes (STANDARD/LIBERAL per matrix) |
| EXCEPTED ERROR/WARN | Pass | 3 | error/warning + `suppressed: true` | Notice (with "excepted" badge) | Already excepted |
| INFO/NOTE | Pass | 3 | note | Notice | No — below governance threshold |
| SUPPRESS | No output | 0 | — | — | No — not emitted |
| UNCONDITIONAL ERROR | Block | 1 | error | Error | No — tool rejects exception creation |

The SARIF output for excepted findings includes `suppressed: true` in the result properties (per SARIF spec §3.27.23), preserving the finding for reporting while marking it as handled. This means SARIF consumers (GitHub Code Scanning, SonarQube) can distinguish active from excepted findings without custom parsing.

### Governance Health in CI Output

Integrating with Seren's Enforcement-Diagnostic Stack, the CI output includes governance health alongside the gate result:

```
$ strict check src/elspeth/

GATE: 2 blocking findings, 1 unconditional, 5 excepted, 3 advisory
  SBE-R03:core/config.py:42    hasattr() [UNCONDITIONAL — no exception permitted]
  SBE-R01:engine/retry.py:89   .get() on TIER_2 data [ACTIVE — no exception]

GOVERNANCE:
  decision_groups: 4 active, 1 warning (expires in 9 days), 0 expired
  ⚠ "sparse-token-lookup" (8 findings) expires 2026-03-17 — run 'strict review sparse-token-lookup'
  exception coverage: 5/7 blockable findings excepted (71% suppression rate)

HEALTH:
  suppression rate 14% of total findings (below 15% threshold)
  violation velocity 0.8/day (declining — good)

Exit code: 1 (2 active blocking findings)
```

The GOVERNANCE section is new — it surfaces exception lifecycle status in every CI run, making expiry visible before it becomes an emergency. This sits between Seren's Layer 1 (gate) and Layer 3 (diagnostics) as a governance-specific status display.

## Summary

| Open Item | Resolution |
|-----------|-----------|
| **Label set** | 5 provenance × 2 validation (full model) for *rule evaluation*; 4 governance classes (UNCONDITIONAL/STANDARD/LIBERAL/TRANSPARENT) for *exception management*. Governance complexity: 2 active pathways, not 70. |
| **Exceptionability matrix** | 24 UNCONDITIONAL cells (zero governance cost), 32 governable cells (22 STANDARD + 10 LIBERAL), 14 below threshold (TRANSPARENT + SUPPRESS). `decision_group` constrained to same provenance tier. |
| **Integration mapping** | Excepted findings → exit 3 (advisory). Expiry uses 4-phase lifecycle (active → warning → grace → hard-expired). INFO has no exception pathway. SARIF uses `suppressed: true`. Governance health in CI output. |

### What This Produces That No Other Round 4 Position Will Reach

The exceptionability matrix is the missing piece that connects the label set (Open Item 1) to the integration mapping (Open Item 3). Without it, we know what the tool detects and how it outputs — but not which detections can be managed and which are absolute. The UNCONDITIONAL class is particularly important: it defines the floor below which no governance mechanism can override the tool. `hasattr()` is banned. `.get()` on TIER_1 is banned. Broad except on TIER_1 is banned. These are not design choices — they are project invariants encoded in the tool's governance model. Everything above that floor is a decision that the grouped fingerprint governance model (from Round 3) can manage at scale.
