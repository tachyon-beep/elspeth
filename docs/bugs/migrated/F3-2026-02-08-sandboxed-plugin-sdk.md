## Summary

Open ELSPETH to user-written plugins while maintaining audit integrity. A fourth trust tier for user plugin code with capability-limited sandboxing and contract-driven validation.

## Severity

- Severity: low
- Priority: P3
- Type: feature
- Status: open
- Bead ID: elspeth-rapid-w2q7.7

## Current vs Target

**Current:** All plugins are system-owned code (per CLAUDE.md). Correct for RC, but limits adoption.

**Target:** A Tier 4 (Sandboxed) trust level for user plugins:

| Tier | Trust | What |
|------|-------|------|
| 1 | Full | Our audit data |
| 2 | Elevated | Pipeline data post-source |
| 3 | Zero | External data |
| **4** | **Sandboxed** | **User plugin code** |

## Plugin SDK

```python
from elspeth.sdk import Transform, contract

@contract(
    input_fields={'customer_id': str, 'amount': float},
    output_fields={'customer_id': str, 'amount': float, 'risk_tier': str},
    determinism='deterministic',
    side_effects=False,
)
class RiskTierTransform(Transform):
    def process(self, row, ctx):
        tier = 'high' if row['amount'] > 10000 else 'low'
        return {**row, 'risk_tier': tier}
```

## Sandbox Constraints

- No filesystem access (except explicit config)
- No network access (except declared external calls with rate limiting)
- No subprocess spawning
- Memory and CPU limits per invocation
- Import whitelist (no os, subprocess, socket)
- Timeout per row processing

## Implementation Options

- RestrictedPython (AST-level restriction)
- Process isolation (subprocess with seccomp/AppArmor)
- WASM sandbox (wasmtime-py)
- Docker-based isolation

## Dependencies

- Parent: `w2q7` — ELSPETH-NEXT epic
