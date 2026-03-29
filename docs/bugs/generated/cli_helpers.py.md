## Summary

`bootstrap_and_run()` skips the SQLCipher + JSONL plaintext-journal warning that the main CLI execution path emits, so dependency/sub-pipeline runs can write an unencrypted sidecar audit journal without any operator-visible warning.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/cli_helpers.py
- Line(s): 209-328, especially 276-289
- Function/Method: `bootstrap_and_run`

## Evidence

`bootstrap_and_run()` opens the audit database with JSONL journal options, but it never checks the `passphrase is not None and config.landscape.dump_to_jsonl` case before doing so:

```python
# src/elspeth/cli_helpers.py:276-289
passphrase = resolve_audit_passphrase(config.landscape)
db = LandscapeDB.from_url(
    config.landscape.url,
    passphrase=passphrase,
    dump_to_jsonl=config.landscape.dump_to_jsonl,
    dump_to_jsonl_path=config.landscape.dump_to_jsonl_path,
    dump_to_jsonl_fail_on_error=config.landscape.dump_to_jsonl_fail_on_error,
    dump_to_jsonl_include_payloads=config.landscape.dump_to_jsonl_include_payloads,
    dump_to_jsonl_payload_base_path=(
        str(config.payload_store.base_path)
        if config.landscape.dump_to_jsonl_payload_base_path is None
        else config.landscape.dump_to_jsonl_payload_base_path
    ),
)
```

The main CLI execution path has an explicit warning for this exact configuration:

```python
# src/elspeth/cli.py:961-968
if passphrase is not None and config.landscape.dump_to_jsonl:
    import structlog

    structlog.get_logger().warning(
        "JSONL journal is not encrypted",
        hint="The JSONL change journal is written in plaintext even when the audit database is encrypted with SQLCipher.",
    )
```

The configuration model confirms that JSONL journaling can include payload content, increasing the sensitivity of what is written in plaintext:

- `/home/john/elspeth/src/elspeth/core/config.py:998-1017`
- `dump_to_jsonl`
- `dump_to_jsonl_include_payloads`
- `dump_to_jsonl_payload_base_path`

`bootstrap_and_run()` is used for programmatic pipeline execution and dependency runs (`/home/john/elspeth/src/elspeth/cli.py:482-489`, `/home/john/elspeth/tests/unit/engine/test_bootstrap_preflight.py:18-191`), so this is not dead code: nested pipeline execution can take the silent path today.

What the code does:
- Opens SQLCipher DB and optional JSONL journal in `bootstrap_and_run()` with no warning.

What it should do:
- Emit the same warning as `_execute_pipeline_with_instances()` before opening the DB, or share a single helper so both paths enforce the same operator-facing behavior.

## Root Cause Hypothesis

`bootstrap_and_run()` was extracted as a programmatic analogue of the CLI run path, but the SQLCipher/JSONL warning logic was copied incompletely. The DB initialization arguments stayed in sync, while the pre-open safety warning in `cli.py` was omitted from `cli_helpers.py`.

## Suggested Fix

Add the same guard used in `/home/john/elspeth/src/elspeth/cli.py:961-968` before `LandscapeDB.from_url(...)` in `bootstrap_and_run()`. Better yet, factor the warning + DB construction into a shared helper used by both code paths.

Example shape:

```python
if passphrase is not None and config.landscape.dump_to_jsonl:
    structlog.get_logger().warning(
        "JSONL journal is not encrypted",
        hint="The JSONL change journal is written in plaintext even when the audit database is encrypted with SQLCipher.",
    )
```

A regression test should cover `bootstrap_and_run()` specifically, since current tests under `/home/john/elspeth/tests/unit/engine/test_bootstrap_preflight.py` do not exercise `dump_to_jsonl=True`.

## Impact

Dependency pipelines and other programmatic executions that go through `bootstrap_and_run()` can produce a plaintext JSONL audit journal alongside an encrypted SQLCipher database without any warning. That does not corrupt audit lineage, but it does create an observability/security gap: operators may reasonably assume “encrypted audit DB” means the whole audit footprint is encrypted, while this path silently leaves a plaintext journal, potentially including payload material.
