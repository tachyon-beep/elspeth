# T1: Freeze All 16 Mutable Audit Record Dataclasses

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `frozen=True` to all 16 mutable `@dataclass` definitions in `contracts/audit.py`, enforcing immutability at the Tier 1 audit boundary.

**Architecture:** These 16 dataclasses are audit records that flow from the engine/recorder into the Landscape database. They are already immutable *by convention* — the explore agent confirmed zero post-construction mutation sites across `src/` and `tests/`. Adding `frozen=True` converts this convention to an enforcement. No `dataclasses.replace()` changes are needed.

**Tech Stack:** Python `dataclasses` module, `pytest` for verification.

**Filigree Issue:** `elspeth-rapid-141d43` (in_progress)

---

### Task 1: Add `frozen=True` to All 16 Dataclasses

**Files:**
- Modify: `src/elspeth/contracts/audit.py` (16 decorator changes)

**Step 1: Apply `frozen=True` to all 16 bare `@dataclass` decorators**

The 16 targets (by line number in current file):

| Line | Class                    | Has `__post_init__`? |
|------|--------------------------|----------------------|
| 43   | `Run`                    | Yes (enum validation) |
| 70   | `Node`                   | Yes (enum validation) |
| 98   | `Edge`                   | Yes (enum validation) |
| 118  | `Row`                    | No |
| 131  | `Token`                  | No |
| 146  | `TokenParent`            | No |
| 259  | `Call`                   | Yes (enum validation) |
| 293  | `Artifact`               | No |
| 309  | `RoutingEvent`           | Yes (enum validation) |
| 331  | `Batch`                  | Yes (enum validation) |
| 355  | `BatchMember`            | No |
| 364  | `BatchOutput`            | No |
| 373  | `Checkpoint`             | Yes (hash validation) |
| 415  | `RowLineage`             | No |
| 466  | `ValidationErrorRecord`  | No |
| 553  | `TransformErrorRecord`   | No |

For each, change `@dataclass` to `@dataclass(frozen=True)`.

**DO NOT TOUCH** these already-frozen types:
- `NodeStateOpen` (line 155) — already `frozen=True`
- `NodeStatePending` (line 176) — already `frozen=True`
- `NodeStateCompleted` (line 203) — already `frozen=True`
- `NodeStateFailed` (line 229) — already `frozen=True`
- `NonCanonicalMetadata` (line 485) — already `frozen=True`
- `TokenOutcome` (line 572) — already `frozen=True`
- `Operation` (line 605) — already `frozen=True, slots=True`
- `SecretResolution` (line 698) — already `frozen=True, slots=True`

**DO NOT TOUCH** these TypedDict types (not dataclasses):
- `ExportStatusUpdate` (line 439)
- `BatchStatusUpdate` (line 453)

**Step 2: Run tests to verify no breakage**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_audit.py tests/unit/core/landscape/test_models_mutation_gaps.py -v`
Expected: All tests PASS (no mutation sites exist, so freezing is purely additive enforcement).

**Step 3: Run full unit test suite**

Run: `.venv/bin/python -m pytest tests/unit/ -x -q`
Expected: All PASS

---

### Task 2: Extend Immutability Tests for Newly-Frozen Types

**Files:**
- Modify: `tests/unit/contracts/test_audit.py` (extend `TestFrozenDataclassImmutability`)

**Step 1: Write the new parametrized test entries**

Add 16 new entries to the existing `TestFrozenDataclassImmutability` parametrized test at line ~1354. Each entry creates a minimal instance and attempts to mutate a field.

The new entries to add (after existing NonCanonicalMetadata entry):

```python
# Run
(
    lambda: Run(
        run_id="r1",
        started_at=datetime.now(UTC),
        config_hash="a" * 64,
        settings_json="{}",
        canonical_version="1.0",
        status=RunStatus.RUNNING,
    ),
    "run_id",
),
# Node
(
    lambda: Node(
        node_id="n1",
        run_id="r1",
        plugin_name="test",
        node_type=NodeType.SOURCE,
        plugin_version="1.0",
        determinism=Determinism.DETERMINISTIC,
        config_hash="a" * 64,
        config_json="{}",
        registered_at=datetime.now(UTC),
    ),
    "node_id",
),
# Edge
(
    lambda: Edge(
        edge_id="e1",
        run_id="r1",
        from_node_id="n1",
        to_node_id="n2",
        label="continue",
        default_mode=RoutingMode.MOVE,
        created_at=datetime.now(UTC),
    ),
    "edge_id",
),
# Row
(
    lambda: Row(
        row_id="row-1",
        run_id="r1",
        source_node_id="n1",
        row_index=0,
        source_data_hash="a" * 64,
        created_at=datetime.now(UTC),
    ),
    "row_id",
),
# Token
(
    lambda: Token(
        token_id="t1",
        row_id="row-1",
        created_at=datetime.now(UTC),
    ),
    "token_id",
),
# TokenParent
(
    lambda: TokenParent(
        token_id="t1",
        parent_token_id="t0",
        ordinal=0,
    ),
    "token_id",
),
# Call
(
    lambda: Call(
        call_id="c1",
        call_index=0,
        call_type=CallType.HTTP,
        status=CallStatus.SUCCESS,
        request_hash="a" * 64,
        created_at=datetime.now(UTC),
        state_id="s1",
    ),
    "call_id",
),
# Artifact
(
    lambda: Artifact(
        artifact_id="a1",
        run_id="r1",
        produced_by_state_id="s1",
        sink_node_id="sink-1",
        artifact_type="csv",
        path_or_uri="/tmp/out.csv",
        content_hash="a" * 64,
        size_bytes=1024,
        created_at=datetime.now(UTC),
    ),
    "artifact_id",
),
# RoutingEvent
(
    lambda: RoutingEvent(
        event_id="evt-1",
        state_id="s1",
        edge_id="e1",
        routing_group_id="rg-1",
        ordinal=0,
        mode=RoutingMode.MOVE,
        created_at=datetime.now(UTC),
    ),
    "event_id",
),
# Batch
(
    lambda: Batch(
        batch_id="b1",
        run_id="r1",
        aggregation_node_id="agg-1",
        attempt=1,
        status=BatchStatus.DRAFT,
        created_at=datetime.now(UTC),
    ),
    "batch_id",
),
# BatchMember
(
    lambda: BatchMember(
        batch_id="b1",
        token_id="t1",
        ordinal=0,
    ),
    "batch_id",
),
# BatchOutput
(
    lambda: BatchOutput(
        batch_id="b1",
        output_type="token",
        output_id="t2",
    ),
    "batch_id",
),
# Checkpoint
(
    lambda: Checkpoint(
        checkpoint_id="cp-1",
        run_id="r1",
        token_id="t1",
        node_id="n1",
        sequence_number=1,
        created_at=datetime.now(UTC),
        upstream_topology_hash="a" * 64,
        checkpoint_node_config_hash="b" * 64,
    ),
    "checkpoint_id",
),
# RowLineage
(
    lambda: RowLineage(
        row_id="row-1",
        run_id="r1",
        source_node_id="n1",
        row_index=0,
        source_data_hash="a" * 64,
        created_at=datetime.now(UTC),
        source_data=None,
        payload_available=False,
    ),
    "row_id",
),
# ValidationErrorRecord
(
    lambda: ValidationErrorRecord(
        error_id="verr-1",
        run_id="r1",
        node_id="n1",
        row_hash="a" * 64,
        error="test error",
        schema_mode="fixed",
        destination="quarantine",
        created_at=datetime.now(UTC),
    ),
    "error_id",
),
# TransformErrorRecord
(
    lambda: TransformErrorRecord(
        error_id="terr-1",
        run_id="r1",
        token_id="t1",
        transform_id="xform-1",
        row_hash="a" * 64,
        destination="error_sink",
        created_at=datetime.now(UTC),
    ),
    "error_id",
),
```

And update the `ids=` list to include:
```python
ids=[
    # Existing 6:
    "NodeStateOpen",
    "NodeStatePending",
    "NodeStateCompleted",
    "NodeStateFailed",
    "TokenOutcome",
    "NonCanonicalMetadata",
    # New 16:
    "Run",
    "Node",
    "Edge",
    "Row",
    "Token",
    "TokenParent",
    "Call",
    "Artifact",
    "RoutingEvent",
    "Batch",
    "BatchMember",
    "BatchOutput",
    "Checkpoint",
    "RowLineage",
    "ValidationErrorRecord",
    "TransformErrorRecord",
],
```

Also add the necessary imports at top of file if not already present:
- `Checkpoint` (already imported via `from elspeth.contracts import ...`)
- `RowLineage` — **NOT currently imported**, needs adding

**Step 2: Run the immutability tests**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_audit.py::TestFrozenDataclassImmutability -v`
Expected: 22 PASS (6 existing + 16 new)

**Step 3: Commit**

```bash
git add src/elspeth/contracts/audit.py tests/unit/contracts/test_audit.py
git commit -m "fix(audit): freeze all 16 mutable audit record dataclasses (T1)

Add frozen=True to Run, Node, Edge, Row, Token, TokenParent, Call,
Artifact, RoutingEvent, Batch, BatchMember, BatchOutput, Checkpoint,
RowLineage, ValidationErrorRecord, TransformErrorRecord.

Enforces immutability at Tier 1 audit boundary — mutations now crash
at the mutation site instead of silently corrupting the audit trail.

Extends TestFrozenDataclassImmutability to cover all 22 frozen types.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Verification Gate

**Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: All PASS (8,000+ tests)

**Step 2: Run mypy**

Run: `.venv/bin/python -m mypy src/elspeth/contracts/audit.py`
Expected: Clean (no errors)

**Step 3: Run ruff**

Run: `.venv/bin/python -m ruff check src/elspeth/contracts/audit.py tests/unit/contracts/test_audit.py`
Expected: Clean

**Step 4: Verify frozen count**

Run: `grep -c 'frozen=True' src/elspeth/contracts/audit.py`
Expected: 24 (16 newly frozen + 8 already frozen)

**Step 5: Close Filigree issue**

Close `elspeth-rapid-141d43` with reason: "All 16 audit dataclasses frozen. 22/22 immutability tests pass. Unblocks T9."
