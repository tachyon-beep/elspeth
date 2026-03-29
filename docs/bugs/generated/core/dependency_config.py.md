## Summary

`dependency_config.py` under-validates preflight config strings, so malformed dependency/gate/probe settings pass Pydantic validation and only fail later during bootstrap/probe construction.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/core/dependency_config.py
- Line(s): 19-20, 28-29, 37-38
- Function/Method: `DependencyConfig`, `CommencementGateConfig`, `CollectionProbeConfig`

## Evidence

`dependency_config.py` only enforces `min_length=1` on the key preflight strings:

```python
name: str = Field(min_length=1, ...)
settings: str = Field(min_length=1, ...)
condition: str = Field(min_length=1, ...)
collection: str = Field(min_length=1, ...)
provider: str = Field(min_length=1, ...)
```

Source: [dependency_config.py:19](/home/john/elspeth/src/elspeth/core/dependency_config.py#L19), [dependency_config.py:20](/home/john/elspeth/src/elspeth/core/dependency_config.py#L20), [dependency_config.py:28](/home/john/elspeth/src/elspeth/core/dependency_config.py#L28), [dependency_config.py:29](/home/john/elspeth/src/elspeth/core/dependency_config.py#L29), [dependency_config.py:37](/home/john/elspeth/src/elspeth/core/dependency_config.py#L37), [dependency_config.py:38](/home/john/elspeth/src/elspeth/core/dependency_config.py#L38)

That means values like `"   "` or `" chroma "` are accepted as “valid” config. The failure is deferred to downstream runtime code:

- Probe provider names are only checked later in [probe_factory.py:105](/home/john/elspeth/src/elspeth/plugins/infrastructure/probe_factory.py#L105) through [probe_factory.py:109](/home/john/elspeth/src/elspeth/plugins/infrastructure/probe_factory.py#L109), where `config.provider` is looked up in `_PROBE_REGISTRY` and raises `ValueError` only after config loading and graph/bootstrap setup.
- Dependency paths are consumed verbatim in [dependency_resolver.py:111](/home/john/elspeth/src/elspeth/engine/dependency_resolver.py#L111), so padded/blank-ish `settings` strings become bad filesystem lookups later instead of being rejected at config time.
- Commencement-gate expressions are not validated in the model; they are only checked later in [bootstrap.py:48](/home/john/elspeth/src/elspeth/engine/bootstrap.py#L48) through [bootstrap.py:55](/home/john/elspeth/src/elspeth/engine/bootstrap.py#L55).

This is inconsistent with the rest of the config layer, which strips and validates eagerly. For example, `GateSettings` rejects blank names and validates expressions during model construction in [config.py:502](/home/john/elspeth/src/elspeth/core/config.py#L502) through [config.py:528](/home/john/elspeth/src/elspeth/core/config.py#L528), and RAG provider configs reject unknown providers in-model in [rag/config.py:106](/home/john/elspeth/src/elspeth/plugins/transforms/rag/config.py#L106) through [rag/config.py:112](/home/john/elspeth/src/elspeth/plugins/transforms/rag/config.py#L112).

## Root Cause Hypothesis

These models were implemented with minimal `Field(min_length=1)` constraints instead of the repo’s normal `field_validator`/`model_validator` pattern. As a result, “non-empty string” is treated as sufficient validation even for fields whose downstream consumers require trimmed, recognized, or syntactically valid values.

## Suggested Fix

Add eager validators in `dependency_config.py` that match the rest of ELSPETH’s config behavior:

- Strip and reject blank-only strings for `name`, `settings`, `condition`, `collection`, and `provider`.
- Validate `condition` with `ExpressionParser` at model-construction time.
- Validate `provider` against the supported probe provider registry, or convert it to a constrained enum/`Literal` if the supported set is intentionally small.

## Impact

Invalid preflight configuration is accepted as “validated” and only fails later during bootstrap. That delays operator feedback, wastes setup work, and breaks the config-contract expectation that bad settings are rejected at the configuration boundary rather than surfacing as later runtime/preflight errors.
