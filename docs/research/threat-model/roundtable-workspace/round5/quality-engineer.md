# Round 5 — Final Dissent and Commitment: Quinn (Quality Engineer)

## 1. Commitment

**I commit to the decided design.** Five provenance labels, two validation states, seven effective states, forty-nine matrix cells. I can build a test suite against this specification and sleep at night.

### On Embedded vs. Separate Validation

My Round 4 position was pragmatic, not principled. I argued that for v0.1's intra-function scope, `VALIDATED` as a provenance label is operationally equivalent to `TIER_3 x STRUCTURALLY_VALIDATED`. That's true — for v0.1, no test case distinguishes them. But the roundtable correctly identified that the 2D model is *structurally* correct (provenance is immutable; validation status evolves), and starting with the wrong abstraction creates migration debt when v1.0 adds inter-procedural analysis.

I was optimizing for fewer corpus cells. The roundtable optimized for conceptual integrity. They were right.

**One residual note:** The 7 effective states (collapsing validation as N/A for TIER_1, TIER_2, and MIXED) are load-bearing for corpus manageability. If a future rule makes validation status meaningful for internal data (e.g., "re-validated pipeline data"), the effective state space expands to 10 and the corpus grows by ~60 entries. This should be a deliberate decision, not an accidental one. I recommend the specification document explicitly state: *"Validation status is N/A for TIER_1, TIER_2, and MIXED in v0.1. Expanding validation to these provenances requires roundtable review."*

## 2. Minority Report: Embedded Validation (v0.1)

Filed for the record. Not a blocking concern.

**The case for embedded:** In intra-function analysis, validation only applies to TIER_3 data entering through `@validates_external`. The 2D model creates two states (UNKNOWN+RAW, UNKNOWN+STRUCTURALLY_VALIDATED) that are theoretically distinct but practically indistinguishable — if provenance is UNKNOWN, we don't know *what* was validated, so the validation status carries less information than it appears to. The embedded model avoids this by making validation a provenance transition (TIER_3 -> VALIDATED), which is what actually happens in the code.

**Why this doesn't block commitment:** The 2D model handles UNKNOWN+SV correctly in the matrix (INFO for most rules — advisory, low confidence). The corpus entries for these cells are small (2 per cell). The conceptual overhead exists but doesn't create false positives or false negatives. It creates 5 additional cells compared to my embedded model, costing ~12 corpus entries. That's an afternoon, not a sprint.

**The case is closed.** I won't revisit this.

## 3. Corpus Authoring Burden

### Hour Estimate

**16-24 hours of focused authoring time for the initial ~208-entry corpus.** Broken down:

| Category | Cells | Entries | Hours | Notes |
|----------|-------|---------|-------|-------|
| R3 `hasattr()` | 7 | ~7 | 1 | All ERROR, structurally identical — vary only the provenance decorator |
| R1/R2 `.get()`/`getattr()` | 14 | ~56 | 4-5 | Paired rules, many cells share structure |
| R4 Broad `except` | 7 | ~28 | 3-4 | Need realistic try/except blocks with different provenance contexts |
| R5 Data->audit | 7 | ~30 | 4-5 | Hardest — requires realistic audit write paths with taint flow |
| R6 `except: pass` | 7 | ~28 | 2-3 | Similar to R4 but simpler (pattern is more constrained) |
| R7 `isinstance()` | 7 | ~24 | 2-3 | Need polymorphic dispatch examples for TN cases |
| Cross-cutting review | — | — | 2-3 | Deduplication, adversarial edge cases, consistency check |
| **Total** | **49** | **~208** | **16-24** | |

**Key efficiency factor:** Many cells share structural templates. A `.get()` on TIER_1 and a `.get()` on TIER_2 differ only in the provenance decorator and the expected severity. Authoring is grid-filling, not creative writing. The R3 row is mechanical — 7 cells, all ERROR, copy-paste with decorator changes, 1 hour.

**The hard entries are R5 (data->audit).** These require realistic code where tainted data flows through variable assignments to a landscape recorder call. Each provenance needs a believable scenario: TIER_3+RAW data reaching `recorder.record_state()` looks different from UNKNOWN data reaching it. These entries are 10-15 lines each and require understanding the actual ELSPETH audit API. Budget 4-5 hours here.

**Maintenance cost:** ~2 entries per quarter from red-team evolution (Riven's evasion examples become corpus entries). Rule additions (new R8, R9) add 7 cells each (~28-35 entries, ~4-5 hours). The corpus is append-mostly — entries rarely change once written because they test Python syntax patterns, which are stable.

### Is This Realistic?

Yes. 16-24 hours is 2-3 focused days. The alternative — maintaining a flat list of ad-hoc test cases without the matrix structure — would be faster to start but impossible to audit for completeness. The matrix gives us a coverage map: every cell is either tested or visibly empty. That visibility is worth the upfront cost.

## 4. INFO Action-Rate Metric: Operational Definition

### What Is an "Action"?

An **action** is a code change within the same PR or subsequent 3 commits that modifies the code region identified by an INFO finding. Specifically:

| Qualifies as action | Does not qualify |
|---------------------|-----------------|
| Modifying the flagged line or its enclosing function | Modifying unrelated code in the same file |
| Adding a provenance annotation that changes the finding's severity | Adding an allowlist entry to suppress the finding |
| Refactoring the flagged pattern to eliminate the finding | Closing the PR without changes (abandon) |
| Adding a comment explaining why the pattern is acceptable (then suppressing) | Merging without addressing the finding |

**The critical distinction:** An allowlist suppression *without* a code change is not an action — it's a dismissal. An allowlist suppression *with* a code change (e.g., adding `@tier2_data` to resolve UNKNOWN provenance, which changes the finding from INFO to a different severity) is an action, because the developer engaged with the finding and changed the code.

### How Is It Measured?

**Measurement requires two data sources:**

1. **SARIF findings** with file paths, line ranges, and finding fingerprints (already specified in the integration mapping)
2. **Git diff correlation** — for each INFO finding in a merged PR's SARIF output, check whether the finding's file:line-range was modified in the merge commit or subsequent 3 commits on the target branch

**Implementation sketch:**

```
For each INFO finding F in SARIF output of PR #N:
  fingerprint = F.fingerprint
  file_path = F.location.file
  line_range = F.location.start_line .. F.location.end_line

  # Check merge commit
  if git_diff(PR_merge_commit) touches (file_path, line_range ± 5 lines):
    action_count += 1
    continue

  # Check subsequent 3 commits on target branch
  for commit in next_3_commits_after_merge(target_branch):
    if git_diff(commit) touches (file_path, line_range ± 5 lines):
      action_count += 1
      break

action_rate = action_count / total_info_findings
```

The `± 5 lines` tolerance accounts for line drift from other changes in the same PR. This is a heuristic — it will produce both false positives (unrelated change near the finding) and false negatives (refactoring that moves code far from original location). For a health metric (not a gate), this precision is acceptable.

### Graduation and Suppression Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| Action rate > 30% for a cell after 20+ observations | Promote cell to WARN | Developers are consistently acting on these findings — they've earned blocking status |
| Action rate < 5% for a cell after 50+ observations | Reclassify cell to SUPPRESS | Findings are noise — remove them |
| Action rate 5-30% | Hold at INFO | Insufficient evidence to reclassify |

**Observation minimums matter.** Promoting a cell to WARN after 3 observations and 2 actions (67% rate) is statistically meaningless. The thresholds above require enough data to be confident the rate is stable. For a team of 5-10 developers, 50 observations on a single cell may take 3-6 months — which aligns with the "6-month survival test" I proposed in Round 4.

## 5. Testability Assessment

### What the Corpus Covers

The golden corpus tests the **rule evaluation matrix** — for each (rule, effective-state) cell, the corpus provides code samples with known provenance and expected verdicts. This covers:

- **Provenance assignment:** Does the tool correctly label data from decorators, heuristic matches, and taint propagation?
- **Rule detection:** Does the tool correctly identify the syntactic pattern (`.get()`, `hasattr()`, broad `except`, etc.)?
- **Severity grading:** Does the tool emit the correct severity for the (rule, provenance) combination?
- **Verdict correctness:** Does a true_negative sample produce no finding? Does a true_positive sample produce a finding at the expected severity?

### What the Corpus Cannot Cover

Three testability gaps exist. None are blocking, but all should be documented in the specification.

**Gap 1: Taint propagation depth.** The corpus tests individual code patterns with explicit provenance annotations. It does not test multi-step taint propagation: `x = external_call()` -> `y = transform(x)` -> `z = y["field"]` -> `recorder.record(z)`. The tool must track provenance through assignments and function calls. This requires **integration tests** beyond the corpus — full-function or multi-function scenarios where provenance flows through 3+ assignment steps before reaching a rule trigger.

**Estimated gap:** ~15-20 integration test cases, structured by propagation depth (2-step, 3-step, cross-function for v1.0). These are separate from the corpus because they test the taint engine, not the rule matrix. Budget 4-6 hours of additional test authoring.

**Gap 2: Decorator-consistency checker.** Riven's decorator abuse attack (Round 4) identified that `@tier1_data` on a function calling `requests.get()` produces wrong provenance. The proposed decorator-consistency checker is a separate analysis pass. The corpus doesn't test it because it's not a rule — it's a meta-validation. This needs its own test suite: ~10 cases of correct decorator usage, ~10 cases of inconsistent decorators (external call under `@internal_data`, internal-only function under `@external_boundary`).

**Estimated gap:** ~20 test cases, 2-3 hours of authoring. Can be structured as a separate test file, not part of the golden corpus.

**Gap 3: MIXED provenance construction.** The corpus can test rules *applied to* MIXED data, but testing *how* data becomes MIXED requires taint engine scenarios where two differently-labelled values are assigned to the same container. The corpus entry would need to show: `container["a"] = tier1_value; container["b"] = tier3_value` and verify that `container` is labelled MIXED. This is a taint engine test, not a rule test.

**Estimated gap:** ~8-10 test cases for MIXED construction scenarios, 1-2 hours.

### Total Test Surface

| Component | Source | Entry Count | Hours |
|-----------|--------|-------------|-------|
| Rule evaluation matrix | Golden corpus | ~208 | 16-24 |
| Taint propagation depth | Integration tests | ~15-20 | 4-6 |
| Decorator consistency | Separate test suite | ~20 | 2-3 |
| MIXED construction | Taint engine tests | ~8-10 | 1-2 |
| **Total** | | **~251-258** | **23-35** |

The golden corpus covers the rule evaluation layer. The three gaps cover the taint engine layer. Together, they provide coverage of the full analysis pipeline. The gaps are not deficiencies in the design — they're additional test needs that the matrix-structured corpus correctly scopes out of its responsibility.

### Determinism Guarantee (Iris)

One final testability concern: Iris's determinism guarantee (byte-identical SARIF output for byte-identical input) is testable through the corpus by running each entry twice and diffing the output. This is cheap (~1 hour to add to the test harness) and catches non-determinism from dict ordering, set iteration, or timestamp injection. I endorse making this a mandatory property of the test suite, not an optional check.

## 6. Summary

| Item | Position |
|------|----------|
| Commit to decided design | **Yes** |
| Embedded validation minority report | Filed, closed, non-blocking |
| Corpus authoring burden | 16-24 hours, realistic for 2-3 focused days |
| INFO action-rate definition | Code change in flagged region within merge or next 3 commits |
| Testability gaps | 3 gaps totalling ~43-50 additional tests beyond corpus; none blocking |
| Blocking concerns | **None** |

The design is testable. The corpus is authorable. The metrics are measurable. Ship it.
