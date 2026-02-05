"""
Unit tests for show_ticket MCP command.

Tests the show_ticket command that retrieves and returns ticket data by ID.
"""

import pytest
from pathlib import Path
from datetime import datetime
from src.mcp_server import _show_ticket
from src.ticket_factory import create_epic, create_task
from src.config import load_bees_config, BeesConfig, HiveConfig, save_bees_config


@pytest.fixture
def setup_test_hive(tmp_path, monkeypatch):
    """Set up an isolated test hive environment."""
    # Change to tmp_path so all operations are isolated
    monkeypatch.chdir(tmp_path)
    
    # Create .bees directory
    bees_dir = tmp_path / ".bees"
    bees_dir.mkdir()
    
    # Create backend hive directory
    hive_path = tmp_path / "tickets"
    hive_path.mkdir()
    
    # Create hive marker
    marker_path = hive_path / ".hive"
    marker_path.mkdir()
    identity_file = marker_path / "identity.json"
    import json
    with open(identity_file, 'w') as f:
        json.dump({
            "normalized_name": "backend",
            "display_name": "Backend",
            "created_at": "2024-01-01T00:00:00",
            "version": "1.0.0"
        }, f)
    
    # Create and save config
    config = BeesConfig(
        hives={
            "backend": HiveConfig(
                display_name="Backend",
                path=str(hive_path),
                created_at="2024-01-01T00:00:00"
            )
        }
    )
    save_bees_config(config)
    
    return hive_path


class TestShowTicket:
    """Tests for the show_ticket MCP command."""

    async def test_show_ticket_epic(self, setup_test_hive):
        """Test showing an epic ticket."""
        # Create a test epic
        ticket_id = create_epic(
            title="Test Epic",
            description="Epic description",
            labels=["test", "epic"],
            owner="tester",
            priority=1,
            status="open",
            hive_name="backend"
        )

        # Show the ticket
        result = await _show_ticket(ticket_id)

        # Verify result structure
        assert result["status"] == "success"
        assert result["ticket_id"] == ticket_id
        assert result["ticket_type"] == "epic"
        assert result["title"] == "Test Epic"
        assert result["description"] == "Epic description"
        assert result["labels"] == ["test", "epic"]
        assert result["owner"] == "tester"
        assert result["priority"] == 1
        assert result["ticket_status"] == "open"
        assert result["parent"] is None
        assert result["children"] is None or result["children"] == []
        assert result["created_at"] is not None
        assert result["updated_at"] is not None
        assert result["bees_version"] is not None  # Version varies by config

    async def test_show_ticket_task(self, setup_test_hive):
        """Test showing a task ticket."""
        # Create an epic first (as parent)
        epic_id = create_epic(
            title="Parent Epic",
            hive_name="backend"
        )

        # Create a task
        task_id = create_task(
            title="Test Task",
            description="Task description",
            parent=epic_id,
            labels=["backend"],
            status="in_progress",
            hive_name="backend"
        )

        # Show the task
        result = await _show_ticket(task_id)

        # Verify result
        assert result["status"] == "success"
        assert result["ticket_id"] == task_id
        assert result["ticket_type"] == "task"
        assert result["title"] == "Test Task"
        assert result["description"] == "Task description"
        assert result["parent"] == epic_id
        assert result["ticket_status"] == "in_progress"

    async def test_show_ticket_nonexistent(self, setup_test_hive):
        """Test showing a ticket that doesn't exist."""
        with pytest.raises(ValueError, match="Ticket does not exist"):
            await _show_ticket("backend.bees-9999")

    async def test_show_ticket_empty_id(self, setup_test_hive):
        """Test showing a ticket with empty ID."""
        with pytest.raises(ValueError, match="ticket_id cannot be empty"):
            await _show_ticket("")

    async def test_show_ticket_malformed_id(self, setup_test_hive):
        """Test showing a ticket with malformed ID (no hive prefix)."""
        with pytest.raises(ValueError, match="Malformed ticket ID"):
            await _show_ticket("bees-abc1")

    async def test_show_ticket_invalid_hive(self, setup_test_hive):
        """Test showing a ticket from non-existent hive."""
        with pytest.raises(ValueError, match="not found in configuration"):
            await _show_ticket("nonexistent.bees-abc1")

    async def test_show_ticket_with_dependencies(self, setup_test_hive):
        """Test showing a ticket with dependencies."""
        # Create blocking ticket
        blocking_id = create_task(
            title="Blocking Task",
            hive_name="backend"
        )

        # Create ticket with dependency
        ticket_id = create_task(
            title="Dependent Task",
            up_dependencies=[blocking_id],
            hive_name="backend"
        )

        # Show the ticket
        result = await _show_ticket(ticket_id)

        # Verify dependencies are included
        assert result["up_dependencies"] == [blocking_id]
        assert blocking_id in result["up_dependencies"]

    async def test_show_ticket_preserves_all_fields(self, setup_test_hive):
        """Test that show_ticket returns all ticket fields."""
        # Create a ticket with many fields set
        ticket_id = create_epic(
            title="Full Epic",
            description="Detailed description",
            labels=["label1", "label2", "label3"],
            owner="john_doe",
            priority=3,
            status="in_progress",
            hive_name="backend"
        )

        result = await _show_ticket(ticket_id)

        # Verify all expected fields are present
        expected_fields = [
            "status", "ticket_id", "ticket_type", "title", "description",
            "labels", "parent", "children", "up_dependencies", "down_dependencies",
            "owner", "priority", "ticket_status", "created_at", "updated_at",
            "created_by", "bees_version"
        ]

        for field in expected_fields:
            assert field in result, f"Missing field: {field}"

    async def test_show_ticket_datetime_serialization(self, setup_test_hive):
        """Test that datetime fields are properly serialized to ISO format."""
        ticket_id = create_epic(
            title="Time Test",
            hive_name="backend"
        )

        result = await _show_ticket(ticket_id)

        # Verify datetime fields are ISO formatted strings
        assert isinstance(result["created_at"], str)
        assert isinstance(result["updated_at"], str)

        # Verify they can be parsed back to datetime
        datetime.fromisoformat(result["created_at"])
        datetime.fromisoformat(result["updated_at"])
