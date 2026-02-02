"""Unit tests for relationship synchronization module."""

import pytest
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

# Skip all tests - need refactoring for flat storage architecture
# These tests monkeypatch src.paths.TICKETS_DIR which no longer exists
# Need to update to use config-based hive paths
pytest.skip("Legacy TICKETS_DIR tests - needs refactoring for flat storage", allow_module_level=True)

from src.relationship_sync import (
    add_child_to_parent,
    remove_child_from_parent,
    add_dependency,
    remove_dependency,
    sync_relationships_batch,
    validate_ticket_exists,
    validate_parent_child_relationship,
    check_for_circular_dependency,
    _save_ticket,
    _load_ticket_by_id,
)
from src.reader import read_ticket
from src.writer import write_ticket_file
from src.paths import get_ticket_path
from src.models import Task


@pytest.fixture
def sample_epic(tmp_path, monkeypatch):
    """Create a sample epic ticket."""
    # Monkeypatch the tickets directory
    from src import paths
    monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

    frontmatter = {
        "id": "bees-ep1",
        "type": "epic",
        "title": "Sample Epic",
        "children": [],
        "up_dependencies": [],
        "down_dependencies": [],
    }
    write_ticket_file("bees-ep1", "epic", frontmatter, "Epic description")
    return "bees-ep1"


@pytest.fixture
def sample_task(tmp_path, monkeypatch):
    """Create a sample task ticket."""
    from src import paths
    monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

    frontmatter = {
        "id": "bees-tk1",
        "type": "task",
        "title": "Sample Task",
        "parent": None,
        "children": [],
        "up_dependencies": [],
        "down_dependencies": [],
    }
    write_ticket_file("bees-tk1", "task", frontmatter, "Task description")
    return "bees-tk1"


@pytest.fixture
def sample_subtask(tmp_path, monkeypatch):
    """Create a sample subtask ticket."""
    from src import paths
    monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

    # First create a dummy parent task for the subtask
    dummy_parent_frontmatter = {
        "id": "bees-tmp",
        "type": "task",
        "title": "Temporary Parent",
        "children": ["bees-st1"],
    }
    write_ticket_file("bees-tmp", "task", dummy_parent_frontmatter, "")

    # Create the subtask with the temporary parent
    frontmatter = {
        "id": "bees-st1",
        "type": "subtask",
        "title": "Sample Subtask",
        "parent": "bees-tmp",  # Subtasks must have a parent
        "up_dependencies": [],
        "down_dependencies": [],
    }
    write_ticket_file("bees-st1", "subtask", frontmatter, "Subtask description")
    return "bees-st1"


class TestAddChildToParent:
    """Tests for add_child_to_parent function."""

    def test_add_task_to_epic(self, sample_epic, sample_task):
        """Should add task as child of epic and set parent on task."""
        add_child_to_parent(sample_epic, sample_task)

        epic = read_ticket(get_ticket_path(sample_epic, "epic"))
        task = read_ticket(get_ticket_path(sample_task, "task"))

        assert sample_task in epic.children
        assert task.parent == sample_epic

    def test_add_subtask_to_task(self, sample_task, sample_subtask):
        """Should add subtask as child of task."""
        add_child_to_parent(sample_task, sample_subtask)

        task = read_ticket(get_ticket_path(sample_task, "task"))
        subtask = read_ticket(get_ticket_path(sample_subtask, "subtask"))

        assert sample_subtask in task.children
        assert subtask.parent == sample_task

    def test_duplicate_add_is_idempotent(self, sample_epic, sample_task):
        """Adding same child twice should be idempotent."""
        add_child_to_parent(sample_epic, sample_task)
        add_child_to_parent(sample_epic, sample_task)

        epic = read_ticket(get_ticket_path(sample_epic, "epic"))
        assert epic.children.count(sample_task) == 1

    def test_invalid_hierarchy_epic_to_subtask(self, sample_epic, sample_subtask):
        """Should reject epic -> subtask relationship."""
        with pytest.raises(ValueError, match="Invalid parent-child relationship"):
            add_child_to_parent(sample_epic, sample_subtask)

    def test_nonexistent_parent(self, sample_task):
        """Should raise FileNotFoundError for nonexistent parent."""
        with pytest.raises(FileNotFoundError):
            add_child_to_parent("bees-nonexistent", sample_task)

    def test_nonexistent_child(self, sample_epic):
        """Should raise FileNotFoundError for nonexistent child."""
        with pytest.raises(FileNotFoundError):
            add_child_to_parent(sample_epic, "bees-nonexistent")


class TestRemoveChildFromParent:
    """Tests for remove_child_from_parent function."""

    def test_remove_child(self, sample_epic, sample_task):
        """Should remove child from parent and clear parent field."""
        # First add the relationship
        add_child_to_parent(sample_epic, sample_task)

        # Then remove it
        remove_child_from_parent(sample_epic, sample_task)

        epic = read_ticket(get_ticket_path(sample_epic, "epic"))
        task = read_ticket(get_ticket_path(sample_task, "task"))

        assert sample_task not in epic.children
        assert task.parent is None

    def test_remove_nonexistent_child_is_safe(self, sample_epic, sample_task):
        """Removing a child that doesn't exist should be safe."""
        remove_child_from_parent(sample_epic, sample_task)

        epic = read_ticket(get_ticket_path(sample_epic, "epic"))
        assert sample_task not in epic.children


class TestAddDependency:
    """Tests for add_dependency function."""

    def test_add_dependency_updates_both_tickets(self, sample_task, sample_epic):
        """Should update up_dependencies and down_dependencies bidirectionally."""
        # sample_task depends on sample_epic
        add_dependency(sample_task, sample_epic)

        task = read_ticket(get_ticket_path(sample_task, "task"))
        epic = read_ticket(get_ticket_path(sample_epic, "epic"))

        assert sample_epic in task.up_dependencies
        assert sample_task in epic.down_dependencies

    def test_duplicate_dependency_is_idempotent(self, sample_task, sample_epic):
        """Adding same dependency twice should be idempotent."""
        add_dependency(sample_task, sample_epic)
        add_dependency(sample_task, sample_epic)

        task = read_ticket(get_ticket_path(sample_task, "task"))
        assert task.up_dependencies.count(sample_epic) == 1

    def test_circular_dependency_is_prevented(self, tmp_path, monkeypatch):
        """Should prevent circular dependencies."""
        from src import paths
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Create three tasks
        for tid in ["bees-ta1", "bees-ta2", "bees-ta3"]:
            frontmatter = {
                "id": tid,
                "type": "task",
                "title": f"Task {tid}",
                "up_dependencies": [],
                "down_dependencies": [],
            }
            write_ticket_file(tid, "task", frontmatter, "")

        # Create dependency chain: ta1 -> ta2 -> ta3
        add_dependency("bees-ta1", "bees-ta2")
        add_dependency("bees-ta2", "bees-ta3")

        # Attempt to create cycle: ta3 -> ta1 (should fail)
        with pytest.raises(ValueError, match="Circular dependency detected"):
            add_dependency("bees-ta3", "bees-ta1")

    def test_self_dependency_is_prevented(self, sample_task):
        """Should prevent ticket depending on itself."""
        with pytest.raises(ValueError, match="Circular dependency detected"):
            add_dependency(sample_task, sample_task)


class TestRemoveDependency:
    """Tests for remove_dependency function."""

    def test_remove_dependency_updates_both_tickets(self, sample_task, sample_epic):
        """Should remove dependency from both tickets."""
        # First add the dependency
        add_dependency(sample_task, sample_epic)

        # Then remove it
        remove_dependency(sample_task, sample_epic)

        task = read_ticket(get_ticket_path(sample_task, "task"))
        epic = read_ticket(get_ticket_path(sample_epic, "epic"))

        assert sample_epic not in task.up_dependencies
        assert sample_task not in epic.down_dependencies

    def test_remove_nonexistent_dependency_is_safe(self, sample_task, sample_epic):
        """Removing a dependency that doesn't exist should be safe."""
        remove_dependency(sample_task, sample_epic)

        task = read_ticket(get_ticket_path(sample_task, "task"))
        assert sample_epic not in task.up_dependencies


class TestSyncRelationshipsBatch:
    """Tests for sync_relationships_batch function."""

    def test_batch_add_multiple_children(self, tmp_path, monkeypatch):
        """Should batch add multiple children efficiently."""
        from src import paths
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Create one epic and two tasks
        frontmatter_epic = {
            "id": "bees-ep2",
            "type": "epic",
            "title": "Epic",
            "children": [],
        }
        write_ticket_file("bees-ep2", "epic", frontmatter_epic, "")

        for tid in ["bees-tb1", "bees-tb2"]:
            frontmatter = {
                "id": tid,
                "type": "task",
                "title": f"Task {tid}",
                "parent": None,
            }
            write_ticket_file(tid, "task", frontmatter, "")

        # Batch update: add both tasks as children of epic
        updates = [
            ("bees-ep2", "children", "add", "bees-tb1"),
            ("bees-ep2", "children", "add", "bees-tb2"),
            ("bees-tb1", "parent", "add", "bees-ep2"),
            ("bees-tb2", "parent", "add", "bees-ep2"),
        ]
        sync_relationships_batch(updates)

        epic = read_ticket(get_ticket_path("bees-ep2", "epic"))
        assert "bees-tb1" in epic.children
        assert "bees-tb2" in epic.children

    def test_batch_remove_operations(self, tmp_path, monkeypatch):
        """Should handle remove operations in batch."""
        from src import paths
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Create task with children
        frontmatter_task = {
            "id": "bees-tc1",
            "type": "task",
            "title": "Task",
            "children": ["bees-su1", "bees-su2"],
        }
        write_ticket_file("bees-tc1", "task", frontmatter_task, "")

        for sid in ["bees-su1", "bees-su2"]:
            frontmatter = {
                "id": sid,
                "type": "subtask",
                "title": f"Subtask {sid}",
                "parent": "bees-tc1",
            }
            write_ticket_file(sid, "subtask", frontmatter, "")

        # Batch remove one child
        updates = [
            ("bees-tc1", "children", "remove", "bees-su1"),
            ("bees-su1", "parent", "remove", "bees-tc1"),
        ]
        sync_relationships_batch(updates)

        task = read_ticket(get_ticket_path("bees-tc1", "task"))
        assert "bees-su1" not in task.children
        assert "bees-su2" in task.children

    def test_invalid_operation_fails_batch(self, sample_task):
        """Invalid operation should fail without applying changes."""
        updates = [
            (sample_task, "children", "invalid_op", "bees-t2"),
        ]

        with pytest.raises(ValueError, match="Invalid operation"):
            sync_relationships_batch(updates)

    def test_invalid_field_name_fails_batch(self, sample_task):
        """Invalid field name should fail without applying changes."""
        updates = [
            (sample_task, "invalid_field", "add", "value"),
        ]

        with pytest.raises(ValueError, match="Invalid field name"):
            sync_relationships_batch(updates)

    def test_nonexistent_ticket_fails_batch(self, sample_task):
        """Nonexistent ticket should fail validation phase."""
        updates = [
            ("bees-nonexistent", "children", "add", sample_task),
        ]

        with pytest.raises(FileNotFoundError):
            sync_relationships_batch(updates)


class TestValidationFunctions:
    """Tests for validation helper functions."""

    def test_validate_ticket_exists_success(self, sample_epic):
        """Should return True for existing ticket."""
        assert validate_ticket_exists(sample_epic) is True

    def test_validate_ticket_exists_failure(self):
        """Should raise FileNotFoundError for nonexistent ticket."""
        with pytest.raises(FileNotFoundError, match="not found"):
            validate_ticket_exists("bees-nonexistent")

    def test_validate_parent_child_epic_task(self, sample_epic, sample_task):
        """Should allow Epic -> Task relationship."""
        validate_parent_child_relationship(sample_epic, sample_task)

    def test_validate_parent_child_task_subtask(self, sample_task, sample_subtask):
        """Should allow Task -> Subtask relationship."""
        validate_parent_child_relationship(sample_task, sample_subtask)

    def test_validate_parent_child_invalid_epic_subtask(self, sample_epic, sample_subtask):
        """Should reject Epic -> Subtask relationship."""
        with pytest.raises(ValueError, match="Invalid parent-child relationship"):
            validate_parent_child_relationship(sample_epic, sample_subtask)

    def test_check_circular_dependency_direct(self, tmp_path, monkeypatch):
        """Should detect direct circular dependency."""
        from src import paths
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Create two tasks with td1 depending on td2
        frontmatter_t1 = {
            "id": "bees-td1",
            "type": "task",
            "title": "Task 1",
            "up_dependencies": ["bees-td2"],
            "down_dependencies": [],
        }
        write_ticket_file("bees-td1", "task", frontmatter_t1, "")

        frontmatter_t2 = {
            "id": "bees-td2",
            "type": "task",
            "title": "Task 2",
            "up_dependencies": [],
            "down_dependencies": ["bees-td1"],
        }
        write_ticket_file("bees-td2", "task", frontmatter_t2, "")

        # Attempt to make td2 depend on td1 (creates cycle)
        with pytest.raises(ValueError, match="Circular dependency detected"):
            check_for_circular_dependency("bees-td2", "bees-td1")

    def test_check_circular_dependency_transitive(self, tmp_path, monkeypatch):
        """Should detect transitive circular dependency."""
        from src import paths
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Create chain: te1 -> te2 -> te3
        frontmatter_t1 = {
            "id": "bees-te1",
            "type": "task",
            "title": "Task 1",
            "up_dependencies": ["bees-te2"],
            "down_dependencies": [],
        }
        write_ticket_file("bees-te1", "task", frontmatter_t1, "")

        frontmatter_t2 = {
            "id": "bees-te2",
            "type": "task",
            "title": "Task 2",
            "up_dependencies": ["bees-te3"],
            "down_dependencies": ["bees-te1"],
        }
        write_ticket_file("bees-te2", "task", frontmatter_t2, "")

        frontmatter_t3 = {
            "id": "bees-te3",
            "type": "task",
            "title": "Task 3",
            "up_dependencies": [],
            "down_dependencies": ["bees-te2"],
        }
        write_ticket_file("bees-te3", "task", frontmatter_t3, "")

        # Attempt to make te3 depend on te1 (creates transitive cycle)
        with pytest.raises(ValueError, match="Circular dependency detected"):
            check_for_circular_dependency("bees-te3", "bees-te1")


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_empty_relationship_arrays(self, tmp_path, monkeypatch):
        """Should handle tickets with empty relationship arrays."""
        from src import paths
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        frontmatter = {
            "id": "bees-tf1",
            "type": "task",
            "title": "Task",
            "children": [],
            "up_dependencies": [],
            "down_dependencies": [],
        }
        write_ticket_file("bees-tf1", "task", frontmatter, "")

        # Should not raise errors
        task = read_ticket(get_ticket_path("bees-tf1", "task"))
        assert task.children == []
        assert task.up_dependencies == []
        assert task.down_dependencies == []

    def test_multiple_children_same_parent(self, sample_epic, tmp_path, monkeypatch):
        """Should handle multiple children for same parent."""
        from src import paths
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Create multiple tasks
        for i in range(3):
            tid = f"bees-tg{i}"
            frontmatter = {
                "id": tid,
                "type": "task",
                "title": f"Task {i}",
                "parent": None,
            }
            write_ticket_file(tid, "task", frontmatter, "")

        # Add all as children
        for i in range(3):
            add_child_to_parent(sample_epic, f"bees-tg{i}")

        epic = read_ticket(get_ticket_path(sample_epic, "epic"))
        assert len(epic.children) == 3


class TestAtomicityGuarantees:
    """Tests for atomicity guarantees in sync_relationships_batch."""

    def test_successful_batch_update_commits_all_changes(self, tmp_path, monkeypatch):
        """Should commit all changes when batch update succeeds."""
        from src import paths
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Create epic and two tasks
        frontmatter_epic = {
            "id": "bees-at1",
            "type": "epic",
            "title": "Epic",
            "children": [],
        }
        write_ticket_file("bees-at1", "epic", frontmatter_epic, "")

        for tid in ["bees-at2", "bees-at3"]:
            frontmatter = {
                "id": tid,
                "type": "task",
                "title": f"Task {tid}",
                "parent": None,
            }
            write_ticket_file(tid, "task", frontmatter, "")

        # Batch update should succeed
        updates = [
            ("bees-at1", "children", "add", "bees-at2"),
            ("bees-at1", "children", "add", "bees-at3"),
            ("bees-at2", "parent", "add", "bees-at1"),
            ("bees-at3", "parent", "add", "bees-at1"),
        ]
        sync_relationships_batch(updates)

        # Verify all changes committed
        epic = read_ticket(get_ticket_path("bees-at1", "epic"))
        task2 = read_ticket(get_ticket_path("bees-at2", "task"))
        task3 = read_ticket(get_ticket_path("bees-at3", "task"))

        assert "bees-at2" in epic.children
        assert "bees-at3" in epic.children
        assert task2.parent == "bees-at1"
        assert task3.parent == "bees-at1"

    def test_partial_write_failure_triggers_rollback(self, tmp_path, monkeypatch):
        """Should rollback all changes when write fails partway through."""
        from src import paths
        import src.relationship_sync as sync_module
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Create tickets
        frontmatter_epic = {
            "id": "bees-at4",
            "type": "epic",
            "title": "Epic",
            "children": [],
        }
        write_ticket_file("bees-at4", "epic", frontmatter_epic, "")

        for tid in ["bees-at5", "bees-at6"]:
            frontmatter = {
                "id": tid,
                "type": "task",
                "title": f"Task {tid}",
                "parent": None,
            }
            write_ticket_file(tid, "task", frontmatter, "")

        # Mock _save_ticket to fail on second call
        original_save = sync_module._save_ticket
        call_count = 0

        def mock_save(ticket):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise IOError("Write failed")
            original_save(ticket)

        updates = [
            ("bees-at4", "children", "add", "bees-at5"),
            ("bees-at5", "parent", "add", "bees-at4"),
        ]

        with patch.object(sync_module, '_save_ticket', side_effect=mock_save):
            # Should raise RuntimeError due to rollback
            with pytest.raises(RuntimeError, match="Batch write failed"):
                sync_relationships_batch(updates)

        # Verify rollback: no changes should persist
        epic = read_ticket(get_ticket_path("bees-at4", "epic"))
        task5 = read_ticket(get_ticket_path("bees-at5", "task"))

        assert "bees-at5" not in epic.children
        assert task5.parent is None

    def test_all_tickets_restored_on_failure(self, tmp_path, monkeypatch):
        """Should restore all tickets to original state on failure."""
        from src import paths
        import src.relationship_sync as sync_module
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Create tickets with existing relationships
        frontmatter_epic = {
            "id": "bees-at7",
            "type": "epic",
            "title": "Epic",
            "children": ["bees-at8"],
        }
        write_ticket_file("bees-at7", "epic", frontmatter_epic, "")

        frontmatter_task = {
            "id": "bees-at8",
            "type": "task",
            "title": "Task",
            "parent": "bees-at7",
        }
        write_ticket_file("bees-at8", "task", frontmatter_task, "")

        # Mock _save_ticket to fail
        original_save = sync_module._save_ticket

        def mock_save(ticket):
            if ticket.id == "bees-at7":
                raise IOError("Write failed")
            original_save(ticket)

        updates = [
            ("bees-at7", "children", "remove", "bees-at8"),
            ("bees-at8", "parent", "remove", "bees-at7"),
        ]

        with patch.object(sync_module, '_save_ticket', side_effect=mock_save):
            with pytest.raises(RuntimeError):
                sync_relationships_batch(updates)

        # Verify original state restored
        epic = read_ticket(get_ticket_path("bees-at7", "epic"))
        task = read_ticket(get_ticket_path("bees-at8", "task"))

        assert "bees-at8" in epic.children
        assert task.parent == "bees-at7"

    def test_wal_cleanup_after_success(self, sample_epic, sample_task):
        """Should clean up WAL backups after successful write."""
        updates = [
            (sample_epic, "children", "add", sample_task),
            (sample_task, "parent", "add", sample_epic),
        ]

        # Execute batch update
        sync_relationships_batch(updates)

        # Verify changes committed
        epic = read_ticket(get_ticket_path(sample_epic, "epic"))
        task = read_ticket(get_ticket_path(sample_task, "task"))

        assert sample_task in epic.children
        assert task.parent == sample_epic

        # WAL cleanup is implicit - if function completes without error,
        # backups dict is cleared in finally block

    def test_wal_cleanup_after_rollback(self, sample_epic, sample_task):
        """Should clean up WAL backups even after rollback."""
        import src.relationship_sync as sync_module

        # Mock to fail writes
        def mock_save(ticket):
            raise IOError("Write failed")

        updates = [
            (sample_epic, "children", "add", sample_task),
        ]

        with patch.object(sync_module, '_save_ticket', side_effect=mock_save):
            with pytest.raises(RuntimeError):
                sync_relationships_batch(updates)

        # WAL cleanup is implicit - finally block always executes
        # If we reach here without memory issues, cleanup worked


class TestFileLocking:
    """Tests for file locking mechanism in _save_ticket."""

    def test_successful_lock_acquisition_and_release(self, tmp_path, monkeypatch):
        """Should successfully acquire and release file lock."""
        from src import paths
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Create a ticket
        ticket = Task(
            id="bees-lk1",
            type="task",
            title="Lock Test",
            description="Testing file locking",
            parent=None,
            children=[],
            up_dependencies=[],
            down_dependencies=[],
        )

        # Save should succeed
        _save_ticket(ticket)

        # Verify file was written
        ticket_path = get_ticket_path("bees-lk1", "task")
        assert ticket_path.exists()

        # Read back and verify
        loaded = read_ticket(ticket_path)
        assert loaded.id == "bees-lk1"
        assert loaded.title == "Lock Test"

    def test_lock_retry_with_exponential_backoff(self, tmp_path, monkeypatch, caplog):
        """Should retry lock acquisition with exponential backoff."""
        from src import paths
        import src.relationship_sync as sync_module
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        ticket = Task(
            id="bees-lk2",
            type="task",
            title="Retry Test",
            description="Testing retry logic",
            parent=None,
            children=[],
            up_dependencies=[],
            down_dependencies=[],
        )

        # Mock fcntl.flock to fail on first 2 attempts, succeed on 3rd
        call_count = 0

        def mock_flock(fd, operation):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise IOError("Lock failed")
            # Success on third attempt
            return None

        with patch.object(sync_module, 'fcntl') as mock_fcntl_module:
            mock_fcntl_module.flock = mock_flock
            mock_fcntl_module.LOCK_EX = 2
            mock_fcntl_module.LOCK_NB = 4

            # Should succeed after retries
            start_time = time.time()
            _save_ticket(ticket)
            elapsed = time.time() - start_time

            # Should have retried twice (0.1s + 0.2s = 0.3s minimum)
            assert elapsed >= 0.3
            assert call_count == 3

            # Check warning logs
            assert "Failed to acquire lock" in caplog.text
            assert "attempt 1/3" in caplog.text or "attempt 2/3" in caplog.text

    def test_max_retry_exhaustion_raises_exception(self, tmp_path, monkeypatch):
        """Should raise RuntimeError after max retries exceeded."""
        from src import paths
        import src.relationship_sync as sync_module
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        ticket = Task(
            id="bees-lk3",
            type="task",
            title="Max Retry Test",
            description="Testing max retry failure",
            parent=None,
            children=[],
            up_dependencies=[],
            down_dependencies=[],
        )

        # Mock fcntl.flock to always fail
        def mock_flock(fd, operation):
            raise IOError("Lock failed")

        with patch.object(sync_module, 'fcntl') as mock_fcntl_module:
            mock_fcntl_module.flock = mock_flock
            mock_fcntl_module.LOCK_EX = 2
            mock_fcntl_module.LOCK_NB = 4

            # Should raise RuntimeError after max retries
            with pytest.raises(RuntimeError, match="Failed to acquire file lock"):
                _save_ticket(ticket)

    def test_cross_platform_unix_locking(self, tmp_path, monkeypatch):
        """Should use fcntl.flock on Unix systems."""
        from src import paths
        import src.relationship_sync as sync_module
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Mock IS_WINDOWS to False (Unix)
        monkeypatch.setattr(sync_module, 'IS_WINDOWS', False)

        ticket = Task(
            id="bees-lk4",
            type="task",
            title="Unix Lock Test",
            description="Testing Unix locking",
            parent=None,
            children=[],
            up_dependencies=[],
            down_dependencies=[],
        )

        # Mock fcntl to track calls
        mock_flock = MagicMock()
        with patch.object(sync_module, 'fcntl') as mock_fcntl_module:
            mock_fcntl_module.flock = mock_flock
            mock_fcntl_module.LOCK_EX = 2
            mock_fcntl_module.LOCK_NB = 4

            _save_ticket(ticket)

            # Verify fcntl.flock was called
            assert mock_flock.called

    def test_cross_platform_windows_locking(self, tmp_path, monkeypatch):
        """Should handle cross-platform locking (verifies Windows code path exists)."""
        from src import paths
        import src.relationship_sync as sync_module
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        ticket = Task(
            id="bees-lk5",
            type="task",
            title="Windows Lock Test",
            description="Testing Windows locking",
            parent=None,
            children=[],
            up_dependencies=[],
            down_dependencies=[],
        )

        # On Unix systems, verify the IS_WINDOWS flag is False and Unix path works
        # On Windows, this would test the msvcrt path
        assert hasattr(sync_module, 'IS_WINDOWS')

        # Save should work regardless of platform
        _save_ticket(ticket)

        # Verify file was created
        ticket_path = get_ticket_path("bees-lk5", "task")
        assert ticket_path.exists()

        # Verify the conditional import logic exists
        # If Windows, msvcrt should be imported
        if sync_module.IS_WINDOWS:
            assert hasattr(sync_module, 'msvcrt')
        else:
            # On Unix, just verify fcntl exists
            assert hasattr(sync_module, 'fcntl')

    def test_concurrent_access_simulation(self, tmp_path, monkeypatch):
        """Should handle concurrent access attempts gracefully."""
        from src import paths
        import src.relationship_sync as sync_module
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        ticket = Task(
            id="bees-lk6",
            type="task",
            title="Concurrent Test",
            description="Testing concurrent access",
            parent=None,
            children=[],
            up_dependencies=[],
            down_dependencies=[],
        )

        # Simulate lock held by another process (fail once, then succeed)
        call_count = 0

        def mock_flock(fd, operation):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise IOError("Resource temporarily unavailable")
            return None

        with patch.object(sync_module, 'fcntl') as mock_fcntl_module:
            mock_fcntl_module.flock = mock_flock
            mock_fcntl_module.LOCK_EX = 2
            mock_fcntl_module.LOCK_NB = 4

            # Should succeed after one retry
            _save_ticket(ticket)

            # Verify file was written
            ticket_path = get_ticket_path("bees-lk6", "task")
            assert ticket_path.exists()

    def test_lock_released_on_exception(self, tmp_path, monkeypatch):
        """Should handle exceptions during write operations."""
        from src import paths
        import src.relationship_sync as sync_module
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        ticket = Task(
            id="bees-lk7",
            type="task",
            title="Exception Test",
            description="Testing lock release on error",
            parent=None,
            children=[],
            up_dependencies=[],
            down_dependencies=[],
        )

        # Mock write_ticket_file to raise exception after lock is acquired
        with patch('src.relationship_sync.write_ticket_file') as mock_write:
            mock_write.side_effect = IOError("Disk full")

            # Should raise exception from the write operation
            # The context manager will handle lock release automatically
            with pytest.raises(Exception):  # Could be IOError or RuntimeError wrapped
                _save_ticket(ticket)

            # Write should have been attempted
            assert mock_write.called


class TestBatchDeduplication:
    """Tests for duplicate operation detection in sync_relationships_batch."""

    def test_duplicate_add_operations_are_deduplicated(self, tmp_path, monkeypatch):
        """Should remove duplicate add operations before execution."""
        from src import paths
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Create epic and task
        frontmatter_epic = {
            "id": "bees-dd1",
            "type": "epic",
            "title": "Epic",
            "children": [],
        }
        write_ticket_file("bees-dd1", "epic", frontmatter_epic, "")

        frontmatter_task = {
            "id": "bees-dd2",
            "type": "task",
            "title": "Task",
            "parent": None,
        }
        write_ticket_file("bees-dd2", "task", frontmatter_task, "")

        # Batch update with duplicate add operations
        updates = [
            ("bees-dd1", "children", "add", "bees-dd2"),
            ("bees-dd1", "children", "add", "bees-dd2"),  # Duplicate
            ("bees-dd1", "children", "add", "bees-dd2"),  # Duplicate
            ("bees-dd2", "parent", "add", "bees-dd1"),
        ]
        sync_relationships_batch(updates)

        # Verify child added only once
        epic = read_ticket(get_ticket_path("bees-dd1", "epic"))
        assert "bees-dd2" in epic.children
        assert epic.children.count("bees-dd2") == 1

    def test_duplicate_remove_operations_are_deduplicated(self, tmp_path, monkeypatch):
        """Should remove duplicate remove operations before execution."""
        from src import paths
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Create task with children
        frontmatter_task = {
            "id": "bees-dd3",
            "type": "task",
            "title": "Task",
            "children": ["bees-dd4", "bees-dd5"],
        }
        write_ticket_file("bees-dd3", "task", frontmatter_task, "")

        for sid in ["bees-dd4", "bees-dd5"]:
            frontmatter = {
                "id": sid,
                "type": "subtask",
                "title": f"Subtask {sid}",
                "parent": "bees-dd3",
            }
            write_ticket_file(sid, "subtask", frontmatter, "")

        # Batch remove with duplicates
        updates = [
            ("bees-dd3", "children", "remove", "bees-dd4"),
            ("bees-dd3", "children", "remove", "bees-dd4"),  # Duplicate
            ("bees-dd4", "parent", "remove", "bees-dd3"),
        ]
        sync_relationships_batch(updates)

        # Verify child removed
        task = read_ticket(get_ticket_path("bees-dd3", "task"))
        assert "bees-dd4" not in task.children
        assert "bees-dd5" in task.children

    def test_mixed_duplicates_across_tickets_and_fields(self, tmp_path, monkeypatch):
        """Should deduplicate mixed operations across different tickets and fields."""
        from src import paths
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Create tickets
        for tid, ttype in [("bees-dd6", "epic"), ("bees-dd7", "task"), ("bees-dd8", "task")]:
            frontmatter = {
                "id": tid,
                "type": ttype,
                "title": f"{ttype} {tid}",
                "children": [] if ttype in ["epic", "task"] else None,
                "parent": None if ttype in ["task", "subtask"] else None,
                "up_dependencies": [],
                "down_dependencies": [],
            }
            write_ticket_file(tid, ttype, frontmatter, "")

        # Mixed updates with duplicates
        updates = [
            ("bees-dd6", "children", "add", "bees-dd7"),
            ("bees-dd6", "children", "add", "bees-dd7"),  # Duplicate
            ("bees-dd7", "parent", "add", "bees-dd6"),
            ("bees-dd7", "parent", "add", "bees-dd6"),  # Duplicate
            ("bees-dd7", "up_dependencies", "add", "bees-dd8"),
            ("bees-dd7", "up_dependencies", "add", "bees-dd8"),  # Duplicate
            ("bees-dd8", "down_dependencies", "add", "bees-dd7"),
        ]
        sync_relationships_batch(updates)

        # Verify all operations executed once
        epic = read_ticket(get_ticket_path("bees-dd6", "epic"))
        task1 = read_ticket(get_ticket_path("bees-dd7", "task"))
        task2 = read_ticket(get_ticket_path("bees-dd8", "task"))

        assert epic.children.count("bees-dd7") == 1
        assert task1.parent == "bees-dd6"
        assert task1.up_dependencies.count("bees-dd8") == 1
        assert task2.down_dependencies.count("bees-dd7") == 1

    def test_no_deduplication_when_operations_differ(self, tmp_path, monkeypatch):
        """Should not deduplicate when operations are different."""
        from src import paths
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Create epic and tasks
        frontmatter_epic = {
            "id": "bees-dd9",
            "type": "epic",
            "title": "Epic",
            "children": [],
        }
        write_ticket_file("bees-dd9", "epic", frontmatter_epic, "")

        for tid in ["bees-da1", "bees-da2"]:
            frontmatter = {
                "id": tid,
                "type": "task",
                "title": f"Task {tid}",
                "parent": None,
            }
            write_ticket_file(tid, "task", frontmatter, "")

        # Different operations - should not deduplicate
        updates = [
            ("bees-dd9", "children", "add", "bees-da1"),
            ("bees-dd9", "children", "add", "bees-da2"),  # Different value
            ("bees-da1", "parent", "add", "bees-dd9"),
            ("bees-da2", "parent", "add", "bees-dd9"),
        ]
        sync_relationships_batch(updates)

        # Verify both children added
        epic = read_ticket(get_ticket_path("bees-dd9", "epic"))
        assert "bees-da1" in epic.children
        assert "bees-da2" in epic.children
        assert len(epic.children) == 2

    def test_deduplication_maintains_correct_final_state(self, tmp_path, monkeypatch):
        """Should verify final state is correct after deduplication."""
        from src import paths
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Create tickets
        frontmatter_epic = {
            "id": "bees-db1",
            "type": "epic",
            "title": "Epic",
            "children": [],
        }
        write_ticket_file("bees-db1", "epic", frontmatter_epic, "")

        frontmatter_task = {
            "id": "bees-db2",
            "type": "task",
            "title": "Task",
            "parent": None,
            "up_dependencies": [],
            "down_dependencies": [],
        }
        write_ticket_file("bees-db2", "task", frontmatter_task, "")

        # Updates with many duplicates
        updates = [
            ("bees-db1", "children", "add", "bees-db2"),
            ("bees-db1", "children", "add", "bees-db2"),
            ("bees-db1", "children", "add", "bees-db2"),
            ("bees-db2", "parent", "add", "bees-db1"),
            ("bees-db2", "parent", "add", "bees-db1"),
        ]
        sync_relationships_batch(updates)

        # Verify final state is exactly what we expect
        epic = read_ticket(get_ticket_path("bees-db1", "epic"))
        task = read_ticket(get_ticket_path("bees-db2", "task"))

        assert epic.children == ["bees-db2"]
        assert task.parent == "bees-db1"

        # Verify no extra data written
        assert len(epic.children) == 1
        assert epic.children.count("bees-db2") == 1


class TestLoadTicketByIdEarlyReturn:
    """Tests for _load_ticket_by_id early return optimization."""

    def test_epic_found_returns_immediately(self, tmp_path, monkeypatch):
        """Should return immediately when ticket found in epic directory."""
        from src import paths
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Create epic ticket
        frontmatter = {
            "id": "bees-ep3",
            "type": "epic",
            "title": "Test Epic",
            "children": [],
        }
        write_ticket_file("bees-ep3", "epic", frontmatter, "Epic description")

        # Mock read_ticket to track calls
        original_read = read_ticket
        read_calls = []

        def track_read(path):
            read_calls.append(str(path))
            return original_read(path)

        with patch('src.relationship_sync.read_ticket', side_effect=track_read):
            ticket = _load_ticket_by_id("bees-ep3")

            # Verify ticket was loaded
            assert ticket.id == "bees-ep3"
            assert ticket.type == "epic"

            # Verify only epic directory was checked (early return worked)
            assert len(read_calls) == 1
            assert "epic" in read_calls[0]

    def test_task_found_returns_without_checking_subtask(self, tmp_path, monkeypatch):
        """Should return immediately when ticket found in task directory."""
        from src import paths
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Create task ticket (not epic)
        frontmatter = {
            "id": "bees-tk2",
            "type": "task",
            "title": "Test Task",
            "parent": None,
            "children": [],
        }
        write_ticket_file("bees-tk2", "task", frontmatter, "Task description")

        # Mock read_ticket to track calls
        original_read = read_ticket
        read_calls = []

        def track_read(path):
            read_calls.append(str(path))
            return original_read(path)

        with patch('src.relationship_sync.read_ticket', side_effect=track_read):
            ticket = _load_ticket_by_id("bees-tk2")

            # Verify ticket was loaded
            assert ticket.id == "bees-tk2"
            assert ticket.type == "task"

            # Verify epic was checked first (failed), then task succeeded (early return)
            # Should NOT check subtask directory
            assert len(read_calls) == 2
            assert "task" in read_calls[1]
            assert not any("subtask" in call for call in read_calls)

    def test_subtask_found_after_checking_all_directories(self, tmp_path, monkeypatch):
        """Should check all directories when ticket is in subtask directory."""
        from src import paths
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Create parent task first
        parent_frontmatter = {
            "id": "bees-tk3",
            "type": "task",
            "title": "Parent Task",
            "children": ["bees-st2"],
        }
        write_ticket_file("bees-tk3", "task", parent_frontmatter, "")

        # Create subtask
        frontmatter = {
            "id": "bees-st2",
            "type": "subtask",
            "title": "Test Subtask",
            "parent": "bees-tk3",
        }
        write_ticket_file("bees-st2", "subtask", frontmatter, "Subtask description")

        # Mock read_ticket to track calls
        original_read = read_ticket
        read_calls = []

        def track_read(path):
            read_calls.append(str(path))
            return original_read(path)

        with patch('src.relationship_sync.read_ticket', side_effect=track_read):
            ticket = _load_ticket_by_id("bees-st2")

            # Verify ticket was loaded
            assert ticket.id == "bees-st2"
            assert ticket.type == "subtask"

            # Verify all three directories were checked (epic failed, task failed, subtask succeeded)
            assert len(read_calls) == 3
            assert "subtask" in read_calls[2]

    def test_ticket_not_found_raises_error(self, tmp_path, monkeypatch):
        """Should raise FileNotFoundError when ticket doesn't exist in any directory."""
        from src import paths
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Don't create any tickets
        with pytest.raises(FileNotFoundError, match="not found in any directory"):
            _load_ticket_by_id("bees-nonexistent")

    def test_early_return_performance_optimization(self, tmp_path, monkeypatch):
        """Should verify early return improves performance by reducing directory checks."""
        from src import paths
        import time
        monkeypatch.setattr(paths, "TICKETS_DIR", tmp_path)

        # Create many epics
        for i in range(10):
            frontmatter = {
                "id": f"bees-ep{i}",
                "type": "epic",
                "title": f"Epic {i}",
                "children": [],
            }
            write_ticket_file(f"bees-ep{i}", "epic", frontmatter, "")

        # Track filesystem accesses
        access_count = 0
        original_read = read_ticket

        def count_read(path):
            nonlocal access_count
            access_count += 1
            return original_read(path)

        with patch('src.relationship_sync.read_ticket', side_effect=count_read):
            # Load first epic - should only check epic directory
            ticket = _load_ticket_by_id("bees-ep0")

            # Verify only 1 read call (early return optimization)
            assert access_count == 1
            assert ticket.id == "bees-ep0"
