# Cross-Cutting Dependency Analysis

## Subsystem Dependency Matrix

### Expected Layering (bottom to top)
```
L0: contracts (foundation — type definitions, protocols)
L1: core (infrastructure — landscape, config, DAG, security)
L2: engine, telemetry (execution — orchestration, processors)
L3: plugins (implementations — sources, transforms, sinks)
L4: cli, tui, mcp, testing (user-facing)
```

### Dependency Direction
```
                    Outbound    Inbound
contracts (L0)         3           8      ← foundation, heavily imported
core (L1)              3           8      ← infrastructure, heavily imported
engine (L2)            4           3
plugins (L3)           2           4
telemetry (L2)         1           2
mcp (L4)               2           0
tui (L4)               2           0
cli (L4)               9           1      ← highest fanout
testing (L4)           0           1
```

## 6 Bidirectional Dependency Cycles

| Cycle | Severity | Root Cause |
|-------|----------|------------|
| contracts ↔ core | HIGH | PluginContext imports LandscapeRecorder, RateLimitRegistry; runtime.py imports Settings classes; url.py imports config/security |
| contracts ↔ engine | MEDIUM | results.py imports MaxRetriesExceeded from engine |
| contracts ↔ plugins | HIGH | PluginContext imports AuditedHTTPClient, AuditedLLMClient; node_state_context imports BufferEntry |
| core ↔ engine | MEDIUM | config.py imports ExpressionParser for gate expression validation |
| core ↔ plugins | MEDIUM | DAG builder/graph/models import SourceProtocol, TransformProtocol, SinkProtocol |
| cli ↔ cli_helpers | LOW | Functional split within same user-facing layer |

## Layer Violation Details

### contracts (L0) → core (L1) — 11 imports
Most severe: contracts is supposed to be the foundation that everything imports FROM.

1. **contracts/config/runtime.py** → `core.config.{CheckpointSettings, ConcurrencySettings, RateLimitSettings, RetrySettings, ServiceRateLimit, TelemetrySettings}` — Runtime configs need Settings classes for `from_settings()` conversion
2. **contracts/contract_records.py** → `core.canonical.canonical_json` — uses canonical serialization
3. **contracts/plugin_context.py** → `core.landscape.recorder.LandscapeRecorder` — god object bundles audit access
4. **contracts/plugin_context.py** → `core.rate_limit.RateLimitRegistry` — god object bundles rate limiting
5. **contracts/plugin_context.py** → `core.canonical.{stable_hash, repr_hash}` — hashing utilities
6. **contracts/schema_contract.py** → `core.canonical.canonical_json` — canonical serialization
7. **contracts/url.py** → `core.config._sanitize_dsn`, `core.config.SecretFingerprintError` — DSN sanitization
8. **contracts/url.py** → `core.security.fingerprint.{get_fingerprint_key, secret_fingerprint}` — security

### contracts (L0) → engine (L2) — 1 import
- **contracts/results.py** → `engine.retry.MaxRetriesExceeded` — trivially fixable (move class to contracts)

### contracts (L0) → plugins (L3) — 3 imports
- **contracts/node_state_context.py** → `plugins.pooling.reorder_buffer.BufferEntry` — data type dependency
- **contracts/plugin_context.py** → `plugins.clients.http.AuditedHTTPClient` — god object
- **contracts/plugin_context.py** → `plugins.clients.llm.AuditedLLMClient` — god object

### core (L1) → engine (L2) — 3 imports
- **core/config.py** → `engine.expression_parser.{ExpressionParser, ExpressionSecurityError, ExpressionSyntaxError}` — config validation uses expression parser

### core (L1) → plugins (L3) — 3 imports
- **core/dag/builder.py** → `plugins.protocols.{SinkProtocol, SourceProtocol, TransformProtocol}`
- **core/dag/graph.py** → `plugins.protocols.{SinkProtocol, SourceProtocol, TransformProtocol}`
- **core/dag/models.py** → `plugins.protocols.TransformProtocol`

## Remediation Candidates

### Quick Wins (trivially fixable)
1. **Move `MaxRetriesExceeded`** from `engine/retry.py` to `contracts/errors.py`
2. **Move `BufferEntry`** from `plugins/pooling/reorder_buffer.py` to `contracts/`
3. **Move `ExpressionParser`** from `engine/` to `core/` or `contracts/` (it's config-adjacent)

### Structural Fixes
4. **Move plugin protocols** from `plugins/protocols.py` to `contracts/` — protocols define the interfaces, they belong in the contracts layer
5. **Split `PluginContext`** — it's a god object in `contracts/` that imports from core and plugins. Either:
   a. Move PluginContext to a higher layer (e.g., engine)
   b. Define protocol interfaces in contracts, implement in core
   c. Use dependency injection to eliminate direct imports
6. **Move `canonical_json`/hashing** to contracts or create a shared `contracts/serialization.py`
7. **Invert Settings→Runtime dependency** — have Settings classes provide conversion methods, or co-locate

### Architectural Rethinking
8. **PluginContext as god object** — this is the #1 coupling vector. It bundles LandscapeRecorder, RateLimitRegistry, AuditedHTTPClient, AuditedLLMClient, hashing utilities. Refactoring this into protocol-based injection would break most cycles.
