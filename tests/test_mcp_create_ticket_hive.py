"""Unit tests for MCP _create_ticket with hive_name support."""

import pytest
from pathlib import Path
import tempfile
import shutil
import os

from src.mcp_server import _create_ticket
from src.reader import read_ticket
from src.paths import get_ticket_path
from src.id_utils import is_valid_ticket_id
from src.config import save_bees_config, BeesConfig, HiveConfig
from datetime import datetime


@pytest.fixture
def temp_tickets_dir():
    """Create temporary hive directory with config-based setup."""
    # Create temp directory structure
    temp_dir = Path(tempfile.mkdtemp())

    # Save original working directory
    original_cwd = os.getcwd()

    # Change to temp directory
    os.chdir(temp_dir)

    # Create hive directories for testing
    backend_dir = temp_dir / "backend"
    backend_dir.mkdir()
    frontend_dir = temp_dir / "frontend"
    frontend_dir.mkdir()
    test_hive_dir = temp_dir / "test_hive"
    test_hive_dir.mkdir()
    my_hive_dir = temp_dir / "my_hive"
    my_hive_dir.mkdir()
    front_end_dir = temp_dir / "front_end"
    front_end_dir.mkdir()
    back_end_dir = temp_dir / "back_end"
    back_end_dir.mkdir()
    myhive_dir = temp_dir / "myhive"
    myhive_dir.mkdir()
    test_123_dir = temp_dir / "test_123"
    test_123_dir.mkdir()
    test_dir = temp_dir / "test"
    test_dir.mkdir()
    a_dir = temp_dir / "a"
    a_dir.mkdir()
    _1_dir = temp_dir / "_1"
    _1_dir.mkdir()

    # Initialize .bees/config.json with test hives
    config = BeesConfig(
        hives={
            'backend': HiveConfig(
                path=str(backend_dir),
                display_name='Backend',
                created_at=datetime.now().isoformat()
            ),
            'frontend': HiveConfig(
                path=str(frontend_dir),
                display_name='Frontend',
                created_at=datetime.now().isoformat()
            ),
            'test_hive': HiveConfig(
                path=str(test_hive_dir),
                display_name='Test Hive',
                created_at=datetime.now().isoformat()
            ),
            'my_hive': HiveConfig(
                path=str(my_hive_dir),
                display_name='My Hive',
                created_at=datetime.now().isoformat()
            ),
            'front_end': HiveConfig(
                path=str(front_end_dir),
                display_name='Front End',
                created_at=datetime.now().isoformat()
            ),
            'back_end': HiveConfig(
                path=str(back_end_dir),
                display_name='Back End',
                created_at=datetime.now().isoformat()
            ),
            'myhive': HiveConfig(
                path=str(myhive_dir),
                display_name='MyHive',
                created_at=datetime.now().isoformat()
            ),
            'test_123': HiveConfig(
                path=str(test_123_dir),
                display_name='Test-123',
                created_at=datetime.now().isoformat()
            ),
            'test': HiveConfig(
                path=str(test_dir),
                display_name='Test',
                created_at=datetime.now().isoformat()
            ),
            'a': HiveConfig(
                path=str(a_dir),
                display_name='A',
                created_at=datetime.now().isoformat()
            ),
            '_1': HiveConfig(
                path=str(_1_dir),
                display_name='1',
                created_at=datetime.now().isoformat()
            ),
        },
        allow_cross_hive_dependencies=True,
        schema_version='1.0'
    )
    save_bees_config(config)

    yield temp_dir

    # Restore original working directory and cleanup
    os.chdir(original_cwd)
    shutil.rmtree(temp_dir)


class TestMCPCreateTicketWithHive:
    """Tests for _create_ticket() MCP tool with hive_name parameter."""

    def test_create_epic_with_hive(self, temp_tickets_dir):
        """Should create epic with hive-prefixed ID when hive_name provided."""
        result = _create_ticket(
            ticket_type="epic",
            title="Backend Epic",
            description="Backend work",
            hive_name="backend"
        )

        assert result["status"] == "success"
        ticket_id = result["ticket_id"]
        assert ticket_id.startswith("backend.bees-")
        assert is_valid_ticket_id(ticket_id)

        # Verify file was created and content (flat storage in hive root)
        epic_path = get_ticket_path(ticket_id, "epic")
        assert epic_path.exists()
        assert epic_path.parent == temp_tickets_dir / "backend"  # Flat storage - file in hive root
        epic = read_ticket(epic_path)
        assert epic.title == "Backend Epic"

    def test_create_task_with_hive(self, temp_tickets_dir):
        """Should create task with hive-prefixed ID."""
        result = _create_ticket(
            ticket_type="task",
            title="Backend Task",
            description="Backend work",
            hive_name="backend"
        )

        assert result["status"] == "success"
        ticket_id = result["ticket_id"]
        assert ticket_id.startswith("backend.bees-")
        assert is_valid_ticket_id(ticket_id)

    def test_create_subtask_with_hive(self, temp_tickets_dir):
        """Should create subtask with hive-prefixed ID."""
        # Create parent task first
        parent_result = _create_ticket(
            ticket_type="task",
            title="Parent Task",
            hive_name="backend"
        )
        parent_id = parent_result["ticket_id"]

        # Create subtask with hive
        result = _create_ticket(
            ticket_type="subtask",
            title="Backend Subtask",
            hive_name="backend",
            parent=parent_id,
            description="Backend work"
        )

        assert result["status"] == "success"
        ticket_id = result["ticket_id"]
        assert ticket_id.startswith("backend.bees-")
        assert is_valid_ticket_id(ticket_id)

        # Verify parent relationship
        subtask = read_ticket(get_ticket_path(ticket_id, "subtask"))
        assert subtask.parent == parent_id

    def test_hive_name_normalization(self, temp_tickets_dir):
        """Should normalize hive names."""
        result = _create_ticket(
            ticket_type="epic",
            title="Test Epic",
            hive_name="My Hive"
        )

        ticket_id = result["ticket_id"]
        assert ticket_id.startswith("my_hive.bees-")

        result = _create_ticket(
            ticket_type="epic",
            title="Test Epic 2",
            hive_name="Front-End"
        )

        ticket_id = result["ticket_id"]
        assert ticket_id.startswith("front_end.bees-")

    def test_multiple_hives(self, temp_tickets_dir):
        """Should support creating tickets in multiple hives."""
        # Create tickets in different hives
        backend_result = _create_ticket(
            ticket_type="epic",
            title="Backend Epic",
            hive_name="backend"
        )

        frontend_result = _create_ticket(
            ticket_type="epic",
            title="Frontend Epic",
            hive_name="frontend"
        )

        # Both should succeed with hive-prefixed IDs
        assert backend_result["ticket_id"].startswith("backend.bees-")
        assert frontend_result["ticket_id"].startswith("frontend.bees-")

    def test_hive_with_all_ticket_types(self, temp_tickets_dir):
        """Should support hive_name for epic, task, and subtask."""
        # Create epic with hive
        epic_result = _create_ticket(
            ticket_type="epic",
            title="Hive Epic",
            hive_name="test_hive"
        )
        assert epic_result["ticket_id"].startswith("test_hive.bees-")

        # Create task with hive
        task_result = _create_ticket(
            ticket_type="task",
            title="Hive Task",
            hive_name="test_hive"
        )
        assert task_result["ticket_id"].startswith("test_hive.bees-")

        # Create subtask with hive
        subtask_result = _create_ticket(
            ticket_type="subtask",
            title="Hive Subtask",
            parent=task_result["ticket_id"],
            hive_name="test_hive"
        )
        assert subtask_result["ticket_id"].startswith("test_hive.bees-")


    def test_cross_hive_relationships(self, temp_tickets_dir):
        """Should allow relationships between tickets in different hives."""
        # Create parent epic in one hive
        parent_result = _create_ticket(
            ticket_type="epic",
            title="Parent Epic",
            hive_name="frontend"
        )
        parent_id = parent_result["ticket_id"]

        # Create child task in different hive
        child_result = _create_ticket(
            ticket_type="task",
            title="Child Task",
            hive_name="backend",
            parent=parent_id
        )

        # Both should succeed
        assert parent_result["status"] == "success"
        assert child_result["status"] == "success"
        assert child_result["ticket_id"].startswith("backend.bees-")

        # Verify relationship
        child = read_ticket(get_ticket_path(child_result["ticket_id"], "task"))
        assert child.parent == parent_id

    def test_hive_with_dependencies(self, temp_tickets_dir):
        """Should support dependencies with hive-prefixed IDs."""
        # Create blocking task with hive
        blocking_result = _create_ticket(
            ticket_type="task",
            title="Blocking Task",
            hive_name="backend"
        )
        blocking_id = blocking_result["ticket_id"]

        # Create blocked task with dependency
        blocked_result = _create_ticket(
            ticket_type="task",
            title="Blocked Task",
            up_dependencies=[blocking_id],
            hive_name="backend"
        )

        assert blocked_result["status"] == "success"
        assert blocked_result["ticket_id"].startswith("backend.bees-")

        # Verify dependency was set
        blocked = read_ticket(get_ticket_path(blocked_result["ticket_id"], "task"))
        assert blocking_id in blocked.up_dependencies


class TestMCPCreateTicketHiveValidation:
    """Tests for _create_ticket() hive_name validation."""

    def test_valid_hive_names_pass(self, temp_tickets_dir):
        """Valid hive names should pass validation."""
        # Simple alphanumeric
        result1 = _create_ticket(
            ticket_type="epic",
            title="Test 1",
            hive_name="backend"
        )
        assert result1["status"] == "success"
        assert result1["ticket_id"].startswith("backend.bees-")

        # Mixed case (gets normalized)
        result2 = _create_ticket(
            ticket_type="epic",
            title="Test 2",
            hive_name="Back End"
        )
        assert result2["status"] == "success"
        assert result2["ticket_id"].startswith("back_end.bees-")

    def test_special_chars_only_hive_name_raises_error(self, temp_tickets_dir):
        """Hive name with only special characters should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Test",
                hive_name="!@#$%"
            )
        assert "Invalid hive_name" in str(exc_info.value)
        assert "must contain at least one alphanumeric character" in str(exc_info.value)

    def test_normalized_empty_string_raises_error(self, temp_tickets_dir):
        """Hive name that normalizes to empty string should raise ValueError."""
        # Names with only hyphens that become empty after normalization
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Test",
                hive_name="---"
            )
        assert "Invalid hive_name" in str(exc_info.value)

    def test_hive_with_special_chars_passes(self, temp_tickets_dir):
        """Hive name with special chars but has alphanumeric should pass."""
        result = _create_ticket(
            ticket_type="epic",
            title="Test Epic",
            hive_name="my@hive"
        )
        assert result["status"] == "success"
        # Should normalize to myhive (@ removed)
        assert result["ticket_id"].startswith("myhive.bees-")

    def test_hive_with_only_special_chars_fails(self, temp_tickets_dir):
        """Hive name with only special chars should fail validation."""
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Test",
                hive_name="!!!!"
            )
        assert "Invalid hive_name" in str(exc_info.value)
        assert "must contain at least one alphanumeric character" in str(exc_info.value)

    def test_hive_with_mixed_alphanumeric_special_passes(self, temp_tickets_dir):
        """Hive name with mixed alphanumeric/special chars should pass."""
        result = _create_ticket(
            ticket_type="epic",
            title="Test Epic",
            hive_name="test-123"
        )
        assert result["status"] == "success"
        assert result["ticket_id"].startswith("test_123.bees-")

    def test_normalized_result_never_empty_when_alphanumeric_present(self, temp_tickets_dir):
        """Verify normalized result is never empty when alphanumeric check passes."""
        # If we have at least one alphanumeric char, normalization cannot result in empty string
        test_cases = [
            "a",           # Single letter
            "1",           # Single digit
            "@a@",         # Letter surrounded by special chars
            "!!!test!!!",  # Alphanumeric with special chars
            "my-hive-123", # Mixed with hyphens
        ]

        for hive_name in test_cases:
            result = _create_ticket(
                ticket_type="epic",
                title=f"Test for {hive_name}",
                hive_name=hive_name
            )
            assert result["status"] == "success"
            ticket_id = result["ticket_id"]
            # Verify ID has a non-empty prefix before .bees-
            prefix = ticket_id.split(".bees-")[0]
            assert len(prefix) > 0, f"Normalized hive name is empty for input '{hive_name}'"


class TestMCPCreateTicketRequiredHive:
    """Tests for _create_ticket() with required hive_name parameter (Task bees-0pe2j)."""

    def test_create_ticket_without_hive_raises_error(self, temp_tickets_dir):
        """Should raise TypeError when hive_name is not provided."""
        with pytest.raises(TypeError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Test Epic"
            )
        # Python raises TypeError for missing required parameter
        assert "hive_name" in str(exc_info.value)

    def test_create_ticket_with_none_hive_raises_error(self, temp_tickets_dir):
        """Should raise ValueError when hive_name is None."""
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Test Epic",
                hive_name=None
            )
        assert "hive_name is required" in str(exc_info.value)

    def test_create_ticket_with_empty_string_raises_error(self, temp_tickets_dir):
        """Should raise ValueError when hive_name is empty string."""
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Test Epic",
                hive_name=""
            )
        assert "hive_name is required" in str(exc_info.value)

    def test_create_ticket_with_whitespace_raises_error(self, temp_tickets_dir):
        """Should raise ValueError when hive_name is whitespace only."""
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Test Epic",
                hive_name="   "
            )
        assert "hive_name is required" in str(exc_info.value)

    def test_create_ticket_with_valid_hive_succeeds(self, temp_tickets_dir):
        """Should succeed when valid hive_name is provided."""
        result = _create_ticket(
            ticket_type="epic",
            title="Test Epic",
            hive_name="backend"
        )
        assert result["status"] == "success"
        assert result["ticket_id"].startswith("backend.bees-")

    def test_all_ticket_types_require_hive(self, temp_tickets_dir):
        """All ticket types (epic, task, subtask) should require hive_name."""
        # Epic without hive_name
        with pytest.raises(TypeError):
            _create_ticket(
                ticket_type="epic",
                title="Epic"
            )

        # Task without hive_name
        with pytest.raises(TypeError):
            _create_ticket(
                ticket_type="task",
                title="Task"
            )

        # Create parent first for subtask test
        parent_result = _create_ticket(
            ticket_type="task",
            title="Parent",
            hive_name="test"
        )

        # Subtask without hive_name
        with pytest.raises(TypeError):
            _create_ticket(
                ticket_type="subtask",
                title="Subtask",
                parent=parent_result["ticket_id"]
            )

    def test_error_messages_are_clear(self, temp_tickets_dir):
        """Error messages should clearly indicate hive_name is required."""
        # None value
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Test",
                hive_name=None
            )
        assert "required" in str(exc_info.value).lower()

        # Empty string
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Test",
                hive_name=""
            )
        assert "required" in str(exc_info.value).lower()
