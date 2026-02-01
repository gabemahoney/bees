"""Unit tests for ticket factory functions with hive_name support."""

import pytest
from pathlib import Path
import tempfile
import shutil

from src.ticket_factory import create_epic, create_task, create_subtask
from src.reader import read_ticket
from src.paths import get_ticket_path
from src.id_utils import is_valid_ticket_id


@pytest.fixture
def temp_tickets_dir():
    """Create temporary tickets directory."""
    temp_dir = Path(tempfile.mkdtemp())
    tickets_dir = temp_dir / "tickets"
    tickets_dir.mkdir()
    (tickets_dir / "epics").mkdir()
    (tickets_dir / "tasks").mkdir()
    (tickets_dir / "subtasks").mkdir()

    # Temporarily override TICKETS_DIR
    import src.paths
    original_tickets_dir = src.paths.TICKETS_DIR
    src.paths.TICKETS_DIR = tickets_dir

    yield tickets_dir

    # Restore original and cleanup
    src.paths.TICKETS_DIR = original_tickets_dir
    shutil.rmtree(temp_dir)


class TestCreateEpicWithHive:
    """Tests for create_epic() with hive_name parameter."""

    def test_create_epic_without_hive(self, temp_tickets_dir):
        """Should create epic with standard ID."""
        epic_id = create_epic(
            title="Test Epic",
            description="Test description"
        )

        assert epic_id.startswith("bees-")
        assert is_valid_ticket_id(epic_id)

        # Verify file was created
        epic_path = get_ticket_path(epic_id, "epic")
        assert epic_path.exists()

        # Verify content
        epic = read_ticket(epic_path)
        assert epic.id == epic_id
        assert epic.title == "Test Epic"

    def test_create_epic_with_hive(self, temp_tickets_dir):
        """Should create epic with hive-prefixed ID."""
        epic_id = create_epic(
            title="Backend Epic",
            description="Backend work",
            hive_name="backend"
        )

        assert epic_id.startswith("backend.bees-")
        assert is_valid_ticket_id(epic_id)

        # Verify file was created
        epic_path = get_ticket_path(epic_id, "epic")
        assert epic_path.exists()

        # Verify content
        epic = read_ticket(epic_path)
        assert epic.id == epic_id
        assert epic.title == "Backend Epic"

    def test_create_epic_normalizes_hive_name(self, temp_tickets_dir):
        """Should normalize hive name in generated ID."""
        epic_id = create_epic(
            title="Test Epic",
            hive_name="My Hive"
        )

        assert epic_id.startswith("my_hive.bees-")
        assert is_valid_ticket_id(epic_id)


class TestCreateTaskWithHive:
    """Tests for create_task() with hive_name parameter."""

    def test_create_task_without_hive(self, temp_tickets_dir):
        """Should create task with standard ID."""
        task_id = create_task(
            title="Test Task",
            description="Test description"
        )

        assert task_id.startswith("bees-")
        assert is_valid_ticket_id(task_id)

        # Verify file was created
        task_path = get_ticket_path(task_id, "task")
        assert task_path.exists()

    def test_create_task_with_hive(self, temp_tickets_dir):
        """Should create task with hive-prefixed ID."""
        task_id = create_task(
            title="Backend Task",
            description="Backend work",
            hive_name="backend"
        )

        assert task_id.startswith("backend.bees-")
        assert is_valid_ticket_id(task_id)

        # Verify file was created
        task_path = get_ticket_path(task_id, "task")
        assert task_path.exists()

        # Verify content
        task = read_ticket(task_path)
        assert task.id == task_id
        assert task.title == "Backend Task"

    def test_create_task_with_parent_different_hive(self, temp_tickets_dir):
        """Should allow task with different hive than parent."""
        # Create parent epic without hive
        parent_id = create_epic(title="Parent Epic")

        # Create child task with hive
        task_id = create_task(
            title="Child Task",
            parent=parent_id,
            hive_name="backend"
        )

        assert task_id.startswith("backend.bees-")
        assert is_valid_ticket_id(task_id)

        # Verify parent relationship
        task = read_ticket(get_ticket_path(task_id, "task"))
        assert task.parent == parent_id


class TestCreateSubtaskWithHive:
    """Tests for create_subtask() with hive_name parameter."""

    def test_create_subtask_without_hive(self, temp_tickets_dir):
        """Should create subtask with standard ID."""
        # Create parent task first
        parent_id = create_task(title="Parent Task")

        subtask_id = create_subtask(
            title="Test Subtask",
            parent=parent_id,
            description="Test description"
        )

        assert subtask_id.startswith("bees-")
        assert is_valid_ticket_id(subtask_id)

        # Verify file was created
        subtask_path = get_ticket_path(subtask_id, "subtask")
        assert subtask_path.exists()

    def test_create_subtask_with_hive(self, temp_tickets_dir):
        """Should create subtask with hive-prefixed ID."""
        # Create parent task first
        parent_id = create_task(title="Parent Task")

        subtask_id = create_subtask(
            title="Backend Subtask",
            parent=parent_id,
            description="Backend work",
            hive_name="backend"
        )

        assert subtask_id.startswith("backend.bees-")
        assert is_valid_ticket_id(subtask_id)

        # Verify file was created
        subtask_path = get_ticket_path(subtask_id, "subtask")
        assert subtask_path.exists()

        # Verify content
        subtask = read_ticket(subtask_path)
        assert subtask.id == subtask_id
        assert subtask.title == "Backend Subtask"
        assert subtask.parent == parent_id

    def test_create_subtask_normalizes_hive_name(self, temp_tickets_dir):
        """Should normalize hive name in generated ID."""
        parent_id = create_task(title="Parent Task")

        subtask_id = create_subtask(
            title="Test Subtask",
            parent=parent_id,
            hive_name="Front-End"
        )

        assert subtask_id.startswith("front_end.bees-")
        assert is_valid_ticket_id(subtask_id)


class TestFactoryHiveNamespacing:
    """Tests for hive namespacing in ticket factories."""

    def test_different_hives_can_have_overlapping_ids(self, temp_tickets_dir):
        """Different hives namespace their IDs independently."""
        # Create tickets in different hives
        backend_id = create_epic(title="Backend Epic", hive_name="backend")
        frontend_id = create_epic(title="Frontend Epic", hive_name="frontend")
        no_hive_id = create_epic(title="No Hive Epic")

        # All should be valid and different
        assert is_valid_ticket_id(backend_id)
        assert is_valid_ticket_id(frontend_id)
        assert is_valid_ticket_id(no_hive_id)
        assert backend_id != frontend_id != no_hive_id

    def test_all_ticket_types_support_hive(self, temp_tickets_dir):
        """Epic, Task, and Subtask all support hive_name parameter."""
        # Create one of each type with same hive
        epic_id = create_epic(title="Epic", hive_name="test_hive")
        task_id = create_task(title="Task", hive_name="test_hive")
        subtask_id = create_subtask(
            title="Subtask",
            parent=task_id,
            hive_name="test_hive"
        )

        # All should have same hive prefix
        assert epic_id.startswith("test_hive.bees-")
        assert task_id.startswith("test_hive.bees-")
        assert subtask_id.startswith("test_hive.bees-")
