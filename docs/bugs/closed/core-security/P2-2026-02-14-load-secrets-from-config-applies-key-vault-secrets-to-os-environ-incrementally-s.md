## Summary

`load_secrets_from_config()` applies Key Vault secrets to `os.environ` incrementally, so a later failure leaves a partially mutated environment with no corresponding secret-resolution audit records.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/security/config_secrets.py`
- Line(s): `153-160`, `168-178`, `180-205`
- Function/Method: `load_secrets_from_config`

## Evidence

`config_secrets.py` writes each secret to global process state before the full load completes:

```python
# src/elspeth/core/security/config_secrets.py:153-160
for env_var_name, keyvault_secret_name in ordered_mapping:
    ...
    secret_value, _ref = loader.get_secret(keyvault_secret_name)
    ...
    os.environ[env_var_name] = str(secret_value)
```

If a later secret fails, the function raises immediately and never returns `resolutions`:

```python
# src/elspeth/core/security/config_secrets.py:180-205
except SecretNotFoundError as e:
    raise SecretLoadError(...) from e
...
except Exception as e:
    raise SecretLoadError(...) from e
```

There is no rollback path for already-written env vars in this function.

Integration evidence:
- Audit insertion only occurs later from returned `resolutions` (`src/elspeth/core/landscape/_run_recording.py:355-384`).
- On `SecretLoadError`, CLI exits (`src/elspeth/cli.py:422-424`), but the function itself still leaves partial in-process state if used programmatically or retried in the same interpreter.

Verified repro (in this workspace): with mapping `{"API1":"secret1","API2":"secret2"}` and `secret2` missing, function raises `SecretLoadError` and `API1` remains changed (`old -> new1`) in `os.environ`.

## Root Cause Hypothesis

The function mixes external fetch, fingerprinting, and global state mutation in one per-secret loop, with fail-fast exceptions but no transactional cleanup. Because audit recording is deferred until after successful return, a mid-loop failure can leave mutated environment state without persisted secret-resolution lineage.

## Suggested Fix

Make secret loading atomic in this function:

1. Load and fingerprint all secrets first into a temporary structure.
2. Only after all succeed, apply environment mutations.
3. On any exception after mutation begins, rollback to prior env values.

Example approach (inside this file): snapshot prior values for touched keys, and restore them in an exception handler before re-raising `SecretLoadError`.

## Impact

- Partial secret state can leak across retries/calls in the same process.
- Subsequent operations may use secrets that were loaded during a failed run setup.
- Secret usage can occur without corresponding `secret_resolutions` rows, weakening audit completeness guarantees.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/security/config_secrets.py.md`
- Finding index in source report: 1
- Beads: pending
