## Summary

`LandscapeSettings.enabled` is accepted in `/home/john/elspeth/src/elspeth/core/config.py` but never changes runtime behavior; `landscape.enabled: false` still boots the audit database and runs with Landscape recording enabled.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/core/config.py
- Line(s): 979, 1246-1351
- Function/Method: `LandscapeSettings`, `ElspethSettings`

## Evidence

`LandscapeSettings` exposes an `enabled` flag:

```python
# src/elspeth/core/config.py:979-983
enabled: bool = Field(default=True, description="Enable audit trail recording")
backend: Literal["sqlite", "sqlcipher", "postgresql"] = Field(
    default="sqlite",
)
```

But the execution path does not consult it before creating the audit DB:

```python
# src/elspeth/cli.py:970-982
db = LandscapeDB.from_url(
    config.landscape.url,
    passphrase=passphrase,
    dump_to_jsonl=config.landscape.dump_to_jsonl,
    ...
)
```

The project’s own alignment test documents that this field is not wired at runtime:

```python
# tests/unit/core/test_config_alignment.py:230-233
PENDING_FIELDS: ClassVar[set[str]] = {
    "enabled",  # Always assumed True
    "backend",  # Used by resolve_audit_passphrase() to select SQLCipher backend
}
```

So `config.py` validates and stores a setting that the engine ignores. What the code does: accepts `landscape.enabled=False` as valid config. What it should do: either reject `False` up front or implement an actual no-Landscape mode.

## Root Cause Hypothesis

`enabled` was modeled in `LandscapeSettings` as if audit disabling were supported, but no runtime contract or execution path was added for it. The alignment test has already acknowledged the drift, so the bug persists as a silent config/runtime mismatch.

## Suggested Fix

Fail fast in `config.py` until disabling Landscape is truly supported. For example, add a validator on `LandscapeSettings` that rejects `enabled=False` with a clear message.

```python
@model_validator(mode="after")
def validate_enabled_supported(self) -> "LandscapeSettings":
    if not self.enabled:
        raise ValueError("landscape.enabled=false is not implemented; Landscape is currently mandatory")
    return self
```

If audit disabling is intended to be supported, then the larger fix belongs outside this file; in that case `config.py` should still reject unsupported values until the runtime work exists.

## Impact

This is a configuration precedence/contract violation. Operators can supply a setting that appears valid and is carried into the resolved config, but the system ignores it and still records audit data. That creates misleading reproducibility records and undermines confidence that validated config matches actual runtime behavior.
---
## Summary

`LandscapeSettings.backend` is only partially validated, so `config.py` accepts contradictory `backend`/`url` combinations that runtime then resolves by URL, not by the declared backend.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/core/config.py
- Line(s): 980-1044
- Function/Method: `LandscapeSettings.validate_database_url`, `LandscapeSettings.validate_sqlcipher_backend`

## Evidence

`LandscapeSettings` exposes a backend selector and URL separately:

```python
# src/elspeth/core/config.py:980-989
backend: Literal["sqlite", "sqlcipher", "postgresql"] = Field(
    default="sqlite",
    description="Database backend type (sqlcipher requires the 'security' extra)",
)
url: str = Field(
    default="sqlite:///./state/audit.db",
    description="Full SQLAlchemy database URL",
)
```

But validation only checks one special case:

```python
# src/elspeth/core/config.py:1039-1044
@model_validator(mode="after")
def validate_sqlcipher_backend(self) -> "LandscapeSettings":
    if self.backend == "sqlcipher" and not self.url.startswith("sqlite"):
        raise ValueError("backend='sqlcipher' requires a SQLite URL ...")
    return self
```

At runtime, DB creation is driven by the URL plus optional passphrase, not by `backend`:

```python
# src/elspeth/core/landscape/database.py:521-529
if passphrase is not None:
    engine = cls._create_sqlcipher_engine(url, passphrase)
else:
    engine = create_engine(url, echo=False)
    if url.startswith("sqlite"):
        cls._configure_sqlite(engine)
```

And passphrase resolution looks only at `backend == "sqlcipher"`:

```python
# src/elspeth/cli_helpers.py:355-362
if settings is not None and settings.backend == "sqlcipher":
    env_var = settings.encryption_key_env
    passphrase = os.environ.get(env_var)
    ...
    return passphrase
return None
```

The project’s own alignment test also marks `backend` as not really runtime-wired:

```python
# tests/unit/core/test_config_alignment.py:230-233
PENDING_FIELDS: ClassVar[set[str]] = {
    "enabled",  # Always assumed True
    "backend",  # Used by resolve_audit_passphrase() to select SQLCipher backend
}
```

What the code does: accepts `backend: sqlite` with a PostgreSQL URL, or `backend: postgresql` with a SQLite URL. What it should do: reject mismatches so the declared backend and effective backend cannot diverge.

## Root Cause Hypothesis

`backend` started as descriptive metadata, then gained one behavioral use for SQLCipher passphrase resolution, but `config.py` never enforced full consistency between the symbolic backend and the actual SQLAlchemy URL scheme. That leaves a split-brain contract: validation accepts one backend while runtime obeys another.

## Suggested Fix

Add full backend/URL consistency validation in `LandscapeSettings`, not just the SQLCipher special case. For example:

```python
@model_validator(mode="after")
def validate_backend_matches_url(self) -> "LandscapeSettings":
    if self.url.startswith("postgresql"):
        expected = "postgresql"
    elif self.url.startswith("sqlite"):
        expected = "sqlite"
    else:
        expected = "Unknown"

    if self.backend == "sqlcipher":
        if expected != "sqlite":
            raise ValueError("backend='sqlcipher' requires a SQLite URL")
    elif self.backend != expected:
        raise ValueError(
            f"landscape.backend={self.backend!r} does not match URL scheme implied by {self.url!r}"
        )
    return self
```

If `backend` is meant to remain advisory, then the safer fix is to remove it from user config and derive behavior solely from the URL plus explicit encryption settings.

## Impact

This is a config contract violation with security implications. A validated config can declare one backend while the engine opens another, and SQLCipher passphrase handling depends on `backend` rather than the URL. That makes effective database behavior ambiguous and can cause accepted configurations to run differently from what the audited settings claim.
