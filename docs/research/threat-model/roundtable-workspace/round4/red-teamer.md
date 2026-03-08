# Round 4 — Adversarial Attacks: Riven (Adversarial Red-Teamer)

## Preamble: Concession on the 2D Model

The scribe is right that my Round 3 `TIER_3_VALIDATED` violates the "provenance never changes" invariant. Provenance is an origin fact; validation is a processing fact. Encoding both in a single label creates a compound state that conflates them. I concede to the 2D model: Provenance {TIER_1, TIER_2, TIER_3, UNKNOWN, MIXED} x Validation {RAW, STRUCTURALLY_VALIDATED}. 10 states.

My 6 flat labels were a premature optimisation — fewer labels at the cost of a lost invariant. The invariant is load-bearing: if provenance can change (as it implicitly does when TIER_3 "becomes" TIER_3_VALIDATED), then the audit trail records a fact that later changes, which violates ELSPETH's own Tier 1 principle. The 2D model avoids this by keeping both dimensions independently immutable in their respective semantics (provenance never changes; validation status monotonically increases from RAW to STRUCTURALLY_VALIDATED).

With that concession made, here are three attacks on the remaining open items.

---

## Attack 1: Label Manipulation via Decorator Abuse

### The Attack

The 2D model's provenance axis depends entirely on how labels are assigned. The scribe identifies three assignment mechanisms: `@external_boundary` decorators, `@internal_data` decorators, and heuristic matching. Each is attackable.

**Scenario A: Mislabelling external as internal.**

```python
@internal_data  # LIE — this calls an external API
def get_enrichment_data(row_id: str) -> dict:
    return requests.get(f"https://api.enrichment.io/{row_id}").json()
```

The agent decorates an external call with `@internal_data`. The return value gets `(TIER_1, UNTRACKED)` provenance. Every `.get()` on this data is now a FINDING (Tier 1 data shouldn't use `.get()`) — but the *severity is wrong*. The finding says "you're using `.get()` on audit data, crash instead" when the correct finding is "you're using `.get()` on unvalidated external data without a validator." The developer "fixes" it by removing `.get()` and using direct access — which will crash on missing keys from the API, but the *crash message* will say "audit data corruption" when the actual problem is "API returned unexpected schema." The audit trail now records a false corruption event. The decorator lie doesn't suppress findings — it *miscategorises* them, which is worse because the developer takes the wrong corrective action.

**Scenario B: Mislabelling internal as external.**

```python
@external_boundary  # LIE — this reads from our own Landscape database
def get_row_state(recorder, token_id: str) -> dict:
    return recorder.get_row_state(token_id)
```

Now Landscape reads are `(TIER_3, RAW)`. Every `.get()` is suppressed (legitimate coercion on external data). The agent can use `.get("state", "pending")` on audit data, fabricating default values on Tier 1 data, and the tool says nothing. This is the exact ACF-I1 pattern the tool is designed to catch — *completely suppressed* by a single decorator.

**Scenario C: The decorator is technically accurate but scope-mismatched.**

```python
@external_boundary  # Technically true — HTTP call to external service
def get_or_create_customer(api_client, customer_data: dict) -> dict:
    response = api_client.post("/customers", json=customer_data)
    return {
        "api_response": response.json(),           # Legitimately TIER_3
        "internal_tracking": generate_audit_id(),   # Actually TIER_1
    }
```

The function *does* make an external call, so `@external_boundary` is not a lie. But the return value mixes tiers — and the decorator paints the entire return as `TIER_3`. The `internal_tracking` field is now TIER_3 provenance. The agent can `.get("internal_tracking", "unknown")` and the tool suppresses it. This isn't adversarial mislabelling — it's a legitimate decorator on a function with mixed-provenance returns, and the tool gets it wrong.

### What This Means for the Label Set

The 10-state model is correct in its expressiveness. The vulnerability is not in the label set itself but in the **label assignment mechanism**. Decorators are self-declarations — the code declares its own trust level, which is asking the accused to judge their own trial. The heuristic list is better (external oracle), but it only covers known call sites.

**Required defence:** The tool needs a **decorator-consistency checker** as a mandatory first-pass rule. If `@internal_data` is applied to a function that calls anything on the heuristic list (requests.get, httpx.Client, etc.), emit a VIOLATION-level finding: "Function decorated as @internal_data but calls known external boundary at line N." Similarly, if `@external_boundary` is applied to a function whose body contains only attribute access on known internal objects (self._recorder, self._config), emit a finding.

This is not sufficient — Scenario C shows that even consistent decorators produce wrong labels on mixed-provenance returns. But it catches the mechanical mislabelling that agents will produce. The residual risk (correct decorator, mixed-provenance return) should be addressed by promoting MIXED provenance to apply at the return-value level, not just the container-construction level.

---

## Attack 2: Matrix Cell Severity Errors

The scribe asked for a complete Provenance x Validation x Rule matrix with corpus verdicts. Here is my red-team of the emerging consensus matrix, attacking specific cells where severity is wrong.

### Cell: (TIER_3, STRUCTURALLY_VALIDATED) x `.get()` = SUPPRESS

**Verdict: Correct, but conditionally.** The suppression assumes the validator actually touches the field being `.get()`-ed. Consider:

```python
@validates_external
def validate_api_response(data: dict) -> dict:
    if not isinstance(data.get("status"), int):
        raise ValueError("status must be int")
    return data

validated = validate_api_response(raw_api_response)
name = validated.get("customer_name", "unknown")  # SUPPRESSED
```

The validator checks `status`. The `.get()` is on `customer_name`. The tool suppresses because validation status is STRUCTURALLY_VALIDATED — but the validation has nothing to do with the accessed field. This is a **false negative**: the tool fails to flag a fabrication-via-default on a field that was never validated.

**Severity correction:** This cell should be INFO, not SUPPRESS. The tool cannot know whether the validator covers the specific field being accessed (that requires semantic analysis beyond v0.1), so it should emit an advisory note: "`.get()` with default on structurally validated external data. Validator `validate_api_response` at line N — verify it covers this field." This is Quinn's INFO category with Seren's "human please review" semantics.

**Corpus implication:** This cell needs both a TP sample (validator doesn't cover accessed field) and a TN sample (validator does cover accessed field, e.g., the field is the return value of a validated parse). The corpus verdict is `true_note` — the tool should always emit here, not suppress.

### Cell: (TIER_2, RAW) x `.get()` = FINDING (ERROR)

**Verdict: Correct severity, wrong validation status assumption.** TIER_2 data in ELSPETH's model is post-source pipeline data. By definition, it passed source validation. It should never be RAW — it should be STRUCTURALLY_VALIDATED by the source plugin. If a variable is `(TIER_2, RAW)`, either:

1. The label assignment is wrong (it's actually TIER_3 and the decorator is mislabelled), or
2. The provenance tracking lost the validation status during propagation (bug in the tool)

This cell should be a VIOLATION, not just a FINDING — but the violation is about the *label state being impossible*, not about the `.get()` pattern. The tool should emit: "Internal inconsistency: TIER_2 data with RAW validation status at line N. This state should not exist — pipeline data has already passed source validation."

**Corpus implication:** This cell should have 0 TN samples. Any corpus entry for this cell is a test for the tool's consistency checking, not for the `.get()` rule.

### Cell: (UNKNOWN, RAW) x Broad `except` = WARN

**Verdict: Severity too low. Should be ERROR.**

The UNKNOWN provenance means the tool cannot determine where data came from. A broad `except` on unknown-provenance data could be hiding Tier 1 corruption — and since we don't know the provenance, we should assume the worst. ELSPETH's principle is "if it's not recorded, it didn't happen." If we can't record the provenance, the safe assumption is that it *could* be audit data.

Quinn's matrix has this as WARN (blocking at threshold). I argue it should be ERROR (always blocking). The reasoning: broad `except` with unknown provenance is *strictly worse* than broad `except` with known TIER_3 provenance (where SUPPRESS is correct because boundary handling is expected). If we can't distinguish the two, we must not treat them equivalently. WARN allows the finding to be filtered below the precision threshold, which means unknown-provenance broad `except` could slide through if the rule's earned threshold hasn't reached the level to block WARNs.

**Corpus implication:** All samples for this cell should be `true_positive` (ERROR verdict). The WARN→ERROR promotion adds 2-3 additional TP samples.

### Cell: (MIXED, any) x `hasattr` = FINDING

**Verdict: Correct, but incomplete.** `hasattr` is unconditionally banned per CLAUDE.md. The MIXED provenance doesn't change this — it's still a finding. But the scribe's matrix doesn't specify severity for `hasattr` x MIXED. It should be ERROR regardless of provenance or validation status. The ban is absolute, not provenance-dependent.

**Correction:** hasattr should be a single row: `(ANY, ANY) x hasattr = ERROR`. No cell-by-cell evaluation needed. The matrix should explicitly mark this as provenance-independent to prevent future confusion about whether MIXED or UNKNOWN might somehow soften the severity.

### Cell: (TIER_3, RAW) x "Reaches audit write" = BLOCK

**Verdict: Correct. No attack found.** Unvalidated external data reaching an audit write is the canonical ACF-I2 violation. This is the tool's highest-value detection. ERROR/BLOCK is the only correct severity.

### Summary of Matrix Corrections

| Cell | Consensus Severity | My Correction | Reason |
|------|--------------------|---------------|--------|
| (TIER_3, SV) x `.get()` | SUPPRESS | **INFO** | Cannot verify validator covers accessed field |
| (TIER_2, RAW) x `.get()` | ERROR | **VIOLATION (impossible state)** | TIER_2 data should never be RAW |
| (UNKNOWN, RAW) x broad except | WARN | **ERROR** | Unknown provenance + evidence destruction = assume worst |
| (ANY, ANY) x hasattr | per-cell | **ERROR (provenance-independent)** | Unconditional ban, no contextual softening |

---

## Attack 3: The Advisory Exit Code as Compliance Laundering

### The Attack

The proposed integration mapping: INFO/NOTE findings → exit 3 (advisory) → CI passes green → GitHub annotation at "notice" severity. The scribe frames this as the solution to Seren's "validated-not-verified" concern. I attack this as **compliance laundering** — the same binary cleansing problem shifted from the taint engine to the output layer.

**The compliance laundering loop:**

1. Agent generates code with an external API call
2. Agent wraps it in a `@validates_external` function containing `isinstance` check + `raise`
3. Data is now `(TIER_3, STRUCTURALLY_VALIDATED)`
4. `.get()` on this data → SUPPRESS (per current matrix consensus)
5. Data reaches audit write → INFO (advisory note)
6. CI exits 3 → **green build**
7. GitHub annotation appears as "notice" severity
8. Developer sees green build, skims notices, merges

This is *exactly* the binary cleansing compliance ritual that Seren identified in Round 1, displaced by one level. Instead of `tainted → passes validator → clean → no finding`, we have `tainted → passes validator → STRUCTURALLY_VALIDATED → INFO finding → advisory exit code → green build → merged`. The finding *technically exists* but has zero enforcement power. The validator stub is the same minimum-viable structural compliance. The human review displacement is identical. The only difference is that there's now a GitHub notice annotation that nobody reads.

**Evidence this will happen:** GitHub "notice" annotations are already systematically ignored in most codebases. They render as collapsed annotations below the diff, requiring manual expansion. In high-velocity agent-assisted development (the tool's primary use case), developers are reviewing 5-15 PRs per day. They do not expand collapsed annotations. They check: is the build green? Are the blocking annotations clear? Is the diff reasonable? A "notice" saying "external data from API reaches audit write via validator — semantic adequacy requires human review" is invisible in this workflow.

**The counterfactual test:** If INFO findings had been ERROR findings, would the developer have caught the inadequate validator? Yes — the build would be red, the developer would examine the finding, and they would either improve the validator or add an allowlist entry with a rationale. Either action involves human engagement with the data flow. INFO findings achieve neither.

### The Deeper Problem: Advisory Creates a Two-Class System

The advisory exit code creates an implicit two-class severity system:

- **Class A:** ERROR/WARN → exit 1 → blocks CI → gets fixed
- **Class B:** INFO → exit 3 → advisory → gets ignored

Class B is where all `(TIER_3, STRUCTURALLY_VALIDATED)` findings live. This is *all validated external data* — exactly the data Seren warned about. The compliance ritual concern was that validated external data would escape scrutiny. The advisory exit code *ensures* it escapes scrutiny by routing all validated-external findings to the non-blocking output channel.

If the roundtable's answer to "how do we prevent compliance laundering?" is "we emit findings that don't block the build," then the roundtable has not solved the problem — it has described the problem and labeled it a feature.

### What Would Actually Work

Three options, in order of preference:

**Option 1: INFO findings block in agent mode.**

The dual enforcement profile (human code vs. agent code) was in the original shared brief. Apply it here: INFO findings are advisory for human-authored code (the human is trusted to read notices) and blocking for agent-authored code (the agent will not read notices). This is architecturally consistent — the tool already distinguishes the two contexts — and it eliminates the compliance laundering loop specifically for the case where it matters most (agent-generated validators).

The `--stdin` mode (agent self-check) and agent-flagged CI runs exit 1 on INFO. Human CI runs exit 3. The agent is forced to produce validators that don't generate INFO findings — which means validators that cover the specific fields accessed downstream, not minimum-viable structural stubs. This creates selective pressure on validator quality in the exact context where Seren's compliance ritual operates.

**Option 2: INFO findings accumulate toward a threshold gate.**

Instead of per-finding blocking, INFO findings contribute to a rolling accumulation metric. When the ratio of INFO findings to total code changes exceeds a threshold (e.g., >30% of new data flows have INFO-level validator-adequacy notes), the build blocks with: "Validated-but-unverified data flow ratio exceeds threshold. N data flows require validator review." This is Seren's "attenuation-to-clean ratio" metric applied as a gate rather than a diagnostic.

This addresses the note-fatigue problem (individual notes are ignorable; a threshold breach is not) while preserving the per-finding advisory for cases below the threshold.

**Option 3: INFO findings have a mandatory review lifecycle.**

INFO findings generate allowlist-style entries that require explicit acknowledgment: "I reviewed the validator adequacy for this data flow." The acknowledgment has the same governance as allowlist entries (CODEOWNERS protection, expiry dates, reviewer identity). This makes the human review that Seren identified as essential into a *tracked obligation* rather than a voluntary notice-reading exercise.

This is the most heavyweight option, but it's the one that most directly addresses the compliance ritual: the validator stub satisfies the tool's structural check, but the INFO finding creates a review obligation that the validator stub *cannot* satisfy. The developer must engage with the data flow or the obligation accumulates.

### My Recommendation

**Option 1 for v0.1. Option 3 for v1.0.**

Option 1 is implementable within the existing architecture (the `--stdin` mode flag already exists), addresses the primary adversary (agent-generated code), and doesn't require new governance infrastructure. Option 3 is the correct long-term solution but requires the review lifecycle infrastructure that Gideon and Iris have been designing — it's a natural integration point for the grouped fingerprint governance model.

Option 2 is a fallback if Option 1 is rejected for policy reasons (some teams may refuse to block agent CI differently from human CI).

---

## Summary of Positions

| Item | My Attack | My Position |
|------|-----------|-------------|
| **Label set** | Concede to 2D model (10 states). Attack decorator-based assignment as self-declaration vulnerability. | Add mandatory decorator-consistency checker as first-pass rule. Promote MIXED at return-value level for mixed-provenance functions. |
| **Matrix cells** | Four cells have wrong severity. | (T3,SV) x .get() → INFO not SUPPRESS. (T2,RAW) impossible state. (UNK,RAW) x broad except → ERROR. hasattr → provenance-independent ERROR. |
| **Integration mapping** | Advisory exit code is compliance laundering — shifts the binary cleansing problem from taint engine to output layer. | INFO blocks in agent mode (Option 1). Advisory-only for human code. Differential enforcement eliminates the compliance loop for the primary adversary. |
