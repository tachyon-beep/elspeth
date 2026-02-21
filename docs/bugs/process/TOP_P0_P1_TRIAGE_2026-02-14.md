# Top P0/P1 Triage - 2026-02-14

## Scope

- Converted top codex sweep findings into structured bug files and Beads issues.
- Open triage set: 13 P1 issues.
- Closed triage set: 1 P0 + 1 P1 already fixed in commit `abd7f439`.

## Open Bugs

| Beads ID | Priority | Title | Bug File |
|---|---|---|---|
| `elspeth-rapid-jkmk` | P1 | load_settings drops unknown top-level keys silently | `docs/bugs/open/core-config/P1-2026-02-14-load-settings-drops-unknown-top-level-keys.md` |
| `elspeth-rapid-5rom` | P1 | complete_node_state can commit invalid terminal combinations | `docs/bugs/open/core-landscape/P1-2026-02-14-complete-node-state-commits-invalid-terminal-combinations.md` |
| `elspeth-rapid-uqy2` | P1 | MockClock allows non-finite and non-monotonic values | `docs/bugs/open/engine/P1-2026-02-14-mock-clock-allows-nonfinite-or-nonmonotonic-time.md` |
| `elspeth-rapid-r826` | P1 | Gate executor can leave OPEN node states on dispatch exceptions | `docs/bugs/open/engine/P1-2026-02-14-gate-executor-can-leave-open-node-states-on-dispatch-errors.md` |
| `elspeth-rapid-ti23` | P1 | resume can create a new empty DB for missing settings path | `docs/bugs/open/cli/P1-2026-02-14-resume-can-create-empty-db-when-settings-path-is-wrong.md` |
| `elspeth-rapid-wkb6` | P1 | purge retention-days accepts non-positive override values | `docs/bugs/open/cli/P1-2026-02-14-purge-retention-days-accepts-nonpositive-values.md` |
| `elspeth-rapid-o70k` | P1 | MCP call_tool returns success for invalid args/unknown tools | `docs/bugs/open/mcp/P1-2026-02-14-call-tool-returns-success-for-invalid-args-or-unknown-tools.md` |
| `elspeth-rapid-z6qk` | P1 | MCP get_errors accepts invalid error_type values | `docs/bugs/open/mcp/P1-2026-02-14-get-errors-accepts-invalid-error-type-values.md` |
| `elspeth-rapid-gkrd` | P1 | AzureBlobSink misses required-field validation | `docs/bugs/open/plugins/P1-2026-02-14-azure-blob-sink-misses-required-field-validation.md` |
| `elspeth-rapid-ydk4` | P1 | OpenRouterBatch misclassifies success rows when error key exists | `docs/bugs/open/plugins/P1-2026-02-14-openrouter-batch-misclassifies-success-rows-with-error-key.md` |
| `elspeth-rapid-u16i` | P1 | DatabaseSink default mode allows schema-invalid rows | `docs/bugs/open/plugins/P1-2026-02-14-database-sink-default-allows-schema-invalid-rows.md` |
| `elspeth-rapid-r042` | P1 | SchemaContract.with_field crashes on nested JSON values | `docs/bugs/open/contracts/P1-2026-02-14-schema-contract-with-field-crashes-on-nested-json-values.md` |
| `elspeth-rapid-nmcc` | P1 | Sanitized URL wrappers can be constructed with unsanitized values | `docs/bugs/open/contracts/P1-2026-02-14-sanitized-url-types-can-be-constructed-with-secrets.md` |

## Closed Fixed

| Beads ID | Priority | Bug File | Fixed Commit |
|---|---|---|---|
| `elspeth-rapid-imp3` | P0 | `docs/bugs/closed/core-checkpoint/P0-2026-02-14-recovery-row-drop-with-mixed-buffered-tokens.md` | `abd7f439` |
| `elspeth-rapid-o4ps` | P1 | `docs/bugs/closed/core-landscape/P1-2026-02-14-empty-operation-payloads-not-recorded.md` | `abd7f439` |
