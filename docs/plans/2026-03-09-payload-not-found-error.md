# PayloadNotFoundError Domain Exception — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace stdlib `KeyError` with a domain-specific `PayloadNotFoundError` in the `PayloadStore` protocol so that callers cannot accidentally catch the wrong exception parent class.

**Architecture:** The new exception lives in `contracts/payload_store.py` (L0) alongside the existing `IntegrityError`. All callers are in `core/` (L1). The change is mechanical: define the exception, update the two implementations (`FilesystemPayloadStore` and `MockPayloadStore`), update all catch sites (both direct and indirect via `_retrieve_and_parse_payload()`), update all tests. No behavioral change — same semantics, better type safety.

**Tech Stack:** Python exceptions, pytest, Hypothesis property tests

**Prior context:** The bug that motivated this was `journal.py:_load_payload()` catching `OSError` when the protocol actually raises `KeyError`. That was hot-fixed in commit `fc43e03f` by adding `KeyError` to the except tuple. This plan replaces that `KeyError` with `PayloadNotFoundError` throughout.

**Review history:** Plan reviewed twice by four specialist agents (reality, architecture, quality, systems). v2 incorporated initial findings. v3 addresses the second review round: fixed broken intermediate commit (property test moved to Task 2), clarified ambiguous import instruction (Task 4d), added debug logging to silent PURGED paths, added missing `get_row_data` PURGED test, fixed stale integration test docstring.

---

## Task 1: Define `PayloadNotFoundError` in contracts

**Files:**
- Modify: `src/elspeth/contracts/payload_store.py:13-56`
- Modify: `src/elspeth/contracts/__init__.py:217,428-429`
- Modify: `tests/unit/core/test_payload_store.py` (contract test)

**Step 1: Add the exception class after the `IntegrityError` class definition (insert after line 21, which is the `pass` body of `IntegrityError`)**

```python
class PayloadNotFoundError(Exception):
    """Raised when a payload blob is not found (purged, stale reference).

    This is a normal operational condition — retention policies purge old
    payloads. Callers decide whether to degrade gracefully or propagate.
    """

    def __init__(self, content_hash: str) -> None:
        if not content_hash:
            raise ValueError("PayloadNotFoundError requires a non-empty content_hash")
        self.content_hash = content_hash
        super().__init__(f"Payload not found: {content_hash}")
```

**Step 2: Add a design note to the module docstring (line 1-8)**

Add to the module docstring after "Consolidated here to avoid circular imports and provide single source of truth.":
```python
IntegrityError and PayloadNotFoundError are the complete exception vocabulary
for this protocol — one for corruption, one for absence. Do not add further
exception subtypes without strong justification.
```

**Step 3: Update the `retrieve()` docstring (line 52-53)**

Change:
```python
            KeyError: If content not found
```
To:
```python
            PayloadNotFoundError: If content not found
```

**Step 4: Re-export from `contracts/__init__.py`**

Update the import at line 217:
```python
from elspeth.contracts.payload_store import IntegrityError, PayloadNotFoundError, PayloadStore
```

Add `"PayloadNotFoundError",` to `__all__` between `"IntegrityError"` and `"PayloadStore"` (around line 428-429):
```python
    # payload_store
    "IntegrityError",
    "PayloadNotFoundError",
    "PayloadStore",
```

**Step 5: Add contract test for exception hierarchy**

Add to `tests/unit/core/test_payload_store.py` in the `TestPayloadStoreProtocol` class:

```python
    def test_payload_not_found_error_is_not_a_keyerror(self) -> None:
        """PayloadNotFoundError must NOT be catchable by except KeyError.

        This is the whole point of the domain exception — callers that
        catch KeyError (e.g. for dict lookups) must not accidentally
        swallow a missing-payload condition.
        """
        from elspeth.contracts.payload_store import PayloadNotFoundError

        assert not issubclass(PayloadNotFoundError, KeyError)
        assert not issubclass(PayloadNotFoundError, LookupError)
```

**Step 6: Run type check to confirm export is clean**

Run: `.venv/bin/python -c "from elspeth.contracts import PayloadNotFoundError; print(PayloadNotFoundError)"`
Expected: `<class 'elspeth.contracts.payload_store.PayloadNotFoundError'>`

**Step 7: Commit**

```
(refactor) Add PayloadNotFoundError domain exception to PayloadStore protocol
```

---

## Task 2: Update `FilesystemPayloadStore` implementation and property tests

> **Atomic boundary:** The property test at `tests/property/core/test_payload_store_properties.py` exercises `FilesystemPayloadStore` directly. It MUST be updated in the same commit as the implementation change, or the property test suite will fail (it still expects `KeyError`).

**Files:**
- Modify: `src/elspeth/core/payload_store.py:136-147`
- Modify: `tests/unit/core/test_payload_store.py:57-64`
- Modify: `tests/property/core/test_payload_store_properties.py:175-188`

**Step 1: Write the failing test**

Replace `test_retrieve_nonexistent_raises` (line 57-64) with a single test that checks both exception type and attributes:

```python
    def test_retrieve_nonexistent_raises_payload_not_found_error(self, tmp_path: Path) -> None:
        from elspeth.contracts.payload_store import PayloadNotFoundError
        from elspeth.core.payload_store import FilesystemPayloadStore

        store = FilesystemPayloadStore(base_path=tmp_path)
        fake_hash = "b" * 64

        with pytest.raises(PayloadNotFoundError) as exc_info:
            store.retrieve(fake_hash)

        assert exc_info.value.content_hash == fake_hash
        assert fake_hash in str(exc_info.value)
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/core/test_payload_store.py::TestFilesystemPayloadStore::test_retrieve_nonexistent_raises_payload_not_found_error -v`
Expected: FAIL — `KeyError` raised instead of `PayloadNotFoundError`

**Step 3: Update implementation**

In `src/elspeth/core/payload_store.py`:

Add import near the top (after the existing `from elspeth.contracts import payload_store as payload_contracts` import):
```python
from elspeth.contracts.payload_store import PayloadNotFoundError
```

Change line 147 from:
```python
            raise KeyError(f"Payload not found: {content_hash}") from exc
```
To:
```python
            raise PayloadNotFoundError(content_hash) from exc
```

Update docstring at line 140 from:
```python
            KeyError: If content not found
```
To:
```python
            PayloadNotFoundError: If content not found
```

**Step 4: Update the property test**

The property test at `tests/property/core/test_payload_store_properties.py:175-188` exercises `FilesystemPayloadStore` directly and must be updated in this same commit.

Change `test_retrieve_nonexistent_raises_keyerror` (line 175-188) to:
```python
    def test_retrieve_nonexistent_raises_payload_not_found_error(self, content: bytes) -> None:
        """Property: Retrieving non-existent content raises PayloadNotFoundError.

        The store should not return garbage or empty bytes for
        content that doesn't exist.
        """
        from elspeth.contracts.payload_store import PayloadNotFoundError

        with tempfile.TemporaryDirectory() as tmp_dir:
            store = FilesystemPayloadStore(Path(tmp_dir) / "payloads")

            # Generate hash without storing
            fake_hash = hashlib.sha256(content).hexdigest()

            with pytest.raises(PayloadNotFoundError) as exc_info:
                store.retrieve(fake_hash)

            assert exc_info.value.content_hash == fake_hash
```

**Step 5: Run all store tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/core/test_payload_store.py tests/property/core/test_payload_store_properties.py -v`
Expected: All pass

**Step 6: Commit**

```
(refactor) FilesystemPayloadStore raises PayloadNotFoundError instead of KeyError
```

---

## Task 3: Update `MockPayloadStore` test fixture

**Files:**
- Modify: `tests/fixtures/stores.py:14,33-34`

**Step 1: Update `MockPayloadStore` import at line 14**

Change:
```python
from elspeth.contracts.payload_store import IntegrityError, PayloadStore
```
To:
```python
from elspeth.contracts.payload_store import IntegrityError, PayloadNotFoundError, PayloadStore
```

**Step 2: Update the raise at line 34**

Change:
```python
            raise KeyError(f"Payload not found: {content_hash}")
```
To:
```python
            raise PayloadNotFoundError(content_hash)
```

**Step 3: Run store tests**

Run: `.venv/bin/python -m pytest tests/unit/core/test_payload_store.py tests/property/core/test_payload_store_properties.py -v`
Expected: All pass

**Step 4: Commit**

```
(refactor) MockPayloadStore raises PayloadNotFoundError instead of KeyError
```

---

## Task 4: Update callers — `journal.py`, `recovery.py`, `execution_repository.py`, `query_repository.py`

**Files:**
- Modify: `src/elspeth/core/landscape/journal.py:16,264`
- Modify: `src/elspeth/core/checkpoint/recovery.py:18,254`
- Modify: `src/elspeth/core/landscape/execution_repository.py` (import + line 987)
- Modify: `src/elspeth/core/landscape/query_repository.py:25,150-151,209,526`

### 4a: `journal.py`

The journal currently imports `FilesystemPayloadStore` at line 16. Add the new exception import:
```python
from elspeth.contracts.payload_store import PayloadNotFoundError
```

Change line 264 from:
```python
        except (OSError, KeyError) as exc:
```
To:
```python
        except (OSError, PayloadNotFoundError) as exc:
```

### 4b: `recovery.py`

The recovery module imports from `elspeth.contracts` at line 18. Add `PayloadNotFoundError` to that import:
```python
from elspeth.contracts import Checkpoint, PayloadNotFoundError, PayloadStore, PluginSchema, ResumeCheck, ResumePoint, RowOutcome, RunStatus, SchemaContract
```

Change line 254 from:
```python
            except KeyError as exc:
                raise ValueError(f"Row {row_id} payload has been purged - cannot resume") from exc
```
To:
```python
            except PayloadNotFoundError as exc:
                raise ValueError(f"Row {row_id} payload has been purged (hash={exc.content_hash}) - cannot resume") from exc
```

> **Out of scope:** `recovery.py` line 515 has `except (ValueError, KeyError)` — this catches deserialization errors from `ContractAuditRecord.from_json()`, NOT from payload retrieval. The existing comment at lines 516-518 explains this. Do NOT change it.

### 4c: `execution_repository.py`

Add import (alongside existing contracts imports around line 16):
```python
from elspeth.contracts.payload_store import PayloadNotFoundError
```

Change line 987 from:
```python
        except KeyError:
            return CallDataResult(state=CallDataState.PURGED, data=None)
```
To:
```python
        except PayloadNotFoundError as exc:
            logger.debug("Call response payload purged", content_hash=exc.content_hash, call_id=call_id)
            return CallDataResult(state=CallDataState.PURGED, data=None)
```

### 4d: `query_repository.py`

> **Critical — missed in plan v1.** This file has THREE modification points, not just the docstring. `_retrieve_and_parse_payload()` propagates the exception to two callers that catch `KeyError` directly.

> **Import note:** Lines 25-26 are TWO separate import statements:
> - Line 25: `from elspeth.contracts.payload_store import IntegrityError as PayloadIntegrityError`
> - Line 26: `from elspeth.contracts.payload_store import PayloadStore`
>
> Replace BOTH lines with a single merged import:
```python
from elspeth.contracts.payload_store import IntegrityError as PayloadIntegrityError, PayloadNotFoundError, PayloadStore
```

Update `_retrieve_and_parse_payload()` docstring at line 150-151 from:
```python
            KeyError: Payload was purged by retention policy (caller decides handling)
```
To:
```python
            PayloadNotFoundError: Payload was purged by retention policy (caller decides handling)
```

Update `get_row_data()` at line 209 from:
```python
        except KeyError:
            return RowDataResult(state=RowDataState.PURGED, data=None)
```
To:
```python
        except PayloadNotFoundError as exc:
            logger.debug("Payload purged, returning PURGED state", content_hash=exc.content_hash)
            return RowDataResult(state=RowDataState.PURGED, data=None)
```

Update `explain_row()` at line 526 from:
```python
            except KeyError:
                # Payload purged by retention policy — expected, continue without data
                pass
```
To:
```python
            except PayloadNotFoundError as exc:
                logger.debug("Payload purged, continuing without source data", content_hash=exc.content_hash)
```

**Step: Run all landscape and checkpoint tests**

Run: `.venv/bin/python -m pytest tests/unit/core/landscape/ tests/unit/core/checkpoint/ -v`
Expected: Possible failures in journal tests (they inject `FileNotFoundError`, which is no longer caught for the right reason — see Task 5)

**Step: Commit**

```
(refactor) All PayloadStore callers catch PayloadNotFoundError instead of KeyError
```

---

## Task 5: Fix tests that inject wrong exception types

**Files:**
- Modify: `tests/unit/core/landscape/test_journal.py:551-576`
- Modify: `tests/unit/core/landscape/test_query_methods.py:1546-1556`
- Modify: `tests/integration/audit/test_recorder_row_data.py:102` (stale docstring)


### 5a: Journal tests

The existing journal tests inject `FileNotFoundError` as the mock side effect. This was wrong even before our change — it tested the `OSError` branch, not the `KeyError`/`PayloadNotFoundError` branch. Split into tests for both failure modes.

**Step 1: Replace `test_read_failure_returns_error` (line 551-563) with two tests**

```python
    def test_read_failure_missing_blob_returns_error(self, tmp_path: Path) -> None:
        from elspeth.contracts.payload_store import PayloadNotFoundError

        journal = _make_journal(
            tmp_path,
            include_payloads=True,
            payload_base_path=str(tmp_path / "payloads"),
        )
        journal._payload_store = Mock()
        journal._payload_store.retrieve.side_effect = PayloadNotFoundError("deadbeef" * 8)

        content, error = journal._load_payload("some-ref")
        assert content is None
        assert error is not None
        assert "payload_read_failed" in error

    def test_read_failure_os_error_returns_error(self, tmp_path: Path) -> None:
        journal = _make_journal(
            tmp_path,
            include_payloads=True,
            payload_base_path=str(tmp_path / "payloads"),
        )
        journal._payload_store = Mock()
        journal._payload_store.retrieve.side_effect = OSError("disk failure")

        content, error = journal._load_payload("some-ref")
        assert content is None
        assert error is not None
        assert "payload_read_failed" in error
```

**Step 2: Replace `test_read_failure_with_fail_on_error_raises` (line 565-576) with two tests**

```python
    def test_read_failure_missing_blob_with_fail_on_error_raises(self, tmp_path: Path) -> None:
        from elspeth.contracts.payload_store import PayloadNotFoundError

        journal = _make_journal(
            tmp_path,
            fail_on_error=True,
            include_payloads=True,
            payload_base_path=str(tmp_path / "payloads"),
        )
        journal._payload_store = Mock()
        journal._payload_store.retrieve.side_effect = PayloadNotFoundError("deadbeef" * 8)

        with pytest.raises(PayloadNotFoundError):
            journal._load_payload("some-ref")

    def test_read_failure_os_error_with_fail_on_error_raises(self, tmp_path: Path) -> None:
        journal = _make_journal(
            tmp_path,
            fail_on_error=True,
            include_payloads=True,
            payload_base_path=str(tmp_path / "payloads"),
        )
        journal._payload_store = Mock()
        journal._payload_store.retrieve.side_effect = OSError("disk failure")

        with pytest.raises(OSError):
            journal._load_payload("some-ref")
```

### 5b: Query repository test

The existing test at `test_query_methods.py:1546` injects `KeyError` on the mock. After our change, the real store raises `PayloadNotFoundError`, so the mock must match.

**Step 3: Update `test_purged_payload_returns_lineage_without_data` (line 1546-1556)**

```python
    def test_purged_payload_returns_lineage_without_data(self):
        """PayloadNotFoundError (purged) is the only graceful degradation — not a crash."""
        from elspeth.contracts.payload_store import PayloadNotFoundError

        mock_store = MagicMock()
        mock_store.retrieve.side_effect = PayloadNotFoundError("deadbeef" * 8)
        repo = self._make_repo_with_row(mock_store)

        lineage = repo.explain_row("run-1", "row-1")

        assert lineage is not None
        assert lineage.source_data is None
        assert lineage.payload_available is False
```

### 5c: Add missing `get_row_data` PURGED test

The existing tests only cover `explain_row()` for the PURGED path. `get_row_data()` also catches `PayloadNotFoundError` (at line 209) but has no dedicated test. Add after the existing `test_purged_payload_returns_lineage_without_data`:

```python
    def test_get_row_data_purged_returns_purged_state(self):
        """get_row_data returns PURGED when payload was removed by retention policy."""
        from elspeth.contracts.payload_store import PayloadNotFoundError

        mock_store = MagicMock()
        mock_store.retrieve.side_effect = PayloadNotFoundError("deadbeef" * 8)
        repo = self._make_repo_with_row(mock_store)

        result = repo.get_row_data("row-1")

        assert result.state == RowDataState.PURGED
        assert result.data is None
```

> **Note:** This test uses the same `_make_repo_with_row()` helper (line 1484) as the existing `explain_row` tests. Verify that `RowDataState` and `RowDataResult` are already imported in the test file; if not, add the import.

### 5d: Fix stale integration test docstring

At `tests/integration/audit/test_recorder_row_data.py:102`, the docstring says:
```python
        """Returns PURGED when payload_store raises KeyError."""
```

Change to:
```python
        """Returns PURGED when payload has been deleted (PayloadNotFoundError)."""
```

**Step 4: Run all affected tests**

Run: `.venv/bin/python -m pytest tests/unit/core/landscape/test_journal.py tests/unit/core/landscape/test_query_methods.py tests/integration/audit/test_recorder_row_data.py -v`
Expected: All pass

**Step 5: Commit**

```
(test) Tests inject PayloadNotFoundError — split journal tests by failure mode, add get_row_data PURGED test
```

---

## Task 6: Full test suite and pre-commit validation

**Step 1: Run full unit + property test suite**

Run: `.venv/bin/python -m pytest tests/unit/ tests/property/ -x -q`
Expected: All pass

**Step 2: Run mypy**

Run: `.venv/bin/python -m mypy src/`
Expected: No new errors

**Step 3: Run tier model enforcer**

Run: `.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model`
Expected: Pass (no new violations — `PayloadNotFoundError` is in `contracts/` L0, importable everywhere)

**Step 4: Run ruff**

Run: `.venv/bin/python -m ruff check src/ tests/`
Expected: Clean

**Step 5: Final commit if any fixups needed, then squash or leave as task-by-task history**

---

## Modification Summary

| File | Lines | Change |
|------|-------|--------|
| `contracts/payload_store.py` | 1-8, 21, 53 | Add `PayloadNotFoundError` class, design note, update `retrieve()` docstring |
| `contracts/__init__.py` | 217, 428 | Re-export `PayloadNotFoundError` |
| `core/payload_store.py` | 140, 147 | `raise PayloadNotFoundError(content_hash)`, update docstring |
| `core/landscape/journal.py` | 16, 264 | Import + catch `PayloadNotFoundError` instead of `KeyError` |
| `core/checkpoint/recovery.py` | 18, 254-255 | Import + catch `PayloadNotFoundError`, enrich error message with `content_hash` |
| `core/landscape/execution_repository.py` | imports, 987-988 | Import + catch `PayloadNotFoundError`, add debug log with `content_hash` |
| `core/landscape/query_repository.py` | 25-26, 150-151, 209, 526 | Replace two imports with one merged import + update docstring + **two catch sites** with debug logging |
| `tests/fixtures/stores.py` | 14, 34 | Import + raise `PayloadNotFoundError` |
| `tests/unit/core/test_payload_store.py` | 57-64, new | Replace with `PayloadNotFoundError` test + add hierarchy contract test |
| `tests/property/core/test_payload_store_properties.py` | 175-188 | Expect `PayloadNotFoundError`, assert `content_hash` attribute |
| `tests/unit/core/landscape/test_journal.py` | 551-576 | Split into `PayloadNotFoundError` and `OSError` test variants (graceful + fatal) |
| `tests/unit/core/landscape/test_query_methods.py` | 1546-1556, new | Inject `PayloadNotFoundError` instead of `KeyError`, add `get_row_data` PURGED test |
| `tests/integration/audit/test_recorder_row_data.py` | 102 | Fix stale docstring ("raises KeyError" → "PayloadNotFoundError") |

## Review Feedback Log

| # | Finding | Source | Resolution |
|---|---------|--------|------------|
| 1 | Missing `except KeyError:` at `query_repository.py:209,526` | All 4 reviewers | Added to Task 4d |
| 2 | Missing `_retrieve_and_parse_payload()` docstring update | Architect, Systems | Added to Task 4d |
| 3 | Merge Tasks 3+4 (MockPayloadStore + property tests) | Architect, Systems | Merged into Task 3 |
| 4 | Update mock in `test_purged_payload_returns_lineage_without_data` | QA | Added to Task 5b |
| 5 | Add `OSError + fail_on_error=True` journal test | QA, Python | Added to Task 5a |
| 6 | Add `content_hash` guard in `__init__` | Python | Added to Task 1 |
| 7 | Enrich `recovery.py` error message with `exc.content_hash` | Python | Added to Task 4b |
| 8 | Add `not issubclass(PayloadNotFoundError, KeyError)` contract test | QA | Added to Task 1 |
| 9 | Note `recovery.py:515` is intentionally out of scope | QA | Added to Task 4b |
| 10 | Remove duplicate test (old + new redundant) | Python, QA | Task 2 replaces old test directly |
| 11 | Add design note documenting closed exception set | Systems | Added to Task 1 |
| 12 | Common `PayloadStoreError` base class | Python | Deferred — not justified until a third exception type is needed |
| 13 | Prefer umbrella `contracts` import style | Python | Noted — left to implementer discretion per file |
| 14 | Task 2 commit breaks property tests (intermediate broken state) | Architecture, Systems | Property test moved from Task 3 into Task 2 (v3) |
| 15 | Task 4d import instruction ambiguous (two separate import lines) | Reality | Added explicit note about lines 25-26 being two statements (v3) |
| 16 | No test for `get_row_data` PURGED path | Quality | Added Task 5c (v3) |
| 17 | Property test should assert `content_hash` attribute | Quality | Added assertion to Task 2 property test (v3) |
| 18 | Silent PURGED catch paths discard exception without logging | Quality | Added `logger.debug` to Task 4c and 4d catch sites (v3) |
| 19 | Stale docstring in `test_recorder_row_data.py:102` | Architecture | Added Task 5d (v3) |
| 20 | `IntegrityError` handling inconsistency across repositories | Systems | Pre-existing, out of scope — track as follow-up filigree issue |
| 21 | "Line 21" insertion point ambiguous | Reality | Clarified wording in Task 1 (v3) |
