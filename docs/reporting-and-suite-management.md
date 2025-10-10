# Suite Management & Analytics Reporting

This guide walks through the new CLI flows for maintaining legacy-style suites, generating
experiment scaffolds, and producing consolidated analytics artefacts.

## Prerequisites

Install the optional dependencies used by the reporting pipeline:

```bash
pip install -e .[dev]      # brings in pandas + openpyxl for Excel exports
pip install matplotlib seaborn
```

> The remainder of the CLI only requires the base installation, but report generation skips
> Excel/visual outputs when pandas or matplotlib are unavailable.

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

```
outputs/sample_suite_reports/
├── baseline/                # per-experiment stats.json files
├── exp_variant/             # per-experiment stats.json files (variants)
└── consolidated/
    ├── analysis_config.json
    ├── analysis.xlsx        # requires pandas + openpyxl
    ├── analysis_summary.png # requires matplotlib
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
- **failure_analysis.json** – captured row-level failures (including retry history).
- **validation_results.json** – output from `validate_suite`, including warnings and preflight estimates.

### Optional-dependency fallbacks

When pandas/openpyxl/matplotlib are missing, the CLI logs an informational message and skips the
Excel or PNG artefacts while still producing JSON/Markdown reports. Install the suggested packages
to unlock the full pipeline.

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
