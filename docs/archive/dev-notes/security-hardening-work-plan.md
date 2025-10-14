# Security Hardening Work Plan (Archive & Status)

This note archives the ISS/IRAP-oriented security work packages previously tracked in `external/work_plan.md` and `external/WP1.md`. It records which actions are complete and which remain on the compliance roadmap.

## Status Summary (April 2024)

| Work Package | Focus | Status | Notes / Next Steps |
|--------------|-------|--------|---------------------|
| **WP1 – Spreadsheet/CSV Output Mitigation** | Escape formula-triggering characters in CSV/Excel outputs. | ✅ Delivered (Oct 2023) | Sanitisation helper lives in `plugins/outputs/_sanitize.py`; manifests record guard settings; compatibility matrix in `docs/notes/sanitization_compat.md`. |
| **WP2 – Repository Sink Logging & Credential Guidance** | Redact repo sink logs; document token scopes. | ⏳ In progress | Adjust logging once structured logging (WP8) lands; add guidance to compliance docs. |
| **WP3 – Signed Artifact Key Handling** | Modernise key logging/messages and document storage/rotation. | ⏳ In progress | Update signed sink warnings; fold guidance into compliance roadmap. |
| **WP4 – Expanded Validation & Scenario Coverage** | Broaden config validation and scenarios. | ⏳ Backlog | Add tests for security-level downgrades, https enforcement, repo dry-run scenario. |
| **WP5 – Operational Hardening Checklist** | Ops-facing security checklist. | ⏳ Backlog | Should live in compliance roadmap + docs/security_checklist.md (to be created). |
| **WP6 – Config Guardrails & Secure Mode** | Fail-closed “secure mode” validation. | ⏳ Backlog | Integrate with compliance roadmap Phase 2/3. |
| **WP7 – Supply-Chain & Dependency Hygiene** | Lockfiles, SBOM, scanners. | ⏳ Backlog | Planned for compliance roadmap Automation phase. |
| **WP8 – Structured Logging & SIEM Integration** | JSON logs, WARN/ERROR hygiene. | ⏳ Backlog | To align with telemetry middleware work (feature roadmap). |
| **WP9 – Runtime & Egress Hardening** | Runtime baseline (non-root, umask), egress allow-lists. | ⏳ Backlog | Document in environment hardening guide; integrate into secure mode. |
| **WP10 – Legacy Cleanup & Docs Refresh** | Remove stale artefacts, keep docs current. | ⚙️ Ongoing | Continue through regular documentation reviews. |
| **WP11 – IRAP Pack (Threat Model & Control Matrix)** | Produce assessor-ready artefacts. | ⏳ Backlog | Covered in compliance roadmap (Phase 3). |

## Highlight: WP1 Implementation (Delivered)

The spreadsheet/CSV sanitisation effort (WP1) shipped the following:

- Shared sanitisation helper ensuring leading `= + - @` (and tabs/newlines) are prefixed with configurable guard (`'` by default).
- `sanitize_formulas` and `sanitize_guard` options surfaced on CSV/Excel/LocalBundle sinks; metadata recorded in manifests.
- Compatibility matrix script validating Excel, LibreOffice, pandas, and Python `csv` interoperability.
- Tests cover idempotency, Unicode, metadata propagation; warnings emit when sanitisation disabled.
- Documentation updates in `docs/end_to_end_scenarios.md` and sample manifests.

## Relationship to Current Roadmaps

- Open items above are mapped into `COMPLIANCE_ROADMAP.md` (security tooling, accreditation artefacts, operational integration).
- Feature roadmap items (telemetry middleware, structured logs, plugin attestation) support WP7, WP8, and WP2.
- Use this archive for historical context; maintain live status in the compliance roadmap backlog.
