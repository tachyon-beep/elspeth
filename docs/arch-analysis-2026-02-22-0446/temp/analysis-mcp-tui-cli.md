# Architecture Analysis: MCP Server, TUI, and CLI
## Date: 2026-02-22 | Branch: RC3.3-architectural-remediation

---

## File Inventory and Line Counts

| File | Lines |
|------|-------|
| `src/elspeth/mcp/server.py` | 864 |
| `src/elspeth/mcp/analyzer.py` | 172 |
| `src/elspeth/mcp/types.py` | 649 |
| `src/elspeth/mcp/analyzers/contracts.py` | 199 |
| `src/elspeth/mcp/analyzers/diagnostics.py` | 449 |
| `src/elspeth/mcp/analyzers/queries.py` | 774 |
| `src/elspeth/mcp/analyzers/reports.py` | 710 |
| **MCP subtotal** | **3,817** |
| `src/elspeth/tui/explain_app.py` | 123 |
| `src/elspeth/tui/constants.py` | 16 |
| `src/elspeth/tui/types.py` | 144 |
| `src/elspeth/tui/screens/explain_screen.py` | 404 |
| `src/elspeth/tui/widgets/lineage_tree.py` | 213 |
| `src/elspeth/tui/widgets/node_detail.py` | 234 |
| **TUI subtotal** | **1,134** |
| `src/elspeth/cli.py` | 2,094 |
| `src/elspeth/cli_helpers.py` | 212 |
| `src/elspeth/cli_formatters.py` | 184 |
| **CLI subtotal** | **2,490** |
| **Total analyzed** | **7,441** |

Note: MEMORY.md reported `server.py` at ~2355 lines and `cli.py` at ~2094 lines. The actual `server.py` is 864 lines — significantly smaller than remembered. The 2355-line number was likely from a pre-refactor version where all analyzer logic lived in server.py before it was split into the `analyzers/` submodules. The refactoring succeeded.

---

## MCP Subsystem (3,817 lines total)

### server.py (864 lines)

**Purpose:** MCP protocol machinery for the Landscape audit analysis server. Exposes read-only tools to LLM clients (Claude, etc.) that allow querying the audit database. This is the MCP entry point; it owns argument validation, tool registration, the dispatcher, and the CLI entry point.

**Key classes/functions:**
- `_ArgSpec` (frozen dataclass): Declarative schema for one MCP tool's arguments — required_str, optional_str, optional_str_defaults, optional_int, optional_dict.
- `_TOOL_ARGS` (dict): Static registry mapping 23 tool names to their `_ArgSpec`. The complete tool surface lives here.
- `_validate_tool_args()`: Validates and normalizes MCP arguments at the Tier 3 trust boundary. Returns a clean dict with only declared fields.
- `create_server()`: Factory that wires `LandscapeAnalyzer` to the MCP `Server`, registers `list_tools()` and `call_tool()` handlers.
- `call_tool()`: Long if/elif dispatch chain mapping 23 tool names to `analyzer.*` method calls. No blanket try/except — database errors propagate as MCP protocol errors.
- `_find_audit_databases()`: Auto-discovery of `.db` files with priority ranking (audit.db in runs/ > other audit.db > landscape.db).
- `_prompt_for_database()`: Interactive selection when multiple databases found.
- `main()`: `argparse`-based CLI entry point (separate from the Typer-based `elspeth` CLI).

**Dependencies:**
- `mcp.server` (MCP SDK — external)
- `elspeth.contracts.enums.RunStatus`
- `elspeth.mcp.analyzer.LandscapeAnalyzer`

**Size concerns:** At 864 lines, server.py is appropriately sized now. The `list_tools()` handler is verbose (about 300 lines of tool definition JSON), but this is structural repetition, not logic duplication. The if/elif dispatch at ~100 lines is a smell — see concerns.

**Concerns:**
1. **Dual arg validation approach**: The `list_tools()` tool schemas (JSON Schema in `inputSchema`) and `_TOOL_ARGS` `_ArgSpec` are two separate representations of the same information. They can diverge. If a tool adds a new optional parameter to `_ArgSpec` but not to `inputSchema`, the client schema is stale. There is no code-level enforcement that these stay in sync.
2. **if/elif dispatch (100 lines)**: The `call_tool()` dispatcher is a manual if/elif chain over 23 tools. This must be updated every time a new tool is added — three places: `_TOOL_ARGS`, `list_tools()`, and `call_tool()`. A dispatch table (`dict[str, Callable]`) would reduce this to one place.
3. **argparse not Typer**: The `main()` function uses argparse while the rest of the CLI uses Typer. This is intentional (the MCP server is a separate entry point in `pyproject.toml`), but it means two different CLI libraries in the project and two different UX patterns.
4. **`_find_audit_databases()` uses `rglob`**: Searching from CWD with depth-5 recursion is fine for local use but could be slow in large monorepo or network-mounted directories.
5. **`input()` in `_prompt_for_database()`**: Interactive stdin reading will block in MCP server mode if the TTY check fails. The `is_interactive = sys.stdin.isatty()` guard handles this correctly, but the fallback auto-selects silently — potentially surprising.

---

### analyzer.py (172 lines)

**Purpose:** Pure facade/delegator. `LandscapeAnalyzer` holds the `LandscapeDB` and `LandscapeRecorder` instances and delegates every public method to one of the four submodules (`queries`, `reports`, `diagnostics`, `contracts`). Contains `__init__` and `close()` plus 20 thin delegation methods.

**Key classes/functions:**
- `LandscapeAnalyzer.__init__()`: Creates `LandscapeDB.from_url()` and `LandscapeRecorder`.
- `close()`: Closes the database connection.
- 20 delegation methods, each calling the corresponding submodule function with `(self._db, self._recorder, ...)`.

**Dependencies:**
- `elspeth.core.landscape.database.LandscapeDB`
- `elspeth.core.landscape.recorder.LandscapeRecorder`
- `elspeth.mcp.analyzers.*` (contracts, diagnostics, queries, reports)
- `elspeth.mcp.types.*` (all return type annotations)

**Size concerns:** 172 lines — well-sized for a facade.

**Concerns:**
1. **`_db` and `_recorder` passed to every submodule call**: Every delegation passes both `db` and `recorder`. This is a consequence of using module-level functions rather than a class per domain. This pattern means every function signature has a mandatory `(db, recorder, ...)` prefix — callers always pass both even when only one is used. A per-domain class would hide this plumbing.
2. **`LandscapeRecorder` created but mostly bypassed**: The submodules use `recorder.*` for some calls (e.g., `recorder.get_run()`, `recorder.get_nodes()`) but bypass it entirely for complex queries (directly importing schema tables and writing SQLAlchemy queries). There is no consistent access pattern. `recorder` is effectively a partial ORM wrapper.
3. **`explain_token` special-cases `None` to `ErrorResult`**: The `None` → `{"error": "..."}` translation happens in `analyzer.py` itself, not in `queries.py`. This is an inconsistency — other methods let the submodule return `ErrorResult` directly.

---

### types.py (649 lines)

**Purpose:** TypedDict definitions for all MCP return types. Provides static structure for the dicts returned by `LandscapeAnalyzer` methods. At runtime these are plain dicts; mypy uses them for structural verification.

**Key types (grouped):**
- **Group A (Simple Records)**: `RunRecord`, `RowRecord`, `TokenRecord`, `OperationRecord`, `OperationCallRecord`, `NodeStateRecord` — flat projections of database rows.
- **Group B (Dataclass Mirrors)**: `RunDetail`, `NodeDetail`, `CallDetail` — type aliases for `dict[str, Any]` because `dataclass_to_dict()` produces fully dynamic structures. These are nominal, not structural.
- **Group C (Complex Reports)**: `RunSummaryReport`, `DAGStructureReport`, `PerformanceReport`, `ErrorAnalysisReport`, `LLMUsageReport`, `OutcomeAnalysisReport`, `SchemaDescription`, `ErrorsReport`, `DiagnosticReport`, `FailureContextReport`, `RecentActivityReport`, `RunContractReport`, `FieldExplanation`, `ContractViolationsReport`, `ExplainTokenResult`.
- **Group D (Utility)**: `ErrorResult`, `FieldNotFoundError`.

**Dependencies:** Only `typing` (standard library).

**Size concerns:** 649 lines — large for a types file, but the size is justified by the large number of distinct return types (22 TypedDicts + aliases). Each type is fully documented.

**Concerns:**
1. **`dict[str, Any]` type aliases for Group B are not structural**: `RunDetail = dict[str, Any]` provides no mypy benefit — any dict satisfies it. The comment explains why (dataclass_to_dict produces dynamic output), but this is a gap in the type safety story for the most complex return types.
2. **`# type: ignore[typeddict-item]` suppression in callers**: Multiple return sites in the analyzer submodules suppress typeddict-item errors because `dataclass_to_dict()` returns `dict[str, Any]` rather than the specific TypedDict. The types file doesn't fix this — it accepts the limitation via Group B aliases.
3. **`total=False` on `LLMUsageReport` and `ErrorsReport`**: These use `total=False` with `Required[]` for conditionally-present keys. This is the correct pattern but creates asymmetric access — callers can't use direct field access on the optional fields without checking first. The inconsistency between "some fields always present, some conditional" is semantically correct but increases caller complexity.
4. **`ExplainTokenResult` uses `list[dict[str, Any]]` for nested items**: The deeply nested structures (routing_events, node_states) fall back to untyped lists. This is documented and explained, but it is a gap.
5. **`DAGEdge` uses functional TypedDict form**: Necessary because `"from"` is a Python keyword. Minor but noteworthy — this edge case is correctly handled.

---

### analyzers/queries.py (774 lines)

**Purpose:** Core CRUD query functions — `list_runs`, `get_run`, `list_rows`, `list_nodes`, `list_tokens`, `list_operations`, `get_operation_calls`, `explain_token`, `get_errors`, `get_node_states`, `get_calls`, `query`. Also contains the SQL read-only validation logic (`_validate_readonly_sql`, `_strip_sql_comments`, `_strip_sql_string_literals`).

**Key functions:**
- `list_runs()`: Validates `status` against `RunStatus` enum before filtering.
- `explain_token()`: Delegates to `core.landscape.lineage.explain()`, then annotates routing events with `flow_type` and builds `divert_summary`.
- `get_errors()`: Conditionally includes validation/transform errors based on `error_type` param.
- `get_node_states()`: Validates `status` against `NodeStateStatus` enum.
- `_validate_readonly_sql()`: Multi-step validation: strips comments → rejects multi-statement → requires SELECT/WITH prefix → scans for forbidden keywords via word-boundary regex.
- `_strip_sql_comments()` / `_strip_sql_string_literals()`: Hand-rolled parsers handling SQL comment and string literal boundaries.
- `query()`: Calls `_validate_readonly_sql()` then executes via `text()`.

**Dependencies:**
- `elspeth.core.landscape.database.LandscapeDB`
- `elspeth.core.landscape.recorder.LandscapeRecorder`
- `elspeth.core.landscape.formatters` (dataclass_to_dict, serialize_datetime)
- `elspeth.core.landscape.lineage` (explain)
- `elspeth.core.landscape.schema` (various table objects, imported locally)
- `elspeth.contracts` (RunStatus, NodeStateStatus)
- `elspeth.mcp.types` (various return types)

**Size concerns:** 774 lines. About 250 lines (one-third) are the SQL safety utilities (`_validate_readonly_sql` and its helpers). This is a coherent block of security logic but could be extracted to `mcp/sql_safety.py` if it ever needs to be shared or tested in isolation.

**Concerns:**
1. **Hand-rolled SQL parser for comment/string stripping**: `_strip_sql_comments` and `_strip_sql_string_literals` are custom state-machine parsers. They handle the most common cases correctly (single/double quotes, `--` and `/* */` comments, `''` escape). However they do not handle: backtick-quoted identifiers (MySQL/SQLite), dollar-quoted strings (PostgreSQL `$$...$$`), or Unicode quote variants. For the stated use case (LLM-generated queries against SQLite), this is acceptable, but the limitation should be documented.
2. **Keyword blocklist is deny-list, not allow-list**: The approach of checking for forbidden keywords is less robust than requiring the query to be a parse tree that starts with SELECT. An LLM could potentially find novel bypass vectors not in the blocklist. The `SELECT`/`WITH` prefix check provides the primary defense; the keyword scan is defense-in-depth.
3. **`SET` is in the blocklist**: `SET` appears in many SELECT contexts (e.g., SQLite `SELECT ... EXCEPT SELECT` set operations don't use `SET`, but PostgreSQL `SET` is a config command). This may produce false positives for legitimate queries. The word-boundary match mitigates but does not eliminate this.
4. **Local imports pattern**: SQLAlchemy imports (`from sqlalchemy import ...`) and schema imports (`from elspeth.core.landscape.schema import ...`) are inside function bodies throughout. This delays import errors to runtime and reduces IDE navigation. It avoids circular imports, which is likely the reason, but it should be noted.
5. **`explain_token` does post-processing in queries.py**: The `flow_type` annotation and `divert_summary` construction happen in `queries.py` after calling the `lineage.explain()` function. This is business logic in a CRUD layer.

---

### analyzers/reports.py (710 lines)

**Purpose:** Computed analysis functions — `get_run_summary`, `get_dag_structure`, `get_performance_report`, `get_error_analysis`, `get_llm_usage_report`, `describe_schema`, `get_outcome_analysis`.

**Key functions:**
- `get_run_summary()`: 9 separate count queries (rows, tokens, nodes, states, operations, source_loads, sink_writes, validation errors, transform errors) plus outcome distribution and avg duration. Notably these are N individual queries, not a single aggregated query.
- `get_dag_structure()`: Uses `recorder.get_nodes()` and `recorder.get_edges()`, builds Mermaid diagram string. Uses sequential N0/N1/... aliases after the fix for node_id prefix collisions.
- `get_performance_report()`: Joins `node_states` to `nodes` using composite key, computes per-node timing statistics, identifies bottlenecks (>20% total time) and high-variance nodes (max > 5x avg).
- `get_llm_usage_report()`: Queries both `state_id` and `operation_id` call paths via `union_all` to cover LLM calls from both transform and source/sink contexts.
- `get_outcome_analysis()`: Counts terminal/non-terminal tokens, fork/join operations, and sink distribution.
- `describe_schema()`: Uses SQLAlchemy inspector — defers to the engine rather than hardcoding schema knowledge.

**Dependencies:**
- `elspeth.contracts.enums` (CallStatus, NodeType, RoutingMode)
- `elspeth.core.landscape.database.LandscapeDB`
- `elspeth.core.landscape.recorder.LandscapeRecorder`
- `elspeth.core.landscape.schema` (various table objects, imported locally)
- `elspeth.mcp.types` (return types)

**Size concerns:** 710 lines. This is appropriately sized for 7 non-trivial analytical functions.

**Concerns:**
1. **`get_run_summary()` issues 9 separate queries**: Row count, token count, node count, state count, operation count, source_load count, sink_write count, validation error count, transform error count — all separate queries. Plus outcome distribution and avg duration. This is 11 round trips to SQLite for a single "summary" call. For SQLite on disk, this is acceptable but non-optimal. A single CTE-based query would reduce this significantly.
2. **`get_performance_report()` has a potential N+1 path**: The `failed_query` is a separate aggregation over `node_states` filtered by `status == "failed"`. This is fine — it's a batched query. But the `pct_of_total` calculation in Python loops over `stats_rows`, which was already fetched in the prior query. No N+1 issue, but worth noting the two-query pattern.
3. **`high_variance` filter uses truthiness**: `if n["avg_ms"] and n["max_ms"] and n["max_ms"] > 5 * n["avg_ms"]` — using truthiness on numeric values will incorrectly exclude nodes with `avg_ms = 0` (zero-duration) even if they have non-zero max. Should be `is not None`.
4. **`get_llm_usage_report()` empty-case return is non-uniform**: When no LLM calls exist, it returns `{"run_id": ..., "message": ..., "call_types": {}}`. When LLM calls exist, it returns `{"run_id": ..., "call_types": ..., "llm_summary": ..., "by_plugin": ...}`. The `LLMUsageReport` TypedDict's `total=False` accommodates this, but callers must handle both shapes.
5. **The `type: ignore` comments on TypedDict returns**: Multiple `# type: ignore[typeddict-item]` suppressions in return statements because the dict literals are "structurally correct" but mypy cannot verify nested TypedDicts built from SA Row attributes. This is a known limitation, but the volume of suppression is notable.

---

### analyzers/diagnostics.py (449 lines)

**Purpose:** Emergency diagnostic and activity functions — `diagnose`, `get_failure_context`, `get_recent_activity`.

**Key functions:**
- `diagnose()`: Scans for failed runs (last 5), stuck runs (running > 1 hour), stuck operations (open > 1 hour), high-error-rate completed runs (>10 validation errors), and quarantined rows. Returns structured problem list with severity, recommendations, and next_steps.
- `get_failure_context()`: For a given run, fetches failed node states (with composite-key join to nodes), transform errors, and validation errors. Builds `patterns` dict identifying which plugins are failing and whether retries occurred.
- `get_recent_activity()`: Batch queries row and state counts for all runs in the time window (N+1 fix noted in code). Returns timeline with per-run stats.

**Dependencies:**
- `elspeth.core.landscape.database.LandscapeDB`
- `elspeth.core.landscape.recorder.LandscapeRecorder`
- `elspeth.core.landscape.schema` (various table objects, locally imported)
- `elspeth.mcp.types` (return types)

**Size concerns:** 449 lines — appropriately sized for 3 complex functions.

**Concerns:**
1. **`get_failure_context()` raises `RuntimeError` for Tier 1 corruption**: The code checks `if e.node_id is not None and e.plugin_name is None` (orphaned FK in validation_errors) and raises `RuntimeError`. This is correct Tier 1 handling per CLAUDE.md. However, this error will propagate through `call_tool()` as an MCP protocol error rather than a user-visible error message, which is the correct behavior — but operators should be aware that this is a "crash the MCP call" scenario.
2. **`diagnose()` hardcodes 1-hour threshold**: The stuck run/operation threshold is hardcoded as `timedelta(hours=1)`. There is no configuration for this. For pipelines with known long-running jobs (batch ML, etc.), this will always show false-positive stuck_runs warnings.
3. **`diagnose()` counts quarantined rows across ALL runs**: The quarantined_count query has no time window — it sums all quarantined outcomes in the entire database history. A database with years of runs will always show a non-zero quarantine count, making this permanently "INFO" level even if recent runs are clean. It should be scoped to recent runs.
4. **`get_recent_activity()` time window default is 60 minutes**: Fine for interactive use. For automated monitoring via MCP (e.g., scheduled checks), the default may be too narrow.

---

### analyzers/contracts.py (199 lines)

**Purpose:** Schema contract query functions — `get_run_contract`, `explain_field`, `list_contract_violations`.

**Key functions:**
- `get_run_contract()`: Retrieves the stored `SourceSchemaContract` for a run, serializes fields to `ContractField` dicts (converting `python_type.__name__`).
- `explain_field()`: Looks up a field by normalized or original name using `contract.find_name()`, returns provenance.
- `list_contract_violations()`: Direct SQLAlchemy query on `validation_errors_table` filtered by `violation_type IS NOT NULL`.

**Dependencies:**
- `elspeth.core.landscape.database.LandscapeDB`
- `elspeth.core.landscape.recorder.LandscapeRecorder`
- `elspeth.core.landscape.schema` (validation_errors_table, locally imported)
- `elspeth.mcp.types` (return types)

**Size concerns:** 199 lines — well-sized.

**Concerns:**
1. **`python_type.__name__` serialization**: Converting `python_type` (a `type` object) to `.__name__` is simple but fragile. If `python_type` is something like `list[str]` or a generic alias, `.__name__` will fail with `AttributeError`. The caller of `contract.fields` controls what goes in `python_type`, so this may be fine in practice, but it is an implicit contract.
2. **`list_contract_violations()` has local import of `validation_errors_table`**: Consistent with the pattern in other submodules, but see the general concern about local imports.

---

## MCP Architecture Summary

The MCP subsystem has a clean four-layer architecture:

```
client (LLM)
    ↓ JSON via stdio
server.py (MCP protocol layer)
    - Tier 3 boundary: _validate_tool_args()
    - Tool registration: list_tools()
    - Dispatch: call_tool() if/elif chain
    ↓
analyzer.py (facade)
    - LandscapeDB + LandscapeRecorder lifecycle
    - 20 thin delegation methods
    ↓
analyzers/{queries, reports, diagnostics, contracts}.py
    - Domain-specific SQL and analysis logic
    ↓
core/landscape/{database, recorder, schema, lineage}.py
    - Actual database access
```

This is a well-structured decomposition. The original `server.py` at 2355 lines (per MEMORY.md) was a monolith; the current 864-line version is primarily protocol machinery, with business logic properly separated.

**Tool count:** 23 tools registered. The tool surface is comprehensive and well-documented. The MCP tool descriptions are clear and actionable for an LLM caller.

---

## TUI Subsystem (1,134 lines total)

### explain_app.py (123 lines)

**Purpose:** Textual `App` subclass wrapping `ExplainScreen`. Provides keybindings (q/r/?), layout CSS (2-column grid, lineage tree left, detail panel right), and lifecycle management. Renders screen state as `Static` widgets for the initial view.

**Key classes:**
- `ExplainApp(App[None])`: Thin wrapper. `compose()` dispatches on `ExplainScreen.state` using `match`/`case` pattern matching (exhaustive over the discriminated union). Renders tree nodes and detail panel as `Static` widgets.
- `action_refresh()`: Clears and reloads `ExplainScreen`, then calls `self.notify()`.
- `action_help()`: Shows a notification string.

**Dependencies:**
- `textual.app`, `textual.binding`, `textual.widgets`
- `elspeth.core.landscape.LandscapeDB`
- `elspeth.tui.constants.WidgetIDs`
- `elspeth.tui.screens.explain_screen` (ExplainScreen, state types)

**Concerns:**
1. **`compose()` renders `Static` widgets from `ExplainScreen` data**: The TUI renders `Static` text widgets rather than interactive Textual widgets. This means the lineage tree and detail panel are non-interactive in the current implementation — they cannot be scrolled, expanded/collapsed, or clicked within the Textual framework. The `ExplainScreen` has `LineageTree` and `NodeDetailPanel` objects that produce text output, but they are not Textual `Widget` subclasses and therefore cannot be mounted.
2. **`action_refresh()` notifies but does NOT update widgets**: After clearing and reloading `ExplainScreen`, the existing `Static` widgets in the Textual DOM still hold the old rendered text. Calling `self.notify("Refreshed")` does not re-render. The refresh action is effectively a no-op for the display. This is a known limitation (noted in the code comment) but it means the TUI's refresh feature is broken.
3. **`action_help()` shows a hardcoded string**: "Press q to quit, r to refresh, arrow keys to navigate" — but the TUI does not support arrow key navigation (no `on_key` handler). The help message is misleading.

---

### constants.py (16 lines)

**Purpose:** Widget ID constants (`WidgetIDs.LINEAGE_TREE`, `WidgetIDs.DETAIL_PANEL`). Prevents magic string drift between CSS selectors and `compose()`.

**Concerns:** None. This is correct, minimal, and well-justified.

---

### types.py (144 lines)

**Purpose:** TypedDict definitions for TUI data contracts. Defines `NodeInfo`, `SourceInfo`, `TokenDisplayInfo`, `LineageData`, `NodeStateInfo`, `ExecutionErrorDisplay`, `TransformErrorDisplay`, `ArtifactDisplay`.

**Key types:**
- `LineageData`: The primary data contract passed to `LineageTree`. All fields required.
- `NodeStateInfo`: Uses `total=False` with `Required` for node_id/plugin_name/node_type; optional fields for execution state (state_id, token_id, status, timing, hashes, errors, artifacts).
- `ExecutionErrorDisplay`, `TransformErrorDisplay`, `ArtifactDisplay`: Parsed/validated representations of audit record sub-structures.

**Concerns:**
1. **`NodeStateInfo.total=False` with explicit Required**: The comment accurately describes the semantics. The pattern is correct but verbose. Three required fields plus 11 optional fields in one TypedDict is doing a lot of work. A cleaner model might split `NodeRegistrationInfo` (always present) from `NodeExecutionState` (optional, when a token has visited).
2. **`ArtifactDisplay.total=False` but all fields are `Required`**: All four fields are marked `Required[...]` within `total=False`. This effectively makes the TypedDict fully required. Using `total=True` (the default) would be cleaner and semantically equivalent.

---

### screens/explain_screen.py (404 lines)

**Purpose:** Business logic layer for the explain TUI screen. Manages a discriminated union state machine (`UninitializedState | LoadingFailedState | LoadedState`), loads pipeline structure from `LandscapeDB`, and coordinates `LineageTree` and `NodeDetailPanel`.

**Key classes:**
- `InvalidStateTransitionError`: Custom exception for invalid state transitions.
- `ScreenStateType` (Enum): Discriminator values.
- `UninitializedState`, `LoadingFailedState`, `LoadedState`: Frozen dataclasses forming the discriminated union. `LoadingFailedState` preserves `db` and `run_id` for retry. `LoadedState` holds the loaded `LineageData` and `LineageTree`.
- `ExplainScreen`: Not a Textual `Screen` subclass — it is a plain Python class that manages state and coordinates widgets. This is an important architectural point.

**Key methods:**
- `_load_pipeline_structure()`: Queries nodes via `recorder.get_nodes()`, categorizes by `NodeType`, builds `LineageData`, creates `LineageTree`. Catches `DatabaseError | OperationalError` (recoverable) but lets other exceptions propagate (bugs in our code).
- `load()`, `retry()`, `clear()`: State transition methods with `InvalidStateTransitionError` guards.
- `_load_node_state()`: Queries a single node by composite PK.
- `render()`: Returns text string representation of the screen. Used for `--no-tui` output path.

**Dependencies:**
- `sqlalchemy.exc` (DatabaseError, OperationalError)
- `elspeth.contracts.NodeType`
- `elspeth.core.landscape.LandscapeDB`
- `elspeth.core.landscape.recorder.LandscapeRecorder`
- `elspeth.tui.types` (LineageData, NodeStateInfo)
- `elspeth.tui.widgets.lineage_tree.LineageTree`
- `elspeth.tui.widgets.node_detail.NodeDetailPanel`

**Concerns:**
1. **`ExplainScreen` is not a Textual `Screen`**: Despite the name, `ExplainScreen` is a plain Python class, not `textual.app.Screen`. It cannot be mounted in a Textual app using `app.push_screen()`. The `ExplainApp` accesses it as a data manager, not as a Textual widget. This naming is misleading and creates an architectural gap.
2. **Token loading is deferred but never completed**: `lineage_data["tokens"]` is always `[]` (empty list). The comment says "Tokens loaded separately when needed." But there is no code path that populates tokens. The `ExplainApp.compose()` matches `LoadedState(tree=tree)` and renders the tree, but the tree will never show token nodes because they are always empty.
3. **`_load_node_state()` only returns required fields**: When a node is selected, only `node_id`, `plugin_name`, and `node_type` are returned. The comment acknowledges this: "Full node state requires a token_id to look up execution state." But there is no UI mechanism for the user to select a specific token in the TUI. The detail panel will always show "N/A" for all execution state fields.
4. **`get_detail_panel_state()` accesses `self._detail_panel._state`**: This reaches into a private attribute of `NodeDetailPanel`. Should use `detail_panel.state` (which doesn't exist as a property — `NodeDetailPanel` only has `update_state()` and `render_content()`).
5. **`_PROCESSING_TYPES` is defined as a set literal inside `_load_pipeline_structure()`**: This constant is re-created on every call. Minor inefficiency.

---

### widgets/lineage_tree.py (213 lines)

**Purpose:** Data model for the lineage tree. `LineageTree` builds a `TreeNode` hierarchy from `LineageData` and provides `get_tree_nodes()` (flat traversal for rendering), `get_node_by_id()`, `toggle_node()`. Not a Textual widget.

**Key classes:**
- `TreeNode` (dataclass): label, node_id, node_type, children list, expanded bool.
- `LineageTree`: Builds tree in `_build_tree()`. Source → transforms (linear chain) → sinks → tokens (under terminal sink nodes).

**Concerns:**
1. **DAG pipelines rendered as linear chain**: The code comment correctly identifies this as a known limitation: "DAG pipelines with fork/coalesce are rendered as a linear chain — parallel branches and merge points are not shown." For multi-sink or fork/join pipelines, the tree will be misleading. This is acceptable as a known limitation but should be surfaced in the `--help` docs.
2. **`_TYPE_LABELS` dict accessed without `.get()`**: `type_label = _TYPE_LABELS[raw_type]` will raise `KeyError` if a new `NodeType` is added that is not in the map. Since `transform_nodes` is filtered by `_PROCESSING_TYPES` (a set of specific NodeType members), and `_TYPE_LABELS` covers the same members, these two sets should be kept in sync. There is no enforcement.
3. **Token-sink routing uses `path[-1]`**: Tokens are placed under their terminal sink based on `token["path"][-1]`. But `path` is always `[]` (empty) because token loading is never completed. No tokens will ever appear in the tree.

---

### widgets/node_detail.py (234 lines)

**Purpose:** `NodeDetailPanel` renders `NodeStateInfo` as formatted text. Handles the three error variant types (ExecutionError, TransformErrorReason, unknown). Validates audit data at Tier 1 boundary (crashes on type errors and format violations).

**Key functions:**
- `_validate_execution_error()`: Checks `"type"` and `"exception"` required keys; adds optional `"traceback"` and `"phase"` if present.
- `_validate_transform_error()`: Checks `"reason"` required key; adds optional `"error"`, `"message"`, `"error_type"`, `"field"`.
- `_validate_artifact()`: Checks all four required keys.
- `NodeDetailPanel.render_content()`: Renders header, identity, status, hashes, error (if present), artifact (if present).

**Concerns:**
1. **`render_content()` uses `.get()` on required fields via `self._state.get("state_id")`**: `NodeStateInfo` uses `total=False` with `Required` markers. Mypy can see that `state_id` is optional (not Required), so `.get()` is correct there. But `plugin_name` and `node_id` (Required) are accessed with `self._state["plugin_name"]` — correct. The mixed access pattern (direct bracket for Required, `.get()` for optional) is correct and consistent with CLAUDE.md.
2. **`or "N/A"` truthiness checks on optional fields**: `status or "N/A"` will incorrectly show "N/A" if `status` is an empty string `""`. For display purposes this is acceptable, but it violates the "truthiness vs `is not None`" concern from MEMORY.md.
3. **`_format_size()` has unnecessary elif chain**: The `if/elif/elif/else` for byte formatting could use a list of thresholds. Minor style issue.
4. **Error discriminated union is fragile**: The decision between `ExecutionError` and `TransformErrorReason` variants is made by checking key presence (`if "type" in error and "exception" in error`). If a future error format has both `"type"` and `"exception"` keys for a different reason, it will be misclassified. A `"__variant__"` discriminator key would be more robust.

---

## TUI Architecture Summary

The TUI subsystem has a fundamental architectural problem: **it appears to implement a complete interactive TUI but the interactivity is non-functional.**

The data model layer (`ExplainScreen`, `LineageTree`, `NodeDetailPanel`) is well-designed:
- Clean discriminated union state machine
- Correct Tier 1 trust model for audit data
- Good separation of data loading and rendering

However, the UI layer (`ExplainApp`) renders the data model as static `Static` text widgets rather than interactive Textual widgets, because the domain model classes (`LineageTree`, `NodeDetailPanel`, `ExplainScreen`) are plain Python classes, not Textual `Widget` subclasses.

The practical result:
- Tokens never appear in the tree (loading deferred, never completed)
- Execution state never appears in detail panel (requires token selection)
- Refresh does not update displayed content
- Arrow key navigation mentioned in help does not work
- The TUI looks like a static text dump wrapped in a Textual frame

**The `--no-tui` text output path through `explain_screen.render()` is the only fully functional output path.** The TUI mode is essentially a non-interactive wrapper around the same text output.

This is a significant gap between the TUI's apparent capability (interactive lineage exploration) and its actual capability (static text display in a Textual frame). The MCP `explain_token` tool provides richer lineage data with less UI investment.

---

## CLI Subsystem (2,490 lines total)

### cli.py (2,094 lines)

**Purpose:** Main Typer CLI application with commands: `run`, `explain`, `validate`, `resume`, `purge`, `health`, and the `plugins list` subcommand. Also contains shared infrastructure: `_orchestrator_context()` (context manager for run/resume), `_execute_pipeline_with_instances()`, `_execute_resume_with_instances()`, `_build_resume_graphs()`, `_load_settings_with_secrets()`, `_ensure_output_directories()`, `_validate_existing_sqlite_db_url()`, `_load_raw_yaml()`, `_format_validation_error()`.

**Commands:**
| Command | Lines (approx) | Purpose |
|---------|----------------|---------|
| `run` | ~200 | Execute pipeline, requires `--execute` flag |
| `explain` | ~200 | Lineage explorer (TUI/text/JSON modes) |
| `validate` | ~150 | Validate config without running |
| `resume` | ~450 | Resume interrupted run from checkpoint |
| `purge` | ~200 | Purge old payload blobs |
| `health` | ~190 | System health check for deployment |
| `plugins list` | ~50 | List available plugins |
| Infrastructure | ~650 | Shared helpers, context managers, etc. |

**Key infrastructure:**
- `_load_settings_with_secrets()`: Three-phase loading (raw YAML → Key Vault secrets → Dynaconf resolution). Used by `run`, `validate`, `resume`.
- `_orchestrator_context()`: Context manager that builds `PipelineConfig`, `EventBus`, formatters, runtime configs, `RateLimitRegistry`, `CheckpointManager`, `TelemetryManager`, and `Orchestrator`. Shared between `run` and `resume`. This is a 90-line function that manages 8+ objects.
- `_execute_pipeline_with_instances()`: Orchestrates `LandscapeDB` creation, `FilesystemPayloadStore`, and calls `_orchestrator_context()` + `orchestrator.run()`.
- `_build_resume_graphs()`: Builds both validation and execution graphs for resume (original source for topology hash, NullSource for execution).

**Dependencies:** Extensive. The CLI is the integration layer:
- `typer`, `yaml`, `pydantic`
- `elspeth.contracts.*`
- `elspeth.core.config.*`
- `elspeth.core.dag.*`
- `elspeth.core.landscape.*`
- `elspeth.core.checkpoint.*`
- `elspeth.core.payload_store.*`
- `elspeth.core.rate_limit.*`
- `elspeth.engine.*`
- `elspeth.plugins.*`
- `elspeth.telemetry.*`
- `elspeth.tui.*`
- `elspeth.testing.chaosllm.cli` (sub-app registration)
- `elspeth.cli_helpers.*`
- `elspeth.cli_formatters.*`
- `sqlalchemy`
- `rich` (for `_format_validation_error`)

**Size concerns:** 2,094 lines. This is large. The single-file CLI monolith merges several distinct responsibilities. However, for a CLI, moderate monolithism is acceptable — the commands are largely sequential scripts with shared infrastructure. The real concerns are specific patterns (see below).

**Concerns:**

1. **Error handling duplication across commands**: The pattern of catching `FileNotFoundError`, `YamlParserError`, `YamlScannerError`, `yaml.YAMLError`, `ValidationError`, `ValueError`, `SecretLoadError` and emitting an error message + `raise typer.Exit(1)` appears in `run`, `validate`, `resume`, and `purge` — all calling `_load_settings_with_secrets()`. The `validate` command uses `_format_validation_error()` (rich-formatted) while `run` and `resume` use plain `typer.echo()`. This is inconsistent UX and ~200 lines of repeated error-handling boilerplate.

2. **`_orchestrator_context()` is a 90-line setup function**: It creates 8+ objects (EventBus, formatters, 4 runtime configs, RateLimitRegistry, CheckpointManager, TelemetryManager, Orchestrator) and tears down 2 (rate_limit_registry, telemetry_manager). The `db` lifecycle is owned by the caller (not this context manager), creating a split responsibility. The caller owns `db.close()`, the context manager owns `rate_limit_registry.close()` and `telemetry_manager.close()`. This split is documented but fragile.

3. **`resume` command is 450 lines**: The largest command. It handles 5 distinct cases: settings not found, settings load failure, database not found, dry run display, and actual execution. The execution path alone covers: plugin instantiation, graph building, sink validation (resume mode, append mode, field resolution, output target validation), NullSource wiring, and the resume execution itself. This would benefit from extraction.

4. **`health` command calls `subprocess.run(["git", "rev-parse", ...])` silently**: The `except Exception: git_sha = "unknown"` catch is extremely broad. This is acceptable for a health check (non-critical), but it hides the actual failure reason. More importantly, calling `git` as a subprocess in a CLI command is environment-dependent (git not installed, no .git directory, etc.).

5. **`_validate_existing_sqlite_db_url()` is 40 lines of URL parsing**: It manually parses SQLite URL variants (file:, file::memory:, ?mode=memory, ?uri=1) to check if the file exists. This is complex and error-prone. SQLAlchemy's `make_url()` already handles most of this; the manual URI parsing layer adds fragility.

6. **`plugins` sub-app is a singleton via `_plugin_manager_cache`**: The module-level `_plugin_manager_cache` is a global mutable singleton. This works for a CLI process (one initialization per process), but it makes testing harder and couples `cli_helpers.instantiate_plugins_from_config()` to the CLI module (it calls `from elspeth.cli import _get_plugin_manager`).

7. **`_format_validation_error()` uses `rich` directly**: This is the only place `rich` is used directly (other output uses `typer.echo()`). It creates inconsistency — `validate` gets rich-formatted error panels while `run` and `resume` get plain text errors for the same underlying error types. The `validate` command's error UX is better, but the inconsistency is architectural debt.

8. **Mixed `json` import pattern**: In `run` and `resume`, `import json` appears multiple times inside conditional blocks (`if output_format == "json":`). Some blocks use `import json as json_mod` and some use `import json`. This inconsistency across blocks is minor but reflects the incremental nature of the JSON output additions.

9. **`explain` command loads settings twice for passphrase resolution**: When `--database` is provided (no `--settings`), the code tries to `load_settings(settings_path)` separately just to get `landscape_settings` for passphrase resolution. If settings loading fails for any reason, it catches the error and silently falls through (passphrase will be None). This silent fallthrough violates CLAUDE.md's no-silent-failure principle and could allow opening an encrypted database without a passphrase (which would produce a cryptic "file is not a database" error).

---

### cli_helpers.py (212 lines)

**Purpose:** Plugin instantiation and database URL resolution helpers extracted from cli.py. Four functions: `instantiate_plugins_from_config()`, `resolve_database_url()`, `resolve_latest_run_id()`, `resolve_run_id()`, `resolve_audit_passphrase()`.

**Key functions:**
- `instantiate_plugins_from_config()`: Instantiates source, transforms, aggregations, and sinks from `ElspethSettings`. Validates `is_batch_aware` for aggregations. Returns `dict[str, Any]` (see concerns).
- `resolve_database_url()`: Priority resolution: CLI > explicit settings > default settings.yaml.
- `resolve_audit_passphrase()`: Reads passphrase from environment variable when backend is sqlcipher. Raises `RuntimeError` if env var not set.

**Concerns:**
1. **`instantiate_plugins_from_config()` returns `dict[str, Any]`**: The return type is an untyped dict with string keys. Callers access `plugins["source"]`, `plugins["sinks"]`, etc. by magic string. A `PluginBundle` dataclass would give static typing and IDE navigation.
2. **`instantiate_plugins_from_config()` calls `from elspeth.cli import _get_plugin_manager`**: This creates a circular-import-style coupling where `cli_helpers` depends on `cli` (a private function). The plugin manager singleton lives in cli.py to avoid a separate module, but `cli_helpers` reaches back into cli.py to get it. This is backwards — the singleton should live in a separate `plugins/manager_singleton.py` or similar.
3. **`resolve_database_url()` silently catches all exceptions on settings load**: `except Exception as e: raise ValueError(...)` — broad exception capture, re-raised with context. This is acceptable (the re-raise preserves the cause), but it means SQLAlchemy initialization errors (e.g., bad URL in settings) present as "Error loading settings" which may be confusing.

---

### cli_formatters.py (184 lines)

**Purpose:** Factory functions for CLI event formatters. `create_console_formatters()` and `create_json_formatters()` return `dict[type, Callable]` mapping event types to handler functions. `subscribe_formatters()` wires them to the EventBus.

**Key functions:**
- `create_console_formatters(prefix)`: Returns handlers for PhaseStarted, PhaseCompleted, PhaseError, RunSummary, ProgressEvent — human-readable with icons (✓, ✗, ⚠, ⏸).
- `create_json_formatters()`: Returns handlers for the same events — structured JSON to stdout.
- `subscribe_formatters()`: Iterates the formatter dict and calls `event_bus.subscribe()`.

**Dependencies:**
- `elspeth.contracts.cli.ProgressEvent`
- `elspeth.contracts.events.*`
- `elspeth.core.events.EventBusProtocol`
- `typer`

**Size concerns:** 184 lines — appropriate.

**Concerns:**
1. **MEMORY.md notes "CLI duplication (~600 lines of event formatters x3)"**: The current `cli_formatters.py` (184 lines) appears to be the result of a previous deduplication. The two formatter factories in this file are the single source of truth. The "x3" duplication mentioned in MEMORY.md no longer exists in the current code — this concern is resolved.
2. **Console formatter uses emojis**: `✓`, `✗`, `⚠`, `⏸`, `⚠` are used throughout. These may not render correctly on all terminals. Typer does not guard against non-UTF-8 terminals here. Minor concern.
3. **`_format_run_summary()` has complex formatting logic for routed destinations**: The `routed_summary` string is built conditionally. This is correct but could be extracted for readability.
4. **`event.routed_destinations` typed as iterable of `(name, count)` tuples**: The formatter relies on the contract that `event.routed_destinations` produces `(str, int)` pairs. This is not validated in the formatter — it trusts the event data as Tier 2 pipeline data (correct behavior).

---

## Cross-Cutting Concerns

### 1. Trust Tier Compliance

The MCP subsystem correctly applies the trust tier model:
- `_validate_tool_args()` treats MCP arguments as Tier 3 (external) and validates immediately.
- The `call_tool()` dispatcher has no blanket try/except — database/audit errors propagate as MCP protocol errors (Tier 1 crash behavior).
- `get_failure_context()` correctly raises `RuntimeError` on orphaned FK (Tier 1 corruption).
- `_validate_readonly_sql()` correctly guards the external SQL input.

The TUI correctly applies the trust tier model:
- `NodeDetailPanel.render_content()` crashes on invalid `error_json` type (Tier 1).
- `_validate_execution_error()` etc. crash on missing required keys (Tier 1).

The CLI has one violation identified:
- The `explain` command silently ignores settings loading failures when resolving the passphrase (`except (ValidationError, SecretLoadError) as e: pass`). This is a silent failure at a trust boundary.

### 2. Composite Primary Key Pattern

All MCP analyzer queries correctly use the composite `(node_id, run_id)` join pattern documented in CLAUDE.md:
- `get_failure_context()`: `.join(nodes_table, (node_states_table.c.node_id == nodes_table.c.node_id) & (node_states_table.c.run_id == nodes_table.c.run_id))`
- `get_performance_report()`: Same composite join.
- `get_error_analysis()`: Composite join via `outerjoin`.
- `list_operations()`: Composite join.

This is a systemic win — the pattern is consistently applied.

### 3. Defensive Programming

The MCP and TUI files are generally well-behaved with respect to CLAUDE.md's prohibition on defensive patterns:
- TypedDict fields accessed directly after validation.
- No defensive `.get()` on system-owned data.
- Crashes on audit data anomalies.

One exception: `NodeDetailPanel.render_content()` uses `.get()` on optional `NodeStateInfo` fields — this is correct because these fields are genuinely optional (marked `total=False` without `Required`).

### 4. The `(db, recorder)` Threading Pattern

Every analyzer submodule function signature is `(db: LandscapeDB, recorder: LandscapeRecorder, ...)`. This is a consequence of the module-function architecture rather than class-method architecture. The duplication is mechanical but represents 20+ function signatures that each carry two mandatory context arguments. When the `recorder` is not needed (e.g., `list_contract_violations` uses direct SQL, not the recorder), the `recorder` parameter is still present. A per-domain class (e.g., `class ContractAnalyzer`) would internalize this.

### 5. Schema Import Pattern

All SQL queries in the analyzer submodules import schema table objects (`from elspeth.core.landscape.schema import runs_table, ...`) inside function bodies rather than at module level. This is consistent across all four submodules. The pattern avoids circular imports but makes the dependency graph less visible and disables IDE import navigation.

---

## Known Issues Summary

| Severity | Location | Issue |
|----------|----------|-------|
| HIGH | tui/explain_app.py | TUI is non-interactive; `Static` widgets cannot respond to user input |
| HIGH | tui/explain_app.py | `action_refresh()` does not update displayed widgets |
| HIGH | tui/screens/explain_screen.py | Token loading always deferred, never completed — tokens never appear |
| HIGH | tui/screens/explain_screen.py | Node execution state never loaded in TUI (requires token selection UI) |
| MEDIUM | cli.py (explain) | Silent passphrase resolution failure when settings load fails |
| MEDIUM | mcp/server.py | `_ArgSpec` and `inputSchema` can diverge — no enforcement |
| MEDIUM | mcp/server.py | if/elif dispatch (23 branches) must be updated in 3 places per new tool |
| MEDIUM | mcp/analyzers/reports.py | `get_run_summary()` issues 11 separate queries |
| MEDIUM | mcp/analyzers/reports.py | `high_variance` uses truthiness on numeric values (should be `is not None`) |
| MEDIUM | mcp/analyzers/diagnostics.py | `diagnose()` counts quarantined rows across all historical runs |
| MEDIUM | mcp/analyzers/diagnostics.py | 1-hour stuck threshold is hardcoded |
| MEDIUM | cli.py | Error handling boilerplate duplicated in run/validate/resume/purge |
| MEDIUM | cli.py | `_orchestrator_context()` split lifecycle (caller owns db, ctx owns registry) |
| MEDIUM | cli_helpers.py | `plugins["..."]` magic string access — untyped dict return |
| MEDIUM | cli_helpers.py | `cli_helpers` imports private `_get_plugin_manager` from `cli` — backwards |
| LOW | tui/screens/explain_screen.py | `_PROCESSING_TYPES` recreated on every `_load_pipeline_structure()` call |
| LOW | tui/screens/explain_screen.py | `get_detail_panel_state()` accesses private `._state` attribute |
| LOW | tui/widgets/lineage_tree.py | `_TYPE_LABELS` and `_PROCESSING_TYPES` sets must be manually kept in sync |
| LOW | mcp/analyzers/queries.py | SQL safety parser does not handle backtick quotes or dollar-quoted strings |
| LOW | mcp/analyzers/queries.py | `SET` in blocklist may cause false positives |
| LOW | cli.py | `validate` uses rich-formatted errors; `run`/`resume` use plain text |
| LOW | cli.py | `_validate_existing_sqlite_db_url()` manually re-parses URLs SQLAlchemy handles |

---

## Recommendations for RC3.3

### Priority 1 (Correctness / Data Integrity)

1. **Fix the silent passphrase failure in `explain` command**: The `except (ValidationError, SecretLoadError) as e: pass` that falls through to `passphrase = None` should surface the error. If the user provided `--settings`, a settings failure should be fatal. If not, the fallthrough is correct but should log a warning.

2. **Fix `high_variance` truthiness check in `get_performance_report()`**: Change `if n["avg_ms"] and n["max_ms"]` to `if n["avg_ms"] is not None and n["max_ms"] is not None`. A node with zero average duration would be incorrectly excluded.

3. **Fix `diagnose()` quarantine count scope**: Scope the quarantined row count to recent runs (last N days or last N runs) rather than all historical runs. An always-non-zero INFO problem is noise that reduces the signal value of `diagnose()`.

### Priority 2 (Architecture)

4. **Replace the if/elif dispatch in `call_tool()`**: Replace the 100-line if/elif chain with a dispatch table:
   ```python
   _DISPATCH: dict[str, Callable[..., Any]] = {
       "list_runs": lambda a: analyzer.list_runs(limit=a["limit"], status=a["status"]),
       ...
   }
   result = _DISPATCH[name](args)
   ```
   This eliminates the "3 places to update per new tool" problem.

5. **Add sync enforcement between `_TOOL_ARGS` and `list_tools()` `inputSchema`**: Either generate the `inputSchema` from `_ArgSpec` at registration time, or add a test that verifies the tool names in `_TOOL_ARGS` match the tools registered in `list_tools()`. Currently these can silently diverge.

6. **Extract `PluginBundle` dataclass in `cli_helpers.py`**: Replace `dict[str, Any]` return with:
   ```python
   @dataclass(frozen=True, slots=True)
   class PluginBundle:
       source: SourceProtocol
       source_settings: SourceSettings
       transforms: list[WiredTransform]
       sinks: dict[str, SinkProtocol]
       aggregations: dict[str, tuple[TransformProtocol, AggregationSettings]]
   ```
   This gives static typing and eliminates magic string access throughout cli.py.

7. **Move `_get_plugin_manager()` to a separate module**: Break the `cli_helpers` → `cli` import cycle by moving the plugin manager singleton to `plugins/manager_singleton.py` (or similar). Both `cli.py` and `cli_helpers.py` should import from there.

8. **Consolidate error handling in CLI commands**: The 4 commands that call `_load_settings_with_secrets()` all have nearly identical 30-line error-handling blocks. Extract to:
   ```python
   def _handle_settings_load(settings_path: Path, ...) -> tuple[ElspethSettings, list]:
       """Load settings with standardized error handling."""
   ```

### Priority 3 (TUI Remediation or Removal)

9. **Decide the TUI's fate**: The TUI as currently implemented is not functional as an interactive tool. The options are:
   - **Option A**: Complete the TUI — make `LineageTree` and `NodeDetailPanel` proper Textual `Widget` subclasses, implement token loading, implement node selection, implement scrolling. This is significant work.
   - **Option B**: Remove the TUI — the `elspeth explain --no-tui` text output and `elspeth-mcp` + `explain_token` provide equivalent functionality without the interactive layer. The `ExplainApp` and `ExplainScreen` classes are largely unused infrastructure. Remove them and simplify the explain command to only support `--no-tui` and `--json` modes.
   - **Option C**: Acknowledge the TUI as a scaffold and document its limitations clearly.

   Given the "no legacy code" policy and the TUI's non-functional state, Option B is most consistent with project principles. The MCP server provides a richer interactive experience via Claude than the TUI does.

10. **Fix `ExplainScreen` token loading**: If the TUI is retained, the `lineage_data["tokens"]` must actually be populated. The `tokens` field requires querying `token_outcomes_table` to determine which tokens reached which sinks. This is available from `get_outcome_analysis()` data.

### Priority 4 (Quality)

11. **Scope `get_run_summary()` to fewer queries**: The 11 separate COUNT queries could be reduced to 3-4 using CTEs or subqueries. For large databases, this is a performance improvement; for small SQLite databases, it's an aesthetic improvement.

12. **Document SQL safety parser limitations**: Add a comment to `_validate_readonly_sql()` noting that backtick-quoted identifiers and PostgreSQL dollar-quoted strings are not supported. For the stated use case (SQLite + LLM-generated queries), this is acceptable.

13. **Unify CLI error formatting**: Apply `_format_validation_error()` (rich-formatted) consistently across `run`, `validate`, `resume`, and `purge` commands, or revert `validate` to use `typer.echo()` like the others. Inconsistent error UX is a user experience debt.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|-----------|-------|
| MCP architecture | HIGH | All 7 files read completely; architecture is clear and well-structured |
| MCP correctness | HIGH | Queries verified; composite key usage consistent; trust tier handling correct |
| TUI functionality | HIGH | Non-interactive status is certain from the code; token loading gap is confirmed |
| CLI architecture | HIGH | All 3 files read completely; structure is clear |
| CLI correctness | HIGH | Silent passphrase failure confirmed in code |
| `high_variance` truthiness bug | HIGH | Confirmed: `if n["avg_ms"] and n["max_ms"]` excludes zeros |
| `diagnose()` quarantine scope | HIGH | Confirmed: no WHERE clause scoping to recent runs |
| "600 lines CLI duplication x3" from MEMORY.md | HIGH (resolved) | `cli_formatters.py` is 184 lines and is the single source; duplication was already fixed |
| "server.py 2355 lines" from MEMORY.md | HIGH (historical) | Current server.py is 864 lines; the refactoring into analyzers/ submodules happened |
