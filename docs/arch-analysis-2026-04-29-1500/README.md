# Architecture Analysis Workspace — 2026-04-29

This workspace is a **hierarchical multi-pass architecture analysis** of the
ELSPETH codebase produced by adapting the `axiom-system-archaeologist`
analyze-codebase skill for very-large repos (~121k LOC, 11 top-level
subsystems). It is a frozen audit artefact: deliverables here are not
expected to be edited, only consumed.

## Quickstart

| If you want… | Read |
|---|---|
| **The findings** | [`99-stitched-report.md`](99-stitched-report.md) — the synthesis report, ~6,933 words, 48 cross-cluster claims, 119 citations |
| **A picture** | [`99-cross-cluster-graph.md`](99-cross-cluster-graph.md) — Container + Component diagrams synthesising the L3 import topology |
| **The L1 dispatch trail** | [`04-l1-summary.md`](04-l1-summary.md) — original L1 dispatch queue (§7) + Phase 0 amendments (§7.5) |
| **The L3 import oracle** | [`temp/l3-import-graph.json`](temp/l3-import-graph.json) (machine-readable, schema v1.0) or `.mmd` / `.dot` for visualisation |
| **A specific cluster** | `clusters/<name>/04-cluster-report.md` for engine, core, composer, plugins, contracts |
| **Why the analysis was structured this way** | [`00-coordination.md`](00-coordination.md) — coordination plan + execution log across all phases |

## Workspace layout

```
docs/arch-analysis-2026-04-29-1500/
├── README.md                       (this file)
├── 00-coordination.md              Coordination plan + execution log (all phases)
├── 00b-existing-knowledge-map.md   ~250 atomic claims indexed from prior docs (KNOW-* IDs)
├── 01-discovery-findings.md        Holistic codebase shape and entry points
├── 02-l1-subsystem-map.md          11 top-level subsystem catalog entries (depth-capped)
├── 03-l1-context-diagram.md        C4 System Context + Container view
├── 04-l1-summary.md                §7 dispatch queue + §7.5 Phase 0 amendments
├── 99-stitched-report.md           Phase 8 synthesis report (THE DELIVERABLE)
├── 99-cross-cluster-graph.md       Phase 8 system-level architecture diagrams
├── clusters/                       Per-cluster L2 deep-dive workspaces
│   ├── engine/                     L2 #1 — orchestrator + executors + processor
│   ├── core/                       L2 #3 — landscape, dag, config, canonical, etc.
│   ├── composer/                   L2 #2 — web/ + composer_mcp/ (7-node SCC)
│   ├── plugins/                    L2 #4 — infrastructure, sources, transforms, sinks
│   └── contracts/                  L2 #5 — protocols, types, schema contracts
└── temp/                           Oracles, manifests, validators (see semantics below)
```

Each `clusters/<name>/` follows the same internal layout:

```
clusters/<name>/
├── 00-cluster-coordination.md
├── 01-cluster-discovery.md
├── 02-cluster-catalog.md           Sub-subsystem catalog (one level deeper than L1)
├── 03-cluster-diagrams.md          Cluster-scoped C4 Container + Component
├── 04-cluster-report.md            Cluster-level synthesis (top-3 confidence + uncertainty)
└── temp/                           Cluster-scoped oracle subsets and validators
```

## `temp/` semantics

The `temp/` directories contain two distinct file classes — **do not delete or
relocate without distinguishing them**:

| Class | Examples | Durability | Cited by other deliverables? |
|---|---|---|---|
| **Oracle artefacts** | `temp/l3-import-graph.{json,mmd,dot}`, `clusters/*/temp/intra-cluster-edges.json`, `clusters/*/temp/layer-check-*.txt`, `temp/tier-model-oracle.txt` | Frozen, durable | Yes — cited by JSON path or filename throughout |
| **Pass workings** | `temp/synthesis-input-manifest.md`, `temp/reconciliation-log.md`, `temp/validation-*.md`, `temp/doc-correctness-*.md` | Single-use | No — consumed once at validation time |

Both classes are kept under `temp/` for workspace tidiness; the durability
distinction is documented here rather than enforced by directory structure.

## Phase chronology

The workspace was produced over a sequence of disciplined phases, each with
its own scope-override prompt, time budget, validator gate, and citation
contract. Phase boundaries are recorded in the
[execution log](00-coordination.md#execution-log).

| Phase | Date | Output |
|---|---|---|
| **L1 shallow map** | 2026-04-29 (~40 min) | 6 deliverables; 11 subsystems classified composite vs leaf |
| **Phase 0 — L3 oracle** | 2026-04-29 02:32Z | `enforce_tier_model.py dump-edges` extension + 12 tests + 3 graph artefacts |
| **Phase 0.5 — L1 amendment** | 2026-04-29 02:45Z | `04-l1-summary.md` §7.5 added (oracle findings F1–F5) |
| **L2 #1 — engine** | 2026-04-29 | `clusters/engine/` |
| **L2 #2 — composer** | 2026-04-29 | `clusters/composer/` (7-node SCC analysed as unit) |
| **L2 #3 — core** | 2026-04-29 | `clusters/core/` |
| **L2 #4 — plugins** | 2026-04-29 | `clusters/plugins/` (infrastructure-first reading order) |
| **L2 #5 — contracts** | 2026-04-29 | `clusters/contracts/` |
| **Phase 8 — stitching** | 2026-04-29 07:30Z | `99-stitched-report.md` + `99-cross-cluster-graph.md` |
| **Phase 9 — doc-correctness** | 2026-04-29 | T1–T5 resolved across `ARCHITECTURE.md`, `CLAUDE.md`, `PLUGIN.md`; 13 deferrals |

## Headline findings

These are the load-bearing findings the workspace produced. Full evidence
chains are in `99-stitched-report.md` §3–§7.

1. **7-node strongly-connected component** spans every web/* sub-package
   (`web ↔ web/auth ↔ web/blobs ↔ web/composer ↔ web/execution ↔
   web/secrets ↔ web/sessions`). No acyclic decomposition is possible
   within `web/`. *Source: `temp/l3-import-graph.json`
   `strongly_connected_components[4]`.*

2. **`plugins/infrastructure/` is the load-bearing spine** of the plugins
   ecosystem. The `plugins/sinks → plugins/infrastructure` edge has weight
   45 (heaviest single L3 edge); sinks/sources/transforms are all clients.
   *Source: same JSON, `.edges`.*

3. **`composer_mcp/` is not a sibling of `mcp/`.** It imports
   `web/composer/` at weight 12; the L1 sibling/sibling framing was
   wrong. The L2 composer cluster pass absorbed both.

4. **`mcp/` and `composer_mcp/` are independent.** Zero edges in either
   direction. The L1 catalog's "do not merge" guidance for `mcp/` is
   upheld.

5. **75 of 77 L3 edges are unconditional runtime coupling.** Zero
   `TYPE_CHECKING`-only edges; only 2 conditional. The codebase does not
   hide its dependencies; lazy-import patterns are essentially absent at
   the L3 boundary.

## Recommended downstream consumers

`99-stitched-report.md` §9 names these packs:

- **`axiom-system-architect`** — architecture critique + improvement roadmap
  (consumes §3 cross-cluster findings, §6 reconciled tensions, §7 debt
  candidates).
- **`ordis-security-architect`** — STRIDE threat model + controls design
  (consumes §3.3 trust-boundary topology, §3.4 audit-trail completeness,
  the trust-tier model from CLAUDE.md).
- **`axiom-system-archaeologist` L3 deep-dives** — file-level analysis of
  the 6+ files >1,500 LOC flagged at L1 (`tools.py`, `state.py`,
  `processor.py`, `config.py`, `dag/graph.py`, `errors.py`,
  `orchestrator/core.py`).
- **Cross-cluster integration-tier audit** — KNOW-C44 production-path
  conformance.

## Re-running the L3 oracle

The graph is deterministic. To re-derive after codebase changes:

```bash
.venv/bin/python scripts/cicd/enforce_tier_model.py dump-edges \
  --root src/elspeth \
  --format json \
  --output /tmp/l3-import-graph-fresh.json \
  --no-timestamp
```

`--no-timestamp` produces byte-identical output across runs given the same
source tree, so `diff` against the workspace artefact will show only true
import-graph drift.

## What's NOT in this workspace

The L1 deferrals list (`04-l1-summary.md`) explicitly excluded:

- `src/elspeth/web/frontend/` (~13k LOC TS/React) — different toolchain;
  needs a frontend-aware archaeologist.
- `tests/` (~351k LOC, 851 files) — own architectural surface; deferred
  to a separate test-architecture pass.
- `examples/` (36 pipelines) — noted by count, not analysed individually.
- `scripts/` beyond the layer/freeze enforcers — out of scope.
- Any single file >1,500 LOC — flagged as L3 deep-dive candidate, not
  inlined.

These remain legitimately deferred. Re-opening them is a future-pack
decision.
