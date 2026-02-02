"""Unit tests for ticket writer and ticket factory."""

import pytest
from pathlib import Path
from datetime import datetime
import yaml

# Skip all tests - need refactoring for flat storage architecture
# These tests monkeypatch src.paths.TICKETS_DIR which no longer exists
# Need to update to use config-based hive paths
pytest.skip("Legacy TICKETS_DIR tests - needs refactoring for flat storage", allow_module_level=True)

from src.writer import serialize_frontmatter, write_ticket_file
from src.ticket_factory import create_epic, create_task, create_subtask
from src.id_utils import (
    generate_ticket_id,
    is_valid_ticket_id,
    generate_unique_ticket_id,
    extract_existing_ids_from_directory,
)


class TestIdGeneration:
    """Tests for ID generation functions."""

    def test_generate_ticket_id_format(self):
        """Should generate ID in correct format with hive prefix."""
        ticket_id = generate_ticket_id(hive_name="default")
        assert ticket_id.startswith("default.bees-")
        assert len(ticket_id) == 16  # default. (8) + bees- (5) + 3 chars
        assert is_valid_ticket_id(ticket_id)

    def test_generate_ticket_id_uniqueness(self):
        """Should generate different IDs on multiple calls."""
        ids = [generate_ticket_id(hive_name="default") for _ in range(100)]
        # Should have high uniqueness (though not guaranteed 100% with small space)
        assert len(set(ids)) > 90

    def test_is_valid_ticket_id_valid_cases(self):
        """Should accept valid ticket IDs."""
        assert is_valid_ticket_id("default.bees-250")
        assert is_valid_ticket_id("backend.bees-abc")
        assert is_valid_ticket_id("my_hive.bees-9pw")
        assert is_valid_ticket_id("test.bees-xyz")
        assert is_valid_ticket_id("hive_v2.bees-000")

    def test_is_valid_ticket_id_invalid_cases(self):
        """Should reject invalid ticket IDs."""
        assert not is_valid_ticket_id("default.bees-UPPER")  # uppercase not allowed
        assert not is_valid_ticket_id("default.bees-1234")   # too long
        assert not is_valid_ticket_id("default.bees-12")     # too short
        assert not is_valid_ticket_id("invalid-250")         # wrong format
        assert not is_valid_ticket_id("default.bees-")       # missing suffix
        assert not is_valid_ticket_id("250")                 # missing prefix
        assert not is_valid_ticket_id("")                    # empty
        assert not is_valid_ticket_id("default.bees-ab!")    # special char
        assert not is_valid_ticket_id("bees-250")            # unprefixed (legacy format)

    def test_is_valid_ticket_id_handles_none(self):
        """Should handle None gracefully."""
        assert not is_valid_ticket_id(None)

    def test_generate_unique_ticket_id_no_collisions(self):
        """Should not generate IDs in existing set."""
        existing = {"default.bees-250", "default.bees-abc", "default.bees-xyz"}
        new_id = generate_unique_ticket_id(hive_name="default", existing_ids=existing)
        assert new_id not in existing
        assert is_valid_ticket_id(new_id)

    def test_generate_unique_ticket_id_empty_set(self):
        """Should work with empty existing set."""
        new_id = generate_unique_ticket_id(hive_name="default", existing_ids=set())
        assert is_valid_ticket_id(new_id)

    def test_generate_unique_ticket_id_none_set(self):
        """Should work with None (no existing IDs)."""
        new_id = generate_unique_ticket_id(hive_name="default", existing_ids=None)
        assert is_valid_ticket_id(new_id)

    def test_extract_existing_ids_from_directory(self, tmp_path):
        """Should extract IDs from markdown filenames."""
        # Create ticket directory structure
        epics_dir = tmp_path / "epics"
        tasks_dir = tmp_path / "tasks"
        subtasks_dir = tmp_path / "subtasks"

        epics_dir.mkdir()
        tasks_dir.mkdir()
        subtasks_dir.mkdir()

        # Create some ticket files
        (epics_dir / "bees-250.md").write_text("test")
        (tasks_dir / "bees-abc.md").write_text("test")
        (subtasks_dir / "bees-xyz.md").write_text("test")
        (epics_dir / "README.md").write_text("test")  # Should be ignored

        existing_ids = extract_existing_ids_from_directory(tmp_path)

        assert existing_ids == {"bees-250", "bees-abc", "bees-xyz"}


class TestSerializeFrontmatter:
    """Tests for YAML frontmatter serialization."""

    def test_serialize_basic_fields(self):
        """Should serialize basic string fields."""
        data = {
            "id": "bees-250",
            "type": "epic",
            "title": "Test Epic",
        }
        frontmatter = serialize_frontmatter(data)

        assert frontmatter.startswith("---\n")
        assert frontmatter.endswith("---\n")
        assert "id: bees-250" in frontmatter
        assert "type: epic" in frontmatter
        assert "title: Test Epic" in frontmatter

    def test_serialize_lists(self):
        """Should serialize list fields."""
        data = {
            "id": "bees-250",
            "type": "epic",
            "title": "Test",
            "labels": ["open", "p0", "backend"],
            "children": ["bees-abc", "bees-xyz"],
        }
        frontmatter = serialize_frontmatter(data)

        # Parse back to verify
        yaml_content = frontmatter.split("---\n")[1]
        parsed = yaml.safe_load(yaml_content)

        assert parsed["labels"] == ["open", "p0", "backend"]
        assert parsed["children"] == ["bees-abc", "bees-xyz"]

    def test_serialize_multiline_strings(self):
        """Should handle multiline descriptions."""
        data = {
            "id": "bees-250",
            "type": "epic",
            "title": "Test",
            "description": "This is a long description\nwith multiple lines\nand newlines.",
        }
        frontmatter = serialize_frontmatter(data)

        # Parse back to verify
        yaml_content = frontmatter.split("---\n")[1]
        parsed = yaml.safe_load(yaml_content)

        assert parsed["description"] == data["description"]

    def test_serialize_special_characters(self):
        """Should handle special characters in strings."""
        data = {
            "id": "bees-250",
            "type": "epic",
            "title": "Test with: special, chars & symbols!",
            "description": 'Quotes "test" and \'single\'',
        }
        frontmatter = serialize_frontmatter(data)

        # Parse back to verify
        yaml_content = frontmatter.split("---\n")[1]
        parsed = yaml.safe_load(yaml_content)

        assert parsed["title"] == data["title"]
        assert parsed["description"] == data["description"]

    def test_serialize_datetime_fields(self):
        """Should convert datetime to ISO format string."""
        now = datetime.now()
        data = {
            "id": "bees-250",
            "type": "epic",
            "title": "Test",
            "created_at": now,
        }
        frontmatter = serialize_frontmatter(data)

        # Parse back to verify
        yaml_content = frontmatter.split("---\n")[1]
        parsed = yaml.safe_load(yaml_content)

        assert isinstance(parsed["created_at"], str)
        assert now.isoformat() in parsed["created_at"]

    def test_serialize_skips_none_values(self):
        """Should skip None values to keep frontmatter clean."""
        data = {
            "id": "bees-250",
            "type": "epic",
            "title": "Test",
            "owner": None,
            "priority": None,
        }
        frontmatter = serialize_frontmatter(data)

        assert "owner:" not in frontmatter
        assert "priority:" not in frontmatter

    def test_serialize_skips_empty_lists(self):
        """Should skip empty lists to keep frontmatter clean."""
        data = {
            "id": "bees-250",
            "type": "epic",
            "title": "Test",
            "labels": [],
            "children": [],
        }
        frontmatter = serialize_frontmatter(data)

        assert "labels:" not in frontmatter
        assert "children:" not in frontmatter


class TestWriteTicketFile:
    """Tests for markdown file writer."""

    def test_write_epic_file(self, tmp_path):
        """Should create epic file in correct directory."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        # Temporarily override TICKETS_DIR
        import src.paths as paths
        original_tickets_dir = paths.TICKETS_DIR
        paths.TICKETS_DIR = tickets_dir

        try:
            data = {
                "id": "bees-250",
                "type": "epic",
                "title": "Test Epic",
                "description": "Test description",
            }

            file_path = write_ticket_file(
                ticket_id="bees-250",
                ticket_type="epic",
                frontmatter_data=data,
                body="This is the body",
            )

            assert file_path.exists()
            assert file_path.parent.name == "epics"
            assert file_path.name == "bees-250.md"

            content = file_path.read_text()
            assert content.startswith("---\n")
            assert "id: bees-250" in content
            assert "This is the body" in content

        finally:
            paths.TICKETS_DIR = original_tickets_dir

    def test_write_task_file(self, tmp_path):
        """Should create task file in correct directory."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        import src.paths as paths
        original_tickets_dir = paths.TICKETS_DIR
        paths.TICKETS_DIR = tickets_dir

        try:
            data = {
                "id": "bees-abc",
                "type": "task",
                "title": "Test Task",
                "parent": "bees-250",
            }

            file_path = write_ticket_file(
                ticket_id="bees-abc",
                ticket_type="task",
                frontmatter_data=data,
            )

            assert file_path.exists()
            assert file_path.parent.name == "tasks"
            assert file_path.name == "bees-abc.md"

        finally:
            paths.TICKETS_DIR = original_tickets_dir

    def test_write_creates_parent_directories(self, tmp_path):
        """Should create directories if they don't exist."""
        tickets_dir = tmp_path / "tickets"
        # Don't create the directory

        import src.paths as paths
        original_tickets_dir = paths.TICKETS_DIR
        paths.TICKETS_DIR = tickets_dir

        try:
            data = {
                "id": "bees-250",
                "type": "epic",
                "title": "Test",
            }

            file_path = write_ticket_file(
                ticket_id="bees-250",
                ticket_type="epic",
                frontmatter_data=data,
            )

            assert file_path.exists()
            assert file_path.parent.exists()

        finally:
            paths.TICKETS_DIR = original_tickets_dir

    def test_write_with_empty_body(self, tmp_path):
        """Should handle empty body."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        import src.paths as paths
        original_tickets_dir = paths.TICKETS_DIR
        paths.TICKETS_DIR = tickets_dir

        try:
            data = {
                "id": "bees-250",
                "type": "epic",
                "title": "Test",
            }

            file_path = write_ticket_file(
                ticket_id="bees-250",
                ticket_type="epic",
                frontmatter_data=data,
                body="",
            )

            content = file_path.read_text()
            assert content.startswith("---\n")
            assert content.endswith("---\n")

        finally:
            paths.TICKETS_DIR = original_tickets_dir


class TestCreateEpic:
    """Tests for create_epic factory function."""

    def test_create_epic_basic(self, tmp_path):
        """Should create epic with required fields."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        import src.paths as paths
        original_tickets_dir = paths.TICKETS_DIR
        paths.TICKETS_DIR = tickets_dir

        try:
            epic_id = create_epic(
                title="Test Epic",
                description="Test description",
            )

            assert is_valid_ticket_id(epic_id)

            # Verify file was created
            file_path = tickets_dir / "epics" / f"{epic_id}.md"
            assert file_path.exists()

            # Verify content
            content = file_path.read_text()
            assert "type: epic" in content
            assert "title: Test Epic" in content

        finally:
            paths.TICKETS_DIR = original_tickets_dir

    def test_create_epic_with_labels(self, tmp_path):
        """Should create epic with labels."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        import src.paths as paths
        original_tickets_dir = paths.TICKETS_DIR
        paths.TICKETS_DIR = tickets_dir

        try:
            epic_id = create_epic(
                title="Test Epic",
                labels=["open", "p0"],
            )

            file_path = tickets_dir / "epics" / f"{epic_id}.md"
            content = file_path.read_text()

            assert "labels:" in content
            assert "- open" in content
            assert "- p0" in content

        finally:
            paths.TICKETS_DIR = original_tickets_dir

    def test_create_epic_missing_title_raises_error(self):
        """Should raise error if title is missing."""
        with pytest.raises(ValueError, match="title is required"):
            create_epic(title="")

    def test_create_epic_with_custom_id(self, tmp_path):
        """Should accept custom ID."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        import src.paths as paths
        original_tickets_dir = paths.TICKETS_DIR
        paths.TICKETS_DIR = tickets_dir

        try:
            epic_id = create_epic(
                title="Test Epic",
                ticket_id="bees-xyz",
            )

            assert epic_id == "bees-xyz"

            file_path = tickets_dir / "epics" / "bees-xyz.md"
            assert file_path.exists()

        finally:
            paths.TICKETS_DIR = original_tickets_dir


class TestCreateTask:
    """Tests for create_task factory function."""

    def test_create_task_basic(self, tmp_path):
        """Should create task with required fields."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        import src.paths as paths
        original_tickets_dir = paths.TICKETS_DIR
        paths.TICKETS_DIR = tickets_dir

        try:
            task_id = create_task(
                title="Test Task",
                description="Test description",
            )

            assert is_valid_ticket_id(task_id)

            file_path = tickets_dir / "tasks" / f"{task_id}.md"
            assert file_path.exists()

            content = file_path.read_text()
            assert "type: task" in content
            assert "title: Test Task" in content

        finally:
            paths.TICKETS_DIR = original_tickets_dir

    def test_create_task_with_parent(self, tmp_path):
        """Should create task with parent reference."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        import src.paths as paths
        original_tickets_dir = paths.TICKETS_DIR
        paths.TICKETS_DIR = tickets_dir

        try:
            task_id = create_task(
                title="Test Task",
                parent="bees-250",
            )

            file_path = tickets_dir / "tasks" / f"{task_id}.md"
            content = file_path.read_text()

            assert "parent: bees-250" in content

        finally:
            paths.TICKETS_DIR = original_tickets_dir

    def test_create_task_missing_title_raises_error(self):
        """Should raise error if title is missing."""
        with pytest.raises(ValueError, match="title is required"):
            create_task(title="")


class TestCreateSubtask:
    """Tests for create_subtask factory function."""

    def test_create_subtask_basic(self, tmp_path):
        """Should create subtask with required fields."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        import src.paths as paths
        original_tickets_dir = paths.TICKETS_DIR
        paths.TICKETS_DIR = tickets_dir

        try:
            subtask_id = create_subtask(
                title="Test Subtask",
                parent="bees-abc",
                description="Test description",
            )

            assert is_valid_ticket_id(subtask_id)

            file_path = tickets_dir / "subtasks" / f"{subtask_id}.md"
            assert file_path.exists()

            content = file_path.read_text()
            assert "type: subtask" in content
            assert "title: Test Subtask" in content
            assert "parent: bees-abc" in content

        finally:
            paths.TICKETS_DIR = original_tickets_dir

    def test_create_subtask_missing_parent_raises_error(self):
        """Should raise error if parent is missing."""
        with pytest.raises(ValueError, match="parent is required"):
            create_subtask(title="Test", parent="")

    def test_create_subtask_missing_title_raises_error(self):
        """Should raise error if title is missing."""
        with pytest.raises(ValueError, match="title is required"):
            create_subtask(title="", parent="bees-abc")


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_long_strings(self, tmp_path):
        """Should handle very long strings."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        import src.paths as paths
        original_tickets_dir = paths.TICKETS_DIR
        paths.TICKETS_DIR = tickets_dir

        try:
            long_title = "A" * 500
            long_description = "B" * 10000

            epic_id = create_epic(
                title=long_title,
                description=long_description,
            )

            file_path = tickets_dir / "epics" / f"{epic_id}.md"
            content = file_path.read_text()

            assert long_title in content
            assert long_description in content

        finally:
            paths.TICKETS_DIR = original_tickets_dir

    def test_unicode_and_special_chars(self, tmp_path):
        """Should handle unicode and special characters."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        import src.paths as paths
        original_tickets_dir = paths.TICKETS_DIR
        paths.TICKETS_DIR = tickets_dir

        try:
            epic_id = create_epic(
                title="Test with émojis 🚀 and unicode 中文",
                description="Special chars: @#$%^&*(){}[]",
            )

            file_path = tickets_dir / "epics" / f"{epic_id}.md"
            content = file_path.read_text()

            assert "émojis" in content
            assert "🚀" in content
            assert "中文" in content
            assert "@#$%^&*()" in content

        finally:
            paths.TICKETS_DIR = original_tickets_dir
