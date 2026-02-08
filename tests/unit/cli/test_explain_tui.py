# tests/unit/cli/test_explain_tui.py
"""Tests for explain command TUI screen state model.

Migrated from tests/cli/test_explain_tui.py.
Tests that require LandscapeDB (screen loading, state transitions with real DB)
are deferred to integration tier.
"""

import pytest

from elspeth.tui.screens.explain_screen import (
    InvalidStateTransitionError,
    UninitializedState,
)


class TestExplainScreen:
    """Tests for ExplainScreen component."""

    def test_can_import_screen(self) -> None:
        """ExplainScreen can be imported."""
        from elspeth.tui.screens.explain_screen import ExplainScreen

        assert ExplainScreen is not None

    def test_explain_screen_has_tree_widget(self) -> None:
        """Explain screen includes LineageTree widget."""
        from elspeth.tui.screens.explain_screen import ExplainScreen

        screen = ExplainScreen()
        widgets = screen.get_widget_types()

        assert "LineageTree" in widgets

    def test_explain_screen_has_detail_panel(self) -> None:
        """Explain screen includes NodeDetailPanel widget."""
        from elspeth.tui.screens.explain_screen import ExplainScreen

        screen = ExplainScreen()
        widgets = screen.get_widget_types()

        assert "NodeDetailPanel" in widgets

    def test_detail_panel_property_accessible(self) -> None:
        """detail_panel property provides public access to NodeDetailPanel."""
        from elspeth.tui.screens.explain_screen import ExplainScreen
        from elspeth.tui.widgets.node_detail import NodeDetailPanel

        screen = ExplainScreen()
        panel = screen.detail_panel

        assert isinstance(panel, NodeDetailPanel)

    def test_render_without_data(self) -> None:
        """Screen renders gracefully without data."""
        from elspeth.tui.screens.explain_screen import ExplainScreen

        screen = ExplainScreen()
        content = screen.render()

        assert "ELSPETH" in content
        assert "No node selected" in content or "Select a node" in content


class TestExplainScreenStateModel:
    """Tests for the discriminated union state model (no DB required)."""

    def test_uninitialized_state_without_db(self) -> None:
        """Screen without db/run_id enters UninitializedState."""
        from elspeth.tui.screens.explain_screen import ExplainScreen

        screen = ExplainScreen()
        assert isinstance(screen.state, UninitializedState)

    def test_clear_from_uninitialized_is_idempotent(self) -> None:
        """clear() from UninitializedState -> UninitializedState (no-op)."""
        from elspeth.tui.screens.explain_screen import ExplainScreen

        screen = ExplainScreen()
        assert isinstance(screen.state, UninitializedState)

        screen.clear()

        assert isinstance(screen.state, UninitializedState)

    def test_retry_from_uninitialized_raises(self) -> None:
        """retry() from UninitializedState raises InvalidStateTransitionError."""
        from elspeth.tui.screens.explain_screen import ExplainScreen

        screen = ExplainScreen()
        assert isinstance(screen.state, UninitializedState)

        with pytest.raises(InvalidStateTransitionError) as exc_info:
            screen.retry()

        assert exc_info.value.method == "retry"
        assert exc_info.value.current_state == "UninitializedState"
        assert "LoadingFailedState" in exc_info.value.allowed_states
