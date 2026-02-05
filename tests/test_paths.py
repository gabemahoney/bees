"""Unit tests for path resolution utilities."""

import pytest
from pathlib import Path
from datetime import datetime
from src.paths import (
    get_ticket_path,
    ensure_ticket_directory_exists,
    list_tickets,
    infer_ticket_type_from_id,
)
from src.mcp_id_utils import parse_ticket_id
from src.config import BeesConfig, HiveConfig, save_bees_config
from src.repo_context import repo_root_context


@pytest.fixture
def setup_hive_config(tmp_path, monkeypatch):
    """Create hive configuration with backend and frontend hives."""
    monkeypatch.chdir(tmp_path)

    # Create hive directories
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    # Initialize .bees/config.json and maintain context for test execution
    with repo_root_context(tmp_path):
        config = BeesConfig(
            hives={
                'backend': HiveConfig(
                    path=str(backend_dir),
                    display_name='Backend',
                    created_at=datetime.now().isoformat()
                ),
                'frontend': HiveConfig(
                    path=str(frontend_dir),
                    display_name='Frontend',
                    created_at=datetime.now().isoformat()
                ),
            },
            allow_cross_hive_dependencies=True,
            schema_version='1.0'
        )
        save_bees_config(config)
        
        yield tmp_path


class TestParseTicketId:
    """Tests for parse_ticket_id function from mcp_id_utils (used by paths.py)."""

    def test_parses_hive_prefixed_id(self):
        """Should parse hive-prefixed ID into hive_name and base_id."""
        hive_name, base_id = parse_ticket_id("backend.bees-abc1")
        assert hive_name == "backend"
        assert base_id == "bees-abc1"

    def test_parses_id_with_multiple_dots(self):
        """Should split on first dot only."""
        hive_name, base_id = parse_ticket_id("my.hive.bees-xyz")
        assert hive_name == "my"
        assert base_id == "hive.bees-xyz"

    def test_accepts_unprefixed_id(self):
        """Should accept unprefixed (legacy) IDs and return empty hive_name."""
        hive_name, base_id = parse_ticket_id("bees-abc1")
        assert hive_name == ""
        assert base_id == "bees-abc1"

    def test_rejects_none(self):
        """Should raise ValueError for None."""
        with pytest.raises(ValueError, match="ticket_id cannot be None"):
            parse_ticket_id(None)  # type: ignore

    def test_rejects_empty_string(self):
        """Should raise ValueError for empty string."""
        with pytest.raises(ValueError, match="ticket_id cannot be empty"):
            parse_ticket_id("")

    def test_rejects_whitespace_only(self):
        """Should raise ValueError for whitespace-only string."""
        with pytest.raises(ValueError, match="ticket_id cannot be empty"):
            parse_ticket_id("   ")

    def test_handles_hive_name_with_numbers(self):
        """Should handle hive names containing numbers."""
        hive_name, base_id = parse_ticket_id("hive123.bees-abc")
        assert hive_name == "hive123"
        assert base_id == "bees-abc"


class TestPathsFunctionsWithRefactoredParsing:
    """Tests for paths.py functions after refactoring to use mcp_id_utils.parse_ticket_id()."""

    def test_get_ticket_path_validates_hive_prefix(self, tmp_path, monkeypatch):
        """get_ticket_path() should validate hive prefix after calling parse_ticket_id()."""
        from datetime import datetime
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        # Create hive configuration
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)
        with repo_root_context(tmp_path):
            config = BeesConfig(
                hives={"backend": HiveConfig(path=str(backend_dir), display_name="Backend", created_at=datetime.now().isoformat())}
            )
            save_bees_config(config)

            # Should accept hive-prefixed ID
            path = get_ticket_path("backend.bees-abc1", "epic")
            assert path == backend_dir / "backend.bees-abc1.md"

            # Should reject unprefixed ID
            with pytest.raises(ValueError, match="must have hive prefix"):
                get_ticket_path("bees-abc1", "epic")

    def test_infer_ticket_type_validates_hive_prefix(self, tmp_path, monkeypatch):
        """infer_ticket_type_from_id() should validate hive prefix after calling parse_ticket_id()."""
        from datetime import datetime
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        # Create hive configuration with ticket
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)
        with repo_root_context(tmp_path):
            config = BeesConfig(
                hives={"backend": HiveConfig(path=str(backend_dir), display_name="Backend", created_at=datetime.now().isoformat())}
            )
            save_bees_config(config)

            (backend_dir / "backend.bees-abc1.md").write_text("---\nbees_version: 1.1\ntype: epic\n---\n")

            # Should accept hive-prefixed ID
            ticket_type = infer_ticket_type_from_id("backend.bees-abc1")
            assert ticket_type == "epic"

            # Should return None for unprefixed ID (not raise error)
            ticket_type = infer_ticket_type_from_id("bees-abc1")
            assert ticket_type is None

    def test_get_ticket_path_handles_parse_errors(self):
        """get_ticket_path() should handle ValueError from parse_ticket_id()."""
        # Empty string should raise ValueError
        with pytest.raises(ValueError, match="ticket_id cannot be empty"):
            get_ticket_path("", "epic")

    def test_infer_ticket_type_handles_parse_errors(self):
        """infer_ticket_type_from_id() should handle ValueError from parse_ticket_id()."""
        # Empty string should return None
        ticket_type = infer_ticket_type_from_id("")
        assert ticket_type is None


class TestGetTicketPath:
    """Tests for get_ticket_path function (requires hive-prefixed IDs after refactoring)."""

    def test_epic_path_rejects_legacy_id(self):
        """Should reject legacy IDs without hive prefix (validation added after parse_ticket_id)."""
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

    def test_accepts_any_ticket_type(self, setup_hive_config):
        """Should accept any ticket type (validation removed in flat storage)."""
        # In flat storage, ticket_type doesn't affect path
        path = get_ticket_path("backend.bees-250", "invalid")  # type: ignore
        # Should not raise, path is always the same
        assert path == setup_hive_config / "backend" / "backend.bees-250.md"

    def test_flat_storage_path_for_epic(self, setup_hive_config):
        """Should return flat storage path in hive root for epic."""
        path = get_ticket_path("backend.bees-abc", "epic")
        assert path == setup_hive_config / "backend" / "backend.bees-abc.md"

    def test_flat_storage_path_for_task(self, setup_hive_config):
        """Should return flat storage path in hive root for task."""
        path = get_ticket_path("backend.bees-xyz", "task")
        assert path == setup_hive_config / "backend" / "backend.bees-xyz.md"

    def test_flat_storage_path_for_subtask(self, setup_hive_config):
        """Should return flat storage path in hive root for subtask."""
        path = get_ticket_path("frontend.bees-123", "subtask")
        assert path == setup_hive_config / "frontend" / "frontend.bees-123.md"

    def test_flat_storage_ignores_ticket_type(self, setup_hive_config):
        """Should return same path regardless of ticket type (flat storage)."""
        epic_path = get_ticket_path("backend.bees-abc", "epic")
        task_path = get_ticket_path("backend.bees-abc", "task")
        subtask_path = get_ticket_path("backend.bees-abc", "subtask")
        # All paths should be identical in flat storage
        assert epic_path == task_path == subtask_path
        assert epic_path == setup_hive_config / "backend" / "backend.bees-abc.md"


class TestEnsureTicketDirectoryExists:
    """Tests for ensure_ticket_directory_exists function (flat storage)."""

    def test_creates_directory_if_missing(self, tmp_path, monkeypatch):
        """Should create hive root directory if it doesn't exist."""
        monkeypatch.chdir(tmp_path)

        hive_dir = tmp_path / "backend"
        assert not hive_dir.exists()

        ensure_ticket_directory_exists("backend")
        assert hive_dir.exists()
        assert hive_dir.is_dir()

    def test_no_error_if_directory_exists(self, tmp_path, monkeypatch):
        """Should not raise error if directory already exists."""
        monkeypatch.chdir(tmp_path)

        hive_dir = tmp_path / "backend"
        hive_dir.mkdir(parents=True)

        # Should not raise
        ensure_ticket_directory_exists("backend")
        assert hive_dir.exists()

    def test_invalid_hive_name_raises_error(self):
        """Should raise ValueError for empty hive name."""
        with pytest.raises(ValueError, match="hive_name is required"):
            ensure_ticket_directory_exists("")


class TestListTickets:
    """Tests for list_tickets function (scans hives from config)."""

    def test_list_epic_tickets_returns_empty_without_hives(self, tmp_path, monkeypatch):
        """Should return empty list when no hives configured."""
        monkeypatch.chdir(tmp_path)

        # No hives configured
        with repo_root_context(tmp_path):
            tickets = list_tickets("epic")
            assert tickets == []

    def test_list_all_tickets_returns_empty_without_hives(self, tmp_path, monkeypatch):
        """Should return empty list when no hives configured."""
        monkeypatch.chdir(tmp_path)

        # No hives configured
        with repo_root_context(tmp_path):
            tickets = list_tickets()
            assert tickets == []

    def test_empty_directory(self, tmp_path, monkeypatch):
        """Should return empty list for empty hive directory (flat storage)."""
        from datetime import datetime
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        # Create empty hive root directory
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)

        with repo_root_context(tmp_path):
            config = BeesConfig(
                hives={"backend": HiveConfig(path=str(backend_dir), display_name="Backend", created_at=datetime.now().isoformat())}
            )
            save_bees_config(config)

            tickets = list_tickets("subtask")
            assert tickets == []

    def test_nonexistent_directory(self, tmp_path, monkeypatch):
        """Should return empty list when hive path doesn't exist."""
        from datetime import datetime
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        # Configure hive with nonexistent path
        with repo_root_context(tmp_path):
            config = BeesConfig(
                hives={"backend": HiveConfig(path=str(tmp_path / "nonexistent"), display_name="Backend", created_at=datetime.now().isoformat())}
            )
            save_bees_config(config)

            tickets = list_tickets("task")
            assert tickets == []

    def test_sorted_output(self, tmp_path, monkeypatch):
        """Should return tickets in sorted order (flat storage)."""
        from datetime import datetime
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        # Create hive with tickets in root directory
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)

        # Create in random order with YAML frontmatter
        (backend_dir / "backend.bees-zzz.md").write_text("---\ntype: epic\n---\n")
        (backend_dir / "backend.bees-aaa.md").write_text("---\ntype: epic\n---\n")
        (backend_dir / "backend.bees-mmm.md").write_text("---\ntype: epic\n---\n")

        with repo_root_context(tmp_path):
            config = BeesConfig(
                hives={"backend": HiveConfig(path=str(backend_dir), display_name="Backend", created_at=datetime.now().isoformat())}
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
        with repo_root_context(tmp_path):
            ticket_type = infer_ticket_type_from_id("bees-250")
            assert ticket_type is None

    def test_returns_none_for_legacy_task_ticket(self, tmp_path, monkeypatch):
        """Should return None for legacy IDs without hive prefix."""
        monkeypatch.chdir(tmp_path)

        with repo_root_context(tmp_path):
            ticket_type = infer_ticket_type_from_id("bees-jty")
            assert ticket_type is None

    def test_returns_none_for_legacy_subtask_ticket(self, tmp_path, monkeypatch):
        """Should return None for legacy IDs without hive prefix."""
        monkeypatch.chdir(tmp_path)

        with repo_root_context(tmp_path):
            ticket_type = infer_ticket_type_from_id("bees-abc")
            assert ticket_type is None

    def test_returns_none_for_nonexistent_ticket(self, tmp_path, monkeypatch):
        """Should return None for ticket ID that doesn't exist."""
        monkeypatch.chdir(tmp_path)

        # Create hive directory but no ticket files
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)

        with repo_root_context(tmp_path):
            ticket_type = infer_ticket_type_from_id("backend.nonexistent-id")
            assert ticket_type is None

    def test_infers_epic_from_yaml_frontmatter(self, setup_hive_config):
        """Should infer type 'epic' from YAML frontmatter in flat storage."""
        backend_dir = setup_hive_config / "backend"

        ticket_file = backend_dir / "backend.bees-abc.md"
        ticket_file.write_text("---\nbees_version: 1.1\ntype: epic\ntitle: Test Epic\n---\n\nBody content")

        ticket_type = infer_ticket_type_from_id("backend.bees-abc")
        assert ticket_type == "epic"

    def test_infers_task_from_yaml_frontmatter(self, setup_hive_config):
        """Should infer type 'task' from YAML frontmatter in flat storage."""
        backend_dir = setup_hive_config / "backend"

        ticket_file = backend_dir / "backend.bees-xyz.md"
        ticket_file.write_text("---\nbees_version: 1.1\ntype: task\ntitle: Test Task\n---\n\nBody content")

        ticket_type = infer_ticket_type_from_id("backend.bees-xyz")
        assert ticket_type == "task"

    def test_infers_subtask_from_yaml_frontmatter(self, setup_hive_config):
        """Should infer type 'subtask' from YAML frontmatter in flat storage."""
        frontend_dir = setup_hive_config / "frontend"

        ticket_file = frontend_dir / "frontend.bees-123.md"
        ticket_file.write_text("---\nbees_version: 1.1\ntype: subtask\ntitle: Test Subtask\n---\n\nBody content")

        ticket_type = infer_ticket_type_from_id("frontend.bees-123")
        assert ticket_type == "subtask"

    def test_returns_none_for_invalid_yaml(self, tmp_path, monkeypatch):
        """Should return None when YAML frontmatter is invalid."""
        monkeypatch.chdir(tmp_path)

        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)

        ticket_file = backend_dir / "backend.bees-bad.md"
        ticket_file.write_text("---\n[invalid: yaml: content\n---\n\nBody")

        with repo_root_context(tmp_path):
            ticket_type = infer_ticket_type_from_id("backend.bees-bad")
            assert ticket_type is None

    def test_returns_none_for_missing_type_field(self, tmp_path, monkeypatch):
        """Should return None when type field is missing from YAML."""
        monkeypatch.chdir(tmp_path)

        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)

        ticket_file = backend_dir / "backend.bees-notype.md"
        ticket_file.write_text("---\ntitle: Test\n---\n\nBody content")

        with repo_root_context(tmp_path):
            ticket_type = infer_ticket_type_from_id("backend.bees-notype")
            assert ticket_type is None

    def test_returns_none_for_empty_id(self, tmp_path, monkeypatch):
        """Should return None for empty ticket ID."""
        monkeypatch.chdir(tmp_path)

        with repo_root_context(tmp_path):
            ticket_type = infer_ticket_type_from_id("")
            assert ticket_type is None

    def test_handles_nonexistent_directories(self, tmp_path, monkeypatch):
        """Should handle case when ticket directories don't exist."""
        monkeypatch.chdir(tmp_path)

        # Legacy ID - should return None
        with repo_root_context(tmp_path):
            ticket_type = infer_ticket_type_from_id("bees-123")
            assert ticket_type is None

    def test_returns_none_for_missing_bees_version(self, tmp_path, monkeypatch):
        """Should return None when bees_version field is missing from YAML."""
        monkeypatch.chdir(tmp_path)

        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)

        ticket_file = backend_dir / "backend.bees-noversion.md"
        ticket_file.write_text("---\ntype: epic\ntitle: Test\n---\n\nBody content")

        with repo_root_context(tmp_path):
            ticket_type = infer_ticket_type_from_id("backend.bees-noversion")
            assert ticket_type is None

    def test_validates_bees_version_before_type(self, tmp_path, monkeypatch):
        """Should validate bees_version field before returning type."""
        from datetime import datetime
        from src.config import BeesConfig, HiveConfig, save_bees_config
        import json

        monkeypatch.chdir(tmp_path)

        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)

        # Create hive configuration
        with repo_root_context(tmp_path):
            config = BeesConfig(
                hives={"backend": HiveConfig(path=str(backend_dir), display_name="Backend", created_at=datetime.now().isoformat())}
            )
            save_bees_config(config)

            # Valid ticket with both bees_version and type
            ticket_file = backend_dir / "backend.bees-valid.md"
            ticket_file.write_text("---\nbees_version: 1.1\ntype: task\ntitle: Test\n---\n\nBody content")

            ticket_type = infer_ticket_type_from_id("backend.bees-valid")
            assert ticket_type == "task"


class TestLegacyIDRejection:
    """Tests for legacy unprefixed ID rejection after TICKETS_DIR removal."""

    def test_get_ticket_path_rejects_legacy_id(self):
        """Should reject legacy IDs without hive prefix in get_ticket_path()."""
        with pytest.raises(ValueError, match="must have hive prefix"):
            get_ticket_path("bees-250", "epic")

    def test_get_ticket_path_accepts_hive_prefixed_id(self, tmp_path, monkeypatch):
        """Should accept hive-prefixed IDs in get_ticket_path() with flat storage."""
        from datetime import datetime
        from src.config import BeesConfig, HiveConfig, save_bees_config
        import json

        # Mock current working directory
        monkeypatch.chdir(tmp_path)

        # Create hive root directory (flat storage)
        hive_dir = tmp_path / "backend"
        hive_dir.mkdir(parents=True)

        # Create hive configuration
        with repo_root_context(tmp_path):
            config = BeesConfig(
                hives={"backend": HiveConfig(path=str(hive_dir), display_name="Backend", created_at=datetime.now().isoformat())}
            )
            save_bees_config(config)

            # Should not raise
            path = get_ticket_path("backend.bees-250", "epic")
            assert path == hive_dir / "backend.bees-250.md"

    def test_infer_ticket_type_returns_none_for_legacy_id(self):
        """Should return None for legacy IDs without hive prefix in infer_ticket_type_from_id()."""
        ticket_type = infer_ticket_type_from_id("bees-250")
        assert ticket_type is None

    def test_infer_ticket_type_works_for_hive_prefixed_id(self, tmp_path, monkeypatch):
        """Should work for hive-prefixed IDs in infer_ticket_type_from_id() with flat storage."""
        from datetime import datetime
        from src.config import BeesConfig, HiveConfig, save_bees_config
        import json

        # Mock current working directory
        monkeypatch.chdir(tmp_path)

        # Create hive root directory with ticket (flat storage)
        hive_dir = tmp_path / "backend"
        hive_dir.mkdir(parents=True)

        # Create hive configuration
        with repo_root_context(tmp_path):
            config = BeesConfig(
                hives={"backend": HiveConfig(path=str(hive_dir), display_name="Backend", created_at=datetime.now().isoformat())}
            )
            save_bees_config(config)

            (hive_dir / "backend.bees-250.md").write_text("---\nbees_version: 1.1\ntype: epic\n---\n")

            ticket_type = infer_ticket_type_from_id("backend.bees-250")
            assert ticket_type == "epic"

    def test_ensure_ticket_directory_requires_hive_name(self):
        """Should require hive_name parameter in ensure_ticket_directory_exists()."""
        with pytest.raises(ValueError, match="hive_name is required"):
            ensure_ticket_directory_exists("")

    def test_ensure_ticket_directory_works_with_hive_name(self, tmp_path, monkeypatch):
        """Should work when hive_name is provided in ensure_ticket_directory_exists()."""
        monkeypatch.chdir(tmp_path)

        hive_dir = tmp_path / "backend"
        assert not hive_dir.exists()

        ensure_ticket_directory_exists("backend")
        assert hive_dir.exists()
        assert hive_dir.is_dir()


class TestFlatStorageArchitecture:
    """Tests for flat storage architecture (bees_version 1.1)."""

    def test_get_ticket_path_returns_root_path(self, tmp_path, monkeypatch):
        """get_ticket_path() should return path in hive root, not subdirectory."""
        from datetime import datetime
        from src.config import BeesConfig, HiveConfig, save_bees_config
        import json

        monkeypatch.chdir(tmp_path)

        # Create hive directory and configuration
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)

        with repo_root_context(tmp_path):
            config = BeesConfig(
                hives={"backend": HiveConfig(path=str(backend_dir), display_name="Backend", created_at=datetime.now().isoformat())}
            )
            save_bees_config(config)

            path = get_ticket_path("backend.bees-abc", "epic")
            assert path == tmp_path / "backend" / "backend.bees-abc.md"

            # Should be same path regardless of ticket type
            path_task = get_ticket_path("backend.bees-abc", "task")
            assert path == path_task

    def test_infer_ticket_type_reads_yaml(self, tmp_path, monkeypatch):
        """infer_ticket_type_from_id() should read type from YAML frontmatter."""
        from datetime import datetime
        from src.config import BeesConfig, HiveConfig, save_bees_config
        import json

        monkeypatch.chdir(tmp_path)

        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)

        # Create hive configuration
        with repo_root_context(tmp_path):
            config = BeesConfig(
                hives={"backend": HiveConfig(path=str(backend_dir), display_name="Backend", created_at=datetime.now().isoformat())}
            )
            save_bees_config(config)

            # Create ticket with epic type in YAML
            ticket_file = backend_dir / "backend.bees-test.md"
            ticket_file.write_text("---\nbees_version: 1.1\ntype: task\ntitle: Test\n---\n\nBody")

            ticket_type = infer_ticket_type_from_id("backend.bees-test")
            assert ticket_type == "task"

    def test_ensure_directory_creates_root_only(self, tmp_path, monkeypatch):
        """ensure_ticket_directory_exists() should create hive root only."""
        monkeypatch.chdir(tmp_path)

        backend_dir = tmp_path / "backend"
        assert not backend_dir.exists()

        ensure_ticket_directory_exists("backend")

        assert backend_dir.exists()
        assert backend_dir.is_dir()
        # Should not create subdirectories
        assert not (backend_dir / "epics").exists()
        assert not (backend_dir / "tasks").exists()
        assert not (backend_dir / "subtasks").exists()

    def test_list_tickets_scans_root(self, tmp_path, monkeypatch):
        """list_tickets() should scan hive root directory."""
        from datetime import datetime
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)

        # Create tickets in root with different types
        (backend_dir / "backend.bees-epic1.md").write_text("---\nbees_version: 1.1\ntype: epic\n---\n")
        (backend_dir / "backend.bees-task1.md").write_text("---\nbees_version: 1.1\ntype: task\n---\n")
        (backend_dir / "backend.bees-subtask1.md").write_text("---\nbees_version: 1.1\ntype: subtask\n---\n")

        with repo_root_context(tmp_path):
            config = BeesConfig(
                hives={"backend": HiveConfig(path=str(backend_dir), display_name="Backend", created_at=datetime.now().isoformat())}
            )
            save_bees_config(config)

            # List all tickets
            all_tickets = list_tickets()
            assert len(all_tickets) == 3

            # List by type
            epics = list_tickets("epic")
            assert len(epics) == 1
            assert epics[0].name == "backend.bees-epic1.md"

            tasks = list_tickets("task")
            assert len(tasks) == 1
            assert tasks[0].name == "backend.bees-task1.md"


class TestListTicketsFromHives:
    """Tests for list_tickets() scanning all hives."""

    def test_list_tickets_scans_all_hives(self, tmp_path, monkeypatch):
        """Should scan all configured hives when listing tickets (flat storage)."""
        from datetime import datetime
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        # Create hive root directories
        backend_dir = tmp_path / "backend"
        frontend_dir = tmp_path / "frontend"
        backend_dir.mkdir(parents=True)
        frontend_dir.mkdir(parents=True)

        # Create tickets in root with YAML frontmatter
        (backend_dir / "backend.bees-abc.md").write_text("---\nbees_version: 1.1\ntype: epic\n---\n")
        (frontend_dir / "frontend.bees-xyz.md").write_text("---\nbees_version: 1.1\ntype: task\n---\n")

        # Configure hives
        now = datetime.now().isoformat()
        with repo_root_context(tmp_path):
            config = BeesConfig(
                hives={
                    "backend": HiveConfig(path=str(backend_dir), display_name="Backend", created_at=now),
                    "frontend": HiveConfig(path=str(frontend_dir), display_name="Frontend", created_at=now),
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
        """Should filter by ticket type when listing from hives (flat storage)."""
        from datetime import datetime
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        # Create hive root directory
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)

        # Create tickets in root with YAML frontmatter
        (backend_dir / "backend.bees-epic1.md").write_text("---\nbees_version: 1.1\ntype: epic\n---\n")
        (backend_dir / "backend.bees-task1.md").write_text("---\nbees_version: 1.1\ntype: task\n---\n")

        # Configure hives
        with repo_root_context(tmp_path):
            config = BeesConfig(
                hives={"backend": HiveConfig(path=str(backend_dir), display_name="Backend", created_at=datetime.now().isoformat())}
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
        with repo_root_context(tmp_path):
            tickets = list_tickets()
            assert tickets == []

    def test_list_tickets_filters_by_bees_version(self, tmp_path, monkeypatch):
        """Should only return files with bees_version field (valid tickets)."""
        from datetime import datetime
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)

        # Valid ticket with bees_version
        (backend_dir / "backend.bees-valid.md").write_text("---\nbees_version: 1.1\ntype: epic\n---\n")
        # Invalid - missing bees_version
        (backend_dir / "backend.bees-invalid.md").write_text("---\ntype: epic\n---\n")
        # Regular markdown file (not a ticket)
        (backend_dir / "README.md").write_text("# README\n\nJust a regular file")

        with repo_root_context(tmp_path):
            config = BeesConfig(
                hives={"backend": HiveConfig(path=str(backend_dir), display_name="Backend", created_at=datetime.now().isoformat())}
            )
            save_bees_config(config)

            # Should only return the valid ticket
            tickets = list_tickets()
            assert len(tickets) == 1
            assert tickets[0].name == "backend.bees-valid.md"

    def test_list_tickets_filters_by_type_with_bees_version(self, tmp_path, monkeypatch):
        """Should filter by type and validate bees_version."""
        from datetime import datetime
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)

        # Valid tickets with bees_version
        (backend_dir / "backend.bees-epic1.md").write_text("---\nbees_version: 1.1\ntype: epic\n---\n")
        (backend_dir / "backend.bees-task1.md").write_text("---\nbees_version: 1.1\ntype: task\n---\n")
        # Invalid - missing bees_version
        (backend_dir / "backend.bees-epic2.md").write_text("---\ntype: epic\n---\n")

        with repo_root_context(tmp_path):
            config = BeesConfig(
                hives={"backend": HiveConfig(path=str(backend_dir), display_name="Backend", created_at=datetime.now().isoformat())}
            )
            save_bees_config(config)

            # Should only return valid epic (with bees_version)
            epics = list_tickets("epic")
            assert len(epics) == 1
            assert epics[0].name == "backend.bees-epic1.md"

    def test_list_tickets_excludes_eggs_directory(self, tmp_path, monkeypatch):
        """Should exclude tickets in /eggs subdirectory."""
        from datetime import datetime
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)

        # Ticket in hive root (should be included)
        (backend_dir / "backend.bees-root.md").write_text("---\nbees_version: 1.1\ntype: epic\n---\n")

        # Ticket in /eggs subdirectory (should be excluded)
        eggs_dir = backend_dir / "eggs"
        eggs_dir.mkdir()
        (eggs_dir / "backend.bees-eggs.md").write_text("---\nbees_version: 1.1\ntype: task\n---\n")

        with repo_root_context(tmp_path):
            config = BeesConfig(
                hives={"backend": HiveConfig(path=str(backend_dir), display_name="Backend", created_at=datetime.now().isoformat())}
            )
            save_bees_config(config)

            # Should only return root ticket, not eggs ticket
            tickets = list_tickets()
            assert len(tickets) == 1
            assert tickets[0].name == "backend.bees-root.md"

    def test_list_tickets_excludes_evicted_directory(self, tmp_path, monkeypatch):
        """Should exclude tickets in /evicted subdirectory."""
        from datetime import datetime
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)

        # Ticket in hive root (should be included)
        (backend_dir / "backend.bees-root.md").write_text("---\nbees_version: 1.1\ntype: epic\n---\n")

        # Ticket in /evicted subdirectory (should be excluded)
        evicted_dir = backend_dir / "evicted"
        evicted_dir.mkdir()
        (evicted_dir / "backend.bees-evicted.md").write_text("---\nbees_version: 1.1\ntype: task\n---\n")

        with repo_root_context(tmp_path):
            config = BeesConfig(
                hives={"backend": HiveConfig(path=str(backend_dir), display_name="Backend", created_at=datetime.now().isoformat())}
            )
            save_bees_config(config)

            # Should only return root ticket, not evicted ticket
            tickets = list_tickets()
            assert len(tickets) == 1
            assert tickets[0].name == "backend.bees-root.md"
