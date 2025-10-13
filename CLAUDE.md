# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Elspeth is a secure, pluggable orchestration framework for responsible LLM experimentation. It bundles a hardened experiment runner, policy-aware plugin registry, and reporting pipeline so teams can run comparative LLM studies without compromising compliance or auditability.

**Core Value Proposition:** Composable plugins, security by default, governed suites, analytics-ready outputs, and enterprise observability.

## Essential Commands

### Environment Setup

```bash
# Bootstrap environment (creates .venv, installs deps, runs tests)
make bootstrap

# Bootstrap without running tests
make bootstrap-no-test

# Activate environment for manual work
source .venv/bin/activate
pip install -e .[dev,analytics-visual]
```

### Testing

```bash
# Fast feedback (excludes slow tests)
python -m pytest -m "not slow"

# Full test suite
python -m pytest

# Triage mode (stop on first failure, suppress warnings)
python -m pytest --maxfail=1 --disable-warnings

# Run single test file
python -m pytest tests/test_experiments.py

# Run single test function
python -m pytest tests/test_experiments.py::test_function_name

# With coverage report
python -m pytest --cov=elspeth --cov-report=term-missing
```

Test coverage data is written to `coverage.xml` for SonarQube/SonarCloud integration.

### Linting & Type Checking

```bash
# Run all lint checks (ruff format, ruff check, pytype)
make lint

# Individual tools
.venv/bin/python -m ruff format docs src tests
.venv/bin/python -m ruff check docs src tests
.venv/bin/python -m pytype src/elspeth
```

### Running Experiments

```bash
# Run the sample suite (exercises CSV datasource, mock LLM, analytics)
make sample-suite

# Full CLI invocation with options
python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite \
  --reports-dir outputs/sample_suite_reports \
  --head 0 \
  --live-outputs

# Preview without writing outputs (omit --live-outputs)
python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite \
  --head 5
```

Key output directories:

- `outputs/sample_suite/` - Experiment CSV exports
- `outputs/sample_suite_reports/` - Analytics reports (JSON, Markdown, Excel, PNG/HTML visuals)

## High-Level Architecture

### Core Components

**1. Orchestration Layer** (`src/elspeth/core/`)

- `orchestrator.py`: `ExperimentOrchestrator` wires datasource → LLM client → sinks
- `experiments/suite_runner.py`: `ExperimentSuiteRunner` manages multi-experiment suites with configuration merging (defaults → prompt packs → experiment overrides)
- `experiments/runner.py`: `ExperimentRunner` executes single experiments with row/aggregation plugins, concurrency, retries, and early stopping
- `artifact_pipeline.py`: `ArtifactPipeline` resolves sink dependencies, topologically sorts execution order, enforces security clearances

**2. Plugin System** (`src/elspeth/plugins/`, `src/elspeth/core/experiments/plugin_registry.py`)

- **Registry**: Central factory (`src/elspeth/core/registry.py`) for datasources, LLM clients, and sinks
- **Datasources**: CSV (local/blob), Azure Blob with profiles (`plugins/datasources/`)
- **LLM Clients**: Azure OpenAI, HTTP OpenAI, Mock, Static (`plugins/llms/`)
- **Middleware**: Audit logging, prompt shields, Azure Content Safety, health monitoring (`plugins/llms/middleware*.py`)
- **Experiment Plugins**:
  - Row-level: Score extraction, RAG query, noop (`plugins/experiments/metrics.py`, `rag_query.py`)
  - Aggregators: Statistics, recommendations, variant ranking, agreement, power analysis (`plugins/experiments/metrics.py`)
  - Validation: Regex, JSON structure, LLM guard (`plugins/experiments/validation.py`)
  - Early Stop: Threshold triggers (`plugins/experiments/early_stop.py`)
  - Baseline Comparisons: Row count, score deltas, effect sizes, significance tests (`plugins/experiments/metrics.py`)
- **Sinks**: CSV, Excel, JSON bundles, signed artifacts, Azure Blob, GitHub/Azure DevOps repos, analytics reports (JSON/Markdown), visual analytics (PNG/HTML), embeddings stores (pgvector/Azure Search) (`plugins/outputs/`)

**3. Security & Context System** (`src/elspeth/core/plugins/context.py`, `src/elspeth/core/security/`)

- Every plugin receives a `PluginContext` with `security_level`, `provenance`, `plugin_kind`, `plugin_name`
- Security levels flow: datasource + LLM → experiment context → sinks
- Artifact pipeline enforces "read-up" restrictions: sinks cannot consume artifacts from higher security classifications
- Signing and sanitization are built into pipelines (formula guards in CSV/Excel, artifact signatures in `signed_artifact` sink)

**4. Configuration & Validation** (`src/elspeth/config.py`, `src/elspeth/core/config_schema.py`)

- YAML-based configuration with schema validation
- Three-layer merge: defaults → prompt packs → experiment config
- Prompt packs (`config/sample_suite/packs/`) bundle prompts, middleware, plugins, and defaults
- Settings files (`config/sample_suite/settings.yaml`) define suite structure and global defaults

**5. Retrieval & Embeddings** (`src/elspeth/retrieval/`)

- `embedding.py`: Generate embeddings via Azure OpenAI or OpenAI
- `providers.py`: Abstract vector store providers (pgvector, Azure Search)
- `service.py`: Query and upsert operations with namespace isolation
- Used by `embeddings_store` sink and `retrieval_context` utility plugin

### Key Data Flows

1. **Single Experiment**: Datasource loads DataFrame → ExperimentRunner applies row plugins → LLM client (with middleware) generates responses → Aggregator plugins summarize → Validation plugins check constraints → Sinks write outputs
2. **Suite Execution**: ExperimentSuiteRunner iterates experiments → Merges configs → Builds runners → Executes each → Runs baseline comparisons → Calls suite-level middleware hooks → Aggregates results
3. **Artifact Pipeline**: Sinks declare `produces`/`consumes` → Pipeline resolves dependencies → Topological sort → Executes in order → Each sink receives consumed artifacts, writes, produces new artifacts → Security checks at every step

## Configuration Architecture

### Merge Hierarchy

Configuration merges in this order (later overrides earlier):

1. Suite defaults (`suite.defaults`)
2. Prompt pack (referenced by `prompt_pack` key)
3. Experiment-specific config (`experiments[].`)

### Prompt Packs

Located in `config/sample_suite/packs/*.yaml`:

- Bundle related prompts, middleware, plugins, security levels
- Reusable across experiments
- Override suite defaults
- See `docs/architecture/configuration-merge.md` for merge semantics

### Key Configuration Sections

- `datasource`: Plugin type and options (must include `security_level`)
- `llm`: LLM client plugin and options (must include `security_level`)
- `experiments[]`: Array of experiment definitions
- `prompt_packs`: Named pack definitions
- `defaults`: Suite-level defaults for prompts, plugins, middleware

## Plugin Development Guidelines

### Adding a New Plugin

1. **Choose the plugin type**: datasource, LLM client, middleware, row/aggregator/validation/early-stop, sink
2. **Implement the protocol**: See `src/elspeth/core/interfaces.py` for contracts
3. **Accept PluginContext**: Factory signature must be `create(options: Dict[str, Any], context: PluginContext) -> Plugin`
4. **Define JSON schema**: Validation schema in registry (`src/elspeth/core/registry.py` or experiment plugin registry)
5. **Register in registry**: Add to appropriate registry dict (`_datasources`, `_llms`, `_sinks`)
6. **Write tests**: Mirror package structure in `tests/` (e.g., `tests/test_outputs_mysink.py`)
7. **Document**: Add entry to `docs/architecture/plugin-catalogue.md`

### Context-Aware Factories

All plugins now use context-aware creation:

```python
def create_my_plugin(options: Dict[str, Any], context: PluginContext) -> MyPlugin:
    instance = MyPlugin(**options)
    instance.security_level = context.security_level
    instance._elspeth_context = context
    return instance
```

Registry automatically handles context propagation. Nested plugin creation (e.g., LLM in validation plugin) uses `create_llm_from_definition` which inherits parent context.

### Security Level Requirements

- Datasources, LLMs, and sinks **must** declare `security_level` in their configuration
- Registry validation enforces this requirement
- Security levels: `public`, `internal`, `confidential`, `restricted` (or custom strings)
- Pipeline enforces that sinks cannot read artifacts from higher security tiers

## Testing Patterns

### Fixtures

`tests/conftest.py` provides:

- `sample_dataframe()`: Standard test DataFrame
- `mock_llm_client()`: Deterministic mock LLM
- `tmp_path`: Pytest's temporary directory fixture

### Test Organization

- Mirror source structure: `src/elspeth/plugins/outputs/csv_file.py` → `tests/test_outputs_csv.py`
- Use `test_*.py` naming convention
- Parametrize tests for edge cases (see `tests/test_experiment_metrics_plugins.py` for examples)
- Integration tests should exercise full CLI or suite runner flows (see `tests/test_cli_end_to_end.py`)

### Markers

```python
@pytest.mark.integration  # Requires external services (pgvector, Azure)
@pytest.mark.slow         # Long-running tests
```

Exclude slow tests: `python -m pytest -m "not slow"`

## When Modifying Analytics or Reporting

After changing `SuiteReportGenerator`, analytics sinks, or visual outputs, regenerate reference artifacts:

```bash
python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite \
  --reports-dir outputs/sample_suite_reports \
  --head 0 \
  --live-outputs
```

Verify:

- `outputs/sample_suite_reports/` contains expected JSON, Markdown, Excel, PNG/HTML files
- No schema breaks or format regressions
- Update tests if output formats change (see `tests/test_outputs_visual.py`, `tests/test_integration_visual_suite.py`)

## Security & Compliance

### Key Controls

- **Prompt Sanitization**: Strict Jinja2 rendering without eval (see `src/elspeth/core/prompts/`)
- **Formula Sanitization**: CSV/Excel sinks guard against formula injection (configurable via `sanitize_formulas`, `sanitize_guard`)
- **Artifact Signing**: `signed_artifact` sink produces HMAC signatures with manifests
- **Audit Logging**: Middleware logs requests/responses with security-aware filtering (see `audit_logger` middleware)
- **Security Levels**: Per-plugin classification enforced throughout pipelines

### Documentation References

- `docs/architecture/security-controls.md` - Control inventory
- `docs/architecture/threat-surfaces.md` - Threat model
- `docs/architecture/CONTROL_INVENTORY.md` - Comprehensive control list
- `docs/TRACEABILITY_MATRIX.md` - Requirements traceability

## Common Pitfalls

1. **Forgetting `security_level`**: All datasources, LLMs, and sinks require explicit `security_level` in config. Registry validation will fail if missing.
2. **Artifact Pipeline Cycles**: If sinks have circular dependencies via `consumes`/`produces`, pipeline raises `ValueError`. Check dependency graph.
3. **Context Not Propagated**: When creating nested plugins (e.g., validator LLM), use `create_llm_from_definition` to inherit parent context, not direct instantiation.
4. **Configuration Merge Confusion**: Remember the hierarchy: defaults → prompt pack → experiment config. Check `docs/architecture/configuration-merge.md` for precedence rules.
5. **Middleware Shared State**: Suite runner caches middleware instances by fingerprint. Be careful with mutable state in middleware plugins.
6. **Test Data Security**: Never commit real API keys or sensitive data. Use environment variables or mock clients in tests.

## Important Files & Directories

### Source Code

- `src/elspeth/cli.py` - Main CLI entrypoint
- `src/elspeth/config.py` - Configuration loading and validation
- `src/elspeth/core/orchestrator.py` - Single experiment orchestrator
- `src/elspeth/core/experiments/suite_runner.py` - Suite orchestration
- `src/elspeth/core/registry.py` - Central plugin registry
- `src/elspeth/core/artifact_pipeline.py` - Sink dependency resolution
- `src/elspeth/plugins/` - All plugin implementations

### Configuration

- `config/sample_suite/settings.yaml` - Sample suite configuration
- `config/sample_suite/packs/*.yaml` - Reusable prompt packs
- `config/sample_suite/*.yaml` - Individual experiment suites

### Documentation

- `docs/architecture/README.md` - Architecture guide index
- `docs/architecture/plugin-catalogue.md` - Complete plugin reference
- `docs/architecture/configuration-merge.md` - Config merge semantics
- `docs/reporting-and-suite-management.md` - Operational guide
- `docs/end_to_end_scenarios.md` - Usage walkthroughs

### Tests

- `tests/conftest.py` - Shared fixtures
- `tests/test_experiments.py` - Core experiment runner tests
- `tests/test_suite_runner_integration.py` - Suite integration tests
- `tests/test_artifact_pipeline.py` - Sink dependency tests

## Development Workflow

1. **Create feature branch**: `git checkout -b <topic>/<description>`
2. **Make changes**: Follow PEP 8, use type hints, keep functions focused
3. **Run tests**: `python -m pytest -m "not slow"`
4. **Run linters**: `make lint`
5. **Update docs**: Adjust `docs/` if adding features or changing behavior
6. **Regenerate artifacts** (if needed): Run sample suite to verify outputs
7. **Commit**: Use imperative style ("Add", "Fix", "Refactor"), concise body
8. **Open PR**: Link issues, describe changes, list verification commands

## Retrieval & RAG Integration

### Embeddings Store Sink

The `embeddings_store` sink persists experiment results as embeddings for later retrieval:

- **Providers**: `pgvector` (PostgreSQL), `azure_search` (Azure Cognitive Search)
- **Configuration**: Define `provider`, `namespace`, DSN/endpoint, embedding model, metadata fields
- **Security**: Namespace derived from `PluginContext.security_level` to isolate tiers
- **Usage**: See `tests/test_outputs_embeddings_store.py`

### Retrieval Utility Plugin

The `retrieval_context` utility plugin queries vector stores and returns structured context:

- **Use Case**: Enrich prompts with relevant past experiments or knowledge base articles
- **Configuration**: `provider`, `dsn/endpoint`, `embed_model`, `query_field`, `inject_mode`, `top_k`, `min_score`
- **Context Aware**: Uses `PluginContext` to enforce namespace isolation
- **Coverage**: `tests/test_retrieval_utility.py`

### RAG Query Row Plugin (Legacy)

The `rag_query` experiment row plugin is now a shim over `retrieval_context`. Prefer the utility plugin for new work.

## References

- Main README: `/home/john/elspeth/README.md`
- Contributing Guide: `/home/john/elspeth/CONTRIBUTING.md`
- Repository Guidelines: `/home/john/elspeth/AGENTS.md`
- Architecture Docs: `/home/john/elspeth/docs/architecture/`
- Plugin Catalogue: `/home/john/elspeth/docs/architecture/plugin-catalogue.md`
