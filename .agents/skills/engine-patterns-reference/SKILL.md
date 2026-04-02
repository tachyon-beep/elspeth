---
name: engine-patterns-reference
description: >
  Engine internals and implementation patterns — composite primary keys, schema contracts,
  header normalization, aggregation timeouts, canonical JSON, retry semantics, secret
  handling, test path integrity, tech stack, source layout, and the attributability test.
  Use when working on engine code, Landscape queries, DAG validation, hashing, secrets,
  or when you need to understand the source tree structure.
---

# Engine Patterns Reference

## Composite Primary Key Pattern: nodes Table

**CRITICAL:** The `nodes` table has a composite primary key `(node_id, run_id)`. This means the same `node_id` can exist in multiple runs when the same pipeline runs multiple times.

**Queries touching `node_states` must use `node_states.run_id` directly:**

```python
# WRONG - Ambiguous join when node_id is reused across runs
query = (
    select(calls_table)
    .join(node_states_table, calls_table.c.state_id == node_states_table.c.state_id)
    .join(nodes_table, node_states_table.c.node_id == nodes_table.c.node_id)  # BUG!
    .where(nodes_table.c.run_id == run_id)
)

# CORRECT - Use denormalized run_id on node_states
query = (
    select(calls_table)
    .join(node_states_table, calls_table.c.state_id == node_states_table.c.state_id)
    .where(node_states_table.c.run_id == run_id)  # Direct filter, no ambiguous join
)
```

**Why:** The `node_states` table has a denormalized `run_id` column (schema comment: "Added for composite FK"). Use it directly instead of joining through `nodes` table. The join on `node_id` alone would match multiple nodes rows when `node_id` is reused.

**If you MUST access columns from `nodes` table:** Use composite join with BOTH keys:

```python
.join(
    nodes_table,
    (node_states_table.c.node_id == nodes_table.c.node_id) &
    (node_states_table.c.run_id == nodes_table.c.run_id)
)
```

## Schema Contracts (DAG Validation)

Transforms can declare field requirements that are validated at DAG construction:

```yaml
# Source guarantees these fields in output
source:
  plugin: csv
  options:
    schema:
      mode: observed
      guaranteed_fields: [customer_id, amount]

# Transform requires these fields in input
transforms:
  - plugin: llm_classifier
    options:
      required_input_fields: [customer_id, amount]
```

The DAG validates that upstream `guaranteed_fields` satisfy downstream `required_input_fields`. For template-based transforms, use `elspeth.core.templates.extract_jinja2_fields()` to discover template dependencies during development.

## Header Normalization and Engine Custody

**Source field names are normalized to valid Python identifiers at the source boundary.** This is non-negotiable — it's not cosmetic cleanup, it's a language boundary requirement.

User-chosen field names must cross multiple language boundaries during pipeline execution: Python attribute access (`row.field`), Jinja2 templates (`{{ row.field }}`), expression parser AST nodes, SQL column names, and JSON keys. Each has different reserved words, quoting rules, and valid character sets. Normalizing once at the source boundary (Tier 3 -> Tier 2 transition) means every downstream consumer gets names that are valid in every context.

**The engine takes custody of the original headers.** The `SchemaContract` preserves `original_name` metadata on every field throughout the pipeline. At the sink boundary, three header modes control output:

| Mode | Output | Use Case |
|------|--------|----------|
| `NORMALIZED` | `customer_id` | Default — pipeline working names |
| `ORIGINAL` | `Customer ID` | Restore what the source provided |
| `CUSTOM` | Explicit mapping | External system handover with specific naming requirements |

This is a **restoration**, not a transformation — the engine preserved the originals as metadata and gives them back on request. The `CUSTOM` mode deliberately refuses to silently fall back to normalized names for unmapped fields, because wrong column names in an external system handover are worse than a crash.

**Collision detection operates on normalized names.** The transform executor (`engine/executors/transform.py`) centrally enforces field collision detection pre-execution for any transform that declares `declared_output_fields`. This is mandatory and engine-level — plugins don't opt in, they declare their output fields and the engine prevents collisions before the transform runs.

## Aggregation Timeout Behavior

Aggregation triggers fire in two ways:

- **Count trigger**: Fires immediately when row count threshold is reached
- **Timeout trigger**: Checked **before** each row is processed

**Known Limitation (True Idle):** Timeout triggers fire when the next row arrives, not during completely idle periods. If no rows arrive, buffered data won't flush until either:

1. A new row arrives (triggering the timeout check)
2. The source completes (triggering end-of-source flush)

For streaming sources that may never end, combine timeout with count triggers, or implement periodic heartbeat rows at the source level.

## Canonical JSON - Two-Phase with RFC 8785

**NaN and Infinity are strictly rejected, not silently converted.** This is defense-in-depth for audit integrity:

```python
import rfc8785

# Two-phase canonicalization
def canonical_json(obj: Any) -> str:
    normalized = _normalize_for_canonical(obj)  # Phase 1: pandas/numpy -> primitives (ours)
    return rfc8785.dumps(normalized)            # Phase 2: RFC 8785/JCS standard serialization
```

- **Phase 1 (our code)**: Normalize pandas/numpy types, reject NaN/Infinity
- **Phase 2 (`rfc8785`)**: Deterministic JSON per RFC 8785 (JSON Canonicalization Scheme)

Test cases must cover: `numpy.int64`, `numpy.float64`, `pandas.Timestamp`, `NaT`, `NaN`, `Infinity`.

## Retry Semantics

- `(token_id, node_id, attempt)` is unique in the `node_states` table (also `(token_id, step_index, attempt)`)
- Each attempt recorded as a separate `node_states` row
- Backoff metadata captured

## Secret Handling

Never store secrets directly - use HMAC fingerprints for audit:

```python
fingerprint = hmac.new(fingerprint_key, secret.encode(), hashlib.sha256).hexdigest()
```

Secrets can be loaded from environment variables (default) or Azure Key Vault via the `secrets:` section in `settings.yaml`:

```yaml
secrets:
  source: keyvault
  vault_url: https://my-vault.vault.azure.net  # Must be literal URL, not env var reference
  mapping:
    AZURE_OPENAI_KEY: azure-openai-key
    ELSPETH_FINGERPRINT_KEY: elspeth-fingerprint-key
```

`vault_url` must be a literal HTTPS URL because secrets are loaded before environment variable resolution. Secret resolutions are recorded in the `secret_resolutions` Landscape table (vault source, HMAC fingerprint, latency).

## Test Path Integrity

**Never bypass production code paths in tests.** BUG-LINEAGE-01 hid for weeks because tests manually built `ExecutionGraph` objects instead of using `from_plugin_instances()`. Manual construction had the correct mapping; the production path had a different (wrong) one. Tests passed, production was broken.

```python
# WRONG - bypasses production logic
graph = ExecutionGraph()
graph.add_node("source", ...)
graph._branch_to_coalesce = {"path_a": "merge1"}  # Tests pass, production breaks

# CORRECT - exercises the real code path
graph = ExecutionGraph.from_plugin_instances(source=source, transforms=transforms, ...)
```

**Rules:** Integration tests MUST use `ExecutionGraph.from_plugin_instances()` and `instantiate_plugins_from_config()`. Manual construction is acceptable only for unit tests of isolated algorithms (topo sort, cycle detection, visualization).

## The Attributability Test

For any output, the system must prove complete lineage:

```python
from elspeth.core.landscape.lineage import explain

lineage = explain(recorder, run_id, token_id=token_id)
assert lineage is not None
assert lineage.source_row is not None
assert len(lineage.node_states) > 0
```

## Technology Stack

### Core Framework

| Component | Technology | Rationale |
| --------- | ---------- | --------- |
| CLI | Typer | Type-safe, auto-generated help |
| TUI | Textual | Interactive terminal UI for `explain`, `status` |
| Configuration | Dynaconf + Pydantic | Multi-source precedence + validation |
| Plugins | pluggy | Battle-tested (pytest uses it) |
| Data | pandas | Standard for tabular data |
| Database | SQLAlchemy Core | Multi-backend without ORM overhead |
| Migrations | Alembic | Schema versioning |
| Retries | tenacity | Industry standard backoff |
| Telemetry | OpenTelemetry (api, sdk, otlp exporter) | Distributed tracing and metrics |

### Acceleration Stack (avoid reinventing)

| Component | Technology | Replaces |
| --------- | ---------- | -------- |
| Canonical JSON | `rfc8785` | Hand-rolled serialization (RFC 8785/JCS standard) |
| DAG Validation | NetworkX | Custom graph algorithms (acyclicity, topo sort) |
| Logging | structlog | Ad-hoc logging (structured events) |
| Rate Limiting | pyrate-limiter | Custom leaky buckets |
| Diffing | DeepDiff | Custom comparison (for verify mode) |
| Property Testing | Hypothesis | Manual edge-case hunting |

### Optional Plugin Packs

| Pack | Technology | Use Case |
| ---- | ---------- | -------- |
| LLM | LiteLLM | 100+ LLM providers unified |
| Azure | azure-storage-blob, azure-identity, azure-keyvault-secrets | Azure cloud integration |
| Telemetry | ddtrace | Datadog APM integration |
| Web | beautifulsoup4, html2text | Web scraping transforms |
| Security | sqlcipher3 | Audit database encryption at rest |
| MCP | mcp | Landscape analysis server protocol |

## Source Layout

```text
src/elspeth/
+-- core/
|   +-- landscape/      # Audit trail storage (recorder, exporter, schema)
|   +-- checkpoint/     # Crash recovery checkpoints
|   +-- dag/            # DAG construction, validation, graph models (NetworkX)
|   +-- rate_limit/     # Rate limiting for external calls
|   +-- retention/      # Payload purge policies
|   +-- security/       # Secret fingerprinting via HMAC, URL/IP validation
|   +-- config.py       # Configuration loading (Dynaconf + Pydantic)
|   +-- canonical.py    # Deterministic JSON hashing (RFC 8785)
|   +-- events.py       # Synchronous event bus for CLI observability
|   +-- expression_parser.py # AST-based expression parsing (no eval)
|   +-- identifiers.py  # ID generation utilities
|   +-- logging.py      # Structured logging setup
|   +-- operations.py   # Operation type definitions
|   +-- payload_store.py # Content-addressable storage for large blobs
|   +-- templates.py    # Jinja2 field extraction
+-- contracts/          # Type contracts, schemas, protocol definitions, hashing primitives, and phase-typed contexts
+-- engine/
|   +-- orchestrator/   # Full run lifecycle management (core, aggregation, export, outcomes, validation)
|   +-- executors/      # Transform, gate, sink, aggregation executors
|   +-- processor.py    # DAG traversal with work queue
|   +-- dag_navigator.py # DAG path navigation
|   +-- coalesce_executor.py # Fork/join barrier with merge policies
|   +-- batch_adapter.py # Batch windowing logic
|   +-- retry.py        # Tenacity-based retry with backoff
|   +-- tokens.py       # Token identity and lineage management
|   +-- triggers.py     # Aggregation trigger evaluation
|   +-- clock.py        # Clock abstraction for testing
|   +-- spans.py        # Telemetry span management
+-- plugins/
|   +-- infrastructure/ # Shared: base classes, protocols, config, clients, batching, pooling
|   +-- sources/        # CSVSource, JSONSource, NullSource, AzureBlobSource
|   +-- transforms/     # FieldMapper, Passthrough, Truncate, LLM, Azure safety, etc.
|   +-- sinks/          # CSVSink, JSONSink, DatabaseSink, AzureBlobSink
+-- telemetry/          # OpenTelemetry exporters and instrumentation
+-- testing/            # ChaosLLM, ChaosWeb, ChaosEngine test servers
|   +-- chaosllm/       # Fake OpenAI/Azure LLM server with error/latency injection
|   +-- chaosweb/       # Fake web server with failure profiles
|   +-- chaosengine/    # Engine-level test utilities
|   +-- chaosllm_mcp/   # MCP server for ChaosLLM metrics and control
+-- mcp/                # Landscape MCP analysis server
|   +-- analyzers/      # Domain-specific analysis tools (contracts, diagnostics, queries, reports)
|   +-- server.py       # MCP server implementation
|   +-- types.py        # MCP type definitions
+-- tui/                # Terminal UI (Textual) - explain screens and widgets
|   +-- screens/        # TUI screen implementations
|   +-- widgets/        # TUI widget components
|   +-- explain_app.py  # Explain TUI application entry point
|   +-- constants.py    # TUI constants
+-- cli.py              # Typer CLI
+-- cli_helpers.py      # CLI utility functions
+-- cli_formatters.py   # Event formatting for CLI output
```

## Offensive Programming Examples

**Examples of good offensive programming:**

```python
# Detect corruption at read time — don't let bad data propagate
try:
    data = json.loads(stored_json)
except json.JSONDecodeError as exc:
    raise AuditIntegrityError(
        f"Corrupt JSON for run {run_id}: database corruption (Tier 1 violation). "
        f"Parse error: {exc}"
    ) from exc

# Validate write-side invariants at construction — reject garbage before it enters the audit trail
@dataclass(frozen=True)
class SecretResolutionInput:
    fingerprint: str
    def __post_init__(self) -> None:
        if len(self.fingerprint) != 64 or not all(c in "0123456789abcdef" for c in self.fingerprint):
            raise ValueError(f"fingerprint must be 64-char lowercase hex, got {self.fingerprint!r}")

# Use atomic guards to prevent TOCTOU races — detect the anomaly, don't just hope it doesn't happen
result = conn.execute(
    update(table).where(table.c.id == id).where(table.c.field.is_(None)).values(field=value)
)
if result.rowcount == 0:
    # Distinguish "not found" from "already set" — different operator actions needed
    existing = conn.execute(select(table.c.field).where(table.c.id == id)).fetchone()
    if existing is not None and existing.field is not None:
        raise AuditIntegrityError(f"Cannot overwrite: field already exists for {id}")
    raise ValueError(f"Record {id} not found")
```

**When to add offensive checks:**

- **Tier 1 read paths**: Data from our own database should be exactly what we expect. If it isn't, crash immediately with context — this is corruption or tampering.
- **Write-side DTOs**: Validate invariants at construction (via `__post_init__`) before data enters the audit trail. Cheaper to reject garbage at the door than to discover it on read.
- **State transitions**: When a method has preconditions (e.g., "contract must not already exist"), assert them with contextual error messages, not silent no-ops.
- **Exception chains**: Always use `from exc` to preserve the original exception chain. `from None` destroys diagnostic information.

### hasattr Alternatives

**`hasattr()` is unconditionally banned.** Everything `hasattr` does can be done more safely:

| Instead of `hasattr` | Use | Why |
|---------------------|-----|-----|
| `hasattr(obj, "attr")` before access | `try: obj.attr` / `except AttributeError:` | `hasattr` swallows all exceptions from `@property` getters, not just missing attributes |
| `hasattr(self, "method_" + name)` for dispatch | Explicit allowset (`frozenset`) + `isinstance` | `hasattr` lets you bypass the gate just by defining a method — no review required |
| `hasattr(e, "field")` on caught exceptions | `isinstance(e, SpecificType)` or direct access | Exception types define their attributes — if the type is in the `except` clause, the attribute exists |
