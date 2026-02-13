# ExternalCallCompleted Token Correlation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure `ExternalCallCompleted` telemetry includes `token_id` for transform-context calls so telemetry can be correlated directly with row/token lineage.

**Architecture:** Add optional `token_id` to the telemetry event contract, propagate it through audited client and plugin-context emission paths, and prefer explicit token context when available while allowing operation-context calls to omit it. Keep existing XOR invariant (`state_id` vs `operation_id`) unchanged.

**Tech Stack:** Python 3.12, dataclasses, pytest, telemetry contracts/exporters.

**Prerequisites:**
- Activate repo venv (`.venv`) and run tests via `.venv/bin/python -m pytest`.
- Work on branch `RC3-quality-sprint`.

---

### Task 1: Write Failing Correlation Tests

**Files:**
- Modify: `tests/unit/plugins/test_context.py`
- Modify: `tests/unit/plugins/clients/test_audited_llm_client.py`
- Modify: `tests/unit/plugins/clients/test_http.py`

**Step 1: Add PluginContext telemetry assertions**
Add tests that verify:
- transform-context (`state_id`) emission includes `token_id` when `ctx.token` is set.
- operation-context (`operation_id`) emission allows `token_id is None`.

**Step 2: Add audited client telemetry assertions**
Add tests that verify emitted `ExternalCallCompleted` contains `token_id` when `AuditedLLMClient` / `AuditedHTTPClient` are initialized with `token_id`.

**Step 3: Run tests to verify RED state**
Run:
```bash
.venv/bin/python -m pytest tests/unit/plugins/test_context.py -k "token_id and record_call" -q
.venv/bin/python -m pytest tests/unit/plugins/clients/test_audited_llm_client.py -k "telemetry and token_id" -q
.venv/bin/python -m pytest tests/unit/plugins/clients/test_http.py -k "telemetry and token_id" -q
```

Expected: failures because event contract/emitters currently have no `token_id` field.

**Definition of Done:**
- [ ] New assertions exist for transform vs operation context token correlation.
- [ ] Tests fail for the expected reason (missing `token_id` support).

---

### Task 2: Implement Contract + Emission Support

**Files:**
- Modify: `src/elspeth/contracts/events.py`
- Modify: `src/elspeth/contracts/plugin_context.py`
- Modify: `src/elspeth/plugins/clients/base.py`
- Modify: `src/elspeth/plugins/clients/llm.py`
- Modify: `src/elspeth/plugins/clients/http.py`
- Modify: `src/elspeth/plugins/llm/base.py`
- Modify: `src/elspeth/plugins/llm/azure.py`
- Modify: `src/elspeth/plugins/llm/azure_multi_query.py`
- Modify: `src/elspeth/plugins/llm/openrouter.py`
- Modify: `src/elspeth/plugins/llm/openrouter_multi_query.py`
- Modify: `src/elspeth/plugins/transforms/azure/content_safety.py`
- Modify: `src/elspeth/plugins/transforms/azure/prompt_shield.py`
- Modify: `src/elspeth/plugins/transforms/web_scrape.py`

**Step 1: Extend telemetry event contract**
Add optional field:
```python
token_id: str | None = None
```
to `ExternalCallCompleted` with docstring note that transform-context calls should populate it when known.

**Step 2: Thread token context through emitters**
- `PluginContext.record_call(...)`: set `token_id` from `ctx.token` (or `None` for operation context).
- `AuditedClientBase`: accept/store optional `token_id` and expose internal resolution helper for emitters.
- `AuditedLLMClient` / `AuditedHTTPClient`: include `token_id=` when constructing `ExternalCallCompleted`.

**Step 3: Pass token context at known call sites**
Update audited-client construction paths that already have token identity in scope to pass `token_id`, while preserving existing behavior where token is genuinely unavailable.

**Step 4: Keep invariants unchanged**
Do not change `ExternalCallCompleted` XOR validation for `state_id` vs `operation_id`.

**Definition of Done:**
- [ ] `ExternalCallCompleted` supports optional `token_id`.
- [ ] Transform-context emit paths populate `token_id` when available.
- [ ] Operation-context paths remain valid with `token_id=None`.

---

### Task 3: Verify, Close Bug, and Land

**Files:**
- Modify: `docs/bugs/open/engine-spans/P2-2026-02-05-externalcallcompleted-telemetry-lacks-token-i.md` (move to closed)
- Create/Modify: `docs/bugs/closed/engine-spans/P2-2026-02-05-externalcallcompleted-telemetry-lacks-token-i.md`

**Step 1: Run focused verification suite**
Run:
```bash
.venv/bin/python -m pytest tests/unit/plugins/test_context.py tests/unit/plugins/clients/test_audited_llm_client.py tests/unit/plugins/clients/test_http.py -q
.venv/bin/python -m pytest tests/unit/telemetry/test_filtering.py tests/unit/telemetry/test_contracts.py -q
```

**Step 2: Close bug documentation**
Move the bug file from `open` to `closed`, mark `Status: CLOSED`, and add dated verification notes with evidence paths.

**Step 3: Update and close issue tracking**
- Keep `elspeth-rapid-69zv` status accurate.
- Close with reason once tests pass and bug doc is closed.

**Step 4: Commit and push**
Run:
```bash
git add <changed files>
git commit -m "fix(telemetry): include token_id in external call events"
git pull --rebase
bd sync
git push
git status
```

**Definition of Done:**
- [ ] Tests pass for token correlation behavior.
- [ ] Bug doc moved to closed with evidence.
- [ ] Beads issue closed.
- [ ] Commit pushed; branch is up to date with origin.
