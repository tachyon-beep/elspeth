# ELSPETH RC-2 Release Validation Checklist

**Purpose:** What MUST work before shipping RC-2. This is not a feature list - it's the minimum bar for release.

**Criterion:** If any item fails, RC-2 cannot ship.

**Status note (2026-02-01):** Checkmarks indicate **code-review evidence only** (implementation + tests present). Items are otherwise **unverified** until tests/verification are run per the procedure below.

**Legend:** `[CR]` code-review evidence only; `[GAP: ...]` known failure that blocks RC-2; `[KNOWN LIMITATION]` acceptable RC-2 limitation (see list below).

---

## 1. AUDIT INTEGRITY (Non-Negotiable)

These are the core promises of ELSPETH. Failure here is a showstopper.

### 1.1 Source Data Capture

- [x] Every source row has `source_data_ref` populated before any processing **[CR]**
- [x] Source row payload persisted to PayloadStore (not just hash) **[CR]**
- [x] `elspeth run` command wires PayloadStore **[CR]**
- [x] Quarantined rows recorded with original data and failure reason **[CR]**

### 1.2 Transform Boundaries

- [x] Every transform execution creates node_state record **[CR]**
- [x] Input hash recorded before transform runs **[CR]**
- [x] Output hash recorded after successful transform **[CR]**
- [x] Failed transforms record error details with retryable flag **[CR]**

### 1.3 External Call Recording

- [x] LLM calls record full request/response payloads **[CR]**
- [x] HTTP calls record request/response with status codes **[CR]**
- [x] Call latency captured **[CR]**
- [x] Calls linked to correct node_state **[CR]**

### 1.4 Terminal States

- [x] Every token reaches exactly one terminal state **[CR]**
- [x] No silent drops (row enters system → row has recorded outcome) **[CR]**
- [x] Terminal states: COMPLETED, ROUTED, FORKED, CONSUMED_IN_BATCH, COALESCED, QUARANTINED, FAILED **[CR]**

### 1.5 Lineage Query

- [x] `explain_token()` returns complete lineage for any token **[CR]**
- [x] Lineage includes: source_row → tokens → node_states → calls → routing_events → outcome **[CR]**
- [x] Fork/coalesce lineage traversable (parent_token_id chain) **[CR]**

---

## 2. CORE ENGINE FUNCTIONALITY

### 2.1 Linear Pipeline

- [x] Source → Transform chain → Sink works **[CR]**
- [x] Multiple transforms execute in sequence **[CR]**
- [x] Output sink receives all non-routed rows **[CR]**

### 2.2 Gate Routing

- [x] Gates evaluate conditions correctly **[CR]**
- [x] `continue` passes row to next node **[CR]**
- [x] `route_to_sink` sends row to named sink with reason **[CR]**
- [x] Routing events recorded in audit trail **[CR]**

### 2.3 Fork/Coalesce

- [x] Fork creates child tokens with correct parent linkage **[CR]**
- [x] Each branch executes independently **[CR]**
- [x] Coalesce merges tokens when all branches complete **[CR]**
- [x] Coalesce timeout fires (not just at end-of-source) - **CRIT-03 in RC2 plan** **[CR]**

### 2.4 Aggregation

- [x] Count trigger fires at threshold **[CR]**
- [x] Timeout trigger fires (with known limitation: only on next row arrival) **[CR]**
- [x] End-of-source flushes remaining buffers **[CR]**
- [x] Batch members linked to batch in audit trail **[CR]**
- [x] Trigger type recorded in metadata **[CR]**

### 2.5 Retry Logic

- [x] Transient failures retry with backoff **[CR]**
- [x] Max retries respected **[CR]**
- [x] Each attempt recorded separately **[CR]**
- [x] Non-retryable errors fail immediately **[CR]**

---

## 3. CLI COMMANDS

### 3.1 `elspeth run`

- [x] `--settings` loads configuration **[CR]**
- [x] `--execute` required to actually run (safety gate) **[CR]**
- [x] `--dry-run` validates without executing **[CR]**
- [x] PayloadStore instantiated and passed to engine **[CR]**

### 3.2 `elspeth validate`

- [x] Validates YAML syntax **[CR]**
- [x] Validates plugin references exist **[CR]**
- [x] Validates sink references in routes **[CR]**
- [x] Reports clear error messages **[CR]**

### 3.3 `elspeth resume`

- [x] Loads checkpoint from previous run **[CR]**
- [x] Resumes from last known good state **[CR]**
- [x] PayloadStore wired correctly (already works) **[CR]**

### 3.4 `elspeth explain`

- [x] `--run` and `--row` parameters work **[CR]**
- [x] Returns lineage data (JSON mode minimum) **[CR]**
- [ ] TUI mode acceptable as "preview" for RC2 **[GAP: CLI launches ExplainApp without DB; TUI shows placeholder instead of lineage]**

### 3.5 `elspeth plugins list`

- [x] Lists all available plugins **[CR]**
- [x] `--type` filter works **[CR]**

### 3.6 `elspeth purge`

- [x] `--retention-days` respected **[CR]**
- [x] `--dry-run` shows what would be deleted **[CR]**
- [x] Preserves hashes after payload deletion **[CR]**

---

## 4. PLUGIN CORRECTNESS

### 4.1 Sources

- [x] CSV source handles multiline quoted fields **[CR]**
- [x] JSON source handles both array and JSONL formats **[CR]**
- [x] Field normalization produces valid Python identifiers **[CR]**
- [x] Collision detection reports clear errors **[CR]**

### 4.2 Core Transforms

- [x] Passthrough passes rows unchanged **[CR]**
- [x] Field mapper renames fields correctly **[CR]**
- [x] Truncate respects length limits **[CR]**

### 4.3 LLM Transforms (if using LLM pack)

- [x] Azure LLM transform calls API and records response **[CR]**
- [x] Template variables substituted correctly **[CR]**
- [x] Structured output mode returns parsed JSON **[CR]**
- [ ] Rate limiting prevents 429 errors **[KNOWN LIMITATION]**

### 4.4 Sinks

- [x] CSV sink writes valid CSV **[CR]**
- [x] JSON sink writes valid JSON/JSONL **[CR]**
- [x] Database sink inserts rows correctly **[CR]**

---

## 5. DATA INTEGRITY

### 5.1 Canonical JSON

- [x] NaN rejected with clear error (not silently converted) **[CR]**
- [x] Infinity rejected with clear error **[CR]**
- [x] numpy types converted correctly **[CR]**
- [x] pandas Timestamp → UTC ISO8601 **[CR]**
- [x] Hash stable across process restarts **[CR]**

### 5.2 Payload Store

- [x] `put()` stores data and returns ref **[CR]**
- [x] `get()` retrieves data by ref **[CR]**
- [x] `exists()` returns correct boolean **[CR]**
- [x] Hash verification on read **[CR]**

### 5.3 Database Integrity

- [x] Foreign keys enforced **[CR]**
- [x] No orphan records **[CR]**
- [x] Unique constraints respected **[CR]**

---

## 6. ERROR HANDLING

### 6.1 Source Errors

- [x] Malformed rows quarantined (not crash) **[CR]**
- [x] Quarantine records original data **[CR]**
- [x] Processing continues for valid rows **[CR]**

### 6.2 Transform Errors

- [x] Errors recorded with reason **[CR]**
- [x] Row routed to error sink if configured **[CR]**
- [x] Pipeline continues for other rows **[CR]**

### 6.3 External Call Errors

- [x] Timeouts recorded with details **[CR]**
- [x] 4xx/5xx responses recorded **[CR]**
- [x] Retry logic engages for transient errors **[CR]**

---

## 7. CONFIGURATION

### 7.1 Basic Loading

- [x] YAML syntax parsed correctly **[CR]**
- [x] Environment variable interpolation `${VAR}` works **[CR]**
- [x] Default values applied **[CR]**

### 7.2 Validation

- [x] Invalid plugin names rejected **[CR]**
- [x] Invalid sink references in routes rejected **[CR]**
- [x] Missing required fields reported **[CR]**

---

## KNOWN ISSUES ACCEPTABLE FOR RC-2

These are documented limitations, not blockers:

1. **Timeout triggers** - Fire only when next row arrives (documented limitation)
2. **Explain TUI** - Works but may show "preview" quality
3. **Rate limiting** - Engine infrastructure exists but not wired through CLI (documented, workaround: LLM plugins have their own)
4. **Concurrent processing** - Config exists but not integrated (single-threaded acceptable for RC2)
5. **Profile system** - Deferred (single settings file works)
6. **Redaction profiles** - Deferred (manual redaction in plugins acceptable)

---

## VERIFICATION PROCEDURE

For each item above:

1. Write or identify existing test
2. Run test against clean database
3. Verify audit trail contains expected records
4. Mark checkbox when confirmed

**Release gate:** All non-"acceptable limitation" items checked.
