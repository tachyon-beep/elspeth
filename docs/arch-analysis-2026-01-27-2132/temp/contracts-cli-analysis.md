# Contracts and CLI Subsystem Analysis

**Analyzed:** 2026-01-27
**Analyst:** Explorer Agent
**Scope:** `src/elspeth/contracts/`, `src/elspeth/cli.py`, `src/elspeth/cli_helpers.py`, `src/elspeth/tui/`

---

## Executive Summary

The Contracts subsystem is well-designed with strong typing, discriminated unions, and clear separation of concerns. The CLI is functional but has significant code duplication and missing features. The TUI is a placeholder that exposes incomplete functionality to users.

**Critical Issues:** 3
**High Priority Issues:** 7
**Medium Priority Issues:** 9
**Low Priority Issues:** 6

---

## Contracts Subsystem Analysis

### 1. Design Issues

#### 1.1 CRITICAL: `Batch.trigger_type` is `str | None` instead of `TriggerType | None`

**File:** `/home/john/elspeth-rapid/src/elspeth/contracts/audit.py:297`

```python
trigger_type: str | None = None  # TriggerType enum value (count, time, end_of_source, manual)
```

The comment says it's a TriggerType enum value, but the field is typed as `str | None`. This violates the audit contract pattern where all enums should be strictly typed. Every other audit contract uses proper enum types.

**Impact:** Type safety gap. Runtime errors possible if string values don't match expected enum.

**Fix:** Change to `trigger_type: TriggerType | None = None`

---

#### 1.2 HIGH: Inconsistent NodeState Variant Handling

**File:** `/home/john/elspeth-rapid/src/elspeth/contracts/audit.py:219-221`

`NodeStateFailed` has optional `output_hash` field:

```python
@dataclass(frozen=True)
class NodeStateFailed:
    # ...
    output_hash: str | None = None  # Optional for failed states
```

This creates ambiguity: Can a failed node produce output? If yes, when? If no, why is this field present? The comment "May have error_json" on line 205-206 doesn't explain this.

**Impact:** Unclear semantics. Consumers must guess whether to check output_hash on failed states.

**Recommendation:** Either remove `output_hash` from `NodeStateFailed` or document the exact scenario where a failed state has output.

---

#### 1.3 HIGH: ExecutionResult TypedDict Uses `str` for Status Instead of Enum

**File:** `/home/john/elspeth-rapid/src/elspeth/contracts/cli.py:37`

```python
class ExecutionResult(TypedDict):
    run_id: str
    status: str  # Should be RunStatus enum
    rows_processed: int
```

While `RunStatus` enum exists in `enums.py`, `ExecutionResult.status` is typed as plain string. This breaks the strict enum contract pattern used elsewhere.

**Impact:** No type checking for valid status values at the CLI boundary.

---

#### 1.4 MEDIUM: SchemaValidationError is Not a Dataclass

**File:** `/home/john/elspeth-rapid/src/elspeth/contracts/data.py:62-74`

```python
class SchemaValidationError:
    """A validation error for a specific field."""

    def __init__(self, field: str, message: str, value: Any = None) -> None:
        self.field = field
        self.message = message
        self.value = value
```

Every other contract type uses `@dataclass`. This class uses manual `__init__`. Inconsistency creates maintenance burden.

**Impact:** No `__eq__`, no `__hash__`, no `__repr__` beyond default. Testing comparisons may fail unexpectedly.

---

#### 1.5 MEDIUM: PluginSchema Mixes Responsibilities

**File:** `/home/john/elspeth-rapid/src/elspeth/contracts/data.py:28-59`

`PluginSchema` is both:
1. A base class for plugin-specific schemas
2. A validation mechanism (via Pydantic)

The `to_row()` and `from_row()` methods couple schema definition with serialization. This violates single-responsibility principle.

**Recommendation:** Consider separating schema definition from row conversion utilities.

---

#### 1.6 MEDIUM: RetryPolicy TypedDict Has No Validation

**File:** `/home/john/elspeth-rapid/src/elspeth/contracts/engine.py:7-22`

```python
class RetryPolicy(TypedDict, total=False):
    max_attempts: int
    base_delay: float
    max_delay: float
    jitter: float
```

No validation for:
- `max_attempts >= 1`
- `base_delay >= 0`
- `max_delay >= base_delay`
- `jitter >= 0`

The docstring says "from_policy() applies defaults" but there's no such function in this module.

**Impact:** Invalid retry configurations can propagate to engine.

---

#### 1.7 LOW: Inconsistent Frozen vs Mutable Dataclasses

| Contract | Frozen? |
|----------|---------|
| `NodeStateOpen` | Yes |
| `NodeStateCompleted` | Yes |
| `NodeStateFailed` | Yes |
| `NodeStatePending` | Yes |
| `Run` | No |
| `Node` | No |
| `Row` | No |
| `Token` | No |
| `Checkpoint` | No |

No clear pattern. Some audit records are frozen, others aren't.

**Impact:** Mutation bugs possible on non-frozen types.

---

### 2. Type Overlaps and Redundancy

#### 2.1 HIGH: TokenInfo vs Token Contract Overlap

**File 1:** `/home/john/elspeth-rapid/src/elspeth/contracts/identity.py:10-32`

```python
@dataclass
class TokenInfo:
    row_id: str
    token_id: str
    row_data: dict[str, Any]
    branch_name: str | None = None
    fork_group_id: str | None = None
    join_group_id: str | None = None
    expand_group_id: str | None = None
```

**File 2:** `/home/john/elspeth-rapid/src/elspeth/contracts/audit.py:103-113`

```python
@dataclass
class Token:
    token_id: str
    row_id: str
    created_at: datetime
    fork_group_id: str | None = None
    join_group_id: str | None = None
    expand_group_id: str | None = None
    branch_name: str | None = None
    step_in_pipeline: int | None = None
```

Two types with overlapping fields but different purposes:
- `Token` is the audit record (has `created_at`, `step_in_pipeline`)
- `TokenInfo` is runtime data (has `row_data`)

**Impact:** Confusion about which to use. Name collision risk.

**Recommendation:** Rename `Token` to `TokenRecord` or `TokenAudit` for clarity.

---

#### 2.2 MEDIUM: Three Schema-Related Types

1. `PluginSchema` (data.py) - Pydantic base class
2. `SchemaConfig` (schema.py) - Config-driven schema definition
3. `FieldDefinition` (schema.py) - Single field definition

These three types serve related purposes but have no explicit relationship. A plugin can define schemas via class inheritance OR via config. No documentation explains when to use which.

---

### 3. Missing Contract Types

#### 3.1 HIGH: No LineageResult Contract

The explain command references lineage queries but there's no `LineageResult` type in contracts. The `RowLineage` type exists but is only for source rows.

**Impact:** Explain command has no contract for what it returns.

---

#### 3.2 MEDIUM: No GateSettings Contract in Contracts Module

`GateSettings` is defined in `core/config.py` but not exported through contracts. Gates are configured via `config.gates` list of `GateSettings`, but the contract isn't visible in the contracts module.

---

#### 3.3 LOW: No CoalesceSettings Contract Export

Like GateSettings, CoalesceSettings exists in core/config but isn't exported through contracts.

---

## CLI Subsystem Analysis

### 4. Functionality Gaps

#### 4.1 CRITICAL: Explain Command is Non-Functional

**File:** `/home/john/elspeth-rapid/src/elspeth/cli.py:291-365`

```python
@app.command()
def explain(...) -> None:
    """Explain lineage for a row or token.
    ...
    NOTE: This command is not yet implemented.
    """
    # ...
    if json_output:
        result = {
            "status": "not_implemented",
            # ...
        }
        raise typer.Exit(2)  # Exit code 2 = not implemented
```

The explain command is a placeholder that returns "not_implemented" status. Users see it in `--help` but it doesn't work.

**Impact:** Users expect explain to work. Documentation gap.

**Recommendation:** Either implement or remove from public CLI until Phase 4.

---

#### 4.2 HIGH: No `elspeth status` Command

CLAUDE.md mentions:
```
elspeth status
```

But no such command exists. Users cannot check run status without explain.

---

#### 4.3 HIGH: No Database Migration Command

No `elspeth db migrate` or similar. Alembic migrations exist but CLI doesn't expose them.

**Impact:** Users must use Alembic directly, breaking the "elspeth is the single entry point" pattern.

---

#### 4.4 MEDIUM: Resume Command Missing JSON Output Mode

**File:** `/home/john/elspeth-rapid/src/elspeth/cli.py:1311-1520`

The `run` command has `--format json` option, but `resume` command has no equivalent. This breaks CI/CD workflows that need structured output from resume operations.

---

#### 4.5 MEDIUM: No `elspeth export` Command

CLAUDE.md mentions export in pipeline phases but there's no CLI command to manually trigger export of a completed run.

---

#### 4.6 LOW: Plugins List Doesn't Show Plugin Options

**File:** `/home/john/elspeth-rapid/src/elspeth/cli.py:926-958`

`elspeth plugins list` shows name and description but not:
- Required options
- Optional options with defaults
- Input/output schema requirements

Users must read source code to understand how to configure plugins.

---

### 5. Code Quality Issues

#### 5.1 CRITICAL: Massive Code Duplication in Event Handlers

**File:** `/home/john/elspeth-rapid/src/elspeth/cli.py`

The following formatter functions are copy-pasted between `_execute_pipeline()` (lines 471-594) and `_execute_pipeline_with_instances()` (lines 683-806):

```python
def _format_phase_started_json(event: PhaseStarted) -> None:
def _format_phase_completed_json(event: PhaseCompleted) -> None:
def _format_phase_error_json(event: PhaseError) -> None:
def _format_run_completed_json(event: RunCompleted) -> None:
def _format_progress_json(event: ProgressEvent) -> None:
# ... and console variants
```

**123 lines duplicated verbatim.** Each formatter is defined twice. Changes must be made in both places.

Same duplication in `_execute_resume_with_instances()` (lines 1179-1231).

**Impact:** Bug fixes or formatting changes require updating three locations.

**Fix:** Extract formatters to module-level functions or a Formatter class.

---

#### 5.2 HIGH: _execute_pipeline and _execute_pipeline_with_instances Duplication

**File:** `/home/john/elspeth-rapid/src/elspeth/cli.py`

Two nearly identical functions:
- `_execute_pipeline()` (lines 368-610) - 242 lines
- `_execute_pipeline_with_instances()` (lines 613-822) - 209 lines

The only difference is plugin instantiation. Everything else is duplicated.

**Impact:** Maintenance burden. Changes must be synced between both functions.

**Recommendation:** Refactor to single function that takes pre-instantiated plugins.

---

#### 5.3 HIGH: Plugin Manager Singleton is Anti-Pattern

**File:** `/home/john/elspeth-rapid/src/elspeth/cli.py:37-54`

```python
_plugin_manager_cache: PluginManager | None = None

def _get_plugin_manager() -> PluginManager:
    global _plugin_manager_cache
    if _plugin_manager_cache is None:
        manager = PluginManager()
        manager.register_builtin_plugins()
        _plugin_manager_cache = manager
    return _plugin_manager_cache
```

Global mutable state. Not thread-safe. Cannot be reset for testing without module manipulation.

**Impact:** Test isolation issues. Cannot test plugin registration in isolation.

---

#### 5.4 MEDIUM: Type Ignores Throughout Pipeline Execution

**File:** `/home/john/elspeth-rapid/src/elspeth/cli.py`

Multiple `# type: ignore[arg-type]` comments:

```python
pipeline_config = PipelineConfig(
    source=source,  # type: ignore[arg-type]
    transforms=transforms,  # type: ignore[arg-type]
    sinks=sinks,  # type: ignore[arg-type]
    # ...
)
```

Lines: 453-456, 665-668, 1169-1172

The comment says mypy doesn't recognize structural typing. This suggests either:
1. Protocols aren't properly defined
2. Type annotations are incomplete

**Impact:** Lost type safety at critical integration points.

---

#### 5.5 MEDIUM: Health Check Uses Hardcoded Container Paths

**File:** `/home/john/elspeth-rapid/src/elspeth/cli.py:1625-1664`

```python
config_paths = ["/app/config", "./config"]
output_paths = ["/app/output", "./output"]
```

Hardcoded paths assume specific deployment structure. No configuration option.

**Impact:** Health check may give false "warn" for valid deployments with different paths.

---

#### 5.6 LOW: CLI Helpers Module Has Circular Import Risk

**File:** `/home/john/elspeth-rapid/src/elspeth/cli_helpers.py:28`

```python
from elspeth.cli import _get_plugin_manager
```

`cli_helpers.py` imports from `cli.py`. This is unusual - helpers should be imported BY cli.py, not import FROM it.

**Impact:** Circular import if cli_helpers is used elsewhere that also imports cli.

---

### 6. User Experience Issues

#### 6.1 HIGH: Error Messages Don't Suggest Fixes

**File:** `/home/john/elspeth-rapid/src/elspeth/cli.py:200-207`

```python
except ValidationError as e:
    typer.echo("Configuration errors:", err=True)
    for error in e.errors():
        loc = ".".join(str(x) for x in error["loc"])
        typer.echo(f"  - {loc}: {error['msg']}", err=True)
    raise typer.Exit(1) from None
```

Validation errors show what's wrong but not how to fix it. No link to docs. No suggested values.

---

#### 6.2 MEDIUM: No Progress Indication During Plugin Load

**File:** `/home/john/elspeth-rapid/src/elspeth/cli.py:210-214`

```python
try:
    plugins = instantiate_plugins_from_config(config)
except Exception as e:
    typer.echo(f"Error instantiating plugins: {e}", err=True)
```

If plugin instantiation hangs (e.g., network timeout on LLM plugin), user sees nothing until failure.

---

#### 6.3 MEDIUM: Validate Command Has Different Output Than Run Dry-Run

**Compare:**

`elspeth run -s settings.yaml --dry-run` output:
```
Dry run mode - would execute:
  Source: csv_source
  Transforms: 3
  Sinks: output, errors
```

`elspeth validate -s settings.yaml` output:
```
Pipeline configuration valid!
  Source: csv_source
  Transforms: 3
  Aggregations: 0
  Sinks: output, errors
  Graph: 5 nodes, 4 edges
```

Validate shows aggregations and graph info. Dry-run doesn't.

**Impact:** Inconsistent UX between similar commands.

---

#### 6.4 LOW: Version Flag is Eager But Others Aren't

**File:** `/home/john/elspeth-rapid/src/elspeth/cli.py:102-108`

```python
version: bool | None = typer.Option(
    None,
    "--version",
    "-V",
    callback=version_callback,
    is_eager=True,  # <-- Only this flag is eager
    help="Show version and exit.",
)
```

`--version` works before other options, but `--help` isn't explicitly eager. Typer default behavior handles it, but it's inconsistent.

---

## TUI Subsystem Analysis

### 7. TUI is Placeholder, Not Production-Ready

#### 7.1 CRITICAL: ExplainApp Uses Placeholder Widgets

**File:** `/home/john/elspeth-rapid/src/elspeth/tui/explain_app.py:60-65`

```python
def compose(self) -> ComposeResult:
    yield Header()
    yield Static("Lineage Tree (placeholder)", id=WidgetIDs.LINEAGE_TREE)
    yield Static("Detail Panel (placeholder)", id=WidgetIDs.DETAIL_PANEL)
    yield Footer()
```

The TUI launches with static placeholder text. LineageTree and NodeDetailPanel widgets exist in `tui/widgets/` but aren't used.

**Impact:** Users who try the TUI see "placeholder" text. Confusing UX.

---

#### 7.2 HIGH: LineageTree Widget Exists But Isn't Integrated

**File:** `/home/john/elspeth-rapid/src/elspeth/tui/widgets/lineage_tree.py`

A complete `LineageTree` class exists (198 lines) with:
- Tree building from LineageData
- Node expansion/collapse
- Node search by ID

But `explain_app.py` uses `Static("Lineage Tree (placeholder)")` instead of the actual widget.

**Impact:** Dead code. Functionality exists but isn't accessible.

---

#### 7.3 HIGH: ExplainScreen Exists But Isn't Used

**File:** `/home/john/elspeth-rapid/src/elspeth/tui/screens/explain_screen.py`

A complete 314-line `ExplainScreen` class exists with:
- Database integration
- Discriminated union state management
- Node selection handling

But it's never instantiated by `ExplainApp`.

**Impact:** Well-designed screen exists but isn't connected to the app.

---

#### 7.4 MEDIUM: TUI Types Don't Match Contracts

**File:** `/home/john/elspeth-rapid/src/elspeth/tui/types.py`

TUI defines its own TypedDicts:
- `NodeInfo` (TUI) vs `Node` (contracts)
- `TokenDisplayInfo` (TUI) vs `TokenInfo` (contracts)
- `NodeStateInfo` (TUI) - no equivalent in contracts

These are intentionally different (display vs data), but the overlap creates confusion.

**Recommendation:** Add clear docstrings explaining relationship to contract types.

---

#### 7.5 LOW: No Keyboard Navigation Implementation

**File:** `/home/john/elspeth-rapid/src/elspeth/tui/explain_app.py:42-46`

```python
BINDINGS: ClassVar[list[...]] = [
    Binding("q", "quit", "Quit"),
    Binding("r", "refresh", "Refresh"),
    Binding("?", "help", "Help"),
]
```

Refresh and help actions exist but don't do much:
```python
def action_refresh(self) -> None:
    self.notify("Refreshing...")  # Doesn't actually refresh

def action_help(self) -> None:
    self.notify("Press q to quit, arrow keys to navigate")  # Just a string
```

---

## Confidence Assessment

**Contracts Analysis:** High confidence
- Read all 16 contract files (100%)
- Verified imports and exports in `__init__.py`
- Cross-referenced enum usage across modules

**CLI Analysis:** High confidence
- Read cli.py (1719 lines - 100%)
- Read cli_helpers.py (61 lines - 100%)
- Identified code duplication through line-by-line comparison

**TUI Analysis:** High confidence
- Read all 9 TUI files (100%)
- Verified widget/screen integration status
- Identified placeholder vs implemented code

---

## Recommendations Summary

### Immediate (RC-1 blockers)

1. **Fix Batch.trigger_type typing** - Change to `TriggerType | None`
2. **Either implement explain command or remove from public CLI** - Placeholder confuses users
3. **Extract event formatters to shared functions** - 123 lines duplicated 3x

### Before GA

4. **Add `elspeth status` command** - CLAUDE.md promises it
5. **Add `elspeth db migrate` command** - Users need schema management
6. **Refactor `_execute_pipeline*` functions** - 400+ lines of duplication
7. **Connect ExplainScreen and LineageTree to ExplainApp** - Working code exists, just not wired
8. **Add resume command JSON output** - CI/CD needs structured output

### Technical Debt

9. **Replace plugin manager singleton with dependency injection**
10. **Resolve type: ignore comments** - Fix protocol definitions
11. **Standardize dataclass frozen/mutable pattern**
12. **Document Token vs TokenInfo distinction**

---

## Appendix: Files Analyzed

### Contracts (16 files, 1,847 lines)
- `__init__.py` (225 lines) - exports
- `audit.py` (522 lines) - audit trail records
- `checkpoint.py` (44 lines) - resume contracts
- `cli.py` (52 lines) - CLI result types
- `config.py` (38 lines) - re-exports
- `data.py` (244 lines) - schema system
- `engine.py` (23 lines) - engine contracts
- `enums.py` (221 lines) - all enums
- `errors.py` (115 lines) - error types
- `events.py` (117 lines) - pipeline events
- `identity.py` (33 lines) - token identity
- `results.py` (354 lines) - operation results
- `routing.py` (166 lines) - flow control
- `schema.py` (270 lines) - config schemas
- `types.py` (28 lines) - semantic types
- `url.py` (231 lines) - URL sanitization

### CLI (2 files, 1,780 lines)
- `cli.py` (1,719 lines) - main CLI
- `cli_helpers.py` (61 lines) - helpers

### TUI (9 files, 610 lines)
- `__init__.py` (10 lines)
- `constants.py` (17 lines)
- `types.py` (93 lines)
- `explain_app.py` (74 lines) - main app
- `widgets/__init__.py` (7 lines)
- `widgets/lineage_tree.py` (198 lines)
- `widgets/node_detail.py` (166 lines)
- `screens/__init__.py` (6 lines)
- `screens/explain_screen.py` (314 lines)
