"""
Unit tests for MCP server business logic.

Tests ticket operations (create, update, delete), validation logic,
and business rules enforcement. Lifecycle tests are in test_mcp_server_lifecycle.py.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.mcp_server import (
    _create_ticket,
    _update_ticket,
    _delete_ticket,
    get_repo_root_from_path,
    validate_hive_path
)
from src.mcp_id_utils import (
    parse_ticket_id,
    parse_hive_from_ticket_id
)
from src.repo_context import repo_root_context


class TestUpdateTicket:
    """Tests for update_ticket MCP tool functionality."""
    # Removed temp_tickets_dir fixture - now using single_hive from conftest.py

    async def test_update_ticket_basic_fields(self, single_hive, monkeypatch):
        """Test updating basic fields (title, labels, status, owner, priority)."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)

        from src.ticket_factory import create_epic
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create an epic
        epic_id = create_epic(
            hive_name="backend",
            title="Original Title",
            description="Original description",
            labels=["label1"],
            status="open",
            owner="alice@example.com",
            priority=2
        )

        # Update basic fields
        result = await _update_ticket(
            ticket_id=epic_id,
            title="Updated Title",
            description="Updated description",
            labels=["label1", "label2"],
            status="in_progress",
            owner="bob@example.com",
            priority=0
        )

        assert result["status"] == "success"
        assert result["ticket_id"] == epic_id

        # Verify updates
        ticket_path = get_ticket_path(epic_id, "epic")
        epic = read_ticket(ticket_path)

        assert epic.title == "Updated Title"
        assert epic.description == "Updated description"
        assert epic.labels == ["label1", "label2"]
        assert epic.status == "in_progress"
        assert epic.owner == "bob@example.com"
        assert epic.priority == 0

    async def test_update_ticket_nonexistent(self, single_hive, monkeypatch):
        """Test updating a non-existent ticket raises ValueError."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)

        with pytest.raises(ValueError, match="Ticket does not exist"):
            await _update_ticket(ticket_id="backend.bees-nonexistent", title="Test")

    async def test_update_ticket_empty_title(self, single_hive, monkeypatch):
        """Test updating with empty title raises ValueError."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)

        from src.ticket_factory import create_epic

        epic_id = create_epic(hive_name="backend", title="Original Title")

        with pytest.raises(ValueError, match="Ticket title cannot be empty"):
            await _update_ticket(ticket_id=epic_id, title="")

        with pytest.raises(ValueError, match="Ticket title cannot be empty"):
            await _update_ticket(ticket_id=epic_id, title="   ")

    async def test_update_ticket_add_parent(self, single_hive, monkeypatch):
        """Test adding a parent relationship with bidirectional updates."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)

        from src.ticket_factory import create_epic, create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create epic and task
        epic_id = create_epic(hive_name="backend", title="Parent Epic")
        task_id = create_task(hive_name="backend", title="Child Task")

        # Add parent to task
        result = await _update_ticket(ticket_id=task_id, parent=epic_id)

        assert result["status"] == "success"

        # Verify bidirectional updates
        task_path = get_ticket_path(task_id, "task")
        task = read_ticket(task_path)
        assert task.parent == epic_id

        epic_path = get_ticket_path(epic_id, "epic")
        epic = read_ticket(epic_path)
        assert task_id in epic.children

    async def test_update_ticket_remove_parent(self, single_hive, monkeypatch):
        """Test removing a parent relationship with bidirectional updates."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)

        from src.ticket_factory import create_epic, create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create epic and task with parent
        epic_id = create_epic(hive_name="backend", title="Parent Epic")
        task_id = create_task(hive_name="backend", title="Child Task", parent=epic_id)

        # Update bidirectional relationships
        from src.mcp_server import _add_child_to_parent
        _add_child_to_parent(task_id, epic_id)

        # Verify initial state
        epic_path = get_ticket_path(epic_id, "epic")
        epic = read_ticket(epic_path)
        assert task_id in epic.children

        # Remove parent
        result = await _update_ticket(ticket_id=task_id, parent=None)

        assert result["status"] == "success"

        # Verify bidirectional updates
        task_path = get_ticket_path(task_id, "task")
        task = read_ticket(task_path)
        assert task.parent is None

        epic = read_ticket(epic_path)
        assert task_id not in (epic.children or [])

    async def test_update_ticket_add_children(self, single_hive, monkeypatch):
        """Test adding children with bidirectional updates."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)

        from src.ticket_factory import create_epic, create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create epic and tasks
        epic_id = create_epic(hive_name="backend", title="Parent Epic")
        task1_id = create_task(hive_name="backend", title="Child Task 1")
        task2_id = create_task(hive_name="backend", title="Child Task 2")

        # Add children to epic
        result = await _update_ticket(ticket_id=epic_id, children=[task1_id, task2_id])

        assert result["status"] == "success"

        # Verify bidirectional updates
        epic_path = get_ticket_path(epic_id, "epic")
        epic = read_ticket(epic_path)
        assert task1_id in epic.children
        assert task2_id in epic.children

        task1_path = get_ticket_path(task1_id, "task")
        task1 = read_ticket(task1_path)
        assert task1.parent == epic_id

        task2_path = get_ticket_path(task2_id, "task")
        task2 = read_ticket(task2_path)
        assert task2.parent == epic_id

    async def test_update_ticket_remove_children(self, single_hive, monkeypatch):
        """Test removing children with bidirectional updates."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)

        from src.ticket_factory import create_epic, create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create epic with children
        epic_id = create_epic(hive_name="backend", title="Parent Epic")
        task1_id = create_task(hive_name="backend", title="Child Task 1", parent=epic_id)
        task2_id = create_task(hive_name="backend", title="Child Task 2", parent=epic_id)

        # Update bidirectional relationships
        from src.mcp_server import _add_child_to_parent
        _add_child_to_parent(task1_id, epic_id)
        _add_child_to_parent(task2_id, epic_id)

        # Remove all children
        result = await _update_ticket(ticket_id=epic_id, children=[])

        assert result["status"] == "success"

        # Verify bidirectional updates
        epic_path = get_ticket_path(epic_id, "epic")
        epic = read_ticket(epic_path)
        assert epic.children == []

        task1_path = get_ticket_path(task1_id, "task")
        task1 = read_ticket(task1_path)
        assert task1.parent is None

        task2_path = get_ticket_path(task2_id, "task")
        task2 = read_ticket(task2_path)
        assert task2.parent is None

    async def test_update_ticket_add_dependencies(self, single_hive, monkeypatch):
        """Test adding dependencies with bidirectional updates."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)

        from src.ticket_factory import create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create tasks
        task1_id = create_task(hive_name="backend", title="Task 1")
        task2_id = create_task(hive_name="backend", title="Task 2 (blocking)")
        task3_id = create_task(hive_name="backend", title="Task 3 (blocked)")

        # Add dependencies
        result = await _update_ticket(
            ticket_id=task1_id,
            up_dependencies=[task2_id],      # task2 blocks task1
            down_dependencies=[task3_id]     # task1 blocks task3
        )

        assert result["status"] == "success"

        # Verify bidirectional updates
        task1_path = get_ticket_path(task1_id, "task")
        task1 = read_ticket(task1_path)
        assert task2_id in task1.up_dependencies
        assert task3_id in task1.down_dependencies

        task2_path = get_ticket_path(task2_id, "task")
        task2 = read_ticket(task2_path)
        assert task1_id in task2.down_dependencies

        task3_path = get_ticket_path(task3_id, "task")
        task3 = read_ticket(task3_path)
        assert task1_id in task3.up_dependencies

    async def test_update_ticket_remove_dependencies(self, single_hive, monkeypatch):
        """Test removing dependencies with bidirectional updates."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)

        from src.ticket_factory import create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create tasks with dependencies
        task1_id = create_task(
            hive_name="backend", title="Task 1",
            up_dependencies=[],
            down_dependencies=[]
        )
        task2_id = create_task(hive_name="backend", title="Task 2")

        # Add dependency first
        await _update_ticket(ticket_id=task1_id, up_dependencies=[task2_id])

        # Verify initial state
        task1_path = get_ticket_path(task1_id, "task")
        task1 = read_ticket(task1_path)
        assert task2_id in task1.up_dependencies

        # Remove dependencies
        result = await _update_ticket(ticket_id=task1_id, up_dependencies=[])

        assert result["status"] == "success"

        # Verify bidirectional updates
        task1 = read_ticket(task1_path)
        assert task1.up_dependencies == []

        task2_path = get_ticket_path(task2_id, "task")
        task2 = read_ticket(task2_path)
        assert task1_id not in (task2.down_dependencies or [])

    async def test_update_ticket_nonexistent_parent(self, single_hive, monkeypatch):
        """Test updating with non-existent parent raises ValueError."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)

        from src.ticket_factory import create_task

        task_id = create_task(hive_name="backend", title="Test Task")

        with pytest.raises(ValueError, match="Parent ticket does not exist"):
            await _update_ticket(ticket_id=task_id, parent="backend.bees-nonexistent")

    async def test_update_ticket_nonexistent_child(self, single_hive, monkeypatch):
        """Test updating with non-existent child raises ValueError."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)

        from src.ticket_factory import create_epic

        epic_id = create_epic(hive_name="backend", title="Test Epic")

        with pytest.raises(ValueError, match="Child ticket does not exist"):
            await _update_ticket(ticket_id=epic_id, children=["backend.bees-nonexistent"])

    async def test_update_ticket_nonexistent_dependency(self, single_hive, monkeypatch):
        """Test updating with non-existent dependency raises ValueError."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)

        from src.ticket_factory import create_task

        task_id = create_task(hive_name="backend", title="Test Task")

        with pytest.raises(ValueError, match="Dependency ticket does not exist"):
            await _update_ticket(ticket_id=task_id, up_dependencies=["backend.bees-nonexistent"])

        with pytest.raises(ValueError, match="Dependency ticket does not exist"):
            await _update_ticket(ticket_id=task_id, down_dependencies=["backend.bees-nonexistent"])

    async def test_update_ticket_circular_dependency(self, single_hive, monkeypatch):
        """Test updating with circular dependency raises ValueError."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)

        from src.ticket_factory import create_task

        task1_id = create_task(hive_name="backend", title="Task 1")
        task2_id = create_task(hive_name="backend", title="Task 2")

        with pytest.raises(ValueError, match="Circular dependency detected"):
            await _update_ticket(
                ticket_id=task1_id,
                up_dependencies=[task2_id],
                down_dependencies=[task2_id]
            )

    async def test_update_ticket_partial_update(self, single_hive, monkeypatch):
        """Test that partial updates only modify specified fields."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)

        from src.ticket_factory import create_epic
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create epic with various fields
        epic_id = create_epic(
            hive_name="backend", title="Original Title",
            description="Original description",
            labels=["label1", "label2"],
            status="open",
            owner="alice@example.com",
            priority=2
        )

        # Update only title and status
        result = await _update_ticket(
            ticket_id=epic_id,
            title="Updated Title",
            status="in_progress"
        )

        assert result["status"] == "success"

        # Verify only specified fields changed
        ticket_path = get_ticket_path(epic_id, "epic")
        epic = read_ticket(ticket_path)

        assert epic.title == "Updated Title"  # Changed
        assert epic.status == "in_progress"   # Changed
        assert epic.description == "Original description"  # Unchanged
        assert epic.labels == ["label1", "label2"]  # Unchanged
        assert epic.owner == "alice@example.com"  # Unchanged
        assert epic.priority == 2  # Unchanged

    async def test_update_ticket_bidirectional_consistency(self, single_hive, monkeypatch):
        """Test comprehensive bidirectional consistency across multiple updates."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)

        from src.ticket_factory import create_epic, create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create tickets
        epic_id = create_epic(hive_name="backend", title="Epic")
        task1_id = create_task(hive_name="backend", title="Task 1")
        task2_id = create_task(hive_name="backend", title="Task 2")
        task3_id = create_task(hive_name="backend", title="Task 3")

        # Add task1 and task2 as children of epic
        await _update_ticket(ticket_id=epic_id, children=[task1_id, task2_id])

        # Make task3 depend on task1
        await _update_ticket(ticket_id=task3_id, up_dependencies=[task1_id])

        # Verify all relationships are bidirectional
        epic_path = get_ticket_path(epic_id, "epic")
        epic = read_ticket(epic_path)
        assert task1_id in epic.children
        assert task2_id in epic.children

        task1_path = get_ticket_path(task1_id, "task")
        task1 = read_ticket(task1_path)
        assert task1.parent == epic_id
        assert task3_id in task1.down_dependencies

        task2_path = get_ticket_path(task2_id, "task")
        task2 = read_ticket(task2_path)
        assert task2.parent == epic_id

        task3_path = get_ticket_path(task3_id, "task")
        task3 = read_ticket(task3_path)
        assert task1_id in task3.up_dependencies

        # Now remove task2 from epic's children
        await _update_ticket(ticket_id=epic_id, children=[task1_id])

        # Verify task2's parent is cleared
        task2 = read_ticket(task2_path)
        assert task2.parent is None

        # Verify epic only has task1
        epic = read_ticket(epic_path)
        assert task1_id in epic.children
        assert task2_id not in epic.children


class TestColonizeHiveMCPIntegration:
    """Integration tests for colonize_hive MCP tool wrapper."""

    @pytest.fixture
    def git_repo_tmp_path(self, tmp_path, monkeypatch):
        """Create a temporary directory with git repo structure."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        config_dir = tmp_path / ".bees"
        config_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        return tmp_path

    async def test_colonize_hive_success_case(self, git_repo_tmp_path):
        """Test successful colonization via MCP wrapper."""
        from src.mcp_hive_ops import _colonize_hive

        hive_path = git_repo_tmp_path / "backend_hive"
        hive_path.mkdir()

        result = await _colonize_hive("Back End", str(hive_path))

        # Verify success response
        assert result["status"] == "success"
        assert result["normalized_name"] == "back_end"
        assert result["display_name"] == "Back End"
        assert result["path"] == str(hive_path)

        # Verify directory structure created
        assert (hive_path / "eggs").exists()
        assert (hive_path / "evicted").exists()
        assert (hive_path / ".hive").exists()
        assert (hive_path / ".hive" / "identity.json").exists()

    async def test_colonize_hive_creates_marker(self, git_repo_tmp_path):
        """Test that MCP wrapper creates .hive marker with correct identity."""
        from src.mcp_hive_ops import _colonize_hive
        import json

        hive_path = git_repo_tmp_path / "frontend"
        hive_path.mkdir()

        result = await _colonize_hive("Frontend", str(hive_path))

        # Read identity file
        identity_file = hive_path / ".hive" / "identity.json"
        with open(identity_file, 'r') as f:
            identity_data = json.load(f)

        assert identity_data["normalized_name"] == "frontend"
        assert identity_data["display_name"] == "Frontend"
        assert "created_at" in identity_data
        assert "version" in identity_data

    async def test_colonize_hive_invalid_path_not_absolute(self, git_repo_tmp_path):
        """Test error case: path is not absolute."""
        from src.mcp_hive_ops import _colonize_hive

        with pytest.raises(ValueError, match="must be absolute"):
            await _colonize_hive("Test Hive", "relative/path")

    async def test_colonize_hive_path_does_not_exist(self, git_repo_tmp_path):
        """Test that parent directory is created if it doesn't exist."""
        from src.mcp_hive_ops import _colonize_hive

        # Path with non-existent parent - new behavior creates it
        nonexistent_parent = git_repo_tmp_path / "does_not_exist" / "nested"

        # New behavior: parent directory is created automatically
        result = await _colonize_hive("Test Hive", str(nonexistent_parent))

        # Should succeed
        assert result["status"] == "success"
        assert nonexistent_parent.parent.exists()
        assert nonexistent_parent.exists()

    async def test_colonize_hive_path_outside_repo(self, tmp_path, git_repo_tmp_path):
        """Test that colonize works when path is in a different git repo than provided repo_root."""
        from src.mcp_hive_ops import _colonize_hive

        # Create a hive in the git_repo_tmp_path
        # New behavior: When path is outside provided repo_root, it uses the hive path
        # to find the actual repo (git_repo_tmp_path) and uses that instead
        hive_path = git_repo_tmp_path / "test_hive_different_repo"
        hive_path.mkdir()

        # Provide a different repo_root (tmp_path parent) - the function will detect
        # the mismatch and use git_repo_tmp_path instead
        result = await _colonize_hive("Test Hive", str(hive_path))

        # Should succeed by using the correct repo from hive path
        assert result["status"] == "success"

    async def test_colonize_hive_duplicate_name(self, git_repo_tmp_path):
        """Test error case: duplicate hive name."""
        from src.mcp_hive_ops import _colonize_hive

        hive1_path = git_repo_tmp_path / "hive1"
        hive1_path.mkdir()
        hive2_path = git_repo_tmp_path / "hive2"
        hive2_path.mkdir()

        # Create first hive
        result1 = await _colonize_hive("Test Hive", str(hive1_path))
        assert result1["status"] == "success"

        # Try to create second hive with same normalized name
        with pytest.raises(ValueError, match="already exists"):
            await _colonize_hive("Test Hive", str(hive2_path))

    async def test_colonize_hive_invalid_name_empty(self, git_repo_tmp_path):
        """Test error case: name normalizes to empty string."""
        from src.mcp_hive_ops import _colonize_hive

        hive_path = git_repo_tmp_path / "test"
        hive_path.mkdir()

        with pytest.raises(ValueError, match="empty string"):
            await _colonize_hive("!!!", str(hive_path))

    async def test_colonize_hive_registers_in_config(self, git_repo_tmp_path):
        """Test that colonize_hive registers hive in config.json."""
        from src.mcp_hive_ops import _colonize_hive
        from src.config import load_bees_config

        hive_path = git_repo_tmp_path / "api"
        hive_path.mkdir()

        result = await _colonize_hive("API", str(hive_path))

        # Verify hive is in config
        config = load_bees_config()
        assert config is not None
        assert "api" in config.hives
        assert config.hives["api"].display_name == "API"
        assert config.hives["api"].path == str(hive_path)

    async def test_colonize_hive_name_normalization(self, git_repo_tmp_path):
        """Test that MCP wrapper correctly normalizes hive names."""
        from src.mcp_hive_ops import _colonize_hive

        test_cases = [
            ("Back End", "back_end"),
            ("UPPERCASE", "uppercase"),
            ("Multi Word Name", "multi_word_name"),
            ("API-v2", "api_v2"),
        ]

        for i, (display_name, expected_normalized) in enumerate(test_cases):
            hive_path = git_repo_tmp_path / f"hive{i}"
            hive_path.mkdir()

            result = await _colonize_hive(display_name, str(hive_path))

            assert result["normalized_name"] == expected_normalized
            assert result["display_name"] == display_name


class TestColonizeHiveMCPUnit:
    """Unit tests for colonize_hive MCP wrapper function."""

    def test_colonize_hive_tool_callable(self):
        """Test that _colonize_hive function is callable."""
        from src.mcp_hive_ops import _colonize_hive

        assert callable(_colonize_hive)

    def test_colonize_hive_accepts_name_and_path_parameters(self, git_repo_tmp_path):
        """Test that _colonize_hive accepts name and path parameters."""
        from src.mcp_hive_ops import _colonize_hive
        from inspect import signature

        sig = signature(_colonize_hive)
        params = list(sig.parameters.keys())

        assert 'name' in params
        assert 'path' in params

    async def test_colonize_hive_parameter_validation_empty_name(self, git_repo_tmp_path):
        """Test parameter validation for empty name."""
        from src.mcp_hive_ops import _colonize_hive

        hive_path = git_repo_tmp_path / "test"
        hive_path.mkdir()

        # Empty name should normalize to empty string and raise error
        with pytest.raises(ValueError):
            await _colonize_hive("", str(hive_path))

    async def test_colonize_hive_parameter_validation_invalid_path_format(self):
        """Test parameter validation for invalid path format (not absolute)."""
        from src.mcp_hive_ops import _colonize_hive

        with pytest.raises(ValueError):
            await _colonize_hive("Test", "relative/path")

    async def test_colonize_hive_success_response_structure(self, git_repo_tmp_path):
        """Test that success response has correct structure."""
        from src.mcp_hive_ops import _colonize_hive

        hive_path = git_repo_tmp_path / "test"
        hive_path.mkdir()

        result = await _colonize_hive("Test", str(hive_path))

        # Verify response structure
        assert isinstance(result, dict)
        assert "status" in result
        assert "normalized_name" in result
        assert "display_name" in result
        assert "path" in result
        assert result["status"] == "success"

    async def test_colonize_hive_error_response_raises_value_error(self, git_repo_tmp_path):
        """Test that error conditions raise ValueError."""
        from src.mcp_hive_ops import _colonize_hive

        # Invalid path should raise ValueError
        with pytest.raises(ValueError):
            await _colonize_hive("Test", "relative/path")

    async def test_colonize_hive_wraps_core_function(self, git_repo_tmp_path):
        """Test that MCP wrapper calls underlying colonize_hive_core() core function."""
        from src.mcp_hive_ops import _colonize_hive
        from unittest.mock import patch, AsyncMock

        hive_path = git_repo_tmp_path / "test"
        hive_path.mkdir()

        # Mock the core colonize_hive_core function
        with patch('src.mcp_hive_ops.colonize_hive_core', new_callable=AsyncMock) as mock_core:
            mock_core.return_value = {
                "status": "success",
                "normalized_name": "test",
                "display_name": "Test",
                "path": str(hive_path)
            }

            result = await _colonize_hive("Test", str(hive_path))

            # Verify core function was called with correct args (ctx and repo_root default to None)
            mock_core.assert_called_once()
            assert result["status"] == "success"

    async def test_colonize_hive_propagates_core_function_errors(self, git_repo_tmp_path):
        """Test that wrapper propagates errors from core function."""
        from src.mcp_hive_ops import _colonize_hive
        from unittest.mock import patch, AsyncMock

        hive_path = git_repo_tmp_path / "test"
        hive_path.mkdir()

        # Mock core function to return error
        with patch('src.mcp_hive_ops.colonize_hive_core', new_callable=AsyncMock) as mock_core:
            mock_core.return_value = {
                "status": "error",
                "message": "Test error",
                "error_type": "test_error"
            }

            with pytest.raises(ValueError, match="Test error"):
                await _colonize_hive("Test", str(hive_path))

    async def test_colonize_hive_handles_unexpected_exceptions(self, git_repo_tmp_path):
        """Test that wrapper handles unexpected exceptions."""
        from src.mcp_hive_ops import _colonize_hive
        from unittest.mock import patch, AsyncMock

        hive_path = git_repo_tmp_path / "test"
        hive_path.mkdir()

        # Mock core function to raise unexpected exception
        with patch('src.mcp_hive_ops.colonize_hive_core', new_callable=AsyncMock, side_effect=RuntimeError("Unexpected")):
            with pytest.raises(ValueError, match="Failed to colonize hive"):
                await _colonize_hive("Test", str(hive_path))

    @pytest.fixture
    def git_repo_tmp_path(self, tmp_path, monkeypatch):
        """Create a temporary directory with git repo structure."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        config_dir = tmp_path / ".bees"
        config_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        return tmp_path


class TestColonizeHiveMCPErrorCases:
    """Integration tests for colonize_hive error handling."""

    @pytest.fixture
    def git_repo_tmp_path(self, tmp_path, monkeypatch):
        """Create a temporary directory with git repo structure."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        config_dir = tmp_path / ".bees"
        config_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        return tmp_path

    async def test_colonize_hive_filesystem_error_eggs_creation(self, git_repo_tmp_path):
        """Test error case: cannot create /eggs directory."""
        from src.mcp_hive_ops import _colonize_hive
        from unittest.mock import patch

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        # Mock Path.mkdir to raise PermissionError on /eggs creation
        original_mkdir = Path.mkdir
        def mock_mkdir(self, *args, **kwargs):
            if self.name == "eggs":
                raise PermissionError("Permission denied")
            return original_mkdir(self, *args, **kwargs)

        with patch.object(Path, 'mkdir', mock_mkdir):
            with pytest.raises(ValueError, match="eggs"):
                await _colonize_hive("Test Hive", str(hive_path))

    async def test_colonize_hive_filesystem_error_evicted_creation(self, git_repo_tmp_path):
        """Test error case: cannot create /evicted directory."""
        from src.mcp_hive_ops import _colonize_hive
        from unittest.mock import patch

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        # Mock Path.mkdir to raise OSError on /evicted creation
        original_mkdir = Path.mkdir
        def mock_mkdir(self, *args, **kwargs):
            if self.name == "evicted":
                raise OSError("Disk full")
            return original_mkdir(self, *args, **kwargs)

        with patch.object(Path, 'mkdir', mock_mkdir):
            with pytest.raises(ValueError, match="evicted"):
                await _colonize_hive("Test Hive", str(hive_path))

    async def test_colonize_hive_error_writing_identity_file(self, git_repo_tmp_path):
        """Test error case: cannot write .hive/identity.json file."""
        from src.mcp_hive_ops import _colonize_hive
        from unittest.mock import patch

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        # Mock open to raise PermissionError on identity.json write
        original_open = open
        def mock_open_func(file, *args, **kwargs):
            if "identity.json" in str(file):
                raise PermissionError("Permission denied")
            return original_open(file, *args, **kwargs)

        with patch('builtins.open', mock_open_func):
            with pytest.raises(ValueError, match="identity"):
                await _colonize_hive("Test Hive", str(hive_path))

    async def test_colonize_hive_config_write_failure(self, git_repo_tmp_path):
        """Test error case: cannot write config.json."""
        from src.mcp_hive_ops import _colonize_hive
        from unittest.mock import patch

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        # Mock write_hive_config_dict to raise IOError
        with patch('src.mcp_hive_ops.write_hive_config_dict', side_effect=IOError("Disk full")):
            with pytest.raises(ValueError, match="config"):
                await _colonize_hive("Test Hive", str(hive_path))


class TestParseTicketId:
    """Tests for parse_ticket_id() utility function."""

    def test_parse_hive_prefixed_id(self):
        """Test parsing ticket ID with hive prefix."""
        hive_name, base_id = parse_ticket_id("backend.bees-abc1")
        assert hive_name == "backend"
        assert base_id == "bees-abc1"

    def test_parse_legacy_id_without_dot(self):
        """Test parsing legacy ticket ID without hive prefix."""
        hive_name, base_id = parse_ticket_id("bees-abc1")
        assert hive_name == ""
        assert base_id == "bees-abc1"

    def test_parse_id_with_multiple_dots(self):
        """Test parsing ticket ID with multiple dots (splits on first dot only)."""
        hive_name, base_id = parse_ticket_id("multi.dot.bees-xyz9")
        assert hive_name == "multi"
        assert base_id == "dot.bees-xyz9"

    def test_parse_id_with_underscore_hive(self):
        """Test parsing ticket ID with underscored hive name."""
        hive_name, base_id = parse_ticket_id("back_end.bees-123")
        assert hive_name == "back_end"
        assert base_id == "bees-123"

    def test_parse_id_none_raises_error(self):
        """Test that None ticket ID raises ValueError."""
        with pytest.raises(ValueError, match="ticket_id cannot be None"):
            parse_ticket_id(None)

    def test_parse_id_empty_string_raises_error(self):
        """Test that empty string ticket ID raises ValueError."""
        with pytest.raises(ValueError, match="ticket_id cannot be empty"):
            parse_ticket_id("")

    def test_parse_id_whitespace_only_raises_error(self):
        """Test that whitespace-only ticket ID raises ValueError."""
        with pytest.raises(ValueError, match="ticket_id cannot be empty"):
            parse_ticket_id("   ")

    def test_parse_id_returns_tuple(self):
        """Test that parse_ticket_id returns a tuple."""
        result = parse_ticket_id("hive.bees-123")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_parse_id_backward_compatibility(self):
        """Test backward compatibility with legacy format returns empty hive name."""
        hive_name, base_id = parse_ticket_id("bees-legacy")
        assert hive_name == ""  # Empty string for legacy IDs
        assert base_id == "bees-legacy"
        assert isinstance(hive_name, str)  # Not None, but empty string

    def test_parse_id_complex_hive_names(self):
        """Test parsing with various complex hive names."""
        test_cases = [
            ("frontend.bees-abc", ("frontend", "bees-abc")),
            ("api_v2.bees-xyz", ("api_v2", "bees-xyz")),
            ("team-alpha.bees-123", ("team-alpha", "bees-123")),
            ("CamelCase.bees-456", ("CamelCase", "bees-456")),
        ]

        for ticket_id, expected in test_cases:
            result = parse_ticket_id(ticket_id)
            assert result == expected, f"Failed for {ticket_id}"

    def test_parse_id_complex_base_ids(self):
        """Test parsing with various complex base ID formats."""
        test_cases = [
            ("hive.bees-abc1", ("hive", "bees-abc1")),
            ("hive.bees-xyz9", ("hive", "bees-xyz9")),
            ("hive.bees-1234", ("hive", "bees-1234")),
        ]

        for ticket_id, expected in test_cases:
            result = parse_ticket_id(ticket_id)
            assert result == expected, f"Failed for {ticket_id}"

    def test_parse_id_edge_case_dot_at_end(self):
        """Test parsing ID with dot at end (unusual but should handle gracefully)."""
        hive_name, base_id = parse_ticket_id("hive.")
        assert hive_name == "hive"
        assert base_id == ""  # Empty base_id after the dot

    def test_parse_id_edge_case_dot_at_start(self):
        """Test parsing ID with dot at start (unusual but should handle gracefully)."""
        hive_name, base_id = parse_ticket_id(".bees-123")
        assert hive_name == ""  # Empty hive name before the dot
        assert base_id == "bees-123"


class TestUpdateTicketHiveParsing:
    """Tests for hive parsing and routing in update_ticket()."""

    @pytest.fixture
    def mock_config(self, tmp_path):
        """Create a mock hive config for testing."""
        from src.config import BeesConfig, HiveConfig
        from datetime import datetime

        hive_path = tmp_path / "tickets"
        hive_path.mkdir()

        config = BeesConfig(
            hives={
                "backend": HiveConfig(
                    display_name="Backend",
                    path=str(hive_path),
                    created_at=datetime.now().isoformat()
                )
            }
        )
        return config

    @pytest.fixture
    def setup_test_ticket(self, tmp_path, mock_config, monkeypatch):
        """Create a test ticket with prefixed ID."""
        from src.ticket_factory import create_task
        from src.config import save_bees_config

        # Change to tmp_path to ensure all file operations are isolated
        monkeypatch.chdir(tmp_path)
        
        # Save config (will use tmp_path from autouse fixture's Path.cwd())
        config_dir = tmp_path / ".bees"
        config_dir.mkdir(exist_ok=True)
        save_bees_config(mock_config)

        # Create hive marker
        hive_path = Path(mock_config.hives["backend"].path)
        marker_path = hive_path / ".hive"
        marker_path.mkdir(exist_ok=True)
        identity_file = marker_path / "identity.json"
        import json
        with open(identity_file, 'w') as f:
            json.dump({
                "normalized_name": "backend",
                "display_name": "Backend",
                "created_at": "2024-01-01T00:00:00",
                "version": "1.0.0"
            }, f)

        # Create test ticket
        ticket_id = create_task(
            title="Test Task",
            description="Test description",
            hive_name="backend"
        )
        return ticket_id

    @patch('src.mcp_server.load_bees_config')
    async def test_update_ticket_with_valid_prefixed_id(self, mock_load_config, mock_config, setup_test_ticket):
        """Test update_ticket successfully updates with valid prefixed ID."""
        mock_load_config.return_value = mock_config
        ticket_id = setup_test_ticket

        result = await _update_ticket(
            ticket_id=ticket_id,
            title="Updated Title"
        )

        assert result["status"] == "success"
        assert result["ticket_id"] == ticket_id

    @patch('src.mcp_server.load_bees_config')
    async def test_update_ticket_with_malformed_id_raises_error(self, mock_load_config, mock_config):
        """Test update_ticket returns error for malformed ID (no dot)."""
        mock_load_config.return_value = mock_config

        with pytest.raises(ValueError, match="Malformed ticket ID.*Expected format: hive_name.bees-xxxx"):
            await _update_ticket(
                ticket_id="bees-abc1",  # No hive prefix
                title="Updated Title"
            )

    @patch('src.mcp_server.load_bees_config')
    async def test_update_ticket_with_unknown_hive_raises_error(self, mock_load_config, mock_config):
        """Test update_ticket returns error for unknown hive prefix."""
        mock_load_config.return_value = mock_config

        with pytest.raises(ValueError, match="Unknown hive.*not found in config"):
            await _update_ticket(
                ticket_id="unknown_hive.bees-abc1",
                title="Updated Title"
            )

    @patch('src.mcp_server.load_bees_config')
    async def test_update_ticket_routes_to_correct_hive(self, mock_load_config, mock_config, setup_test_ticket):
        """Test update_ticket routes to correct hive based on prefix."""
        mock_load_config.return_value = mock_config
        ticket_id = setup_test_ticket

        # Verify the ticket_id has the expected backend prefix
        assert ticket_id.startswith("backend.")

        # Update should succeed because it routes to the correct hive
        result = await _update_ticket(
            ticket_id=ticket_id,
            status="in_progress"
        )

        assert result["status"] == "success"
        assert result["ticket_id"] == ticket_id


class TestParseHiveFromTicketId:
    """Tests for parse_hive_from_ticket_id helper function."""

    def test_extracts_hive_prefix_from_valid_id(self):
        """Test extraction of hive prefix from valid ticket ID."""
        assert parse_hive_from_ticket_id('backend.bees-abc1') == 'backend'
        assert parse_hive_from_ticket_id('frontend.bees-xyz2') == 'frontend'
        assert parse_hive_from_ticket_id('my_hive.bees-123') == 'my_hive'

    def test_returns_none_for_malformed_id_no_dot(self):
        """Test returns None for IDs without dots (malformed)."""
        assert parse_hive_from_ticket_id('bees-abc1') is None
        assert parse_hive_from_ticket_id('invalid') is None
        assert parse_hive_from_ticket_id('nodotshere') is None

    def test_handles_multiple_dots_correctly(self):
        """Test that only first dot is used to split hive prefix."""
        # With multiple dots, only the first dot matters
        assert parse_hive_from_ticket_id('multi.dot.bees-xyz9') == 'multi'
        assert parse_hive_from_ticket_id('hive.sub.bees-abc') == 'hive'

    def test_handles_empty_prefix(self):
        """Test handling of IDs with empty prefix before dot."""
        # Edge case: dot at beginning
        result = parse_hive_from_ticket_id('.bees-abc1')
        assert result == ''  # Empty string is the prefix

    def test_handles_empty_suffix(self):
        """Test handling of IDs with empty suffix after dot."""
        # Edge case: dot at end
        result = parse_hive_from_ticket_id('backend.')
        assert result == 'backend'


class TestListHives:
    """Tests for list_hives MCP tool functionality."""

    @pytest.fixture
    def temp_repo(self, tmp_path, monkeypatch):
        """Create temporary repository with config directory."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()

        config_dir = repo_root / ".bees"
        config_dir.mkdir()

        monkeypatch.chdir(repo_root)
        return repo_root

    @pytest.fixture
    def mock_ctx(self, temp_repo):
        """Create a mock MCP context for tests."""
        from unittest.mock import Mock

        ctx = Mock()
        mock_root = Mock()
        mock_root.uri = f"file://{temp_repo}"

        async def mock_list_roots():
            return [mock_root]

        ctx.list_roots = mock_list_roots
        return ctx

    async def test_list_hives_returns_all_hives_from_config(self, temp_repo, mock_ctx):
        """Test list_hives returns correct data when config.json exists with hives."""
        from src.mcp_hive_ops import _list_hives
        from src.config import BeesConfig, HiveConfig, save_bees_config

        # Create config with multiple hives
        hive1_path = temp_repo / "hive1"
        hive1_path.mkdir()
        hive2_path = temp_repo / "hive2"
        hive2_path.mkdir()

        config = BeesConfig(hives={
            "back_end": HiveConfig(
                display_name="Back End",
                path=str(hive1_path),
                created_at="2024-01-01T00:00:00"
            ),
            "frontend": HiveConfig(
                display_name="Frontend",
                path=str(hive2_path),
                created_at="2024-01-02T00:00:00"
            )
        })
        save_bees_config(config)

        # Call list_hives
        result = await _list_hives(mock_ctx)

        # Verify response structure
        assert result["status"] == "success"
        assert "hives" in result
        assert len(result["hives"]) == 2

        # Verify hive data
        hives = {h["normalized_name"]: h for h in result["hives"]}
        assert "back_end" in hives
        assert "frontend" in hives

        assert hives["back_end"]["display_name"] == "Back End"
        assert hives["back_end"]["path"] == str(hive1_path)

        assert hives["frontend"]["display_name"] == "Frontend"
        assert hives["frontend"]["path"] == str(hive2_path)

    async def test_list_hives_returns_empty_list_when_no_config(self, temp_repo, mock_ctx):
        """Test list_hives returns empty list with message when config.json doesn't exist."""
        from src.mcp_hive_ops import _list_hives

        # No config.json created - should return empty list
        result = await _list_hives(mock_ctx)

        assert result["status"] == "success"
        assert result["hives"] == []
        assert result["message"] == "No hives configured"

    async def test_list_hives_returns_empty_list_when_no_hives(self, temp_repo, mock_ctx):
        """Test list_hives returns empty list with message when config.json exists but has no hives."""
        from src.mcp_hive_ops import _list_hives
        from src.config import BeesConfig, save_bees_config

        # Create config with empty hives
        config = BeesConfig(hives={})
        save_bees_config(config)

        result = await _list_hives(mock_ctx)

        assert result["status"] == "success"
        assert result["hives"] == []
        assert result["message"] == "No hives configured"

    async def test_list_hives_returns_correct_fields(self, temp_repo, mock_ctx):
        """Test all hive fields are returned correctly (display_name, normalized_name, path)."""
        from src.mcp_hive_ops import _list_hives
        from src.config import BeesConfig, HiveConfig, save_bees_config

        # Create config with a hive
        hive_path = temp_repo / "tickets"
        hive_path.mkdir()

        config = BeesConfig(hives={
            "test_hive": HiveConfig(
                display_name="Test Hive",
                path=str(hive_path),
                created_at="2024-01-01T00:00:00"
            )
        })
        save_bees_config(config)

        result = await _list_hives(mock_ctx)

        assert result["status"] == "success"
        assert len(result["hives"]) == 1

        hive = result["hives"][0]
        assert hive["display_name"] == "Test Hive"
        assert hive["normalized_name"] == "test_hive"
        assert hive["path"] == str(hive_path)

        # Verify only expected fields are present
        assert set(hive.keys()) == {"display_name", "normalized_name", "path"}

    async def test_list_hives_handles_exception(self, temp_repo, mock_ctx, monkeypatch):
        """Test list_hives handles exceptions gracefully."""
        from src.mcp_hive_ops import _list_hives

        # Mock load_bees_config to raise an exception
        def mock_load_error(*args, **kwargs):
            raise Exception("Failed to load config")

        monkeypatch.setattr("src.mcp_hive_ops.load_bees_config", mock_load_error)

        # Should raise ValueError with error message
        with pytest.raises(ValueError, match="Failed to list hives"):
            await _list_hives(mock_ctx)

    async def test_list_hives_with_single_hive(self, temp_repo, mock_ctx):
        """Test list_hives works correctly with a single hive."""
        from src.mcp_hive_ops import _list_hives
        from src.config import BeesConfig, HiveConfig, save_bees_config

        hive_path = temp_repo / "single"
        hive_path.mkdir()

        config = BeesConfig(hives={
            "single": HiveConfig(
                display_name="Single",
                path=str(hive_path),
                created_at="2024-01-01T00:00:00"
            )
        })
        save_bees_config(config)

        result = await _list_hives(mock_ctx)

        assert result["status"] == "success"
        assert len(result["hives"]) == 1
        assert result["hives"][0]["normalized_name"] == "single"

    async def test_list_hives_with_many_hives(self, temp_repo, mock_ctx):
        """Test list_hives works with multiple hives."""
        from src.mcp_hive_ops import _list_hives
        from src.config import BeesConfig, HiveConfig, save_bees_config

        # Create 5 hives
        hives = {}
        for i in range(5):
            hive_path = temp_repo / f"hive{i}"
            hive_path.mkdir()
            hives[f"hive{i}"] = HiveConfig(
                display_name=f"Hive {i}",
                path=str(hive_path),
                created_at=f"2024-01-0{i+1}T00:00:00"
            )

        config = BeesConfig(hives=hives)
        save_bees_config(config)

        result = await _list_hives(mock_ctx)

        assert result["status"] == "success"
        assert len(result["hives"]) == 5

        # Verify all hives are present
        normalized_names = {h["normalized_name"] for h in result["hives"]}
        assert normalized_names == {"hive0", "hive1", "hive2", "hive3", "hive4"}


class TestAbandonHive:
    """Tests for await _abandon_hive() function."""

    @pytest.fixture
    def git_repo_tmp_path(self, tmp_path, monkeypatch):
        """Create a temporary directory with git repo structure."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        return tmp_path

    async def test_abandon_hive_removes_from_config(self, git_repo_tmp_path):
        """Test that abandon_hive removes hive entry from config."""
        from src.mcp_hive_ops import _abandon_hive, _colonize_hive
        from src.config import load_bees_config

        # Create a hive
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()
        await _colonize_hive("Test Hive", str(hive_path))

        # Verify hive exists in config
        config = load_bees_config()
        assert "test_hive" in config.hives

        # Abandon the hive
        result = await _abandon_hive("Test Hive")

        # Verify success
        assert result["status"] == "success"

        # Verify hive removed from config
        config = load_bees_config()
        assert "test_hive" not in config.hives

    async def test_abandon_hive_preserves_files(self, git_repo_tmp_path):
        """Test that abandon_hive leaves ticket files intact."""
        from src.mcp_hive_ops import _abandon_hive, _colonize_hive

        # Create a hive with structure
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()
        await _colonize_hive("Test Hive", str(hive_path))

        # Create some ticket files
        ticket_file = hive_path / "test.md"
        ticket_file.write_text("test ticket")

        # Abandon the hive
        result = await _abandon_hive("Test Hive")

        # Verify files still exist
        assert hive_path.exists()
        assert ticket_file.exists()
        assert ticket_file.read_text() == "test ticket"

        # Verify .hive marker still exists
        assert (hive_path / ".hive").exists()

    async def test_abandon_hive_returns_error_for_nonexistent(self, git_repo_tmp_path):
        """Test that abandon_hive raises ValueError for non-existent hive."""
        from src.mcp_hive_ops import _abandon_hive

        with pytest.raises(ValueError) as exc_info:
            await _abandon_hive("NonExistent")
        
        assert "NonExistent" in str(exc_info.value)
        assert "nonexistent" in str(exc_info.value)

    async def test_abandon_hive_returns_success_message(self, git_repo_tmp_path):
        """Test that abandon_hive returns success message with display name."""
        from src.mcp_hive_ops import _abandon_hive, _colonize_hive

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()
        await _colonize_hive("Back End", str(hive_path))

        result = await _abandon_hive("Back End")

        assert result["status"] == "success"
        assert "Back End" in result["message"]

    async def test_abandon_hive_handles_normalized_name(self, git_repo_tmp_path):
        """Test that abandon_hive works with normalized hive name."""
        from src.mcp_hive_ops import _abandon_hive, _colonize_hive
        from src.config import load_bees_config

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()
        await _colonize_hive("Back End", str(hive_path))

        result = await _abandon_hive("back_end")

        assert result["status"] == "success"

    async def test_abandon_hive_handles_display_name(self, git_repo_tmp_path):
        """Test that abandon_hive works with display name."""
        from src.mcp_hive_ops import _abandon_hive, _colonize_hive

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()
        await _colonize_hive("Back End", str(hive_path))

        result = await _abandon_hive("Back End")

        assert result["status"] == "success"

    async def test_abandon_hive_returns_path(self, git_repo_tmp_path):
        """Test that abandon_hive returns the hive path."""
        from src.mcp_hive_ops import _abandon_hive, _colonize_hive

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()
        await _colonize_hive("Test Hive", str(hive_path))

        result = await _abandon_hive("Test Hive")

        assert result["path"] == str(hive_path)

    async def test_abandon_hive_with_multiple_hives(self, git_repo_tmp_path):
        """Test that abandon_hive removes only target hive from config."""
        from src.mcp_hive_ops import _abandon_hive, _colonize_hive
        from src.config import load_bees_config

        # Create multiple hives
        hive1_path = git_repo_tmp_path / "hive1"
        hive2_path = git_repo_tmp_path / "hive2"
        hive1_path.mkdir()
        hive2_path.mkdir()

        await _colonize_hive("Hive 1", str(hive1_path))
        await _colonize_hive("Hive 2", str(hive2_path))

        # Verify both exist
        config = load_bees_config()
        assert "hive_1" in config.hives
        assert "hive_2" in config.hives

        # Abandon one hive
        result = await _abandon_hive("Hive 1")

        assert result["status"] == "success"

        # Verify only target removed
        config = load_bees_config()
        assert "hive_1" not in config.hives
        assert "hive_2" in config.hives

    async def test_abandon_hive_handles_last_hive(self, git_repo_tmp_path):
        """Test that abandon_hive handles removing the last hive in config."""
        from src.mcp_hive_ops import _abandon_hive, _colonize_hive
        from src.config import load_bees_config

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()
        await _colonize_hive("Test Hive", str(hive_path))

        # Abandon the only hive
        result = await _abandon_hive("Test Hive")

        assert result["status"] == "success"

        # Verify config has no hives
        config = load_bees_config()
        assert len(config.hives) == 0

    async def test_abandon_hive_normalizes_hive_name(self, git_repo_tmp_path):
        """Test that abandon_hive normalizes hive name before lookup."""
        from src.mcp_hive_ops import _abandon_hive, _colonize_hive

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()
        await _colonize_hive("Back End", str(hive_path))

        # Try various forms of the name
        result = await _abandon_hive("BACK END")
        assert result["status"] == "success"

    async def test_abandon_hive_preserves_eggs_directory(self, git_repo_tmp_path):
        """Test that abandon_hive leaves /eggs directory intact."""
        from src.mcp_hive_ops import _abandon_hive, _colonize_hive

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()
        await _colonize_hive("Test Hive", str(hive_path))

        # Abandon hive
        result = await _abandon_hive("Test Hive")

        # Verify /eggs still exists
        assert (hive_path / "eggs").exists()

    async def test_abandon_hive_preserves_evicted_directory(self, git_repo_tmp_path):
        """Test that abandon_hive leaves /evicted directory intact."""
        from src.mcp_hive_ops import _abandon_hive, _colonize_hive

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()
        await _colonize_hive("Test Hive", str(hive_path))

        # Abandon hive
        result = await _abandon_hive("Test Hive")

        # Verify /evicted still exists
        assert (hive_path / "evicted").exists()

    async def test_abandon_hive_response_structure(self, git_repo_tmp_path):
        """Test that abandon_hive returns correct response structure."""
        from src.mcp_hive_ops import _abandon_hive, _colonize_hive

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()
        await _colonize_hive("Test Hive", str(hive_path))

        result = await _abandon_hive("Test Hive")

        # Verify response has all expected keys
        assert "status" in result
        assert "message" in result
        assert "display_name" in result
        assert "normalized_name" in result
        assert "path" in result
        assert result["status"] == "success"


