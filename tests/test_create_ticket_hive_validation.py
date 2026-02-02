"""Unit tests for create_ticket() hive validation logic (Task bees-uol2, Subtask bees-r32n)."""

import pytest
from pathlib import Path
import tempfile
import shutil
import json

from src.mcp_server import _create_ticket
from src.config import init_bees_config_if_needed


@pytest.fixture
def temp_hive_setup():
    """Create temporary hive with proper config setup."""
    temp_dir = Path(tempfile.mkdtemp())

    # Create backend hive directory
    backend_dir = temp_dir / "backend"
    backend_dir.mkdir()

    # Create frontend hive directory
    frontend_dir = temp_dir / "frontend"
    frontend_dir.mkdir()

    # Create .bees config directory
    bees_config_dir = temp_dir / ".bees"
    bees_config_dir.mkdir()

    # Create config.json with registered hives
    config_data = {
        "hives": {
            "backend": {
                "path": str(backend_dir),
                "display_name": "Backend",
                "created_at": "2026-02-02T10:00:00"
            },
            "frontend": {
                "path": str(frontend_dir),
                "display_name": "Frontend",
                "created_at": "2026-02-02T10:00:00"
            }
        }
    }

    config_path = bees_config_dir / "config.json"
    with open(config_path, 'w') as f:
        json.dump(config_data, f, indent=2)

    # Change to temp directory so config can be loaded
    import os
    original_cwd = os.getcwd()
    os.chdir(temp_dir)

    yield {
        "temp_dir": temp_dir,
        "backend_dir": backend_dir,
        "frontend_dir": frontend_dir,
        "config_path": config_path
    }

    # Restore original directory and cleanup
    os.chdir(original_cwd)
    shutil.rmtree(temp_dir)


class TestCreateTicketHiveValidation:
    """Tests for create_ticket() hive validation logic."""

    def test_create_ticket_with_valid_hive_succeeds(self, temp_hive_setup):
        """Should create ticket when hive exists in config."""
        result = _create_ticket(
            ticket_type="epic",
            title="Test Epic",
            hive_name="backend"
        )

        assert result["status"] == "success"
        assert result["ticket_id"].startswith("backend.bees-")

        # Verify file was created in correct hive directory
        backend_dir = temp_hive_setup["backend_dir"]
        ticket_files = list(backend_dir.glob("*.md"))
        assert len(ticket_files) == 1
        assert ticket_files[0].name.startswith("backend.bees-")

    def test_create_ticket_with_nonexistent_hive_raises_error(self, temp_hive_setup):
        """Should raise ValueError when hive does not exist in config."""
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Test Epic",
                hive_name="nonexistent"
            )

        assert "does not exist in config" in str(exc_info.value)
        assert "nonexistent" in str(exc_info.value)

    def test_create_ticket_validates_normalized_hive_name(self, temp_hive_setup):
        """Should validate hive exists after normalizing hive_name."""
        # "BackEnd" normalizes to "backend" which exists in config
        result = _create_ticket(
            ticket_type="epic",
            title="Test Epic",
            hive_name="BackEnd"  # Should normalize to "backend"
        )

        assert result["status"] == "success"
        assert result["ticket_id"].startswith("backend.bees-")

    def test_create_ticket_with_unnormalized_nonexistent_hive_fails(self, temp_hive_setup):
        """Should fail validation when normalized hive_name doesn't exist."""
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Test Epic",
                hive_name="Other Hive"  # Normalizes to "other_hive" which doesn't exist
            )

        assert "does not exist in config" in str(exc_info.value)
        assert "other_hive" in str(exc_info.value)

    def test_create_ticket_routes_to_correct_hive_directory(self, temp_hive_setup):
        """Should store tickets in the correct hive directory from config."""
        # Create ticket in backend hive
        backend_result = _create_ticket(
            ticket_type="epic",
            title="Backend Epic",
            hive_name="backend"
        )

        # Create ticket in frontend hive
        frontend_result = _create_ticket(
            ticket_type="epic",
            title="Frontend Epic",
            hive_name="frontend"
        )

        # Verify backend ticket is in backend directory
        backend_dir = temp_hive_setup["backend_dir"]
        backend_files = list(backend_dir.glob("*.md"))
        assert len(backend_files) == 1
        assert backend_result["ticket_id"] in backend_files[0].name

        # Verify frontend ticket is in frontend directory
        frontend_dir = temp_hive_setup["frontend_dir"]
        frontend_files = list(frontend_dir.glob("*.md"))
        assert len(frontend_files) == 1
        assert frontend_result["ticket_id"] in frontend_files[0].name

    def test_create_ticket_with_multiple_hives(self, temp_hive_setup):
        """Should support creating tickets in different hives."""
        # Create 3 tickets in backend
        for i in range(3):
            result = _create_ticket(
                ticket_type="epic",
                title=f"Backend Epic {i}",
                hive_name="backend"
            )
            assert result["status"] == "success"
            assert result["ticket_id"].startswith("backend.bees-")

        # Create 2 tickets in frontend
        for i in range(2):
            result = _create_ticket(
                ticket_type="epic",
                title=f"Frontend Epic {i}",
                hive_name="frontend"
            )
            assert result["status"] == "success"
            assert result["ticket_id"].startswith("frontend.bees-")

        # Verify counts in each hive
        backend_dir = temp_hive_setup["backend_dir"]
        backend_files = list(backend_dir.glob("*.md"))
        assert len(backend_files) == 3

        frontend_dir = temp_hive_setup["frontend_dir"]
        frontend_files = list(frontend_dir.glob("*.md"))
        assert len(frontend_files) == 2

    def test_ticket_id_format_includes_hive_prefix(self, temp_hive_setup):
        """Generated ticket IDs should follow format: {hive}.bees-{random}."""
        result = _create_ticket(
            ticket_type="epic",
            title="Test Epic",
            hive_name="backend"
        )

        ticket_id = result["ticket_id"]

        # Should match format: backend.bees-abc
        assert "." in ticket_id
        hive_prefix, base_id = ticket_id.split(".", 1)
        assert hive_prefix == "backend"
        assert base_id.startswith("bees-")
        assert len(base_id) == 8  # "bees-" (5) + 3 random chars

    def test_error_message_suggests_creating_hive(self, temp_hive_setup):
        """Error message should suggest using colonize_hive."""
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Test Epic",
                hive_name="newHive"
            )

        error_msg = str(exc_info.value)
        assert "does not exist in config" in error_msg
        assert "create the hive first" in error_msg.lower() or "colonize_hive" in error_msg
        # Verify enhanced error message mentions colonize_hive and registration
        assert "colonize_hive" in error_msg

    def test_all_ticket_types_validate_hive(self, temp_hive_setup):
        """All ticket types should validate hive exists in config."""
        # Epic with nonexistent hive
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Epic",
                hive_name="nonexistent"
            )
        assert "does not exist in config" in str(exc_info.value)

        # Task with nonexistent hive
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="task",
                title="Task",
                hive_name="nonexistent"
            )
        assert "does not exist in config" in str(exc_info.value)

        # Create valid parent for subtask test
        parent_result = _create_ticket(
            ticket_type="task",
            title="Parent",
            hive_name="backend"
        )

        # Subtask with nonexistent hive
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="subtask",
                title="Subtask",
                parent=parent_result["ticket_id"],
                hive_name="nonexistent"
            )
        assert "does not exist in config" in str(exc_info.value)

    def test_create_ticket_does_not_attempt_hive_recovery(self, temp_hive_setup):
        """
        Design Decision Test: create_ticket should be STRICT and not attempt hive recovery.

        This test verifies that _create_ticket fails fast without attempting scan_for_hive
        recovery, maintaining consistency with update_ticket and delete_ticket operations.
        Write operations should be explicit and require hive to be registered in config.
        """
        # Create an unregistered hive directory with proper .hive marker
        temp_dir = temp_hive_setup["temp_dir"]
        unregistered_dir = temp_dir / "unregistered_hive"
        unregistered_dir.mkdir()

        # Create .hive marker to simulate a relocated hive that scan_for_hive could find
        hive_marker_dir = unregistered_dir / ".hive"
        hive_marker_dir.mkdir()
        identity_file = hive_marker_dir / "identity.json"
        with open(identity_file, 'w') as f:
            json.dump({"normalized_name": "unregistered_hive"}, f)

        # Attempt to create ticket in unregistered hive
        # Should fail fast WITHOUT attempting scan_for_hive recovery
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Test Epic",
                hive_name="unregistered_hive"
            )

        error_msg = str(exc_info.value)
        # Should fail with config error, not attempt recovery
        assert "does not exist in config" in error_msg
        assert "colonize_hive" in error_msg
        # Error message should guide user to register hive if it exists
        assert "run colonize_hive to register it" in error_msg

    def test_error_message_guides_unregistered_hive_scenario(self, temp_hive_setup):
        """Error message should guide users when hive directory exists but isn't registered."""
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Test Epic",
                hive_name="unregistered"
            )

        error_msg = str(exc_info.value)
        # Should mention colonize_hive for registration
        assert "colonize_hive" in error_msg
        # Should guide users who have existing directories
        assert "register" in error_msg.lower()


class TestCreateTicketHivePathValidation:
    """Tests for hive path validation in _create_ticket (Task bees-3c0ja)."""

    def test_missing_hive_directory_raises_error(self, temp_hive_setup):
        """Should raise ValueError when hive path does not exist."""
        # Delete backend directory
        backend_dir = temp_hive_setup["backend_dir"]
        shutil.rmtree(backend_dir)

        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Test Epic",
                hive_name="backend"
            )

        error_msg = str(exc_info.value)
        assert "does not exist" in error_msg
        assert str(backend_dir) in error_msg

    def test_hive_path_is_file_not_directory_raises_error(self, temp_hive_setup):
        """Should raise ValueError when hive path is a file instead of directory."""
        # Replace backend directory with a file
        backend_dir = temp_hive_setup["backend_dir"]
        shutil.rmtree(backend_dir)
        backend_dir.touch()  # Create as file instead

        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Test Epic",
                hive_name="backend"
            )

        error_msg = str(exc_info.value)
        assert "not a directory" in error_msg

    def test_non_writable_hive_directory_raises_error(self, temp_hive_setup):
        """Should raise ValueError when hive directory is not writable."""
        import os
        import stat

        backend_dir = temp_hive_setup["backend_dir"]

        # Make directory read-only
        original_mode = backend_dir.stat().st_mode
        backend_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)

        try:
            with pytest.raises(ValueError) as exc_info:
                _create_ticket(
                    ticket_type="epic",
                    title="Test Epic",
                    hive_name="backend"
                )

            error_msg = str(exc_info.value)
            assert "not writable" in error_msg or "permission" in error_msg.lower()
        finally:
            # Restore permissions for cleanup
            backend_dir.chmod(original_mode)

    def test_valid_symlink_to_directory_succeeds(self, temp_hive_setup):
        """Should succeed when hive path is a valid symlink to a directory."""
        backend_dir = temp_hive_setup["backend_dir"]
        temp_dir = temp_hive_setup["temp_dir"]

        # Create actual target directory
        target_dir = temp_dir / "backend_target"
        target_dir.mkdir()

        # Replace backend_dir with symlink
        shutil.rmtree(backend_dir)
        backend_dir.symlink_to(target_dir)

        # Update config to point to symlink
        config_path = temp_hive_setup["config_path"]
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        config_data["hives"]["backend"]["path"] = str(backend_dir)
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)

        # Should succeed - symlink is valid
        result = _create_ticket(
            ticket_type="epic",
            title="Test Epic",
            hive_name="backend"
        )

        assert result["status"] == "success"
        # Verify file was created in target directory
        assert len(list(target_dir.glob("*.md"))) == 1

    def test_broken_symlink_raises_error(self, temp_hive_setup):
        """Should raise ValueError when hive path is a broken symlink."""
        backend_dir = temp_hive_setup["backend_dir"]
        temp_dir = temp_hive_setup["temp_dir"]

        # Create symlink pointing to nonexistent directory
        target_dir = temp_dir / "backend_target_missing"
        shutil.rmtree(backend_dir)
        backend_dir.symlink_to(target_dir)

        # Update config
        config_path = temp_hive_setup["config_path"]
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        config_data["hives"]["backend"]["path"] = str(backend_dir)
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)

        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Test Epic",
                hive_name="backend"
            )

        error_msg = str(exc_info.value)
        assert "does not exist" in error_msg

    def test_successful_path_validation_for_valid_directory(self, temp_hive_setup):
        """Should pass all validations for existing writable directory."""
        # This test verifies the happy path with all validations passing
        result = _create_ticket(
            ticket_type="epic",
            title="Test Epic",
            hive_name="backend"
        )

        assert result["status"] == "success"

        # Verify ticket file was created
        backend_dir = temp_hive_setup["backend_dir"]
        ticket_files = list(backend_dir.glob("*.md"))
        assert len(ticket_files) == 1

    def test_error_messages_are_descriptive(self, temp_hive_setup):
        """Error messages should be clear and actionable."""
        backend_dir = temp_hive_setup["backend_dir"]

        # Test 1: Missing directory
        shutil.rmtree(backend_dir)
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Test",
                hive_name="backend"
            )
        assert "does not exist" in str(exc_info.value)
        assert "create the directory" in str(exc_info.value).lower()

        # Restore directory for next test
        backend_dir.mkdir()

        # Test 2: Not a directory
        shutil.rmtree(backend_dir)
        backend_dir.touch()
        with pytest.raises(ValueError) as exc_info:
            _create_ticket(
                ticket_type="epic",
                title="Test",
                hive_name="backend"
            )
        assert "not a directory" in str(exc_info.value)
