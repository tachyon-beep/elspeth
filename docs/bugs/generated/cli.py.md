## Summary

`explain` silently bypasses the project’s secret-loading flow when it reloads `--settings` for SQLCipher passphrase resolution, so encrypted audit databases can become unreadable in supported configs.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/cli.py
- Line(s): 690-715
- Function/Method: `explain`

## Evidence

`explain` resolves the database first, then separately reloads settings only for passphrase lookup:

- `/home/john/elspeth/src/elspeth/cli.py:690-695`
- `/home/john/elspeth/src/elspeth/cli.py:713-715`

That reload uses `load_settings(settings_path)` directly instead of the CLI’s standard `_load_settings_with_secrets()` path:

- `/home/john/elspeth/src/elspeth/cli.py:286-333` defines `_load_settings_with_secrets()`
- `/home/john/elspeth/src/elspeth/cli.py:380` uses it in `run`
- `/home/john/elspeth/src/elspeth/cli.py:1078` uses it in `validate`
- `/home/john/elspeth/src/elspeth/cli.py:1641` uses it in `resume`

The secret-loading contract explicitly says Key Vault secrets must be injected into `os.environ` before normal config resolution:

- `/home/john/elspeth/src/elspeth/core/security/config_secrets.py:1-25`
- `/home/john/elspeth/src/elspeth/core/security/config_secrets.py:50-57`
- `/home/john/elspeth/src/elspeth/core/security/config_secrets.py:208-210`

`resolve_audit_passphrase()` only reads the passphrase from the configured environment variable; it never reads secrets from config directly:

- `/home/john/elspeth/src/elspeth/cli_helpers.py:331-365`

So if `landscape.encryption_key_env` or the passphrase env var is supplied through the supported `secrets: source: keyvault` flow, `run`/`resume` work, but `explain` can fail because its ad hoc reload skipped the Key Vault injection step.

The same branch also only reloads settings when `settings_path.exists()` is true:

- `/home/john/elspeth/src/elspeth/cli.py:691`

But `settings_path` is created with `Path(settings)` at `/home/john/elspeth/src/elspeth/cli.py:673`, not `expanduser()`. An explicit `--settings ~/pipeline.yaml` can therefore be skipped here even though other CLI paths expand `~`.

Test coverage confirms the gap: there are tests for malformed settings and for “no settings”, but no test for `explain` with SQLCipher/Key Vault/tilde settings:

- `/home/john/elspeth/tests/unit/cli/test_cli.py:221-292`
- `/home/john/elspeth/tests/unit/cli/test_secrets_loading.py:18-228`

## Root Cause Hypothesis

`explain` has a one-off settings reload path for passphrase resolution instead of reusing the same settings-loading contract as the other CLI commands. That duplicated logic drifted: it skips secret injection, does not normalize `~`, and treats a missing explicit settings path as “no settings” rather than a hard error.

## Suggested Fix

Reuse `_load_settings_with_secrets()` in `explain` whenever `--settings` is explicitly provided for passphrase resolution, and normalize the path first with `expanduser()`.

At minimum:

- Normalize `settings_path = Path(settings).expanduser()` before any existence checks.
- If `--settings` was provided, load it through `_load_settings_with_secrets()` instead of `load_settings()`.
- If the explicit settings file is missing, fail immediately instead of silently falling back to `passphrase=None`.

## Impact

`elspeth explain` can fail to open encrypted audit databases in supported deployments, even though `run`, `validate`, and `resume` accept the same config. That blocks lineage inspection for affected runs and undermines the auditability guarantee that operators can always explain past outputs from recorded configuration and data.
---
## Summary

`elspeth web` accepts `--auth` and other `WebSettings` inputs but drops them when launching Uvicorn, so the running app starts with default settings instead of the CLI-requested ones.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/cli.py
- Line(s): 2205-2225
- Function/Method: `web`

## Evidence

The command validates CLI arguments by constructing `WebSettings`:

- `/home/john/elspeth/src/elspeth/cli.py:2205-2206`

But it then launches Uvicorn with the string factory `"elspeth.web.app:create_app"` and `factory=True`:

- `/home/john/elspeth/src/elspeth/cli.py:2220-2225`

`create_app()` defaults to `WebSettings()` when no settings object is passed:

- `/home/john/elspeth/src/elspeth/web/app.py:30-40`

So the CLI-created `settings` object is never used by the app factory. The file itself documents this exact loss of state:

- `/home/john/elspeth/src/elspeth/cli.py:2208-2213`

Existing tests only assert that the warning is printed and that `uvicorn.run()` gets `factory=True`; they do not verify settings propagation:

- `/home/john/elspeth/tests/unit/cli/test_web_command.py:32-40`
- `/home/john/elspeth/tests/unit/cli/test_web_command.py:74-80`

## Root Cause Hypothesis

The CLI and FastAPI factory are wired through Uvicorn’s zero-argument factory protocol, but the command still builds a `WebSettings` instance locally as if it will be passed into `create_app(settings)`. That mismatch leaves the actual app process using defaults.

## Suggested Fix

Wire the validated CLI settings into app creation instead of discarding them. For example:

- Replace the string factory with a callable that closes over the validated `settings`, or
- Store the validated settings in a module-level holder/env contract that `create_app()` reads intentionally, or
- Stop accepting CLI options that cannot be honored yet.

Also add a test that proves `elspeth web --auth oidc` results in an app whose `app.state.settings.auth_provider == "oidc"`.

## Impact

Operators can invoke `elspeth web --auth oidc` (or other non-default settings) and get a server that still runs with default `WebSettings`. That creates configuration-precedence violations and misleading operational behavior: the CLI appears to accept a deployment mode it does not actually apply.
