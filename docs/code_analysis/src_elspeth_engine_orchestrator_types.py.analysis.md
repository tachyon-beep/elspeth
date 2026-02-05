# Analysis: src/elspeth/engine/orchestrator/types.py

**Lines:** 130
**Role:** Type definitions for the orchestrator package. Defines PipelineConfig (run input), RunResult (run output statistics), AggregationFlushResult (aggregation flush counters), RouteValidationError (config validation exception), and the RowPlugin type alias.
**Key dependencies:** Imports `RunStatus` from contracts, `GateProtocol` and `TransformProtocol` from protocols (runtime, for RowPlugin type alias). Used by all other orchestrator submodules (core, validation, export, aggregation) and by external consumers of the orchestrator package.
**Analysis depth:** FULL

## Summary

This is a clean leaf module that correctly follows the project's import cycle prevention strategy. The types are well-defined with appropriate use of dataclasses. The `AggregationFlushResult.__add__` method is a nice design for combining flush results. One notable concern is the lack of immutability on `PipelineConfig` and `RunResult`, and a subtle issue with the `AggregationFlushResult` frozen dataclass containing a mutable dict field.

## Warnings

### [89-105] AggregationFlushResult is frozen but contains mutable dict

**What:** `AggregationFlushResult` is declared `frozen=True` but has a `routed_destinations: dict[str, int]` field. While `frozen=True` prevents reassigning the field (`result.routed_destinations = new_dict` raises `FrozenInstanceError`), it does not prevent mutating the dict's contents (`result.routed_destinations["sink_a"] = 5` would succeed).

**Why it matters:** The `frozen=True` decorator provides a false sense of immutability. Code that receives an `AggregationFlushResult` and mutates `routed_destinations` would affect all holders of the same reference. In practice, the current codebase constructs `AggregationFlushResult` with `dict(routed_destinations)` (creating a fresh dict), and the `__add__` method also creates new dicts, so this is not currently exploitable. But it is a latent bug if future code assumes true immutability.

**Evidence:**
```python
@dataclass(frozen=True, slots=True)
class AggregationFlushResult:
    routed_destinations: dict[str, int] = field(default_factory=dict)
```

### [44-67] PipelineConfig is a mutable dataclass holding mutable collections

**What:** `PipelineConfig` is a plain (non-frozen) dataclass with mutable fields: `transforms: list[RowPlugin]`, `sinks: dict[str, SinkProtocol]`, `config: dict[str, Any]`, `gates: list[GateSettings]`, `aggregation_settings: dict[str, AggregationSettings]`, `coalesce_settings: list[CoalesceSettings]`. Any code with a reference to a `PipelineConfig` can mutate its contents.

**Why it matters:** The orchestrator passes `config` (a `PipelineConfig` instance) to multiple functions and the processor. If any of these functions mutate the config (e.g., appending to `transforms` or modifying `sinks`), it would affect all other consumers. Given that `PipelineConfig` is constructed once and read by many, mutability is a risk. However, a review of the codebase shows it is used as read-only in practice.

**Evidence:**
```python
@dataclass
class PipelineConfig:
    source: SourceProtocol
    transforms: list[RowPlugin]
    sinks: dict[str, SinkProtocol]
    config: dict[str, Any] = field(default_factory=dict)
    gates: list[GateSettings] = field(default_factory=list)
    aggregation_settings: dict[str, AggregationSettings] = field(default_factory=dict)
    coalesce_settings: list[CoalesceSettings] = field(default_factory=list)
```

## Observations

### [107-121] AggregationFlushResult.__add__ is correct and clean

The `__add__` method correctly combines two results by summing all integer counters and merging `routed_destinations` using `Counter`. This enables clean accumulation: `total = result1 + result2`. The method creates a new `AggregationFlushResult` (immutable pattern), which is correct.

### [70-86] RunResult has comprehensive counter fields

`RunResult` includes counters for all major outcome types: succeeded, failed, routed, quarantined, forked, coalesced, coalesce_failed, expanded, buffered. The `routed_destinations` dict provides per-sink routing counts. This matches the counters tracked in `orchestrator.core`.

### [40] RowPlugin type alias is well-placed

The `RowPlugin = TransformProtocol | GateProtocol` alias centralizes the union type used throughout the transforms list, avoiding repetition. The comment about `BaseAggregation` deletion provides historical context.

### [124-130] RouteValidationError is appropriately simple

A plain Exception subclass with a descriptive docstring. No additional fields or methods needed for its use case (carrying a message about invalid route configuration).

### [31-35] Runtime protocol imports are correctly placed outside TYPE_CHECKING

The `GateProtocol` and `TransformProtocol` imports are at runtime (not under `TYPE_CHECKING`) because they are used in the `RowPlugin` type alias which participates in runtime `isinstance()` checks. This is correct and matches the documented rationale in the comment.

## Verdict

**Status:** SOUND
**Recommended action:** No changes required. The module is clean, focused, and correctly structured as a leaf module. The mutable dict in frozen dataclass is a theoretical concern but not practically exploitable in the current codebase. Consider making `PipelineConfig` frozen if the codebase grows to include more consumers.
**Confidence:** HIGH -- This is a simple data definitions module with clear semantics.
