"""Unit tests for ticket factory functions with hive_name support."""

import pytest
import json
from pathlib import Path

from src.ticket_factory import create_epic, create_task, create_subtask
from src.reader import read_ticket
from src.paths import get_ticket_path
from src.id_utils import is_valid_ticket_id


@pytest.fixture
def temp_hive_config(tmp_path, monkeypatch):
    """Create temporary hive configuration and override config file location."""
    import src.config

    # Create temporary hive directories
    backend_hive = tmp_path / "backend"
    frontend_hive = tmp_path / "frontend"
    default_hive = tmp_path / "default"
    test_hive = tmp_path / "test_hive"
    my_hive = tmp_path / "my_hive"
    front_end = tmp_path / "front_end"

    for hive_dir in [backend_hive, frontend_hive, default_hive, test_hive, my_hive, front_end]:
        hive_dir.mkdir()
        (hive_dir / "eggs").mkdir()
        (hive_dir / "evicted").mkdir()

    # Create temporary config file
    config_dir = tmp_path / ".bees"
    config_dir.mkdir()
    config_file = config_dir / "config.json"

    config_data = {
        "hives": {
            "backend": {"path": str(backend_hive), "display_name": "Backend"},
            "frontend": {"path": str(frontend_hive), "display_name": "Frontend"},
            "default": {"path": str(default_hive), "display_name": "Default"},
            "test_hive": {"path": str(test_hive), "display_name": "Test Hive"},
            "my_hive": {"path": str(my_hive), "display_name": "My Hive"},
            "front_end": {"path": str(front_end), "display_name": "Front End"},
        },
        "allow_cross_hive_dependencies": False,
        "schema_version": "1.0"
    }

    with open(config_file, 'w') as f:
        json.dump(config_data, f)

    # Mock get_config_path to return our temporary config file
    monkeypatch.setattr(src.config, 'get_config_path', lambda: config_file)

    # Clear the hive config cache
    if hasattr(src.config, '_hive_config_cache'):
        src.config._hive_config_cache = None

    yield tmp_path


class TestCreateEpicWithHive:
    """Tests for create_epic() with hive_name parameter."""

    def test_create_epic_requires_hive_name(self, temp_hive_config):
        """Should raise TypeError when hive_name is not provided."""
        with pytest.raises(TypeError, match="missing 1 required positional argument: 'hive_name'"):
            create_epic(
                title="Test Epic",
                description="Test description"
            )

    def test_create_epic_with_hive(self, temp_hive_config):
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

    def test_create_epic_normalizes_hive_name(self, temp_hive_config):
        """Should normalize hive name in generated ID."""
        epic_id = create_epic(
            title="Test Epic",
            hive_name="My Hive"
        )

        assert epic_id.startswith("my_hive.bees-")
        assert is_valid_ticket_id(epic_id)


class TestCreateTaskWithHive:
    """Tests for create_task() with hive_name parameter."""

    def test_create_task_requires_hive_name(self, temp_hive_config):
        """Should raise TypeError when hive_name is not provided."""
        with pytest.raises(TypeError, match="missing 1 required positional argument: 'hive_name'"):
            create_task(
                title="Test Task",
                description="Test description"
            )

    def test_create_task_with_hive(self, temp_hive_config):
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

    def test_create_task_with_parent_different_hive(self, temp_hive_config):
        """Should allow task with different hive than parent."""
        # Create parent epic with hive
        parent_id = create_epic(title="Parent Epic", hive_name="frontend")

        # Create child task with different hive
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

    def test_create_subtask_requires_hive_name(self, temp_hive_config):
        """Should raise TypeError when hive_name is not provided."""
        # Create parent task first
        parent_id = create_task(title="Parent Task", hive_name="backend")

        with pytest.raises(TypeError, match="missing 1 required positional argument: 'hive_name'"):
            create_subtask(
                title="Test Subtask",
                parent=parent_id,
                description="Test description"
            )

    def test_create_subtask_with_hive(self, temp_hive_config):
        """Should create subtask with hive-prefixed ID."""
        # Create parent task first
        parent_id = create_task(title="Parent Task", hive_name="backend")

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

    def test_create_subtask_normalizes_hive_name(self, temp_hive_config):
        """Should normalize hive name in generated ID."""
        parent_id = create_task(title="Parent Task", hive_name="backend")

        subtask_id = create_subtask(
            title="Test Subtask",
            parent=parent_id,
            hive_name="Front-End"
        )

        assert subtask_id.startswith("front_end.bees-")
        assert is_valid_ticket_id(subtask_id)


class TestFactoryHiveNamespacing:
    """Tests for hive namespacing in ticket factories."""

    def test_different_hives_can_have_overlapping_ids(self, temp_hive_config):
        """Different hives namespace their IDs independently."""
        # Create tickets in different hives
        backend_id = create_epic(title="Backend Epic", hive_name="backend")
        frontend_id = create_epic(title="Frontend Epic", hive_name="frontend")
        default_id = create_epic(title="Default Hive Epic", hive_name="default")

        # All should be valid and different
        assert is_valid_ticket_id(backend_id)
        assert is_valid_ticket_id(frontend_id)
        assert is_valid_ticket_id(default_id)
        assert backend_id != frontend_id != default_id

    def test_all_ticket_types_support_hive(self, temp_hive_config):
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
