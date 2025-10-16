# Core Directory Structure (Current)

**Last Updated:** 2025-10-17
**Status:** Current structure as of PR #4

> **Note:** A future reorganization is proposed in [docs/roadmap/CORE_DIRECTORY_RESTRUCTURE_PROPOSAL.md](../roadmap/CORE_DIRECTORY_RESTRUCTURE_PROPOSAL.md). This document describes the **current** structure.

## Quick Reference

```
src/elspeth/core/
├── Registries (Plugin Factories)
│   ├── registries/                  - Canonical registry package
│   │   ├── datasource.py            - Datasource plugin registry
│   │   ├── llm.py                   - LLM client plugin registry (hosts `create_llm_from_definition`)
│   │   ├── middleware.py            - LLM middleware registry
│   │   ├── sink.py                  - Output sink plugin registry
│   │   ├── utility.py               - Utility plugin registry
│   │   ├── base.py                  - Base registry infrastructure
│   │   ├── plugin_helpers.py        - Shared helper functions
│   │   └── context_utils.py         - Context derivation helpers
│   ├── registry/                    - Deprecated shim package forwarding to `registries/`
│   ├── datasource_registry.py       - Deprecated shim → `registries.datasource`
│   ├── llm_registry.py              - Deprecated shim → `registries.llm`
│   ├── llm_middleware_registry.py   - Deprecated shim → `registries.middleware`
│   ├── sink_registry.py             - Deprecated shim → `registries.sink`
│   └── utility_plugin_registry.py   - Deprecated shim → `registries.utility`
│
├── Orchestration & Pipeline
│   ├── orchestrator.py              - Main experiment orchestrator
│   ├── artifact_pipeline.py         - Sink dependency resolution
│   ├── artifacts.py                 - Artifact type definitions
│   └── processing.py                - Processing utilities
│
├── Configuration & Validation
│   ├── config_schema.py             - Configuration schemas
│   ├── config_validation.py         - Configuration validation
│   ├── validation.py                - Main validation logic (31K - large!)
│   └── validation_base.py           - Base validation classes
│
├── Core Abstractions
│   ├── protocols.py                 - Protocol definitions (DataSource, Sink, etc.)
│   ├── types.py                     - Core type definitions
│   ├── schema.py                    - JSON schema utilities
│   └── plugin_context.py            - Plugin context system
│
├── Utilities
│   ├── logging.py                   - Logging infrastructure
│   ├── env_helpers.py               - Environment variable helpers
│   └── utilities/                   - Placeholder package (currently empty; reserved for future shared helpers)
│
└── Subsystems (Subdirectories)
    ├── experiments/                 - Experiment runner, suite runner
    ├── controls/                    - Rate limiters, cost trackers
    ├── security/                    - Security controls, PII validation
    └── prompts/                     - Prompt rendering
```

## Navigation Guide

### "I need to understand the plugin system"

- **Start here:** `protocols.py` - Core protocol definitions
- **Then:** `plugin_context.py` - How context flows through plugins
- **Registry base:** `registries/base.py` - Base registry framework
- **Specific registries:** `registries/*.py` modules (root `*_registry.py` files remain as shims)

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
- **Sink ordering:** `artifact_pipeline.py`

### "I need to add configuration validation"

- **Schema definitions:** `config_schema.py`
- **Validation logic:** `config_validation.py`
- **Base validation classes:** `validation_base.py`
- **Main validator:** `validation.py` (⚠️ 31K - large file)

### "I need to work with security/rate limiting/prompts"

- **Security:** `security/` subdirectory
- **Rate limiting:** `controls/rate_limiter_registry.py`
- **Cost tracking:** `controls/cost_tracker_registry.py`
- **Prompts:** `prompts/` subdirectory

## File Size Reference

**Large Files** (>10KB - may need refactoring):

- `validation.py` - 31K ⚠️ Very large
- `schema.py` - 18K
- `registries/sink.py` - 18K
- `artifact_pipeline.py` - 15K
- `logging.py` - 14K
- `types.py` - 13K

**Medium Files** (5-10KB):

- `protocols.py` - 8.9K
- `config_validation.py` - 9.3K
- `registries/llm.py` - 8.5K
- `validation_base.py` - 7.6K
- `orchestrator.py` - 6.9K
- `registries/datasource.py` - 6.2K
- `plugin_context.py` - 5.3K

**Small Files** (<5KB):

- All others

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
from elspeth.core.protocols import (
    DataSource,
    ResultSink,
    LLMClientProtocol,
    LLMMiddleware,
)

# Plugin Context
from elspeth.core.plugin_context import PluginContext, apply_plugin_context

# Validation
from elspeth.core.validation_base import ConfigurationError, validate_schema
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
from elspeth.core.plugin_context import PluginContext

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

1. **Registry Split (in transition):**
    - Canonical infrastructure and implementations live in the `registries/` package
    - Legacy root modules (`*_registry.py`) remain temporarily as compatibility shims
    - Be sure to import from `elspeth.core.registries.*` in new code

2. **Large Files:**
   - `validation.py` is 31KB - may benefit from splitting
   - Consider extracting validators to separate files

3. **No Clear Grouping at Root:**
   - 21 files at root level
   - See proposal for future reorganization

## Frequently Asked Questions

### Q: Why do we have both `registries/` and the old `*_registry.py` files?

**A:** The new `registries/` package contains both the infrastructure and the canonical implementations. The legacy root-level modules and the `registry/` directory now only forward to the new package to keep older imports working during the migration.

### Q: Where do I put a new utility function?

**A:**

- If it's logging-related: `logging.py`
- If it's environment variable-related: `env_helpers.py`
- If it's registry-related: `registries/plugin_helpers.py`
- If it doesn't fit: Consider creating a new file or `utilities/` subdirectory

### Q: Why are there so many registry files?

**A:** Each plugin type has its own registry to keep validation schemas and creation logic separate. This follows the single-responsibility principle.

### Q: Where do I find the LLM middleware implementations?

**A:** LLM middleware **implementations** are in `src/elspeth/plugins/nodes/transforms/llm/middleware/`. The **registry** now lives in `core/registries/middleware.py` (the root `llm_middleware_registry.py` module remains only as a compatibility shim).

### Q: What's the difference between core/experiments/ and plugins/experiments/?

**A:**

- `core/experiments/` = Experiment **framework** (runner, suite runner, plugin registry)
- `plugins/experiments/` = Experiment **plugin implementations** (row processors, aggregators, validators)

## See Also

- [Plugin Catalogue](plugin-catalogue.md) - Complete list of all plugins
- [Configuration Architecture](configuration-merge.md) - How configuration works
- [Core Restructure Proposal](../roadmap/CORE_DIRECTORY_RESTRUCTURE_PROPOSAL.md) - Proposed future reorganization
- [Data Flow Architecture](data-flow-orchestration.md) - How data flows through the system
