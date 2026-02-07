"""Tests for LandscapeJournal retry and recovery behavior."""

import os
from pathlib import Path

import pytest

from elspeth.core.landscape.journal import LandscapeJournal


class TestJournalFailureRecovery:
    """Regression tests for journal silent self-disabling (vts9).

    The original bug: a single write failure permanently disabled the journal
    with just one log message. All subsequent entries were silently dropped.
    """

    def test_single_failure_does_not_permanently_disable(self, tmp_path: Path) -> None:
        """Journal should tolerate individual write failures without permanent shutdown."""
        journal_path = tmp_path / "journal.jsonl"
        journal = LandscapeJournal(str(journal_path), fail_on_error=False)

        # First write succeeds
        journal._append_records([{"test": "record_1"}])
        assert journal_path.read_text().count("\n") == 1

        # Make file read-only to simulate write failure
        journal_path.chmod(0o444)
        try:
            journal._append_records([{"test": "record_2"}])
        finally:
            journal_path.chmod(0o644)

        # Journal should NOT be disabled after a single failure
        assert not journal._disabled
        assert journal._consecutive_failures == 1

        # Next write should succeed (permissions restored)
        journal._append_records([{"test": "record_3"}])
        assert journal._consecutive_failures == 0
        lines = journal_path.read_text().strip().split("\n")
        assert len(lines) == 2  # record_1 and record_3

    def test_disables_after_max_consecutive_failures(self, tmp_path: Path) -> None:
        """Journal should disable after MAX_CONSECUTIVE_FAILURES failures."""
        journal_path = tmp_path / "journal.jsonl"
        journal = LandscapeJournal(str(journal_path), fail_on_error=False)

        # Create the file first, then make it read-only
        journal_path.touch()
        journal_path.chmod(0o444)

        max_failures = LandscapeJournal._MAX_CONSECUTIVE_FAILURES
        try:
            for _ in range(max_failures):
                journal._append_records([{"test": "fail"}])
        finally:
            journal_path.chmod(0o644)

        assert journal._disabled is True
        assert journal._consecutive_failures == max_failures
        assert journal._total_dropped == max_failures

    def test_recovery_attempt_after_100_dropped(self, tmp_path: Path) -> None:
        """Journal should attempt recovery every 100 dropped records."""
        journal_path = tmp_path / "journal.jsonl"
        journal = LandscapeJournal(str(journal_path), fail_on_error=False)

        # Force disabled state with 99 total dropped
        journal._disabled = True
        journal._consecutive_failures = 5
        journal._total_dropped = 99  # Next drop triggers recovery at 100

        # This triggers a recovery attempt (100th dropped record)
        journal._append_records([{"test": "recovery"}])

        # After successful recovery attempt, journal should be working again
        assert not journal._disabled
        assert journal._consecutive_failures == 0
        assert "recovery" in journal_path.read_text()

    @pytest.mark.skipif(os.getuid() == 0, reason="Root can write to read-only files")
    def test_fail_on_error_raises_immediately(self, tmp_path: Path) -> None:
        """With fail_on_error=True, write failures should raise."""
        journal_path = tmp_path / "journal.jsonl"
        journal = LandscapeJournal(str(journal_path), fail_on_error=True)

        journal_path.touch()
        journal_path.chmod(0o444)
        try:
            with pytest.raises(PermissionError):
                journal._append_records([{"test": "fail"}])
        finally:
            journal_path.chmod(0o644)
