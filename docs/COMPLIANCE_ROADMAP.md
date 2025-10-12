# Compliance Roadmap & Accreditation Plan

This roadmap expands on the compliance uplift required for Elspeth, mapping documentation, tooling, and governance workstreams to accreditation expectations (e.g., ISM, Essential Eight, IRAP). It complements `FEATURE_ROADMAP.md` by focusing on evidence, policy, and assurance deliverables.

## 1. Objectives

1. Deliver an auditable documentation platform (Sphinx-based) capable of producing HTML/PDF evidence packages.
2. Automate security and compliance evidence collection (code scans, dependency audits, diagrams, test artefacts).
3. Assemble accreditation-ready artefacts (System Security Plan, control matrix, incident/change procedures, evidence bundles).
4. Align operations with agency expectations (support model, governance, change management).

## 2. Phased Timeline & Effort

| Phase | Duration | Key Outputs | Effort (FTE-weeks) | Roles |
|-------|----------|-------------|--------------------|-------|
| **Foundation** | Weeks 1–3 | Sphinx + MyST baseline, CI doc build, doc contribution guidelines | 6 | Tech writer (2), DevOps (1), Maintainer (0.5), Security analyst (0.5) |
| **Automation & Scanning** | Weeks 4–6 | Bandit + Semgrep + Safety in CI, doc linting hooks, diagram generation scripts | 5 | DevOps (2), Security engineer (1.5), Tech writer (1) |
| **Compliance Pack Build-out** | Weeks 7–10 | Threat models, DFDs, control matrix, System Security Plan skeleton, incident/change runbooks | 8 | Tech writer (3), Security/compliance analyst (3), Architect (2) |
| **Evidence & Formal Methods Pilot** | Weeks 11–14 | Evidence export tooling, accreditation annex templates, formal-methods spike (e.g., TLA+/Alloy for artifact pipeline) | 6 | Security engineer (2), Architect (2), Formal methods specialist (2) |
| **Operational Integration** | Weeks 15–18 | Release checklist updates, support handbook, governance charter, accreditation readiness review | 4 | Maintainer (1.5), Ops lead (1), Tech writer (1.5) |

_Total estimated: ~29 FTE-weeks over ~18 weeks. Adjust if formal methods are deferred (-2 FTE-weeks)._

## 3. Workstreams

### 3.1 Documentation Platform

- Migrate critical docs to Sphinx (architecture overview, configuration merge, security controls, plugin catalogue).
- Add MyST to retain Markdown authoring, with doc8/vale linting.
- Set up CI publishing (GitHub Pages/Read the Docs) with approval gates.
- Establish doc style guide, review checklist, and PR template.

### 3.2 Security Tooling & Evidence Automation

- Integrate Semgrep ruleset tailored to Essential Eight/ISM (map high severity to control IDs).
- Configure Bandit (policy tuning) and Safety/pip-audit for dependencies; store reports in evidence bucket.
- Automate pyreverse/pydeps diagram generation with curation scripts; archive outputs per release.
- Capture pytest coverage, Sonar/SAST, lint results as part of evidence bundle.

### 3.3 Accreditation Artefacts

- Compile control matrix mapping ISM controls to implementation (code, docs, tests, scans).
- Build System Security Plan template referencing Sphinx sections.
- Produce Incident Response Plan, Change Management Plan, Configuration Baseline, Backup/DR procedures.
- Prepare data flow diagrams (STRIDE-based) and threat models; link mitigations in `TRACEABILITY_MATRIX.md`.
- Assemble evidence export script (ZIP of docs PDFs, scan reports, coverage, signed manifests).

### 3.4 Formal Methods (Pilot)

- Identify high-risk component (e.g., security level propagation in artifact pipeline).
- Draft lightweight TLA+/Alloy specification verifying invariants (no downgrade of security level, dependable signing flow).
- Integrate output (spec, proofs) into accreditation annex; note whether to expand in future phases.

### 3.5 Operations & Governance

- Update release checklist to mandate doc rebuild, scan pass, evidence export, governance sign-off.
- Define support/incident escalation model (24/7 or best-effort as per agency SLA).
- Document change-management workflow (CAB, approval gates, rollback policy).
- Create OSS governance charter (steering committee, CODEOWNERS, decision process, plugin certification criteria).

### 3.6 Evidence Management

- Provision secure artifact storage (AU-region S3/Azure Blob) with access controls and retention policy.
- Version evidence bundles per release; automate checksums and signed manifests.
- Maintain index describing each evidence artifact (source, timestamp, control mapping).

## 4. Dependencies & Risks

- **Staffing**: Requires dedicated tech writer and security analyst; formal methods need specialist time.
- **Tooling Complexity**: Diagram generation and Semgrep tuning may require multiple iterations to reduce noise.
- **Governance Buy-in**: Ensure agency leadership endorses cadence and documentation expectations.
- **Evidence Storage**: Must comply with agency data handling policies (classification, retention). Plan for backups and tamper detection.

## 5. Success Metrics

- Documentation build success rate == 100% (warnings treated as errors).
- Security scans (Bandit, Semgrep, Safety) integrated with CI; high-severity issues triaged within SLA.
- Control matrix coverage: 100% of scoped ISM controls mapped to artefacts.
- Evidence bundles produced for each release, signed & archived.
- Accreditation pre-assessment yields only minor documentation gaps.
- Team engagement: contributions to docs from multiple roles, tracked via commit analytics.

## 6. Immediate Actions

1. Kick off Sphinx prototype (import architecture docs + README) and validate CI publishing path.
2. Confirm compliance frameworks (ISM, Essential Eight, IRAP) with agency security lead; align control matrix taxonomy.
3. Provision secure storage for evidence artefacts with IAM/ACLs and retention policy.
4. Draft Semgrep/Bandit rule tuning backlog; start with advisory severity before gating builds.
5. Schedule regular roadmap reviews (fortnightly) with development, security, and operations stakeholders.

## 7. Review Cadence

- Revisit this roadmap quarterly, updating timelines, completion status, and new accreditation requirements.
- Publish status reports to the agency steering group, highlighting completed artefacts, outstanding gaps, and resourcing needs.
