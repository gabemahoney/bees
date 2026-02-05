"""Unit tests for ticket writer and factory functions with hive support."""

import pytest
from pathlib import Path
from datetime import datetime

from src.writer import write_ticket_file
from src.ticket_factory import create_epic, create_task, create_subtask
from src.id_utils import is_valid_ticket_id
from src.config import save_bees_config, BeesConfig, HiveConfig


@pytest.fixture
def test_hive(tmp_path, monkeypatch):
    """Create temporary hive with config for testing."""
    # Create test hive directory
    test_hive_dir = tmp_path / "test_hive"
    test_hive_dir.mkdir()
    
    # Change to temp directory so config saves there
    monkeypatch.chdir(tmp_path)
    
    # Initialize .bees/config.json with test hive
    config = BeesConfig(
        hives={
            'test': HiveConfig(
                path=str(test_hive_dir),
                display_name='Test Hive',
                created_at=datetime.now().isoformat()
            )
        }
    )
    save_bees_config(config)
    
    return test_hive_dir


class TestWriteTicketFile:
    """Tests for write_ticket_file with hive-based flat storage."""

    def test_write_epic_file(self, test_hive):
        """Should create epic file in hive root directory."""
        data = {
            "id": "test.bees-250",
            "type": "epic",
            "title": "Test Epic",
            "description": "Test description",
        }

        file_path = write_ticket_file(
            ticket_id="test.bees-250",
            ticket_type="epic",
            frontmatter_data=data,
            body="This is the body",
        )

        assert file_path.exists()
        assert file_path.parent == test_hive
        assert file_path.name == "test.bees-250.md"

        content = file_path.read_text()
        assert content.startswith("---\n")
        assert "id: test.bees-250" in content
        assert "This is the body" in content

    def test_write_task_file(self, test_hive):
        """Should create task file in hive root directory."""
        data = {
            "id": "test.bees-abc",
            "type": "task",
            "title": "Test Task",
            "parent": "test.bees-250",
        }

        file_path = write_ticket_file(
            ticket_id="test.bees-abc",
            ticket_type="task",
            frontmatter_data=data,
        )

        assert file_path.exists()
        assert file_path.parent == test_hive
        assert file_path.name == "test.bees-abc.md"

    def test_write_subtask_file(self, test_hive):
        """Should create subtask file in hive root directory."""
        data = {
            "id": "test.bees-xyz",
            "type": "subtask",
            "title": "Test Subtask",
            "parent": "test.bees-abc",
        }

        file_path = write_ticket_file(
            ticket_id="test.bees-xyz",
            ticket_type="subtask",
            frontmatter_data=data,
        )

        assert file_path.exists()
        assert file_path.parent == test_hive
        assert file_path.name == "test.bees-xyz.md"

    def test_write_creates_parent_directories(self, tmp_path, monkeypatch):
        """Should create hive directory if it doesn't exist."""
        # Create new hive directory path (but don't create it yet)
        new_hive_dir = tmp_path / "new_hive"
        
        # Change to temp directory
        monkeypatch.chdir(tmp_path)
        
        # Register hive in config
        config = BeesConfig(
            hives={
                'newhive': HiveConfig(
                    path=str(new_hive_dir),
                    display_name='New Hive',
                    created_at=datetime.now().isoformat()
                )
            }
        )
        save_bees_config(config)

        data = {
            "id": "newhive.bees-250",
            "type": "epic",
            "title": "Test",
        }

        file_path = write_ticket_file(
            ticket_id="newhive.bees-250",
            ticket_type="epic",
            frontmatter_data=data,
        )

        assert file_path.exists()
        assert file_path.parent.exists()
        assert file_path.parent == new_hive_dir

    def test_write_with_empty_body(self, test_hive):
        """Should handle empty body."""
        data = {
            "id": "test.bees-250",
            "type": "epic",
            "title": "Test",
        }

        file_path = write_ticket_file(
            ticket_id="test.bees-250",
            ticket_type="epic",
            frontmatter_data=data,
            body="",
        )

        content = file_path.read_text()
        assert content.startswith("---\n")
        assert content.endswith("---\n")

    def test_write_adds_bees_version(self, test_hive):
        """Should automatically add bees_version field."""
        data = {
            "id": "test.bees-250",
            "type": "epic",
            "title": "Test",
        }

        file_path = write_ticket_file(
            ticket_id="test.bees-250",
            ticket_type="epic",
            frontmatter_data=data,
        )

        content = file_path.read_text()
        assert "bees_version:" in content

    def test_write_rejects_invalid_ticket_id_format(self, test_hive):
        """Should raise ValueError for invalid ticket_id format."""
        data = {
            "id": "bees-INVALID",
            "type": "epic",
            "title": "Test",
        }

        with pytest.raises(ValueError, match="Invalid ticket ID format"):
            write_ticket_file(
                ticket_id="bees-INVALID",
                ticket_type="epic",
                frontmatter_data=data,
            )

    def test_write_rejects_path_traversal_attempts(self, test_hive):
        """Should reject path traversal attacks."""
        data = {
            "id": "../etc/passwd",
            "type": "epic",
            "title": "Test",
        }

        with pytest.raises(ValueError, match="Invalid ticket ID format"):
            write_ticket_file(
                ticket_id="../etc/passwd",
                ticket_type="epic",
                frontmatter_data=data,
            )

    def test_write_rejects_empty_ticket_id(self, test_hive):
        """Should reject empty ticket_id."""
        data = {
            "id": "",
            "type": "epic",
            "title": "Test",
        }

        with pytest.raises(ValueError, match="Invalid ticket ID format"):
            write_ticket_file(
                ticket_id="",
                ticket_type="epic",
                frontmatter_data=data,
            )

    def test_write_accepts_valid_hive_prefixed_id(self, test_hive):
        """Should accept valid hive-prefixed ticket IDs."""
        data = {
            "id": "test.bees-abc",
            "type": "epic",
            "title": "Test",
        }

        file_path = write_ticket_file(
            ticket_id="test.bees-abc",
            ticket_type="epic",
            frontmatter_data=data,
        )

        assert file_path.exists()
        content = file_path.read_text()
        assert "id: test.bees-abc" in content


class TestCreateEpic:
    """Tests for create_epic factory function."""

    def test_create_epic_basic(self, test_hive):
        """Should create epic with required fields."""
        epic_id = create_epic(
            title="Test Epic",
            description="Test description",
            hive_name="test",
        )

        assert is_valid_ticket_id(epic_id)
        assert epic_id.startswith("test.bees-")

        # Verify file was created
        file_path = test_hive / f"{epic_id}.md"
        assert file_path.exists()

        # Verify content
        content = file_path.read_text()
        assert "type: epic" in content
        assert "title: Test Epic" in content

    def test_create_epic_with_labels(self, test_hive):
        """Should create epic with labels."""
        epic_id = create_epic(
            title="Test Epic",
            labels=["open", "p0"],
            hive_name="test",
        )

        file_path = test_hive / f"{epic_id}.md"
        content = file_path.read_text()

        assert "labels:" in content
        assert "- open" in content
        assert "- p0" in content

    def test_create_epic_missing_title_raises_error(self):
        """Should raise error if title is missing."""
        with pytest.raises(ValueError, match="title is required"):
            create_epic(title="", hive_name="test")

    def test_create_epic_with_custom_id(self, test_hive):
        """Should accept custom ID."""
        epic_id = create_epic(
            title="Test Epic",
            ticket_id="test.bees-xyz",
            hive_name="test",
        )

        assert epic_id == "test.bees-xyz"

        file_path = test_hive / "test.bees-xyz.md"
        assert file_path.exists()

    def test_create_epic_with_dependencies(self, test_hive):
        """Should create epic with dependencies."""
        epic_id = create_epic(
            title="Test Epic",
            up_dependencies=["test.bees-abc"],
            down_dependencies=["test.bees-xyz"],
            hive_name="test",
        )

        file_path = test_hive / f"{epic_id}.md"
        content = file_path.read_text()

        assert "up_dependencies:" in content
        assert "down_dependencies:" in content


class TestCreateTask:
    """Tests for create_task factory function."""

    def test_create_task_basic(self, test_hive):
        """Should create task with required fields."""
        task_id = create_task(
            title="Test Task",
            description="Test description",
            hive_name="test",
        )

        assert is_valid_ticket_id(task_id)
        assert task_id.startswith("test.bees-")

        file_path = test_hive / f"{task_id}.md"
        assert file_path.exists()

        content = file_path.read_text()
        assert "type: task" in content
        assert "title: Test Task" in content

    def test_create_task_with_parent(self, test_hive):
        """Should create task with parent reference."""
        task_id = create_task(
            title="Test Task",
            parent="test.bees-250",
            hive_name="test",
        )

        file_path = test_hive / f"{task_id}.md"
        content = file_path.read_text()

        assert "parent: test.bees-250" in content

    def test_create_task_missing_title_raises_error(self):
        """Should raise error if title is missing."""
        with pytest.raises(ValueError, match="title is required"):
            create_task(title="", hive_name="test")


class TestCreateSubtask:
    """Tests for create_subtask factory function."""

    def test_create_subtask_basic(self, test_hive):
        """Should create subtask with required fields."""
        subtask_id = create_subtask(
            title="Test Subtask",
            parent="test.bees-abc",
            description="Test description",
            hive_name="test",
        )

        assert is_valid_ticket_id(subtask_id)
        assert subtask_id.startswith("test.bees-")

        file_path = test_hive / f"{subtask_id}.md"
        assert file_path.exists()

        content = file_path.read_text()
        assert "type: subtask" in content
        assert "title: Test Subtask" in content
        assert "parent: test.bees-abc" in content

    def test_create_subtask_missing_parent_raises_error(self):
        """Should raise error if parent is missing."""
        with pytest.raises(ValueError, match="parent is required"):
            create_subtask(title="Test", parent="", hive_name="test")

    def test_create_subtask_missing_title_raises_error(self):
        """Should raise error if title is missing."""
        with pytest.raises(ValueError, match="title is required"):
            create_subtask(title="", parent="test.bees-abc", hive_name="test")


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_long_strings(self, test_hive):
        """Should handle very long strings."""
        long_title = "A" * 500
        long_description = "B" * 10000

        epic_id = create_epic(
            title=long_title,
            description=long_description,
            hive_name="test",
        )

        file_path = test_hive / f"{epic_id}.md"
        content = file_path.read_text()

        assert long_title in content
        assert long_description in content

    def test_unicode_and_special_chars(self, test_hive):
        """Should handle unicode and special characters."""
        epic_id = create_epic(
            title="Test with émojis 🚀 and unicode 中文",
            description="Special chars: @#$%^&*(){}[]",
            hive_name="test",
        )

        file_path = test_hive / f"{epic_id}.md"
        content = file_path.read_text()

        assert "émojis" in content
        assert "🚀" in content
        assert "中文" in content
        assert "@#$%^&*()" in content
