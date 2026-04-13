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

## Plugin Capabilities Registry

### Sources

| Plugin | Description | Input | Secrets | Network | Key Options |
|--------|-------------|-------|---------|---------|-------------|
| `csv` | Read CSV/TSV files | file path | no | no | `path`, `delimiter`, `encoding`, `skip_rows`, `columns`, `field_mapping` |
| `json` | Read JSON array or JSONL files | file path | no | no | `path`, `format` (json/jsonl), `data_key`, `encoding`, `field_mapping` |
| `text` | Read text file, one line per row | file path | no | no | `path`, `column` (output field name), `strip_whitespace`, `skip_blank_lines` |
| `azure_blob` | Read from Azure Blob Storage | cloud blob | yes | yes | `container`, `blob_path`, `format`, auth config |
| `dataverse` | Query Dataverse via OData or FetchXML | API query | yes | yes | `environment_url`, `entity`+`select`+`filter` OR `fetch_xml`, auth config |
| `null` | Empty source for resume operations | none | no | no | (internal use) |

### Transforms

| Plugin | Description | Stateful | Secrets | Network | Adds/Changes Fields |
|--------|-------------|----------|---------|---------|---------------------|
| `passthrough` | Identity — passes rows unchanged | no | no | no | (none) |
| `field_mapper` | Rename fields | no | no | no | Renames specified fields |
| `truncate` | Truncate text fields to max length | no | no | no | Truncates in-place |
| `keyword_filter` | Filter rows by keyword presence | no | no | no | (routing only) |
| `json_explode` | Expand nested JSON into row fields | no | no | no | Promotes nested fields |
| `batch_stats` | Compute batch statistics | **yes** | no | no | Emits aggregate rows |
| `batch_replicate` | Replicate rows for fan-out | no | no | no | Emits N copies per row |
| `web_scrape` | Fetch content from URLs | no | no | yes | Adds `content` field |
| `llm` | Send row data to LLM via template | no | yes | yes | Adds `llm_response` field |
| `azure_content_safety` | Content moderation | no | yes | yes | Adds safety scores |
| `azure_prompt_shield` | Jailbreak detection | no | yes | yes | Adds shield results |
| `azure_batch_llm` | Azure batch LLM processing | no | yes | yes | Adds response field |
| `openrouter_batch_llm` | OpenRouter batch processing | no | yes | yes | Adds response field |
| `rag_retrieval` | Retrieve from vector store | no | yes | depends | Adds retrieval results |
| `type_coerce` | Convert field types | no | no | no | Coerces in-place |
| `value_transform` | Compute fields via expressions | no | no | no | Adds/modifies fields |

### Sinks

| Plugin | Description | Secrets | Network | Key Options |
|--------|-------------|---------|---------|-------------|
| `csv` | Write CSV file | no | no | `path`, `delimiter`, `mode`, `headers` |
| `json` | Write JSON/JSONL file | no | no | `path`, `format`, `indent`, `mode`, `headers` |
| `database` | Write to SQL database | yes | depends | `url`, `table`, `if_exists` |
| `azure_blob` | Upload to Azure Blob Storage | yes | yes | `container`, `blob_path`, `format`, auth config |
| `dataverse` | Upsert to Dataverse | yes | yes | `environment_url`, `entity`, `field_mapping`, `alternate_key` |
| `chroma_sink` | Store in ChromaDB | depends | depends | `collection`, `mode`, `document_field`, `id_field` |

## Plugin Quick Reference

### Sources

**csv** — Read delimited files (CSV, TSV) into rows.
Minimal config: `{"path": "data.csv"}`
Gotchas:
- Headers are auto-normalized to identifiers (`"First Name"` becomes `first_name`) — use `field_mapping` if you need specific names.

**json** — Read a JSON array of objects or a JSONL file.
Minimal config: `{"path": "data.json"}`
Gotchas:
- If your JSON is wrapped (e.g., `{"results": [...]}`), you must set `data_key` to the array key — without it, the source sees one object, not many rows.

**text** — Read a text file, one line per row.
Minimal config: `{"path": "input.txt", "column": "line"}`
Gotchas:
- `column` is required — it names the single output field. Omitting it is a validation error.

### Transforms

**web_scrape** — Fetch and extract content from a URL in each row.
Minimal config: `{"url_field": "url"}`
Gotchas:
- You must specify `url_field` — the name of the row field containing the URL to fetch. There is no default.

**llm** — Send row data to an LLM using a Jinja2 template.
Minimal config: `{"template": "Summarise: {{ row['text'] }}", "provider": "openrouter", "model": "anthropic/claude-3.5-sonnet"}`
Gotchas:
- The response is always a **string** in `llm_response` (or custom `response_field`), even if the model returns JSON. Use `json_explode` after this step to parse structured output.
- Templates use `{{ row['field_name'] }}` syntax. List all referenced fields in `required_input_fields`.

**keyword_filter** — Route rows based on keyword presence in a field.
Minimal config: `{"field": "text", "keywords": ["urgent", "critical"]}`
Gotchas:
- Matching is **case-insensitive by default**. Set `case_sensitive: true` if you need exact case matching.

**json_explode** — Expand a nested JSON string field into top-level row fields.
Minimal config: `{"field": "llm_response"}`
Gotchas:
- The `field` must contain a valid JSON string. Typically used after an `llm` step — make sure the LLM template instructs the model to return JSON.

**field_mapper** — Rename fields in each row.
Minimal config: `{"mapping": {"old_name": "new_name"}}`

**type_coerce** — Convert field types (str→int, str→float, str→bool, *→str).
Minimal config: `{"conversions": [{"field": "price", "to": "float"}]}`
Gotchas:
- Strict coercion only — "3.5" won't coerce to int, bool only accepts 0/1/true/false strings.
- Use before `value_transform` when source data has string types that need numeric operations.

**value_transform** — Compute new or modified field values using expressions.
Minimal config: `{"operations": [{"target": "total", "expression": "row['price'] * row['quantity']"}]}`
Gotchas:
- Operations run sequentially — later operations can reference fields computed by earlier ones.
- Only safe expressions allowed (no function calls like `round()`, `len()`, etc.).

### Sinks

**csv** — Write rows to a CSV file.
Minimal config: `{"path": "output.csv"}`

**json** — Write rows to a JSON or JSONL file.
Minimal config: `{"path": "output.json"}`
Gotchas:
- Default format is `json` (single array). Set `format: "jsonl"` for one record per line — important for large outputs or streaming consumers.

## Source Semantics

**csv**: Headers normalized to identifiers. Use `columns` for headerless files, `field_mapping` for overrides.

**json**: Array of objects or JSONL. Use `data_key` for wrapped arrays (e.g., `{"results": [...]}`). Format auto-detected from extension.

**text**: One line per row, single field. `column` option required (the field name).

**Blob wiring**: `set_source_from_blob` infers plugin from MIME: `text/csv`→csv, `application/json`→json, `text/plain`→text.

**Schema modes**: `observed` (infer from data), `fixed` (exact fields, reject extras), `flexible` (known fields + extras OK). Fields: `"name: type"` where type is str/int/float/bool/any.

### Inline data (no file upload needed)

When the user provides data directly in conversation (a URL, a JSON snippet, a few CSV rows), create a blob and wire it as the source:

1. `create_blob` with content and MIME type → returns `blob_id`
2. `set_source_from_blob` with the `blob_id`

No separate "inline source" plugin exists — the blob system handles it. Never ask the user to upload a file when the data is already in the conversation.

**Examples:**
- URL → `create_blob(filename="input.txt", mime_type="text/plain", content="https://example.com")` then `set_source_from_blob`
- JSON → `create_blob(filename="data.json", mime_type="application/json", content='[{"id": 1}]')` then `set_source_from_blob`
- CSV rows → `create_blob(filename="data.csv", mime_type="text/csv", content="name,age\nAlice,30")` then `set_source_from_blob`

## Validation Warning Glossary

### Warnings (non-blocking)

| Warning | Meaning | Fix |
|---------|---------|-----|
| Output '{name}' is not referenced by any on_success, on_error, or route | Orphaned output — nothing sends data to it | Match the output name to a node's on_success/route |
| Source on_success '{target}' does not match any node input or output | Source sends data to a nonexistent connection point | Fix source on_success to match a node input or output name |
| Node '{id}' has no outgoing edges | Processing step produces output that goes nowhere | Set the node's on_success to an output or downstream node |
| Output '{name}' uses plugin '{plugin}' but filename extension suggests a different format | Sink plugin doesn't match file extension | Change extension or plugin to match |

### Suggestions (optional)

| Suggestion | Meaning | Fix |
|------------|---------|-----|
| Consider adding error routing | Transform failures have no dedicated destination | Add an error output and wire on_error to it |
| Single output pipeline — consider adding a second output for rejected rows | No place for problem records | Add a quarantine/error output |
| Source has no explicit schema | Downstream field references depend on runtime column names | Add explicit schema with expected field names and types |

## Common Patterns

### 1. URL → Scrape → Extract → JSON
`text` source → `web_scrape` → `llm` (extraction template) → `json` sink

### 2. File → Classify → Route
`csv`/`json` source → `llm` (classification) → `gate` (on response) → multiple sinks

### 3. File → Summarise → Save
`csv`/`json`/`text` source → `llm` (summarisation) → `json` sink

### 4. Batch LLM Over Rows
`csv`/`json` source → `llm` (row template with `{{ row['field'] }}`) → `csv`/`json` sink

### 5. Content Moderation
`csv` source → `azure_content_safety` → `gate` (severity threshold) → approved/flagged sinks

### 6. RAG Retrieval + Generation
source → `rag_retrieval` → `llm` (uses retrieved context) → `json` sink

### 7. Transform Chain with Error Diversion
source → transform A (on_error → errors sink) → transform B → results sink + errors sink

### 8. Fork/Join Enrichment
source → fork gate → path A + path B → `coalesce` → sink

## Execution Shape Reference

Most transforms **add** fields — original row fields are preserved. Key exceptions:
- `batch_stats`: **replaces** input rows with aggregate results
- `gate`: routes unchanged row (no field changes)
- LLM response is always a **string** — use `json_explode` after LLM to parse into structured fields
- Sinks serialize the **full row** (all accumulated fields)

## LLM Provider Configuration

| Provider | Config | Secret | Model ID |
|----------|--------|--------|----------|
| Azure OpenAI | `provider: "azure"` | Credential-based | Uses `deployment_name` |
| OpenRouter | `provider: "openrouter"` | `OPENROUTER_API_KEY` | `provider/model-name` |

## Session Management

Sessions persist as JSON in `.scratch/`. Use `list_sessions` to see saved work, `load_session` to resume, `delete_session` to clean up.

## Reference

Full tool documentation: `docs/reference/composer-tools.md`
Full config reference: `docs/reference/configuration.md`
