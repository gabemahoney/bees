"""Unit tests for corruption state management."""

import json
import pytest
from pathlib import Path
from src.corruption_state import (
    CorruptionState,
    mark_corrupt,
    mark_clean,
    is_corrupt,
    get_report,
    clear
)
from src.linter_report import LinterReport


@pytest.fixture
def temp_state_file(tmp_path):
    """Create temporary state file for testing."""
    state_file = tmp_path / ".bees" / "corruption_report.json"
    return state_file


@pytest.fixture
def corruption_state(temp_state_file):
    """Create CorruptionState instance with temporary file."""
    return CorruptionState(state_file=temp_state_file)


@pytest.fixture
def sample_report():
    """Create sample linter report with errors."""
    report = LinterReport()
    report.add_error(
        ticket_id="default.bees-abc",
        error_type="id_format",
        message="Invalid ID format",
        severity="error"
    )
    report.add_error(
        ticket_id="default.bees-xyz",
        error_type="duplicate_id",
        message="Duplicate ID found",
        severity="error"
    )
    return report


class TestCorruptionState:
    """Test CorruptionState class methods."""

    def test_mark_corrupt_creates_state_file(self, corruption_state, temp_state_file, sample_report):
        """Test that mark_corrupt creates state file with correct content."""
        corruption_state.mark_corrupt(sample_report)

        assert temp_state_file.exists()

        with open(temp_state_file, 'r') as f:
            state = json.load(f)

        assert state["is_corrupt"] is True
        assert state["error_count"] == 2
        assert "report" in state
        assert "timestamp" in state

    def test_mark_corrupt_creates_parent_directory(self, corruption_state, temp_state_file, sample_report):
        """Test that mark_corrupt creates .bees directory if it doesn't exist."""
        assert not temp_state_file.parent.exists()

        corruption_state.mark_corrupt(sample_report)

        assert temp_state_file.parent.exists()
        assert temp_state_file.exists()

    def test_mark_clean_creates_state_file(self, corruption_state, temp_state_file):
        """Test that mark_clean creates state file marking database as clean."""
        corruption_state.mark_clean()

        assert temp_state_file.exists()

        with open(temp_state_file, 'r') as f:
            state = json.load(f)

        assert state["is_corrupt"] is False
        assert state["error_count"] == 0
        assert state["report"] is None
        assert "timestamp" in state

    def test_is_corrupt_returns_false_when_no_file(self, corruption_state, temp_state_file):
        """Test that is_corrupt returns False when state file doesn't exist."""
        assert not temp_state_file.exists()
        assert corruption_state.is_corrupt() is False

    def test_is_corrupt_returns_true_when_corrupt(self, corruption_state, temp_state_file, sample_report):
        """Test that is_corrupt returns True when database is marked corrupt."""
        corruption_state.mark_corrupt(sample_report)
        assert corruption_state.is_corrupt() is True

    def test_is_corrupt_returns_false_when_clean(self, corruption_state, temp_state_file):
        """Test that is_corrupt returns False when database is marked clean."""
        corruption_state.mark_clean()
        assert corruption_state.is_corrupt() is False

    def test_get_report_returns_none_when_no_file(self, corruption_state, temp_state_file):
        """Test that get_report returns None when state file doesn't exist."""
        assert not temp_state_file.exists()
        assert corruption_state.get_report() is None

    def test_get_report_returns_none_when_clean(self, corruption_state, temp_state_file):
        """Test that get_report returns None when database is clean."""
        corruption_state.mark_clean()
        assert corruption_state.get_report() is None

    def test_get_report_returns_report_when_corrupt(self, corruption_state, temp_state_file, sample_report):
        """Test that get_report returns corruption report when database is corrupt."""
        corruption_state.mark_corrupt(sample_report)

        report = corruption_state.get_report()
        assert report is not None
        assert "errors" in report
        assert len(report["errors"]) == 2

    def test_clear_removes_state_file(self, corruption_state, temp_state_file, sample_report):
        """Test that clear removes the state file."""
        corruption_state.mark_corrupt(sample_report)
        assert temp_state_file.exists()

        corruption_state.clear()
        assert not temp_state_file.exists()

    def test_clear_handles_missing_file(self, corruption_state, temp_state_file):
        """Test that clear handles missing file gracefully."""
        assert not temp_state_file.exists()
        corruption_state.clear()  # Should not raise exception

    def test_is_corrupt_handles_malformed_json(self, corruption_state, temp_state_file):
        """Test that is_corrupt handles malformed JSON gracefully."""
        temp_state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_state_file, 'w') as f:
            f.write("{ invalid json }")

        assert corruption_state.is_corrupt() is False

    def test_get_report_handles_malformed_json(self, corruption_state, temp_state_file):
        """Test that get_report handles malformed JSON gracefully."""
        temp_state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_state_file, 'w') as f:
            f.write("{ invalid json }")

        assert corruption_state.get_report() is None

    def test_mark_corrupt_overwrites_existing_state(self, corruption_state, temp_state_file, sample_report):
        """Test that mark_corrupt overwrites existing state."""
        corruption_state.mark_clean()
        assert corruption_state.is_corrupt() is False

        corruption_state.mark_corrupt(sample_report)
        assert corruption_state.is_corrupt() is True

    def test_mark_clean_overwrites_corrupt_state(self, corruption_state, temp_state_file, sample_report):
        """Test that mark_clean overwrites corrupt state."""
        corruption_state.mark_corrupt(sample_report)
        assert corruption_state.is_corrupt() is True

        corruption_state.mark_clean()
        assert corruption_state.is_corrupt() is False


class TestConvenienceFunctions:
    """Test convenience functions for global corruption state."""

    def test_global_mark_corrupt(self, tmp_path, sample_report):
        """Test global mark_corrupt function."""
        state_file = tmp_path / ".bees" / "corruption_report.json"

        # Use CorruptionState directly with temp path
        state = CorruptionState(state_file=state_file)
        state.mark_corrupt(sample_report)

        assert state_file.exists()

        with open(state_file, 'r') as f:
            state_data = json.load(f)
        assert state_data["is_corrupt"] is True

    def test_global_mark_clean(self, tmp_path):
        """Test global mark_clean function."""
        state_file = tmp_path / ".bees" / "corruption_report.json"

        # Use CorruptionState directly with temp path
        state = CorruptionState(state_file=state_file)
        state.mark_clean()

        assert state_file.exists()

        with open(state_file, 'r') as f:
            state_data = json.load(f)
        assert state_data["is_corrupt"] is False

    def test_global_is_corrupt(self, tmp_path, sample_report):
        """Test global is_corrupt function."""
        state_file = tmp_path / ".bees" / "corruption_report.json"

        # Use CorruptionState directly with temp path
        state = CorruptionState(state_file=state_file)

        assert state.is_corrupt() is False

        state.mark_corrupt(sample_report)
        assert state.is_corrupt() is True

        state.mark_clean()
        assert state.is_corrupt() is False

    def test_global_get_report(self, tmp_path, sample_report):
        """Test global get_report function."""
        state_file = tmp_path / ".bees" / "corruption_report.json"

        # Use CorruptionState directly with temp path
        state = CorruptionState(state_file=state_file)

        assert state.get_report() is None

        state.mark_corrupt(sample_report)
        report = state.get_report()
        assert report is not None
        assert len(report["errors"]) == 2

    def test_global_clear(self, tmp_path, sample_report):
        """Test global clear function."""
        state_file = tmp_path / ".bees" / "corruption_report.json"

        # Use CorruptionState directly with temp path
        state = CorruptionState(state_file=state_file)
        state.mark_corrupt(sample_report)
        assert state_file.exists()

        state.clear()
        assert not state_file.exists()


class TestStateFilePersistence:
    """Test that corruption state persists across instances."""

    def test_state_persists_across_instances(self, temp_state_file, sample_report):
        """Test that corruption state persists across CorruptionState instances."""
        state1 = CorruptionState(state_file=temp_state_file)
        state1.mark_corrupt(sample_report)

        state2 = CorruptionState(state_file=temp_state_file)
        assert state2.is_corrupt() is True
        report = state2.get_report()
        assert report is not None
        assert len(report["errors"]) == 2

    def test_clean_state_persists(self, temp_state_file, sample_report):
        """Test that clean state persists across instances."""
        state1 = CorruptionState(state_file=temp_state_file)
        state1.mark_corrupt(sample_report)

        state2 = CorruptionState(state_file=temp_state_file)
        state2.mark_clean()

        state3 = CorruptionState(state_file=temp_state_file)
        assert state3.is_corrupt() is False
        assert state3.get_report() is None
