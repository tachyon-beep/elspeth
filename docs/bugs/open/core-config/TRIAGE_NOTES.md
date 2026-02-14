# Core Config Triage Notes

**Triaged:** 2026-02-14
**Scope:** `docs/bugs/open/core-config/` (1 finding from static analysis)
**Source code reviewed:** `src/elspeth/core/config.py` (load_settings, ElspethSettings)

## Summary

| # | File | Original | Triaged | Verdict |
|---|------|----------|---------|---------|
| 1 | `P1-...-load-settings-drops-unknown-top-level-keys.md` | P1 | **P1 confirmed** | Real bug — `extra="forbid"` defeated by pre-filter allowlist |

## Detailed Assessment

### Finding 1: `load_settings()` drops unknown top-level keys — CONFIRMED P1

**Verdict: Real bug. P1 confirmed.**

**Mechanism:** `config.py:1988-1989` filters raw config to only known `ElspethSettings` fields
before passing to Pydantic:

```python
known_fields = set(ElspethSettings.model_fields.keys())
raw_config = {k: v for k, v in raw_config.items() if k in known_fields}
```

This was added to strip Dynaconf internal keys (`LOAD_DOTENV`, `ENVIRONMENTS`,
`SETTINGS_FILES`, `MERGE_ENABLED`, etc.) which would trigger `extra="forbid"`.
However, it also strips user typos.

**`extra="forbid"` at line 1226 is effectively dead code** for unknown top-level keys —
it can never fire because they're removed before Pydantic validation.

**Impact by field:**

| Field | Default | Impact of typo |
|-------|---------|----------------|
| `source` | REQUIRED | Still caught (Pydantic missing-field error) |
| `sinks` | REQUIRED | Still caught (Pydantic missing-field error) |
| `transforms` | `[]` | Pipeline runs with NO transforms — silent misconfiguration |
| `gates` | `[]` | No routing rules — all rows go to default path |
| `coalesce` | `[]` | No fork merging configured |
| `aggregations` | `[]` | No batching configured |
| `retry` | defaults | Retry uses defaults (may differ from intent) |
| `checkpoint` | defaults | Checkpoint uses defaults |
| `rate_limit` | defaults | Rate limiting uses defaults |
| `telemetry` | defaults | Telemetry uses defaults |

The `transforms` case is the most dangerous: a typo causes the pipeline to skip
all data processing with no error or warning.

**Fix approach:** Replace the positive allowlist with a negative blocklist of known
Dynaconf internal keys, then let `extra="forbid"` do its job on remaining unknowns.
Dynaconf internals have distinctive names (uppercase, underscore-prefixed) that don't
overlap with Elspeth's schema fields. Example:

```python
_DYNACONF_INTERNAL_KEYS = {
    "load_dotenv", "environments", "settings_files", "merge_enabled",
    "allow_raw_secrets", "envvar_prefix", "root_path", ...
}
filtered = {k: v for k, v in raw_config.items() if k not in _DYNACONF_INTERNAL_KEYS}
return ElspethSettings(**filtered)  # extra="forbid" catches typos
```

Alternatively, keep the allowlist but explicitly warn/error on dropped non-Dynaconf keys.
