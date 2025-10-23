# Security Patch Automation

**Status:** ✅ Active
**Owner:** DevOps / Security Team
**Last Updated:** 2025-10-21

---

## Overview

Elspeth implements **automated security patch management** to minimize vulnerability exposure windows while maintaining comprehensive safety controls. Security patches are automatically merged and deployed after passing all CI gates.

**Key Principle:** Speed + Safety = Automated patching with rigorous testing

---

## How It Works

### 1. Security Vulnerability Detection (Daily)

**Schedule:** Every day at 00:00 UTC

```yaml
# Dependabot checks for security updates daily
schedule:
  interval: "daily"
  time: "00:00"
```

**What Happens:**
1. Dependabot scans all Python dependencies
2. Checks GitHub Security Advisories (GHSA)
3. Checks CVE databases
4. If vulnerability found → Creates PR immediately

**Labels Applied:**
- `dependencies`
- `security`
- `auto-merge-enabled`
- `priority-critical`

### 2. Automated CI Validation

When security PR is created, **all CI gates run automatically**:

#### Required Gates (ALL must pass):

| Gate | Purpose | Failure Action |
|------|---------|----------------|
| **Tests** | 979+ tests must pass | Block auto-merge |
| **Coverage** | ≥80% line coverage | Block auto-merge |
| **Ruff** | Code formatting/linting | Block auto-merge |
| **Mypy** | Type checking | Block auto-merge |
| **Bandit** | Security static analysis | Block auto-merge |
| **Semgrep** | Security pattern matching | Block auto-merge |
| **Vulture** | Dead code detection | Block auto-merge |
| **pip-audit** | Vulnerability scanning | Block auto-merge |
| **Dependency Review** | License + supply chain | Block auto-merge |

**Estimated CI Runtime:** ~15-20 minutes

### 3. Auto-Merge Decision (After CI Passes)

**Workflow:** `.github/workflows/dependabot-auto-merge.yml`

**Safety Checks:**
```yaml
# Only auto-merge if ALL conditions are true:
- github.actor == 'dependabot[bot]'
- contains(labels, 'security')
- update-type == 'semver-patch' OR 'semver-minor'
- All CI checks passed
- No 'hold' label present
```

**Decision Tree:**
```
Security PR Created
    ↓
Is it from Dependabot? ──NO──> Manual review required
    ↓ YES
Has 'security' label? ──NO──> Manual review required
    ↓ YES
CI passed? ──NO──> Manual review required
    ↓ YES
Is patch/minor? ──NO──> Manual review required (major version)
    ↓ YES
Has 'hold' label? ──YES──> Manual review required
    ↓ NO
✅ AUTO-MERGE
```

### 4. Automated Approval & Merge

**Actions Taken:**
1. **Add comment** with audit trail
2. **Approve PR** with automated approval
3. **Enable auto-merge** (squash + delete branch)
4. **Wait for merge** to complete

**Example Comment:**
```markdown
🤖 **Automated Security Patch Approval**

This security patch has passed all CI gates and is approved for auto-merge:

✅ All tests passing
✅ Coverage ≥80%
✅ Security scans clean
✅ Update type: version-update:semver-patch

**Next Steps:**
1. Auto-merge this PR
2. Create new patch version tag
3. Trigger container image build
4. Publish signed image to GHCR

**Audit Trail:**
- PR: #123
- Dependency: pandas
- Previous version: 2.3.3
- New version: 2.3.4
- CVE: CVE-2024-12345
```

### 5. Automated Version Bump & Image Build

**After merge completes:**

1. **Determine new version:**
   - Get latest tag (e.g., `v0.1.5`)
   - Increment patch version (→ `v0.1.6`)

2. **Create version tag:**
   ```bash
   git tag -a v0.1.6 -m "Security patch release v0.1.6"
   git push origin v0.1.6
   ```

3. **Trigger image build:**
   - Tag push triggers `.github/workflows/publish.yml`
   - Builds Docker image: `ghcr.io/tachyon-beep/elspeth:v0.1.6`
   - Runs Grype vulnerability scan (fails on HIGH)
   - Signs image with Cosign (keyless OIDC)
   - Attests SBOM (CycloneDX format)
   - Publishes to GitHub Container Registry (GHCR)

4. **Create GitHub Release:**
   - Title: "Security Patch v0.1.6"
   - Notes: CVE details, audit trail, verification commands
   - Marked as latest release

**Total Time:** Security patch → Production image = **~30-45 minutes**

---

## Security Guarantees

### What Gets Auto-Merged

✅ **YES - Auto-merge enabled:**
- Security patches (CVSS any severity)
- Patch version updates (2.3.3 → 2.3.4)
- Minor version updates (2.3.3 → 2.4.0)
- All CI gates passed
- Lockfile integrity verified
- No 'hold' label

❌ **NO - Manual review required:**
- Major version updates (2.3.3 → 3.0.0)
- Any CI gate failure
- License compliance issues
- New HIGH/CRITICAL vulnerabilities introduced
- 'hold' label present
- Non-Dependabot PRs

### Safety Mechanisms

**1. Comprehensive Testing**
```
979+ tests covering:
- Unit tests (all modules)
- Integration tests (CLI, pipelines)
- Plugin tests (datasources, LLMs, sinks)
- Security tests (signing, sanitization)
```

**2. Coverage Enforcement**
```
Per-file coverage ≥80%
Overall coverage ~90%
Branch coverage ~78%
```

**3. Security Scanning**
```
- Bandit: Python security linting
- Semgrep: Pattern-based vulnerability detection
- pip-audit: Dependency vulnerability scanning
- Grype: Container image scanning
- Dependency Review: Supply chain analysis
```

**4. Lockfile Verification**
```bash
# Ensures dependency integrity
python scripts/verify_locked_install.py -r requirements-dev.lock
```

**5. Deterministic Builds**
```
- Hash-verified dependencies (--require-hashes)
- SHA-pinned GitHub Actions
- Reproducible lockfiles (pip-compile)
- Immutable base images (digest-pinned)
```

---

## Manual Override: Preventing Auto-Merge

If you need to prevent auto-merge of a security PR:

### Option 1: Add 'hold' Label

```bash
gh pr edit <PR-NUMBER> --add-label "hold"
```

**Effect:** Workflow detects 'hold' label and skips auto-merge

### Option 2: Close and Reopen as Manual PR

```bash
# Close Dependabot PR
gh pr close <PR-NUMBER>

# Create manual PR with same changes
git checkout -b security/manual-patch
# Cherry-pick changes
git push origin security/manual-patch
gh pr create --base main --head security/manual-patch
```

### Option 3: Disable Workflow Temporarily

```bash
# Disable auto-merge workflow in GitHub UI
# Settings → Actions → Workflows → dependabot-auto-merge.yml → Disable
```

**Remember to re-enable after manual merge!**

---

## Monitoring & Alerting

### GitHub UI

**View Security PRs:**
```
Repository → Pull Requests → Label: "security"
```

**Check Auto-Merge Status:**
```
PR → Checks tab → "Dependabot Auto-Merge Security Patches"
```

**View Built Images:**
```
Repository → Packages → elspeth
```

### GitHub CLI

```bash
# List security PRs
gh pr list --label "security"

# View specific security PR
gh pr view <PR-NUMBER>

# Check if PR is set to auto-merge
gh pr view <PR-NUMBER> --json autoMergeRequest

# List recent releases
gh release list --limit 10

# View container image tags
gh api /user/packages/container/elspeth/versions
```

### Email Notifications

**Configure notifications:**
```
GitHub Settings → Notifications → Dependabot alerts → Email
```

**Recommended:**
- Dependabot security updates: ✅ Email + Web
- Workflow failures: ✅ Email + Web
- PR merged: Optional (can be noisy)

---

## SLA & Response Times

### Security Patch Lifecycle

| Stage | Target Time | Measurement |
|-------|-------------|-------------|
| **Detection** | <24 hours | Dependabot checks daily |
| **PR Creation** | Immediate | Automated |
| **CI Validation** | 15-20 minutes | GitHub Actions |
| **Auto-Merge** | Immediate | After CI passes |
| **Image Build** | 10-15 minutes | publish.yml workflow |
| **Total (CVE → Image)** | **<45 minutes** | End-to-end |

**For CRITICAL vulnerabilities (CVSS 9.0-10.0):**
- Manual monitoring recommended
- Consider emergency manual merge if <45 min is too slow

### Regular Updates (Non-Security)

| Update Type | Review SLA | Auto-Merge |
|-------------|------------|------------|
| Patch (2.3.3 → 2.3.4) | 1 week | ❌ No |
| Minor (2.3.3 → 2.4.0) | 1 week | ❌ No |
| Major (2.3.3 → 3.0.0) | 2-4 weeks | ❌ No |

**All require manual approval** from team member.

---

## Rollback Procedures

### If Security Patch Causes Issues

**1. Immediate Rollback (Revert Image)**

```bash
# Identify working version
gh release list

# Rollback deployment to previous version
docker pull ghcr.io/tachyon-beep/elspeth:v0.1.5  # Previous working version

# Or pull 'latest' if it points to working version
docker pull ghcr.io/tachyon-beep/elspeth:latest
```

**2. Revert Git Commit**

```bash
# Find merge commit
git log --oneline --grep="security(deps)" | head -n1

# Revert merge
git revert -m 1 <merge-commit-sha>
git push origin main
```

**3. Create Rollback Tag**

```bash
# Tag previous working version as 'stable'
git tag -f stable v0.1.5
git push origin stable --force
```

**4. Disable Auto-Merge Temporarily**

```bash
# Disable workflow via GitHub UI while investigating
# Settings → Actions → Workflows → dependabot-auto-merge.yml → Disable
```

**5. Investigation & Fix**

```bash
# Identify root cause
# Fix compatibility issue
# Re-enable auto-merge
# Or add dependency to ignore list in dependabot.yml
```

---

## Audit Trail & Compliance

### What Gets Recorded

Every auto-merged security patch creates:

1. **Pull Request** with full diff and CI results
2. **Git Commit** with squashed changes
3. **Version Tag** with annotated message
4. **GitHub Release** with CVE details
5. **Container Image** with signature and SBOM
6. **Workflow Logs** (retained 90 days)

### Compliance Evidence

**For auditors:**
```bash
# Show all security patches in date range
gh pr list \
  --label "security" \
  --state "merged" \
  --search "merged:2024-01-01..2024-12-31"

# Show specific patch details
gh pr view <PR-NUMBER>

# Verify image signature
cosign verify \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp "https://github.com/tachyon-beep/elspeth/.*" \
  ghcr.io/tachyon-beep/elspeth:v0.1.6

# Extract SBOM
cosign verify-attestation \
  --type cyclonedx \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp "https://github.com/tachyon-beep/elspeth/.*" \
  ghcr.io/tachyon-beep/elspeth:v0.1.6 | jq
```

### Retention Policy

| Artifact | Retention | Location |
|----------|-----------|----------|
| Git commits | Permanent | GitHub repository |
| Pull requests | Permanent | GitHub |
| Workflow logs | 90 days | GitHub Actions |
| Container images | Permanent | GHCR (tagged versions) |
| SBOM attestations | Permanent | GHCR (attached to images) |
| Signatures | Permanent | Rekor transparency log |

---

## Regular Updates (Non-Security)

**Schedule:** Weekly on Monday 9 AM UTC

**Process:**
1. Dependabot creates PR (labeled `dependencies`, no `security`)
2. CI runs automatically
3. **Manual review required** (1 approver)
4. Manual merge via GitHub UI or CLI
5. No automated image build (tag created manually when ready)

**Review Guidelines:**
- Check changelog for breaking changes
- Review test results
- Consider impact on production
- Merge when convenient (no urgency)

---

## Configuration Files

### Dependabot Config
- **File:** `.github/dependabot.yml`
- **Security Pipeline:** Lines 7-44 (daily checks)
- **Regular Pipeline:** Lines 46-234 (weekly checks)

### Auto-Merge Workflow
- **File:** `.github/workflows/dependabot-auto-merge.yml`
- **Trigger:** PR opened/synchronized + CI completion
- **Permissions:** `contents: write`, `pull-requests: write`

### Dependency Review
- **File:** `.github/workflows/dependency-review.yml`
- **Trigger:** All pull requests
- **Blocks:** HIGH/CRITICAL vulnerabilities, license violations

### Image Publish
- **File:** `.github/workflows/publish.yml`
- **Trigger:** Version tag push (v*)
- **Output:** Signed image + SBOM attestation

---

## Troubleshooting

### Issue: Auto-Merge Not Triggering

**Symptoms:** Security PR created but not auto-merging

**Checks:**
```bash
# 1. Verify PR has correct labels
gh pr view <PR-NUMBER> --json labels

# Expected: "security", "auto-merge-enabled"

# 2. Check CI status
gh pr checks <PR-NUMBER>

# All checks must be green

# 3. Verify workflow ran
gh run list --workflow=dependabot-auto-merge.yml --limit 5

# 4. Check for 'hold' label
gh pr view <PR-NUMBER> --json labels | grep hold
```

**Common Causes:**
- CI still running (wait for completion)
- CI failed (fix issues, rerun)
- Major version update (requires manual review)
- 'hold' label present (remove to enable)
- Workflow disabled (check Actions settings)

### Issue: Image Build Failed

**Symptoms:** Tag created but no image published

**Checks:**
```bash
# Check publish workflow status
gh run list --workflow=publish.yml --limit 5

# View specific run
gh run view <RUN-ID>

# Check for Grype failures (vulnerability scan)
gh run view <RUN-ID> --log | grep -i grype
```

**Common Causes:**
- HIGH/CRITICAL vulnerability in base image
- Docker build failure
- Cosign signing error
- GHCR authentication issue

**Resolution:**
- Review workflow logs
- Fix underlying issue
- Retag to retry: `git tag -f v0.1.6 && git push origin v0.1.6 --force`

### Issue: False Positive Vulnerability

**Symptoms:** Grype blocks image build for known false positive

**Resolution:**
```yaml
# Add to .grype.yaml (create if doesn't exist)
ignore:
  - vulnerability: CVE-2024-12345
    fix-state: not-fixed
    reason: "False positive - not applicable to our use case"
    expiration: "2025-12-31"
```

---

## Future Enhancements

**Planned:**
- [ ] Canary deployments (auto-deploy to staging)
- [ ] Prometheus metrics for patch lifecycle
- [ ] Slack notifications for security patches
- [ ] Auto-rollback on deployment failures
- [ ] Security patch dashboard (Grafana)

**Under Consideration:**
- [ ] Multi-environment promotion pipeline
- [ ] Automated regression testing in staging
- [ ] Blue/green deployments
- [ ] Integration with vulnerability management platform

---

## Related Documentation

- Main Dependabot docs: `docs/operations/dependabot.md`
- Security policy: `SECURITY.md`
- CI workflow: `.github/workflows/ci.yml`
- Container signing: `README.md` (Container Signing section)
- Patch management SLA: `docs/security/patch-management-sla.md` (to be created)

---

## Contact & Support

**For questions:**
- Review process: GitHub Issues with label `dependabot`
- Security concerns: See `SECURITY.md`
- Workflow issues: GitHub Actions logs

**Emergency contacts:**
- Security incidents: [Follow incident response plan]
- Production issues: [On-call rotation]

---

**Last Reviewed:** 2025-10-21
**Next Review:** 2025-11-21 (monthly)
