"""
Unit tests for create_ticket MCP tool implementation.

Tests ticket creation with factory functions, bidirectional relationship updates,
validation, and error handling.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.mcp_server import _create_ticket
from src.reader import read_ticket
from src.paths import get_ticket_path


@pytest.fixture
def setup_tickets_dir(tmp_path, monkeypatch):
    """Create temporary hive directory structure for testing."""
    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Create default hive directory
    default_dir = tmp_path / "default"
    default_dir.mkdir()

    # Initialize .bees/config.json with default hive
    from src.config import save_bees_config, BeesConfig, HiveConfig
    from datetime import datetime

    config = BeesConfig(
        hives={
            'default': HiveConfig(
                path=str(default_dir),
                display_name='Default',
                created_at=datetime.now().isoformat()
            ),
        },
        allow_cross_hive_dependencies=True,
        schema_version='1.0'
    )
    save_bees_config(config, repo_root=tmp_path)

    yield tmp_path


class TestCreateEpic:
    """Tests for creating epic tickets."""

    async def test_create_epic_without_parent_success(self, setup_tickets_dir):
        """Test creating an epic without parent (valid case)."""
        result = await _create_ticket(
            ticket_type="epic",
            title="Test Epic",
            description="Test epic description",
            labels=["test", "epic"],
            priority=0,
            hive_name="default"
        )

        assert result["status"] == "success"
        assert "ticket_id" in result
        assert result["ticket_type"] == "epic"
        assert result["title"] == "Test Epic"

        # Verify ticket file was created
        ticket_id = result["ticket_id"]
        ticket_path = get_ticket_path(ticket_id, "epic")
        assert ticket_path.exists()

        # Verify ticket content
        ticket = read_ticket(ticket_path)
        assert ticket.title == "Test Epic"
        assert ticket.description == "Test epic description"
        assert "test" in ticket.labels
        assert ticket.priority == 0

    async def test_create_epic_with_parent_fails(self, setup_tickets_dir):
        """Test that creating an epic with parent raises error."""
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(
                ticket_type="epic",
                title="Test Epic",
                parent="bees-xyz",
                hive_name="default"
            )

        assert "Epics cannot have a parent" in str(exc_info.value)

    async def test_create_epic_with_dependencies(self, setup_tickets_dir):
        """Test creating epic with up/down dependencies."""
        # First create a dependency epic
        dep_result = await _create_ticket(
            ticket_type="epic",
            title="Dependency Epic",
            hive_name="default"
        )
        dep_id = dep_result["ticket_id"]

        # Create epic with dependency
        result = await _create_ticket(
            ticket_type="epic",
            title="Test Epic",
            up_dependencies=[dep_id],
            hive_name="default"
        )

        assert result["status"] == "success"
        ticket_id = result["ticket_id"]

        # Verify bidirectional update
        ticket = read_ticket(get_ticket_path(ticket_id, "epic"))
        assert dep_id in ticket.up_dependencies

        dep_ticket = read_ticket(get_ticket_path(dep_id, "epic"))
        assert ticket_id in dep_ticket.down_dependencies


class TestCreateTask:
    """Tests for creating task tickets."""

    async def test_create_task_with_parent_success(self, setup_tickets_dir):
        """Test creating a task with parent epic."""
        # First create parent epic
        epic_result = await _create_ticket(
            ticket_type="epic",
            title="Parent Epic",
            hive_name="default"
        )
        epic_id = epic_result["ticket_id"]

        # Create task with parent
        result = await _create_ticket(
            ticket_type="task",
            title="Test Task",
            parent=epic_id,
            description="Task description",
            labels=["backend"],
            hive_name="default"
        )

        assert result["status"] == "success"
        task_id = result["ticket_id"]
        assert result["ticket_type"] == "task"

        # Verify task has parent
        task = read_ticket(get_ticket_path(task_id, "task"))
        assert task.parent == epic_id

        # Verify parent has child (bidirectional update)
        epic = read_ticket(get_ticket_path(epic_id, "epic"))
        assert task_id in epic.children

    async def test_create_task_without_parent_success(self, setup_tickets_dir):
        """Test creating a task without parent (valid case)."""
        result = await _create_ticket(
            ticket_type="task",
            title="Standalone Task",
            hive_name="default"
        )

        assert result["status"] == "success"
        task_id = result["ticket_id"]

        task = read_ticket(get_ticket_path(task_id, "task"))
        assert task.parent is None or task.parent == ""

    async def test_create_task_with_nonexistent_parent_fails(self, setup_tickets_dir):
        """Test that creating task with non-existent parent fails."""
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(
                ticket_type="task",
                title="Test Task",
                parent="bees-nonexistent",
                hive_name="default"
            )

        assert "Parent ticket does not exist" in str(exc_info.value)


class TestCreateSubtask:
    """Tests for creating subtask tickets."""

    async def test_create_subtask_with_parent_success(self, setup_tickets_dir):
        """Test creating subtask with required parent task."""
        # Create parent task
        task_result = await _create_ticket(
            ticket_type="task",
            title="Parent Task",
            hive_name="default"
        )
        task_id = task_result["ticket_id"]

        # Create subtask with parent
        result = await _create_ticket(
            ticket_type="subtask",
            title="Test Subtask",
            parent=task_id,
            description="Subtask description",
            hive_name="default"
        )

        assert result["status"] == "success"
        subtask_id = result["ticket_id"]
        assert result["ticket_type"] == "subtask"

        # Verify subtask has parent
        subtask = read_ticket(get_ticket_path(subtask_id, "subtask"))
        assert subtask.parent == task_id

        # Verify parent has child (bidirectional update)
        task = read_ticket(get_ticket_path(task_id, "task"))
        assert subtask_id in task.children

    async def test_create_subtask_without_parent_fails(self, setup_tickets_dir):
        """Test that creating subtask without parent fails."""
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(
                ticket_type="subtask",
                title="Test Subtask",
                hive_name="default"
            )

        assert "Subtasks must have a parent" in str(exc_info.value)


class TestBidirectionalRelationships:
    """Tests for bidirectional relationship updates."""

    async def test_parent_children_bidirectional_update(self, setup_tickets_dir):
        """Test that parent's children array is updated when creating child."""
        # Create parent
        parent_result = await _create_ticket(
            ticket_type="epic",
            title="Parent Epic",
            hive_name="default"
        )
        parent_id = parent_result["ticket_id"]

        # Create child
        child_result = await _create_ticket(
            ticket_type="task",
            title="Child Task",
            parent=parent_id,
            hive_name="default"
        )
        child_id = child_result["ticket_id"]

        # Verify both sides of relationship
        parent = read_ticket(get_ticket_path(parent_id, "epic"))
        child = read_ticket(get_ticket_path(child_id, "task"))

        assert child.parent == parent_id
        assert child_id in parent.children

    async def test_up_dependencies_bidirectional_update(self, setup_tickets_dir):
        """Test that up_dependencies updates blocking ticket's down_dependencies."""
        # Create blocking ticket
        blocking_result = await _create_ticket(
            ticket_type="task",
            title="Blocking Task",
            hive_name="default"
        )
        blocking_id = blocking_result["ticket_id"]

        # Create dependent ticket
        dependent_result = await _create_ticket(
            ticket_type="task",
            title="Dependent Task",
            up_dependencies=[blocking_id],
            hive_name="default"
        )
        dependent_id = dependent_result["ticket_id"]

        # Verify bidirectional update
        blocking = read_ticket(get_ticket_path(blocking_id, "task"))
        dependent = read_ticket(get_ticket_path(dependent_id, "task"))

        assert blocking_id in dependent.up_dependencies
        assert dependent_id in blocking.down_dependencies

    async def test_down_dependencies_bidirectional_update(self, setup_tickets_dir):
        """Test that down_dependencies updates blocked ticket's up_dependencies."""
        # Create blocked ticket
        blocked_result = await _create_ticket(
            ticket_type="task",
            title="Blocked Task",
            hive_name="default"
        )
        blocked_id = blocked_result["ticket_id"]

        # Create blocking ticket
        blocking_result = await _create_ticket(
            ticket_type="task",
            title="Blocking Task",
            down_dependencies=[blocked_id],
            hive_name="default"
        )
        blocking_id = blocking_result["ticket_id"]

        # Verify bidirectional update
        blocking = read_ticket(get_ticket_path(blocking_id, "task"))
        blocked = read_ticket(get_ticket_path(blocked_id, "task"))

        assert blocked_id in blocking.down_dependencies
        assert blocking_id in blocked.up_dependencies

    async def test_multiple_children_bidirectional_update(self, setup_tickets_dir):
        """Test creating multiple children updates parent correctly."""
        # Create parent
        parent_result = await _create_ticket(
            ticket_type="epic",
            title="Parent Epic",
            hive_name="default"
        )
        parent_id = parent_result["ticket_id"]

        # Create multiple children
        child1_result = await _create_ticket(
            ticket_type="task",
            title="Child 1",
            parent=parent_id,
            hive_name="default"
        )
        child1_id = child1_result["ticket_id"]

        child2_result = await _create_ticket(
            ticket_type="task",
            title="Child 2",
            parent=parent_id,
            hive_name="default"
        )
        child2_id = child2_result["ticket_id"]

        # Verify parent has both children
        parent = read_ticket(get_ticket_path(parent_id, "epic"))
        assert child1_id in parent.children
        assert child2_id in parent.children


class TestValidation:
    """Tests for input validation and error handling."""

    async def test_empty_title_fails(self, setup_tickets_dir):
        """Test that empty title raises error."""
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(
                ticket_type="epic",
                title="",
                hive_name="default"
            )

        assert "Ticket title cannot be empty" in str(exc_info.value)

    async def test_whitespace_only_title_fails(self, setup_tickets_dir):
        """Test that whitespace-only title raises error."""
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(
                ticket_type="epic",
                title="   ",
                hive_name="default"
            )

        assert "Ticket title cannot be empty" in str(exc_info.value)

    async def test_invalid_ticket_type_fails(self, setup_tickets_dir):
        """Test that invalid ticket_type raises error."""
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(
                ticket_type="invalid",
                title="Test",
                hive_name="default"
            )

        assert "Invalid ticket_type" in str(exc_info.value)

    async def test_nonexistent_dependency_fails(self, setup_tickets_dir):
        """Test that non-existent dependency raises error."""
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(
                ticket_type="task",
                title="Test Task",
                up_dependencies=["bees-nonexistent"],
                hive_name="default"
            )

        assert "Dependency ticket does not exist" in str(exc_info.value)

    async def test_circular_dependency_fails(self, setup_tickets_dir):
        """Test that circular dependency (same ticket in up and down) fails."""
        # Create a task
        task_result = await _create_ticket(
            ticket_type="task",
            title="Existing Task",
            hive_name="default"
        )
        task_id = task_result["ticket_id"]

        # Try to create ticket with task_id in both up and down dependencies
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(
                ticket_type="task",
                title="Test Task",
                up_dependencies=[task_id],
                down_dependencies=[task_id],
                hive_name="default"
            )

        assert "Circular dependency detected" in str(exc_info.value)


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    async def test_create_ticket_with_all_optional_fields(self, setup_tickets_dir):
        """Test creating ticket with all optional fields populated."""
        result = await _create_ticket(
            ticket_type="epic",
            title="Full Epic",
            description="Full description",
            labels=["label1", "label2"],
            owner="user@example.com",
            priority=2,
            status="in_progress",
            hive_name="default"
        )

        assert result["status"] == "success"
        ticket_id = result["ticket_id"]

        ticket = read_ticket(get_ticket_path(ticket_id, "epic"))
        assert ticket.title == "Full Epic"
        assert ticket.description == "Full description"
        assert len(ticket.labels) == 2
        assert ticket.owner == "user@example.com"
        assert ticket.priority == 2
        assert ticket.status == "in_progress"

    async def test_create_ticket_with_minimal_fields(self, setup_tickets_dir):
        """Test creating ticket with only required fields."""
        result = await _create_ticket(
            ticket_type="epic",
            title="Minimal Epic",
            hive_name="default"
        )

        assert result["status"] == "success"
        ticket_id = result["ticket_id"]

        ticket = read_ticket(get_ticket_path(ticket_id, "epic"))
        assert ticket.title == "Minimal Epic"

    async def test_create_ticket_with_unicode_title(self, setup_tickets_dir):
        """Test creating ticket with unicode characters in title."""
        result = await _create_ticket(
            ticket_type="epic",
            title="Unicode Test: 你好 🚀",
            hive_name="default"
        )

        assert result["status"] == "success"
        ticket_id = result["ticket_id"]

        ticket = read_ticket(get_ticket_path(ticket_id, "epic"))
        assert ticket.title == "Unicode Test: 你好 🚀"

    async def test_create_ticket_with_long_description(self, setup_tickets_dir):
        """Test creating ticket with very long description."""
        long_description = "x" * 10000

        result = await _create_ticket(
            ticket_type="epic",
            title="Long Description Test",
            description=long_description,
            hive_name="default"
        )

        assert result["status"] == "success"
        ticket_id = result["ticket_id"]

        ticket = read_ticket(get_ticket_path(ticket_id, "epic"))
        assert len(ticket.description) == 10000
