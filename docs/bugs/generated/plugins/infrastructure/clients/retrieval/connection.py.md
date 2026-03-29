## Summary

`ChromaConnectionConfig` does not validate `persist_directory` for path traversal, so the shared validator accepts `..` paths and leaves `ChromaSinkConfig` and `ChromaCollectionProbe` able to read/write Chroma state outside the intended directory.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/connection.py
- Line(s): 36-39, 51-69
- Function/Method: `ChromaConnectionConfig.validate_mode_fields`

## Evidence

`persist_directory` is declared in the target file, but there is no field validator for it:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/connection.py:36-39
persist_directory: str | None = Field(
    default=None,
    description="Path to ChromaDB data directory (persistent mode only)",
)
```

The only validation in the target is the mode cross-check:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/connection.py:51-69
@model_validator(mode="after")
def validate_mode_fields(self) -> ChromaConnectionConfig:
    if self.mode == "persistent":
        if self.persist_directory is None:
            raise ValueError("persist_directory is required when mode='persistent'")
```

By contrast, the provider-specific config has an extra validator that rejects `..` components:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/chroma.py:66-71
@field_validator("persist_directory")
@classmethod
def validate_persist_directory(cls, v: str | None) -> str | None:
    if v is not None and ".." in v.split("/"):
        raise ValueError(f"persist_directory must not contain '..' path components, got {v!r}")
    return v
```

Other consumers trust the target file as the shared validator:

```python
# /home/john/elspeth/src/elspeth/plugins/sinks/chroma_sink.py:94-106
@model_validator(mode="after")
def validate_connection(self) -> ChromaSinkConfig:
    ChromaConnectionConfig(
        collection=self.collection,
        mode=self.mode,
        persist_directory=self.persist_directory,
        ...
    )
```

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/probe_factory.py:29-38
try:
    ChromaConnectionConfig(collection=collection, **config)
except ValidationError as exc:
    ...
```

Verified behavior in this repo:

- `ChromaConnectionConfig(collection="test", mode="persistent", persist_directory="/tmp/../etc/chroma")` is accepted.
- `ChromaSinkConfig.from_dict(...)` with the same path is accepted.
- `ChromaCollectionProbe("test", {"mode": "persistent", "persist_directory": "/tmp/../etc/chroma"})` is accepted.

Test coverage also reflects the gap:
- Provider path traversal is tested in [/home/john/elspeth/tests/unit/plugins/infrastructure/clients/retrieval/test_chroma.py#L84](/home/john/elspeth/tests/unit/plugins/infrastructure/clients/retrieval/test_chroma.py#L84)
- Shared connection tests do not cover it in [/home/john/elspeth/tests/unit/plugins/infrastructure/clients/retrieval/test_connection.py#L13](/home/john/elspeth/tests/unit/plugins/infrastructure/clients/retrieval/test_connection.py#L13)
- Sink/probe validation tests only cover mode/host requirements in [/home/john/elspeth/tests/unit/plugins/sinks/test_chroma_sink_config.py#L101](/home/john/elspeth/tests/unit/plugins/sinks/test_chroma_sink_config.py#L101) and [/home/john/elspeth/tests/unit/plugins/infrastructure/test_probe_factory.py#L167](/home/john/elspeth/tests/unit/plugins/infrastructure/test_probe_factory.py#L167)

## Root Cause Hypothesis

The path validation was implemented only in `ChromaSearchProviderConfig` instead of being centralized in `ChromaConnectionConfig`, even though sink and probe code were later written to treat `ChromaConnectionConfig` as the shared source of truth for connection validation.

## Suggested Fix

Add a `@field_validator("persist_directory")` to `ChromaConnectionConfig` with the same `..` rejection logic currently living in `ChromaSearchProviderConfig`, then delete the duplicate provider-only validator so all three consumers share one contract.

Example shape:

```python
@field_validator("persist_directory")
@classmethod
def validate_persist_directory(cls, v: str | None) -> str | None:
    if v is not None and ".." in v.split("/"):
        raise ValueError(f"persist_directory must not contain '..' path components, got {v!r}")
    return v
```

Add regression tests for:

- `ChromaConnectionConfig` rejecting traversal paths
- `ChromaSinkConfig.from_dict(...)` rejecting traversal paths via delegation
- `ChromaCollectionProbe(...)` rejecting traversal paths at construction

## Impact

Persistent-mode sink and probe configs can target parent directories unexpectedly, which is a configuration trust-boundary validation gap. It also creates inconsistent behavior across Chroma integrations: the provider rejects traversal paths, but sink and probe accept the same input, so preflight/readiness and write-path behavior diverge for identical connection settings.
