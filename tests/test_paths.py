"""Unit tests for path resolution utilities."""

import pytest
from pathlib import Path
from src.paths import (
    get_ticket_directory,
    get_ticket_path,
    ensure_ticket_directory_exists,
    list_tickets,
    infer_ticket_type_from_id,
    _parse_ticket_id_for_path,
)


class TestParseTicketIdForPath:
    """Tests for _parse_ticket_id_for_path function (requires hive-prefixed IDs)."""

    def test_parses_hive_prefixed_id(self):
        """Should parse hive-prefixed ID into hive_name and base_id."""
        hive_name, base_id = _parse_ticket_id_for_path("backend.bees-abc1")
        assert hive_name == "backend"
        assert base_id == "bees-abc1"

    def test_parses_id_with_multiple_dots(self):
        """Should split on first dot only."""
        hive_name, base_id = _parse_ticket_id_for_path("my.hive.bees-xyz")
        assert hive_name == "my"
        assert base_id == "hive.bees-xyz"

    def test_rejects_unprefixed_id(self):
        """Should raise ValueError for unprefixed (legacy) IDs."""
        with pytest.raises(ValueError, match="must have hive prefix"):
            _parse_ticket_id_for_path("bees-abc1")

    def test_rejects_none(self):
        """Should raise ValueError for None."""
        with pytest.raises(ValueError, match="ticket_id cannot be None"):
            _parse_ticket_id_for_path(None)  # type: ignore

    def test_rejects_empty_string(self):
        """Should raise ValueError for empty string."""
        with pytest.raises(ValueError, match="ticket_id cannot be empty"):
            _parse_ticket_id_for_path("")

    def test_rejects_whitespace_only(self):
        """Should raise ValueError for whitespace-only string."""
        with pytest.raises(ValueError, match="ticket_id cannot be empty"):
            _parse_ticket_id_for_path("   ")

    def test_handles_hive_name_with_numbers(self):
        """Should handle hive names containing numbers."""
        hive_name, base_id = _parse_ticket_id_for_path("hive123.bees-abc")
        assert hive_name == "hive123"
        assert base_id == "bees-abc"


class TestGetTicketDirectory:
    """Tests for get_ticket_directory function (deprecated, requires hive_name)."""

    def test_epic_directory_requires_hive_name(self):
        """Should require hive_name parameter."""
        with pytest.raises(ValueError, match="hive_name is required"):
            get_ticket_directory("epic")

    def test_task_directory_requires_hive_name(self):
        """Should require hive_name parameter."""
        with pytest.raises(ValueError, match="hive_name is required"):
            get_ticket_directory("task")

    def test_subtask_directory_requires_hive_name(self):
        """Should require hive_name parameter."""
        with pytest.raises(ValueError, match="hive_name is required"):
            get_ticket_directory("subtask")

    def test_invalid_type_raises_error(self):
        """Should raise ValueError for invalid ticket type."""
        with pytest.raises(ValueError, match="Invalid ticket type"):
            get_ticket_directory("invalid", "backend")  # type: ignore

    def test_empty_string_raises_error(self):
        """Should raise ValueError for empty string type."""
        with pytest.raises(ValueError):
            get_ticket_directory("", "backend")  # type: ignore

    def test_case_sensitive(self):
        """Should be case-sensitive and reject uppercase types."""
        with pytest.raises(ValueError):
            get_ticket_directory("EPIC", "backend")  # type: ignore


class TestGetTicketPath:
    """Tests for get_ticket_path function (requires hive-prefixed IDs)."""

    def test_epic_path_rejects_legacy_id(self):
        """Should reject legacy IDs without hive prefix."""
        with pytest.raises(ValueError, match="must have hive prefix"):
            get_ticket_path("bees-250", "epic")

    def test_task_path_rejects_legacy_id(self):
        """Should reject legacy IDs without hive prefix."""
        with pytest.raises(ValueError, match="must have hive prefix"):
            get_ticket_path("bees-jty", "task")

    def test_subtask_path_rejects_legacy_id(self):
        """Should reject legacy IDs without hive prefix."""
        with pytest.raises(ValueError, match="must have hive prefix"):
            get_ticket_path("bees-abc", "subtask")

    def test_empty_id_raises_error(self):
        """Should raise ValueError for empty ticket ID."""
        with pytest.raises(ValueError, match="ticket_id cannot be empty"):
            get_ticket_path("", "epic")

    def test_invalid_type_raises_error(self):
        """Should raise ValueError for invalid ticket type."""
        with pytest.raises(ValueError, match="Invalid ticket type"):
            get_ticket_path("backend.bees-250", "invalid")  # type: ignore

    def test_special_characters_in_hive_prefixed_id(self, tmp_path, monkeypatch):
        """Should handle hive-prefixed IDs."""
        monkeypatch.chdir(tmp_path)
        path = get_ticket_path("backend.bees-abc", "task")
        assert path == tmp_path / "backend" / "tasks" / "backend.bees-abc.md"


class TestEnsureTicketDirectoryExists:
    """Tests for ensure_ticket_directory_exists function (requires hive_name)."""

    def test_creates_directory_if_missing(self, tmp_path, monkeypatch):
        """Should create directory if it doesn't exist when hive_name provided."""
        monkeypatch.chdir(tmp_path)

        epic_dir = tmp_path / "backend" / "epics"
        assert not epic_dir.exists()

        ensure_ticket_directory_exists("epic", "backend")
        assert epic_dir.exists()
        assert epic_dir.is_dir()

    def test_no_error_if_directory_exists(self, tmp_path, monkeypatch):
        """Should not raise error if directory already exists."""
        monkeypatch.chdir(tmp_path)

        task_dir = tmp_path / "backend" / "tasks"
        task_dir.mkdir(parents=True)

        # Should not raise
        ensure_ticket_directory_exists("task", "backend")
        assert task_dir.exists()

    def test_invalid_type_raises_error(self):
        """Should raise ValueError for invalid ticket type."""
        with pytest.raises(ValueError):
            ensure_ticket_directory_exists("invalid", "backend")  # type: ignore


class TestListTickets:
    """Tests for list_tickets function (scans hives from config)."""

    def test_list_epic_tickets_returns_empty_without_hives(self, tmp_path, monkeypatch):
        """Should return empty list when no hives configured."""
        monkeypatch.chdir(tmp_path)

        # No hives configured
        tickets = list_tickets("epic")
        assert tickets == []

    def test_list_all_tickets_returns_empty_without_hives(self, tmp_path, monkeypatch):
        """Should return empty list when no hives configured."""
        monkeypatch.chdir(tmp_path)

        # No hives configured
        tickets = list_tickets()
        assert tickets == []

    def test_empty_directory(self, tmp_path, monkeypatch):
        """Should return empty list for empty hive directory."""
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        # Create hive with empty directories
        backend_dir = tmp_path / "backend"
        subtask_dir = backend_dir / "subtasks"
        subtask_dir.mkdir(parents=True)

        config = BeesConfig(
            hives={"backend": HiveConfig(path=str(backend_dir), display_name="Backend")}
        )
        save_bees_config(config)

        tickets = list_tickets("subtask")
        assert tickets == []

    def test_nonexistent_directory(self, tmp_path, monkeypatch):
        """Should return empty list when hive path doesn't exist."""
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        # Configure hive with nonexistent path
        config = BeesConfig(
            hives={"backend": HiveConfig(path=str(tmp_path / "nonexistent"), display_name="Backend")}
        )
        save_bees_config(config)

        tickets = list_tickets("task")
        assert tickets == []

    def test_sorted_output(self, tmp_path, monkeypatch):
        """Should return tickets in sorted order."""
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        # Create hive with tickets
        backend_dir = tmp_path / "backend"
        epic_dir = backend_dir / "epics"
        epic_dir.mkdir(parents=True)

        # Create in random order
        (epic_dir / "backend.bees-zzz.md").touch()
        (epic_dir / "backend.bees-aaa.md").touch()
        (epic_dir / "backend.bees-mmm.md").touch()

        config = BeesConfig(
            hives={"backend": HiveConfig(path=str(backend_dir), display_name="Backend")}
        )
        save_bees_config(config)

        tickets = list_tickets("epic")
        names = [t.name for t in tickets]
        assert names == sorted(names)


class TestInferTicketTypeFromId:
    """Tests for infer_ticket_type_from_id function (requires hive-prefixed IDs)."""

    def test_returns_none_for_legacy_epic_ticket(self, tmp_path, monkeypatch):
        """Should return None for legacy IDs without hive prefix."""
        monkeypatch.chdir(tmp_path)

        # Legacy ID format is no longer supported
        ticket_type = infer_ticket_type_from_id("bees-250")
        assert ticket_type is None

    def test_returns_none_for_legacy_task_ticket(self, tmp_path, monkeypatch):
        """Should return None for legacy IDs without hive prefix."""
        monkeypatch.chdir(tmp_path)

        ticket_type = infer_ticket_type_from_id("bees-jty")
        assert ticket_type is None

    def test_returns_none_for_legacy_subtask_ticket(self, tmp_path, monkeypatch):
        """Should return None for legacy IDs without hive prefix."""
        monkeypatch.chdir(tmp_path)

        ticket_type = infer_ticket_type_from_id("bees-abc")
        assert ticket_type is None

    def test_returns_none_for_nonexistent_ticket(self, tmp_path, monkeypatch):
        """Should return None for ticket ID that doesn't exist."""
        monkeypatch.chdir(tmp_path)

        # Create hive directories but no ticket files
        backend_dir = tmp_path / "backend"
        for subdir in ["epics", "tasks", "subtasks"]:
            (backend_dir / subdir).mkdir(parents=True)

        ticket_type = infer_ticket_type_from_id("backend.nonexistent-id")
        assert ticket_type is None

    def test_returns_first_match_for_duplicate_id(self, tmp_path, monkeypatch):
        """Should return first match when ID exists in multiple directories."""
        monkeypatch.chdir(tmp_path)

        # Create same ticket ID in multiple directories (edge case)
        backend_dir = tmp_path / "backend"
        epic_dir = backend_dir / "epics"
        task_dir = backend_dir / "tasks"
        epic_dir.mkdir(parents=True)
        task_dir.mkdir(parents=True)
        (epic_dir / "backend.bees-dup.md").touch()
        (task_dir / "backend.bees-dup.md").touch()

        # Should return 'epic' as it's checked first
        ticket_type = infer_ticket_type_from_id("backend.bees-dup")
        assert ticket_type == "epic"

    def test_returns_none_for_empty_id(self, tmp_path, monkeypatch):
        """Should return None for empty ticket ID."""
        monkeypatch.chdir(tmp_path)

        ticket_type = infer_ticket_type_from_id("")
        assert ticket_type is None

    def test_handles_nonexistent_directories(self, tmp_path, monkeypatch):
        """Should handle case when ticket directories don't exist."""
        monkeypatch.chdir(tmp_path)

        # Legacy ID - should return None
        ticket_type = infer_ticket_type_from_id("bees-123")
        assert ticket_type is None


class TestLegacyIDRejection:
    """Tests for legacy unprefixed ID rejection after TICKETS_DIR removal."""

    def test_get_ticket_path_rejects_legacy_id(self):
        """Should reject legacy IDs without hive prefix in get_ticket_path()."""
        with pytest.raises(ValueError, match="must have hive prefix"):
            get_ticket_path("bees-250", "epic")

    def test_get_ticket_path_accepts_hive_prefixed_id(self, tmp_path, monkeypatch):
        """Should accept hive-prefixed IDs in get_ticket_path()."""
        # Mock current working directory
        monkeypatch.chdir(tmp_path)

        # Create hive directory structure
        hive_dir = tmp_path / "backend"
        epic_dir = hive_dir / "epics"
        epic_dir.mkdir(parents=True)

        # Should not raise
        path = get_ticket_path("backend.bees-250", "epic")
        assert path == hive_dir / "epics" / "backend.bees-250.md"

    def test_infer_ticket_type_returns_none_for_legacy_id(self):
        """Should return None for legacy IDs without hive prefix in infer_ticket_type_from_id()."""
        ticket_type = infer_ticket_type_from_id("bees-250")
        assert ticket_type is None

    def test_infer_ticket_type_works_for_hive_prefixed_id(self, tmp_path, monkeypatch):
        """Should work for hive-prefixed IDs in infer_ticket_type_from_id()."""
        # Mock current working directory
        monkeypatch.chdir(tmp_path)

        # Create hive directory with ticket
        hive_dir = tmp_path / "backend"
        epic_dir = hive_dir / "epics"
        epic_dir.mkdir(parents=True)
        (epic_dir / "backend.bees-250.md").touch()

        ticket_type = infer_ticket_type_from_id("backend.bees-250")
        assert ticket_type == "epic"

    def test_get_ticket_directory_requires_hive_name(self):
        """Should require hive_name parameter in get_ticket_directory()."""
        with pytest.raises(ValueError, match="hive_name is required"):
            get_ticket_directory("epic")

    def test_get_ticket_directory_works_with_hive_name(self, tmp_path, monkeypatch):
        """Should work when hive_name is provided in get_ticket_directory()."""
        monkeypatch.chdir(tmp_path)

        path = get_ticket_directory("epic", "backend")
        assert path == tmp_path / "backend" / "epics"

    def test_ensure_ticket_directory_requires_hive_name(self):
        """Should require hive_name parameter in ensure_ticket_directory_exists()."""
        with pytest.raises(ValueError, match="hive_name is required"):
            ensure_ticket_directory_exists("epic")

    def test_ensure_ticket_directory_works_with_hive_name(self, tmp_path, monkeypatch):
        """Should work when hive_name is provided in ensure_ticket_directory_exists()."""
        monkeypatch.chdir(tmp_path)

        epic_dir = tmp_path / "backend" / "epics"
        assert not epic_dir.exists()

        ensure_ticket_directory_exists("epic", "backend")
        assert epic_dir.exists()
        assert epic_dir.is_dir()


class TestListTicketsFromHives:
    """Tests for list_tickets() scanning all hives."""

    def test_list_tickets_scans_all_hives(self, tmp_path, monkeypatch):
        """Should scan all configured hives when listing tickets."""
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        # Create hive directories
        backend_dir = tmp_path / "backend"
        frontend_dir = tmp_path / "frontend"

        backend_epics = backend_dir / "epics"
        frontend_tasks = frontend_dir / "tasks"
        backend_epics.mkdir(parents=True)
        frontend_tasks.mkdir(parents=True)

        # Create tickets
        (backend_epics / "backend.bees-abc.md").touch()
        (frontend_tasks / "frontend.bees-xyz.md").touch()

        # Configure hives
        config = BeesConfig(
            hives={
                "backend": HiveConfig(path=str(backend_dir), display_name="Backend"),
                "frontend": HiveConfig(path=str(frontend_dir), display_name="Frontend"),
            }
        )
        save_bees_config(config)

        # List all tickets
        tickets = list_tickets()
        assert len(tickets) == 2
        ticket_names = {t.name for t in tickets}
        assert "backend.bees-abc.md" in ticket_names
        assert "frontend.bees-xyz.md" in ticket_names

    def test_list_tickets_filters_by_type(self, tmp_path, monkeypatch):
        """Should filter by ticket type when listing from hives."""
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        # Create hive directory
        backend_dir = tmp_path / "backend"
        backend_epics = backend_dir / "epics"
        backend_tasks = backend_dir / "tasks"
        backend_epics.mkdir(parents=True)
        backend_tasks.mkdir(parents=True)

        # Create tickets of different types
        (backend_epics / "backend.bees-epic1.md").touch()
        (backend_tasks / "backend.bees-task1.md").touch()

        # Configure hives
        config = BeesConfig(
            hives={"backend": HiveConfig(path=str(backend_dir), display_name="Backend")}
        )
        save_bees_config(config)

        # List only epics
        epics = list_tickets("epic")
        assert len(epics) == 1
        assert epics[0].name == "backend.bees-epic1.md"

    def test_list_tickets_returns_empty_when_no_hives(self, tmp_path, monkeypatch):
        """Should return empty list when no hives are configured."""
        monkeypatch.chdir(tmp_path)

        # No hives configured - list_tickets should return empty
        tickets = list_tickets()
        assert tickets == []
