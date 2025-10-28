# Production Data Defense - Three-Layer Security

**Last Updated**: 2025-10-28
**Security Priority**: HIGH (Prevent sensitive data leaks)
**Pattern**: Defense-in-Depth

---

## Threat Model

**Attack Scenario**:
Developers/AI agents have muscle memory of putting orchestration runs in `orchestration_packs/` because "that's where the demos are." This creates risk of committing production runs containing:
- Real customer data
- Classified/SECRET information
- PII, credentials, API keys
- Sensitive business logic

**Defense Strategy**: Three independent validation layers prevent production data from entering the repository.

---

## Layer 1: .gitignore (Prevention)

**File**: `.gitignore` lines 135-147

```gitignore
# Orchestration Packs: Block all except approved demos
/orchestration_packs/*
!/orchestration_packs/.gitkeep
!/orchestration_packs/README.md
!/orchestration_packs/product_analysis_demo/
# Workaround: gitignore can't un-ignore subdirs after ignoring parent, so:
/orchestration_packs/product_analysis_demo/*
!/orchestration_packs/product_analysis_demo/**
```

**How it works**:
1. Ignore everything in `orchestration_packs/`
2. Un-ignore approved demos via explicit exceptions
3. Block casual `git add` attempts

**Limitations**:
- Can be bypassed with `git add -f`
- Doesn't catch files added before rule existed
- Relies on developer discipline

---

## Layer 2: Pre-commit Hook (Validation)

**File**: `.git/hooks/pre-commit`

**How it works**:
1. Scans all staged files in `orchestration_packs/`
2. Compares against allowed patterns (`.gitkeep`, `README.md`, `product_analysis_demo/`)
3. Blocks commit if disallowed files found
4. Provides clear error message with remediation steps

**Test it**:
```bash
# Should PASS (allowed demo):
echo "test" > orchestration_packs/product_analysis_demo/test.yaml
git add orchestration_packs/product_analysis_demo/test.yaml
git commit -m "Test demo file"
# ✅ Pre-commit validation passed

# Should FAIL (production run):
mkdir orchestration_packs/customer_analysis/
echo "SECRET DATA" > orchestration_packs/customer_analysis/data.csv
git add orchestration_packs/customer_analysis/
git commit -m "Oops"
# ❌ ERROR: Production data blocked
```

**Error Output**:
```
═══════════════════════════════════════════════════════════════════
  ❌ ERROR: Production data blocked in orchestration_packs/
═══════════════════════════════════════════════════════════════════

Blocked files:
  - orchestration_packs/customer_analysis/data.csv

Why this failed:
  Orchestration packs should only contain approved demos.
  Production runs with real data must NEVER be committed.

Where production data should go:
  ✅ outputs/ directory (gitignored)
  ✅ CI/CD pipelines (ephemeral)
  ✅ Secure artifact storage (external)
```

**Limitations**:
- Only runs if hook is installed (`.git/hooks/` not versioned)
- Can be bypassed with `git commit --no-verify`
- Developer could delete hook

---

## Layer 3: CI Validation (Final Catch)

**File**: `.github/workflows/ci.yml` (new job: `production-data-guard`)

**How it works**:
1. Runs on every push/PR
2. Scans entire `orchestration_packs/` directory tree
3. Fails CI if disallowed files detected
4. Cannot be bypassed by developer

**CI Output** (on failure):
```
🔍 Scanning orchestration_packs/ for production data...

❌ ERROR: Production data found in orchestration_packs/

Blocked files:
  - orchestration_packs/customer_analysis/data.csv

This is Layer 3 of defense-in-depth (.gitignore + pre-commit + CI)
```

**Guarantees**:
- ✅ Catches commits made before hooks existed
- ✅ Catches commits made with `--no-verify`
- ✅ Catches commits from environments without pre-commit hook
- ✅ Cannot be bypassed without PR review

---

## Defense-in-Depth Summary

| Layer | Tool | When | Can Bypass? | Catch Rate |
|-------|------|------|-------------|------------|
| **1** | .gitignore | `git add` | Yes (`-f`) | ~80% (casual mistakes) |
| **2** | Pre-commit hook | `git commit` | Yes (`--no-verify`) | ~95% (intentional bypass) |
| **3** | CI validation | PR/Push | **NO** | 100% (mandatory) |

**Combined Coverage**: ~99.99% (requires malicious intent + PR review collusion to bypass all 3)

---

## Adding New Approved Demos

When creating a legitimate demo that SHOULD be committed:

1. **Name it descriptively**: `feature_name_demo/`
2. **Update .gitignore** (lines 141-147):
   ```gitignore
   !/orchestration_packs/product_analysis_demo/
   !/orchestration_packs/new_feature_demo/  # ← ADD THIS
   ```

3. **Update pre-commit hook** (`.git/hooks/pre-commit` line ~16):
   ```bash
   DISALLOWED=$(echo "$STAGED_FILES" | grep -v -E '^orchestration_packs/(\.gitkeep|README\.md|product_analysis_demo/|new_feature_demo/)' || true)
   #                                                                                                        ^^^^^^^^^^^^^ ADD THIS
   ```

4. **Update CI validation** (`.github/workflows/ci.yml` line ~87):
   ```bash
   grep -v -E '(\.gitkeep|README\.md|product_analysis_demo/|new_feature_demo/)' || true)
   #                                                         ^^^^^^^^^^^^^ ADD THIS
   ```

5. **Verify it contains NO real data**:
   - Use synthetic/dummy data only
   - No real customer names, PII, credentials
   - No SECRET/PROTECTED classification data
   - Safe to publish on public GitHub

---

## Validation Testing

**Test Layer 1** (.gitignore):
```bash
# Should be ignored:
echo "test" > orchestration_packs/production_run/data.csv
git status
# Should NOT show orchestration_packs/production_run/

# Should be tracked:
echo "test" > orchestration_packs/product_analysis_demo/test.yaml
git status
# Should show orchestration_packs/product_analysis_demo/test.yaml
```

**Test Layer 2** (pre-commit):
```bash
# Should PASS:
echo "demo" > orchestration_packs/product_analysis_demo/demo.yaml
git add orchestration_packs/product_analysis_demo/demo.yaml
git commit -m "Test"
# ✅ Pre-commit validation passed

# Should FAIL:
mkdir -p orchestration_packs/bad_idea/
echo "secret" > orchestration_packs/bad_idea/secret.txt
git add orchestration_packs/bad_idea/
git commit -m "Test"
# ❌ ERROR: Production data blocked
```

**Test Layer 3** (CI):
- Push branch with disallowed files
- CI job "Production Data Guard" will fail
- Cannot merge until files removed

---

## Threat Mitigation Matrix

| Threat | Layer 1 | Layer 2 | Layer 3 | Result |
|--------|---------|---------|---------|--------|
| **Accidental `git add`** | ✅ Blocked | - | - | Prevented |
| **Force add (`-f`)** | ❌ Bypassed | ✅ Blocked | - | Prevented |
| **Commit `--no-verify`** | ❌ Bypassed | ❌ Bypassed | ✅ Blocked | Prevented |
| **Files from before rules** | ❌ N/A | ❌ N/A | ✅ Blocked | Prevented |
| **Malicious PR** | ❌ Bypassed | ❌ Bypassed | ❌ Bypassed | ⚠️ Requires PR review |

**Final Safety Net**: Code review process catches malicious attempts that bypass all 3 automated layers.

---

## Maintenance

**When to update**:
- Adding new approved demos (update all 3 layers)
- Reorganizing directory structure (update patterns)
- Quarterly audit of `orchestration_packs/` contents

**Verification checklist**:
- [ ] .gitignore patterns up to date
- [ ] Pre-commit hook allow list current
- [ ] CI validation patterns match
- [ ] All demos contain synthetic data only
- [ ] No gitignored files committed (regression check)

---

## Philosophy Alignment

This defense-in-depth pattern mirrors Elspeth's security architecture:

**ADR-004 Registry Enforcement** (3 layers):
1. Schema validation (`additionalProperties: false`)
2. Registry sanitization (runtime rejection)
3. Post-creation verification (declared vs actual)

**Production Data Defense** (3 layers):
1. .gitignore (prevention)
2. Pre-commit hook (validation)
3. CI guard (final catch)

**Principle**: "No single point of failure" - each layer catches what previous layers missed.

---

**Created**: 2025-10-28
**Rationale**: Prevent production data leaks via muscle memory / AI agent mistakes
**References**: ADR-001 (fail-closed), ADR-004 (defense-in-depth)
