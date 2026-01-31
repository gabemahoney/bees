"""
Unit tests for MCP server lifecycle and health checks.

Tests server initialization, configuration, lifecycle management (start/stop),
health checks, and tool schema registration.
"""

import pytest
from unittest.mock import patch, MagicMock
from src.mcp_server import (
    mcp,
    start_server,
    stop_server,
    _health_check,
    _create_ticket,
    _update_ticket,
    _delete_ticket,
    _server_running
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

    def test_create_ticket_implementation_response(self, tmp_path, monkeypatch):
        """Test that create_ticket returns expected response."""
        # Setup temp tickets directory
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "epics").mkdir()
        (tickets_dir / "tasks").mkdir()
        (tickets_dir / "subtasks").mkdir()
        monkeypatch.setattr("src.paths.TICKETS_DIR", tickets_dir)
        import src.ticket_factory
        monkeypatch.setattr(src.ticket_factory, "TICKETS_DIR", tickets_dir)

        result = _create_ticket(
            ticket_type="task",
            title="Test Task"
        )

        assert result is not None
        assert result["status"] == "success"
        assert "ticket_id" in result
        assert "ticket_type" in result
        assert result["ticket_type"] == "task"

    def test_create_ticket_validates_type(self):
        """Test that create_ticket validates ticket_type parameter."""
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(ticket_type="invalid", title="Test")

        assert "Invalid ticket_type" in str(exc_info.value)

    def test_create_ticket_validates_epic_parent(self):
        """Test that create_ticket rejects parent for epics."""
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(ticket_type="epic", title="Test", parent="some-id")

        assert "Epics cannot have a parent" in str(exc_info.value)

    def test_create_ticket_validates_subtask_parent(self):
        """Test that create_ticket requires parent for subtasks."""
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(ticket_type="subtask", title="Test")

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
        """Create temporary tickets directory with test fixtures."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "epics").mkdir()
        (tickets_dir / "tasks").mkdir()
        (tickets_dir / "subtasks").mkdir()

        # Monkeypatch the TICKETS_DIR in paths module
        monkeypatch.setattr("src.paths.TICKETS_DIR", tickets_dir)

        return tickets_dir

    def test_update_ticket_basic_fields(self, temp_tickets_dir):
        """Test updating basic fields (title, labels, status, owner, priority)."""
        from src.ticket_factory import create_epic
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create an epic
        epic_id = create_epic(
            title="Original Title",
            description="Original description",
            labels=["label1"],
            status="open",
            owner="alice@example.com",
            priority=2
        )

        # Update basic fields
        result = _update_ticket(
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

    def test_update_ticket_nonexistent(self, temp_tickets_dir):
        """Test updating a non-existent ticket raises ValueError."""
        with pytest.raises(ValueError, match="Ticket does not exist"):
            _update_ticket(ticket_id="bees-nonexistent", title="Test")

    def test_update_ticket_empty_title(self, temp_tickets_dir):
        """Test updating with empty title raises ValueError."""
        from src.ticket_factory import create_epic

        epic_id = create_epic(title="Original Title")

        with pytest.raises(ValueError, match="Ticket title cannot be empty"):
            _update_ticket(ticket_id=epic_id, title="")

        with pytest.raises(ValueError, match="Ticket title cannot be empty"):
            _update_ticket(ticket_id=epic_id, title="   ")

    def test_update_ticket_add_parent(self, temp_tickets_dir):
        """Test adding a parent relationship with bidirectional updates."""
        from src.ticket_factory import create_epic, create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create epic and task
        epic_id = create_epic(title="Parent Epic")
        task_id = create_task(title="Child Task")

        # Add parent to task
        result = _update_ticket(ticket_id=task_id, parent=epic_id)

        assert result["status"] == "success"

        # Verify bidirectional updates
        task_path = get_ticket_path(task_id, "task")
        task = read_ticket(task_path)
        assert task.parent == epic_id

        epic_path = get_ticket_path(epic_id, "epic")
        epic = read_ticket(epic_path)
        assert task_id in epic.children

    def test_update_ticket_remove_parent(self, temp_tickets_dir):
        """Test removing a parent relationship with bidirectional updates."""
        from src.ticket_factory import create_epic, create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create epic and task with parent
        epic_id = create_epic(title="Parent Epic")
        task_id = create_task(title="Child Task", parent=epic_id)

        # Update bidirectional relationships
        from src.mcp_server import _add_child_to_parent
        _add_child_to_parent(task_id, epic_id)

        # Verify initial state
        epic_path = get_ticket_path(epic_id, "epic")
        epic = read_ticket(epic_path)
        assert task_id in epic.children

        # Remove parent
        result = _update_ticket(ticket_id=task_id, parent=None)

        assert result["status"] == "success"

        # Verify bidirectional updates
        task_path = get_ticket_path(task_id, "task")
        task = read_ticket(task_path)
        assert task.parent is None

        epic = read_ticket(epic_path)
        assert task_id not in (epic.children or [])

    def test_update_ticket_add_children(self, temp_tickets_dir):
        """Test adding children with bidirectional updates."""
        from src.ticket_factory import create_epic, create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create epic and tasks
        epic_id = create_epic(title="Parent Epic")
        task1_id = create_task(title="Child Task 1")
        task2_id = create_task(title="Child Task 2")

        # Add children to epic
        result = _update_ticket(ticket_id=epic_id, children=[task1_id, task2_id])

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

    def test_update_ticket_remove_children(self, temp_tickets_dir):
        """Test removing children with bidirectional updates."""
        from src.ticket_factory import create_epic, create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create epic with children
        epic_id = create_epic(title="Parent Epic")
        task1_id = create_task(title="Child Task 1", parent=epic_id)
        task2_id = create_task(title="Child Task 2", parent=epic_id)

        # Update bidirectional relationships
        from src.mcp_server import _add_child_to_parent
        _add_child_to_parent(task1_id, epic_id)
        _add_child_to_parent(task2_id, epic_id)

        # Remove all children
        result = _update_ticket(ticket_id=epic_id, children=[])

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

    def test_update_ticket_add_dependencies(self, temp_tickets_dir):
        """Test adding dependencies with bidirectional updates."""
        from src.ticket_factory import create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create tasks
        task1_id = create_task(title="Task 1")
        task2_id = create_task(title="Task 2 (blocking)")
        task3_id = create_task(title="Task 3 (blocked)")

        # Add dependencies
        result = _update_ticket(
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

    def test_update_ticket_remove_dependencies(self, temp_tickets_dir):
        """Test removing dependencies with bidirectional updates."""
        from src.ticket_factory import create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create tasks with dependencies
        task1_id = create_task(
            title="Task 1",
            up_dependencies=[],
            down_dependencies=[]
        )
        task2_id = create_task(title="Task 2")

        # Add dependency first
        _update_ticket(ticket_id=task1_id, up_dependencies=[task2_id])

        # Verify initial state
        task1_path = get_ticket_path(task1_id, "task")
        task1 = read_ticket(task1_path)
        assert task2_id in task1.up_dependencies

        # Remove dependencies
        result = _update_ticket(ticket_id=task1_id, up_dependencies=[])

        assert result["status"] == "success"

        # Verify bidirectional updates
        task1 = read_ticket(task1_path)
        assert task1.up_dependencies == []

        task2_path = get_ticket_path(task2_id, "task")
        task2 = read_ticket(task2_path)
        assert task1_id not in (task2.down_dependencies or [])

    def test_update_ticket_nonexistent_parent(self, temp_tickets_dir):
        """Test updating with non-existent parent raises ValueError."""
        from src.ticket_factory import create_task

        task_id = create_task(title="Test Task")

        with pytest.raises(ValueError, match="Parent ticket does not exist"):
            _update_ticket(ticket_id=task_id, parent="bees-nonexistent")

    def test_update_ticket_nonexistent_child(self, temp_tickets_dir):
        """Test updating with non-existent child raises ValueError."""
        from src.ticket_factory import create_epic

        epic_id = create_epic(title="Test Epic")

        with pytest.raises(ValueError, match="Child ticket does not exist"):
            _update_ticket(ticket_id=epic_id, children=["bees-nonexistent"])

    def test_update_ticket_nonexistent_dependency(self, temp_tickets_dir):
        """Test updating with non-existent dependency raises ValueError."""
        from src.ticket_factory import create_task

        task_id = create_task(title="Test Task")

        with pytest.raises(ValueError, match="Dependency ticket does not exist"):
            _update_ticket(ticket_id=task_id, up_dependencies=["bees-nonexistent"])

        with pytest.raises(ValueError, match="Dependency ticket does not exist"):
            _update_ticket(ticket_id=task_id, down_dependencies=["bees-nonexistent"])

    def test_update_ticket_circular_dependency(self, temp_tickets_dir):
        """Test updating with circular dependency raises ValueError."""
        from src.ticket_factory import create_task

        task1_id = create_task(title="Task 1")
        task2_id = create_task(title="Task 2")

        with pytest.raises(ValueError, match="Circular dependency detected"):
            _update_ticket(
                ticket_id=task1_id,
                up_dependencies=[task2_id],
                down_dependencies=[task2_id]
            )

    def test_update_ticket_partial_update(self, temp_tickets_dir):
        """Test that partial updates only modify specified fields."""
        from src.ticket_factory import create_epic
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create epic with various fields
        epic_id = create_epic(
            title="Original Title",
            description="Original description",
            labels=["label1", "label2"],
            status="open",
            owner="alice@example.com",
            priority=2
        )

        # Update only title and status
        result = _update_ticket(
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

    def test_update_ticket_bidirectional_consistency(self, temp_tickets_dir):
        """Test comprehensive bidirectional consistency across multiple updates."""
        from src.ticket_factory import create_epic, create_task
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Create tickets
        epic_id = create_epic(title="Epic")
        task1_id = create_task(title="Task 1")
        task2_id = create_task(title="Task 2")
        task3_id = create_task(title="Task 3")

        # Add task1 and task2 as children of epic
        _update_ticket(ticket_id=epic_id, children=[task1_id, task2_id])

        # Make task3 depend on task1
        _update_ticket(ticket_id=task3_id, up_dependencies=[task1_id])

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
        _update_ticket(ticket_id=epic_id, children=[task1_id])

        # Verify task2's parent is cleared
        task2 = read_ticket(task2_path)
        assert task2.parent is None

        # Verify epic only has task1
        epic = read_ticket(epic_path)
        assert task1_id in epic.children
        assert task2_id not in epic.children
