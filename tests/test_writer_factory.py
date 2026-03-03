"""
Unit tests for ticket file writing.

PURPOSE:
Tests ticket file writing including YAML frontmatter generation, file
formatting, and filesystem operations.

SCOPE - Tests that belong here:
- write_ticket_file(): Write Ticket objects to filesystem
- YAML frontmatter generation
- File format (frontmatter + description)
- File encoding (UTF-8)
- Directory creation (ensure parent directories exist)
- Atomic write operations
- Integration with ticket_factory (create -> write workflow)

SCOPE - Tests that DON'T belong here:
- Ticket reading -> test_reader.py
- Ticket factories -> test_ticket_factory.py (factory object creation)
- Ticket creation logic -> test_create_ticket.py
- Path resolution -> test_paths.py

RELATED FILES:
- test_reader.py: Ticket file reading (inverse operation)
- test_ticket_factory.py: Ticket object creation
- test_create_ticket.py: End-to-end ticket creation
- test_paths.py: Path resolution for write operations
"""

from datetime import datetime

import pytest

from src.id_utils import is_valid_ticket_id
from src.repo_context import repo_root_context
from src.ticket_factory import (
    _create_bee_with_id,
    _create_child_tier_with_id,
    create_bee,
    create_child_tier,
)
from src.writer import write_ticket_file
from tests.conftest import write_scoped_config
from tests.test_constants import (
    HIVE_TEST,
    TICKET_ID_PARENT_BEE,
    TICKET_ID_T1,
    TICKET_ID_T2,
    TICKET_ID_TEST_BEE,
    TITLE_TEST_BEE,
    TITLE_TEST_SUBTASK,
    TITLE_TEST_TASK,
)


@pytest.fixture
def test_hive(tmp_path, monkeypatch, mock_global_bees_dir):
    """Create temporary hive with config for testing."""
    test_hive_dir = tmp_path / HIVE_TEST
    test_hive_dir.mkdir()

    monkeypatch.chdir(tmp_path)

    scope_data = {
        "hives": {HIVE_TEST: {"path": str(test_hive_dir), "display_name": "Test Hive", "created_at": datetime.now().isoformat()}},
        "child_tiers": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
    }
    write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

    with repo_root_context(tmp_path):
        yield test_hive_dir


class TestWriteTicketFile:
    """Tests for write_ticket_file with hierarchical directory storage."""

    def test_write_bee_creates_directory_at_root(self, test_hive):
        """Should create bee ticket in hierarchical directory at hive root."""
        ticket_id = TICKET_ID_TEST_BEE
        data = {"id": ticket_id, "type": "bee", "title": TITLE_TEST_BEE}

        file_path = write_ticket_file(
            ticket_id=ticket_id,
            ticket_type="bee",
            frontmatter_data=data,
            body="This is the body",
            hive_name=HIVE_TEST,
        )

        # Verify hierarchical structure: {hive_root}/{ticket_id}/{ticket_id}.md
        assert file_path.exists()
        assert file_path.parent.name == ticket_id
        assert file_path.parent.parent == test_hive
        assert file_path.name == f"{ticket_id}.md"

        content = file_path.read_text()
        assert content.startswith("---\n")
        assert f"id: {ticket_id}" in content
        assert "This is the body" in content

    def test_write_child_creates_directory_under_parent(self, test_hive):
        """Should create child ticket in directory nested under parent."""
        # First create parent bee
        parent_id = TICKET_ID_TEST_BEE
        parent_data = {"id": parent_id, "type": "bee", "title": "Parent Bee"}
        parent_path = write_ticket_file(
            ticket_id=parent_id,
            ticket_type="bee",
            frontmatter_data=parent_data,
            hive_name=HIVE_TEST,
        )

        # Create child task
        child_id = TICKET_ID_T1
        child_data = {"id": child_id, "type": "t1", "title": TITLE_TEST_TASK, "parent": parent_id}
        child_path = write_ticket_file(
            ticket_id=child_id,
            ticket_type="t1",
            frontmatter_data=child_data,
            hive_name=HIVE_TEST,
        )

        # Verify hierarchical structure: {parent_dir}/{child_id}/{child_id}.md
        assert child_path.exists()
        assert child_path.parent.name == child_id
        assert child_path.parent.parent == parent_path.parent
        assert child_path.name == f"{child_id}.md"

    def test_write_grandchild_creates_deeply_nested_directory(self, test_hive):
        """Should create grandchild ticket in deeply nested directory structure."""
        # Create parent bee
        bee_id = TICKET_ID_TEST_BEE
        bee_data = {"id": bee_id, "type": "bee", "title": "Bee"}
        _bee_path = write_ticket_file(bee_id, "bee", bee_data, hive_name=HIVE_TEST)

        # Create child task
        task_id = TICKET_ID_T1
        task_data = {"id": task_id, "type": "t1", "title": "Task", "parent": bee_id}
        _task_path = write_ticket_file(task_id, "t1", task_data, hive_name=HIVE_TEST)

        # Create grandchild subtask
        subtask_id = TICKET_ID_T2
        subtask_data = {"id": subtask_id, "type": "t2", "title": TITLE_TEST_SUBTASK, "parent": task_id}
        subtask_path = write_ticket_file(subtask_id, "t2", subtask_data, hive_name=HIVE_TEST)

        # Verify deep nesting: {bee_dir}/{task_dir}/{subtask_dir}/{subtask_id}.md
        assert subtask_path.exists()
        assert subtask_path.parent.name == subtask_id
        assert subtask_path.parent.parent.name == task_id
        assert subtask_path.parent.parent.parent.name == bee_id
        assert subtask_path.name == f"{subtask_id}.md"

    def test_update_existing_ticket_preserves_location(self, test_hive):
        """Should update existing ticket file in place without moving it."""
        ticket_id = TICKET_ID_TEST_BEE
        data = {"id": ticket_id, "type": "bee", "title": "Original Title"}

        # Create ticket
        original_path = write_ticket_file(ticket_id, "bee", data, hive_name=HIVE_TEST)

        # Update ticket (change title)
        updated_data = {"id": ticket_id, "type": "bee", "title": "Updated Title"}
        updated_path = write_ticket_file(ticket_id, "bee", updated_data, hive_name=HIVE_TEST)

        # Should be same path
        assert updated_path == original_path
        assert updated_path.exists()

        content = updated_path.read_text()
        assert "Updated Title" in content

    def test_write_creates_parent_directories(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Should create full directory chain including hive and ticket directories."""
        new_hive_dir = tmp_path / "new_hive"
        monkeypatch.chdir(tmp_path)

        scope_data = {
            "hives": {"newhive": {"path": str(new_hive_dir), "display_name": "New Hive", "created_at": datetime.now().isoformat()}},
            "child_tiers": {},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        with repo_root_context(tmp_path):
            data = {"id": TICKET_ID_TEST_BEE, "type": "bee", "title": "Test"}
            file_path = write_ticket_file(
                ticket_id=TICKET_ID_TEST_BEE, ticket_type="bee", frontmatter_data=data, hive_name="newhive",
            )

            # Verify hierarchical structure was created
            assert file_path.exists()
            assert file_path.parent.name == TICKET_ID_TEST_BEE
            assert file_path.parent.parent == new_hive_dir

    def test_write_adds_schema_version(self, test_hive):
        """Should automatically add schema_version field."""
        ticket_id = TICKET_ID_TEST_BEE
        data = {"id": ticket_id, "type": "bee", "title": TITLE_TEST_BEE}

        file_path = write_ticket_file(
            ticket_id=ticket_id, ticket_type="bee", frontmatter_data=data, hive_name=HIVE_TEST,
        )

        content = file_path.read_text()
        assert "schema_version:" in content

    @pytest.mark.parametrize(
        "ticket_id,match",
        [
            pytest.param("not-a-valid-id-##", "Invalid ticket ID format", id="invalid_format"),
            pytest.param("../etc/passwd", "Invalid ticket ID format", id="path_traversal"),
            pytest.param("", "Invalid ticket ID format", id="empty"),
        ],
    )
    def test_write_rejects_invalid_ticket_id(self, test_hive, ticket_id, match):
        """Should raise ValueError for invalid ticket_id formats."""
        data = {"id": ticket_id, "type": "bee", "title": "Test"}
        with pytest.raises(ValueError, match=match):
            write_ticket_file(ticket_id=ticket_id, ticket_type="bee", frontmatter_data=data, hive_name=HIVE_TEST)

    def test_write_ticket_file_with_explicit_path_skips_scan(self, test_hive):
        """Providing file_path should skip os.walk scan entirely."""
        import os
        from unittest.mock import patch

        ticket_id = TICKET_ID_TEST_BEE
        target_dir = test_hive / ticket_id
        target_dir.mkdir(parents=True, exist_ok=True)
        explicit_path = target_dir / f"{ticket_id}.md"

        data = {"id": ticket_id, "type": "bee", "title": "Explicit Path Bee"}

        with patch("os.walk", wraps=os.walk) as mock_walk:
            result_path = write_ticket_file(
                ticket_id=ticket_id,
                ticket_type="bee",
                frontmatter_data=data,
                body="Body content",
                hive_name=HIVE_TEST,
                file_path=explicit_path,
            )

        assert result_path == explicit_path
        assert result_path.exists()
        mock_walk.assert_not_called()


class TestCreateEpic:
    """Tests for create_bee factory function with hierarchical storage."""

    def test_create_bee_basic(self, test_hive):
        """Should create bee with hierarchical directory structure."""
        epic_id, _ = create_bee(title=TITLE_TEST_BEE, description="Test description", hive_name=HIVE_TEST)

        assert is_valid_ticket_id(epic_id)
        # New format: bees use "b." prefix
        assert epic_id.startswith("b.")

        # Verify hierarchical structure
        file_path = test_hive / epic_id / f"{epic_id}.md"
        assert file_path.exists()
        content = file_path.read_text()
        assert "type: bee" in content
        assert f"title: {TITLE_TEST_BEE}" in content

    def test_create_bee_with_tags(self, test_hive):
        """Should create bee with tags in hierarchical structure."""
        epic_id, _ = create_bee(title=TITLE_TEST_BEE, tags=["open", "p0"], hive_name=HIVE_TEST)

        file_path = test_hive / epic_id / f"{epic_id}.md"
        content = file_path.read_text()
        assert "tags:" in content
        assert "- open" in content
        assert "- p0" in content

    def test_create_bee_missing_title_raises_error(self):
        """Should raise error if title is missing."""
        with pytest.raises(ValueError, match="title is required"):
            create_bee(title="", hive_name=HIVE_TEST)

    def test_create_bee_with_custom_id(self, test_hive):
        """Should accept custom ID and create hierarchical structure."""
        custom_id = TICKET_ID_PARENT_BEE
        epic_id, _ = _create_bee_with_id(ticket_id=custom_id, title=TITLE_TEST_BEE, hive_name=HIVE_TEST)

        assert epic_id == custom_id
        file_path = test_hive / custom_id / f"{custom_id}.md"
        assert file_path.exists()

    def test_create_bee_with_dependencies(self, test_hive):
        """Should create bee with dependencies in hierarchical structure."""
        epic_id, _ = create_bee(
            title=TITLE_TEST_BEE,
            up_dependencies=[TICKET_ID_TEST_BEE],
            down_dependencies=[TICKET_ID_PARENT_BEE],
            hive_name=HIVE_TEST,
        )

        file_path = test_hive / epic_id / f"{epic_id}.md"
        content = file_path.read_text()
        assert "up_dependencies:" in content
        assert "down_dependencies:" in content

    def test_create_bee_rejects_invalid_ticket_id(self, test_hive):
        """Should raise ValueError when ticket_id contains characters outside ID_CHARSET."""
        with pytest.raises(ValueError, match="Invalid ticket_id"):
            _create_bee_with_id(ticket_id="b.INVALID_BAD", title="X", hive_name=HIVE_TEST)


class TestCreateTask:
    """Tests for create_child_tier factory function with t1 tier (task equivalent)."""

    def test_create_task_basic(self, test_hive):
        """Should create t1 tier ticket with hierarchical directory structure under parent."""
        # Create parent bee first (t1 requires parent)
        parent_id = TICKET_ID_TEST_BEE
        _create_bee_with_id(ticket_id=parent_id, title="Parent Bee", hive_name=HIVE_TEST)

        task_id, _ = create_child_tier(ticket_type="t1", title=TITLE_TEST_TASK, parent=parent_id, description="Test description", hive_name=HIVE_TEST)

        assert is_valid_ticket_id(task_id)
        # t1 should be nested under parent in hierarchical structure
        file_path = test_hive / parent_id / task_id / f"{task_id}.md"
        assert file_path.exists()
        content = file_path.read_text()
        assert "type: t1" in content

    def test_create_task_with_parent(self, test_hive):
        """Should create t1 tier ticket nested under parent in hierarchical structure."""
        # First create parent bee
        parent_id = TICKET_ID_TEST_BEE
        _create_bee_with_id(ticket_id=parent_id, title="Parent Bee", hive_name=HIVE_TEST)

        # Create t1 ticket with parent
        task_id, _ = create_child_tier(ticket_type="t1", title=TITLE_TEST_TASK, parent=parent_id, hive_name=HIVE_TEST)

        # Verify t1 ticket is nested under parent
        file_path = test_hive / parent_id / task_id / f"{task_id}.md"
        assert file_path.exists()
        content = file_path.read_text()
        assert f"parent: {parent_id}" in content

    def test_create_task_missing_title_raises_error(self):
        """Should raise error if title is missing."""
        with pytest.raises(ValueError, match="title is required"):
            create_child_tier(ticket_type="t1", title="", parent=TICKET_ID_TEST_BEE, hive_name=HIVE_TEST)

    def test_create_child_tier_rejects_invalid_ticket_id(self, test_hive):
        """Should raise ValueError when ticket_id contains characters outside ID_CHARSET."""
        parent_id = TICKET_ID_TEST_BEE
        _create_bee_with_id(ticket_id=parent_id, title="Parent Bee", hive_name=HIVE_TEST)
        with pytest.raises(ValueError, match="Invalid ticket_id"):
            _create_child_tier_with_id(ticket_id="t1.INVALID_BAD", ticket_type="t1", title="X", parent=parent_id, hive_name=HIVE_TEST)


class TestCreateSubtask:
    """Tests for create_child_tier factory function with t2 tier (subtask equivalent)."""

    def test_create_subtask_basic(self, test_hive):
        """Should create t2 tier ticket nested under parent in hierarchical structure."""
        # Create parent bee first
        bee_id = TICKET_ID_TEST_BEE
        _create_bee_with_id(ticket_id=bee_id, title="Parent Bee", hive_name=HIVE_TEST)

        # Create parent t1 ticket
        parent_id = TICKET_ID_T1
        _create_child_tier_with_id(ticket_id=parent_id, ticket_type="t1", title="Parent Task", parent=bee_id, hive_name=HIVE_TEST)

        # Create t2 tier ticket
        subtask_id, _ = create_child_tier(
            ticket_type="t2", title=TITLE_TEST_SUBTASK, parent=parent_id, description="Test description", hive_name=HIVE_TEST,
        )

        assert is_valid_ticket_id(subtask_id)
        # Verify t2 ticket is nested under parent t1 ticket
        file_path = test_hive / bee_id / parent_id / subtask_id / f"{subtask_id}.md"
        assert file_path.exists()
        content = file_path.read_text()
        assert "type: t2" in content
        assert f"parent: {parent_id}" in content

    @pytest.mark.parametrize(
        "title,parent,match",
        [
            pytest.param(TITLE_TEST_SUBTASK, "", "parent is required", id="missing_parent"),
            pytest.param("", TICKET_ID_T1, "title is required", id="missing_title"),
        ],
    )
    def test_create_subtask_missing_required_fields(self, title, parent, match):
        """Should raise error if required fields are missing."""
        with pytest.raises(ValueError, match=match):
            create_child_tier(ticket_type="t2", title=title, parent=parent, hive_name=HIVE_TEST)


