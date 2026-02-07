# Bug Report: Mutable Operator Allowlists Allow Runtime Tampering of Expression Rules

## Summary

- `_COMPARISON_OPS`, `_BINARY_OPS`, `_UNARY_OPS`, and `_BOOL_OPS` are mutable module-level dicts that define the expression whitelist; any import can mutate them and silently change validation/evaluation rules.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row @ `1c70074ef3b71e4fe85d4f926e52afeca50197ab`
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Deep bug audit of `src/elspeth/engine/expression_parser.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. In a Python shell, run:
   ```python
   import ast, operator
   from elspeth.engine.expression_parser import _BINARY_OPS, ExpressionParser
   _BINARY_OPS[ast.Pow] = operator.pow
   parser = ExpressionParser("row['x'] ** 2")
   parser.evaluate({"x": 3})
   ```
2. Observe that the expression parses and evaluates successfully.

## Expected Behavior

- The expression whitelist should be immutable at runtime, and forbidden operators like `**` should always be rejected.

## Actual Behavior

- Mutating the operator maps enables previously forbidden operators, and the parser accepts and evaluates expressions that should be blocked.

## Evidence

- Mutable operator allowlists defined at module scope: `src/elspeth/engine/expression_parser.py:48-83`.
- Validation uses these maps to decide what is allowed: `src/elspeth/engine/expression_parser.py:182-206`.
- Evaluation uses these maps to execute operations: `src/elspeth/engine/expression_parser.py:368-415`.

## Impact

- User-facing impact: Config gates and trigger conditions can be altered at runtime if any in-process code mutates the allowlists, leading to unexpected routing behavior.
- Data integrity / security impact: Undermines the “restricted expression parser” guarantee and can allow forbidden operations to execute, eroding auditability and security boundaries.
- Performance or cost impact: Indirect; allows enabling heavier operators (e.g., exponentiation) or custom functions, potentially increasing runtime costs.

## Root Cause Hypothesis

- The operator allowlists are mutable module-level dicts and are not protected against modification, so runtime mutation changes both validation and evaluation behavior.

## Proposed Fix

- Code changes (modules/files): Make operator allowlists immutable in `src/elspeth/engine/expression_parser.py` (e.g., `types.MappingProxyType` or `Final[Mapping[...]]`), and avoid exposing mutable references.
- Config or schema changes: None.
- Tests to add/update: Add a unit test that attempts to mutate each operator map and asserts a `TypeError` (or equivalent) is raised; add a regression test showing forbidden operators remain rejected after attempted mutation.
- Risks or migration steps: Minimal; ensure tests or internal code don’t rely on mutating these dicts (none found in repo).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/contracts/plugin-protocol.md:824-843` (restricted expression parser rules).
- Observed divergence: The whitelist is mutable at runtime, so the “restricted parser” guarantee can be bypassed by in-process mutation.
- Reason (if known): Likely an oversight during initial implementation; no immutability enforcement added.
- Alignment plan or decision needed: Make allowlists immutable and add tests to enforce the restriction boundary.

## Acceptance Criteria

- Attempts to mutate operator allowlists raise an error.
- Expressions using forbidden operators (e.g., `**`) are rejected even after attempted mutation.
- Existing expression parser tests still pass.

## Tests

- Suggested tests to run: `python -m pytest tests/engine/test_expression_parser.py`
- New tests required: yes, immutability regression tests for operator allowlists.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/contracts/plugin-protocol.md` (Expression Safety section).
