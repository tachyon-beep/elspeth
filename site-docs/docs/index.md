# Elspeth Documentation

**Extensible Layered Secure Pipeline Engine for Transformation and Handling**

Elspeth is a general-purpose orchestration platform implementing **sense-decide-act workflows**: sources provide inputs, transforms apply logic (analytical, decisional, or procedural), and sinks handle outputs—whether storing results, triggering automation, or actuating real-world effects.

**Transformation** covers any source-to-output logic: data ETL, LLM inference, statistical analysis, rule evaluation, or custom processing. **Handling** encompasses the full range of sink behaviors: persisting to databases, writing reports, sending notifications, invoking APIs, or commanding external systems.

While Elspeth excels at LLM experimentation with hardened runners, policy-aware registries, and comparative studies, the plugin architecture supports any workflow topology. Security controls—**Bell-LaPadula Multi-Level Security (MLS)** enforcement, artifact signing, audit logging, spreadsheet sanitization—are baked into every pipeline stage.

---

## Quick Start

<div class="grid cards" markdown>

-   :material-download:{ .lg .middle } **Installation**

    ---

    Get Elspeth running on your system in minutes

    [:octicons-arrow-right-24: Install now](getting-started/installation.md)

-   :material-rocket-launch:{ .lg .middle } **Quickstart**

    ---

    Run your first experiment in 5 minutes (no API keys needed)

    [:octicons-arrow-right-24: Try it out](getting-started/quickstart.md)

-   :material-file-document:{ .lg .middle } **First Experiment**

    ---

    Build a complete experiment from scratch (15-20 minutes)

    [:octicons-arrow-right-24: Get started](getting-started/first-experiment.md)

-   :material-shield-lock:{ .lg .middle } **Security Model**

    ---

    Understand Bell-LaPadula MLS enforcement

    [:octicons-arrow-right-24: Learn more](user-guide/security-model.md)

</div>

---

## Core Features

### Security-First Design

- ✅ **Bell-LaPadula Multi-Level Security (MLS)** - Immutable classification with fail-fast validation
- ✅ **Artifact Signing** - HMAC-SHA256/SHA512, RSA-PSS-SHA256, ECDSA-P256-SHA256
- ✅ **PII Detection** - Block emails, SSNs, credit cards, Australian TFN/Medicare
- ✅ **Classified Material Detection** - Block SECRET, TOP SECRET, TS//SCI markings
- ✅ **Formula Sanitization** - Prevent Excel/CSV injection attacks
- ✅ **Comprehensive Audit Logging** - JSONL audit trail with correlation IDs

### Flexible Architecture

- 🔌 **40+ Built-in Plugins** - Datasources, transforms (LLM, ETL, analytics, rules), sinks, middleware
- 🔄 **Middleware Pipeline** - Security filters, monitoring, content safety, custom logic
- 📊 **Workflow Helpers** - Validation, aggregation, baseline comparison, early stop
- 🎯 **Dependency-Ordered Execution** - Artifact pipeline with sink chaining
- ⚡ **Concurrency Support** - Parallel execution with rate limiting
- 💾 **Checkpoint Recovery** - Resume long-running workflows

### Production-Ready

- 📝 **Configuration as Code** - Validated YAML with schema enforcement
- 🔁 **Retry Logic** - Exponential backoff with exhaustion hooks
- 💰 **Cost Tracking** - Token usage and API cost aggregation
- 📈 **Baseline Comparison** - Statistical significance, effect size, Bayesian analysis
- 🎨 **Visual Analytics** - Charts (PNG/HTML) with metadata embedding
- 📦 **Signed Bundles** - Tamper-evident artifact packages

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  YAML Configuration → Validated → Environment Resolution    │
└───────────────────────┬─────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  Datasources (ClassifiedDataFrame)                          │
│  CSV Local/Blob, Azure Blob → Tagged with SecurityLevel    │
└───────────────────────┬─────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  Workflow Orchestrator (Operating Level = MIN of all)       │
└───────────────────────┬─────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  Workflow Runner (Concurrency, Retries, Checkpoints)        │
└───────────────────────┬─────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  Transforms + Middleware (Security Filters, Monitoring)     │
│  LLM (Azure OpenAI, HTTP, Mock), ETL, Analytics, Rules     │
└───────────────────────┬─────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  Artifact Pipeline (Dependency-Ordered Sinks)                │
│  CSV, Excel, Signed Bundles, Azure Blob, GitHub Repos      │
└─────────────────────────────────────────────────────────────┘
```

**Key Principle**: Security levels propagate throughout the pipeline with fail-fast enforcement at every boundary.

---

## Documentation Sections

### Getting Started

Perfect for new users learning Elspeth:

- **[Installation](getting-started/installation.md)** - Setup guide with lockfile requirements
- **[Quickstart](getting-started/quickstart.md)** - 5-minute hello world (no API keys)
- **[First Experiment](getting-started/first-experiment.md)** - 15-20 minute tutorial from scratch

### User Guide

In-depth guides for using Elspeth effectively:

- **[Security Model](user-guide/security-model.md)** - Bell-LaPadula MLS explained with 4 scenarios
- **[Configuration](user-guide/configuration.md)** - YAML reference with merge order, environment variables, 3 runnable patterns

### Plugins

Discover and configure 40+ built-in plugins:

- **[Plugin Catalogue](plugins/overview.md)** - Use case-driven plugin documentation
  - Loading Data (3 datasources)
  - Processing with LLMs (4 clients + 8 middleware)
  - Saving Results (11 sinks)
  - Experiment Helpers (validation, aggregation, baseline, early stop)
  - RAG (2 vector stores)
  - Cost & Rate Limiting (5 controls)

### Architecture

Understand Elspeth's design and decisions:

- **[Architecture Overview](architecture/overview.md)** - System architecture, component layers, data flow
- **[ADR Catalogue](architecture/adrs.md)** - 13 Architecture Decision Records explaining "why"
  - ADR-001: Design Philosophy (security-first, fail-closed)
  - ADR-002: Multi-Level Security (Bell-LaPadula MLS)
  - ADR-002a: Trusted Container Model (ClassifiedDataFrame)
  - ADR-004: Mandatory BasePlugin Inheritance (security bones)
  - ADR-005: Frozen Plugin Protection (dedicated infrastructure)
  - ...and 8 more

### API Reference

Auto-generated API documentation for developers:

- **[API Overview](api-reference/index.md)** - Quick navigation and examples
- **[Core](api-reference/core/base-plugin.md)** - BasePlugin, ClassifiedDataFrame, SecurityLevel
- **[Registries](api-reference/registries/base.md)** - Plugin registration and factories
- **[Plugins](api-reference/plugins/datasources.md)** - Datasource, Transform, Sink APIs
- **[Pipeline](api-reference/pipeline/artifact-pipeline.md)** - Dependency resolution and chaining

---

## Common Use Cases

### Data ETL & Analytics

```yaml
# Transform and analyze data without external APIs
datasource:
  type: csv_local
  path: data/raw_data.csv
  security_level: OFFICIAL

transform:
  type: custom_analytics  # Rule-based logic, statistical analysis
  security_level: OFFICIAL

sinks:
  - type: excel_workbook
    base_path: reports/
    security_level: OFFICIAL
  - type: analytics_report
    formats: [json, markdown]
```

**Use for**: Data validation, statistical analysis, business rule evaluation, compliance reporting

---

### Environmental Monitoring & Alerting (Sense-Decide-Act)

```yaml
# Weather monitoring with automated public safety alerts
datasource:
  type: satellite_telemetry  # Custom plugin: satellite weather data stream
  refresh_interval: 300  # Poll every 5 minutes
  security_level: OFFICIAL

transform:
  type: meteorology_analyzer  # Custom plugin: specialist analysis system
  thresholds:
    severe_weather: 0.8
    flood_risk: 0.7
    fire_danger: 0.9
  security_level: OFFICIAL

sinks:
  # Conditional routing based on analysis results
  - type: emergency_broadcast  # Custom plugin: SMS/radio alert system
    condition: severity >= 0.8
    recipients: regional_contacts
    security_level: OFFICIAL

  - type: weather_api  # Custom plugin: public weather service
    condition: severity >= 0.5
    security_level: OFFICIAL

  - type: archive_csv  # Standard plugin: historical record
    path: data/weather_log.csv
    security_level: OFFICIAL
```

**Real-world pattern**:
- **Sense**: Satellite telemetry ingress (temperature, pressure, humidity)
- **Decide**: Specialist meteorology system analyzes conditions, assigns severity scores
- **Act**: Route alerts to emergency broadcast systems based on thresholds (high severity → SMS alerts, moderate → API updates, all → archive)

**Use for**: Environmental monitoring, infrastructure sensors (IoT), industrial process control, public safety alerting, automated operations

---

### LLM Experimentation (Development & Testing)

```yaml
# Simple LLM configuration for testing (no sensitive data)
datasource:
  type: csv_local
  path: data/test.csv
  security_level: UNOFFICIAL

llm:
  type: mock  # No API keys needed
  response_template: "Mock: {text}"
  security_level: UNOFFICIAL

sinks:
  - type: csv
    path: results.csv
    security_level: UNOFFICIAL
```

**Start here**: [Quickstart](getting-started/quickstart.md)

---

### LLM Production with Security

```yaml
# Secure configuration with middleware and signing
datasource:
  type: azure_blob
  security_level: PROTECTED

llm:
  type: azure_openai
  security_level: PROTECTED
  middleware:
    - type: pii_shield        # Block PII
    - type: classified_material  # Block classified markings
    - type: azure_content_safety  # External content check
    - type: audit_logger      # Comprehensive logging

sinks:
  - type: signed_artifact
    algorithm: HMAC-SHA256
    security_level: PROTECTED
```

**Learn more**: [Security Model](user-guide/security-model.md), [Configuration Guide](user-guide/configuration.md)

---

### RAG with Baseline Comparison

```yaml
# RAG-enabled experiment with statistical comparison
experiment:
  datasource:
    type: csv_local
    path: data/questions.csv

  llm:
    type: azure_openai

  row_plugins:
    - type: retrieval_context  # Add vector store context
      provider: pgvector
      top_k: 5

  baseline:
    experiment_name: without_rag
    comparison_plugins:
      - type: score_significance
        criteria: [accuracy, relevance]

  sinks:
    - type: analytics_report
      formats: [json, markdown]
```

**Learn more**: [Plugin Catalogue: RAG](plugins/overview.md#advanced-retrieval-augmented-generation-rag), [Architecture Overview](architecture/overview.md)

---

## Project Information

### Version & Status

- **Version**: 0.1.0-dev (pre-release)
- **Python**: 3.12+
- **License**: [Check repository for details]
- **Repository**: [GitHub](https://github.com/yourusername/elspeth)

### Documentation Organization

This documentation site provides **user-facing guides and API reference**. For comprehensive developer documentation including:

- ADR source files (full text with implementation details)
- Refactoring methodology (complexity reduction)
- Migration plans (plugin architecture evolution)
- Testing overview and strategy
- Compliance controls and traceability matrices

...see the `docs/` directory in the repository.

### Getting Help

- **Issues**: [GitHub Issues](https://github.com/yourusername/elspeth/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/elspeth/discussions)
- **Security**: See `docs/compliance/incident-response.md` in repository

---

## Next Steps

<div class="grid cards" markdown>

-   :material-play-circle:{ .lg .middle } **Run Your First Experiment**

    ---

    Follow the quickstart guide to run a complete experiment in 5 minutes

    [:octicons-arrow-right-24: Quickstart](getting-started/quickstart.md)

-   :material-school:{ .lg .middle } **Learn the Security Model**

    ---

    Understand Bell-LaPadula MLS with 4 worked scenarios

    [:octicons-arrow-right-24: Security Model](user-guide/security-model.md)

-   :material-puzzle:{ .lg .middle } **Explore Plugins**

    ---

    Discover 40+ built-in plugins organized by use case

    [:octicons-arrow-right-24: Plugin Catalogue](plugins/overview.md)

-   :material-code-braces:{ .lg .middle } **Develop Plugins**

    ---

    Build custom datasources, transforms, and sinks

    [:octicons-arrow-right-24: API Reference](api-reference/index.md)

</div>

---

!!! success "Welcome to Elspeth!"
    Elspeth brings **security-first orchestration** to sense-decide-act workflows with:

    - ✅ Bell-LaPadula MLS enforcement (immutable classification)
    - ✅ 40+ built-in plugins (extensible architecture)
    - ✅ Fail-fast validation (catch errors before data retrieval)
    - ✅ Comprehensive audit trails (JSONL logs with correlation IDs)
    - ✅ Production-ready features (signing, checkpointing, retries)

    **Ready to start?** Head to the [Quickstart](getting-started/quickstart.md) or [First Experiment](getting-started/first-experiment.md) guide!
