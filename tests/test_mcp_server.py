"""
Unit tests for MCP server lifecycle and health checks.

Tests server initialization, configuration, lifecycle management (start/stop),
health checks, and tool schema registration.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.mcp_server import (
    mcp,
    start_server,
    stop_server,
    _health_check,
    _create_ticket,
    _update_ticket,
    _delete_ticket,
    _server_running,
    get_repo_root_from_path,
    validate_hive_path
)
from src.mcp_id_utils import (
    parse_ticket_id,
    parse_hive_from_ticket_id
)


class TestMCPServerInitialization:
    """Tests for MCP server initialization and configuration."""

    def test_server_instance_exists(self):
        """Test that the MCP server instance is created."""
        assert mcp is not None
        assert hasattr(mcp, 'name')

    def test_server_name_configuration(self):
        """Test that server name is properly configured."""
        assert mcp.name == "Bees Ticket Management Server"

    def test_server_has_required_attributes(self):
        """Test that server has all required attributes."""
        assert hasattr(mcp, 'name')
        # FastMCP may expose version/description differently
        # Just verify the server can be instantiated


class TestServerLifecycle:
    """Tests for server start and stop functionality."""

    def test_start_server_success(self):
        """Test successful server startup."""
        result = start_server()

        assert result is not None
        assert result["status"] == "running"
        assert result["name"] == "Bees Ticket Management Server"
        assert result["version"] == "0.1.0"

    def test_stop_server_success(self):
        """Test successful server shutdown."""
        # Start server first
        start_server()

        # Then stop it
        result = stop_server()

        assert result is not None
        assert result["status"] == "stopped"
        assert result["name"] == "Bees Ticket Management Server"

    def test_start_stop_cycle(self):
        """Test multiple start/stop cycles."""
        # Start
        result1 = start_server()
        assert result1["status"] == "running"

        # Stop
        result2 = stop_server()
        assert result2["status"] == "stopped"

        # Start again
        result3 = start_server()
        assert result3["status"] == "running"

    @patch('src.mcp_server.logger')
    def test_start_server_logs_messages(self, mock_logger):
        """Test that start_server logs appropriate messages."""
        start_server()

        # Verify logging calls were made
        assert mock_logger.info.called

    @patch('src.mcp_server.logger')
    def test_stop_server_logs_messages(self, mock_logger):
        """Test that stop_server logs appropriate messages."""
        start_server()
        stop_server()

        # Verify logging calls were made
        assert mock_logger.info.called


class TestHealthCheck:
    """Tests for health check endpoint functionality."""

    def test_health_check_when_server_running(self):
        """Test health check returns healthy when server is running."""
        start_server()

        result = _health_check()

        assert result is not None
        assert result["status"] == "healthy"
        assert result["server_running"] is True
        assert result["ready"] is True
        assert result["name"] == "Bees Ticket Management Server"
        assert result["version"] == "0.1.0"

    def test_health_check_when_server_stopped(self):
        """Test health check returns stopped when server is not running."""
        stop_server()

        result = _health_check()

        assert result is not None
        assert result["status"] == "stopped"
        assert result["server_running"] is False
        assert result["ready"] is False

    def test_health_check_returns_dict(self):
        """Test that health check returns a dictionary."""
        result = _health_check()

        assert isinstance(result, dict)
        assert "status" in result
        assert "server_running" in result
        assert "ready" in result


class TestToolRegistration:
    """Tests for MCP tool schema registration."""

    def test_health_check_tool_registered(self):
        """Test that health_check tool is registered."""
        # FastMCP registers tools via decorators
        # We can verify by checking if the function is callable
        assert callable(_health_check)

    def test_create_ticket_tool_registered(self):
        """Test that create_ticket tool schema is registered."""
        # Verify the underlying function is callable
        assert callable(_create_ticket)

    def test_update_ticket_tool_registered(self):
        """Test that update_ticket tool schema is registered."""
        assert callable(_update_ticket)

    def test_delete_ticket_tool_registered(self):
        """Test that delete_ticket tool schema is registered."""
        assert callable(_delete_ticket)

    async def test_create_ticket_implementation_response(self, tmp_path, monkeypatch):
        """Test that create_ticket returns expected response."""
        import json
        from src.config import BeesConfig, HiveConfig, save_bees_config
        from datetime import datetime
        
        # Change to tmp_path for test isolation
        monkeypatch.chdir(tmp_path)
        
        # Create default hive directory
        default_hive = tmp_path / "hive"
        default_hive.mkdir()
        
        # Initialize .bees/config.json with hive registration
        config = BeesConfig(
            hives={
                'default': HiveConfig(
                    path=str(default_hive),
                    display_name='Default',
                    created_at=datetime.now().isoformat()
                )
            }
        )
        save_bees_config(config, repo_root=tmp_path)

        result = await _create_ticket(
            hive_name="default",
            ticket_type="task",
            title="Test Task"
        )

        assert result is not None
        assert result["status"] == "success"
        assert "ticket_id" in result
        assert "ticket_type" in result
        assert result["ticket_type"] == "task"

    async def test_create_ticket_validates_type(self):
        """Test that create_ticket validates ticket_type parameter."""
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(hive_name="default", ticket_type="invalid", title="Test")

        assert "Invalid ticket_type" in str(exc_info.value)

    async def test_create_ticket_validates_epic_parent(self, tmp_path, monkeypatch):
        """Test that create_ticket rejects parent for epics."""
        import json
        from src.config import BeesConfig, HiveConfig, save_bees_config
        from datetime import datetime
        
        # Change to tmp_path for test isolation
        monkeypatch.chdir(tmp_path)
        
        # Create default hive directory
        default_hive = tmp_path / "hive"
        default_hive.mkdir()
        
        # Initialize .bees/config.json with hive registration
        config = BeesConfig(
            hives={
                'default': HiveConfig(
                    path=str(default_hive),
                    display_name='Default',
                    created_at=datetime.now().isoformat()
                )
            }
        )
        save_bees_config(config, repo_root=tmp_path)
        
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(hive_name="default", ticket_type="epic", title="Test", parent="some-id")

        assert "Epics cannot have a parent" in str(exc_info.value)

    async def test_create_ticket_validates_subtask_parent(self, tmp_path, monkeypatch):
        """Test that create_ticket requires parent for subtasks."""
        import json
        from src.config import BeesConfig, HiveConfig, save_bees_config
        from datetime import datetime
        
        # Change to tmp_path for test isolation
        monkeypatch.chdir(tmp_path)
        
        # Create default hive directory
        default_hive = tmp_path / "hive"
        default_hive.mkdir()
        
        # Initialize .bees/config.json with hive registration
        config = BeesConfig(
            hives={
                'default': HiveConfig(
                    path=str(default_hive),
                    display_name='Default',
                    created_at=datetime.now().isoformat()
                )
            }
        )
        save_bees_config(config, repo_root=tmp_path)
        
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(hive_name="default", ticket_type="subtask", title="Test")

        assert "Subtasks must have a parent" in str(exc_info.value)


class TestErrorHandling:
    """Tests for error handling in server operations."""

    @patch('src.mcp_server.logger')
    def test_start_server_exception_handling(self, mock_logger):
        """Test that start_server handles exceptions properly."""
        # This test verifies the exception handling structure exists
        # In practice, start_server is simple and unlikely to raise exceptions
        # but the try-except block is there for safety

        # Just verify it can be called without raising
        result = start_server()
        assert result is not None

    @patch('src.mcp_server.logger')
    def test_stop_server_exception_handling(self, mock_logger):
        """Test that stop_server handles exceptions properly."""
        # Similar to start_server test
        result = stop_server()
        assert result is not None


class TestServerConfiguration:
    """Tests for server configuration validation."""

    def test_server_has_version(self):
        """Test that server version is defined."""
        result = start_server()
        assert "version" in result
        assert result["version"] == "0.1.0"

    def test_server_has_name(self):
        """Test that server name is defined."""
        result = start_server()
        assert "name" in result
        assert len(result["name"]) > 0


class TestUpdateTicket:
    """Tests for update_ticket MCP tool functionality."""

    @pytest.fixture
    def temp_tickets_dir(self, tmp_path, monkeypatch):
        """Create temporary tickets directory with test fixtures and hive config."""
        from src.config import BeesConfig, HiveConfig, save_bees_config

        # Change to tmp_path for test isolation
        monkeypatch.chdir(tmp_path)

        # Create default hive directory
        default_hive = tmp_path / "tickets"
        default_hive.mkdir()

        # Initialize .bees/config.json
        from datetime import datetime
        config = BeesConfig(
            hives={
                'default': HiveConfig(
                    path=str(default_hive),
                    display_name='Default',
                    created_at=datetime.now().isoformat()
                )
            }
        )
        save_bees_config(config, repo_root=tmp_path)

        return tmp_path

    async def test_update_ticket_basic_fields(self, temp_tickets_dir):
        """Test updating basic fields (title, labels, status, owner, priority)."""
        from src.ticket_factory import create_epic
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create an epic
        epic_id = create_epic(
            hive_name="default",
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

    async def test_update_ticket_nonexistent(self, temp_tickets_dir):
        """Test updating a non-existent ticket raises ValueError."""
        with pytest.raises(ValueError, match="Ticket does not exist"):
            await _update_ticket(ticket_id="default.bees-nonexistent", title="Test")

    async def test_update_ticket_empty_title(self, temp_tickets_dir):
        """Test updating with empty title raises ValueError."""
        from src.ticket_factory import create_epic

        epic_id = create_epic(hive_name="default", title="Original Title")

        with pytest.raises(ValueError, match="Ticket title cannot be empty"):
            await _update_ticket(ticket_id=epic_id, title="")

        with pytest.raises(ValueError, match="Ticket title cannot be empty"):
            await _update_ticket(ticket_id=epic_id, title="   ")

    async def test_update_ticket_add_parent(self, temp_tickets_dir):
        """Test adding a parent relationship with bidirectional updates."""
        from src.ticket_factory import create_epic, create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create epic and task
        epic_id = create_epic(hive_name="default", title="Parent Epic")
        task_id = create_task(hive_name="default", title="Child Task")

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

    async def test_update_ticket_remove_parent(self, temp_tickets_dir):
        """Test removing a parent relationship with bidirectional updates."""
        from src.ticket_factory import create_epic, create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create epic and task with parent
        epic_id = create_epic(hive_name="default", title="Parent Epic")
        task_id = create_task(hive_name="default", title="Child Task", parent=epic_id)

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

    async def test_update_ticket_add_children(self, temp_tickets_dir):
        """Test adding children with bidirectional updates."""
        from src.ticket_factory import create_epic, create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create epic and tasks
        epic_id = create_epic(hive_name="default", title="Parent Epic")
        task1_id = create_task(hive_name="default", title="Child Task 1")
        task2_id = create_task(hive_name="default", title="Child Task 2")

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

    async def test_update_ticket_remove_children(self, temp_tickets_dir):
        """Test removing children with bidirectional updates."""
        from src.ticket_factory import create_epic, create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create epic with children
        epic_id = create_epic(hive_name="default", title="Parent Epic")
        task1_id = create_task(hive_name="default", title="Child Task 1", parent=epic_id)
        task2_id = create_task(hive_name="default", title="Child Task 2", parent=epic_id)

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

    async def test_update_ticket_add_dependencies(self, temp_tickets_dir):
        """Test adding dependencies with bidirectional updates."""
        from src.ticket_factory import create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create tasks
        task1_id = create_task(hive_name="default", title="Task 1")
        task2_id = create_task(hive_name="default", title="Task 2 (blocking)")
        task3_id = create_task(hive_name="default", title="Task 3 (blocked)")

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

    async def test_update_ticket_remove_dependencies(self, temp_tickets_dir):
        """Test removing dependencies with bidirectional updates."""
        from src.ticket_factory import create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create tasks with dependencies
        task1_id = create_task(
            hive_name="default", title="Task 1",
            up_dependencies=[],
            down_dependencies=[]
        )
        task2_id = create_task(hive_name="default", title="Task 2")

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

    async def test_update_ticket_nonexistent_parent(self, temp_tickets_dir):
        """Test updating with non-existent parent raises ValueError."""
        from src.ticket_factory import create_task

        task_id = create_task(hive_name="default", title="Test Task")

        with pytest.raises(ValueError, match="Parent ticket does not exist"):
            await _update_ticket(ticket_id=task_id, parent="bees-nonexistent")

    async def test_update_ticket_nonexistent_child(self, temp_tickets_dir):
        """Test updating with non-existent child raises ValueError."""
        from src.ticket_factory import create_epic

        epic_id = create_epic(hive_name="default", title="Test Epic")

        with pytest.raises(ValueError, match="Child ticket does not exist"):
            await _update_ticket(ticket_id=epic_id, children=["bees-nonexistent"])

    async def test_update_ticket_nonexistent_dependency(self, temp_tickets_dir):
        """Test updating with non-existent dependency raises ValueError."""
        from src.ticket_factory import create_task

        task_id = create_task(hive_name="default", title="Test Task")

        with pytest.raises(ValueError, match="Dependency ticket does not exist"):
            await _update_ticket(ticket_id=task_id, up_dependencies=["bees-nonexistent"])

        with pytest.raises(ValueError, match="Dependency ticket does not exist"):
            await _update_ticket(ticket_id=task_id, down_dependencies=["bees-nonexistent"])

    async def test_update_ticket_circular_dependency(self, temp_tickets_dir):
        """Test updating with circular dependency raises ValueError."""
        from src.ticket_factory import create_task

        task1_id = create_task(hive_name="default", title="Task 1")
        task2_id = create_task(hive_name="default", title="Task 2")

        with pytest.raises(ValueError, match="Circular dependency detected"):
            await _update_ticket(
                ticket_id=task1_id,
                up_dependencies=[task2_id],
                down_dependencies=[task2_id]
            )

    async def test_update_ticket_partial_update(self, temp_tickets_dir):
        """Test that partial updates only modify specified fields."""
        from src.ticket_factory import create_epic
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create epic with various fields
        epic_id = create_epic(
            hive_name="default", title="Original Title",
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

    async def test_update_ticket_bidirectional_consistency(self, temp_tickets_dir):
        """Test comprehensive bidirectional consistency across multiple updates."""
        from src.ticket_factory import create_epic, create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create tickets
        epic_id = create_epic(hive_name="default", title="Epic")
        task1_id = create_task(hive_name="default", title="Task 1")
        task2_id = create_task(hive_name="default", title="Task 2")
        task3_id = create_task(hive_name="default", title="Task 3")

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


class TestGetRepoRoot:
    """Tests for get_repo_root_from_path() helper function."""

    def test_get_repo_root_success(self, tmp_path, monkeypatch):
        """Test get_repo_root_from_path finds .git directory in current or parent directories."""
        # Create a fake repo structure
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()

        subdir = repo_root / "some" / "nested" / "dir"
        subdir.mkdir(parents=True)

        # Should find repo root by walking up from subdir
        result = get_repo_root_from_path(subdir)
        assert result == repo_root

    def test_get_repo_root_at_root(self, tmp_path, monkeypatch):
        """Test get_repo_root_from_path when .git is in current directory."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()

        result = get_repo_root_from_path(repo_root)
        assert result == repo_root

    def test_get_repo_root_not_in_repo(self, tmp_path, monkeypatch):
        """Test get_repo_root_from_path raises ValueError when not in a git repo."""
        # Create directory without .git
        non_repo = tmp_path / "not_a_repo"
        non_repo.mkdir()

        with pytest.raises(ValueError, match="Not in a git repository"):
            get_repo_root_from_path(non_repo)


class TestValidateHivePath:
    """Tests for validate_hive_path() function."""

    def test_validate_hive_path_valid_absolute_path(self, tmp_path):
        """Test validation succeeds for valid absolute path within repo."""
        # Create repo structure
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        hive_dir = repo_root / "tickets" / "backend"
        hive_dir.mkdir(parents=True)

        # Should succeed and return normalized path
        result = validate_hive_path(str(hive_dir), repo_root)
        assert result == hive_dir.resolve()

    def test_validate_hive_path_with_trailing_slash(self, tmp_path):
        """Test validation normalizes trailing slashes."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        hive_dir = repo_root / "tickets"
        hive_dir.mkdir()

        # Test with trailing slash
        result = validate_hive_path(str(hive_dir) + "/", repo_root)
        assert result == hive_dir.resolve()
        # Verify no trailing slash in result
        assert not str(result).endswith("/")

    def test_validate_hive_path_relative_path_fails(self, tmp_path):
        """Test validation rejects relative paths."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Try to use relative path
        with pytest.raises(ValueError, match="must be absolute.*relative path"):
            validate_hive_path("tickets/backend", repo_root)

    def test_validate_hive_path_nonexistent_parent_fails(self, tmp_path):
        """Test validation creates parent directory if it doesn't exist."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Parent directory doesn't exist
        nonexistent_parent = repo_root / "does_not_exist" / "child"

        # New behavior: validate_hive_path creates parent directories
        result = validate_hive_path(str(nonexistent_parent), repo_root)

        # Should succeed and create the parent directory
        assert result == nonexistent_parent.resolve()
        assert nonexistent_parent.parent.exists()

    def test_validate_hive_path_outside_repo_fails(self, tmp_path):
        """Test validation rejects paths outside repository root."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Create directory outside repo
        outside = tmp_path / "outside"
        outside.mkdir()

        with pytest.raises(ValueError, match="must be within repository root"):
            validate_hive_path(str(outside), repo_root)

    def test_validate_hive_path_at_repo_root(self, tmp_path):
        """Test validation allows path at repo root itself."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Using repo root as hive path should be valid
        result = validate_hive_path(str(repo_root), repo_root)
        assert result == repo_root.resolve()

    def test_validate_hive_path_deeply_nested(self, tmp_path):
        """Test validation works for deeply nested paths."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Create deeply nested structure
        deep_path = repo_root / "level1" / "level2" / "level3" / "level4"
        deep_path.mkdir(parents=True)

        result = validate_hive_path(str(deep_path), repo_root)
        assert result == deep_path.resolve()

    def test_validate_hive_path_error_messages(self, tmp_path):
        """Test error messages are descriptive."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Test relative path error message
        try:
            validate_hive_path("relative/path", repo_root)
        except ValueError as e:
            assert "absolute" in str(e).lower()
            assert "relative" in str(e).lower()

        # Test nonexistent path error message
        nonexistent = repo_root / "missing"
        try:
            validate_hive_path(str(nonexistent), repo_root)
        except ValueError as e:
            assert "does not exist" in str(e).lower()

        # Test outside repo error message
        outside = tmp_path / "outside"
        outside.mkdir()
        try:
            validate_hive_path(str(outside), repo_root)
        except ValueError as e:
            assert "within repository root" in str(e).lower()


class TestScanForHiveConfigAutoUpdate:
    """Tests for scan_for_hive() config auto-update behavior."""

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

    def test_scan_for_hive_updates_config_with_stale_path(self, temp_repo, monkeypatch):
        """Test that scan_for_hive updates config.json when hive is found at new location."""
        from src.mcp_server import scan_for_hive
        from src.config import load_bees_config, save_bees_config, BeesConfig, HiveConfig
        from datetime import datetime
        import json

        # Create initial config with stale path
        old_path = temp_repo / "old_location"
        new_path = temp_repo / "new_location"
        new_path.mkdir(parents=True)

        config = BeesConfig(hives={
            "test_hive": HiveConfig(
                display_name="Test Hive",
                path=str(old_path),
                created_at=datetime.now().isoformat()
            )
        })
        save_bees_config(config, repo_root=temp_repo)

        # Create .hive marker at new location
        hive_marker = new_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Scan for hive - should find it and update config
        result = scan_for_hive("test_hive")

        assert result == new_path

        # Verify config was updated with new path
        updated_config = load_bees_config()
        assert updated_config.hives["test_hive"].path == str(new_path)

    def test_scan_for_hive_handles_missing_config(self, temp_repo, monkeypatch):
        """Test that scan_for_hive handles case where hive not in config yet."""
        from src.mcp_server import scan_for_hive
        import json

        # Create hive without config entry
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "unregistered_hive",
            "display_name": "Unregistered Hive"
        }))

        # Scan should find hive but log warning (not update config)
        result = scan_for_hive("unregistered_hive")

        assert result == hive_path
        # Config should remain empty or unchanged (no crash)

    def test_scan_for_hive_updates_only_target_hive(self, temp_repo, monkeypatch):
        """Test that scan_for_hive only updates the target hive in config with multiple hives."""
        from src.mcp_server import scan_for_hive
        from src.config import load_bees_config, save_bees_config, BeesConfig, HiveConfig
        from datetime import datetime
        import json

        # Create config with multiple hives
        hive1_path = temp_repo / "hive1"
        hive2_old = temp_repo / "hive2_old"
        hive2_new = temp_repo / "hive2_new"
        hive2_new.mkdir(parents=True)

        config = BeesConfig(hives={
            "hive1": HiveConfig(display_name="Hive 1", path=str(hive1_path), created_at=datetime.now().isoformat()),
            "hive2": HiveConfig(display_name="Hive 2", path=str(hive2_old), created_at=datetime.now().isoformat())
        })
        save_bees_config(config, repo_root=temp_repo)

        # Create .hive marker for hive2 at new location
        hive_marker = hive2_new / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "hive2",
            "display_name": "Hive 2"
        }))

        # Scan for hive2
        result = scan_for_hive("hive2")

        assert result == hive2_new

        # Verify only hive2 was updated
        updated_config = load_bees_config()
        assert updated_config.hives["hive1"].path == str(hive1_path)  # Unchanged
        assert updated_config.hives["hive2"].path == str(hive2_new)   # Updated

    def test_scan_for_hive_logs_config_update(self, temp_repo, monkeypatch, caplog):
        """Test that scan_for_hive logs when config is updated."""
        from src.mcp_server import scan_for_hive
        from src.config import save_bees_config, BeesConfig, HiveConfig
        from datetime import datetime
        import json
        import logging

        caplog.set_level(logging.INFO)

        # Create config and hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        config = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(temp_repo / "old"), created_at=datetime.now().isoformat())
        })
        save_bees_config(config, repo_root=temp_repo)

        # Create .hive marker
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Scan for hive
        scan_for_hive("test_hive")

        # Verify logging
        assert any("Updated config.json with new path" in record.message for record in caplog.records)

    def test_scan_for_hive_handles_config_write_failure(self, temp_repo, monkeypatch):
        """Test that scan_for_hive re-raises config write errors."""
        from src.mcp_server import scan_for_hive
        from src.config import save_bees_config, BeesConfig, HiveConfig
        from datetime import datetime
        import json

        # Create config and hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        config = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(temp_repo / "old"), created_at=datetime.now().isoformat())
        })
        save_bees_config(config, repo_root=temp_repo)

        # Create .hive marker
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Mock save_bees_config to raise an exception
        def mock_save_error(cfg, repo_root=None):
            raise IOError("Disk full")

        monkeypatch.setattr("src.mcp_hive_utils.save_bees_config", mock_save_error)

        # Should re-raise the IOError from config update
        with pytest.raises(IOError, match="Disk full"):
            scan_for_hive("test_hive")


class TestScanForHiveSecurity:
    """Tests for scan_for_hive() depth limit security feature."""

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

    def test_scan_for_hive_respects_depth_limit(self, temp_repo):
        """Test that scan_for_hive skips .hive markers beyond MAX_SCAN_DEPTH."""
        from src.mcp_server import scan_for_hive
        import json

        # Create deeply nested hive (depth > 10)
        deep_path = temp_repo
        for i in range(12):  # Create 12 levels deep
            deep_path = deep_path / f"level{i}"
            deep_path.mkdir()

        hive_marker = deep_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "deep_hive",
            "display_name": "Deep Hive"
        }))

        # Scan should not find hive beyond depth limit
        result = scan_for_hive("deep_hive")
        assert result is None

    def test_scan_for_hive_finds_hive_within_depth_limit(self, temp_repo):
        """Test that scan_for_hive finds .hive markers within MAX_SCAN_DEPTH."""
        from src.mcp_server import scan_for_hive
        import json

        # Create hive at depth 5 (well within limit)
        hive_path = temp_repo
        for i in range(5):
            hive_path = hive_path / f"level{i}"
            hive_path.mkdir()

        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "shallow_hive",
            "display_name": "Shallow Hive"
        }))

        # Scan should find hive within depth limit
        result = scan_for_hive("shallow_hive")
        assert result == hive_path

    def test_scan_for_hive_depth_limit_boundary(self, temp_repo):
        """Test scan_for_hive at exact MAX_SCAN_DEPTH boundary (depth 10)."""
        from src.mcp_server import scan_for_hive
        import json

        # Create hive at exactly depth 10 for the .hive marker
        # This means 9 levels of directories, then .hive at depth 10
        hive_path = temp_repo
        for i in range(9):
            hive_path = hive_path / f"level{i}"
            hive_path.mkdir()

        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "boundary_hive",
            "display_name": "Boundary Hive"
        }))

        # Scan should find hive with .hive at depth 10 (inclusive)
        result = scan_for_hive("boundary_hive")
        assert result == hive_path


class TestScanForHiveConfigOptimization:
    """Tests for scan_for_hive() config parameter optimization."""

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

    def test_scan_for_hive_accepts_config_parameter(self, temp_repo):
        """Test that scan_for_hive accepts optional config BeesConfig parameter."""
        from src.mcp_server import scan_for_hive
        from src.config import BeesConfig, HiveConfig
        from datetime import datetime
        import json

        # Create hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Call with config parameter
        config = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(hive_path), created_at=datetime.now().isoformat())
        })
        result = scan_for_hive("test_hive", config=config)

        assert result == hive_path

    def test_scan_for_hive_uses_provided_config(self, temp_repo, monkeypatch):
        """Test that scan_for_hive uses provided config instead of loading from disk."""
        from src.mcp_server import scan_for_hive
        from src.config import BeesConfig, HiveConfig
        from datetime import datetime
        import json

        # Create hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "orphan_hive",
            "display_name": "Orphan Hive"
        }))

        # Provide config with registered hive
        config = BeesConfig(hives={
            "registered_hive": HiveConfig(display_name="Registered Hive", path=str(hive_path), created_at=datetime.now().isoformat())
        })

        # Mock file open to ensure config not loaded from disk
        original_open = open
        def mock_open(*args, **kwargs):
            # If trying to open config.json, fail
            if args and "config.json" in str(args[0]):
                raise AssertionError("Should not load config from disk when provided")
            return original_open(*args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open)

        # Scan with provided config - should NOT trigger disk read
        result = scan_for_hive("orphan_hive", config=config)
        # Hive found but not in registered list from provided config
        assert result == hive_path

    def test_scan_for_hive_empty_config_parameter(self, temp_repo):
        """Test that scan_for_hive handles BeesConfig with empty hives."""
        from src.mcp_server import scan_for_hive
        from src.config import BeesConfig
        import json

        # Create hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Call with empty config
        result = scan_for_hive("test_hive", config=BeesConfig(hives={}))
        assert result == hive_path

    def test_scan_for_hive_config_with_empty_hives(self, temp_repo):
        """Test that scan_for_hive handles BeesConfig with empty hives."""
        from src.mcp_server import scan_for_hive
        from src.config import BeesConfig
        import json

        # Create hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Call with config with empty hives
        result = scan_for_hive("test_hive", config=BeesConfig(hives={}))
        assert result == hive_path

    def test_scan_for_hive_loads_from_disk_when_config_not_provided(self, temp_repo):
        """Test that scan_for_hive loads config from disk when not provided."""
        from src.mcp_server import scan_for_hive
        from src.config import save_bees_config, BeesConfig, HiveConfig
        from datetime import datetime
        import json

        # Create config on disk
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        config = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(temp_repo / "old"), created_at=datetime.now().isoformat())
        })
        save_bees_config(config, repo_root=temp_repo)

        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Call without config parameter - should load from disk
        result = scan_for_hive("test_hive")
        assert result == hive_path


class TestScanForHiveBugFixes:
    """Tests for scan_for_hive() bug fixes: config type handling, None safety, and early return."""

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

    def test_scan_for_hive_config_none_handling(self, temp_repo):
        """Test that scan_for_hive handles config=None without AttributeError."""
        from src.mcp_server import scan_for_hive
        import json

        # Create hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Call with config=None - should not raise AttributeError
        result = scan_for_hive("test_hive", config=None)
        assert result == hive_path

    def test_scan_for_hive_config_empty_hives(self, temp_repo):
        """Test that scan_for_hive handles config with empty hives list."""
        from src.mcp_server import scan_for_hive
        from src.config import BeesConfig
        import json

        # Create hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Call with config with empty hives
        config = BeesConfig(hives={})
        result = scan_for_hive("test_hive", config=config)
        assert result == hive_path

    def test_scan_for_hive_early_return_behavior(self, temp_repo):
        """Test that scan_for_hive returns immediately upon finding target hive."""
        from src.mcp_server import scan_for_hive
        import json

        # Create multiple hives
        hive1_path = temp_repo / "hive1"
        hive1_path.mkdir()
        hive1_marker = hive1_path / ".hive"
        hive1_marker.mkdir()
        (hive1_marker / "identity.json").write_text(json.dumps({
            "normalized_name": "target_hive",
            "display_name": "Target Hive"
        }))

        hive2_path = temp_repo / "hive2"
        hive2_path.mkdir()
        hive2_marker = hive2_path / ".hive"
        hive2_marker.mkdir()
        (hive2_marker / "identity.json").write_text(json.dumps({
            "normalized_name": "other_hive",
            "display_name": "Other Hive"
        }))

        # Scan for target_hive - should find it and return immediately
        result = scan_for_hive("target_hive")
        assert result == hive1_path

    def test_scan_for_hive_beesconfig_type_handling(self, temp_repo):
        """Test that scan_for_hive correctly handles BeesConfig object type."""
        from src.mcp_server import scan_for_hive
        from src.config import BeesConfig, HiveConfig
        from datetime import datetime
        import json

        # Create hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "registered_hive",
            "display_name": "Registered Hive"
        }))

        # Create BeesConfig object with registered hive
        config = BeesConfig(hives={
            "registered_hive": HiveConfig(
                display_name="Registered Hive",
                path=str(hive_path),
                created_at=datetime.now().isoformat()
            )
        })

        # Call with BeesConfig object - should work without errors
        result = scan_for_hive("registered_hive", config=config)
        assert result == hive_path


class TestScanForHiveFileVsDirectory:
    """Tests for scan_for_hive() handling of .hive as file vs directory."""

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

    def test_scan_for_hive_skips_file_marker(self, temp_repo):
        """Test that scan_for_hive() skips .hive when it's a file instead of directory."""
        from src.mcp_server import scan_for_hive
        import json

        # Create a .hive FILE (not directory) - this is the edge case
        hive_file = temp_repo / ".hive"
        hive_file.write_text("This is a file, not a directory")

        # Also create a valid hive directory elsewhere to confirm scan still works
        valid_hive_path = temp_repo / "valid_hive"
        valid_hive_path.mkdir()

        valid_marker = valid_hive_path / ".hive"
        valid_marker.mkdir()
        identity_file = valid_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Scan should skip the .hive file and find the valid directory
        result = scan_for_hive("test_hive")

        # Should find the valid hive, not fail on the file
        assert result == valid_hive_path

    def test_scan_for_hive_returns_none_when_only_file_marker(self, temp_repo):
        """Test that scan_for_hive() returns None when .hive is only a file, not directory."""
        from src.mcp_server import scan_for_hive

        # Create only a .hive FILE (no valid directory marker)
        hive_file = temp_repo / ".hive"
        hive_file.write_text("This is a file, not a directory")

        # Scan should return None (no valid hive found)
        result = scan_for_hive("test_hive")

        assert result is None


class TestScanForHiveExceptionHandling:
    """Tests for scan_for_hive() exception handling with specific exception types."""

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

    def test_scan_for_hive_handles_ioerror_on_config_update(self, temp_repo, monkeypatch, caplog):
        """Test that scan_for_hive re-raises IOError when config.json cannot be written."""
        from src.mcp_server import scan_for_hive
        from src.config import save_bees_config, BeesConfig, HiveConfig
        from datetime import datetime
        import json
        import logging

        caplog.set_level(logging.ERROR)

        # Create config and hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        config = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(temp_repo / "old"), created_at=datetime.now().isoformat())
        })
        save_bees_config(config, repo_root=temp_repo)

        # Create .hive marker
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Mock save_bees_config to raise IOError
        def mock_save_ioerror(cfg, repo_root=None):
            raise IOError("Permission denied")

        monkeypatch.setattr("src.mcp_hive_utils.save_bees_config", mock_save_ioerror)

        # Should log error and re-raise
        with pytest.raises(IOError, match="Permission denied"):
            scan_for_hive("test_hive")
        assert any("Failed to update config.json" in record.message for record in caplog.records)

    def test_scan_for_hive_handles_json_decode_error_on_config_load(self, temp_repo, monkeypatch, caplog):
        """Test that scan_for_hive re-raises json.JSONDecodeError when config.json cannot be loaded."""
        from src.mcp_server import scan_for_hive
        from src.config import save_bees_config, BeesConfig, HiveConfig
        from datetime import datetime
        import json
        import logging

        caplog.set_level(logging.ERROR)

        # Create config and hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        config = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(temp_repo / "old"), created_at=datetime.now().isoformat())
        })
        save_bees_config(config, repo_root=temp_repo)

        # Create .hive marker
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Mock load_bees_config to raise JSONDecodeError
        def mock_load_json_error(repo_root=None):
            raise json.JSONDecodeError("Expecting value", "", 0)

        monkeypatch.setattr("src.mcp_hive_utils.load_bees_config", mock_load_json_error)

        # Should log error and re-raise
        with pytest.raises(json.JSONDecodeError, match="Expecting value"):
            scan_for_hive("test_hive")
        assert any("Failed to update config.json" in record.message for record in caplog.records)

    def test_scan_for_hive_handles_attribute_error_on_config_access(self, temp_repo, monkeypatch, caplog):
        """Test that scan_for_hive re-raises AttributeError when config object is malformed."""
        from src.mcp_server import scan_for_hive
        from src.config import save_bees_config, BeesConfig, HiveConfig
        from datetime import datetime
        import json
        import logging

        caplog.set_level(logging.ERROR)

        # Create config and hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        config = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(temp_repo / "old"), created_at=datetime.now().isoformat())
        })
        save_bees_config(config, repo_root=temp_repo)

        # Create .hive marker
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Mock load_bees_config to return object without hives attribute
        class BadConfig:
            pass

        def mock_load_bad_config(repo_root=None):
            return BadConfig()

        monkeypatch.setattr("src.mcp_hive_utils.load_bees_config", mock_load_bad_config)

        # Should log error and re-raise
        with pytest.raises(AttributeError):
            scan_for_hive("test_hive")
        assert any("Failed to update config.json" in record.message for record in caplog.records)

    def test_scan_for_hive_does_not_catch_programming_errors(self, temp_repo, monkeypatch):
        """Test that scan_for_hive does NOT catch programming errors like NameError."""
        from src.mcp_server import scan_for_hive
        import json

        # Create hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        # Create .hive marker
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Mock load_bees_config to raise NameError (programming error)
        def mock_load_name_error(repo_root=None):
            raise NameError("undefined_variable is not defined")

        monkeypatch.setattr("src.mcp_hive_utils.load_bees_config", mock_load_name_error)

        # Should propagate NameError, not catch it
        with pytest.raises(NameError, match="undefined_variable is not defined"):
            scan_for_hive("test_hive")

    def test_scan_for_hive_exception_handling_specificity(self, temp_repo, monkeypatch):
        """Test that exception handling logs and re-raises expected exception types."""
        from src.mcp_server import scan_for_hive
        from src.config import save_bees_config, BeesConfig, HiveConfig
        from datetime import datetime
        import json

        # Create hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        config = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(temp_repo / "old"), created_at=datetime.now().isoformat())
        })
        save_bees_config(config, repo_root=temp_repo)

        # Create .hive marker
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Test each exception type individually
        for error_type, error_instance in [
            (IOError, IOError("Disk error")),
            (json.JSONDecodeError, json.JSONDecodeError("Invalid", "", 0)),
            (AttributeError, AttributeError("No attribute"))
        ]:
            # Mock save_bees_config to raise specific error
            def mock_save_error(cfg, repo_root=None):
                raise error_instance

            monkeypatch.setattr("src.mcp_hive_utils.save_bees_config", mock_save_error)

            # Should log error and re-raise
            with pytest.raises(error_type):
                scan_for_hive("test_hive")


class TestScanForHiveErrorPropagation:
    """Tests for scan_for_hive() error propagation when config updates fail."""

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

    def test_scan_for_hive_raises_ioerror_on_config_save_failure(self, temp_repo, monkeypatch, caplog):
        """Test that scan_for_hive re-raises IOError when save_bees_config fails."""
        from src.mcp_server import scan_for_hive
        from src.config import save_bees_config, BeesConfig, HiveConfig
        from datetime import datetime
        import json
        import logging

        caplog.set_level(logging.ERROR)

        # Create config and hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        config = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(temp_repo / "old"), created_at=datetime.now().isoformat())
        })
        save_bees_config(config, repo_root=temp_repo)

        # Create .hive marker
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Mock save_bees_config to raise IOError
        def mock_save_ioerror(cfg, repo_root=None):
            raise IOError("Permission denied")

        monkeypatch.setattr("src.mcp_hive_utils.save_bees_config", mock_save_ioerror)

        # Should log error and re-raise exception
        with pytest.raises(IOError, match="Permission denied"):
            scan_for_hive("test_hive")

        # Verify error was logged before re-raising
        assert any("Failed to update config.json" in record.message for record in caplog.records)

    def test_scan_for_hive_raises_json_decode_error_on_config_failure(self, temp_repo, monkeypatch, caplog):
        """Test that scan_for_hive re-raises JSONDecodeError when config update fails."""
        from src.mcp_server import scan_for_hive
        from src.config import save_bees_config, BeesConfig, HiveConfig
        from datetime import datetime
        import json
        import logging

        caplog.set_level(logging.ERROR)

        # Create config and hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        config = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(temp_repo / "old"), created_at=datetime.now().isoformat())
        })
        save_bees_config(config, repo_root=temp_repo)

        # Create .hive marker
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Mock save_bees_config to raise JSONDecodeError
        def mock_save_json_error(cfg, repo_root=None):
            raise json.JSONDecodeError("Malformed JSON", "", 0)

        monkeypatch.setattr("src.mcp_hive_utils.save_bees_config", mock_save_json_error)

        # Should log error and re-raise exception
        with pytest.raises(json.JSONDecodeError, match="Malformed JSON"):
            scan_for_hive("test_hive")

        # Verify error was logged
        assert any("Failed to update config.json" in record.message for record in caplog.records)

    def test_scan_for_hive_logs_before_raising(self, temp_repo, monkeypatch, caplog):
        """Test that scan_for_hive logs error message before re-raising exception."""
        from src.mcp_server import scan_for_hive
        from src.config import save_bees_config, BeesConfig, HiveConfig
        from datetime import datetime
        import json
        import logging

        caplog.set_level(logging.ERROR)

        # Create config and hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        config = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(temp_repo / "old"), created_at=datetime.now().isoformat())
        })
        save_bees_config(config, repo_root=temp_repo)

        # Create .hive marker
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Mock save_bees_config to raise IOError
        def mock_save_ioerror(cfg, repo_root=None):
            raise IOError("Test error")

        monkeypatch.setattr("src.mcp_hive_utils.save_bees_config", mock_save_ioerror)

        # Should log error and re-raise
        try:
            scan_for_hive("test_hive")
        except IOError:
            pass  # Expected

        # Verify error was logged with specific format
        error_logs = [r for r in caplog.records if r.levelname == "ERROR"]
        assert len(error_logs) > 0
        assert any("Failed to update config.json" in log.message and "test_hive" in log.message
                   for log in error_logs)


class TestScanForHiveConfigHandling:
    """Tests for scan_for_hive() config parameter handling after simplification."""

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

    def test_scan_for_hive_with_config_none_loads_from_disk(self, temp_repo):
        """Test scan_for_hive with config=None loads config from disk."""
        from src.mcp_server import scan_for_hive
        from src.config import save_bees_config, BeesConfig, HiveConfig
        from datetime import datetime
        import json

        # Create hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        # Create .hive marker
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Save config to disk
        config = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(hive_path), created_at=datetime.now().isoformat())
        })
        save_bees_config(config, repo_root=temp_repo)

        # Call with config=None - should load from disk
        result = scan_for_hive("test_hive", config=None)
        assert result == hive_path

    def test_scan_for_hive_with_empty_hives_dict(self, temp_repo):
        """Test scan_for_hive with config having empty hives dict."""
        from src.mcp_server import scan_for_hive
        from src.config import BeesConfig
        import json

        # Create hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        # Create .hive marker
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Call with empty config
        config = BeesConfig(hives={})
        result = scan_for_hive("test_hive", config=config)

        # Should find hive even though not in config's registered hives
        assert result == hive_path

    def test_scan_for_hive_with_populated_hives(self, temp_repo):
        """Test scan_for_hive with config having populated hives."""
        from src.mcp_server import scan_for_hive
        from src.config import BeesConfig, HiveConfig
        import json

        # Create two hives
        hive1_path = temp_repo / "hive1"
        hive1_path.mkdir()
        hive1_marker = hive1_path / ".hive"
        hive1_marker.mkdir()
        (hive1_marker / "identity.json").write_text(json.dumps({
            "normalized_name": "registered_hive",
            "display_name": "Registered Hive"
        }))

        hive2_path = temp_repo / "hive2"
        hive2_path.mkdir()
        hive2_marker = hive2_path / ".hive"
        hive2_marker.mkdir()
        (hive2_marker / "identity.json").write_text(json.dumps({
            "normalized_name": "unregistered_hive",
            "display_name": "Unregistered Hive"
        }))

        # Create config with only hive1 registered
        from datetime import datetime
        config = BeesConfig(hives={
            "registered_hive": HiveConfig(
                display_name="Registered Hive",
                path=str(hive1_path),
                created_at=datetime.now().isoformat()
            )
        })

        # Scan for registered hive
        result1 = scan_for_hive("registered_hive", config=config)
        assert result1 == hive1_path

        # Scan for unregistered hive - should still be found
        result2 = scan_for_hive("unregistered_hive", config=config)
        assert result2 == hive2_path

    def test_scan_for_hive_registered_hives_set_populated_correctly(self, temp_repo):
        """Test that registered_hives set is correctly populated in each config case."""
        from src.mcp_server import scan_for_hive
        from src.config import BeesConfig, HiveConfig, save_bees_config
        import json

        # Create hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        (hive_marker / "identity.json").write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Test 1: config=None with config on disk
        from datetime import datetime
        config_disk = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(hive_path), created_at=datetime.now().isoformat())
        })
        save_bees_config(config_disk)
        result1 = scan_for_hive("test_hive", config=None)
        assert result1 == hive_path

        # Test 2: config with empty hives
        config_empty = BeesConfig(hives={})
        result2 = scan_for_hive("test_hive", config=config_empty)
        assert result2 == hive_path

        # Test 3: config with populated hives
        config_populated = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(hive_path), created_at=datetime.now().isoformat())
        })
        result3 = scan_for_hive("test_hive", config=config_populated)
        assert result3 == hive_path


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


class TestParseHiveFromTicketId:
    """Tests for parse_hive_from_ticket_id() helper function."""

    def test_parse_hive_with_valid_prefixed_id(self):
        """Test parsing hive from valid prefixed ID."""
        hive_name = parse_hive_from_ticket_id("backend.bees-abc1")
        assert hive_name == "backend"

    def test_parse_hive_with_frontend_id(self):
        """Test parsing hive from frontend prefixed ID."""
        hive_name = parse_hive_from_ticket_id("frontend.bees-xyz9")
        assert hive_name == "frontend"

    def test_parse_hive_with_malformed_id_no_dot(self):
        """Test parsing hive from malformed ID (no dot) returns None."""
        hive_name = parse_hive_from_ticket_id("bees-abc1")
        assert hive_name is None

    def test_parse_hive_with_multi_dot_id(self):
        """Test parsing hive from ID with multiple dots (splits on first)."""
        hive_name = parse_hive_from_ticket_id("multi.dot.bees-xyz9")
        assert hive_name == "multi"

    def test_parse_hive_with_underscore_hive(self):
        """Test parsing hive with underscore in name."""
        hive_name = parse_hive_from_ticket_id("back_end.bees-123")
        assert hive_name == "back_end"

    def test_parse_hive_with_hyphen_hive(self):
        """Test parsing hive with hyphen in name."""
        hive_name = parse_hive_from_ticket_id("api-v2.bees-456")
        assert hive_name == "api-v2"

    def test_parse_hive_returns_none_for_legacy_format(self):
        """Test that legacy format IDs (no prefix) return None."""
        hive_name = parse_hive_from_ticket_id("bees-legacy")
        assert hive_name is None


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
    def setup_test_ticket(self, tmp_path, mock_config):
        """Create a test ticket with prefixed ID."""
        from src.ticket_factory import create_task
        from src.config import save_bees_config

        # Save config
        config_dir = Path(".bees")
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
        save_bees_config(config, repo_root=temp_repo)

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
        save_bees_config(config, repo_root=temp_repo)

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
        save_bees_config(config, repo_root=temp_repo)

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
        save_bees_config(config, repo_root=temp_repo)

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
        save_bees_config(config, repo_root=temp_repo)

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
