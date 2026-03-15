# Round 5 — Final Dissent and Commitment: Sable (Security Architect)

## Commitment

**I commit to this design.** The 5×2 label set, 49-cell matrix, exit code scheme, governance model, and diagnostics architecture form a coherent security posture. I have no blocking concerns that would prevent implementation.

---

## Minority Report 1: INFO Advisory Is Acceptable — But Narrowly

Riven's compliance laundering attack is the strongest argument against INFO as advisory. I argued in Round 4 that INFO is acceptable because the note persists in SARIF artifacts, providing defence-in-depth through multiple downstream consumers (code reviewers, security auditors, trend analysis, post-incident investigation). I stand by that argument, but I want to be precise about *why* it holds and *when* it would stop holding.

**Why it holds for v0.1:** The INFO surface is narrow — 5 cells out of 49 (10%). Of those, the highest-risk cell is R5 (data reaching audit) on TIER_3+STRUCTURALLY_VALIDATED. This cell represents validated external data flowing to the audit trail — exactly the scenario where the tool honestly cannot determine adequacy. Making this ERROR would force every LLM transform that validates API responses into the exception governance pathway, which is not security — it is bureaucracy that erodes governance credibility.

The SARIF persistence argument works because ELSPETH is a small team with high review discipline. The assumption is that someone reads PR annotations, or at minimum that trend analysis (Seren's Layer 3 diagnostics) catches accumulation patterns. If either assumption fails, the defence-in-depth collapses.

**When it would stop holding:**

1. **If INFO action-rate falls below 5% after 6 months** (Quinn's metric), the category has empirically proven itself invisible. Reclassify affected cells — either promote to WARN (if the findings are valid) or demote to SUPPRESS (if they are noise).
2. **If team size exceeds ~15 engineers**, the "someone reads notices" assumption becomes probabilistic rather than certain. At that scale, Riven's Option 2 (threshold gate on INFO accumulation) becomes necessary.
3. **If agent-generated code exceeds 50% of new data flows**, the compliance laundering surface becomes the majority case, not the edge case. At that point, Riven's Option 1 (INFO blocks in agent self-check mode) should be reconsidered — not as differential enforcement by authorship, but as a mode-specific default that reflects the different review dynamics.

**My position:** Accept INFO as advisory for v0.1. Instrument the INFO action-rate metric from day one. Revisit at the 6-month mark with data, not speculation.

---

## Minority Report 2: Decorator-Consistency Checker Is Necessary But Insufficient

Riven's decorator abuse attack (Scenarios A, B, C) is real. The decorator-consistency checker — cross-referencing `@internal_data` against known external call patterns — catches Scenario A (external call mislabelled as internal) and the inverse of Scenario B (internal access mislabelled as external). This is the right first-pass mitigation.

**What it does not catch:**

- **Scenario C (mixed-provenance returns):** A function legitimately decorated `@external_boundary` that returns both API response data and internally-generated tracking fields. The decorator is honest — the function does call an external system. But the return value contains TIER_1 data (the tracking ID we generated) painted as TIER_3. The consistency checker sees `@external_boundary` + `requests.get()` and says "consistent." The `.get()` on the internal tracking field is suppressed.

- **Decorator omission:** Functions with no decorator default to TIER_2. If a function calls an external API without any decorator, the return value is TIER_2 (pipeline data). Every defensive pattern on this data becomes an ERROR finding ("contract violation on pipeline data") when the correct finding would be SUPPRESS ("legitimate boundary handling on external data"). The consistency checker only fires when decorators *exist* — it cannot detect their *absence*.

**Residual risk assessment:** Both gaps are code review concerns. The tool cannot solve Scenario C without inter-procedural return-value analysis (v1.0+ complexity). Decorator omission is detectable via coverage metrics — if a function in `plugins/transforms/` makes HTTP calls and has no decorator, that is a heuristic signal. But implementing this as a mandatory checker creates its own false positive surface.

**My recommendation:** Ship the decorator-consistency checker in v0.1. Document the two gaps as known limitations. Track Scenario C occurrences via MIXED provenance findings — if a function returns mixed-provenance data and the developer decomposes access (the correct fix), the MIXED findings serve as the detection mechanism. Decorator omission should be addressed in v0.2 via a "coverage report" diagnostic (Seren's Layer 3 channel): "N functions in transform plugins make external calls without provenance decorators."

---

## Remaining Security Concerns

### Concern 1: Exception Expiry Grace Period as Attack Window

Gideon's 4-phase expiry lifecycle includes a 7-day grace period where expired exceptions produce blocking findings. During this grace period, the finding is visible but the code has been shipping with the exception active for up to 90 days (STANDARD) or 180 days (LIBERAL). If the excepted pattern was genuinely problematic, the damage has been accumulating for months.

**This is not a design flaw — it is an inherent limitation of time-boxed governance.** The alternative (no grace period, immediate hard block on expiry) creates cliff-edge failures that incentivise extending exceptions rather than fixing the underlying code. Gideon's 14-day warning phase is the right mitigation: it gives operators two weeks to either fix the code or provide fresh rationale.

**Recommendation:** The 14-day warning should appear in Seren's Layer 3 diagnostics as a first-class signal, not just in the governance output block. Tech leads reviewing `strict health` should see "3 exceptions expiring in 14 days" as prominently as "2 new violations this sprint." The warning phase is the security-relevant window — it is when human attention determines whether accumulated risk gets addressed or rubber-stamped.

### Concern 2: UNCONDITIONAL Cells Must Be Tamper-Evident

24 of 49 cells are UNCONDITIONAL — the tool rejects exception creation entirely. This is the design's strongest security property. If an attacker (or a well-meaning developer under deadline pressure) can modify the exceptionability classification of a cell from UNCONDITIONAL to STANDARD, the entire governance model is compromised for that pattern.

**The classification must be encoded in the tool's source code, not in configuration.** If the exceptionability matrix lives in `strict.toml` or any other editable config file, a single-line change downgrades `hasattr()` from UNCONDITIONAL to STANDARD, and the tool happily accepts exceptions for the unconditionally banned pattern.

**Recommendation:** UNCONDITIONAL cells should be hardcoded constants in the rule engine. STANDARD/LIBERAL classifications may live in configuration (they represent policy choices that may evolve). The CI pipeline should include a test that verifies the UNCONDITIONAL cell count has not decreased — if it drops below 24, the build fails with an explicit message: "UNCONDITIONAL cell count decreased. This requires security review."

### Concern 3: Exit Code 2 Handling in CI Configuration

Exit 2 (tool error) must block CI. This is unanimously decided. But the enforcement depends on *how CI pipelines interpret exit codes*. Many CI systems treat any non-zero exit as failure, which is correct. But some configurations use `|| true` or `continue-on-error: true` to prevent tool failures from blocking the pipeline — a reasonable default for optional linters but catastrophic for a security gate.

**This is an operational concern, not a design concern.** The tool cannot enforce how CI systems interpret its exit codes. But the documentation and integration guide should be explicit: "Exit 2 means the tool could not run. If your CI configuration treats this as a pass, the security gate is open. This is equivalent to removing the lock from your front door."

**Recommendation:** The `strict health` diagnostic should include a self-test: on first run in a CI environment, emit exit 2 intentionally and verify the pipeline treats it as failure. If the pipeline continues, emit a WARN-level finding: "CI pipeline does not block on tool errors (exit 2). Security gate is ineffective." This is a one-time setup verification, not a per-run check.

---

## Summary

| Item | Position | Status |
|------|----------|--------|
| Overall design | **Commit** | No blocking concerns |
| INFO advisory | Accept for v0.1 with instrumented metrics | Agree with consensus, note boundary conditions |
| Decorator-consistency checker | Necessary, ship in v0.1 | Insufficient for Scenario C and omission — document as known limitations |
| Exception expiry | Gideon's 4-phase model is correct | Warning phase needs Layer 3 prominence |
| UNCONDITIONAL tamper-evidence | Hardcode in source, not config | Count-decrease test in CI |
| Exit 2 CI handling | Operational concern | Self-test on first CI run |

I have no further objections. The design is ready for implementation.
