# ELSPETH RC-2 Release Validation Checklist

**Purpose:** What MUST work before shipping RC-2. This is not a feature list - it's the minimum bar for release.

**Criterion:** If any item fails, RC-2 cannot ship.

**Status note (2026-02-01):** This checklist shows **known gaps only** from code review. Items are otherwise **unverified** until tests/verification are run per the procedure below.

**Legend:** `[GAP: ...]` marks a known failure that blocks RC-2.

---

## 1. AUDIT INTEGRITY (Non-Negotiable)

These are the core promises of ELSPETH. Failure here is a showstopper.

### 1.1 Source Data Capture

- [ ] Every source row has `source_data_ref` populated before any processing
- [ ] Source row payload persisted to PayloadStore (not just hash)
- [ ] `elspeth run` command wires PayloadStore (currently broken per CLI-016)
- [ ] Quarantined rows recorded with original data and failure reason

### 1.2 Transform Boundaries

- [ ] Every transform execution creates node_state record
- [ ] Input hash recorded before transform runs
- [ ] Output hash recorded after successful transform
- [ ] Failed transforms record error details with retryable flag

### 1.3 External Call Recording

- [ ] LLM calls record full request/response payloads
- [ ] HTTP calls record request/response with status codes
- [ ] Call latency captured
- [ ] Calls linked to correct node_state

### 1.4 Terminal States

- [ ] Every token reaches exactly one terminal state
- [ ] No silent drops (row enters system → row has recorded outcome)
- [ ] Terminal states: COMPLETED, ROUTED, FORKED, CONSUMED_IN_BATCH, COALESCED, QUARANTINED, FAILED

### 1.5 Lineage Query

- [ ] `explain_token()` returns complete lineage for any token
- [ ] Lineage includes: source_row → tokens → node_states → calls → routing_events → outcome
- [ ] Fork/coalesce lineage traversable (parent_token_id chain)

---

## 2. CORE ENGINE FUNCTIONALITY

### 2.1 Linear Pipeline

- [ ] Source → Transform chain → Sink works
- [ ] Multiple transforms execute in sequence
- [ ] Output sink receives all non-routed rows

### 2.2 Gate Routing

- [ ] Gates evaluate conditions correctly
- [ ] `continue` passes row to next node
- [ ] `route_to_sink` sends row to named sink with reason
- [ ] Routing events recorded in audit trail

### 2.3 Fork/Coalesce

- [ ] Fork creates child tokens with correct parent linkage
- [ ] Each branch executes independently
- [ ] Coalesce merges tokens when all branches complete
- [ ] Coalesce timeout fires (not just at end-of-source) - **CRIT-03 in RC2 plan**

### 2.4 Aggregation

- [ ] Count trigger fires at threshold
- [ ] Timeout trigger fires (with known limitation: only on next row arrival)
- [ ] End-of-source flushes remaining buffers
- [ ] Batch members linked to batch in audit trail
- [ ] Trigger type recorded in metadata

### 2.5 Retry Logic

- [ ] Transient failures retry with backoff
- [ ] Max retries respected
- [ ] Each attempt recorded separately
- [ ] Non-retryable errors fail immediately

---

## 3. CLI COMMANDS

### 3.1 `elspeth run`

- [ ] `--settings` loads configuration
- [ ] `--execute` required to actually run (safety gate)
- [ ] `--dry-run` validates without executing
- [ ] PayloadStore instantiated and passed to engine (FIX REQUIRED)

### 3.2 `elspeth validate`

- [ ] Validates YAML syntax
- [ ] Validates plugin references exist
- [ ] Validates sink references in routes
- [ ] Reports clear error messages

### 3.3 `elspeth resume`

- [ ] Loads checkpoint from previous run
- [ ] Resumes from last known good state
- [ ] PayloadStore wired correctly (already works)

### 3.4 `elspeth explain`

- [ ] `--run` and `--row` parameters work
- [ ] Returns lineage data (JSON mode minimum)
- [ ] TUI mode acceptable as "preview" for RC2 **[GAP: CLI launches ExplainApp without DB; TUI shows placeholder instead of lineage]**

### 3.5 `elspeth plugins list`

- [ ] Lists all available plugins
- [ ] `--type` filter works

### 3.6 `elspeth purge`

- [ ] `--retention-days` respected
- [ ] `--dry-run` shows what would be deleted
- [ ] Preserves hashes after payload deletion

---

## 4. PLUGIN CORRECTNESS

### 4.1 Sources

- [ ] CSV source handles multiline quoted fields
- [ ] JSON source handles both array and JSONL formats
- [ ] Field normalization produces valid Python identifiers
- [ ] Collision detection reports clear errors

### 4.2 Core Transforms

- [ ] Passthrough passes rows unchanged
- [ ] Field mapper renames fields correctly
- [ ] Truncate respects length limits

### 4.3 LLM Transforms (if using LLM pack)

- [ ] Azure LLM transform calls API and records response
- [ ] Template variables substituted correctly
- [ ] Structured output mode returns parsed JSON
- [ ] Rate limiting prevents 429 errors

### 4.4 Sinks

- [ ] CSV sink writes valid CSV
- [ ] JSON sink writes valid JSON/JSONL
- [ ] Database sink inserts rows correctly

---

## 5. DATA INTEGRITY

### 5.1 Canonical JSON

- [ ] NaN rejected with clear error (not silently converted)
- [ ] Infinity rejected with clear error
- [ ] numpy types converted correctly
- [ ] pandas Timestamp → UTC ISO8601
- [ ] Hash stable across process restarts

### 5.2 Payload Store

- [ ] `put()` stores data and returns ref
- [ ] `get()` retrieves data by ref
- [ ] `exists()` returns correct boolean
- [ ] Hash verification on read

### 5.3 Database Integrity

- [ ] Foreign keys enforced
- [ ] No orphan records
- [ ] Unique constraints respected

---

## 6. ERROR HANDLING

### 6.1 Source Errors

- [ ] Malformed rows quarantined (not crash)
- [ ] Quarantine records original data
- [ ] Processing continues for valid rows

### 6.2 Transform Errors

- [ ] Errors recorded with reason
- [ ] Row routed to error sink if configured
- [ ] Pipeline continues for other rows

### 6.3 External Call Errors

- [ ] Timeouts recorded with details
- [ ] 4xx/5xx responses recorded
- [ ] Retry logic engages for transient errors

---

## 7. CONFIGURATION

### 7.1 Basic Loading

- [ ] YAML syntax parsed correctly
- [ ] Environment variable interpolation `${VAR}` works
- [ ] Default values applied

### 7.2 Validation

- [ ] Invalid plugin names rejected
- [ ] Invalid sink references in routes rejected
- [ ] Missing required fields reported

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
