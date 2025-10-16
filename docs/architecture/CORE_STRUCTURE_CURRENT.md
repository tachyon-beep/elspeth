# Core Directory Structure (Current)

**Last Updated:** 2025-10-17
**Status:** Current structure as of PR #4

> **Note:** A future reorganization is proposed in [docs/roadmap/CORE_DIRECTORY_RESTRUCTURE_PROPOSAL.md](../roadmap/CORE_DIRECTORY_RESTRUCTURE_PROPOSAL.md). This document describes the **current** structure.

## Quick Reference

```
src/elspeth/core/
├── base/                      - Protocols, plugin context, schema utilities, core enums
├── pipeline/                  - Artifact pipeline, artifact models, prompt processing helpers
├── config/                    - Configuration schemas and secure-mode validation
├── validation/                - Validation base classes and high-level validators
├── utils/                     - Logging and environment-variable helpers
├── registries/                - Canonical plugin registries (datasource, llm, sink, utility, middleware)
├── orchestrator.py            - Experiment orchestration entry point
├── controls/                  - Rate limiter and cost tracker implementations
├── experiments/               - Experiment runner framework
├── security/                  - Security classification helpers and secure-mode enforcement
└── prompts/                   - Prompt rendering infrastructure
```

## Navigation Guide

### "I need to understand the plugin system"

- **Start here:** `base/protocols.py` – Core protocol definitions (DataSource, ResultSink, LLM interfaces)
- **Then:** `base/plugin_context.py` – How context flows through plugins
- **Registry base:** `registries/base.py` – Base registry framework shared by all plugin registries
- **Specific registries:** `registries/*.py` modules (datasource, llm, middleware, sink, utility)

### "I need to create/register a new plugin"

- **Datasource:** See `registries/datasource.py`
- **LLM Client:** See `registries/llm.py`
- **Middleware:** See `registries/middleware.py`
- **Sink:** See `registries/sink.py`
- **Utility:** See `registries/utility.py`
- **Experiment plugins:** See `experiments/plugin_registry.py`

### "I need to understand how experiments run"

- **Main orchestration:** `orchestrator.py`
- **Single experiment:** `experiments/runner.py`
- **Suite of experiments:** `experiments/suite_runner.py`
- **Sink ordering:** `pipeline/artifact_pipeline.py`

### "I need to add configuration validation"

- **Schema definitions:** `config/schema.py`
- **Secure-mode validation:** `config/validation.py`
- **Base validation classes:** `validation/base.py`
- **Profile validation entrypoints:** `validation/validators.py`

### "I need to work with security/rate limiting/prompts"

- **Security:** `security/` subdirectory
- **Rate limiting:** `controls/rate_limiter_registry.py`
- **Cost tracking:** `controls/cost_tracker_registry.py`
- **Prompts:** `prompts/` subdirectory

## File Size Reference

**Large Files** (>10KB - may need refactoring):

- `validation/validators.py` – 31K ⚠️ Very large
- `base/schema.py` – 18K
- `registries/sink.py` – 18K
- `pipeline/artifact_pipeline.py` – 15K
- `utils/logging.py` – 14K
- `base/types.py` – 13K

**Medium Files** (5-10KB):

- `base/protocols.py` – 8.9K
- `config/validation.py` – 9.3K
- `registries/llm.py` – 8.5K
- `validation/base.py` – 7.6K
- `orchestrator.py` – 6.9K
- `registries/datasource.py` – 6.2K
- `base/plugin_context.py` – 5.3K

**Small Files** (<5KB):

- Remaining modules

## Import Patterns

### Common Imports

```python
# Registries
from elspeth.core.registries.datasource import datasource_registry
from elspeth.core.registries.llm import llm_registry
from elspeth.core.registries.middleware import create_middlewares, register_middleware
from elspeth.core.registries.sink import sink_registry
from elspeth.core.registries.utility import utility_plugin_registry

# Protocols
from elspeth.core.base.protocols import (
    DataSource,
    ResultSink,
    LLMClientProtocol,
    LLMMiddleware,
)

# Plugin Context
from elspeth.core.base.plugin_context import PluginContext, apply_plugin_context

# Validation
from elspeth.core.validation.base import ConfigurationError, validate_schema
from elspeth.core.validation import validate_experiment_config

# Orchestration
from elspeth.core.orchestrator import ExperimentOrchestrator
from elspeth.core.experiments.runner import ExperimentRunner
from elspeth.core.experiments.suite_runner import ExperimentSuiteRunner
```

### Registry Usage Pattern

```python
# Creating a datasource from configuration
from elspeth.core.registries.datasource import datasource_registry
from elspeth.core.base.plugin_context import PluginContext

context = PluginContext(
    security_level="official",
    provenance="config",
    plugin_kind="datasource",
    plugin_name="csv_local",
)

datasource = datasource_registry.create(
    name="csv_local",
    options={"path": "data.csv", "security_level": "official"},
    context=context,
)
```

## Relationship to Other Directories

```text
src/elspeth/
├── core/              ← You are here (framework infrastructure)
│   └── registries, orchestration, validation
│
├── plugins/           ← Plugin implementations
│   ├── nodes/         ← Data flow nodes (sources, transforms, sinks)
│   ├── experiments/   ← Experiment-specific plugins
│   ├── orchestrators/ ← Orchestrator implementations
│   └── utilities/     ← Utility plugins
│
├── config.py          ← Configuration loading (uses core registries)
├── cli.py             ← CLI entrypoint (uses core orchestrator)
└── retrieval/         ← RAG/embedding functionality
```

**Key Distinction:**

- `core/` = Infrastructure and framework
- `plugins/` = Concrete implementations
- `core/` defines protocols, `plugins/` implements them

## Known Issues

1. **Unified registries:**
    - All registry infrastructure and implementations live under `registries/`
    - Legacy root modules have been removed; import exclusively from `elspeth.core.registries.*`

2. **Large Files:**
   - `validation.py` is 31KB - may benefit from splitting
   - Consider extracting validators to separate files

3. **No Clear Grouping at Root:**
   - 21 files at root level
   - See proposal for future reorganization

## Frequently Asked Questions

### Q: Why do we have both `registries/` and the old `*_registry.py` files?

**A:** The new `registries/` package contains both the infrastructure and the canonical implementations. The legacy root-level modules have been removed as part of the 2025-10 restructure—new code must import from `elspeth.core.registries.*`.

### Q: Where do I put a new utility function?

**A:**

- If it's logging-related: `utils/logging.py`
- If it's environment variable-related: `utils/env_helpers.py`
- If it's registry-related: `registries/plugin_helpers.py`
- If it doesn't fit: Consider adding a focused helper in `utils/`

### Q: Why are there so many registry files?

**A:** Each plugin type has its own registry to keep validation schemas and creation logic separate. This follows the single-responsibility principle.

### Q: Where do I find the LLM middleware implementations?

**A:** LLM middleware **implementations** are in `src/elspeth/plugins/nodes/transforms/llm/middleware/`. The **registry** lives in `core/registries/middleware.py`; the legacy `llm_middleware_registry.py` module was removed during the cleanup.

### Q: What's the difference between core/experiments/ and plugins/experiments/?

**A:**

- `core/experiments/` = Experiment **framework** (runner, suite runner, plugin registry)
- `plugins/experiments/` = Experiment **plugin implementations** (row processors, aggregators, validators)

## See Also

- [Plugin Catalogue](plugin-catalogue.md) - Complete list of all plugins
- [Configuration Architecture](configuration-merge.md) - How configuration works
- [Core Restructure Proposal](../roadmap/CORE_DIRECTORY_RESTRUCTURE_PROPOSAL.md) - Proposed future reorganization
- [Data Flow Architecture](data-flow-orchestration.md) - How data flows through the system
