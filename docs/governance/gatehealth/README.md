# Gate Health Oversight

These materials capture the operating rhythm for monitoring AIS quality gates
now that the pipeline emits coverage, SBOM, and vulnerability artefacts by
default. The intent is to provide lightweight governance that can be executed
by the Platform & Compliance team without code changes.

## Weekly Gate Review (15 minutes)

**Participants:** Platform Eng (chair), QA lead, Security lead.  
**Agenda:**

1. Review latest CI runs on `main`
   - Ensure `lint-and-test` job is green and artefacts are present:
     * `coverage-xml`
     * `sbom-json`
     * `pip-audit-report`
   - Confirm `secrets-scan` job passed (gitleaks).  
2. Check coverage trend
   - Target ≥ 85% line coverage (see `coverage.xml` in CI artefacts).  
   - Log any dips below target and create follow-up issues.  
3. Audit findings
   - Open `pip-audit.json`; ensure no vulnerabilities reported.  
   - If findings exist, file remediation tickets and track status.  
4. SBOM verification
   - Confirm `sbom.json` generated; spot-check metadata (component name/version).  
   - Upload SBOM to compliance store if required.  
5. Outstanding gate risks / action items
   - Capture action items in `docs/governance/gatehealth/minutes/`.

## Dashboard Checklist

Populate (or update) the shared dashboard each week with:

- Latest build status (link to CI run).  
- Coverage % from `coverage.xml`.  
- Date of last successful `make audit`.  
- Notes on SBOM storage location.  
- Open gate-related issues (link to tracker).

## Artifact Storage Guidance

- Retain the last four `sbom.json` and `pip-audit.json` artefacts in the
  compliance repo or approved document store.  
- Coverage reports can be rotated weekly; ensure metrics are captured
  before deletion.

## Escalation Rules

- Any failing gate blocks release until a Jira issue is logged and resolved.  
- Security Lead must sign off on vulnerability waivers.  
- Platform Eng to post a weekly summary in #ais-gates Slack channel.
