# Silent Defaults Audit

This document records critical defaults and their rationale to avoid silent or surprising behavior.

- Repository sinks: `fail_fast_missing_token` default is False to preserve backward compatibility. Live runs should set tokens explicitly or enable fail-fast in config.
- Datasource registries: Schema validators are pre-compiled at registration to avoid first-call latency.
- HTTP LLM client: HTTP is allowed only for localhost/loopback; runtime assertion enforces this in addition to endpoint validation.

## CRITICAL (P0)

- Repository sinks: Default `dry_run=True` to prevent accidental writes; `fail_fast_missing_token=False` by default to preserve backward compatibility. Live publishing must set tokens or enable fail-fast.
- Azure Search API Key: retriever requires `api_key` or `api_key_env`; configuration validation fails fast if neither is provided.
- pgvector: default table name `elspeth_rag` must be explicitly configured; connection timeout is appended automatically when provided.

Status: Up to date.
