# Round 1 — Opening Position: Iris (Integration Engineer)

## Summary Position

The semantic boundary enforcer must survive three deployment contexts — pre-commit hook (sub-2s wall clock), CI gate (full project under 10s), and agent self-check (stdin streaming, sub-1s per file) — without any of them becoming the reason teams disable the tool. The current `enforce_tier_model.py` runs 244 files in 0.85s using stdlib `ast`; the enhanced tool must stay within 2× of that budget despite adding taint analysis. I propose a `strict` CLI with three subcommands (`check`, `manifest`, `init`), SARIF-native output, TOML configuration embedded in `pyproject.toml`, and an incremental analysis mode keyed on file content hashes to make pre-commit hooks viable at scale.

## CLI Design

### Commands

```
strict check [paths...]              # Analyse files, exit 0/1/2
strict check --stdin                 # Read single file from stdin (agent mode)
strict check --sarif                 # Output SARIF JSON instead of human text
strict check --changed-only          # Only analyse git-dirty files (pre-commit)
strict check --baseline .strict-baseline.json  # Suppress known findings
strict manifest show                 # Display current trust topology
strict manifest add-exception        # Interactive exception workflow
strict manifest validate             # Check manifest internal consistency
strict init                          # Generate starter manifest from codebase scan
```

### Exit Codes

| Code | Meaning | CI interpretation |
|------|---------|-------------------|
| 0 | No findings (or all suppressed) | Pass |
| 1 | Blocking findings present | Fail gate |
| 2 | Tool error (parse failure, bad config) | Fail gate (don't silently pass on crash) |
| 3 | Advisory findings only (non-blocking) | Pass with annotations |

Exit code 2 is critical — a broken tool must never silently pass the gate. This matches `ruff`'s convention and is the #1 lesson from the existing enforcer: if the tool itself fails, that's a gate failure, not a pass.

### Agent Self-Check (`--stdin` mode)

```bash
cat src/elspeth/engine/processor.py | strict check --stdin --filename src/elspeth/engine/processor.py
```

The `--filename` flag provides path context for rule evaluation (layer detection, manifest lookup) without requiring the file to exist on disk. This is the mode AI agents use for self-checking generated code before writing it. Requirements:

- Must process a single file in <500ms (agents call this per-file in a loop)
- Must not require filesystem access beyond reading the manifest
- Exit codes are the same; agents parse exit code, not output text
- `--sarif` works with `--stdin` for structured consumption

### Human-Readable Output (default)

```
src/elspeth/plugins/transforms/llm.py:47:12  SBE-T02  .get() with default on Tier 2 data
  │ response_data.get("classification", "unknown")
  │                                      ^^^^^^^^^
  │ This fabricates a value when the field is missing. On Tier 2 data,
  │ missing fields indicate an upstream plugin bug — crash, don't mask.
  ╰─ To suppress: strict manifest add-exception SBE-T02 a1b2c3d4

2 findings (1 blocking, 1 advisory)
```

The inline fix suggestion (`strict manifest add-exception ...` with the fingerprint) is deliberate — it makes the suppression workflow a copy-paste operation, reducing friction to the point where developers add proper exceptions rather than disabling the tool.

## Integration Architecture

### Pre-Commit Hook

```yaml
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: strict-boundary-check
      name: Semantic Boundary Check
      entry: .venv/bin/strict check --changed-only --exclude "**/__pycache__/*"
      language: system
      types: [python]
      pass_filenames: false
```

**Why `--changed-only` instead of `pass_filenames`:** The tool needs to load the manifest and build a file-level symbol table regardless. With `--changed-only`, it:

1. Runs `git diff --name-only --cached` internally to get staged Python files
2. Loads the manifest once
3. Parses only changed files
4. Evaluates rules with full manifest context but partial file coverage

This is faster than `pass_filenames: true` because it avoids the shell argument overhead for many files and allows the tool to batch its own work. It's faster than the current `pass_filenames: false` pattern because it doesn't parse unchanged files.

**Performance budget:** Pre-commit must complete in <2s for the common case (1-5 changed files). The current enforcer does 244 files in 0.85s, so per-file AST parse + rule evaluation is ~3.5ms. Even with taint analysis doubling the per-file cost to ~7ms, 5 files = 35ms plus ~200ms manifest loading overhead = well under budget.

**Critical concern: the full-codebase pre-commit pattern.** ELSPETH currently runs ALL hooks with `pass_filenames: false`, scanning the entire codebase on every commit. This works at 244 files (0.85s for the enforcer, ~5s total hook chain). At 500+ files, the hook chain will exceed the psychological 10s threshold where developers start `--no-verify`. The semantic boundary enforcer should NOT follow this pattern — it should demonstrate the `--changed-only` approach that the other hooks should eventually adopt.

### CI Gate (GitHub Actions)

```yaml
- name: Semantic boundary check
  run: strict check src/ --sarif --output strict-results.sarif
  continue-on-error: false

- name: Upload SARIF
  if: always()
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: strict-results.sarif
```

CI runs the full scan (`src/` with no `--changed-only`). This is the authoritative check. The pre-commit hook is a fast-feedback approximation; CI is the source of truth.

**Manifest temporal separation in CI:** The brief specifies that manifest changes (adding exceptions) must be in a prior commit. In CI, this is enforced by:

```bash
# Check if strict.toml changed in the same commit as code changes
MANIFEST_CHANGED=$(git diff --name-only HEAD~1 -- pyproject.toml | grep -c "tool.strict" || true)
CODE_CHANGED=$(git diff --name-only HEAD~1 -- "*.py" | wc -l)
if [ "$MANIFEST_CHANGED" -gt 0 ] && [ "$CODE_CHANGED" -gt 0 ]; then
  echo "::error::Manifest changes must be in a separate commit from code changes"
  exit 1
fi
```

This is a separate CI step, not built into the tool itself. The tool checks exceptions; CI checks temporal separation. Separation of concerns — the tool doesn't need git awareness.

**However, this check has an edge case:** squash-merge workflows collapse the separation. For squash-merge repos, the CI check should compare against the PR base rather than HEAD~1:

```bash
git diff --name-only origin/${{ github.base_ref }}...HEAD
```

### Agent Self-Check Integration

Agents pipe generated code through `--stdin` before writing files:

```python
import subprocess

result = subprocess.run(
    ["strict", "check", "--stdin", "--filename", target_path, "--sarif"],
    input=generated_code.encode(),
    capture_output=True,
)
if result.returncode == 1:
    findings = json.loads(result.stdout)
    # Feed findings back into agent's context for self-correction
```

This creates a feedback loop: agent generates code → `strict` catches boundary violations → agent revises. The `--sarif` output gives the agent structured data to reason about, not prose to parse.

## SARIF Output Design

### Field Mapping

```json
{
  "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json",
  "version": "2.1.0",
  "runs": [{
    "tool": {
      "driver": {
        "name": "strict",
        "version": "0.1.0",
        "informationUri": "https://github.com/...",
        "rules": [{
          "id": "SBE-T02",
          "name": "DefaultOnTrustedData",
          "shortDescription": { "text": ".get() with default on Tier 2 data" },
          "fullDescription": { "text": "..." },
          "defaultConfiguration": { "level": "error" },
          "properties": {
            "trustTier": "tier2",
            "acfCode": "ACF-I1",
            "precision": "high",
            "tags": ["security", "trust-boundary", "data-integrity"]
          }
        }]
      }
    },
    "results": [{
      "ruleId": "SBE-T02",
      "level": "error",
      "message": { "text": ".get() with default 'unknown' on Tier 2 data fabricates values" },
      "locations": [{
        "physicalLocation": {
          "artifactLocation": { "uri": "src/elspeth/plugins/transforms/llm.py" },
          "region": { "startLine": 47, "startColumn": 12, "endColumn": 52 }
        }
      }],
      "fingerprints": {
        "strict/v1": "a1b2c3d4e5f6..."
      },
      "suppressions": []
    }]
  }]
}
```

### Key Design Decisions

**Fingerprints:** The `fingerprints` field uses the same hash scheme as the current enforcer (rule_id + file + symbol_context + code snippet). This enables SARIF-level baseline diffing — GitHub's code scanning can track findings across commits without the tool maintaining state.

**Suppressions:** Allowlisted findings include a `suppressions` array:

```json
"suppressions": [{
  "kind": "inSource",
  "justification": "Boundary validation occurs in calling function validate_api_response()",
  "properties": {
    "reviewer": "john",
    "expires": "2026-06-01",
    "manifestEntry": "SBE-T02/a1b2c3d4"
  }
}]
```

This maps directly to the existing allowlist expiry model. GitHub code scanning respects SARIF suppressions, so allowlisted findings don't create noise in PR annotations.

**Rule levels:** `"error"` for blocking rules, `"warning"` for advisory/graduated rules. This maps to CI exit codes (1 vs. 3) and to GitHub's annotation severity.

## Configuration Format

### `pyproject.toml` Section (not a separate file)

```toml
[tool.strict]
version = "0.1"

# Trust topology — which modules are at which tier
[tool.strict.topology]
tier1 = ["src/elspeth/core/landscape/", "src/elspeth/contracts/"]
tier2 = ["src/elspeth/engine/", "src/elspeth/plugins/"]
tier3_boundaries = ["src/elspeth/plugins/sources/", "src/elspeth/mcp/"]

# Boundary declarations (supplement to decorators)
[tool.strict.boundaries]
external = [
    "httpx.*",
    "requests.*",
    "litellm.*",
    "json.loads",         # When input is from external source
    "subprocess.run",
]
validators = []  # Discovered from @validates_external decorators

# Rule configuration
[tool.strict.rules]
# Rules start as advisory, promote to blocking after precision threshold
SBE-T01 = { level = "blocking", min_precision = 0.95 }
SBE-T02 = { level = "blocking" }
SBE-H01 = { level = "blocking" }  # hasattr — unconditionally blocked
SBE-E01 = { level = "advisory", promoted_after = "2026-06-01" }

# Enforcement profiles
[tool.strict.profiles]
agent = "blocking"   # All rules block for agent-generated code
human = "graduated"  # Rules follow their individual level setting

# Structured exceptions (replaces per-module YAML allowlist)
[[tool.strict.exceptions]]
rule = "SBE-T02"
fingerprint = "a1b2c3d4e5f6"
file = "src/elspeth/core/config.py"
reason = "Dynaconf settings use .get() by design — external library convention"
reviewer = "john"
expires = "2026-09-01"
```

**Why `pyproject.toml` instead of `strict.toml`:** One fewer file in the repo root. The Python ecosystem is converging on `pyproject.toml` for tool config (`[tool.ruff]`, `[tool.mypy]`, `[tool.pytest]`). A separate `strict.toml` adds cognitive overhead ("where's the config?") and requires CODEOWNERS for two files instead of one.

**Counter-argument:** The manifest needs CODEOWNERS protection, and protecting a section of `pyproject.toml` is harder than protecting a whole file. **Resolution:** Use `pyproject.toml` for topology and rule config, but put exceptions in a separate `strict-exceptions.toml` that gets its own CODEOWNERS entry. This splits "what the rules are" (rarely changes, low risk) from "what's suppressed" (changes frequently, needs review).

## Package Structure

```
strict-boundary-enforcer/
├── pyproject.toml
├── src/
│   └── strict/
│       ├── __init__.py
│       ├── __main__.py          # python -m strict
│       ├── cli.py               # Typer CLI
│       ├── analysis/
│       │   ├── collector.py     # Pass 1: symbol collection
│       │   ├── evaluator.py     # Pass 2: rule evaluation
│       │   └── taint.py         # Intra-function taint tracking
│       ├── rules/
│       │   ├── registry.py      # Rule registration
│       │   ├── trust_tier.py    # Tier-specific rules
│       │   └── boundary.py      # Boundary crossing rules
│       ├── output/
│       │   ├── sarif.py         # SARIF serialization
│       │   ├── human.py         # Human-readable output
│       │   └── baseline.py      # Baseline diffing
│       └── config/
│           ├── loader.py        # pyproject.toml + exceptions loading
│           └── manifest.py      # Trust topology model
```

**Entry points:**

```toml
[project.scripts]
strict = "strict.cli:app"

[project.entry-points."pre_commit"]
strict-check = "strict.cli:pre_commit_entry"
```

**Dependencies:** Zero for core analysis (stdlib `ast` + `json` + `tomllib`). Optional `typer` for the CLI (fall back to `argparse` if not installed). Optional `tomli` backport for Python <3.11 (though the brief targets 3.12+, so this may be unnecessary).

**Actually — reconsider Typer.** The brief says zero external dependencies for core. If the CLI is part of "core," then `argparse` it is. Typer is a nice-to-have but adds a dependency. Proposal: `argparse` for the shipped CLI, with a `[cli]` extra that adds Typer for a richer experience. The `argparse` version covers 100% of functionality; Typer adds autocompletion and richer help text.

## Performance Budget

| Context | Target | Bottleneck | Mitigation |
|---------|--------|-----------|------------|
| Pre-commit (1-5 files) | <2s total | Manifest loading (~200ms) | Cache parsed manifest in `.strict-cache/` |
| Pre-commit (full scan) | <3s for 250 files | AST parsing (~3.5ms/file) | Incremental: hash-based skip of unchanged files |
| CI (full project) | <10s for 500 files | Rule evaluation with taint | Parallelize with `multiprocessing` if >100 files |
| Agent `--stdin` (1 file) | <500ms | Process startup (~150ms) | Consider `--server` mode for persistent process |
| SARIF serialization | <100ms for 100 findings | `json.dumps` | Negligible — stdlib JSON is fast enough |

**Measured baseline:** The current enforcer parses 244 files + evaluates pattern rules in 0.85s. That's ~3.5ms per file for AST parse + pattern matching. Taint analysis adds a second pass over the AST, roughly doubling per-file cost to ~7ms. For 244 files: ~1.7s, still under the 2s pre-commit budget for full scan.

**The real bottleneck is process startup, not analysis.** Python interpreter startup is ~50-100ms. Importing `ast` and `tomllib` adds ~20ms. For `--stdin` mode where agents call the tool per-file in a loop, this overhead dominates. Options:

1. **Batch mode:** `strict check file1.py file2.py file3.py` — one process, multiple files
2. **Server mode:** `strict server --socket /tmp/strict.sock` — persistent process, zero startup per check (future enhancement, not v0.1)

### Incremental Analysis

For pre-commit, maintain a `.strict-cache/manifest.json`:

```json
{
  "manifest_hash": "abc123",
  "files": {
    "src/elspeth/engine/processor.py": {
      "content_hash": "def456",
      "findings": [],
      "last_checked": "2026-03-08T10:00:00Z"
    }
  }
}
```

If the manifest hasn't changed and a file's content hash matches, skip analysis and replay cached findings. Cache invalidation is content-addressed, so it's always correct. The cache file goes in `.gitignore`.

## Integration Risks

### What Will Cause Teams to Disable This Tool

1. **False positives on legitimate `.get()` usage.** The #1 kill switch. If the tool flags `os.environ.get("VAR", "default")` or `argparse.Namespace.__dict__.get()`, developers will add `--no-verify` to muscle memory. The heuristic list must ship with comprehensive stdlib/common-library exclusions. **Mitigation:** Ship with a curated allowlist of known-safe `.get()` patterns (stdlib containers, environment variables, CLI argument parsing). Make it easy to extend.

2. **Pre-commit hook exceeding 3s.** Research shows pre-commit hooks above 3s get `--no-verify`'d at 10× the rate of sub-1s hooks. ELSPETH's current hook chain is already ~5-8s total (ruff + mypy + enforcer + contracts). Adding another 2s hook pushes toward developer revolt. **Mitigation:** `--changed-only` mode, incremental caching. Also: advocate for the other hooks to adopt incremental analysis.

3. **Manifest maintenance burden.** If every exception requires editing TOML, getting a reviewer, and making a separate commit, the friction will cause developers to just rewrite code to avoid the pattern — even when the pattern is correct. **Mitigation:** The `strict manifest add-exception` command must generate the TOML entry, open the file at the right location, and pre-fill the fingerprint. One command, one edit, one commit.

4. **Cryptic fingerprints in error messages.** The existing enforcer's fingerprints are SHA-based and opaque. Developers can't tell if a fingerprint is stale, moved, or applies to their code. **Mitigation:** Show the fingerprint in context (file:line + code snippet) in error messages, not just the hash.

5. **Incompatibility with squash-merge workflows.** The "manifest change in prior commit" rule is elegant in merge-commit repos but breaks in squash-merge repos where all PR commits collapse into one. **Mitigation:** The temporal separation check must be a separate CI script (not built into the tool) so teams can adapt it to their merge strategy.

6. **Agent feedback loop latency.** If `--stdin` mode takes >1s, agents will skip self-checking to meet response time expectations. The self-check only works if it's fast enough to be invisible. **Mitigation:** Strict 500ms budget for `--stdin`, with a future `--server` mode for persistent-process zero-startup checking.

### The Meta-Risk: Tool Proliferation

ELSPETH already runs 5 pre-commit hooks. Adding a 6th increases the probability of "just disable all of them." The semantic boundary enforcer should **replace** the existing `enforce_tier_model.py` hook, not supplement it. Migration path: v0.1 runs alongside the existing enforcer (both enabled, findings compared). v0.2 subsumes the existing enforcer's rules. v0.3 removes the old hook. At no point are both blocking simultaneously on the same rule.
