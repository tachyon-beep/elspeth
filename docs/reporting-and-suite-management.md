# Suite Management & Analytics Reporting

This guide walks through the new CLI flows for maintaining legacy-style suites, generating
experiment scaffolds, and producing consolidated analytics artefacts.

## Prerequisites

Install the optional dependencies used by the reporting pipeline:

```bash
pip install -e .[dev,analytics-visual]  # pandas/openpyxl + matplotlib/seaborn for reports
```

> The remainder of the CLI only requires the base installation, but report generation skips
> Excel/visual outputs when pandas or matplotlib are unavailable.[^reporting-deps-2025-10-12]
<!-- UPDATE 2025-10-12: The visual analytics sink also relies on matplotlib (and optionally seaborn) when producing PNG/HTML charts; install these packages before enabling the sink. -->
Optional analytics extras (`pip install -e .[stats-core,stats-agreement,stats-planning,stats-distribution]`)
unlock additional statistical plugins; install the sets your accreditation run depends on so comparative
reports include consistent metrics.[^reporting-analytics-extras-2025-10-12]

## 1. Create or update suites

Clone the repo root and activate the virtual environment:

```bash
source .venv/bin/activate
```

Identify your suite directory (for example `config/sample_suite`). Then run:

```bash
# Scaffold a new experiment by copying prompts from the baseline experiment
python -m elspeth.cli \
  --settings config/settings.yaml \
  --suite-root config/sample_suite \
  --create-experiment-template draft_variant \
  --template-base baseline_experiment \
  --head 0
```

<!-- UPDATE 2025-10-12: Template creation citation refresh -->
Update 2025-10-12: Template and export flags are defined in `src/elspeth/cli.py:80-105`.
<!-- END UPDATE -->

The new experiment lives at `config/sample_suite/draft_variant/` with prompts and a disabled
`config.json`. The command is safe to run repeatedly; change `--template-base` or omit it to
start from the default template.

To export the entire suite definition:

```bash
python -m elspeth.cli \
  --settings config/settings.yaml \
  --suite-root config/sample_suite \
  --export-suite-config outputs/sample_suite_export.json \
  --head 0
```

<!-- UPDATE 2025-10-12: Suite export citation refresh -->
Update 2025-10-12: Suite export and reporting orchestration executes via `_handle_suite_management` at `src/elspeth/cli.py:390-458`.
<!-- END UPDATE -->

The JSON/YAML file contains the suite metadata, experiment list, and per-experiment configuration
ready for auditing or versioned backups.

## 2. Run suites with consolidated reports

Reporting builds on the normal suite run. Provide a target directory via `--reports-dir`:

```bash
python -m elspeth.cli \
  --settings config/settings.yaml \
  --suite-root config/sample_suite \
  --reports-dir outputs/sample_suite_reports \
  --head 0
```

The folder structure contains:

```markdown
outputs/sample_suite_reports/
├── baseline/                # per-experiment stats.json files
├── exp_variant/             # per-experiment stats.json files (variants)
└── consolidated/
    ├── analysis_config.json
    ├── analysis.xlsx        # requires pandas + openpyxl
    ├── analysis_summary.png # requires matplotlib
    ├── analytics_visual.png # generated when visual sink enabled
    ├── comparative_analysis.json
    ├── executive_summary.md
    ├── failure_analysis.json
    ├── recommendations.json
    └── validation_results.json
```

### Artefact overview

- **analysis_config.json** – suite summary, plugin usage, and export metadata.
- **comparative_analysis.json** – baseline vs. variant score statistics and baseline plugin outputs.
- **executive_summary.md** – human-readable highlights (baseline, variant deltas, recommendations).
- **analysis.xlsx** – Excel workbook with summary, comparisons, and recommendation sheets.
- **analysis_summary.png** – bar chart comparing mean scores (error bars reflect std dev).
- **analytics_visual.png / analytics_visual.html** – optional chart outputs when the visual analytics sink is configured; HTML embeds a base64 PNG and inline summary tables.
- **failure_analysis.json** – captured row-level failures (including retry history).
- **validation_results.json** – output from `validate_suite`, including warnings and preflight estimates.

### Optional-dependency fallbacks

When pandas/openpyxl/matplotlib are missing, the CLI logs an informational message and skips the
Excel or PNG artefacts while still producing JSON/Markdown reports. Install the suggested packages
to unlock the full pipeline.
<!-- UPDATE 2025-10-12: When statistical extras are missing, analytics sections still render but omit p-values/intervals; review `analytics_report.json` for null placeholders before distributing. -->

## 3. Automating workflows

Add the commands above to CI pipelines or Make targets. For example:

```Makefile
reports:
 . .venv/bin/activate && \
 python -m elspeth.cli \
   --settings config/settings.yaml \
   --suite-root config/sample_suite \
   --reports-dir outputs/sample_suite_reports \
   --head 0
```

This keeps the suite exports and analytics reports in sync with every build. For multi-suite setups,
iterate over directories or use multiple CLI invocations with different `--suite-root` values.

## 4. Logging & Archival

- Archive the CLI stdout/stderr from report runs; it lists each consolidated artefact and validates
  middleware lifecycle logging expectations (`src/elspeth/tools/reporting.py:33`).[^reporting-logging-2025-10-12]
<!-- UPDATE 2025-10-12: Suite report logging citation refresh -->
Update 2025-10-12: Reporting logs are produced across `src/elspeth/tools/reporting.py:26-199`.
<!-- END UPDATE -->
- Hash or sign artefacts destined for accreditation packages. Recommended structure:

  ```bash
  sha256sum outputs/sample_suite_reports/consolidated/* > outputs/sample_suite_reports/checksums.txt
  python -m elspeth.tools.verify_signature outputs/sample_suite/signed_bundle/signature.json
  ```

  Store the checksum file alongside the signed bundle to provide provenance for auditors.[^reporting-checksums-2025-10-12]
- Upload consolidated reports and logs to a secure evidence store (e.g., Azure Blob, GitHub dry-run manifest) using dry-run mode first; only flip to live outputs once provenance is captured.[^reporting-archive-2025-10-12]

## Added 2025-10-12 – Reporting Verification Checklist

- After generating reports, open `consolidated/analysis_config.json` and confirm `plugin_summary` enumerates expected middleware, metrics, and sinks (`src/elspeth/tools/reporting.py:83`).[^reporting-plugin-summary-2025-10-12]
- Validate that `consolidated/validation_results.json` captures suite warnings or errors emitted by `validate_suite`; accreditation reviewers rely on these logs (`src/elspeth/tools/reporting.py:38`).[^reporting-validation-2025-10-12]
- If running with `--live-outputs`, confirm repository or blob sinks remained in dry-run mode unless explicitly toggled (`src/elspeth/cli.py:344`).[^reporting-live-outputs-2025-10-12]
<!-- UPDATE 2025-10-12: CLI dry-run citation refresh -->
Update 2025-10-12: Dry-run toggles are enforced at `src/elspeth/cli.py:360-392`.
<!-- END UPDATE -->
- When the visual analytics sink is enabled, review `analytics_visual.png`/`.html` and ensure HTML outputs remain self-contained (no external asset references) before distribution.[^reporting-visual-2025-10-12]

## Update History

- 2025-10-12 – Update 2025-10-12: Added dependency install commands, logging/archival guidance, and accreditation evidence recommendations for suite reporting outputs.
- 2025-10-12 – Documented dependency extras interplay, analytics null-handling, visual chart outputs, and a post-run verification checklist for generated reports.
- 2025-10-12 – Update 2025-10-12: Added references to dependency analysis and verification steps for analytics artefacts.

[^reporting-deps-2025-10-12]: Update 2025-10-12: Dependency requirements align with docs/architecture/dependency-analysis.md (Optional Extras).
[^reporting-analytics-extras-2025-10-12]: Update 2025-10-12: Optional extras cross-referenced in docs/architecture/dependency-analysis.md (Optional Extras).
[^reporting-plugin-summary-2025-10-12]: Update 2025-10-12: Plugin summary expectations tie to docs/architecture/component-diagram.md (Update 2025-10-12: Plugin Registry).
[^reporting-validation-2025-10-12]: Update 2025-10-12: Validation outputs linked to docs/architecture/configuration-security.md (Update 2025-10-12: Suite Defaults).
[^reporting-live-outputs-2025-10-12]: Update 2025-10-12: Dry-run considerations covered in docs/architecture/threat-surfaces.md (Update 2025-10-12: Repository Interfaces).
[^reporting-visual-2025-10-12]: Update 2025-10-12: Visual sink guidance matches docs/architecture/security-controls.md (Update 2025-10-12: Output Sanitisation).
[^reporting-logging-2025-10-12]: Update 2025-10-12: Logging expectations align with docs/logging-standards.md (Suite report exports).
[^reporting-checksums-2025-10-12]: Update 2025-10-12: Signing guidance mirrors docs/architecture/security-controls.md (Artifact Signing).
[^reporting-archive-2025-10-12]: Update 2025-10-12: Evidence archival practices referenced in docs/release-checklist.md (Post-Release artefact handling).
