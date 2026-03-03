"""
Unit tests for hive renaming operations.

PURPOSE:
Tests the rename_hive MCP tool that updates hive names in config and .hive marker,
and optionally renames the hive folder on disk (rename_folder=True by default).
With the new ID system, hive names are NOT part of ticket IDs, so renaming a hive
only updates configuration, metadata, and optionally the folder - ticket files and
IDs remain unchanged.

SCOPE - Tests that belong here:
- _rename_hive(): Complete rename workflow
- Config updates (hive registry key changes, display name updates)
- .hive marker file updates (normalized_name and display_name)
- Folder rename on disk (rename_folder=True default, rename_folder=False opt-out)
- Validation: duplicate name detection, non-existent hive handling
- Error cases: path_conflict, folder_rename_error
- Edge cases: special characters, missing marker files

SCOPE - Tests that DON'T belong here:
- Hive creation -> test_colonize_hive.py
- Hive config management -> test_config.py, test_config_registration.py
- ID generation/parsing -> test_id_utils.py

KEY BEHAVIOR:
- Ticket files are NOT renamed (IDs don't contain hive names)
- Ticket IDs in frontmatter are NOT updated (globally unique)
- Cross-references are NOT updated (IDs don't change)
- Folder on disk IS renamed by default (rename_folder=True)
"""

import json
from datetime import datetime
from unittest.mock import patch

import pytest

from src.config import BeesConfig, HiveConfig, load_bees_config, save_bees_config
from src.mcp_hive_ops import _rename_hive
from src.repo_context import repo_root_context
from tests.test_constants import (
    RESULT_STATUS_SUCCESS,
    TICKET_ID_MCP_RENAME_TASK1,
    TICKET_ID_MCP_RENAME_TASK2,
    TICKET_ID_MCP_RENAME_TASK3,
)


@pytest.fixture
def temp_hive_setup(multi_hive_config):
    """Create temporary hive directories with test tickets using new ID format."""
    repo_root, hive_paths, config_data = multi_hive_config
    backend_dir, frontend_dir = hive_paths[0], hive_paths[1]

    # Create .git directory to make it a git repo (for tests that check git)
    git_dir = repo_root / ".git"
    git_dir.mkdir(exist_ok=True)

    # Update config
    with repo_root_context(repo_root):
        config = BeesConfig(
            hives={
                "backend": HiveConfig(path=str(backend_dir), display_name="Backend", created_at=datetime.now().isoformat()),
                "frontend": HiveConfig(
                    path=str(frontend_dir), display_name="Frontend", created_at=datetime.now().isoformat()
                ),
            },
            schema_version="1.0",
        )
        save_bees_config(config)

    # Create sample tickets in backend hive with NEW ID format (type-prefixed)
    ticket1_path = backend_dir / f"{TICKET_ID_MCP_RENAME_TASK1}.md"
    ticket1_path.write_text(f"""---
id: {TICKET_ID_MCP_RENAME_TASK1}
title: Test Ticket 1
type: t1
status: open
created_at: '2024-01-01T00:00:00'
schema_version: '0.1'
---
Test ticket 1 body
""")

    ticket2_path = backend_dir / f"{TICKET_ID_MCP_RENAME_TASK2}.md"
    ticket2_path.write_text(f"""---
id: {TICKET_ID_MCP_RENAME_TASK2}
title: Test Ticket 2
type: t1
status: open
parent: {TICKET_ID_MCP_RENAME_TASK1}
created_at: '2024-01-01T00:00:00'
schema_version: '0.1'
---
Test ticket 2 body
""")

    # Create ticket in frontend with cross-hive reference
    frontend_ticket = frontend_dir / f"{TICKET_ID_MCP_RENAME_TASK3}.md"
    frontend_ticket.write_text(f"""---
id: {TICKET_ID_MCP_RENAME_TASK3}
title: Frontend Ticket
type: t1
status: open
up_dependencies:
- {TICKET_ID_MCP_RENAME_TASK1}
- {TICKET_ID_MCP_RENAME_TASK2}
created_at: '2024-01-01T00:00:00'
schema_version: '0.1'
---
Frontend ticket body
""")

    # Create .hive marker directory with identity.json
    hive_marker_dir = backend_dir / ".hive"
    hive_marker_dir.mkdir(exist_ok=True)
    identity_file = hive_marker_dir / "identity.json"
    identity_file.write_text(
        json.dumps(
            {"normalized_name": "backend", "display_name": "Backend", "created_at": "2024-01-01T00:00:00"}, indent=2
        )
    )

    with repo_root_context(repo_root):
        yield repo_root, backend_dir, frontend_dir


class TestRenameHiveSuccess:
    """Tests for successful rename_hive() operations."""

    async def test_basic_rename_moves_folder_and_updates_config(self, temp_hive_setup):
        """Default rename_folder=True moves folder on disk and updates config path."""
        repo_root, backend_dir, frontend_dir = temp_hive_setup
        new_dir = repo_root / "api_layer"

        result = await _rename_hive("backend", "api_layer")

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["old_name"] == "backend"
        assert result["new_name"] == "api_layer"
        assert result["old_path"] == str(backend_dir)
        assert result["new_path"] == str(new_dir)

        # Folder moved on disk
        assert new_dir.exists()
        assert not backend_dir.exists()

        # Config points to new path
        config = load_bees_config()
        assert "backend" not in config.hives
        assert "api_layer" in config.hives
        assert config.hives["api_layer"].display_name == "api_layer"
        assert config.hives["api_layer"].path == str(new_dir)

    async def test_rename_preserves_ticket_filenames(self, temp_hive_setup):
        """Ticket files keep their names at new location (IDs don't contain hive names)."""
        repo_root, backend_dir, frontend_dir = temp_hive_setup
        new_dir = repo_root / "api_layer"

        result = await _rename_hive("backend", "api_layer")
        assert result["status"] == RESULT_STATUS_SUCCESS

        # Files exist at NEW location with SAME names
        assert (new_dir / f"{TICKET_ID_MCP_RENAME_TASK1}.md").exists()
        assert (new_dir / f"{TICKET_ID_MCP_RENAME_TASK2}.md").exists()

    async def test_rename_preserves_frontmatter_ids(self, temp_hive_setup):
        """Ticket IDs in frontmatter remain unchanged (globally unique IDs)."""
        repo_root, backend_dir, frontend_dir = temp_hive_setup
        new_dir = repo_root / "api_layer"

        result = await _rename_hive("backend", "api_layer")
        assert result["status"] == RESULT_STATUS_SUCCESS

        content = (new_dir / f"{TICKET_ID_MCP_RENAME_TASK1}.md").read_text()
        assert f"id: {TICKET_ID_MCP_RENAME_TASK1}" in content
        assert "api_layer" not in content

    async def test_rename_updates_hive_marker_at_new_location(self, temp_hive_setup):
        """Should update .hive/identity.json with new identity at moved location."""
        repo_root, backend_dir, frontend_dir = temp_hive_setup
        new_dir = repo_root / "api_layer"

        result = await _rename_hive("backend", "api_layer")
        assert result["status"] == RESULT_STATUS_SUCCESS

        identity_path = new_dir / ".hive" / "identity.json"
        assert identity_path.exists()

        with open(identity_path) as f:
            identity = json.load(f)

        assert identity["normalized_name"] == "api_layer"
        assert identity["display_name"] == "api_layer"

    async def test_rename_empty_hive(self, temp_hive_setup):
        """Should successfully rename hive with no tickets, folder moves."""
        repo_root, backend_dir, frontend_dir = temp_hive_setup

        for ticket_file in frontend_dir.glob("*.md"):
            ticket_file.unlink()

        result = await _rename_hive("frontend", "ui_layer")

        assert result["status"] == RESULT_STATUS_SUCCESS
        config = load_bees_config()
        assert "frontend" not in config.hives
        assert "ui_layer" in config.hives
        assert (repo_root / "ui_layer").exists()
        assert not frontend_dir.exists()


class TestRenameHiveErrors:
    """Tests for error cases in rename_hive()."""

    async def test_missing_hive_error(self, temp_hive_setup):
        """Should return error when old hive doesn't exist."""
        result = await _rename_hive("nonexistent", "new_name")

        assert result["status"] == "error"
        assert result["error_type"] == "hive_not_found"
        assert "nonexistent" in result["message"]

    async def test_name_conflict_error(self, temp_hive_setup):
        """Should return error when new name conflicts with existing hive."""
        result = await _rename_hive("backend", "frontend")

        assert result["status"] == "error"
        assert result["error_type"] == "name_conflict"
        assert "already exists" in result["message"]

    @pytest.mark.parametrize(
        "old_name, new_name, expected_error_type, expected_msg",
        [
            ("---", "new_name", "hive_not_found", "does not exist"),
            ("backend", "!!!", "validation_error", "normalizes to empty string"),
        ],
    )
    async def test_invalid_name_normalization(
        self, temp_hive_setup, old_name, new_name, expected_error_type, expected_msg
    ):
        """Should return error when names normalize to empty string."""
        result = await _rename_hive(old_name, new_name)

        assert result["status"] == "error"
        assert result["error_type"] == expected_error_type
        assert expected_msg in result["message"]

    async def test_path_conflict_error(self, temp_hive_setup):
        """Should return path_conflict when target folder already exists on disk."""
        repo_root, backend_dir, frontend_dir = temp_hive_setup

        # Create target directory to force path_conflict
        (repo_root / "new_hive").mkdir()

        result = await _rename_hive("backend", "new_hive")

        assert result["status"] == "error"
        assert result["error_type"] == "path_conflict"

    async def test_folder_rename_error(self, temp_hive_setup):
        """Should return folder_rename_error when shutil.move fails."""
        with patch("src.mcp_hive_ops.shutil.move", side_effect=OSError("disk full")):
            result = await _rename_hive("backend", "api_layer")

        assert result["status"] == "error"
        assert result["error_type"] == "folder_rename_error"
        assert "disk full" in result["message"]


class TestRenameHiveEdgeCases:
    """Tests for edge cases in rename_hive()."""

    async def test_rename_with_special_characters_preserves_display_name(self, temp_hive_setup):
        """Should normalize special characters and preserve display name case."""
        repo_root, backend_dir, frontend_dir = temp_hive_setup

        result = await _rename_hive("backend", "API-Layer")

        assert result["status"] == RESULT_STATUS_SUCCESS
        config = load_bees_config()
        assert "api_layer" in config.hives
        assert config.hives["api_layer"].display_name == "API-Layer"

    async def test_rename_handles_missing_marker_file(self, temp_hive_setup):
        """Should create .hive/identity.json if missing at new location."""
        repo_root, backend_dir, frontend_dir = temp_hive_setup
        new_dir = repo_root / "api_layer"

        (backend_dir / ".hive" / "identity.json").unlink()

        result = await _rename_hive("backend", "api_layer")
        assert result["status"] == RESULT_STATUS_SUCCESS

        identity_path = new_dir / ".hive" / "identity.json"
        assert identity_path.exists()

        with open(identity_path) as f:
            identity = json.load(f)

        assert identity["normalized_name"] == "api_layer"
        assert identity["display_name"] == "api_layer"

    async def test_rename_folder_false_preserves_disk_location(self, temp_hive_setup):
        """With rename_folder=False, folder stays on disk, config path unchanged."""
        repo_root, backend_dir, frontend_dir = temp_hive_setup
        original_path = str(backend_dir)

        result = await _rename_hive("backend", "api_layer", rename_folder=False)

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert "old_path" not in result
        assert "new_path" not in result

        # Folder unchanged on disk
        assert backend_dir.exists()

        # Config path unchanged
        config = load_bees_config()
        assert config.hives["api_layer"].path == original_path


class TestRenameHiveIntegration:
    """Integration tests verifying end-to-end rename operations."""

    async def test_rename_does_not_affect_other_hives(self, temp_hive_setup):
        """Should not modify tickets in other hives at all."""
        repo_root, backend_dir, frontend_dir = temp_hive_setup

        frontend_ticket_path = frontend_dir / f"{TICKET_ID_MCP_RENAME_TASK3}.md"
        original_content = frontend_ticket_path.read_text()

        await _rename_hive("backend", "api_layer")

        # Frontend ticket should be completely unchanged
        assert frontend_ticket_path.exists()
        new_content = frontend_ticket_path.read_text()
        assert new_content == original_content
