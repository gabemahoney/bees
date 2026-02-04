"""
Unit tests for mcp_relationships module.

Tests bidirectional relationship synchronization functions including:
- _update_bidirectional_relationships() main entry point
- Helper functions for parent/child and dependency management
- Edge cases and error handling
"""

import pytest
from pathlib import Path
from datetime import datetime
from src.mcp_relationships import (
    _update_bidirectional_relationships,
    _add_child_to_parent,
    _remove_child_from_parent,
    _set_parent_on_child,
    _remove_parent_from_child,
    _add_to_down_dependencies,
    _remove_from_down_dependencies,
    _add_to_up_dependencies,
    _remove_from_up_dependencies,
)
from src.reader import read_ticket
from src.writer import write_ticket_file
from src.paths import get_ticket_path
from src.config import save_bees_config, BeesConfig, HiveConfig


@pytest.fixture
def setup_hive(tmp_path, monkeypatch):
    """Create temporary hive directory structure for testing."""
    monkeypatch.chdir(tmp_path)

    # Create default hive directory
    default_dir = tmp_path / "default"
    default_dir.mkdir()

    # Initialize .bees/config.json with default hive
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


def create_test_epic(ticket_id: str, children: list[str] | None = None):
    """Helper to create a test epic ticket."""
    frontmatter = {
        "id": ticket_id,
        "type": "epic",
        "title": f"Test Epic {ticket_id}",
        "children": children or [],
        "up_dependencies": [],
        "down_dependencies": [],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "status": "open",
        "bees_version": "1.1"
    }
    write_ticket_file(ticket_id, "epic", frontmatter, f"Description for {ticket_id}")


def create_test_task(ticket_id: str, parent: str | None = None, children: list[str] | None = None):
    """Helper to create a test task ticket."""
    frontmatter = {
        "id": ticket_id,
        "type": "task",
        "title": f"Test Task {ticket_id}",
        "parent": parent,
        "children": children or [],
        "up_dependencies": [],
        "down_dependencies": [],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "status": "open",
        "bees_version": "1.1"
    }
    write_ticket_file(ticket_id, "task", frontmatter, f"Description for {ticket_id}")


def create_test_subtask(ticket_id: str, parent: str):
    """Helper to create a test subtask ticket."""
    frontmatter = {
        "id": ticket_id,
        "type": "subtask",
        "title": f"Test Subtask {ticket_id}",
        "parent": parent,
        "up_dependencies": [],
        "down_dependencies": [],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "status": "open",
        "bees_version": "1.1"
    }
    write_ticket_file(ticket_id, "subtask", frontmatter, f"Description for {ticket_id}")


class TestUpdateBidirectionalRelationships:
    """Tests for _update_bidirectional_relationships main function."""

    def test_update_with_parent(self, setup_hive):
        """Test updating parent relationship adds child to parent's children."""
        # Create parent epic
        create_test_epic("default.bees-ep1")

        # Create child task
        create_test_task("default.bees-tk1")

        # Update bidirectional relationships
        _update_bidirectional_relationships(
            new_ticket_id="default.bees-tk1",
            parent="default.bees-ep1"
        )

        # Verify parent has child in children array
        parent_path = get_ticket_path("default.bees-ep1", "epic")
        parent_ticket = read_ticket(parent_path)
        assert "default.bees-tk1" in parent_ticket.children

    def test_update_with_children(self, setup_hive):
        """Test updating children relationship sets parent on each child."""
        # Create parent epic
        create_test_epic("default.bees-ep1")

        # Create child tasks
        create_test_task("default.bees-tk1")
        create_test_task("default.bees-tk2")

        # Update bidirectional relationships
        _update_bidirectional_relationships(
            new_ticket_id="default.bees-ep1",
            children=["default.bees-tk1", "default.bees-tk2"]
        )

        # Verify children have parent set
        for child_id in ["default.bees-tk1", "default.bees-tk2"]:
            child_path = get_ticket_path(child_id, "task")
            child_ticket = read_ticket(child_path)
            assert child_ticket.parent == "default.bees-ep1"

    def test_update_with_up_dependencies(self, setup_hive):
        """Test updating up_dependencies adds to blocking ticket's down_dependencies."""
        # Create two epics
        create_test_epic("default.bees-ep1")
        create_test_epic("default.bees-ep2")

        # Update bidirectional relationships
        _update_bidirectional_relationships(
            new_ticket_id="default.bees-ep2",
            up_dependencies=["default.bees-ep1"]
        )

        # Verify blocking ticket has dependent in down_dependencies
        blocking_path = get_ticket_path("default.bees-ep1", "epic")
        blocking_ticket = read_ticket(blocking_path)
        assert "default.bees-ep2" in blocking_ticket.down_dependencies

    def test_update_with_down_dependencies(self, setup_hive):
        """Test updating down_dependencies adds to blocked ticket's up_dependencies."""
        # Create two epics
        create_test_epic("default.bees-ep1")
        create_test_epic("default.bees-ep2")

        # Update bidirectional relationships
        _update_bidirectional_relationships(
            new_ticket_id="default.bees-ep1",
            down_dependencies=["default.bees-ep2"]
        )

        # Verify blocked ticket has blocker in up_dependencies
        blocked_path = get_ticket_path("default.bees-ep2", "epic")
        blocked_ticket = read_ticket(blocked_path)
        assert "default.bees-ep1" in blocked_ticket.up_dependencies

    def test_update_nonexistent_parent_raises_error(self, setup_hive):
        """Test that referencing nonexistent parent raises ValueError."""
        create_test_task("default.bees-tk1")

        with pytest.raises(ValueError, match="Parent ticket not found"):
            _update_bidirectional_relationships(
                new_ticket_id="default.bees-tk1",
                parent="default.bees-nonexistent"
            )

    def test_update_nonexistent_child_raises_error(self, setup_hive):
        """Test that referencing nonexistent child raises ValueError."""
        create_test_epic("default.bees-ep1")

        with pytest.raises(ValueError, match="Child ticket not found"):
            _update_bidirectional_relationships(
                new_ticket_id="default.bees-ep1",
                children=["default.bees-nonexistent"]
            )


class TestAddChildToParent:
    """Tests for _add_child_to_parent helper function."""

    def test_add_child_to_parent_success(self, setup_hive):
        """Test successfully adding child to parent's children array."""
        create_test_epic("default.bees-ep1")
        create_test_task("default.bees-tk1")

        _add_child_to_parent("default.bees-tk1", "default.bees-ep1")

        parent_path = get_ticket_path("default.bees-ep1", "epic")
        parent_ticket = read_ticket(parent_path)
        assert "default.bees-tk1" in parent_ticket.children

    def test_add_child_idempotent(self, setup_hive):
        """Test that adding same child multiple times is idempotent."""
        create_test_epic("default.bees-ep1", children=["default.bees-tk1"])
        create_test_task("default.bees-tk1")

        _add_child_to_parent("default.bees-tk1", "default.bees-ep1")

        parent_path = get_ticket_path("default.bees-ep1", "epic")
        parent_ticket = read_ticket(parent_path)
        # Should only appear once
        assert parent_ticket.children.count("default.bees-tk1") == 1

    def test_add_child_nonexistent_parent_raises_error(self, setup_hive):
        """Test that adding child to nonexistent parent raises ValueError."""
        create_test_task("default.bees-tk1")

        with pytest.raises(ValueError, match="Parent ticket not found"):
            _add_child_to_parent("default.bees-tk1", "default.bees-nonexistent")


class TestRemoveChildFromParent:
    """Tests for _remove_child_from_parent helper function."""

    def test_remove_child_from_parent_success(self, setup_hive):
        """Test successfully removing child from parent's children array."""
        create_test_epic("default.bees-ep1", children=["default.bees-tk1"])
        create_test_task("default.bees-tk1", parent="default.bees-ep1")

        _remove_child_from_parent("default.bees-tk1", "default.bees-ep1")

        parent_path = get_ticket_path("default.bees-ep1", "epic")
        parent_ticket = read_ticket(parent_path)
        assert "default.bees-tk1" not in parent_ticket.children

    def test_remove_child_not_in_parent(self, setup_hive):
        """Test removing child that's not in parent's children is safe."""
        create_test_epic("default.bees-ep1", children=[])
        create_test_task("default.bees-tk1")

        # Should not raise error
        _remove_child_from_parent("default.bees-tk1", "default.bees-ep1")

        parent_path = get_ticket_path("default.bees-ep1", "epic")
        parent_ticket = read_ticket(parent_path)
        assert parent_ticket.children == []


class TestSetParentOnChild:
    """Tests for _set_parent_on_child helper function."""

    def test_set_parent_on_child_success(self, setup_hive):
        """Test successfully setting parent on child ticket."""
        create_test_epic("default.bees-ep1")
        create_test_task("default.bees-tk1")

        _set_parent_on_child("default.bees-ep1", "default.bees-tk1")

        child_path = get_ticket_path("default.bees-tk1", "task")
        child_ticket = read_ticket(child_path)
        assert child_ticket.parent == "default.bees-ep1"

    def test_set_parent_nonexistent_child_raises_error(self, setup_hive):
        """Test setting parent on nonexistent child raises ValueError."""
        create_test_epic("default.bees-ep1")

        with pytest.raises(ValueError, match="Child ticket not found"):
            _set_parent_on_child("default.bees-ep1", "default.bees-nonexistent")


class TestRemoveParentFromChild:
    """Tests for _remove_parent_from_child helper function."""

    def test_remove_parent_from_task_success(self, setup_hive):
        """Test successfully removing parent from task."""
        create_test_epic("default.bees-ep1")
        create_test_task("default.bees-tk1", parent="default.bees-ep1")

        _remove_parent_from_child("default.bees-tk1")

        child_path = get_ticket_path("default.bees-tk1", "task")
        child_ticket = read_ticket(child_path)
        assert child_ticket.parent is None

    def test_remove_parent_from_subtask_not_allowed(self, setup_hive):
        """Test that removing parent from subtask is not allowed."""
        create_test_task("default.bees-tk1")
        create_test_subtask("default.bees-st1", parent="default.bees-tk1")

        # Should log warning but not raise error
        _remove_parent_from_child("default.bees-st1")

        # Verify subtask still has parent
        child_path = get_ticket_path("default.bees-st1", "subtask")
        child_ticket = read_ticket(child_path)
        assert child_ticket.parent == "default.bees-tk1"


class TestDependencyHelpers:
    """Tests for dependency helper functions."""

    def test_add_to_down_dependencies(self, setup_hive):
        """Test adding ticket to blocking ticket's down_dependencies."""
        create_test_epic("default.bees-ep1")
        create_test_epic("default.bees-ep2")

        _add_to_down_dependencies("default.bees-ep2", "default.bees-ep1")

        blocking_path = get_ticket_path("default.bees-ep1", "epic")
        blocking_ticket = read_ticket(blocking_path)
        assert "default.bees-ep2" in blocking_ticket.down_dependencies

    def test_remove_from_down_dependencies(self, setup_hive):
        """Test removing ticket from blocking ticket's down_dependencies."""
        # Create epic with down_dependency
        frontmatter = {
            "id": "default.bees-ep1",
            "type": "epic",
            "title": "Test Epic",
            "children": [],
            "up_dependencies": [],
            "down_dependencies": ["default.bees-ep2"],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "status": "open",
            "bees_version": "1.1"
        }
        write_ticket_file("default.bees-ep1", "epic", frontmatter, "Description")
        create_test_epic("default.bees-ep2")

        _remove_from_down_dependencies("default.bees-ep2", "default.bees-ep1")

        blocking_path = get_ticket_path("default.bees-ep1", "epic")
        blocking_ticket = read_ticket(blocking_path)
        assert "default.bees-ep2" not in blocking_ticket.down_dependencies

    def test_add_to_up_dependencies(self, setup_hive):
        """Test adding ticket to blocked ticket's up_dependencies."""
        create_test_epic("default.bees-ep1")
        create_test_epic("default.bees-ep2")

        _add_to_up_dependencies("default.bees-ep1", "default.bees-ep2")

        blocked_path = get_ticket_path("default.bees-ep2", "epic")
        blocked_ticket = read_ticket(blocked_path)
        assert "default.bees-ep1" in blocked_ticket.up_dependencies

    def test_remove_from_up_dependencies(self, setup_hive):
        """Test removing ticket from blocked ticket's up_dependencies."""
        # Create epic with up_dependency
        frontmatter = {
            "id": "default.bees-ep2",
            "type": "epic",
            "title": "Test Epic",
            "children": [],
            "up_dependencies": ["default.bees-ep1"],
            "down_dependencies": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "status": "open",
            "bees_version": "1.1"
        }
        write_ticket_file("default.bees-ep2", "epic", frontmatter, "Description")
        create_test_epic("default.bees-ep1")

        _remove_from_up_dependencies("default.bees-ep1", "default.bees-ep2")

        blocked_path = get_ticket_path("default.bees-ep2", "epic")
        blocked_ticket = read_ticket(blocked_path)
        assert "default.bees-ep1" not in blocked_ticket.up_dependencies


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_null_parent_handled(self, setup_hive):
        """Test that null parent is handled gracefully."""
        create_test_task("default.bees-tk1")

        # Should not raise error
        _update_bidirectional_relationships(
            new_ticket_id="default.bees-tk1",
            parent=None
        )

    def test_empty_children_array(self, setup_hive):
        """Test that empty children array is handled gracefully."""
        create_test_epic("default.bees-ep1")

        # Should not raise error
        _update_bidirectional_relationships(
            new_ticket_id="default.bees-ep1",
            children=[]
        )

    def test_empty_dependencies_arrays(self, setup_hive):
        """Test that empty dependency arrays are handled gracefully."""
        create_test_epic("default.bees-ep1")

        # Should not raise error
        _update_bidirectional_relationships(
            new_ticket_id="default.bees-ep1",
            up_dependencies=[],
            down_dependencies=[]
        )
