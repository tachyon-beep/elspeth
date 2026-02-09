# ADR: Declarative DAG Wiring — Explicit Input/Output Connections on All Nodes

**Status:** Approved (P3 future extension)
**Bead:** `elspeth-rapid-tbia`
**Date:** 2026-02-09
**Decision Makers:** Architecture Review Board
**Depends On:** ADR-explicit-sink-routing (`elspeth-rapid-o639`), processor refactoring (new prerequisite)
**Review Board Verdict:** Unanimous Approve (3/3) with conditions — all incorporated below

## Context

The `on_success` ADR (elspeth-rapid-o639) makes output routing explicit — every terminal node declares where its output goes. But input routing remains implicit: transforms receive data based on YAML list position. The DAG builder infers edges from ordering.

This creates two description models coexisting in one YAML:
- **Outputs**: Explicit (`on_success: sink_name`, gate `routes:`)
- **Inputs**: Implicit (position in list, fork branch association via gate `fork_to:`)

For simple linear pipelines, implicit inputs are fine. For complex topologies (forks, diamonds, multi-path convergence), the implicit wiring becomes opaque — you have to mentally walk the ordered list and fork annotations to understand the dataflow.

### Architectural Pattern: Positional Encoding

The current model encodes graph topology in list ordering — a form of *positional encoding* where information is carried by arrangement rather than declaration. This creates invisible invariants: the meaning of `transforms[2]` depends on the existence and position of `transforms[0]` and `transforms[1]`. Insert a new node at position 1 and you've implicitly rewired everything downstream without touching any explicit configuration.

This pattern is a known fragility in ordered-list-as-graph representations. Systems that moved from implicit to explicit wiring (Apache Beam, Airflow, dbt, Terraform) all succeeded architecturally. dbt's `ref()` model is the closest analogue — every model explicitly declares its upstream dependencies, creating a fully declarative DAG. dbt has 50,000+ active projects and nobody complains about `ref()` being too verbose — because explicitness IS the feature for data lineage.

### Current Model (Post on_success ADR)

```yaml
source:
  plugin: csv
  options:
    path: input.csv
    on_success: output

transforms:
  - plugin: enricher           # implicitly receives from source (position 0)
  - plugin: validator          # implicitly receives from enricher (position 1)
    on_success: output

sinks:
  output: { plugin: csv }
```

Edges are inferred: source → enricher (position), enricher → validator (position), validator → output (explicit `on_success`). Two implicit edges, one explicit.

### Proposed Model (Fully Declarative)

```yaml
source:
  plugin: csv
  options:
    path: input.csv
  on_success: enrichment        # named output connection

transforms:
  - plugin: enricher
    name: enricher
    input: enrichment           # explicit: receives from source
    on_success: validation      # named output connection

  - plugin: validator
    name: validator
    input: validation           # explicit: receives from enricher
    on_success: output          # routes to sink

sinks:
  output: { plugin: csv }
```

Every edge is explicit. The YAML IS the graph.

## Decision

### Add `input: str` to Transform, Gate, Aggregation, and Coalesce Settings

Every processing node declares where it receives data:

```python
class TransformSettings(BaseModel):
    input: str                    # NEW: named input connection
    on_success: str | None = None # from on_success ADR
    on_error: str | None = None   # existing
```

### Named Connections Replace Positional Ordering

Connections are named strings that link one node's output to another node's input. They are **edge labels** in the DAG.

```yaml
source:
  on_success: raw_data           # source outputs to "raw_data"

transforms:
  - plugin: enricher
    input: raw_data              # enricher reads from "raw_data"
    on_success: enriched         # enricher outputs to "enriched"

  - plugin: classifier
    input: enriched              # classifier reads from "enriched"
    on_success: results_sink     # classifier outputs to sink
```

The DAG builder matches `on_success` values to `input` values to create MOVE edges. Validation rules:
- A connection name in `on_success` that appears in no `input` and is not a sink name → `GraphValidationError` (dangling output)
- A connection name in `input` that appears in no `on_success` and is not a source output → `GraphValidationError` (missing input)
- A connection name that collides with a sink name → `GraphValidationError` (namespace collision — see Q1 resolution below)
- Two transforms with the same `input` value → `GraphValidationError` (ambiguous fan-out — use a gate for explicit splitting)
- Error messages should include Levenshtein-distance suggestions for near-miss typos

### Connection and Sink Namespaces Are Separate

Connection names (internal wiring between nodes) and sink names (terminal destinations) occupy **separate namespaces**. A connection name that matches a sink name is a validation error.

- `on_success: enriched` where `enriched` is an `input:` on another transform → connection (MOVE edge to next node)
- `on_success: output_sink` where `output_sink` is a configured sink → terminal routing (MOVE edge to sink)
- `on_success: foo` where `foo` is BOTH a connection and a sink → `GraphValidationError` ("Connection name 'foo' collides with sink name 'foo'")

This prevents action-at-a-distance bugs where adding a new sink silently reroutes an existing connection.

### Gate Routes Become Connection Names

Gate `routes:` values can be connection names (feeding downstream transforms) or sink names (terminal routing):

```yaml
gates:
  - name: splitter
    input: enriched
    condition: "row['score'] > 0.8"
    routes:
      "true": premium_path       # connection to downstream transform
      "false": standard_path     # connection to downstream transform

transforms:
  - plugin: premium_enricher
    input: premium_path          # fed by gate's "true" route
    on_success: premium_sink

  - plugin: standard_enricher
    input: standard_path         # fed by gate's "false" route
    on_success: standard_sink
```

Gate route values that are connection names feed downstream transforms. Gate route values that are sink names are terminal routing decisions (existing behavior).

### Fork/Join Becomes Natural

Fork is expressed when a gate's routes feed multiple downstream transforms. Join (coalesce) is explicit when a coalesce node declares multiple inputs:

```yaml
gates:
  - name: forker
    input: enriched
    condition: "True"
    routes:
      "all": fork
    fork_to: [analysis_a, analysis_b]

transforms:
  - plugin: analyzer_a
    input: analysis_a
    on_success: merge_input_a

  - plugin: analyzer_b
    input: analysis_b
    on_success: merge_input_b

coalesce:
  - name: merger
    inputs: [merge_input_a, merge_input_b]   # multiple inputs
    on_success: final_sink
```

### Source-Only Pipeline

```yaml
source:
  plugin: csv
  options:
    path: input.csv
  on_success: output             # direct connection to sink

sinks:
  output: { plugin: csv }
```

No transforms, no `input:` fields needed. Source → sink via named connection.

## Prerequisites

### Prerequisite 1: on_success ADR (elspeth-rapid-o639)

The on_success ADR must be implemented first. It establishes the `on_success` field on protocols and config, removes `default_sink`, and creates the explicit output routing foundation.

### Prerequisite 2: Processor Refactoring (new work item)

**CRITICAL:** The processor (`engine/processor.py`) currently uses positional step indices to traverse transforms:

- `_WorkItem.start_step` is a positional index threaded through the entire work queue
- `transforms[start_step:]` slicing for continuation after forks, coalesce, aggregation
- `start_step + step_offset + 1` arithmetic for audit step numbers
- Fork children, coalesce merges, and aggregation flushes all compute `next_step` as positional offsets
- 20+ references to `start_step` across the processor

The processor fundamentally models execution as "walk a list from position N." This means it depends on the transforms list being in topological order. The declarative wiring ADR allows YAML order to be cosmetic — which breaks this assumption.

**The processor must be refactored to follow DAG edges (via `node_id`) instead of positional indices (via `start_step`).** This is a separate work item that must be completed BEFORE declarative wiring. Doing both simultaneously doubles the blast radius.

**Transitional constraint:** Until the processor is refactored, YAML order must match topological order. The DAG builder validates this: if a transform's `input:` references a connection produced by a later YAML entry, `GraphValidationError` is raised with a message like "Transform 'X' with `input: Y` must appear after the node that produces 'Y'. Reorder your transforms list."

After processor refactoring, this constraint is lifted and YAML order becomes purely cosmetic.

## Impact Analysis

### What Changes

| Area | Change | Scope |
|------|--------|-------|
| `core/config.py` | Add `input:` field to `TransformSettings`, `GateSettings`, `AggregationSettings`, `CoalesceSettings` | ~20 lines |
| `core/dag.py` | Replace positional edge inference with connection-name matching in `from_plugin_instances()` | ~200 lines (rewrite of edge creation) |
| `core/dag.py` | Add connection validation (dangling outputs, missing inputs, namespace collisions, near-miss suggestions) | ~80 lines |
| `engine/processor.py` | Refactored to use `node_id` instead of `start_step` (prerequisite, separate work item) | ~200 lines |
| `plugins/protocols.py` | No change — `input` is a config/wiring concern, not a plugin concern | 0 |
| All example YAMLs | Add `input:` to every transform/gate | All examples |
| All tests | Update pipeline construction | Broad (~800+ refs) |

### What Doesn't Change

- **Executors**: Return results. Don't know about wiring.
- **Orchestrator**: Routes tokens through DAG edges. No change (once processor refactored).
- **Landscape**: Records node_states and routing_events. No change.
- **Plugin protocols**: Plugins don't know about wiring — they receive rows and return results.

### Blast Radius (Quantified)

| Metric | Count | Notes |
|--------|-------|-------|
| `from_plugin_instances()` calls | 129 across 35 files | Every call gains `input:` on all transforms |
| `fork_to` refs | 201 across 31 files | Verify `fork_to` ↔ `input:` wiring |
| Transform list construction | 233 across 46 files | Every transform list needs `input:` added |
| Example YAMLs | 26 settings files | Add `input:` + `on_success:` to every node |
| **Estimated total** | **~800+ refs** | Larger than on_success ADR (~472 refs) |

**Critical leverage points:**
- `tests/fixtures/pipeline.py` — single highest-leverage file (cascades to 20+ test files)
- `tests/unit/core/test_dag.py` — most affected test file (37 `from_plugin_instances`, 22 `fork_to`)
- `tests/fixtures/factories.py` — factory infrastructure

## Risks

### R1: Configuration verbosity (MEDIUM)

A 3-transform linear pipeline goes from 0 wiring lines to 6 (3 `input:` + 3 `on_success:`). Mitigated by scaffold tooling (`elspeth scaffold`). Verbosity is the feature for an auditability framework — the YAML is the auditable artifact.

### R2: Namespace confusion (LOW if separate namespaces enforced)

Connection names colliding with sink names was identified as the primary risk loop. Mitigated by the review board's decision to use separate namespaces with collision-as-error validation.

### R3: DAG construction rewrite (HIGH)

`from_plugin_instances()` is ~500 lines and the single most critical function for pipeline correctness. Rewriting its edge-creation logic is high-risk. Mitigated by: implementing AFTER on_success ADR (which simplifies the function), comprehensive property tests, and the prerequisite processor refactoring (which isolates the change to DAG construction).

### R4: Blast radius (HIGH)

~800+ references across tests and examples. Mechanical but extensive. Mitigated by updating `tests/fixtures/pipeline.py` first (single leverage point) and using migration scripts for example YAMLs.

## Review Board Decisions

| Question | Decision | Vote |
|----------|----------|------|
| Q1: Connection namespace | Separate from sink namespace; collision is `GraphValidationError` | Unanimous |
| Q2: Multiple `input:` on transforms | Single input only; multiple inputs reserved for coalesce | Unanimous |
| Q3: Backward compatibility | Atomic change, no phased rollout | Unanimous |
| Q4: Does `path:` survive | Moot — no `path:` field exists on `TransformSettings`; fork branch association is via `fork_to:` on gates, which maps naturally to connection names | Unanimous |
| Q5: YAML ordering | Enforce topological order as transitional constraint until processor refactored to follow DAG edges | Unanimous |
| Q6: Verbosity mitigation | Accept verbosity now (option a); `chain:` syntactic sugar deferred to post-release user feedback | Unanimous |
| Processor refactoring | Must be completed BEFORE declarative wiring; `start_step` → `node_id` is a separate work item | Unanimous |
| Implementation sequencing | on_success ADR → processor refactoring → declarative wiring (three sequential phases) | Unanimous |

## Implementation Sequencing

```
Phase 1: on_success ADR (elspeth-rapid-o639)    ← approved, P1
    ↓
Phase 2: Processor refactoring                   ← new work item needed
    (start_step → node_id, ~200 lines)
    ↓
Phase 3: Declarative DAG wiring (this ADR)       ← P3
    (from_plugin_instances() rewrite, ~800+ test refs)
```

Each phase is independently committable and testable. Phase 2 is a refactoring with no behavioral change — the processor follows the same paths, just indexed by node_id instead of position. Phase 3 changes how edges are built but not how they're traversed.

## References

- Prerequisite ADR: `docs/design/adr/adr-explicit-sink-routing.md` (on_success)
- DAG construction: `core/dag.py:from_plugin_instances()` (lines 366-835)
- Processor positional indexing: `engine/processor.py` (`start_step`, `_WorkItem`, `transforms[start_step:]`)
- Gate routing: `core/config.py:GateSettings.routes`
- Fork/join: `core/dag.py` fork edge creation (lines 680-700)
- Analogous systems: dbt `ref()`, Apache Beam PCollections, Airflow `>>` operator
