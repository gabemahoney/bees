"""
Unit tests for delete_ticket MCP tool implementation.

Tests ticket deletion, relationship cleanup (parent/children/dependencies),
cascade delete behavior, and error handling.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.mcp_server import _delete_ticket, _create_ticket
from src.reader import read_ticket
from src.paths import get_ticket_path


@pytest.fixture
def setup_tickets_dir(tmp_path, monkeypatch):
    """Create temporary tickets directory structure."""
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
    save_bees_config(config)

    yield tmp_path


class TestDeleteTicketBasic:
    """Tests for basic delete_ticket functionality."""

    def test_delete_ticket_file_removal(self, setup_tickets_dir):
        """Test that delete_ticket removes the ticket file."""
        # Create an epic ticket
        result = _create_ticket(
            ticket_type="epic",
            title="Test Epic",
            description="Test description",
            hive_name="default"
        )
        ticket_id = result["ticket_id"]

        # Verify ticket file exists
        ticket_path = get_ticket_path(ticket_id, "epic")
        assert ticket_path.exists()

        # Delete the ticket
        result = _delete_ticket(ticket_id=ticket_id)

        # Verify result
        assert result["status"] == "success"
        assert result["ticket_id"] == ticket_id
        assert result["ticket_type"] == "epic"

        # Verify ticket file is removed
        assert not ticket_path.exists()

    def test_delete_nonexistent_ticket_error(self, setup_tickets_dir):
        """Test that deleting non-existent ticket raises ValueError."""
        with pytest.raises(ValueError, match="Ticket does not exist"):
            _delete_ticket(ticket_id="nonexistent-id")


class TestDeleteTicketParentCleanup:
    """Tests for cleaning up parent's children array when deleting."""

    def test_delete_ticket_removes_from_parent_children(self, setup_tickets_dir):
        """Test that deleting a ticket removes it from parent's children array."""
        # Create parent epic and child task
        parent_result = _create_ticket(ticket_type="epic", title="Parent Epic", hive_name="default")
        parent_id = parent_result["ticket_id"]

        child_result = _create_ticket(ticket_type="task", title="Child Task", parent=parent_id, hive_name="default")
        child_id = child_result["ticket_id"]

        # Verify parent has child in children array
        parent = read_ticket(get_ticket_path(parent_id, "epic"))
        assert child_id in parent.children

        # Delete child ticket
        result = _delete_ticket(ticket_id=child_id)

        # Verify success
        assert result["status"] == "success"

        # Verify parent's children array no longer contains child
        parent = read_ticket(get_ticket_path(parent_id, "epic"))
        assert child_id not in (parent.children or [])

    def test_delete_ticket_without_parent(self, setup_tickets_dir):
        """Test that deleting a ticket without parent works correctly."""
        # Create epic without parent
        result = _create_ticket(ticket_type="epic", title="Epic Without Parent", hive_name="default")
        ticket_id = result["ticket_id"]

        # Delete the ticket
        result = _delete_ticket(ticket_id=ticket_id)

        # Verify success
        assert result["status"] == "success"
        assert not get_ticket_path(ticket_id, "epic").exists()


class TestDeleteTicketDependencyCleanup:
    """Tests for cleaning up dependency arrays in related tickets."""

    def test_delete_ticket_removes_from_down_dependencies(self, setup_tickets_dir):
        """Test that deleting a ticket removes it from blocking tickets' down_dependencies."""
        # Create two epics with dependency relationship
        blocking_result = _create_ticket(ticket_type="epic", title="Blocking Epic", hive_name="default")
        blocking_id = blocking_result["ticket_id"]

        blocked_result = _create_ticket(
            ticket_type="epic",
            title="Blocked Epic",
            up_dependencies=[blocking_id],
            hive_name="default"
        )
        blocked_id = blocked_result["ticket_id"]

        # Verify blocking ticket has blocked ticket in down_dependencies
        blocking = read_ticket(get_ticket_path(blocking_id, "epic"))
        assert blocked_id in blocking.down_dependencies

        # Delete blocked ticket
        _delete_ticket(ticket_id=blocked_id)

        # Verify blocking ticket's down_dependencies no longer contains deleted ticket
        blocking = read_ticket(get_ticket_path(blocking_id, "epic"))
        assert blocked_id not in (blocking.down_dependencies or [])

    def test_delete_ticket_removes_from_up_dependencies(self, setup_tickets_dir):
        """Test that deleting a ticket removes it from blocked tickets' up_dependencies."""
        # Create two epics with dependency relationship
        blocking_result = _create_ticket(ticket_type="epic", title="Blocking Epic", hive_name="default")
        blocking_id = blocking_result["ticket_id"]

        blocked_result = _create_ticket(
            ticket_type="epic",
            title="Blocked Epic",
            up_dependencies=[blocking_id],
            hive_name="default"
        )
        blocked_id = blocked_result["ticket_id"]

        # Verify blocked ticket has blocking ticket in up_dependencies
        blocked = read_ticket(get_ticket_path(blocked_id, "epic"))
        assert blocking_id in blocked.up_dependencies

        # Delete blocking ticket
        _delete_ticket(ticket_id=blocking_id)

        # Verify blocked ticket's up_dependencies no longer contains deleted ticket
        blocked = read_ticket(get_ticket_path(blocked_id, "epic"))
        assert blocking_id not in (blocked.up_dependencies or [])

    def test_delete_ticket_with_multiple_dependencies(self, setup_tickets_dir):
        """Test deleting a ticket with multiple dependency relationships."""
        # Create epics with complex dependency structure
        epic1_result = _create_ticket(ticket_type="epic", title="Epic 1", hive_name="default")
        epic1_id = epic1_result["ticket_id"]

        epic2_result = _create_ticket(ticket_type="epic", title="Epic 2", hive_name="default")
        epic2_id = epic2_result["ticket_id"]

        epic3_result = _create_ticket(
            ticket_type="epic",
            title="Epic 3",
            up_dependencies=[epic1_id],
            down_dependencies=[epic2_id],
            hive_name="default"
        )
        epic3_id = epic3_result["ticket_id"]

        # Delete epic3
        _delete_ticket(ticket_id=epic3_id)

        # Verify epic1's down_dependencies cleaned up
        epic1 = read_ticket(get_ticket_path(epic1_id, "epic"))
        assert epic3_id not in (epic1.down_dependencies or [])

        # Verify epic2's up_dependencies cleaned up
        epic2 = read_ticket(get_ticket_path(epic2_id, "epic"))
        assert epic3_id not in (epic2.up_dependencies or [])


class TestDeleteTicketCascade:
    """Tests for cascade delete behavior with children."""

    def test_cascade_delete_children(self, setup_tickets_dir):
        """Test that cascade=True recursively deletes all children."""
        # Create parent epic with multiple children
        parent_result = _create_ticket(ticket_type="epic", title="Parent Epic", hive_name="default")
        parent_id = parent_result["ticket_id"]

        child1_result = _create_ticket(ticket_type="task", title="Child 1", parent=parent_id, hive_name="default")
        child1_id = child1_result["ticket_id"]

        child2_result = _create_ticket(ticket_type="task", title="Child 2", parent=parent_id, hive_name="default")
        child2_id = child2_result["ticket_id"]

        # Verify children exist
        assert get_ticket_path(child1_id, "task").exists()
        assert get_ticket_path(child2_id, "task").exists()

        # Delete parent with cascade=True
        result = _delete_ticket(ticket_id=parent_id, cascade=True)

        # Verify success
        assert result["status"] == "success"

        # Verify all tickets are deleted
        assert not get_ticket_path(parent_id, "epic").exists()
        assert not get_ticket_path(child1_id, "task").exists()
        assert not get_ticket_path(child2_id, "task").exists()

    def test_cascade_delete_nested_children(self, setup_tickets_dir):
        """Test that cascade delete works with nested hierarchies."""
        # Create nested hierarchy: Epic -> Task -> Subtask
        epic_result = _create_ticket(ticket_type="epic", title="Epic", hive_name="default")
        epic_id = epic_result["ticket_id"]

        task_result = _create_ticket(ticket_type="task", title="Task", parent=epic_id, hive_name="default")
        task_id = task_result["ticket_id"]

        subtask_result = _create_ticket(ticket_type="subtask", title="Subtask", parent=task_id, hive_name="default")
        subtask_id = subtask_result["ticket_id"]

        # Delete epic with cascade=True
        _delete_ticket(ticket_id=epic_id, cascade=True)

        # Verify all tickets are deleted
        assert not get_ticket_path(epic_id, "epic").exists()
        assert not get_ticket_path(task_id, "task").exists()
        assert not get_ticket_path(subtask_id, "subtask").exists()

    def test_delete_without_cascade_unlinks_children(self, setup_tickets_dir):
        """Test that cascade=False unlinks children instead of deleting them."""
        # Create parent epic with child
        parent_result = _create_ticket(ticket_type="epic", title="Parent Epic", hive_name="default")
        parent_id = parent_result["ticket_id"]

        child_result = _create_ticket(ticket_type="task", title="Child Task", parent=parent_id, hive_name="default")
        child_id = child_result["ticket_id"]

        # Verify child has parent reference
        child = read_ticket(get_ticket_path(child_id, "task"))
        assert child.parent == parent_id

        # Delete parent with cascade=False (default)
        _delete_ticket(ticket_id=parent_id, cascade=False)

        # Verify parent is deleted
        assert not get_ticket_path(parent_id, "epic").exists()

        # Verify child still exists but parent reference is removed
        assert get_ticket_path(child_id, "task").exists()
        child = read_ticket(get_ticket_path(child_id, "task"))
        assert child.parent is None

    def test_delete_ticket_without_children(self, setup_tickets_dir):
        """Test that deleting ticket without children works with cascade parameter."""
        # Create epic without children
        result = _create_ticket(ticket_type="epic", title="Epic Without Children", hive_name="default")
        ticket_id = result["ticket_id"]

        # Delete with cascade=True should work fine
        result = _delete_ticket(ticket_id=ticket_id, cascade=True)

        # Verify success
        assert result["status"] == "success"
        assert not get_ticket_path(ticket_id, "epic").exists()


class TestDeleteTicketEdgeCases:
    """Tests for edge cases and error handling."""

    def test_delete_ticket_with_all_relationships(self, setup_tickets_dir):
        """Test deleting a ticket with parent, children, and dependencies."""
        # Create complex relationship structure
        parent_result = _create_ticket(ticket_type="epic", title="Parent", hive_name="default")
        parent_id = parent_result["ticket_id"]

        blocking_result = _create_ticket(ticket_type="epic", title="Blocking", hive_name="default")
        blocking_id = blocking_result["ticket_id"]

        target_result = _create_ticket(
            ticket_type="task",
            title="Target Task",
            parent=parent_id,
            up_dependencies=[blocking_id],
            hive_name="default"
        )
        target_id = target_result["ticket_id"]

        child_result = _create_ticket(ticket_type="subtask", title="Child", parent=target_id, hive_name="default")
        child_id = child_result["ticket_id"]

        # Delete target without cascade (unlinks child)
        _delete_ticket(ticket_id=target_id, cascade=False)

        # Verify target is deleted
        assert not get_ticket_path(target_id, "task").exists()

        # Verify parent's children cleaned up
        parent = read_ticket(get_ticket_path(parent_id, "epic"))
        assert target_id not in (parent.children or [])

        # Verify blocking ticket's down_dependencies cleaned up
        blocking = read_ticket(get_ticket_path(blocking_id, "epic"))
        assert target_id not in (blocking.down_dependencies or [])

        # Verify child is unlinked but still exists
        # Note: Subtasks cannot be unlinked (they require a parent), so they remain
        # pointing to the deleted parent
        assert get_ticket_path(child_id, "subtask").exists()
        child = read_ticket(get_ticket_path(child_id, "subtask"))
        assert child.parent == target_id  # Subtask still points to deleted parent

    def test_cascade_delete_with_dependencies(self, setup_tickets_dir):
        """Test that cascade delete also cleans up dependencies for children."""
        # Create parent with child that has dependencies
        parent_result = _create_ticket(ticket_type="epic", title="Parent", hive_name="default")
        parent_id = parent_result["ticket_id"]

        blocking_result = _create_ticket(ticket_type="epic", title="Blocking", hive_name="default")
        blocking_id = blocking_result["ticket_id"]

        child_result = _create_ticket(
            ticket_type="task",
            title="Child",
            parent=parent_id,
            up_dependencies=[blocking_id],
            hive_name="default"
        )
        child_id = child_result["ticket_id"]

        # Verify blocking relationship exists
        blocking = read_ticket(get_ticket_path(blocking_id, "epic"))
        assert child_id in blocking.down_dependencies

        # Cascade delete parent
        _delete_ticket(ticket_id=parent_id, cascade=True)

        # Verify both parent and child are deleted
        assert not get_ticket_path(parent_id, "epic").exists()
        assert not get_ticket_path(child_id, "task").exists()

        # Verify blocking ticket's down_dependencies cleaned up
        blocking = read_ticket(get_ticket_path(blocking_id, "epic"))
        assert child_id not in (blocking.down_dependencies or [])
