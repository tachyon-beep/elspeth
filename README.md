# Elspeth

> Secure, pluggable orchestration for responsible LLM experimentation.

Elspeth bundles a hardened experiment runner, policy-aware plugin registry, and reporting pipeline so teams can run comparative LLM studies without compromising compliance or auditability. Datasources, LLM clients, metrics, and sinks remain swappable while trace metadata, sanitisation, and signing keep artefacts defensible.

## Highlights

- **Composable plugin system** – Drop in datasources, LLM adapters, middleware, metrics, and result sinks registered via `src/elspeth/core/registry.py` without touching the orchestrator.
- **Security by default** – Strict prompt rendering, retry logging, per-artifact security levels, spreadsheet sanitisation, and optional signed bundles are built into the pipeline.
- **Governed suites** – Merge prompt packs, suite defaults, and experiment overrides with validation and dry-run tooling before executing batch comparisons.
- **Analytics ready** – Generate CSV, Excel, JSON, Markdown, or visual PNG/HTML reports alongside retry/cost summaries for downstream review.
- **Enterprise observability** – Integrate rate limiting, cost tracking, audit logging, and telemetry middleware while preserving deterministic mocks for offline development.

## Quick Start

### Prerequisites

- Python 3.12
- GNU Make (or run the equivalent `scripts/bootstrap.sh`)
- Optionally: a virtual environment (`python -m venv .venv`)

### Install & bootstrap

```bash
make bootstrap           # creates .venv/, installs extras, runs pytest
# or skip the initial test pass
make bootstrap-no-test
```

Activate the environment when working manually:

```bash
source .venv/bin/activate
pip install -e .[dev]
```

### Run the sample suite

The sample configuration exercises the CSV datasource, mock LLM, analytics sinks, and reporting flow with no external dependencies.

```bash
make sample-suite
```

Key artefacts land in `outputs/sample_suite_reports/` (analytics, visual charts, Excel workbook) alongside experiment CSV exports under `outputs/sample_suite/`.

### Explore the CLI

```bash
python -m elspeth.cli --help
python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite \
  --reports-dir outputs/sample_suite_reports
```

Pass `--live-outputs` to allow repository or blob sinks to write to their targets and `--head 0` to skip preview tables.

## Documentation Hub

| Topic | Description |
| ------ | ----------- |
| [Usage & Operations](docs/reporting-and-suite-management.md) | Running suites, managing reports, and operational workflows. |
| [End-to-End Scenarios](docs/end_to_end_scenarios.md) | Guided walkthroughs for typical experimentation pipelines. |
| [Configuration & Prompt Packs](docs/architecture/configuration-merge.md) | Deep dive into how profiles, packs, and defaults merge. |
| [Plugin Catalogue](docs/architecture/plugin-catalogue.md) | Datasources, LLM clients, middleware, metrics, and sinks. |
| [Security & Compliance](docs/architecture/security-controls.md) | Controls inventory, threat surfaces, and accreditation notes. |
| [Architecture Overview](docs/architecture/README.md) | Component diagrams, data flows, and lifecycle documentation. |
| [Logging & Observability](docs/logging-standards.md) | Standards for audit logs and telemetry integration. |
| [Upgrade & Migration Guides](docs/migration-guide.md) | Version-to-version migration checklist and upgrade strategy. |

Prefer a consolidated index? Check `docs/README.md` for a map of every reference.

## Architecture Snapshot

- **Ingestion** – Datasources normalise tabular inputs and tag security levels before experimentation (`src/elspeth/plugins/datasources/`).
- **Orchestrator** – `ExperimentOrchestrator` wires datasource, LLM client, sinks, and controls, then dispatches to `ExperimentSuiteRunner` for suites.
- **Artifact Pipeline** – Sinks declare dependencies and security clearances; the pipeline orchestrates writes, chaining, and signing.
- **Analytics** – `SuiteReportGenerator` produces combined CSV/Excel/visual artefacts, while the `VisualAnalyticsSink` renders PNG/HTML summaries.

For diagrams and deep detail, see `docs/architecture/architecture-overview.md`, `docs/architecture/component-diagram.md`, and `docs/architecture/data-flow-diagrams.md`.

## Testing & Quality Gates

- Run `python -m pytest -m "not slow"` (or `make test`) for fast feedback.
- Use `python -m pytest --maxfail=1 --disable-warnings` during triage.
- Lint/format with `make lint` (runs `ruff` formatting/checks plus `pytype`).
- Regenerate analytics artefacts after reporting or sink changes:

  ```bash
  python -m elspeth.cli \
    --settings config/sample_suite/settings.yaml \
    --suite-root config/sample_suite \
    --reports-dir outputs/sample_suite_reports \
    --head 0
  ```

Coverage data is emitted to `coverage.xml` for SonarQube/SonarCloud.

## Contributing

We welcome issues, improvements, and new plugins. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md) for branching, coding-style, and testing guidelines. The [`docs/release-checklist.md`](docs/release-checklist.md) tracks release expectations, and `docs/architecture/upgrade-strategy.md` covers compatibility policies.

## Community & Support

- File bugs and feature requests via GitHub Issues.
- Reference `docs/architecture/incident-response.md` for high-severity escalation processes.
- Compliance teams can consult `docs/architecture/CONTROL_INVENTORY.md` and `docs/TRACEABILITY_MATRIX.md` for audit evidence.

## License

License information will be published in `LICENSE`. Until then, reach out to the maintainers before redistributing or deploying Elspeth in production environments.

---

> ✨ Looking for implementation details? Browse the source under `src/elspeth/` and the comprehensive architecture notes in `docs/architecture/`.
