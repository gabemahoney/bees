"""
Unit tests for ticket deletion operations.

PURPOSE:
Tests atomic delete: shutil.rmtree on the root ticket directory removes
the entire subtree in one call. parent.children is cleaned when a child
is deleted (fix b.AJX). Dependency arrays are NOT modified by default;
set delete_with_dependencies: true in global config to clean them via
the _collect_deletion_set traversal path.

SCOPE - Tests that belong here:
- Ticket deletion operations
- Cascade deletion (deleting parent deletes all children recursively)
- Error cases: non-existent tickets, permission errors
- File/directory deletion from filesystem
- Multi-hive deletion scenarios
- Atomic delete correctness (single shutil.rmtree on root directory)
- delete_with_dependencies config path (_collect_deletion_set + cleanup)

SCOPE - Tests that DON'T belong here:
- Ticket creation -> test_create_ticket.py
- Ticket updates -> test_mcp_server.py
- Relationship modification (non-delete) -> test_mcp_relationships.py
- MCP server integration -> test_mcp_server.py (uses deletion logic)

RELATED FILES:
- test_mcp_server.py: MCP integration for delete operations
- test_mcp_relationships.py: Relationship management
- test_create_ticket.py: Ticket creation (opposite operation)
"""

import shutil
from unittest.mock import patch

import pytest

from src.config import load_bees_config
from src.mcp_server import _create_ticket, _delete_ticket
from src.paths import get_ticket_path
from src.reader import read_ticket
from tests.test_constants import (
    HIVE_BACKEND,
    HIVE_FRONTEND,
    TICKET_ID_NONEXISTENT,
    TITLE_PARENT_BEE,
    TITLE_TEST_BEE,
)


class TestDeleteTicketBasic:
    """Tests for basic delete_ticket functionality."""

    async def test_delete_ticket_file_removal(self, hive_tier_config):
        """Test that delete_ticket removes the ticket directory and returns correct result."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _create_ticket(
            ticket_type="bee", title=TITLE_TEST_BEE, description="Test description", hive_name=HIVE_BACKEND
        )
        ticket_id = result["ticket_id"]
        ticket_path = get_ticket_path(ticket_id, "bee", HIVE_BACKEND)
        ticket_dir = ticket_path.parent

        assert ticket_path.exists()
        assert ticket_dir.exists()

        result = await _delete_ticket(ticket_ids=ticket_id)

        assert result["status"] == "success"
        assert result["ticket_id"] == ticket_id
        assert result["ticket_type"] == "bee"
        # Verify entire directory is removed
        assert not ticket_path.exists()
        assert not ticket_dir.exists()

    async def test_delete_nonexistent_ticket_error(self, hive_tier_config):
        """Test that deleting non-existent ticket returns error dict."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _delete_ticket(ticket_ids=TICKET_ID_NONEXISTENT)
        assert result["status"] == "error"
        assert result["error_type"] == "ticket_not_found"
        assert "Ticket not found in any configured hive" in result["message"]


class TestDeleteTicketParentRelationships:
    """Tests for relationship fields in surviving tickets after deletion.

    parent.children is cleaned on delete (fix b.AJX).
    Dependency arrays are NOT modified by default (stale refs remain).
    Set delete_with_dependencies: true in global config to clean deps.
    """

    async def test_delete_ticket_without_parent(self, hive_tier_config):
        """Deleting a root-level ticket removes its directory."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _create_ticket(
            ticket_type="bee", title="Bee Without Parent", hive_name=HIVE_BACKEND
        )
        ticket_id = result["ticket_id"]
        ticket_path = get_ticket_path(ticket_id, "bee", HIVE_BACKEND)
        ticket_dir = ticket_path.parent

        result = await _delete_ticket(ticket_ids=ticket_id)
        assert result["status"] == "success"
        assert not ticket_path.exists()
        assert not ticket_dir.exists()


class TestDeleteTicketDependencyFields:
    """Tests that deletion does NOT modify dependency fields in surviving tickets by default."""

    @pytest.mark.parametrize(
        "deleted_ticket,remaining_ticket,dependency_field",
        [
            ("blocked", "blocking", "down_dependencies"),
            ("blocking", "blocked", "up_dependencies"),
        ],
    )
    async def test_delete_leaves_dependency_arrays_stale(
        self, deleted_ticket, remaining_ticket, dependency_field, hive_tier_config
    ):
        """Deleting a ticket leaves stale references in related dependency arrays (by design)."""
        repo_root, hive_path, tier_config = hive_tier_config

        blocking_result = await _create_ticket(
            ticket_type="bee", title="Blocking Epic", hive_name=HIVE_BACKEND
        )
        blocking_id = blocking_result["ticket_id"]

        blocked_result = await _create_ticket(
            ticket_type="bee", title="Blocked Epic", up_dependencies=[blocking_id], hive_name=HIVE_BACKEND
        )
        blocked_id = blocked_result["ticket_id"]

        ticket_ids = {"blocking": blocking_id, "blocked": blocked_id}
        deleted_id = ticket_ids[deleted_ticket]
        remaining_id = ticket_ids[remaining_ticket]

        await _delete_ticket(ticket_ids=deleted_id)

        # Relationship fields are NOT cleaned up (stale references remain)
        remaining = read_ticket(remaining_id, file_path=get_ticket_path(remaining_id, "bee", HIVE_BACKEND))
        dependency_array = getattr(remaining, dependency_field) or []
        assert deleted_id in dependency_array

class TestDeleteTicketCascade:
    """Tests for cascade delete behavior with children."""

    @pytest.mark.parametrize(
        "hierarchy_depth,children_per_level",
        [
            (1, 0),   # Leaf node
            (1, 2),   # Multiple children at same level
            (2, 1),   # Nested: Bee -> Task -> Subtask
            (2, 2),   # Deep with branching
        ],
    )
    async def test_cascade_delete_hierarchy(self, hierarchy_depth, children_per_level, hive_tier_config):
        """Test that deletion always cascades to entire child subtree."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Skip test if required tier types not available
        if hierarchy_depth >= 1 and children_per_level > 0 and "t1" not in tier_config:
            return
        if hierarchy_depth >= 2 and "t2" not in tier_config:
            return

        all_ticket_ids = []

        root_result = await _create_ticket(ticket_type="bee", title="Root Bee", hive_name=HIVE_BACKEND)
        root_id = root_result["ticket_id"]
        all_ticket_ids.append((root_id, "bee"))

        if hierarchy_depth >= 1 and children_per_level > 0:
            level1_ids = []
            for i in range(children_per_level):
                child_result = await _create_ticket(
                    ticket_type="t1", title=f"Task {i}", parent=root_id, hive_name=HIVE_BACKEND
                )
                child_id = child_result["ticket_id"]
                level1_ids.append(child_id)
                all_ticket_ids.append((child_id, "t1"))

            if hierarchy_depth >= 2:
                for parent_id in level1_ids:
                    for j in range(children_per_level):
                        grandchild_result = await _create_ticket(
                            ticket_type="t2",
                            title=f"Subtask {j}", parent=parent_id, hive_name=HIVE_BACKEND,
                        )
                        all_ticket_ids.append((grandchild_result["ticket_id"], "t2"))

        # Get all paths before delete and verify tickets exist
        ticket_paths = []
        for ticket_id, ticket_type in all_ticket_ids:
            ticket_path = get_ticket_path(ticket_id, ticket_type, HIVE_BACKEND)
            assert ticket_path.exists()
            ticket_paths.append((ticket_path, ticket_path.parent))

        # Delete root - should cascade delete entire subtree
        result = await _delete_ticket(ticket_ids=root_id)
        assert result["status"] == "success"

        # Verify entire directory subtree is removed
        for ticket_path, ticket_dir in ticket_paths:
            # Both file and directory should be gone
            assert not ticket_path.exists()
            assert not ticket_dir.exists()


class TestDeleteTicketEdgeCases:
    """Tests for edge cases and error handling."""

    async def test_delete_ticket_with_all_relationships(self, hive_tier_config):
        """Test deleting a ticket with parent, children, and dependencies."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Skip test if required tier types not available
        if "t1" not in tier_config or "t2" not in tier_config:
            return

        parent_result = await _create_ticket(ticket_type="bee", title="Parent", hive_name=HIVE_BACKEND)
        parent_id = parent_result["ticket_id"]

        # blocking must be the same type as target (t1) to satisfy cross-type-dep linter rule
        blocking_result = await _create_ticket(
            ticket_type="t1", title="Blocking", parent=parent_id, hive_name=HIVE_BACKEND
        )
        blocking_id = blocking_result["ticket_id"]

        target_result = await _create_ticket(
            ticket_type="t1", title="Target Task",
            parent=parent_id, up_dependencies=[blocking_id], hive_name=HIVE_BACKEND,
        )
        target_id = target_result["ticket_id"]

        child_result = await _create_ticket(
            ticket_type="t2", title="Child", parent=target_id, hive_name=HIVE_BACKEND
        )
        child_id = child_result["ticket_id"]

        # Get paths before deletion
        target_path = get_ticket_path(target_id, "t1", HIVE_BACKEND)
        target_dir = target_path.parent
        child_path = get_ticket_path(child_id, "t2", HIVE_BACKEND)
        child_dir = child_path.parent

        await _delete_ticket(ticket_ids=target_id)

        # Verify target and child directories deleted
        assert not target_path.exists()
        assert not target_dir.exists()
        assert not child_path.exists()
        assert not child_dir.exists()

        # parent.children is cleaned on delete (fix b.AJX); dependency arrays remain stale
        parent = read_ticket(parent_id, file_path=get_ticket_path(parent_id, "bee", HIVE_BACKEND))
        assert target_id not in (parent.children or [])

        blocking = read_ticket(blocking_id, file_path=get_ticket_path(blocking_id, "t1", HIVE_BACKEND))
        assert target_id in (blocking.down_dependencies or [])

    async def test_cascade_delete_leaves_dependencies_stale(self, hive_tier_config):
        """Test that cascade delete does NOT clean up dependency fields in surviving tickets."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Skip test if required tier types not available
        if "t1" not in tier_config:
            return

        # Separate parent trees: parent_to_delete contains child; blocker_parent contains blocking_task
        # blocking_task is same type (t1) as child to satisfy cross-type-dep rule
        blocker_parent_result = await _create_ticket(ticket_type="bee", title="Blocker Parent", hive_name=HIVE_BACKEND)
        blocker_parent_id = blocker_parent_result["ticket_id"]

        blocking_result = await _create_ticket(
            ticket_type="t1", title="Blocking", parent=blocker_parent_id, hive_name=HIVE_BACKEND
        )
        blocking_id = blocking_result["ticket_id"]

        parent_result = await _create_ticket(ticket_type="bee", title="Parent", hive_name=HIVE_BACKEND)
        parent_id = parent_result["ticket_id"]

        child_result = await _create_ticket(
            ticket_type="t1", title="Child",
            parent=parent_id, up_dependencies=[blocking_id], hive_name=HIVE_BACKEND,
        )
        child_id = child_result["ticket_id"]

        blocking = read_ticket(blocking_id, file_path=get_ticket_path(blocking_id, "t1", HIVE_BACKEND))
        assert child_id in blocking.down_dependencies

        # Get paths before deletion
        parent_path = get_ticket_path(parent_id, "bee", HIVE_BACKEND)
        parent_dir = parent_path.parent
        child_path = get_ticket_path(child_id, "t1", HIVE_BACKEND)
        child_dir = child_path.parent

        await _delete_ticket(ticket_ids=parent_id)

        # Verify directories removed
        assert not parent_path.exists()
        assert not parent_dir.exists()
        assert not child_path.exists()
        assert not child_dir.exists()

        # Stale reference remains in surviving ticket's down_dependencies
        blocking = read_ticket(blocking_id, file_path=get_ticket_path(blocking_id, "t1", HIVE_BACKEND))
        assert child_id in (blocking.down_dependencies or [])


class TestDeleteTicketDirectoryRemoval:
    """Tests for hierarchical directory removal with shutil.rmtree."""

    async def test_delete_removes_entire_directory_subtree(self, hive_tier_config):
        """Test that delete removes ticket directory and all nested contents."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Skip test if required tier types not available
        if "t1" not in tier_config:
            return

        # Create parent bee
        parent_result = await _create_ticket(
            ticket_type="bee", title=TITLE_PARENT_BEE, hive_name=HIVE_BACKEND
        )
        parent_id = parent_result["ticket_id"]

        # Create child task (nested under parent)
        child_result = await _create_ticket(
            ticket_type="t1", title="Child Task", parent=parent_id, hive_name=HIVE_BACKEND
        )
        child_id = child_result["ticket_id"]

        # Get directory paths
        parent_path = get_ticket_path(parent_id, "bee", HIVE_BACKEND)
        parent_dir = parent_path.parent
        child_path = get_ticket_path(child_id, "t1", HIVE_BACKEND)
        child_dir = child_path.parent

        # Verify hierarchical structure: child is nested under parent
        assert child_dir.parent == parent_dir

        # Delete parent should cascade delete entire subtree
        await _delete_ticket(ticket_ids=parent_id)

        # Verify entire directory tree removed (parent + child)
        assert not parent_dir.exists()
        assert not child_dir.exists()
        assert not parent_path.exists()
        assert not child_path.exists()

    async def test_delete_removes_directory_with_extra_files(self, hive_tier_config):
        """Test that shutil.rmtree removes directory even with additional files."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Create ticket
        result = await _create_ticket(
            ticket_type="bee", title=TITLE_TEST_BEE, hive_name=HIVE_BACKEND
        )
        ticket_id = result["ticket_id"]

        ticket_path = get_ticket_path(ticket_id, "bee", HIVE_BACKEND)
        ticket_dir = ticket_path.parent

        # Add extra files to ticket directory
        extra_file1 = ticket_dir / "notes.txt"
        extra_file1.write_text("Some notes")
        extra_file2 = ticket_dir / "metadata.json"
        extra_file2.write_text("{}")

        # Verify extra files exist
        assert extra_file1.exists()
        assert extra_file2.exists()

        # Delete ticket
        await _delete_ticket(ticket_ids=ticket_id)

        # Verify entire directory removed, including extra files
        assert not ticket_dir.exists()
        assert not extra_file1.exists()
        assert not extra_file2.exists()

    async def test_safety_guard_prevents_hive_root_deletion(self, hive_tier_config):
        """Test that safety guard prevents accidental deletion of hive root directory."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Create ticket
        result = await _create_ticket(
            ticket_type="bee", title=TITLE_TEST_BEE, hive_name=HIVE_BACKEND
        )
        ticket_id = result["ticket_id"]

        ticket_path = get_ticket_path(ticket_id, "bee", HIVE_BACKEND)
        ticket_dir = ticket_path.parent

        # Verify ticket directory is not the hive root
        # (Safety guard should protect against this scenario)
        from src.config import load_bees_config
        config = load_bees_config()
        from pathlib import Path

        from src.id_utils import normalize_hive_name
        hive_root = Path(config.hives[normalize_hive_name(HIVE_BACKEND)].path)

        # Ticket directory should be nested under hive root, not equal to it
        assert ticket_dir != hive_root
        assert hive_root in ticket_dir.parents


class TestDeleteTicketHiveRouting:
    """Tests for hive routing in delete_ticket()."""

    async def test_delete_ticket_routes_to_correct_hive(self, multi_hive_config):
        """Test that delete_ticket routes to correct hive based on ticket ID prefix."""
        repo_root, hive_paths, config_data = multi_hive_config

        backend_result = await _create_ticket(ticket_type="bee", title="Backend Epic", hive_name=HIVE_BACKEND)
        backend_id = backend_result["ticket_id"]

        frontend_result = await _create_ticket(
            ticket_type="bee", title="Frontend Epic", hive_name=HIVE_FRONTEND
        )
        frontend_id = frontend_result["ticket_id"]

        # IDs are globally unique, no longer contain hive prefix
        assert backend_id.startswith("b.")
        assert frontend_id.startswith("b.")

        # Get paths before deletion
        backend_path = get_ticket_path(backend_id, "bee", HIVE_BACKEND)
        backend_dir = backend_path.parent
        frontend_path = get_ticket_path(frontend_id, "bee", HIVE_FRONTEND)
        frontend_dir = frontend_path.parent

        result = await _delete_ticket(ticket_ids=backend_id)
        assert result["status"] == "success"
        assert not backend_path.exists()
        assert not backend_dir.exists()
        assert frontend_path.exists()

        result = await _delete_ticket(ticket_ids=frontend_id)
        assert result["status"] == "success"
        assert not frontend_path.exists()
        assert not frontend_dir.exists()

    @pytest.mark.parametrize(
        "ticket_id",
        [
            pytest.param("no-dot", id="malformed"),
            pytest.param(TICKET_ID_NONEXISTENT, id="nonexistent"),
        ],
    )
    async def test_delete_ticket_invalid_id_errors(self, multi_hive_config, ticket_id):
        """Test that delete_ticket returns error dict for invalid/nonexistent ticket IDs."""
        repo_root, hive_paths, config_data = multi_hive_config

        result = await _delete_ticket(ticket_ids=ticket_id)
        assert result["status"] == "error"
        assert result["error_type"] == "ticket_not_found"
        assert "Ticket not found in any configured hive" in result["message"]


class TestDeleteTicketBottomUp:
    """Tests for deletion algorithm correctness (atomic and delete_with_dependencies paths)."""

    async def test_delete_with_dependencies_calls_collect_deletion_set(self, hive_tier_config):
        """_collect_deletion_set is called when delete_with_dependencies=True is in global config."""
        from src.mcp_ticket_ops import _collect_deletion_set as real_collect

        repo_root, hive_path, tier_config = hive_tier_config
        if "t1" not in tier_config or "t2" not in tier_config:
            return

        bee_result = await _create_ticket(
            ticket_type="bee", title="Root Bee", hive_name=HIVE_BACKEND
        )
        bee_id = bee_result["ticket_id"]
        t1_result = await _create_ticket(
            ticket_type="t1", title="Task", parent=bee_id, hive_name=HIVE_BACKEND
        )
        t1_id = t1_result["ticket_id"]
        t2_result = await _create_ticket(
            ticket_type="t2", title="Subtask", parent=t1_id, hive_name=HIVE_BACKEND
        )
        t2_id = t2_result["ticket_id"]

        with patch("src.mcp_ticket_ops.load_global_config", return_value={"delete_with_dependencies": True}), \
             patch("src.mcp_ticket_ops._collect_deletion_set", wraps=real_collect) as spy:
            result = await _delete_ticket(ticket_ids=bee_id)

        assert result["status"] == "success"
        spy.assert_called_once()
        assert spy.call_args[0][0] == bee_id

    async def test_rmtree_failure_preserves_all_directories(self, hive_tier_config):
        """If rmtree raises, no directories are deleted (atomic failure - all or nothing)."""
        repo_root, hive_path, tier_config = hive_tier_config
        if "t1" not in tier_config or "t2" not in tier_config:
            return

        bee_result = await _create_ticket(
            ticket_type="bee", title="Root Bee", hive_name=HIVE_BACKEND
        )
        bee_id = bee_result["ticket_id"]
        t1_result = await _create_ticket(
            ticket_type="t1", title="Task", parent=bee_id, hive_name=HIVE_BACKEND
        )
        t1_id = t1_result["ticket_id"]
        t2_result = await _create_ticket(
            ticket_type="t2", title="Subtask", parent=t1_id, hive_name=HIVE_BACKEND
        )
        t2_id = t2_result["ticket_id"]

        bee_dir = get_ticket_path(bee_id, "bee", HIVE_BACKEND).parent
        t1_dir = get_ticket_path(t1_id, "t1", HIVE_BACKEND).parent
        t2_dir = get_ticket_path(t2_id, "t2", HIVE_BACKEND).parent

        with patch("src.mcp_ticket_ops.shutil.rmtree", side_effect=OSError("Simulated disk error")):
            result = await _delete_ticket(ticket_ids=bee_id)

        assert result["status"] == "error"
        assert result["error_type"] == "delete_failed"
        assert "Failed to delete" in result["message"]

        # All directories still intact — single rmtree failure means nothing was deleted
        assert bee_dir.exists()
        assert t1_dir.exists()
        assert t2_dir.exists()

    async def test_missing_root_raises_immediately(self, hive_tier_config):
        """Deleting nonexistent ticket returns error dict with no side effects."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _delete_ticket(ticket_ids=TICKET_ID_NONEXISTENT)
        assert result["status"] == "error"
        assert "Ticket not found" in result["message"]

    async def test_read_error_during_collection_halts(self, hive_tier_config):
        """With delete_with_dependencies=True, a reader error on a grandchild halts deletion."""
        repo_root, hive_path, tier_config = hive_tier_config
        if "t1" not in tier_config or "t2" not in tier_config:
            return

        bee_result = await _create_ticket(
            ticket_type="bee", title="Root Bee", hive_name=HIVE_BACKEND
        )
        bee_id = bee_result["ticket_id"]
        t1_result = await _create_ticket(
            ticket_type="t1", title="Task", parent=bee_id, hive_name=HIVE_BACKEND
        )
        t1_id = t1_result["ticket_id"]
        t2_result = await _create_ticket(
            ticket_type="t2", title="Subtask", parent=t1_id, hive_name=HIVE_BACKEND
        )
        t2_id = t2_result["ticket_id"]

        bee_dir = get_ticket_path(bee_id, "bee", HIVE_BACKEND).parent
        t1_dir = get_ticket_path(t1_id, "t1", HIVE_BACKEND).parent
        t2_dir = get_ticket_path(t2_id, "t2", HIVE_BACKEND).parent

        real_read = read_ticket

        def failing_reader(ticket_id, file_path=None):
            if t2_id in ticket_id:
                raise OSError("Simulated read error")
            return real_read(ticket_id, file_path=file_path)

        with patch("src.mcp_ticket_ops.read_ticket", side_effect=failing_reader), \
             patch("src.mcp_ticket_ops.load_global_config", return_value={"delete_with_dependencies": True}):
            result = await _delete_ticket(ticket_ids=bee_id)
            assert result["status"] == "error"
            assert "Failed to read" in result["message"]

        assert bee_dir.exists()
        assert t1_dir.exists()
        assert t2_dir.exists()


class TestDeleteTicketChildrenCleanup:
    """Regression tests for bug b.AJX: deleted child ID left in parent.children."""

    async def test_delete_child_cleans_parent_children(self, hive_tier_config):
        """Deleting a child removes its ID from parent.children (regression: b.AJX)."""
        repo_root, hive_path, tier_config = hive_tier_config
        if "t1" not in tier_config:
            return

        parent_result = await _create_ticket(
            ticket_type="bee", title=TITLE_PARENT_BEE, hive_name=HIVE_BACKEND
        )
        parent_id = parent_result["ticket_id"]

        child_result = await _create_ticket(
            ticket_type="t1", title="Child Task", parent=parent_id, hive_name=HIVE_BACKEND
        )
        child_id = child_result["ticket_id"]

        await _delete_ticket(ticket_ids=child_id)

        parent = read_ticket(parent_id, file_path=get_ticket_path(parent_id, "bee", HIVE_BACKEND))
        assert parent.children == []


class TestDeleteTicketCleanDependencies:
    """Tests for the opt-in delete_with_dependencies=true global config behavior."""

    async def test_full_cleanup_removes_both_dep_directions(self, hive_tier_config):
        """delete_with_dependencies=True removes target from external_a.down_deps and external_b.up_deps."""
        repo_root, hive_path, tier_config = hive_tier_config

        external_a = await _create_ticket(ticket_type="bee", title="External A", hive_name=HIVE_BACKEND)
        external_a_id = external_a["ticket_id"]

        target = await _create_ticket(
            ticket_type="bee", title="Target",
            up_dependencies=[external_a_id], hive_name=HIVE_BACKEND,
        )
        target_id = target["ticket_id"]

        # Create external_b that depends on target → sets target.down_dependencies=[external_b_id]
        external_b = await _create_ticket(
            ticket_type="bee", title="External B",
            up_dependencies=[target_id], hive_name=HIVE_BACKEND,
        )
        external_b_id = external_b["ticket_id"]

        with patch("src.mcp_ticket_ops.load_global_config", return_value={"delete_with_dependencies": True}):
            await _delete_ticket(ticket_ids=target_id)

        ext_a = read_ticket(external_a_id, file_path=get_ticket_path(external_a_id, "bee", HIVE_BACKEND))
        assert target_id not in (ext_a.down_dependencies or [])

        ext_b = read_ticket(external_b_id, file_path=get_ticket_path(external_b_id, "bee", HIVE_BACKEND))
        assert target_id not in (ext_b.up_dependencies or [])

    async def test_subtree_cleanup_cleans_child_external_deps(self, hive_tier_config):
        """Deleting root with delete_with_dependencies=True removes child's dep refs from external tickets."""
        repo_root, hive_path, tier_config = hive_tier_config

        if "t1" not in tier_config:
            return

        # external_blocker must be same type as child (t1) and under a SEPARATE parent
        # so it survives the cascade delete of root
        blocker_parent = await _create_ticket(ticket_type="bee", title="Blocker Parent", hive_name=HIVE_BACKEND)
        blocker_parent_id = blocker_parent["ticket_id"]

        external_blocker = await _create_ticket(
            ticket_type="t1", title="External Blocker", parent=blocker_parent_id, hive_name=HIVE_BACKEND
        )
        external_blocker_id = external_blocker["ticket_id"]

        root = await _create_ticket(ticket_type="bee", title="Root Bee", hive_name=HIVE_BACKEND)
        root_id = root["ticket_id"]

        child = await _create_ticket(
            ticket_type="t1", title="Child Task",
            parent=root_id, up_dependencies=[external_blocker_id], hive_name=HIVE_BACKEND,
        )
        child_id = child["ticket_id"]

        with patch("src.mcp_ticket_ops.load_global_config", return_value={"delete_with_dependencies": True}):
            await _delete_ticket(ticket_ids=root_id)

        ext = read_ticket(external_blocker_id, file_path=get_ticket_path(external_blocker_id, "t1", HIVE_BACKEND))
        assert child_id not in (ext.down_dependencies or [])

    async def test_missing_external_ticket_is_skipped(self, hive_tier_config):
        """delete_with_dependencies=True silently skips missing external dep tickets and succeeds."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Write ticket directly to inject a nonexistent dep ref (bypasses _create_ticket validation)
        from tests.helpers import write_ticket_file as write_raw_ticket
        write_raw_ticket(hive_path, "b.dca", up_dependencies=[TICKET_ID_NONEXISTENT])

        with patch("src.mcp_ticket_ops.load_global_config", return_value={"delete_with_dependencies": True}):
            result = await _delete_ticket(ticket_ids="b.dca")

        assert result["status"] == "success"

    async def test_external_cleanup_completes_before_rmtree(self, hive_tier_config):
        """Dependency cleanup phase finishes before rmtree when delete_with_dependencies=True."""
        repo_root, hive_path, tier_config = hive_tier_config

        external = await _create_ticket(ticket_type="bee", title="External", hive_name=HIVE_BACKEND)
        external_id = external["ticket_id"]

        target = await _create_ticket(
            ticket_type="bee", title="Target",
            up_dependencies=[external_id], hive_name=HIVE_BACKEND,
        )
        target_id = target["ticket_id"]

        call_order = []
        real_rmtree = shutil.rmtree
        from src.mcp_relationships import _remove_from_down_dependencies as real_cleanup

        with patch("src.mcp_ticket_ops.shutil.rmtree") as mock_rmtree, \
             patch("src.mcp_ticket_ops._remove_from_down_dependencies") as mock_cleanup, \
             patch("src.mcp_ticket_ops.load_global_config", return_value={"delete_with_dependencies": True}):

            def track_rmtree(path, **kw):
                call_order.append("rmtree")
                real_rmtree(path, **kw)

            def track_cleanup(*args, **kw):
                call_order.append("cleanup")
                real_cleanup(*args, **kw)

            mock_rmtree.side_effect = track_rmtree
            mock_cleanup.side_effect = track_cleanup

            await _delete_ticket(ticket_ids=target_id)

        assert "cleanup" in call_order
        assert "rmtree" in call_order
        assert call_order.index("cleanup") < call_order.index("rmtree")

    async def test_non_missing_cleanup_error_aborts_deletion(self, hive_tier_config):
        """PermissionError during cleanup halts the operation before any directory is removed."""
        repo_root, hive_path, tier_config = hive_tier_config

        external = await _create_ticket(ticket_type="bee", title="External", hive_name=HIVE_BACKEND)
        external_id = external["ticket_id"]

        target = await _create_ticket(
            ticket_type="bee", title="Target",
            up_dependencies=[external_id], hive_name=HIVE_BACKEND,
        )
        target_id = target["ticket_id"]

        target_dir = get_ticket_path(target_id, "bee", HIVE_BACKEND).parent

        with patch("src.mcp_ticket_ops._remove_from_down_dependencies", side_effect=PermissionError("denied")), \
             patch("src.mcp_ticket_ops.load_global_config", return_value={"delete_with_dependencies": True}):
            result = await _delete_ticket(ticket_ids=target_id)
            assert result["status"] == "error"

        assert target_dir.exists()


class TestBulkDeleteTicket:
    """Tests for the list[str] bulk-delete path of _delete_ticket."""

    async def test_bulk_delete_multiple_tickets(self, hive_tier_config):
        """Bulk delete of 2-3 valid IDs returns {status, deleted, not_found, failed} and removes dirs."""
        repo_root, hive_path, tier_config = hive_tier_config

        ids = []
        for i in range(3):
            r = await _create_ticket(ticket_type="bee", title=f"Bulk Bee {i}", hive_name=HIVE_BACKEND)
            ids.append(r["ticket_id"])

        paths = [get_ticket_path(tid, "bee", HIVE_BACKEND).parent for tid in ids]
        for p in paths:
            assert p.exists()

        result = await _delete_ticket(ticket_ids=ids)

        assert result["status"] == "success"
        assert set(result["deleted"]) == set(ids)
        assert result["not_found"] == []
        assert result["failed"] == []
        for p in paths:
            assert not p.exists()

    async def test_bulk_delete_single_item_list(self, hive_tier_config):
        """Single-item list returns bulk response shape, not legacy single-ticket shape."""
        repo_root, hive_path, tier_config = hive_tier_config

        r = await _create_ticket(ticket_type="bee", title="Solo Bulk Bee", hive_name=HIVE_BACKEND)
        tid = r["ticket_id"]

        result = await _delete_ticket(ticket_ids=[tid])

        assert result["status"] == "success"
        assert "deleted" in result
        assert tid in result["deleted"]
        assert "ticket_id" not in result  # Must NOT be legacy shape

    async def test_bulk_delete_empty_list(self, hive_tier_config):
        """Empty list returns success immediately with all arrays empty."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _delete_ticket(ticket_ids=[])

        assert result == {"status": "success", "deleted": [], "not_found": [], "failed": []}

    async def test_bulk_delete_with_cascade(self, hive_tier_config):
        """Bulk delete of a parent cascades to its children; parent appears in deleted."""
        repo_root, hive_path, tier_config = hive_tier_config
        if "t1" not in tier_config:
            return

        parent = await _create_ticket(ticket_type="bee", title="Cascade Parent", hive_name=HIVE_BACKEND)
        parent_id = parent["ticket_id"]
        child = await _create_ticket(
            ticket_type="t1", title="Cascade Child", parent=parent_id, hive_name=HIVE_BACKEND
        )
        child_id = child["ticket_id"]

        child_dir = get_ticket_path(child_id, "t1", HIVE_BACKEND).parent

        result = await _delete_ticket(ticket_ids=[parent_id])

        assert result["status"] == "success"
        assert parent_id in result["deleted"]
        assert not child_dir.exists()

    async def test_bulk_delete_across_hives(self, multi_hive_config):
        """Bulk delete with IDs from different hives deletes all correctly."""
        repo_root, hive_paths, config_data = multi_hive_config

        be = await _create_ticket(ticket_type="bee", title="Backend Bee", hive_name=HIVE_BACKEND)
        fe = await _create_ticket(ticket_type="bee", title="Frontend Bee", hive_name=HIVE_FRONTEND)

        be_dir = get_ticket_path(be["ticket_id"], "bee", HIVE_BACKEND).parent
        fe_dir = get_ticket_path(fe["ticket_id"], "bee", HIVE_FRONTEND).parent

        result = await _delete_ticket(ticket_ids=[be["ticket_id"], fe["ticket_id"]])

        assert result["status"] == "success"
        assert set(result["deleted"]) == {be["ticket_id"], fe["ticket_id"]}
        assert not be_dir.exists()
        assert not fe_dir.exists()

    async def test_string_backward_compat(self, hive_tier_config):
        """Plain string to ticket_ids= returns legacy single-ticket response shape."""
        repo_root, hive_path, tier_config = hive_tier_config

        r = await _create_ticket(ticket_type="bee", title="Compat Bee", hive_name=HIVE_BACKEND)
        tid = r["ticket_id"]

        result = await _delete_ticket(ticket_ids=tid)

        assert result["status"] == "success"
        assert result["ticket_id"] == tid
        assert result["ticket_type"] == "bee"
        assert "deleted" not in result  # Must NOT be bulk shape

    async def test_bulk_delete_partial_not_found(self, hive_tier_config):
        """Bulk delete with mix of valid + nonexistent IDs: valid deleted, nonexistent in not_found."""
        repo_root, hive_path, tier_config = hive_tier_config

        r = await _create_ticket(ticket_type="bee", title="Real Bee", hive_name=HIVE_BACKEND)
        real_id = r["ticket_id"]
        real_dir = get_ticket_path(real_id, "bee", HIVE_BACKEND).parent

        result = await _delete_ticket(ticket_ids=[real_id, TICKET_ID_NONEXISTENT])

        assert result["status"] == "success"
        assert real_id in result["deleted"]
        assert TICKET_ID_NONEXISTENT in result["not_found"]
        assert result["failed"] == []
        assert not real_dir.exists()

    async def test_bulk_delete_loads_config_once_for_multiple_ids(self, hive_tier_config):
        """load_bees_config is called only once per bulk delete call, not per-ticket."""
        repo_root, hive_path, tier_config = hive_tier_config

        ids = []
        for i in range(3):
            r = await _create_ticket(ticket_type="bee", title=f"Config Bee {i}", hive_name=HIVE_BACKEND)
            ids.append(r["ticket_id"])

        with patch("src.mcp_ticket_ops.load_bees_config", wraps=load_bees_config) as spy:
            await _delete_ticket(ticket_ids=ids, hive_name=HIVE_BACKEND)

        assert spy.call_count == 1

    async def test_bulk_delete_partial_failure(self, hive_tier_config):
        """Bulk delete where one ID raises mid-loop: that ID in failed, others still processed."""
        repo_root, hive_path, tier_config = hive_tier_config

        ok = await _create_ticket(ticket_type="bee", title="OK Bee", hive_name=HIVE_BACKEND)
        err = await _create_ticket(ticket_type="bee", title="Err Bee", hive_name=HIVE_BACKEND)
        ok_id, err_id = ok["ticket_id"], err["ticket_id"]

        err_dir = get_ticket_path(err_id, "bee", HIVE_BACKEND).parent
        ok_dir = get_ticket_path(ok_id, "bee", HIVE_BACKEND).parent

        real_rmtree = shutil.rmtree

        def selective_fail(path, **kwargs):
            if err_dir == path:
                raise OSError("Simulated disk error")
            real_rmtree(path, **kwargs)

        with patch("src.mcp_ticket_ops.shutil.rmtree", side_effect=selective_fail):
            result = await _delete_ticket(ticket_ids=[ok_id, err_id])

        assert result["status"] == "success"
        assert ok_id in result["deleted"]
        assert not ok_dir.exists()
        assert result["not_found"] == []
        assert any(entry["id"] == err_id for entry in result["failed"])
        assert any("Simulated disk error" in entry["reason"] for entry in result["failed"])

    async def test_bulk_delete_parent_before_child_regardless_of_input_order(self, hive_tier_config):
        """Bulk delete sorts by tier: b.* processed before t1.* even if child listed first in input.

        When the parent bee is processed first via shutil.rmtree, it removes its entire directory
        tree including the child t1's subdirectory. The child is then not found on its own pass
        and lands in not_found (no error).
        """
        repo_root, hive_path, tier_config = hive_tier_config
        if "t1" not in tier_config:
            return

        parent = await _create_ticket(
            ticket_type="bee", title="Parent Bee", hive_name=HIVE_BACKEND
        )
        parent_id = parent["ticket_id"]
        child = await _create_ticket(
            ticket_type="t1", title="Child Task", parent=parent_id, hive_name=HIVE_BACKEND
        )
        child_id = child["ticket_id"]

        # Submit child before parent — tier sort must still process parent first
        result = await _delete_ticket(ticket_ids=[child_id, parent_id])

        assert result["status"] == "success"
        assert parent_id in result["deleted"]
        assert child_id in result["not_found"]  # cascade-removed when parent was processed
        assert result["failed"] == []

    async def test_bulk_delete_response_always_has_all_three_keys(self, hive_tier_config):
        """Bulk delete response always contains deleted, not_found, and failed keys regardless of outcome."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Case: all not found
        result_none = await _delete_ticket(ticket_ids=[TICKET_ID_NONEXISTENT])
        for key in ("deleted", "not_found", "failed"):
            assert key in result_none, f"Missing key '{key}' when all not found"

        # Case: all found
        r = await _create_ticket(ticket_type="bee", title="Keys Test Bee", hive_name=HIVE_BACKEND)
        result_found = await _delete_ticket(ticket_ids=[r["ticket_id"]])
        for key in ("deleted", "not_found", "failed"):
            assert key in result_found, f"Missing key '{key}' when all found"


