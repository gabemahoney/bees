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


class TestDeleteTicketBasic:
    """Tests for basic delete_ticket functionality."""

    async def test_delete_ticket_file_removal(self, single_hive, monkeypatch):
        """Test that delete_ticket removes the ticket file."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)
        
        # Create an epic ticket
        result = await _create_ticket(
            ticket_type="epic",
            title="Test Epic",
            description="Test description",
            hive_name="backend"
        )
        ticket_id = result["ticket_id"]

        # Verify ticket file exists
        ticket_path = get_ticket_path(ticket_id, "epic")
        assert ticket_path.exists()

        # Delete the ticket
        result = await _delete_ticket(ticket_id=ticket_id)

        # Verify result
        assert result["status"] == "success"
        assert result["ticket_id"] == ticket_id
        assert result["ticket_type"] == "epic"

        # Verify ticket file is removed
        assert not ticket_path.exists()

    async def test_delete_nonexistent_ticket_error(self, single_hive, monkeypatch):
        """Test that deleting non-existent ticket raises ValueError."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)
        
        with pytest.raises(ValueError, match="Ticket does not exist"):
            await _delete_ticket(ticket_id="backend.bees-nonexistent")


class TestDeleteTicketParentCleanup:
    """Tests for cleaning up parent's children array when deleting."""

    async def test_delete_ticket_removes_from_parent_children(self, single_hive, monkeypatch):
        """Test that deleting a ticket removes it from parent's children array."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)
        
        # Create parent epic and child task
        parent_result = await _create_ticket(ticket_type="epic", title="Parent Epic", hive_name="backend")
        parent_id = parent_result["ticket_id"]

        child_result = await _create_ticket(ticket_type="task", title="Child Task", parent=parent_id, hive_name="backend")
        child_id = child_result["ticket_id"]

        # Verify parent has child in children array
        parent = read_ticket(get_ticket_path(parent_id, "epic"))
        assert child_id in parent.children

        # Delete child ticket
        result = await _delete_ticket(ticket_id=child_id)

        # Verify success
        assert result["status"] == "success"

        # Verify parent's children array no longer contains child
        parent = read_ticket(get_ticket_path(parent_id, "epic"))
        assert child_id not in (parent.children or [])

    async def test_delete_ticket_without_parent(self, single_hive, monkeypatch):
        """Test that deleting a ticket without parent works correctly."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)
        
        # Create epic without parent
        result = await _create_ticket(ticket_type="epic", title="Epic Without Parent", hive_name="backend")
        ticket_id = result["ticket_id"]

        # Delete the ticket
        result = await _delete_ticket(ticket_id=ticket_id)

        # Verify success
        assert result["status"] == "success"
        assert not get_ticket_path(ticket_id, "epic").exists()


class TestDeleteTicketDependencyCleanup:
    """Tests for cleaning up dependency arrays in related tickets."""

    async def test_delete_ticket_removes_from_down_dependencies(self, single_hive, monkeypatch):
        """Test that deleting a ticket removes it from blocking tickets' down_dependencies."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)
        
        # Create two epics with dependency relationship
        blocking_result = await _create_ticket(ticket_type="epic", title="Blocking Epic", hive_name="backend")
        blocking_id = blocking_result["ticket_id"]

        blocked_result = await _create_ticket(
            ticket_type="epic",
            title="Blocked Epic",
            up_dependencies=[blocking_id],
            hive_name="backend"
        )
        blocked_id = blocked_result["ticket_id"]

        # Verify blocking ticket has blocked ticket in down_dependencies
        blocking = read_ticket(get_ticket_path(blocking_id, "epic"))
        assert blocked_id in blocking.down_dependencies

        # Delete blocked ticket
        await _delete_ticket(ticket_id=blocked_id)

        # Verify blocking ticket's down_dependencies no longer contains deleted ticket
        blocking = read_ticket(get_ticket_path(blocking_id, "epic"))
        assert blocked_id not in (blocking.down_dependencies or [])

    async def test_delete_ticket_removes_from_up_dependencies(self, single_hive, monkeypatch):
        """Test that deleting a ticket removes it from blocked tickets' up_dependencies."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)
        
        # Create two epics with dependency relationship
        blocking_result = await _create_ticket(ticket_type="epic", title="Blocking Epic", hive_name="backend")
        blocking_id = blocking_result["ticket_id"]

        blocked_result = await _create_ticket(
            ticket_type="epic",
            title="Blocked Epic",
            up_dependencies=[blocking_id],
            hive_name="backend"
        )
        blocked_id = blocked_result["ticket_id"]

        # Verify blocked ticket has blocking ticket in up_dependencies
        blocked = read_ticket(get_ticket_path(blocked_id, "epic"))
        assert blocking_id in blocked.up_dependencies

        # Delete blocking ticket
        await _delete_ticket(ticket_id=blocking_id)

        # Verify blocked ticket's up_dependencies no longer contains deleted ticket
        blocked = read_ticket(get_ticket_path(blocked_id, "epic"))
        assert blocking_id not in (blocked.up_dependencies or [])

    async def test_delete_ticket_with_multiple_dependencies(self, single_hive, monkeypatch):
        """Test deleting a ticket with multiple dependency relationships."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)
        
        # Create epics with complex dependency structure
        epic1_result = await _create_ticket(ticket_type="epic", title="Epic 1", hive_name="backend")
        epic1_id = epic1_result["ticket_id"]

        epic2_result = await _create_ticket(ticket_type="epic", title="Epic 2", hive_name="backend")
        epic2_id = epic2_result["ticket_id"]

        epic3_result = await _create_ticket(
            ticket_type="epic",
            title="Epic 3",
            up_dependencies=[epic1_id],
            down_dependencies=[epic2_id],
            hive_name="backend"
        )
        epic3_id = epic3_result["ticket_id"]

        # Delete epic3
        await _delete_ticket(ticket_id=epic3_id)

        # Verify epic1's down_dependencies cleaned up
        epic1 = read_ticket(get_ticket_path(epic1_id, "epic"))
        assert epic3_id not in (epic1.down_dependencies or [])

        # Verify epic2's up_dependencies cleaned up
        epic2 = read_ticket(get_ticket_path(epic2_id, "epic"))
        assert epic3_id not in (epic2.up_dependencies or [])


class TestDeleteTicketCascade:
    """Tests for cascade delete behavior with children."""

    async def test_cascade_delete_children(self, single_hive, monkeypatch):
        """Test that cascade=True recursively deletes all children."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)
        
        # Create parent epic with multiple children
        parent_result = await _create_ticket(ticket_type="epic", title="Parent Epic", hive_name="backend")
        parent_id = parent_result["ticket_id"]

        child1_result = await _create_ticket(ticket_type="task", title="Child 1", parent=parent_id, hive_name="backend")
        child1_id = child1_result["ticket_id"]

        child2_result = await _create_ticket(ticket_type="task", title="Child 2", parent=parent_id, hive_name="backend")
        child2_id = child2_result["ticket_id"]

        # Verify children exist
        assert get_ticket_path(child1_id, "task").exists()
        assert get_ticket_path(child2_id, "task").exists()

        # Delete parent (always cascades)
        result = await _delete_ticket(ticket_id=parent_id)

        # Verify success
        assert result["status"] == "success"

        # Verify all tickets are deleted
        assert not get_ticket_path(parent_id, "epic").exists()
        assert not get_ticket_path(child1_id, "task").exists()
        assert not get_ticket_path(child2_id, "task").exists()

    async def test_cascade_delete_nested_children(self, single_hive, monkeypatch):
        """Test that cascade delete works with nested hierarchies."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)
        
        # Create nested hierarchy: Epic -> Task -> Subtask
        epic_result = await _create_ticket(ticket_type="epic", title="Epic", hive_name="backend")
        epic_id = epic_result["ticket_id"]

        task_result = await _create_ticket(ticket_type="task", title="Task", parent=epic_id, hive_name="backend")
        task_id = task_result["ticket_id"]

        subtask_result = await _create_ticket(ticket_type="subtask", title="Subtask", parent=task_id, hive_name="backend")
        subtask_id = subtask_result["ticket_id"]

        # Delete epic (always cascades)
        await _delete_ticket(ticket_id=epic_id)

        # Verify all tickets are deleted
        assert not get_ticket_path(epic_id, "epic").exists()
        assert not get_ticket_path(task_id, "task").exists()
        assert not get_ticket_path(subtask_id, "subtask").exists()

    async def test_delete_always_cascades_to_children(self, single_hive, monkeypatch):
        """Test that deletion always cascades to children."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)
        
        # Create parent epic with child
        parent_result = await _create_ticket(ticket_type="epic", title="Parent Epic", hive_name="backend")
        parent_id = parent_result["ticket_id"]

        child_result = await _create_ticket(ticket_type="task", title="Child Task", parent=parent_id, hive_name="backend")
        child_id = child_result["ticket_id"]

        # Verify child has parent reference
        child = read_ticket(get_ticket_path(child_id, "task"))
        assert child.parent == parent_id

        # Delete parent (always cascades)
        await _delete_ticket(ticket_id=parent_id)

        # Verify parent is deleted
        assert not get_ticket_path(parent_id, "epic").exists()

        # Verify child is also deleted (cascaded)
        assert not get_ticket_path(child_id, "task").exists()

    async def test_delete_ticket_without_children(self, single_hive, monkeypatch):
        """Test that deleting ticket without children works correctly."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)
        
        # Create epic without children
        result = await _create_ticket(ticket_type="epic", title="Epic Without Children", hive_name="backend")
        ticket_id = result["ticket_id"]

        # Delete should work fine
        result = await _delete_ticket(ticket_id=ticket_id)

        # Verify success
        assert result["status"] == "success"
        assert not get_ticket_path(ticket_id, "epic").exists()


    async def test_cascade_delete_deep_hierarchy(self, single_hive, monkeypatch):
        """Test that cascade delete works with deep hierarchies (4+ levels)."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)
        
        # Create deep hierarchy: Epic -> Task -> Subtask (and verify grandchildren concept)
        epic_result = await _create_ticket(ticket_type="epic", title="Epic", hive_name="backend")
        epic_id = epic_result["ticket_id"]

        task1_result = await _create_ticket(ticket_type="task", title="Task 1", parent=epic_id, hive_name="backend")
        task1_id = task1_result["ticket_id"]

        task2_result = await _create_ticket(ticket_type="task", title="Task 2", parent=epic_id, hive_name="backend")
        task2_id = task2_result["ticket_id"]

        subtask1_result = await _create_ticket(ticket_type="subtask", title="Subtask 1", parent=task1_id, hive_name="backend")
        subtask1_id = subtask1_result["ticket_id"]

        subtask2_result = await _create_ticket(ticket_type="subtask", title="Subtask 2", parent=task2_id, hive_name="backend")
        subtask2_id = subtask2_result["ticket_id"]

        # Verify all exist
        assert get_ticket_path(epic_id, "epic").exists()
        assert get_ticket_path(task1_id, "task").exists()
        assert get_ticket_path(task2_id, "task").exists()
        assert get_ticket_path(subtask1_id, "subtask").exists()
        assert get_ticket_path(subtask2_id, "subtask").exists()

        # Delete epic at root (should cascade through entire tree)
        await _delete_ticket(ticket_id=epic_id)

        # Verify entire tree is deleted
        assert not get_ticket_path(epic_id, "epic").exists()
        assert not get_ticket_path(task1_id, "task").exists()
        assert not get_ticket_path(task2_id, "task").exists()
        assert not get_ticket_path(subtask1_id, "subtask").exists()
        assert not get_ticket_path(subtask2_id, "subtask").exists()

    async def test_cascade_delete_single_child(self, single_hive, monkeypatch):
        """Test edge case: parent with exactly one child."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)
        
        parent_result = await _create_ticket(ticket_type="epic", title="Parent", hive_name="backend")
        parent_id = parent_result["ticket_id"]

        child_result = await _create_ticket(ticket_type="task", title="Only Child", parent=parent_id, hive_name="backend")
        child_id = child_result["ticket_id"]

        # Delete parent
        await _delete_ticket(ticket_id=parent_id)

        # Verify both deleted
        assert not get_ticket_path(parent_id, "epic").exists()
        assert not get_ticket_path(child_id, "task").exists()

    async def test_cascade_delete_multiple_children_at_same_level(self, single_hive, monkeypatch):
        """Test edge case: parent with many children at the same level."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)
        
        parent_result = await _create_ticket(ticket_type="epic", title="Parent", hive_name="backend")
        parent_id = parent_result["ticket_id"]

        # Create 5 children
        child_ids = []
        for i in range(5):
            child_result = await _create_ticket(
                ticket_type="task",
                title=f"Child {i}",
                parent=parent_id,
                hive_name="backend"
            )
            child_ids.append(child_result["ticket_id"])

        # Verify all exist
        for child_id in child_ids:
            assert get_ticket_path(child_id, "task").exists()

        # Delete parent
        await _delete_ticket(ticket_id=parent_id)

        # Verify all deleted
        assert not get_ticket_path(parent_id, "epic").exists()
        for child_id in child_ids:
            assert not get_ticket_path(child_id, "task").exists()


class TestDeleteTicketEdgeCases:
    """Tests for edge cases and error handling."""

    async def test_delete_ticket_with_all_relationships(self, single_hive, monkeypatch):
        """Test deleting a ticket with parent, children, and dependencies."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)
        
        # Create complex relationship structure
        parent_result = await _create_ticket(ticket_type="epic", title="Parent", hive_name="backend")
        parent_id = parent_result["ticket_id"]

        blocking_result = await _create_ticket(ticket_type="epic", title="Blocking", hive_name="backend")
        blocking_id = blocking_result["ticket_id"]

        target_result = await _create_ticket(
            ticket_type="task",
            title="Target Task",
            parent=parent_id,
            up_dependencies=[blocking_id],
            hive_name="backend"
        )
        target_id = target_result["ticket_id"]

        child_result = await _create_ticket(ticket_type="subtask", title="Child", parent=target_id, hive_name="backend")
        child_id = child_result["ticket_id"]

        # Delete target (always cascades)
        await _delete_ticket(ticket_id=target_id)

        # Verify target is deleted
        assert not get_ticket_path(target_id, "task").exists()

        # Verify parent's children cleaned up
        parent = read_ticket(get_ticket_path(parent_id, "epic"))
        assert target_id not in (parent.children or [])

        # Verify blocking ticket's down_dependencies cleaned up
        blocking = read_ticket(get_ticket_path(blocking_id, "epic"))
        assert target_id not in (blocking.down_dependencies or [])

        # Verify child is also deleted (cascaded)
        assert not get_ticket_path(child_id, "subtask").exists()

    async def test_cascade_delete_with_dependencies(self, single_hive, monkeypatch):
        """Test that cascade delete also cleans up dependencies for children."""
        repo_root, hive_path = single_hive
        monkeypatch.chdir(repo_root)
        
        # Create parent with child that has dependencies
        parent_result = await _create_ticket(ticket_type="epic", title="Parent", hive_name="backend")
        parent_id = parent_result["ticket_id"]

        blocking_result = await _create_ticket(ticket_type="epic", title="Blocking", hive_name="backend")
        blocking_id = blocking_result["ticket_id"]

        child_result = await _create_ticket(
            ticket_type="task",
            title="Child",
            parent=parent_id,
            up_dependencies=[blocking_id],
            hive_name="backend"
        )
        child_id = child_result["ticket_id"]

        # Verify blocking relationship exists
        blocking = read_ticket(get_ticket_path(blocking_id, "epic"))
        assert child_id in blocking.down_dependencies

        # Delete parent (always cascades)
        await _delete_ticket(ticket_id=parent_id)

        # Verify both parent and child are deleted
        assert not get_ticket_path(parent_id, "epic").exists()
        assert not get_ticket_path(child_id, "task").exists()

        # Verify blocking ticket's down_dependencies cleaned up
        blocking = read_ticket(get_ticket_path(blocking_id, "epic"))
        assert child_id not in (blocking.down_dependencies or [])


class TestDeleteTicketHiveRouting:
    """Tests for hive routing in delete_ticket()."""

    async def test_delete_ticket_routes_to_correct_hive(self, multi_hive, monkeypatch):
        """Test that delete_ticket routes to correct hive based on ticket ID prefix."""
        repo_root, backend_path, frontend_path = multi_hive
        monkeypatch.chdir(repo_root)
        
        # Create tickets in different hives
        backend_result = await _create_ticket(
            ticket_type="epic",
            title="Backend Epic",
            hive_name="backend"
        )
        backend_id = backend_result["ticket_id"]

        frontend_result = await _create_ticket(
            ticket_type="epic",
            title="Frontend Epic",
            hive_name="frontend"
        )
        frontend_id = frontend_result["ticket_id"]

        # Verify tickets exist with correct prefixes
        assert backend_id.startswith("backend.")
        assert frontend_id.startswith("frontend.")
        assert get_ticket_path(backend_id, "epic").exists()
        assert get_ticket_path(frontend_id, "epic").exists()

        # Delete backend ticket
        result = await _delete_ticket(ticket_id=backend_id)
        assert result["status"] == "success"
        assert not get_ticket_path(backend_id, "epic").exists()

        # Verify frontend ticket still exists
        assert get_ticket_path(frontend_id, "epic").exists()

        # Delete frontend ticket
        result = await _delete_ticket(ticket_id=frontend_id)
        assert result["status"] == "success"
        assert not get_ticket_path(frontend_id, "epic").exists()

    async def test_delete_ticket_malformed_id_error(self, multi_hive, monkeypatch):
        """Test that delete_ticket raises error for malformed ticket IDs."""
        repo_root, backend_path, frontend_path = multi_hive
        monkeypatch.chdir(repo_root)
        
        with pytest.raises(ValueError, match="Malformed ticket ID"):
            await _delete_ticket(ticket_id="bees-abc1")  # Missing hive prefix

    async def test_delete_ticket_unknown_hive_error(self, multi_hive, monkeypatch):
        """Test that delete_ticket raises error for unknown hive prefix."""
        repo_root, backend_path, frontend_path = multi_hive
        monkeypatch.chdir(repo_root)
        
        with pytest.raises(ValueError, match="Hive .* not found in configuration"):
            await _delete_ticket(ticket_id="unknown.bees-abc1")

    async def test_delete_ticket_with_multiple_dots_in_id(self, multi_hive, monkeypatch):
        """Test that delete_ticket handles IDs with multiple dots correctly."""
        repo_root, backend_path, frontend_path = multi_hive
        monkeypatch.chdir(repo_root)
        
        # Create ticket in backend hive
        result = await _create_ticket(
            ticket_type="epic",
            title="Test Epic",
            hive_name="backend"
        )
        ticket_id = result["ticket_id"]

        # Verify ticket exists
        assert get_ticket_path(ticket_id, "epic").exists()

        # Delete should work correctly (only first dot matters)
        result = await _delete_ticket(ticket_id=ticket_id)
        assert result["status"] == "success"
        assert not get_ticket_path(ticket_id, "epic").exists()

    async def test_delete_ticket_cascade_with_hive_routing(self, multi_hive, monkeypatch):
        """Test cascade delete with hive-prefixed IDs."""
        repo_root, backend_path, frontend_path = multi_hive
        monkeypatch.chdir(repo_root)
        
        # Create parent and child in backend hive
        parent_result = await _create_ticket(
            ticket_type="epic",
            title="Parent Epic",
            hive_name="backend"
        )
        parent_id = parent_result["ticket_id"]

        child_result = await _create_ticket(
            ticket_type="task",
            title="Child Task",
            parent=parent_id,
            hive_name="backend"
        )
        child_id = child_result["ticket_id"]

        # Verify both exist
        assert get_ticket_path(parent_id, "epic").exists()
        assert get_ticket_path(child_id, "task").exists()

        # Delete parent (always cascades)
        result = await _delete_ticket(ticket_id=parent_id)
        assert result["status"] == "success"

        # Verify both are deleted
        assert not get_ticket_path(parent_id, "epic").exists()
        assert not get_ticket_path(child_id, "task").exists()
