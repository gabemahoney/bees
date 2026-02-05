"""
Integration tests for bidirectional relationship synchronization.

These tests verify that MCP functions (_create_ticket, _update_ticket) properly
sync bidirectional relationships (parent ↔ children, dependencies) while the raw
ticket_factory functions (create_epic, create_task, create_subtask) only set
one-way relationships.

Context:
- hive_with_tickets fixture uses raw ticket_factory functions that only set parent fields
- MCP functions call _update_bidirectional_relationships() to sync both directions
- This test verifies the difference in behavior and ensures MCP functions work correctly
"""

import pytest
from pathlib import Path
from src.reader import read_ticket
from src.paths import get_ticket_path, infer_ticket_type_from_id
from src.repo_context import repo_root_context
from src.mcp_ticket_ops import _create_ticket


class TestFixtureVsMCPBehavior:
    """Compare fixture behavior (one-way relationships) vs MCP behavior (bidirectional sync)."""

    def test_hive_with_tickets_creates_oneway_relationships(self, hive_with_tickets):
        """
        Verify that hive_with_tickets fixture creates parent→child links but not children arrays.
        
        This documents the fixture behavior: it uses raw ticket_factory functions that only
        set parent fields without syncing children arrays bidirectionally.
        """
        repo_root, hive_path, epic_id, task_id, subtask_id = hive_with_tickets
        
        with repo_root_context(repo_root):
            # Read tickets
            epic_path = get_ticket_path(epic_id, "epic")
            task_path = get_ticket_path(task_id, "task")
            subtask_path = get_ticket_path(subtask_id, "subtask")
            
            epic = read_ticket(epic_path)
            task = read_ticket(task_path)
            subtask = read_ticket(subtask_path)
            
            # Verify parent fields are set (child → parent direction)
            assert task.parent == epic_id, "Task should have epic as parent"
            assert subtask.parent == task_id, "Subtask should have task as parent"
            
            # Verify children arrays are NOT populated by fixture (no parent → child sync)
            # Note: This is expected behavior for the fixture - it uses raw ticket_factory functions
            assert epic.children is None or task_id not in epic.children, \
                "Fixture should not populate epic's children array"
            assert task.children is None or subtask_id not in task.children, \
                "Fixture should not populate task's children array"

    @pytest.mark.asyncio
    async def test_mcp_create_ticket_syncs_bidirectionally(self, single_hive, monkeypatch):
        """
        Verify that MCP _create_ticket() syncs relationships bidirectionally.
        
        When creating tickets via MCP functions, both parent fields AND children arrays
        should be populated to maintain bidirectional consistency.
        """
        repo_root, hive_path = single_hive
        
        # Change to repo_root so _create_ticket finds correct config
        monkeypatch.chdir(repo_root)
        
        with repo_root_context(repo_root):
            # Create epic via MCP (without ctx for direct function call)
            epic_result = await _create_ticket(
                ticket_type="epic",
                title="MCP Test Epic",
                description="Epic created via MCP",
                hive_name="backend",
                ctx=None
            )
            epic_id = epic_result["ticket_id"]
            
            # Create task via MCP with epic as parent
            task_result = await _create_ticket(
                ticket_type="task",
                title="MCP Test Task",
                description="Task created via MCP",
                parent=epic_id,
                hive_name="backend",
                ctx=None
            )
            task_id = task_result["ticket_id"]
            
            # Create subtask via MCP with task as parent
            subtask_result = await _create_ticket(
                ticket_type="subtask",
                title="MCP Test Subtask",
                description="Subtask created via MCP",
                parent=task_id,
                hive_name="backend",
                ctx=None
            )
            subtask_id = subtask_result["ticket_id"]
            
            # Read tickets to verify bidirectional sync
            epic_path = get_ticket_path(epic_id, "epic")
            task_path = get_ticket_path(task_id, "task")
            subtask_path = get_ticket_path(subtask_id, "subtask")
            
            epic = read_ticket(epic_path)
            task = read_ticket(task_path)
            subtask = read_ticket(subtask_path)
            
            # Verify parent fields are set (child → parent direction)
            assert task.parent == epic_id, "Task should have epic as parent"
            assert subtask.parent == task_id, "Subtask should have task as parent"
            
            # Verify children arrays ARE populated by MCP (parent → child bidirectional sync)
            assert epic.children is not None and task_id in epic.children, \
                "MCP should populate epic's children array with task ID"
            assert task.children is not None and subtask_id in task.children, \
                "MCP should populate task's children array with subtask ID"


class TestBidirectionalSyncEdgeCases:
    """Test edge cases in bidirectional relationship synchronization."""

    @pytest.mark.asyncio
    async def test_create_epic_without_children(self, single_hive, monkeypatch):
        """
        Verify creating an epic without children initializes empty children array.
        """
        repo_root, hive_path = single_hive
        
        # Change to repo_root so _create_ticket finds correct config
        monkeypatch.chdir(repo_root)
        
        with repo_root_context(repo_root):
            # Create epic without children
            result = await _create_ticket(
                ticket_type="epic",
                title="Childless Epic",
                hive_name="backend",
                ctx=None
            )
            epic_id = result["ticket_id"]
            
            # Read epic
            epic_path = get_ticket_path(epic_id, "epic")
            epic = read_ticket(epic_path)
            
            # Children should be None (not set) since no children were specified
            # Note: We only populate children arrays when relationships are established
            assert epic.children is None or epic.children == [], \
                "Epic without children should have None or empty children array"

    @pytest.mark.asyncio
    async def test_multiple_children_sync(self, single_hive, monkeypatch):
        """
        Verify creating multiple children updates parent's children array correctly.
        """
        repo_root, hive_path = single_hive
        
        # Change to repo_root so _create_ticket finds correct config
        monkeypatch.chdir(repo_root)
        
        with repo_root_context(repo_root):
            # Create epic
            epic_result = await _create_ticket(
                ticket_type="epic",
                title="Multi-Child Epic",
                hive_name="backend",
                ctx=None
            )
            epic_id = epic_result["ticket_id"]
            
            # Create multiple tasks with same parent
            task_ids = []
            for i in range(3):
                task_result = await _create_ticket(
                    ticket_type="task",
                    title=f"Task {i+1}",
                    parent=epic_id,
                    hive_name="backend",
                    ctx=None
                )
                task_ids.append(task_result["ticket_id"])
            
            # Read epic to verify all children are in array
            epic_path = get_ticket_path(epic_id, "epic")
            epic = read_ticket(epic_path)
            
            assert epic.children is not None, "Epic should have children array"
            assert len(epic.children) == 3, "Epic should have 3 children"
            for task_id in task_ids:
                assert task_id in epic.children, f"Epic should contain {task_id} in children"

    @pytest.mark.asyncio
    async def test_dependency_bidirectional_sync(self, single_hive, monkeypatch):
        """
        Verify that up_dependencies and down_dependencies are synced bidirectionally.
        """
        repo_root, hive_path = single_hive
        
        # Change to repo_root so _create_ticket finds correct config
        monkeypatch.chdir(repo_root)
        
        with repo_root_context(repo_root):
            # Create two tasks
            task1_result = await _create_ticket(
                ticket_type="task",
                title="Task 1",
                hive_name="backend",
                ctx=None
            )
            task1_id = task1_result["ticket_id"]
            
            # Create task2 that depends on task1 (task1 blocks task2)
            task2_result = await _create_ticket(
                ticket_type="task",
                title="Task 2",
                up_dependencies=[task1_id],  # task2 depends on task1
                hive_name="backend",
                ctx=None
            )
            task2_id = task2_result["ticket_id"]
            
            # Read both tasks to verify bidirectional sync
            task1_path = get_ticket_path(task1_id, "task")
            task2_path = get_ticket_path(task2_id, "task")
            
            task1 = read_ticket(task1_path)
            task2 = read_ticket(task2_path)
            
            # Verify forward relationship: task2 depends on task1
            assert task2.up_dependencies is not None and task1_id in task2.up_dependencies, \
                "Task2 should have task1 in up_dependencies"
            
            # Verify reverse relationship: task1 blocks task2
            assert task1.down_dependencies is not None and task2_id in task1.down_dependencies, \
                "Task1 should have task2 in down_dependencies (bidirectional sync)"

    @pytest.mark.asyncio
    async def test_fixture_missing_children_validation(self, hive_with_tickets):
        """
        Verify that fixture-created tickets have missing children arrays (validation test).
        
        This test validates the test setup itself - ensuring that when we test fixture
        behavior, the fixture really doesn't populate children arrays.
        """
        repo_root, hive_path, epic_id, task_id, subtask_id = hive_with_tickets
        
        with repo_root_context(repo_root):
            epic_path = get_ticket_path(epic_id, "epic")
            task_path = get_ticket_path(task_id, "task")
            
            epic = read_ticket(epic_path)
            task = read_ticket(task_path)
            
            # Validate that fixture doesn't populate children
            # This validates the test infrastructure itself
            if epic.children is not None:
                assert task_id not in epic.children, \
                    "Test validation failed: fixture unexpectedly populated epic.children"
            if task.children is not None:
                assert subtask_id not in task.children, \
                    "Test validation failed: fixture unexpectedly populated task.children"

    @pytest.mark.asyncio
    async def test_empty_children_array_behavior(self, single_hive, monkeypatch):
        """
        Test that tickets with no children have None or empty array (not undefined behavior).
        """
        repo_root, hive_path = single_hive
        
        # Change to repo_root so _create_ticket finds correct config
        monkeypatch.chdir(repo_root)
        
        with repo_root_context(repo_root):
            # Create standalone epic with no children
            result = await _create_ticket(
                ticket_type="epic",
                title="Standalone Epic",
                hive_name="backend",
                ctx=None
            )
            epic_id = result["ticket_id"]
            
            epic_path = get_ticket_path(epic_id, "epic")
            epic = read_ticket(epic_path)
            
            # Verify children is None or empty list (both valid)
            assert epic.children is None or isinstance(epic.children, list), \
                "Children must be None or list type"
            if epic.children is not None:
                assert len(epic.children) == 0, \
                    "Childless epic should have empty children array"

    @pytest.mark.asyncio
    async def test_mcp_syncs_both_fixture_and_mcp_created_tickets(self, hive_with_tickets):
        """
        Test that MCP functions can sync relationships even with fixture-created tickets.
        
        This verifies the integration between fixture setup (one-way) and MCP operations
        (bidirectional sync) - ensuring they work together correctly.
        """
        repo_root, hive_path, epic_id, task_id, subtask_id = hive_with_tickets
        
        with repo_root_context(repo_root):
            # Create a new task using MCP with fixture's epic as parent
            new_task_result = await _create_ticket(
                ticket_type="task",
                title="MCP Task with Fixture Epic Parent",
                parent=epic_id,
                hive_name="backend",
                ctx=None
            )
            new_task_id = new_task_result["ticket_id"]
            
            # Verify bidirectional sync worked between MCP-created task and fixture epic
            epic_path = get_ticket_path(epic_id, "epic")
            epic = read_ticket(epic_path)
            
            new_task_path = get_ticket_path(new_task_id, "task")
            new_task = read_ticket(new_task_path)
            
            # New task should have epic as parent
            assert new_task.parent == epic_id, \
                "MCP-created task should have fixture epic as parent"
            
            # Epic should have new task in children (even though epic was fixture-created)
            assert epic.children is not None and new_task_id in epic.children, \
                "Fixture epic should have MCP task in children after MCP creation"
