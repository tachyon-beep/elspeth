# Dependabot Automated Dependency Management

**Status:** ✅ Active with Auto-Merge for Security Patches
**Configuration:** `.github/dependabot.yml`
**Schedule:**
- **Security updates:** Created immediately when a GitHub Security Advisory is published (bypass weekly schedule)
- **Regular updates:** Weekly (Monday: Python, Tuesday: GitHub Actions, Wednesday: Docker)

---

## Overview

Dependabot automatically monitors dependencies for security vulnerabilities and new versions, creating pull requests when updates are available. This reduces manual maintenance burden while keeping the codebase secure and up-to-date.

**🚀 NEW: Automated Security Patches**

Security vulnerabilities are now automatically merged and deployed after passing all CI gates:
- ⚡ **Response Time:** CVE → Production image in <45 minutes
- 🔒 **Safety:** All CI gates must pass (tests, coverage, security scans)
- 📦 **Automation:** Auto-merge → version bump → image build → release

See: [`docs/operations/security-patch-automation.md`](./security-patch-automation.md) for complete details.

---

## What Gets Updated

### 1. Python Dependencies (pip)
- **Scope:** All packages in `pyproject.toml` and lockfiles
- **Schedule:** Every Monday at 9 AM UTC
- **Lockfiles Updated:**
  - `requirements.lock` (production)
  - `requirements-dev.lock` (development)
  - `requirements-azure.lock` (Azure ML)
  - `requirements-dev-azure.lock` (dev + Azure)

### 2. GitHub Actions
- **Scope:** All actions in `.github/workflows/*.yml`
- **Schedule:** Every Tuesday at 9 AM UTC
- **Maintains:** SHA pins and version comments

### 3. Docker Base Images
- **Scope:** Base images in `Dockerfile`
- **Schedule:** Every Wednesday at 9 AM UTC

---

## How It Works

### Weekly Update Flow

**Monday 9 AM UTC:**
1. Dependabot scans Python dependencies
2. Identifies available updates
3. Groups related packages (Azure SDK, testing tools, etc.)
4. Creates PRs with updated lockfiles
5. CI automatically runs on each PR

**Your Action:**
- Review PRs in GitHub UI
- Check CI results (all gates must pass)
- Review changelogs linked in PR description
- Approve and merge if safe

### Security Vulnerability Flow

**Any Time (no separate config block needed):**
1. GitHub Security Advisory published
2. Dependabot detects the vulnerability **immediately**, independent of the scheduled checks
3. Creates a **high-priority PR** that bypasses the weekly cadence
4. PR is labeled with "security" for easy identification

Note: You do not need a separate "security-only" update entry for the same `package-ecosystem` + `directory`. Dependabot will always open security PRs as soon as an advisory is available. Keeping a single weekly entry for `pip` avoids overlapping configuration errors.

**Your Action:**
- Review within 24 hours
- Merge after CI passes
- Consider emergency deployment if critical

---

## Dependency Grouping Strategy

To reduce PR noise, related packages are updated together:

| Group | Packages | Update Types |
|-------|----------|--------------|
| `azure-sdk` | `azure-*` | minor, patch |
| `testing` | `pytest*`, `*-mock`, `*-cov` | minor, patch |
| `data-stack` | pandas, scipy, matplotlib, seaborn | **patch only** |
| `security-tools` | bandit, semgrep, pip-audit, vulture | minor, patch |
| `dev-tools` | ruff, mypy, types-*, pip-tools | minor, patch |
| `stats-libs` | pingouin, statsmodels | minor, patch |
| `github-actions` | All actions | minor, patch |

**Rationale:**
- **Data stack** (pandas, scipy) uses patch-only to minimize breaking changes
- **Security tools** group ensures audit tooling stays current
- **GitHub Actions** all grouped to maintain consistent CI versions

---

## Reviewing Dependabot PRs

### Pre-Review Checklist

Before reviewing any Dependabot PR:

1. ✅ **CI Must Pass**
   - All tests passing (979/979+)
   - Coverage ≥80%
   - No ruff/mypy errors
   - Bandit/semgrep clean
   - pip-audit passes

2. ✅ **Check PR Description**
   - Review changelog links
   - Note breaking changes
   - Check compatibility notes

3. ✅ **Review Version Jump**
   - Patch update (2.3.3 → 2.3.4): Low risk ✅
   - Minor update (2.3.3 → 2.4.0): Medium risk ⚠️
   - Major update (2.3.3 → 3.0.0): High risk ⛔

### Approval Guidelines

#### ✅ Auto-Approve (Fast Path)

Safe to merge immediately if:
- Patch updates only
- All CI passes
- No breaking changes in changelog
- Part of established group (testing, security-tools)

**Example:**
```
PR: Bump testing group from 8.4.2 to 8.4.3
Changes: pytest 8.4.2 → 8.4.3, pytest-cov 7.0.0 → 7.0.1
CI: ✅ All checks passed
Action: Approve + Merge
```

#### ⚠️ Review Required (Standard Path)

Needs careful review if:
- Minor version updates
- Data stack updates (pandas, scipy)
- Azure SDK updates
- Multiple packages in one group

**Example:**
```
PR: Bump azure-sdk group from 1.25.1 to 1.26.0
Changes: azure-identity, azure-storage-blob, azure-search-documents
CI: ✅ All checks passed
Action: Review changelogs → Test locally → Approve
```

#### ⛔ Deep Investigation (Slow Path)

Requires thorough testing if:
- Major version updates
- CI failures
- Known breaking changes
- Dependencies with complex interactions

**Example:**
```
PR: Bump pydantic from 2.12.2 to 3.0.0
CI: ❌ 15 tests failing (validation schema changes)
Action: Create feature branch → Fix compatibility → Update PR
```

### Handling CI Failures

If Dependabot PR fails CI:

1. **Check Failure Type:**
   - Test failures → Dependency incompatibility
   - Coverage drop → New code paths need tests
   - Linting errors → Code style changes needed
   - Security scan → New vulnerability or false positive

2. **Investigation Steps:**
   ```bash
   # Fetch PR branch
   gh pr checkout 123

   # Run tests locally
   python -m pytest -v --maxfail=5

   # Check specific failure
   python -m pytest tests/test_failing_module.py -vv

   # Review changelog for breaking changes
   # (linked in PR description)
   ```

3. **Resolution Options:**
   - **Simple fix:** Push fix to Dependabot branch
   - **Complex fix:** Close PR, create feature branch, fix issues
   - **Incompatibility:** Add to ignore list in `.github/dependabot.yml`
   - **False alarm:** Investigate further, may be test flakiness

---

## Common Scenarios

### Scenario 1: Conflicting PRs

**Situation:**
- PR #123: Updates `azure-identity` 1.25.1 → 1.26.0
- PR #124: Updates `azure-storage-blob` 12.27.0 → 12.28.0
- Both modify same lockfile

**Solution:**
1. Merge PR #123 first
2. Dependabot auto-rebases PR #124
3. Review and merge PR #124

### Scenario 2: Security Vulnerability

**Situation:**
- Monday morning: PR created for `requests` security update
- Labeled "security", bypasses weekly schedule

**Solution:**
1. **Immediate review** (within 4 hours)
2. Check CVE details in PR description
3. Verify fix version in changelog
4. Merge after CI passes
5. Consider emergency deployment

### Scenario 3: Major Version Update

**Situation:**
- PR: Bump `pandas` from 2.3.3 to 3.0.0
- Breaking changes expected

**Solution:**
1. **Do NOT auto-merge**
2. Create feature branch: `feature/pandas-3.0-migration`
3. Cherry-pick Dependabot's lockfile changes
4. Fix compatibility issues
5. Update tests
6. Full regression testing
7. Merge feature branch
8. Close Dependabot PR

### Scenario 4: Too Many PRs

**Situation:**
- 10 PRs open, overwhelming to review

**Solution:**
1. Prioritize security PRs first
2. Batch-review grouped PRs (same group = similar risk)
3. Consider adjusting `.github/dependabot.yml`:
   ```yaml
   open-pull-requests-limit: 5  # Reduce from 10
   ```

---

## Configuration Tuning

### Adjusting Update Frequency

**Current:** Weekly updates on weekdays

**Options:**

1. **More Frequent (High-Security Environments):**
   ```yaml
   schedule:
     interval: "daily"  # Check every day
   ```

2. **Less Frequent (Stable Production):**
   ```yaml
   schedule:
     interval: "monthly"  # Check first Monday of month
   ```

### Ignoring Problematic Dependencies

If a dependency causes repeated issues:

```yaml
# In .github/dependabot.yml
ignore:
  # Don't update to pandas 3.x (breaking changes not ready)
  - dependency-name: "pandas"
    update-types: ["version-update:semver-major"]

  # Completely ignore problematic-package
  - dependency-name: "problematic-package"
```

### Adding New Groups

To group additional related packages:

```yaml
groups:
  # Example: Group OpenAI and AI libraries
  ai-stack:
    patterns:
      - "openai"
      - "anthropic"
      - "langchain*"
    update-types:
      - "minor"
      - "patch"
```

---

## Integration with CI Security Gates

Dependabot PRs trigger **all** CI security checks:

### Secrets Scanning
- ✅ Gitleaks scans for exposed secrets
- ✅ SARIF report uploaded

### Static Analysis
- ✅ Bandit (HIGH severity + HIGH confidence)
- ✅ Semgrep (p/ci ruleset, ERROR-only)
- ✅ Vulture (dead code detection)
- ✅ Ruff + mypy (linting + type checking)

### Vulnerability Scanning
- ✅ pip-audit on updated lockfile
- ✅ Grype container scanning (if Docker changed)

### Test Coverage
- ✅ 979+ tests must pass
- ✅ Coverage ≥80% enforced
- ✅ Per-file coverage thresholds

**Result:** Dependabot PRs are as secure as manual PRs.

---

## Auto-Merge (Optional - Not Yet Enabled)

For teams comfortable with automation, patch updates can auto-merge:

### Setup (Future Enhancement)

Create `.github/workflows/dependabot-auto-merge.yml`:

```yaml
name: Dependabot Auto-Merge
on: pull_request

permissions:
  contents: write
  pull-requests: write

jobs:
  auto-merge:
    runs-on: ubuntu-latest
    if: github.actor == 'dependabot[bot]'

    steps:
      - name: Fetch metadata
        id: metadata
        uses: dependabot/fetch-metadata@v2
        with:
          github-token: "${{ secrets.GITHUB_TOKEN }}"

      - name: Auto-merge patch updates
        if: |
          steps.metadata.outputs.update-type == 'version-update:semver-patch' &&
          contains(github.event.pull_request.labels.*.name, 'python')
        run: |
          gh pr review --approve "$PR_URL"
          gh pr merge --auto --squash "$PR_URL"
        env:
          PR_URL: ${{ github.event.pull_request.html_url }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Safety:**
- Only patch updates (2.3.3 → 2.3.4)
- Only if all CI passes
- Only for specific labels (python, not docker)
- Manual review for minor/major updates

**Recommendation:** Run manual reviews for 4-6 weeks before enabling auto-merge.

---

## Monitoring and Metrics

### View Dependabot Status

**GitHub UI:**
1. Go to repository "Insights" tab
2. Click "Dependency graph"
3. Click "Dependabot"
4. View alert status, recent PRs, configuration

**GitHub CLI:**
```bash
# List open Dependabot PRs
gh pr list --label "dependencies"

# View Dependabot alerts
gh api /repos/:owner/:repo/dependabot/alerts
```

### Metrics to Track

**Weekly:**
- Number of PRs created
- Time to merge (target: <48 hours)
- CI pass rate (target: >90%)

**Monthly:**
- Dependencies updated
- Security vulnerabilities patched
- Time saved vs manual updates

---

## Troubleshooting

### Issue: Dependabot Not Creating PRs

**Symptoms:** Expected PR on Monday, but none created

**Diagnosis:**
1. Check Dependabot status: Insights > Dependency graph > Dependabot
2. Look for error messages
3. Check `.github/dependabot.yml` syntax

**Common Causes:**
- YAML syntax error
- `open-pull-requests-limit` reached
- All dependencies already up-to-date
- Dependabot disabled in repository settings

**Fix:**
```bash
# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('.github/dependabot.yml'))"

# Check for open PRs
gh pr list --label "dependencies"
```

### Issue: Dependabot PR Conflicts with Main

**Symptoms:** PR shows merge conflicts

**Solution:**
1. Dependabot auto-rebases within 24 hours
2. Or manually trigger rebase:
   ```bash
   # Comment on PR
   @dependabot rebase
   ```

### Issue: Lockfile Hash Mismatch

**Symptoms:** CI fails with "lockfile verification failed"

**Cause:** Dependabot regenerated lockfile differently than `pip-compile`

**Solution:**
```bash
# Fetch PR branch
gh pr checkout 123

# Regenerate lockfiles
pip-compile pyproject.toml -o requirements.lock
pip-compile pyproject.toml -o requirements-dev.lock --extra dev

# Push fix
git add requirements*.lock
git commit -m "fix: regenerate lockfiles with pip-compile"
git push
```

### Issue: Too Many Open PRs

**Symptoms:** 10+ open Dependabot PRs, can't keep up

**Solution 1 - Immediate:**
```bash
# Close non-critical PRs
gh pr list --label "dependencies" --json number,title
gh pr close 123 124 125  # Close patch updates, keep security
```

**Solution 2 - Long-term:**
Edit `.github/dependabot.yml`:
```yaml
open-pull-requests-limit: 5  # Reduce from 10
```

---

## Best Practices

### ✅ Do

- Review Dependabot PRs within 48 hours
- Prioritize security-labeled PRs
- Check CI status before merging
- Read changelogs for minor updates
- Keep `.github/dependabot.yml` documented
- Monitor weekly PR volume and adjust grouping

### ❌ Don't

- Auto-merge without CI passing
- Ignore security PRs for >24 hours
- Merge major updates without testing
- Disable Dependabot without team discussion
- Ignore repeated CI failures (investigate root cause)
- Merge conflicting PRs simultaneously

---

## Additional Resources

### Documentation
- [Dependabot Official Docs](https://docs.github.com/en/code-security/dependabot)
- [pip-tools Integration](https://github.com/dependabot/dependabot-core/blob/main/pip/README.md)
- Project lockfile docs: `docs/operations/lockfiles.md` (if exists)

### Related Files
- Configuration: `.github/dependabot.yml`
- Lockfiles: `requirements*.lock`
- CI workflow: `.github/workflows/ci.yml`
- Verification script: `scripts/verify_locked_install.py`

### Support
- Dependabot issues: GitHub Issues with label "dependabot"
- Security concerns: See `SECURITY.md`
- Team questions: Slack #elspeth-dev (if applicable)

---

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2025-10-21 | Initial Dependabot configuration | Claude Code |

---

**Status:** ✅ Production Ready
**Next Review:** 2025-11-21 (1 month after activation)
