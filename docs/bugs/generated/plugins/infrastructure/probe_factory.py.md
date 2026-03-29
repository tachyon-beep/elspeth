## Summary

`ChromaCollectionProbe` validates client-mode defaults with `ChromaConnectionConfig` but discards the normalized model, so valid configs that omit `port` and/or `ssl` crash later with `KeyError` inside `probe()`.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/infrastructure/probe_factory.py`
- Line(s): 25-38, 48-62
- Function/Method: `ChromaCollectionProbe.__init__`, `ChromaCollectionProbe.probe`

## Evidence

[`probe_factory.py`](/home/john/elspeth/src/elspeth/plugins/infrastructure/probe_factory.py#L25) validates the config by constructing a `ChromaConnectionConfig`, but it keeps the original raw mapping:

```python
def __init__(self, collection: str, config: Mapping[str, Any]) -> None:
    self.collection_name = collection
    self._config = config
    try:
        ChromaConnectionConfig(collection=collection, **config)
```

[`connection.py`](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/connection.py#L44) defines defaults for client mode:

```python
port: int = Field(default=8000, ge=1, le=65535)
ssl: bool = Field(default=True)
```

But [`probe_factory.py`](/home/john/elspeth/src/elspeth/plugins/infrastructure/probe_factory.py#L58) later reads those fields from the raw mapping, not from the validated model:

```python
client = chromadb.HttpClient(
    host=self._config["host"],
    port=self._config["port"],
    ssl=self._config["ssl"],
)
```

So a config like `{"mode": "client", "host": "chroma.local"}` is accepted at construction time, then fails at runtime with `KeyError: 'port'` or `KeyError: 'ssl'`.

That accepted config is already treated as valid by the test suite in [`test_probe_factory.py`](/home/john/elspeth/tests/unit/plugins/infrastructure/test_probe_factory.py#L193):

```python
probe = ChromaCollectionProbe("test-col", {"mode": "client", "host": "chroma.local"})
```

The failure path is user-visible. In the CLI, preflight wraps unexpected exceptions as fatal errors in [`cli.py`](/home/john/elspeth/src/elspeth/cli.py#L498), so this turns a valid config into an unexpected startup crash instead of a readiness result or clean config error.

## Root Cause Hypothesis

The file uses a construct-and-discard validation pattern correctly for constraint checking, but incorrectly for fields with defaults. `ChromaConnectionConfig` normalizes missing client fields (`port`, `ssl`), yet `ChromaCollectionProbe` throws that normalized object away and continues using the original `provider_config` mapping. The implementation therefore violates its own config contract whenever validation injects defaults.

## Suggested Fix

Store the validated `ChromaConnectionConfig` instance and use typed attribute access in `probe()` instead of raw dict indexing. For example:

```python
self._connection = ChromaConnectionConfig(collection=collection, **config)
```

Then:

```python
if self._connection.mode == "persistent":
    client = chromadb.PersistentClient(path=self._connection.persist_directory)
else:
    client = chromadb.HttpClient(
        host=self._connection.host,
        port=self._connection.port,
        ssl=self._connection.ssl,
    )
```

Add a regression test that calls `probe()` for client mode with only `host` set and asserts `HttpClient` receives `port=8000, ssl=True`.

## Impact

Any commencement gate that uses a Chroma collection probe in `client` mode with omitted default fields can fail before gate evaluation starts, even though the config was accepted as valid. That breaks the config/validation contract, turns supported YAML into a fatal preflight crash, and prevents readiness data from reaching gate context or audit recording.
