# Analysis: src/elspeth/plugins/transforms/passthrough.py

**Lines:** 95
**Role:** Passthrough transform -- passes rows through unchanged. Used as a placeholder or for testing pipeline wiring.
**Key dependencies:** `BaseTransform`, `TransformDataConfig`, `PipelineRow`, `TransformResult`, `create_schema_from_config`, `copy.deepcopy`
**Analysis depth:** FULL

## Summary

PassThrough is a clean, minimal transform that follows established codebase patterns closely. It correctly uses `allow_coercion=False`, deep-copies row data to prevent mutation, passes through `contract` on result, and wires `_on_error` from config. No critical findings. One minor observation about defensive validation gating. Overall a solid, well-structured file.

## Critical Findings

None.

## Warnings

### [84] Validation gating on `is_observed` could silently skip validation for observed schemas

**What:** The condition `if self._validate_input and not self._schema_config.is_observed` means that if a user configures `validate_input: true` alongside `schema: {mode: observed}`, validation is silently skipped. No warning or error is raised to inform the user their configuration is contradictory.

**Why it matters:** A user who explicitly opts into validation expects it to happen. Silently skipping it means they believe validation is active when it is not. In a high-stakes pipeline, this false confidence could mean data problems go undetected. However, this is a design choice shared across multiple transforms (field_mapper uses the same pattern), so this is a systemic pattern, not a bug local to this file.

**Evidence:**
```python
if self._validate_input and not self._schema_config.is_observed:
    self.input_schema.model_validate(row.to_dict())  # Raises on failure
```
If `is_observed` is True, the `model_validate` call is never reached, even with `validate_input=True`.

## Observations

### [88] Deep copy is correct but has performance implications

**What:** `copy.deepcopy(row.to_dict())` creates a full deep copy of every row passing through.

**Why it matters:** For a passthrough transform, every row pays the cost of deep copy even though no mutation occurs. This is the correct safety choice (preventing downstream mutation from reaching the original), but for high-throughput pipelines, a passthrough in the DAG adds measurable overhead. This is an acceptable trade-off given audit integrity requirements.

### [66-67] Input and output schemas are identical reference

**What:** Both `self.input_schema` and `self.output_schema` are set to the same schema object. This is correct for a passthrough (no shape change), and consistent with the truncate transform pattern.

### [55] Explicit `_on_error` wiring from config

**What:** `self._on_error: str | None = cfg.on_error` correctly wires the error routing from `TransformDataConfig`. Since PassThrough never returns `TransformResult.error()`, the `_on_error` field will never be read by the engine. But it is still correct to wire it -- the config accepts the field, and wiring it prevents orphaning.

## Verdict

**Status:** SOUND
**Recommended action:** No changes required. The validation-gating observation is a systemic pattern, not a local issue.
**Confidence:** HIGH -- Small file, clear logic, follows established patterns exactly.
