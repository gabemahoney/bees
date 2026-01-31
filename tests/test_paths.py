"""Unit tests for path resolution utilities."""

import pytest
from pathlib import Path
from src.paths import (
    get_ticket_directory,
    get_ticket_path,
    ensure_ticket_directory_exists,
    list_tickets,
    infer_ticket_type_from_id,
    TICKETS_DIR
)


class TestGetTicketDirectory:
    """Tests for get_ticket_directory function."""

    def test_epic_directory(self):
        """Should return path to epics subdirectory."""
        path = get_ticket_directory("epic")
        assert path == TICKETS_DIR / "epics"
        assert path.name == "epics"

    def test_task_directory(self):
        """Should return path to tasks subdirectory."""
        path = get_ticket_directory("task")
        assert path == TICKETS_DIR / "tasks"
        assert path.name == "tasks"

    def test_subtask_directory(self):
        """Should return path to subtasks subdirectory."""
        path = get_ticket_directory("subtask")
        assert path == TICKETS_DIR / "subtasks"
        assert path.name == "subtasks"

    def test_invalid_type_raises_error(self):
        """Should raise ValueError for invalid ticket type."""
        with pytest.raises(ValueError, match="Invalid ticket type"):
            get_ticket_directory("invalid")  # type: ignore

    def test_empty_string_raises_error(self):
        """Should raise ValueError for empty string type."""
        with pytest.raises(ValueError):
            get_ticket_directory("")  # type: ignore

    def test_case_sensitive(self):
        """Should be case-sensitive and reject uppercase types."""
        with pytest.raises(ValueError):
            get_ticket_directory("EPIC")  # type: ignore


class TestGetTicketPath:
    """Tests for get_ticket_path function."""

    def test_epic_path(self):
        """Should return correct path for epic ticket."""
        path = get_ticket_path("bees-250", "epic")
        assert path == TICKETS_DIR / "epics" / "bees-250.md"
        assert path.suffix == ".md"

    def test_task_path(self):
        """Should return correct path for task ticket."""
        path = get_ticket_path("bees-jty", "task")
        assert path == TICKETS_DIR / "tasks" / "bees-jty.md"

    def test_subtask_path(self):
        """Should return correct path for subtask ticket."""
        path = get_ticket_path("bees-abc", "subtask")
        assert path == TICKETS_DIR / "subtasks" / "bees-abc.md"

    def test_empty_id_raises_error(self):
        """Should raise ValueError for empty ticket ID."""
        with pytest.raises(ValueError, match="ticket_id cannot be empty"):
            get_ticket_path("", "epic")

    def test_invalid_type_raises_error(self):
        """Should raise ValueError for invalid ticket type."""
        with pytest.raises(ValueError, match="Invalid ticket type"):
            get_ticket_path("bees-250", "invalid")  # type: ignore

    def test_special_characters_in_id(self):
        """Should handle special characters in ticket ID."""
        path = get_ticket_path("bees-x_y-z", "task")
        assert path.name == "bees-x_y-z.md"


class TestEnsureTicketDirectoryExists:
    """Tests for ensure_ticket_directory_exists function."""

    def test_creates_directory_if_missing(self, tmp_path, monkeypatch):
        """Should create directory if it doesn't exist."""
        # Patch TICKETS_DIR to use tmp_path
        monkeypatch.setattr("src.paths.TICKETS_DIR", tmp_path)

        epic_dir = tmp_path / "epics"
        assert not epic_dir.exists()

        ensure_ticket_directory_exists("epic")
        assert epic_dir.exists()
        assert epic_dir.is_dir()

    def test_no_error_if_directory_exists(self, tmp_path, monkeypatch):
        """Should not raise error if directory already exists."""
        monkeypatch.setattr("src.paths.TICKETS_DIR", tmp_path)

        task_dir = tmp_path / "tasks"
        task_dir.mkdir(parents=True)

        # Should not raise
        ensure_ticket_directory_exists("task")
        assert task_dir.exists()

    def test_invalid_type_raises_error(self):
        """Should raise ValueError for invalid ticket type."""
        with pytest.raises(ValueError):
            ensure_ticket_directory_exists("invalid")  # type: ignore


class TestListTickets:
    """Tests for list_tickets function."""

    def test_list_epic_tickets(self, tmp_path, monkeypatch):
        """Should list all epic tickets."""
        monkeypatch.setattr("src.paths.TICKETS_DIR", tmp_path)

        epic_dir = tmp_path / "epics"
        epic_dir.mkdir(parents=True)

        # Create test files
        (epic_dir / "bees-250.md").touch()
        (epic_dir / "bees-abc.md").touch()
        (epic_dir / "not-ticket.txt").touch()  # Should be excluded

        tickets = list_tickets("epic")
        assert len(tickets) == 2
        assert all(t.suffix == ".md" for t in tickets)

    def test_list_all_tickets(self, tmp_path, monkeypatch):
        """Should list tickets from all types when no filter specified."""
        monkeypatch.setattr("src.paths.TICKETS_DIR", tmp_path)

        # Create structure
        for subdir in ["epics", "tasks", "subtasks"]:
            dir_path = tmp_path / subdir
            dir_path.mkdir(parents=True)
            (dir_path / f"bees-{subdir}.md").touch()

        tickets = list_tickets()
        assert len(tickets) == 3

    def test_empty_directory(self, tmp_path, monkeypatch):
        """Should return empty list for empty directory."""
        monkeypatch.setattr("src.paths.TICKETS_DIR", tmp_path)

        subtask_dir = tmp_path / "subtasks"
        subtask_dir.mkdir(parents=True)

        tickets = list_tickets("subtask")
        assert tickets == []

    def test_nonexistent_directory(self, tmp_path, monkeypatch):
        """Should return empty list for nonexistent directory."""
        monkeypatch.setattr("src.paths.TICKETS_DIR", tmp_path)

        # Don't create the directory
        tickets = list_tickets("task")
        assert tickets == []

    def test_sorted_output(self, tmp_path, monkeypatch):
        """Should return tickets in sorted order."""
        monkeypatch.setattr("src.paths.TICKETS_DIR", tmp_path)

        epic_dir = tmp_path / "epics"
        epic_dir.mkdir(parents=True)

        # Create in random order
        (epic_dir / "bees-zzz.md").touch()
        (epic_dir / "bees-aaa.md").touch()
        (epic_dir / "bees-mmm.md").touch()

        tickets = list_tickets("epic")
        names = [t.name for t in tickets]
        assert names == sorted(names)


class TestInferTicketTypeFromId:
    """Tests for infer_ticket_type_from_id function."""

    def test_returns_epic_for_epic_ticket(self, tmp_path, monkeypatch):
        """Should return 'epic' for ticket ID in epics/ directory."""
        monkeypatch.setattr("src.paths.TICKETS_DIR", tmp_path)

        epic_dir = tmp_path / "epics"
        epic_dir.mkdir(parents=True)
        (epic_dir / "bees-250.md").touch()

        ticket_type = infer_ticket_type_from_id("bees-250")
        assert ticket_type == "epic"

    def test_returns_task_for_task_ticket(self, tmp_path, monkeypatch):
        """Should return 'task' for ticket ID in tasks/ directory."""
        monkeypatch.setattr("src.paths.TICKETS_DIR", tmp_path)

        task_dir = tmp_path / "tasks"
        task_dir.mkdir(parents=True)
        (task_dir / "bees-jty.md").touch()

        ticket_type = infer_ticket_type_from_id("bees-jty")
        assert ticket_type == "task"

    def test_returns_subtask_for_subtask_ticket(self, tmp_path, monkeypatch):
        """Should return 'subtask' for ticket ID in subtasks/ directory."""
        monkeypatch.setattr("src.paths.TICKETS_DIR", tmp_path)

        subtask_dir = tmp_path / "subtasks"
        subtask_dir.mkdir(parents=True)
        (subtask_dir / "bees-abc.md").touch()

        ticket_type = infer_ticket_type_from_id("bees-abc")
        assert ticket_type == "subtask"

    def test_returns_none_for_nonexistent_ticket(self, tmp_path, monkeypatch):
        """Should return None for ticket ID that doesn't exist."""
        monkeypatch.setattr("src.paths.TICKETS_DIR", tmp_path)

        # Create directories but no ticket files
        for subdir in ["epics", "tasks", "subtasks"]:
            (tmp_path / subdir).mkdir(parents=True)

        ticket_type = infer_ticket_type_from_id("nonexistent-id")
        assert ticket_type is None

    def test_returns_first_match_for_duplicate_id(self, tmp_path, monkeypatch):
        """Should return first match when ID exists in multiple directories."""
        monkeypatch.setattr("src.paths.TICKETS_DIR", tmp_path)

        # Create same ticket ID in multiple directories (edge case)
        epic_dir = tmp_path / "epics"
        task_dir = tmp_path / "tasks"
        epic_dir.mkdir(parents=True)
        task_dir.mkdir(parents=True)
        (epic_dir / "bees-dup.md").touch()
        (task_dir / "bees-dup.md").touch()

        # Should return 'epic' as it's checked first
        ticket_type = infer_ticket_type_from_id("bees-dup")
        assert ticket_type == "epic"

    def test_returns_none_for_empty_id(self, tmp_path, monkeypatch):
        """Should return None for empty ticket ID."""
        monkeypatch.setattr("src.paths.TICKETS_DIR", tmp_path)

        ticket_type = infer_ticket_type_from_id("")
        assert ticket_type is None

    def test_handles_nonexistent_directories(self, tmp_path, monkeypatch):
        """Should handle case when ticket directories don't exist."""
        monkeypatch.setattr("src.paths.TICKETS_DIR", tmp_path)

        # Don't create any directories
        ticket_type = infer_ticket_type_from_id("bees-123")
        assert ticket_type is None
