## Summary

DatabaseSink does not actually enforce its documented “wrong types = upstream bug = crash” contract by default; with `validate_input=False`, permissive databases like SQLite will silently persist schema-invalid values instead of failing.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/plugins/sinks/database_sink.py`
- Line(s): 59, 121, 134-143, 446-514
- Function/Method: `DatabaseSink.__init__`, `DatabaseSink.write`

## Evidence

`DatabaseSink` advertises strict no-coercion behavior:

```python
# src/elspeth/plugins/sinks/database_sink.py:5-6
IMPORTANT: Sinks use allow_coercion=False to enforce that transforms
output correct types. Wrong types = upstream bug = crash.
```

and builds a non-coercing schema:

```python
# src/elspeth/plugins/sinks/database_sink.py:134-140
self._schema_class: type[PluginSchema] = create_schema_from_config(
    self._schema_config,
    "DatabaseRowSchema",
    allow_coercion=False,
)
```

But runtime validation is disabled by default and only stored as a flag:

```python
# src/elspeth/plugins/sinks/database_sink.py:59,121
validate_input: bool = False
self.validate_input = cfg.validate_input
```

The sink’s `write()` method never validates rows itself before `INSERT`:

```python
# src/elspeth/plugins/sinks/database_sink.py:501-513
insert_rows = self._serialize_any_typed_fields(rows)
with self._engine.begin() as conn:
    conn.execute(insert(self._table), insert_rows)
```

The only validation hook is executor-side and optional:

```python
# src/elspeth/engine/executors/sink.py:206-216
if sink.validate_input:
    for row in rows:
        try:
            sink.input_schema.model_validate(row)
        except ValidationError as e:
            raise PluginContractViolation(...)
```

So for the default config, schema-invalid rows reach the database unchecked. I verified the integration behavior against SQLite: inserting `{"id": "not-an-int"}` into an `Integer` column succeeds and reads back as a `str`, which means this sink can silently persist upstream type bugs instead of crashing.

## Root Cause Hypothesis

The file assumes `allow_coercion=False` on the schema class is sufficient, but that schema is not enforced unless `validate_input` is turned on manually. The default `False` value turns a contractual sink invariant into optional behavior.

## Suggested Fix

Make type validation mandatory for `DatabaseSink` instead of config-controlled. The smallest target-file fix is to force `self.validate_input = True` in `__init__` and remove or ignore the config toggle for this sink.

If a local guard is preferred, validate inside `write()` before any DDL/DML:

```python
for row in rows:
    self.input_schema.model_validate(row)
```

and let validation failures crash as upstream plugin bugs.

## Impact

Schema-invalid pipeline data can be durably written with the wrong types, especially on SQLite. That violates the Tier 2 sink rule (“no coercion, expect types”), hides upstream transform/source bugs, and can corrupt the audit record by making a bad write look like a legitimate successful sink operation.
---
## Summary

When `DatabaseSink` serializes `dict`/`list` values for `any` fields or observed-mode rows, it hashes and audits the pre-serialization rows instead of the actual SQL payload it sends, so the recorded `content_hash` no longer proves what was written.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `src/elspeth/plugins/sinks/database_sink.py`
- Line(s): 167-193, 464-471, 501-526, 556-563
- Function/Method: `_serialize_any_typed_fields`, `write`

## Evidence

The sink computes its artifact hash from the original rows before any sink-owned transformation:

```python
# src/elspeth/plugins/sinks/database_sink.py:464-471
canonical_payload = canonical_json(rows).encode("utf-8")
content_hash = hashlib.sha256(canonical_payload).hexdigest()
payload_size = len(canonical_payload)
```

But immediately after that, it rewrites complex values into JSON strings before issuing SQL:

```python
# src/elspeth/plugins/sinks/database_sink.py:167-193
if isinstance(value, (dict, list)):
    new_row[field] = json.dumps(value)

# src/elspeth/plugins/sinks/database_sink.py:501-513
insert_rows = self._serialize_any_typed_fields(rows)
with self._engine.begin() as conn:
    conn.execute(insert(self._table), insert_rows)
```

The SQL call record also omits the payload and only stores metadata:

```python
# src/elspeth/plugins/sinks/database_sink.py:518-526
ctx.record_call(
    call_type=CallType.SQL,
    status=CallStatus.SUCCESS,
    request_data={
        "operation": "INSERT",
        "table": self._table_name,
        "row_count": len(rows),
    },
```

That conflicts with the contract:

```python
# docs/contracts/plugin-protocol.md:831-839
| database | SHA-256 of canonical JSON payload BEFORE insert | Proves intent ... |
Key principle: Hash what YOU control ... hash the payload you're sending
```

Here the sink controls `_serialize_any_typed_fields()`, so the payload being sent is `insert_rows`, not `rows`. For a representative row like `{"payload": {"b": 2, "a": 1}}`, the pre-serialization canonical hash and the post-serialization SQL-payload hash differ, because the sent payload becomes a JSON string, not the original nested object.

Repo-local contrast: `ChromaSink` explicitly hashes the actual payload sent after sink-side mutation (`src/elspeth/plugins/sinks/chroma_sink.py:399-425`).

## Root Cause Hypothesis

The implementation assumes only the destination database mutates data, so hashing `rows` is “good enough.” That became false once this file introduced sink-side serialization of complex values into strings. The call audit was not updated to persist the transformed request payload.

## Suggested Fix

Hash and size the actual SQL payload after `_serialize_any_typed_fields()`:

```python
insert_rows = self._serialize_any_typed_fields(rows)
canonical_payload = canonical_json(insert_rows).encode("utf-8")
```

and record enough request data to reconstruct that payload, either by:
- passing the transformed rows in `request_data`, or
- explicitly storing them via payload-store refs and recording the ref/hash.

## Impact

For rows containing complex values in `any` fields or observed-mode columns, the artifact hash and SQL call record do not prove what the sink actually sent. After payload purge, `explain()` can show a successful sink write whose recorded hash does not correspond to the real SQL request body, weakening auditability for exactly the cases this sink special-cases.
