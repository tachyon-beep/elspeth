# Core Directory Structure (Current)

**Last Updated:** 2025-10-17
**Status:** Current structure as of PR #4

> **Note:** A future reorganization is proposed in [docs/archive/roadmap/CORE_DIRECTORY_RESTRUCTURE_PROPOSAL.md](../archive/roadmap/CORE_DIRECTORY_RESTRUCTURE_PROPOSAL.md). This document describes the **current** structure.

## Quick Reference

```
src/elspeth/core/
├── Registries (Plugin Factories)
│   ├── datasource_registry.py       - Datasource plugin registry
│   ├── llm_registry.py              - LLM client plugin registry
│   ├── llm_middleware_registry.py   - Middleware plugin registry
│   ├── sink_registry.py             - Output sink plugin registry
│   ├── utility_plugin_registry.py   - Utility plugin registry
│   └── registry/                    - Base registry infrastructure
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
│   └── env_helpers.py               - Environment variable helpers
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
- **Registry base:** `registry/base.py` - Base registry framework
- **Specific registries:** `*_registry.py` files at root

### "I need to create/register a new plugin"
- **Datasource:** See `datasource_registry.py`
- **LLM Client:** See `llm_registry.py`
- **Middleware:** See `llm_middleware_registry.py`
- **Sink:** See `sink_registry.py`
- **Utility:** See `utility_plugin_registry.py`
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
- `sink_registry.py` - 18K
- `artifact_pipeline.py` - 15K
- `logging.py` - 14K
- `types.py` - 13K
- `registry.py` - 11K (facade - minimal use)

**Medium Files** (5-10KB):
- `protocols.py` - 8.9K
- `config_validation.py` - 9.3K
- `llm_registry.py` - 8.5K
- `validation_base.py` - 7.6K
- `orchestrator.py` - 6.9K
- `datasource_registry.py` - 6.2K
- `plugin_context.py` - 5.3K

**Small Files** (<5KB):
- All others

## Import Patterns

### Common Imports

```python
# Registries
from elspeth.core.datasource_registry import datasource_registry
from elspeth.core.llm_registry import llm_registry
from elspeth.core.llm_middleware_registry import llm_middleware_registry
from elspeth.core.sink_registry import sink_registry

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
from elspeth.core.datasource_registry import datasource_registry
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

```
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

1. **Empty Directories:**
   - `core/llm/` - Empty (only `__pycache__`)
   - `core/plugins/` - Empty (only `__pycache__`)
   - **Action:** Will be deleted after PR #4 merges

2. **Registry Split:**
   - Infrastructure in `registry/` subdirectory
   - Implementations at root level (`*_registry.py`)
   - Can be confusing which is which

3. **Large Files:**
   - `validation.py` is 31KB - may benefit from splitting
   - Consider extracting validators to separate files

4. **No Clear Grouping at Root:**
   - 21 files at root level
   - See proposal for future reorganization

## Frequently Asked Questions

### Q: Why are some registries at root and some in registry/?
**A:** The `registry/` subdirectory contains the **base infrastructure** (base classes, helpers). The root-level `*_registry.py` files are **specific registry implementations**. This split is a historical artifact and may be consolidated in a future refactoring.

### Q: Where do I put a new utility function?
**A:**
- If it's logging-related: `logging.py`
- If it's environment variable-related: `env_helpers.py`
- If it's registry-related: `registry/plugin_helpers.py`
- If it doesn't fit: Consider creating a new file or `utilities/` subdirectory

### Q: Why are there so many registry files?
**A:** Each plugin type has its own registry to keep validation schemas and creation logic separate. This follows the single-responsibility principle.

### Q: Where do I find the LLM middleware implementations?
**A:** LLM middleware **implementations** are in `src/elspeth/plugins/nodes/transforms/llm/middleware/`. The **registry** is in `core/llm_middleware_registry.py`.

### Q: What's the difference between core/experiments/ and plugins/experiments/?
**A:**
- `core/experiments/` = Experiment **framework** (runner, suite runner, plugin registry)
- `plugins/experiments/` = Experiment **plugin implementations** (row processors, aggregators, validators)

## See Also

- [Plugin Catalogue](plugin-catalogue.md) - Complete list of all plugins
- [Configuration Architecture](configuration-merge.md) - How configuration works
- [Core Restructure Proposal](../archive/roadmap/CORE_DIRECTORY_RESTRUCTURE_PROPOSAL.md) - Proposed future reorganization
- [Data Flow Architecture](data-flow-orchestration.md) - How data flows through the system
