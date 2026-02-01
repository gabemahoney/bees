"""Unit tests for update_ticket and delete_ticket with hive-prefixed IDs.

Tests that update_ticket() and delete_ticket() automatically infer hive from ticket ID
without requiring explicit hive_name parameter.
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from src.mcp_server import _create_ticket, _update_ticket, _delete_ticket
from src.reader import read_ticket
from src.paths import get_ticket_path, infer_ticket_type_from_id


@pytest.fixture
def temp_tickets_dir():
    """Create temporary tickets directory."""
    temp_dir = Path(tempfile.mkdtemp())
    tickets_dir = temp_dir / "tickets"
    tickets_dir.mkdir()
    (tickets_dir / "epics").mkdir()
    (tickets_dir / "tasks").mkdir()
    (tickets_dir / "subtasks").mkdir()

    # Create backend hive directories
    backend_dir = temp_dir / "backend"
    backend_dir.mkdir()
    (backend_dir / "epics").mkdir()
    (backend_dir / "tasks").mkdir()
    (backend_dir / "subtasks").mkdir()

    # Create frontend hive directories
    frontend_dir = temp_dir / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "epics").mkdir()
    (frontend_dir / "tasks").mkdir()
    (frontend_dir / "subtasks").mkdir()

    # Temporarily override TICKETS_DIR and change working directory
    import src.paths
    import os
    original_tickets_dir = src.paths.TICKETS_DIR
    original_cwd = os.getcwd()

    src.paths.TICKETS_DIR = tickets_dir
    os.chdir(temp_dir)

    yield temp_dir

    # Restore original and cleanup
    os.chdir(original_cwd)
    src.paths.TICKETS_DIR = original_tickets_dir
    shutil.rmtree(temp_dir)


class TestUpdateTicketHiveInference:
    """Tests that update_ticket() infers hive from ticket ID."""

    def test_update_legacy_ticket_without_hive(self, temp_tickets_dir):
        """Should update ticket in default hive correctly."""
        # Create ticket in default hive
        create_result = _create_ticket(
            ticket_type="epic",
            title="Original Title",
            hive_name="default"
        )
        ticket_id = create_result["ticket_id"]
        assert ticket_id.startswith("default.bees-")

        # Update the ticket
        update_result = _update_ticket(
            ticket_id=ticket_id,
            title="Updated Title"
        )

        assert update_result["status"] == "success"
        assert update_result["ticket_id"] == ticket_id

        # Verify update was applied
        ticket_path = get_ticket_path(ticket_id, "epic")
        updated_ticket = read_ticket(ticket_path)
        assert updated_ticket.title == "Updated Title"

    def test_update_hive_prefixed_ticket(self, temp_tickets_dir):
        """Should update hive-prefixed ticket by inferring hive from ID."""
        # Create ticket with hive
        create_result = _create_ticket(
            ticket_type="epic",
            title="Original Title",
            hive_name="backend"
        )
        ticket_id = create_result["ticket_id"]
        assert ticket_id.startswith("backend.bees-")

        # Update the ticket - no hive_name parameter needed
        update_result = _update_ticket(
            ticket_id=ticket_id,
            title="Updated Title"
        )

        assert update_result["status"] == "success"
        assert update_result["ticket_id"] == ticket_id

        # Verify update was applied to correct hive directory
        ticket_path = get_ticket_path(ticket_id, "epic")
        updated_ticket = read_ticket(ticket_path)
        assert updated_ticket.title == "Updated Title"
        assert updated_ticket.id == ticket_id

    def test_update_different_hives(self, temp_tickets_dir):
        """Should update tickets in different hives correctly."""
        # Create tickets in different hives
        backend_result = _create_ticket(
            ticket_type="epic",
            title="Backend Epic",
            hive_name="backend"
        )
        backend_id = backend_result["ticket_id"]

        frontend_result = _create_ticket(
            ticket_type="epic",
            title="Frontend Epic",
            hive_name="frontend"
        )
        frontend_id = frontend_result["ticket_id"]

        # Update both tickets
        _update_ticket(backend_id, title="Updated Backend")
        _update_ticket(frontend_id, title="Updated Frontend")

        # Verify both were updated correctly
        backend_ticket = read_ticket(get_ticket_path(backend_id, "epic"))
        assert backend_ticket.title == "Updated Backend"

        frontend_ticket = read_ticket(get_ticket_path(frontend_id, "epic"))
        assert frontend_ticket.title == "Updated Frontend"

    def test_update_with_relationships_in_hive(self, temp_tickets_dir):
        """Should handle relationship updates with hive-prefixed IDs."""
        # Create parent and child in backend hive
        parent_result = _create_ticket(
            ticket_type="epic",
            title="Parent Epic",
            hive_name="backend"
        )
        parent_id = parent_result["ticket_id"]

        child_result = _create_ticket(
            ticket_type="task",
            title="Child Task",
            parent=parent_id,
            hive_name="backend"
        )
        child_id = child_result["ticket_id"]

        # Update child's description
        _update_ticket(child_id, description="Updated description")

        # Verify update
        child_ticket = read_ticket(get_ticket_path(child_id, "task"))
        assert child_ticket.description == "Updated description"
        assert child_ticket.parent == parent_id


class TestDeleteTicketHiveInference:
    """Tests that delete_ticket() infers hive from ticket ID."""

    def test_delete_legacy_ticket_without_hive(self, temp_tickets_dir):
        """Should delete ticket in default hive correctly."""
        # Create ticket in default hive
        create_result = _create_ticket(
            ticket_type="epic",
            title="Test Epic",
            hive_name="default"
        )
        ticket_id = create_result["ticket_id"]
        assert ticket_id.startswith("default.bees-")

        # Verify ticket exists
        ticket_path = get_ticket_path(ticket_id, "epic")
        assert ticket_path.exists()

        # Delete the ticket
        delete_result = _delete_ticket(ticket_id=ticket_id)

        assert delete_result["status"] == "success"
        assert delete_result["ticket_id"] == ticket_id

        # Verify ticket was deleted
        assert not ticket_path.exists()

    def test_delete_hive_prefixed_ticket(self, temp_tickets_dir):
        """Should delete hive-prefixed ticket by inferring hive from ID."""
        # Create ticket with hive
        create_result = _create_ticket(
            ticket_type="epic",
            title="Backend Epic",
            hive_name="backend"
        )
        ticket_id = create_result["ticket_id"]
        assert ticket_id.startswith("backend.bees-")

        # Verify ticket exists
        ticket_path = get_ticket_path(ticket_id, "epic")
        assert ticket_path.exists()

        # Delete the ticket - no hive_name parameter needed
        delete_result = _delete_ticket(ticket_id=ticket_id)

        assert delete_result["status"] == "success"
        assert delete_result["ticket_id"] == ticket_id

        # Verify ticket was deleted from correct hive directory
        assert not ticket_path.exists()

    def test_delete_from_different_hives(self, temp_tickets_dir):
        """Should delete tickets from different hives correctly."""
        # Create tickets in different hives
        backend_result = _create_ticket(
            ticket_type="epic",
            title="Backend Epic",
            hive_name="backend"
        )
        backend_id = backend_result["ticket_id"]

        frontend_result = _create_ticket(
            ticket_type="epic",
            title="Frontend Epic",
            hive_name="frontend"
        )
        frontend_id = frontend_result["ticket_id"]

        # Delete backend ticket
        _delete_ticket(ticket_id=backend_id)

        # Verify backend deleted, frontend still exists
        assert not get_ticket_path(backend_id, "epic").exists()
        assert get_ticket_path(frontend_id, "epic").exists()

    def test_delete_with_cascade_in_hive(self, temp_tickets_dir):
        """Should handle cascade delete with hive-prefixed IDs."""
        # Create parent and children in backend hive
        parent_result = _create_ticket(
            ticket_type="epic",
            title="Parent Epic",
            hive_name="backend"
        )
        parent_id = parent_result["ticket_id"]

        child1_result = _create_ticket(
            ticket_type="task",
            title="Child Task 1",
            parent=parent_id,
            hive_name="backend"
        )
        child1_id = child1_result["ticket_id"]

        child2_result = _create_ticket(
            ticket_type="task",
            title="Child Task 2",
            parent=parent_id,
            hive_name="backend"
        )
        child2_id = child2_result["ticket_id"]

        # Verify all exist
        assert get_ticket_path(parent_id, "epic").exists()
        assert get_ticket_path(child1_id, "task").exists()
        assert get_ticket_path(child2_id, "task").exists()

        # Delete parent with cascade
        _delete_ticket(ticket_id=parent_id, cascade=True)

        # Verify all deleted
        assert not get_ticket_path(parent_id, "epic").exists()
        assert not get_ticket_path(child1_id, "task").exists()
        assert not get_ticket_path(child2_id, "task").exists()


class TestBackwardCompatibility:
    """Tests backward compatibility between legacy and hive-prefixed IDs."""

    def test_mixed_id_formats_in_system(self, temp_tickets_dir):
        """Should support multiple hive-prefixed IDs simultaneously."""
        # Create tickets in different hives
        default_epic = _create_ticket(
            ticket_type="epic",
            title="Default Epic",
            hive_name="default"
        )["ticket_id"]

        hive_epic = _create_ticket(
            ticket_type="epic",
            title="Hive Epic",
            hive_name="backend"
        )["ticket_id"]

        # Both should be valid
        assert default_epic.startswith("default.bees-")
        assert hive_epic.startswith("backend.bees-")

        # Both should be readable
        assert infer_ticket_type_from_id(default_epic) == "epic"
        assert infer_ticket_type_from_id(hive_epic) == "epic"

        # Both should be updatable
        _update_ticket(default_epic, title="Updated Default")
        _update_ticket(hive_epic, title="Updated Hive")

        # Both should be deletable
        _delete_ticket(ticket_id=default_epic)
        _delete_ticket(ticket_id=hive_epic)

        # Verify both deleted
        assert not get_ticket_path(default_epic, "epic").exists()
        assert not get_ticket_path(hive_epic, "epic").exists()

    def test_cross_hive_relationships(self, temp_tickets_dir):
        """Should support relationships between different hives."""
        # Create parent in default hive
        parent_result = _create_ticket(
            ticket_type="epic",
            title="Parent Epic",
            hive_name="default"
        )
        parent_id = parent_result["ticket_id"]

        # Create child in backend hive
        child_result = _create_ticket(
            ticket_type="task",
            title="Child Task",
            parent=parent_id,
            hive_name="backend"
        )
        child_id = child_result["ticket_id"]

        # Verify relationship works
        child_ticket = read_ticket(get_ticket_path(child_id, "task"))
        assert child_ticket.parent == parent_id

        # Update should work across hives
        _update_ticket(parent_id, title="Updated Parent")
        _update_ticket(child_id, title="Updated Child")

        # Verify updates
        parent_ticket = read_ticket(get_ticket_path(parent_id, "epic"))
        assert parent_ticket.title == "Updated Parent"

        child_ticket = read_ticket(get_ticket_path(child_id, "task"))
        assert child_ticket.title == "Updated Child"
