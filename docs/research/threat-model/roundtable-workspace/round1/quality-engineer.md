# Round 1 — Opening Position: Quinn (Quality Engineer)

## Summary Position

The semantic boundary enforcer's correctness claim rests entirely on the quality of its test corpus and the rigour of its precision measurement. A tool that blocks CI must prove it is right before it earns that power — and the proof must be reproducible, adversarially evolved, and immune to the "tests pass therefore it works" fallacy. My central concern is **corpus–rule co-evolution**: without a disciplined lifecycle linking rule changes to corpus updates, we will ship a tool whose confidence is backed by stale evidence.

## Golden Corpus Design

### Structure: Labelled Snippet Pairs, Not Full Files

Each corpus entry should be a **self-contained Python snippet** (5–30 lines) with structured metadata. Full files add noise; the tool operates at intra-function granularity (v0.1), so the corpus should match the analysis unit.

```yaml
# corpus/R1/dict_get_on_typed_dataclass.yaml
id: R1-TP-001
rule: R1
verdict: true_positive
category: typed_internal_data
source: |
  @dataclass
  class AuditRecord:
      run_id: str
      status: str

  def check_status(record: AuditRecord) -> str:
      return record.__dict__.get("status", "unknown")  # Fabricates default
expected_findings:
  - line: 7
    rule: R1
    message_contains: "dict.get"
rationale: >
  .get() on a dataclass __dict__ hides missing attribute bugs.
  The dataclass contract guarantees 'status' exists; a default fabricates data.
```

### Size Per Rule

The brief proposes 3 TP + 2 TN minimum per rule. **This is too low for a blocking gate.** My recommendation:

| Sample type | Minimum per rule | Purpose |
|-------------|-----------------|---------|
| True Positive (clear) | 5 | Core detection confidence |
| True Positive (edge) | 3 | Boundary conditions (nested scopes, decorators, comprehensions) |
| True Negative (legitimate use) | 5 | Proves the rule doesn't fire on valid patterns |
| True Negative (near-miss) | 3 | Syntactically similar but semantically different — the hardest negatives |
| Adversarial evasion | 2+ | Red-team additions (initially empty, grows over time) |

That's **18 minimum per rule** to reach blocking status. For 7+ rules, that's ~126 corpus entries at launch. This sounds large, but each is a 5–30 line snippet with YAML metadata — the entire corpus is perhaps 3,000 lines of YAML.

### True Negative Design is Critical

The hardest test is a true negative that looks like a true positive. Examples:

```yaml
# corpus/R1/dict_get_at_trust_boundary.yaml
id: R1-TN-001
rule: R1
verdict: true_negative
category: trust_boundary
source: |
  def parse_api_response(raw: dict[str, Any]) -> str:
      # Tier 3 data — .get() with default is legitimate coercion
      return raw.get("status", "unknown")
expected_findings: []
rationale: >
  This is Tier 3 external data. .get() with a default is acceptable
  coercion at the trust boundary. The v0.1 tool cannot distinguish this
  from Tier 1/2 usage without taint analysis, so this TN tests the
  heuristic exclusion mechanism (e.g., function decorated with
  @external_boundary or parameter typed as raw dict).
```

This entry tests whether the tool's heuristics (decorator-based, naming-based, or type-annotation-based) correctly suppress R1 at trust boundaries. If the tool fires here, that's a **false positive** — and since most Python code is either at boundaries or near them, false positives here will dominate the finding volume.

### Near-Miss True Negatives

```yaml
# corpus/R4/broad_except_with_reraise.yaml
id: R4-TN-003
rule: R4
verdict: true_negative
category: near_miss
source: |
  try:
      result = external_api.fetch(url)
  except Exception as e:
      logger.error("API call failed", error=str(e))
      raise  # Re-raises — not swallowing
expected_findings: []
rationale: >
  Broad except with explicit re-raise is a logging pattern, not suppression.
  The tool must check for raise/raise-from within the except body.
```

## Precision Measurement

### The >95% Threshold is Correct — But the Volume Floor is Not

95% precision over 50 firings means ≤2.5 false positives. That's a reasonable confidence level for a blocking gate. However, **50 firings is too low** for rules that fire frequently. A rule that fires 500 times per scan with 95% precision still generates 25 false positives per CI run — that's ACF-D1 (review DoS) in action.

**Proposed dual threshold:**

| Metric | Threshold | Purpose |
|--------|-----------|---------|
| Precision | ≥95% over last 100 firings | Accuracy per firing |
| False positive rate per scan | ≤5 FPs per full-repo scan | Developer experience |

A rule that's 95% precise but fires 200 times on ELSPETH's codebase produces 10 FPs per scan — that rule should not block CI even though its precision is "high enough."

### Who Labels?

This is the governance question the brief partially answers with "temporal separation" but doesn't address for measurement. My proposal:

1. **Initial corpus labelling:** Done by the rule author + one reviewer who understands the trust model. Both must agree on verdict.
2. **Production labelling:** When a developer adds an allowlist entry, that is an implicit "false positive" label. When they fix their code instead, that's an implicit "true positive" label.
3. **Quarterly review:** Sample 20 allowlist entries. If >10% were added because the developer didn't understand the rule (not because the rule was wrong), that's a documentation problem, not a precision problem.

### Feedback Loop

```
Finding fires → Developer responds:
  ├── Fixes code       → TP (implicit)
  ├── Adds allowlist    → FP candidate (implicit, needs review)
  └── Disputes in PR    → Manual label required

Quarterly:
  - Sample allowlist additions
  - Reclassify: legitimate boundary use vs. "just make it go away"
  - Update precision measurement
  - Demote rules below threshold back to warning
```

## Self-Hosting Strategy

### The Bootstrap Problem

The tool uses `ast.parse()`, `json.loads()`, `yaml.safe_load()`, and reads files from disk — all external boundaries by its own heuristic list. The tool's own code **must** demonstrate the patterns it enforces.

Concrete requirements:

1. **The tool's own `ast.parse()` calls** wrap the call in try/except and validate the result before trusting it. This is correct — the file being analysed is external input (Tier 3). The tool should have `@external_boundary` or equivalent annotation on its file-reading functions.

2. **The tool's own YAML loading** (`yaml.safe_load()` for allowlists) is an external boundary. The tool should validate parsed YAML structure immediately, not carry raw dicts through helper functions.

3. **The tool's internal data structures** (Finding, Allowlist, etc.) should use direct attribute access, not `.get()`. This is already the case in the existing enforcer — `Finding` is a frozen dataclass.

4. **Self-hosting CI gate:** The tool must be in its own CI check that runs the tool against the tool's own source. If the tool can't pass its own rules, it can't ship. This is a `Makefile` target, not a test.

### Allowlist Entries for Self-Hosting

The tool will need allowlist entries for its own legitimate external boundary operations. These entries should be **separately tracked and count toward the tool's own FP rate**. If the tool needs more than ~5 allowlist entries for its own code, that's a signal the rules are poorly calibrated.

## Regression Testing: Snapshot-Based with Approval

### The Problem

When a rule changes, three things can happen to the finding set:

1. New findings appear (rule got stricter) — needs review
2. Findings disappear (rule got more lenient) — needs review
3. Findings change content (message, fingerprint) — may break allowlists

All three are **invisible without explicit tracking**.

### Solution: Deterministic Snapshot Testing

```
tests/
  golden_corpus/
    R1/
      R1-TP-001.yaml   # Individual snippet + expected findings
      R1-TN-001.yaml
    ...
  snapshots/
    full_scan_elspeth.snapshot.json   # Full scan of src/elspeth/ — finding set
```

**Two layers:**

1. **Corpus tests** (per-snippet): Each `.yaml` entry has `expected_findings`. Test runner parses the snippet, runs the tool, asserts exact match. This is the unit test layer.

2. **Full-scan snapshot** (integration): Run the tool against `src/elspeth/`, capture the entire finding set as a sorted JSON snapshot. Any change to the finding set requires explicit `--update-snapshot` with a commit message explaining why.

**Snapshot format (sorted, deterministic):**

```json
{
  "tool_version": "0.1.0",
  "scan_root": "src/elspeth",
  "finding_count": 47,
  "findings": [
    {
      "rule_id": "R1",
      "file_path": "core/config.py",
      "line": 142,
      "fingerprint": "a3b4c5..."
    }
  ]
}
```

The snapshot is checked into version control. CI fails if the snapshot doesn't match. This makes finding-set changes **reviewable in PRs** — a reviewer can see "this rule change added 12 new findings" and assess whether that's intended.

### Fingerprint Stability

Finding fingerprints must be deterministic and stable across:
- Different machines (no absolute paths in fingerprints)
- Different Python versions (AST node attributes may vary — test on 3.10, 3.11, 3.12)
- File moves (fingerprint should include content hash, not just file path)

The existing enforcer uses content-based fingerprints (`hashlib`), which is correct. Test this property explicitly: same snippet, different file paths → same fingerprint.

## Determinism Verification

**Byte-identical output on identical input** is testable:

```python
def test_deterministic_output():
    """Run the tool twice on the same input, assert identical SARIF output."""
    result1 = run_tool(src_dir="src/elspeth")
    result2 = run_tool(src_dir="src/elspeth")
    assert result1 == result2  # Byte comparison on SARIF JSON
```

**Risks to determinism:**

| Risk | Mitigation |
|------|-----------|
| File system ordering (`os.walk`) | Sort file list before processing |
| Dict ordering (Python 3.7+) | Guaranteed insertion-order, but verify SARIF output is sorted |
| Timestamps in output | SARIF allows `startTimeUtc` — exclude from comparison or use frozen clock |
| Hash randomization (`PYTHONHASHSEED`) | Run determinism test with `PYTHONHASHSEED=random` explicitly |

The determinism test should run in CI with `PYTHONHASHSEED=random` to catch any accidental dependence on hash ordering.

## Adversarial Corpus Evolution

### Lifecycle

```
Red-teamer finds evasion pattern
  → Creates corpus entry with verdict: "false_negative"
  → Opens issue: "Rule Rn fails to detect pattern X"
  → Entry added to corpus (test fails — expected)

Rule author fixes rule
  → Corpus entry now passes
  → Rule author checks for new false positives from the fix
  → If FP rate stays within threshold: merge
  → If FP rate increases: negotiate with red-teamer on scope

Corpus entry becomes permanent regression test
```

**Key invariant:** The adversarial corpus is **append-only** for false negatives. Once a false-negative entry is added, it stays forever. The rule must detect it in all future versions. Removing a corpus entry requires the same review rigour as adding an allowlist entry.

### Cross-Rule Adversarial Entries

Some evasion patterns exploit rule interactions — e.g., wrapping `.get()` inside a validated function that *looks* like it has control flow but doesn't actually validate. These entries should be tagged with all relevant rules and tested against the full rule set, not individual rules.

## Testing Risks: Where False Confidence Will Emerge

### Risk 1: Corpus Covers the Easy Cases

The most dangerous failure mode is a corpus that's 100% green but only tests patterns the tool was designed to catch. The hard cases — the ones that actually appear in agentic code — will be slightly different from the corpus entries.

**Mitigation:** Require that at least 30% of TP corpus entries come from **real code observed in ELSPETH PRs**, not synthetic examples. The existing tier model enforcer catches 1-2 violations per day — mine those for corpus entries.

### Risk 2: Self-Hosting Passes Because the Tool's Code is Simple

The tool itself is straightforward AST-walking code. It doesn't have complex trust boundaries, doesn't handle user data in complex ways, and doesn't make external API calls beyond reading files. If it passes its own rules easily, that proves nothing about the rules' behaviour on complex application code.

**Mitigation:** Self-hosting is a necessary but insufficient gate. The real test is the full-scan snapshot against ELSPETH's `src/elspeth/` — which has transforms making LLM API calls, sources parsing CSVs, landscape code touching audit databases, and all three trust tiers in active use.

### Risk 3: Precision Measurement Games

If developers learn that adding allowlist entries is tracked as "FP", they'll fix their code even when the finding is wrong — to avoid being counted as a false positive source. This corrupts the measurement.

**Mitigation:** Allowlist additions should be reviewed but **not penalised**. The precision measurement should use the quarterly sample review, not the implicit label from developer behaviour. Track both metrics separately: "developer response" (noisy signal) and "expert review" (clean signal).

### Risk 4: Snapshot Rot

If the full-scan snapshot is updated without meaningful review ("just update it to make CI green"), it becomes worthless. This is the same failure mode as `pytest --snapshot-update` in UI testing.

**Mitigation:** Snapshot updates require a **separate commit** from the rule change (temporal separation, same principle as manifest changes). The PR diff shows exactly which findings changed. CI enforces that the snapshot commit has no code changes.
