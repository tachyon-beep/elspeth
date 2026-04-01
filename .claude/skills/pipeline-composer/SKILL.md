---
name: pipeline-composer
description: >
  Use when a user wants to create, modify, or debug an ELSPETH pipeline
  configuration. Covers building pipelines conversationally using the
  elspeth-composer MCP tools — plugin discovery, state mutation, validation,
  YAML generation, and session persistence. Also use when reviewing or
  explaining existing pipeline YAML.
---

# Pipeline Composer

Build ELSPETH pipeline configurations conversationally using the `elspeth-composer` MCP tools. These are the same tools the web UI's LLM composer uses — plugin discovery, state mutation, validation, and YAML generation.

## Workflow

1. **`new_session`** — start a composition session (persisted in `.scratch/`)
2. **Discover** — `list_sources`, `list_transforms`, `list_sinks`, `get_plugin_schema`
3. **Build** — `set_pipeline` for complete pipelines, or individual tools for edits
4. **Validate** — every mutation returns validation; fix errors before proceeding
5. **Generate** — `generate_yaml` to produce the pipeline YAML
6. **Save** — `save_session` to persist; `load_session` to resume later

## Building a Pipeline

### Prefer `set_pipeline` for Complete Pipelines

When building a pipeline from scratch, use `set_pipeline` to set everything atomically:

```json
{
  "source": {"plugin": "csv", "on_success": "gate_in", "options": {...}, "on_validation_failure": "discard"},
  "nodes": [{"id": "my_gate", "node_type": "gate", "input": "gate_in", "condition": "row['amount'] > 1000", "routes": {"true": "high", "false": "normal"}}],
  "edges": [],
  "outputs": [{"name": "normal", "plugin": "csv", "options": {...}, "on_write_failure": "discard"}, {"name": "high", "plugin": "csv", "options": {...}, "on_write_failure": "discard"}],
  "metadata": {"name": "My Pipeline", "description": "What it does"}
}
```

Use individual tools (`patch_node_options`, `upsert_node`, `remove_node`) for incremental edits after the pipeline exists.

### Always Discover Before Configuring

Never guess plugin names or option fields. Always call:
- `list_sources` / `list_transforms` / `list_sinks` — see what's available
- `get_plugin_schema` — get the exact JSON Schema for a plugin's options

### Connection Model (DAG Wiring)

Nodes connect via named connection points:

```
source.on_success = "gate_in"  →  gate.input = "gate_in"
gate.routes.true = "high"      →  sink named "high"
gate.routes.false = "normal"   →  sink named "normal"
```

Every pipeline needs: **one source**, **one or more sinks**, and **connections between them**. Orphan nodes cause validation errors.

### Node Types

| Type | Required fields | Key behaviour |
|------|----------------|---------------|
| `transform` | `plugin`, `on_success`, `on_error` | Processes rows, emits to on_success |
| `gate` | `condition`, `routes` | Evaluates expression, routes by result |
| `aggregation` | `plugin`, trigger config | Batches rows until trigger fires |
| `coalesce` | `branches` (min 2) | Merges tokens from parallel fork paths |

### Gate Expressions

Restricted expression language. Key rules:

- **Allowed:** `row['field']`, `row.get('field')`, `len()`, `abs()`, comparisons, boolean ops, arithmetic, membership, ternary
- **Forbidden:** `row.get('field', default)` (defaults fabricate data), `int()`, `str()`, `float()`, `bool()` (not needed — source schema guarantees types)
- **Boolean routes** must use `"true"` / `"false"` as keys
- Call `get_expression_grammar` for the full reference

### Validation

Every mutation tool returns validation state:

```json
{"is_valid": true, "errors": [], "warnings": [...], "suggestions": [...]}
```

**Never present a pipeline as complete until `is_valid` is `true`.** If errors exist, fix them. Use `explain_validation_error` for unclear errors.

## Available Plugins

**Sources:** `csv`, `json`, `text`, `azure_blob`, `dataverse`, `null`

**Transforms:** `passthrough`, `field_mapper`, `truncate`, `keyword_filter`, `json_explode`, `batch_stats`, `batch_replicate`, `web_scrape`, `llm`, `azure_content_safety`, `azure_prompt_shield`, `azure_batch_llm`, `openrouter_batch_llm`, `rag_retrieval`

**Sinks:** `csv`, `json`, `database`, `azure_blob`, `dataverse`, `chroma_sink`

## Common Patterns

### Simple routing (gate)
Source → gate (condition) → sink A / sink B

### Transform chain
Source → transform 1 → transform 2 → sink

### LLM classification
Source → `llm` transform (with template) → gate on LLM output → sinks

### Fork/join (parallel analysis)
Source → fork gate → path A transform + path B transform → coalesce → sink

## Session Management

Sessions persist as JSON in `.scratch/`. Use `list_sessions` to see saved work, `load_session` to resume, `delete_session` to clean up.

## Reference

Full tool documentation: `docs/reference/composer-tools.md`
Full config reference: `docs/reference/configuration.md`
