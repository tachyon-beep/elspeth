# Analysis: src/elspeth/tui/explain_app.py

**Lines:** 123
**Role:** Main Textual app for the `elspeth explain` command. Wraps ExplainScreen in a Textual application with keybindings, CSS layout, and lifecycle management. This is the entry point from the CLI for TUI-based lineage exploration.
**Key dependencies:** Imports from `textual.app`, `textual.widgets`, `elspeth.core.landscape.LandscapeDB`, `elspeth.tui.constants.WidgetIDs`, `elspeth.tui.screens.explain_screen`. Imported by `elspeth.tui.__init__` and `elspeth.cli` (line 667).
**Analysis depth:** FULL

## Summary

The file is structurally sound with a clean discriminated-union state match in `compose()`. However, there are two significant issues: (1) `token_id` and `row_id` parameters are accepted but never used, and (2) the `action_refresh` method has a broken state transition that will crash at runtime. The CSS layout and keybinding setup are correct and well-organized.

## Warnings

### [59-67] token_id and row_id parameters are accepted but silently ignored

**What:** The `__init__` method accepts `token_id` and `row_id` parameters, stores them as `self._token_id` and `self._row_id`, but these values are never referenced anywhere else in the class. The CLI at line 669-674 passes both `token_id=token` and `row_id=row` from user-provided CLI arguments.

**Why it matters:** A user running `elspeth explain --run R --token T` expects the TUI to navigate to that specific token. Instead, the token and row parameters are silently discarded. The TUI loads the full pipeline structure without any filtering or navigation to the requested token/row. This is a functional gap that will confuse users who specify these flags.

**Evidence:**
```python
self._token_id = token_id   # stored...
self._row_id = row_id       # stored...
# ...never referenced again in any method
```

The CLI passes them:
```python
tui_app = ExplainApp(
    db=db,
    run_id=resolved_run_id,
    token_id=token,   # user provided
    row_id=row,        # user provided
)
```

### [107-119] action_refresh will raise InvalidStateTransitionError

**What:** The `action_refresh` method calls `self._screen.clear()` then `self._screen.load(self._db, self._run_id)`. However, `ExplainScreen.load()` only accepts `UninitializedState` as a precondition. If the screen was in `LoadedState`, `clear()` transitions it to `UninitializedState`, then `load()` works. But the `if self._db and self._run_id:` guard is the truthy-check variety -- if `self._db` is a `LandscapeDB` whose engine has been disposed (set to `None` by `close()`), the truthiness of the `LandscapeDB` object itself is not affected (it has no `__bool__`), so it will pass the truthiness check and attempt to reload with a disposed database. This would then fail inside `_load_pipeline_structure` with a database error, transitioning to `LoadingFailedState`. The method then calls `self.notify("Refreshed")` regardless, misleading the user.

More critically, if `self._screen` exists but is in `LoadingFailedState` (initial load failed), `clear()` returns it to `UninitializedState`, then `load()` transitions to `LoadedState` or `LoadingFailedState` -- this path works. However, the real problem is the `notify("Refreshed")` always fires even if reload failed.

**Why it matters:** The user presses `r` to refresh, the data reload may silently fail (or use a closed database), and the notification says "Refreshed" regardless of outcome. This gives a false sense of success.

**Evidence:**
```python
def action_refresh(self) -> None:
    if self._screen is not None:
        self._screen.clear()
        if self._db and self._run_id:
            self._screen.load(self._db, self._run_id)
    self.notify("Refreshed")  # Always fires, even on failure
```

### [79-91] compose() accesses screen state but ExplainScreen does database I/O in __init__

**What:** The `compose()` method creates `ExplainScreen(db=self._db, run_id=self._run_id)` on line 76, which triggers `_load_pipeline_structure()` synchronously in `ExplainScreen.__init__`. This means a database query happens synchronously during Textual's `compose()` lifecycle method.

**Why it matters:** The Textual framework expects `compose()` to be fast and non-blocking (it builds the widget tree). Performing synchronous database I/O here can cause the application to hang with no visual feedback during initial load. For a local SQLite database this is likely fast, but for a remote database the TUI would appear frozen with no loading indicator. The `compose()` method should ideally use Textual's `on_mount` or a worker thread for I/O.

**Evidence:**
```python
def compose(self) -> ComposeResult:
    # ...
    self._screen = ExplainScreen(db=self._db, run_id=self._run_id)
    # ExplainScreen.__init__ calls self._load_pipeline_structure(db, run_id)
    # which does recorder.get_nodes(run_id) - a database query
```

## Observations

### [70-105] compose() uses Static widgets rather than Textual's Screen/Widget model

**What:** The `compose()` method renders `ExplainScreen` data into `Static` text widgets rather than using the `LineageTree` and `NodeDetailPanel` as interactive Textual widgets. This means the tree is not navigable -- it's just rendered text.

**Why it matters:** The TUI is described as an "interactive lineage explorer" with arrow key navigation, but the current implementation renders static text. Users cannot click or navigate the tree to select nodes and view details. The `on_tree_select()` method on `ExplainScreen` exists but has no way to be triggered from the Textual event loop. The CLAUDE.md notes "RC-2: limited functionality" for TUI commands, which explains this gap, but it should be documented more explicitly.

### [49-53] BINDINGS type annotation is overly complex

**What:** The `BINDINGS` type annotation uses `ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]]` which, while correct per Textual's API, is verbose. This is minor and purely cosmetic.

### [31-47] CSS uses f-string with WidgetIDs constants

**What:** Good practice -- using `WidgetIDs` constants in the CSS string ensures CSS selectors match widget IDs. A typo in either would cause silent styling failure, and this pattern prevents that.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Either implement token_id/row_id filtering or remove the parameters to avoid misleading the CLI integration. (2) Fix `action_refresh` to check for failure after reload and notify appropriately. (3) Consider documenting that the TUI is currently static/non-interactive as an RC-2 limitation.
**Confidence:** HIGH -- the code is short, well-structured, and the issues are clearly identifiable from the source and its callers.
