"""Unit tests for create_ticket() hive validation logic (Task bees-uol2, Subtask bees-r32n)."""

import pytest
from pathlib import Path
import json
import shutil

from src.mcp_server import _create_ticket
from src.config import init_bees_config_if_needed


# Removed temp_hive_setup fixture - now using multi_hive from conftest.py


class TestCreateTicketHiveValidation:
    """Tests for create_ticket() hive validation logic."""

    async def test_create_ticket_with_valid_hive_succeeds(self, multi_hive, monkeypatch):
        """Should create ticket when hive exists in config."""
        repo_root, backend_dir, frontend_dir = multi_hive
        monkeypatch.chdir(repo_root)
        
        result = await _create_ticket(
            ticket_type="epic",
            title="Test Epic",
            hive_name="backend"
        )

        assert result["status"] == "success"
        assert result["ticket_id"].startswith("backend.bees-")

        # Verify file was created in correct hive directory
        ticket_files = list(backend_dir.glob("*.md"))
        assert len(ticket_files) == 1
        assert ticket_files[0].name.startswith("backend.bees-")

    async def test_create_ticket_with_nonexistent_hive_raises_error(self, multi_hive, monkeypatch):
        """Should raise ValueError when hive does not exist in config."""
        repo_root, backend_dir, frontend_dir = multi_hive
        monkeypatch.chdir(repo_root)
        
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(
                ticket_type="epic",
                title="Test Epic",
                hive_name="nonexistent"
            )

        assert "not found in config" in str(exc_info.value)
        assert "nonexistent" in str(exc_info.value)

    async def test_create_ticket_validates_normalized_hive_name(self, multi_hive, monkeypatch):
        """Should validate hive exists after normalizing hive_name."""
        repo_root, backend_dir, frontend_dir = multi_hive
        monkeypatch.chdir(repo_root)
        
        # "BackEnd" normalizes to "backend" which exists in config
        result = await _create_ticket(
            ticket_type="epic",
            title="Test Epic",
            hive_name="BackEnd"  # Should normalize to "backend"
        )

        assert result["status"] == "success"
        assert result["ticket_id"].startswith("backend.bees-")

    async def test_create_ticket_with_unnormalized_nonexistent_hive_fails(self, multi_hive, monkeypatch):
        """Should fail validation when normalized hive_name doesn't exist."""
        repo_root, backend_dir, frontend_dir = multi_hive
        monkeypatch.chdir(repo_root)
        
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(
                ticket_type="epic",
                title="Test Epic",
                hive_name="Other Hive"  # Normalizes to "other_hive" which doesn't exist
            )

        assert "not found in config" in str(exc_info.value)
        assert "other_hive" in str(exc_info.value)

    async def test_create_ticket_routes_to_correct_hive_directory(self, multi_hive, monkeypatch):
        """Should store tickets in the correct hive directory from config."""
        repo_root, backend_dir, frontend_dir = multi_hive
        monkeypatch.chdir(repo_root)
        
        # Create ticket in backend hive
        backend_result = await _create_ticket(
            ticket_type="epic",
            title="Backend Epic",
            hive_name="backend"
        )

        # Create ticket in frontend hive
        frontend_result = await _create_ticket(
            ticket_type="epic",
            title="Frontend Epic",
            hive_name="frontend"
        )

        # Verify backend ticket is in backend directory
        backend_files = list(backend_dir.glob("*.md"))
        assert len(backend_files) == 1
        assert backend_result["ticket_id"] in backend_files[0].name

        # Verify frontend ticket is in frontend directory
        frontend_files = list(frontend_dir.glob("*.md"))
        assert len(frontend_files) == 1
        assert frontend_result["ticket_id"] in frontend_files[0].name

    async def test_create_ticket_with_multiple_hives(self, multi_hive, monkeypatch):
        """Should support creating tickets in different hives."""
        repo_root, backend_dir, frontend_dir = multi_hive
        monkeypatch.chdir(repo_root)
        
        # Create 3 tickets in backend
        for i in range(3):
            result = await _create_ticket(
                ticket_type="epic",
                title=f"Backend Epic {i}",
                hive_name="backend"
            )
            assert result["status"] == "success"
            assert result["ticket_id"].startswith("backend.bees-")

        # Create 2 tickets in frontend
        for i in range(2):
            result = await _create_ticket(
                ticket_type="epic",
                title=f"Frontend Epic {i}",
                hive_name="frontend"
            )
            assert result["status"] == "success"
            assert result["ticket_id"].startswith("frontend.bees-")

        # Verify counts in each hive
        backend_files = list(backend_dir.glob("*.md"))
        assert len(backend_files) == 3

        frontend_files = list(frontend_dir.glob("*.md"))
        assert len(frontend_files) == 2

    async def test_ticket_id_format_includes_hive_prefix(self, multi_hive, monkeypatch):
        """Generated ticket IDs should follow format: {hive}.bees-{random}."""
        repo_root, backend_dir, frontend_dir = multi_hive
        monkeypatch.chdir(repo_root)
        
        result = await _create_ticket(
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

    async def test_error_message_suggests_creating_hive(self, multi_hive, monkeypatch):
        """Error message should suggest using colonize_hive."""
        repo_root, backend_dir, frontend_dir = multi_hive
        monkeypatch.chdir(repo_root)
        
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(
                ticket_type="epic",
                title="Test Epic",
                hive_name="newHive"
            )

        error_msg = str(exc_info.value)
        assert "not found in config" in error_msg
        assert "create the hive first" in error_msg.lower() or "colonize_hive" in error_msg
        # Verify enhanced error message mentions colonize_hive and registration
        assert "colonize_hive" in error_msg

    async def test_all_ticket_types_validate_hive(self, multi_hive, monkeypatch):
        """All ticket types should validate hive exists in config."""
        repo_root, backend_dir, frontend_dir = multi_hive
        monkeypatch.chdir(repo_root)
        
        # Epic with nonexistent hive
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(
                ticket_type="epic",
                title="Epic",
                hive_name="nonexistent"
            )
        assert "not found in config" in str(exc_info.value)

        # Task with nonexistent hive
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(
                ticket_type="task",
                title="Task",
                hive_name="nonexistent"
            )
        assert "not found in config" in str(exc_info.value)

        # Create valid parent for subtask test
        parent_result = await _create_ticket(
            ticket_type="task",
            title="Parent",
            hive_name="backend"
        )

        # Subtask with nonexistent hive
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(
                ticket_type="subtask",
                title="Subtask",
                parent=parent_result["ticket_id"],
                hive_name="nonexistent"
            )
        assert "not found in config" in str(exc_info.value)

    async def test_create_ticket_does_not_attempt_hive_recovery(self, multi_hive, monkeypatch):
        """
        Design Decision Test: create_ticket should be STRICT and not attempt hive recovery.

        This test verifies that _create_ticket fails fast without attempting scan_for_hive
        recovery, maintaining consistency with update_ticket and delete_ticket operations.
        Write operations should be explicit and require hive to be registered in config.
        """
        repo_root, backend_dir, frontend_dir = multi_hive
        monkeypatch.chdir(repo_root)
        
        # Create an unregistered hive directory with proper .hive marker
        unregistered_dir = repo_root / "unregistered_hive"
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
            await _create_ticket(
                ticket_type="epic",
                title="Test Epic",
                hive_name="unregistered_hive"
            )

        error_msg = str(exc_info.value)
        # Should fail with config error, not attempt recovery
        assert "not found in config" in error_msg
        assert "colonize_hive" in error_msg
        # Error message should guide user to register hive if it exists
        assert "run colonize_hive to register it" in error_msg

    async def test_error_message_guides_unregistered_hive_scenario(self, multi_hive, monkeypatch):
        """Error message should guide users when hive directory exists but isn't registered."""
        repo_root, backend_dir, frontend_dir = multi_hive
        monkeypatch.chdir(repo_root)
        
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(
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
    """Tests for hive path validation in await _create_ticket (Task bees-3c0ja)."""

    async def test_missing_hive_directory_raises_error(self, multi_hive, monkeypatch):
        """Should raise ValueError when hive path does not exist."""
        repo_root, backend_dir, frontend_dir = multi_hive
        monkeypatch.chdir(repo_root)
        
        # Delete backend directory
        shutil.rmtree(backend_dir)

        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(
                ticket_type="epic",
                title="Test Epic",
                hive_name="backend"
            )

        error_msg = str(exc_info.value)
        assert "does not exist" in error_msg
        assert str(backend_dir) in error_msg

    async def test_hive_path_is_file_not_directory_raises_error(self, multi_hive, monkeypatch):
        """Should raise ValueError when hive path is a file instead of directory."""
        repo_root, backend_dir, frontend_dir = multi_hive
        monkeypatch.chdir(repo_root)
        
        # Replace backend directory with a file
        shutil.rmtree(backend_dir)
        backend_dir.touch()  # Create as file instead

        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(
                ticket_type="epic",
                title="Test Epic",
                hive_name="backend"
            )

        error_msg = str(exc_info.value)
        assert "not a directory" in error_msg

    async def test_non_writable_hive_directory_raises_error(self, multi_hive, monkeypatch):
        """Should raise ValueError when hive directory is not writable."""
        import os
        import stat

        repo_root, backend_dir, frontend_dir = multi_hive
        monkeypatch.chdir(repo_root)

        # Make directory read-only
        original_mode = backend_dir.stat().st_mode
        backend_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)

        try:
            with pytest.raises(ValueError) as exc_info:
                await _create_ticket(
                    ticket_type="epic",
                    title="Test Epic",
                    hive_name="backend"
                )

            error_msg = str(exc_info.value)
            assert "not writable" in error_msg or "permission" in error_msg.lower()
        finally:
            # Restore permissions for cleanup
            backend_dir.chmod(original_mode)

    async def test_valid_symlink_to_directory_succeeds(self, multi_hive, monkeypatch):
        """Should succeed when hive path is a valid symlink to a directory."""
        repo_root, backend_dir, frontend_dir = multi_hive
        monkeypatch.chdir(repo_root)
        
        # Create actual target directory
        target_dir = repo_root / "backend_target"
        target_dir.mkdir()

        # Replace backend_dir with symlink
        shutil.rmtree(backend_dir)
        backend_dir.symlink_to(target_dir)

        # Update config to point to symlink
        config_path = repo_root / ".bees" / "config.json"
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        config_data["hives"]["backend"]["path"] = str(backend_dir)
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)

        # Should succeed - symlink is valid
        result = await _create_ticket(
            ticket_type="epic",
            title="Test Epic",
            hive_name="backend"
        )

        assert result["status"] == "success"
        # Verify file was created in target directory
        assert len(list(target_dir.glob("*.md"))) == 1

    async def test_broken_symlink_raises_error(self, multi_hive, monkeypatch):
        """Should raise ValueError when hive path is a broken symlink."""
        repo_root, backend_dir, frontend_dir = multi_hive
        monkeypatch.chdir(repo_root)
        
        # Create symlink pointing to nonexistent directory
        target_dir = repo_root / "backend_target_missing"
        shutil.rmtree(backend_dir)
        backend_dir.symlink_to(target_dir)

        # Update config
        config_path = repo_root / ".bees" / "config.json"
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        config_data["hives"]["backend"]["path"] = str(backend_dir)
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)

        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(
                ticket_type="epic",
                title="Test Epic",
                hive_name="backend"
            )

        error_msg = str(exc_info.value)
        assert "does not exist" in error_msg

    async def test_successful_path_validation_for_valid_directory(self, multi_hive, monkeypatch):
        """Should pass all validations for existing writable directory."""
        repo_root, backend_dir, frontend_dir = multi_hive
        monkeypatch.chdir(repo_root)
        
        # This test verifies the happy path with all validations passing
        result = await _create_ticket(
            ticket_type="epic",
            title="Test Epic",
            hive_name="backend"
        )

        assert result["status"] == "success"

        # Verify ticket file was created
        ticket_files = list(backend_dir.glob("*.md"))
        assert len(ticket_files) == 1

    async def test_error_messages_are_descriptive(self, multi_hive, monkeypatch):
        """Error messages should be clear and actionable."""
        repo_root, backend_dir, frontend_dir = multi_hive
        monkeypatch.chdir(repo_root)
        
        # Test 1: Missing directory
        shutil.rmtree(backend_dir)
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(
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
            await _create_ticket(
                ticket_type="epic",
                title="Test",
                hive_name="backend"
            )
        assert "not a directory" in str(exc_info.value)
