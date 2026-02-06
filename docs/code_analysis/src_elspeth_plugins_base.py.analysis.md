# Analysis: src/elspeth/plugins/base.py

**Lines:** 506
**Role:** Base classes for all plugins -- `BaseTransform`, `BaseGate`, `BaseSink`, `BaseSource`. These provide default attribute values, lifecycle hooks, and enforce the abstract methods that subclasses must implement. Every concrete plugin in the system inherits from one of these.
**Key dependencies:** Imports `ArtifactDescriptor`, `Determinism`, `PluginSchema`, `SourceRow`, `PipelineRow` from `elspeth.contracts`; imports `PluginContext` from `elspeth.plugins.context`; imports `GateResult`, `TransformResult` from `elspeth.plugins.results`. TYPE_CHECKING imports for `SchemaContract`, `OutputValidationResult`. Consumed by all concrete plugins (CSVSource, JSONSource, AzureBlobSource, FieldMapper, Truncate, etc.), the plugin manager, and tests.
**Analysis depth:** FULL

## Summary

The base classes are well-structured and correctly implement the protocols from `protocols.py`. The class hierarchy is clean, abstract methods are properly marked, and lifecycle hooks use the correct `noqa: B027` pattern for optional overrides. The main concerns are: (1) class-level mutable default for `_output_contract` on `BaseSink` and `_schema_contract` on `BaseSource` (safe in practice because `__init__` re-initializes them, but fragile), (2) `BaseSource._on_validation_failure` is declared as a type annotation without a default value, which could cause `AttributeError` if a subclass forgets to set it, and (3) `BaseTransform.process()` is not declared `@abstractmethod` -- it raises `NotImplementedError` manually instead, which means mypy and static analysis cannot catch missing implementations at definition time.

## Critical Findings

No critical findings.

## Warnings

### [62-124] BaseTransform.process() is not @abstractmethod -- subclass omissions are only caught at runtime

**What:** `BaseTransform.process()` at line 102 is a concrete method that raises `NotImplementedError`. It is NOT decorated with `@abstractmethod`. This means a subclass can be instantiated without implementing `process()`, and the error only surfaces at runtime when `process()` is called.

**Why it matters:** The `BaseGate.evaluate()` at line 195 IS properly `@abstractmethod`, and `BaseSink.write()`, `BaseSink.flush()`, `BaseSink.close()`, and `BaseSource.load()`, `BaseSource.close()` are all `@abstractmethod`. `BaseTransform.process()` is the sole exception, and it is the most commonly subclassed base method. A developer who creates a new transform subclass and forgets to implement `process()` will not get a clear error at class definition or instantiation -- they will get a confusing `NotImplementedError` at processing time during a pipeline run.

**Evidence:**
```python
# Line 102 -- NOT abstract:
def process(
    self,
    row: PipelineRow,
    ctx: PluginContext,
) -> TransformResult:
    raise NotImplementedError(...)

# Compare line 195 -- IS abstract:
@abstractmethod
def evaluate(
    self,
    row: PipelineRow,
    ctx: PluginContext,
) -> GateResult:
```

The comment on line 110-111 explains this is intentional because batch-aware transforms have a different signature. However, this means `@abstractmethod` protection is lost for ALL transforms, not just batch-aware ones. A better approach would be to make `process()` abstract and have batch-aware transforms override it, or to use separate base classes.

### [326, 429] Class-level mutable defaults for _output_contract and _schema_contract

**What:** `BaseSink._output_contract` is set to `None` at class level (line 326), then re-set to `None` in `__init__` (line 335). Similarly, `BaseSource._schema_contract` is set to `None` at class level (line 429), then re-set in `__init__` (line 438).

**Why it matters:** While `None` is immutable so there is no actual shared-state bug, this pattern is fragile. If a future developer changes the default to a mutable value (e.g., a dict or list), all instances would share the same object. The class-level annotation at line 326 (`_output_contract: "SchemaContract | None" = None`) serves as both a type annotation and a default, and the `__init__` re-assignment at line 335 is the actual safety net. Removing the `__init__` re-assignment in a future refactor would not cause an immediate bug (because `None` is safe) but would establish a pattern that fails when defaults become mutable.

**Evidence:**
```python
# Line 326 -- class-level default:
_output_contract: "SchemaContract | None" = None

# Line 335 -- re-initialized in __init__:
self._output_contract = None
```

### [426] BaseSource._on_validation_failure has no default value -- AttributeError if subclass forgets to set it

**What:** `BaseSource._on_validation_failure` is declared as `_on_validation_failure: str` at line 426 without a default value. This is a bare type annotation -- it does not create a class attribute. If a subclass `__init__` does not call `self._on_validation_failure = ...`, accessing the attribute will raise `AttributeError`.

**Why it matters:** While all current concrete sources (CSVSource, JSONSource, NullSource, AzureBlobSource) correctly set `_on_validation_failure` in their constructors via `SourceDataConfig`, a new source plugin that forgets to set it would crash at runtime when the orchestrator validation reads `source._on_validation_failure` (line 161 of `orchestrator/validation.py`). This is "correct" per the crash-on-bug philosophy in CLAUDE.md, but it would be better to catch it earlier -- either with `@abstractmethod` or by raising in `BaseSource.__init__` if not set.

**Evidence:**
```python
# Line 426 -- bare annotation, no default:
_on_validation_failure: str

# Compare line 429 -- has a default:
_schema_contract: "SchemaContract | None" = None
```

The `NullSource` works around this by explicitly setting it:
```python
# null_source.py line 54:
_on_validation_failure: str = "discard"
```

## Observations

### [40-149] BaseTransform is cleanly designed with clear documentation

**What:** The class structure, docstrings, and attribute defaults are well-organized. The `noqa: B027` annotations on lifecycle hooks correctly suppress the "empty method" lint warning for intentionally empty optional hooks.

### [183-193] BaseGate.__init__ uses config["routes"] and config.get("fork_to")

**What:** `BaseGate.__init__` accesses `config["routes"]` with direct key access (crash if missing) and `config.get("fork_to")` with `.get()` (returns None if missing). Per the data manifesto, `config` is system-owned data, so direct access is correct for required fields. The `.get()` for `fork_to` is correct because it is genuinely optional (most gates don't fork).

### [279-295] BaseSink.configure_for_resume() properly raises NotImplementedError

**What:** The default implementation raises `NotImplementedError` with a clear message. Sinks that claim `supports_resume=True` must override this. This is the correct pattern -- the engine only calls this method after checking `supports_resume`, so sinks that don't support resume will never hit this code path.

### [366-383] BaseSink output contract getter/setter pattern is simple and appropriate

**What:** `get_output_contract()` and `set_output_contract()` are simple getter/setter methods. While this is unusual in Python (where properties are preferred), it matches the pattern used in `BaseSource` for `get_schema_contract()` / `set_schema_contract()`. Consistency within the codebase is more valuable than adhering to Python idiom.

### [491-506] BaseSource.get_field_resolution() default returns None

**What:** The default implementation returns `None`, indicating no field normalization. Sources that perform normalization (CSVSource, AzureBlobSource) override this. The return type `tuple[dict[str, str], str | None] | None` is complex but necessary to distinguish "no normalization" from "normalization with/without version".

### [Missing] No BaseCoalesce class exists

**What:** All other plugin types have base classes (`BaseTransform`, `BaseGate`, `BaseSink`, `BaseSource`), but there is no `BaseCoalesce`. The `CoalesceProtocol` exists in `protocols.py` but has no corresponding base class. The engine handles coalesce internally via `CoalesceExecutor` rather than through a plugin base class.

**Why it matters:** This is consistent with the current design where coalesce is an engine-level concern, not a user-configurable plugin. However, if custom coalesce strategies are needed in the future, a base class will need to be created.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Consider making `BaseTransform.process()` abstract, with a separate `BaseBatchTransform` class for batch-aware transforms that makes the batch `process()` abstract instead. This eliminates the runtime-only error detection for missing implementations. (2) The `_on_validation_failure` bare annotation is technically fine (crash-on-bug) but adding validation in `BaseSource.__init__` (e.g., checking `hasattr(self, '_on_validation_failure')` post-init) would catch misconfigured subclasses earlier. (3) The class-level `None` defaults for `_output_contract` and `_schema_contract` are safe but should not be extended to mutable defaults.
**Confidence:** HIGH -- Full read, cross-referenced all concrete implementations (CSVSource, JSONSource, NullSource, AzureBlobSource, FieldMapper, Truncate, etc.) and all engine consumers.
