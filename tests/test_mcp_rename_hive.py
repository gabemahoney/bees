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
- Error cases: path_conflict, folder_rename_error, nested_hive (folder holds another hive)
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
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config import BeesConfig, HiveConfig, find_matching_scope, load_bees_config, load_global_config, save_bees_config
from src.mcp_hive_ops import _rename_hive
from src.repo_context import repo_root_context
from tests.conftest import write_multi_scope_config, write_scoped_config
from tests.helpers import tree_snapshot, write_ticket_file
from tests.test_constants import (
    HIVE_BACKEND,
    RESULT_STATUS_SUCCESS,
    SCOPE_PATTERN_EXACT_CHILD,
    SCOPE_PATTERN_PROJECTS_DEEP,
    SCOPE_PATTERN_WILDCARD_PARENT,
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
        global_config = load_global_config()
        scope_pattern = find_matching_scope(repo_root, global_config)
        save_bees_config(config, scope_pattern)

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


@pytest.fixture(params=["hive_marker_in_ticket_dir", "registered_hive_in_folder"])
def folder_with_nested_hive(request, tmp_path, mock_global_bees_dir):
    """Hive backend, in folder core/, holding another hive (.hive/ in a ticket dir, or registered without one).

    Yields (core folder, nested hive root, global config path).
    """
    hive_dir = tmp_path / "core"
    hives = {HIVE_BACKEND: {"path": str(hive_dir), "display_name": "Backend"}}
    if request.param == "hive_marker_in_ticket_dir":
        nested_root = hive_dir / "b.abc" / "Inner"
        (nested_root / ".hive").mkdir(parents=True)
    else:
        nested_root = hive_dir / "inner"
        nested_root.mkdir(parents=True)
        hives["inner"] = {"path": str(nested_root), "display_name": "Inner"}
    write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": hives, "child_tiers": {}})
    write_ticket_file(nested_root, "b.inn", title="Nested Hive Bee")
    with repo_root_context(tmp_path):
        yield hive_dir, nested_root, mock_global_bees_dir / "config.json"


class TestRenameHiveNestedHive:
    """A hive folder holding another hive is never renamed on disk (b.xvo)."""

    async def test_folder_rename_refused(self, folder_with_nested_hive):
        """nested_hive error naming the other hive; folder, nested hive and config unchanged."""
        hive_dir, nested_root, config_path = folder_with_nested_hive
        config_before = config_path.read_text()
        tree_before = tree_snapshot(hive_dir)

        result = await _rename_hive(HIVE_BACKEND, "api_layer", resolved_root=hive_dir.parent)

        assert result["status"] == "error"
        assert result["error_type"] == "nested_hive"
        assert str(nested_root) in result["message"]
        assert config_path.read_text() == config_before
        assert tree_snapshot(hive_dir) == tree_before
        assert not (hive_dir.parent / "api_layer").exists()

    @pytest.mark.parametrize(
        "new_name, rename_folder, normalized_new",
        [
            pytest.param("api_layer", False, "api_layer", id="without_folder_rename"),
            pytest.param("Core", True, "core", id="folder_already_has_new_name"),
        ],
    )
    async def test_rename_keeping_folder_in_place_succeeds(
        self, folder_with_nested_hive, new_name, rename_folder, normalized_new
    ):
        """With rename_folder=False, or a folder already named for the new name, the hive is renamed in place;
        the nested hive keeps its files and registration."""
        hive_dir, nested_root, config_path = folder_with_nested_hive
        repo_root = hive_dir.parent

        def hive_paths():
            hives = json.loads(config_path.read_text())["scopes"][str(repo_root)]["hives"]
            return {name: entry["path"] for name, entry in hives.items()}

        expected_paths = {**hive_paths(), normalized_new: str(hive_dir)}
        del expected_paths[HIVE_BACKEND]
        nested_before = tree_snapshot(nested_root)

        result = await _rename_hive(HIVE_BACKEND, new_name, resolved_root=repo_root, rename_folder=rename_folder)

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["path"] == str(hive_dir)
        assert hive_paths() == expected_paths
        assert tree_snapshot(nested_root) == nested_before


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


class TestRenameHiveMultiScope:
    """Tests for _rename_hive multi-scope lookup guard behavior."""

    async def test_rename_hive_degraded_state_config_conflict(self, tmp_path, mock_global_bees_dir):
        """Two overlapping scopes both define target hive → config_conflict with abandon_hive instruction, no config modified."""
        hive_dir = tmp_path / HIVE_BACKEND
        hive_dir.mkdir()
        hive_marker = hive_dir / ".hive"
        hive_marker.mkdir()
        (hive_marker / "identity.json").write_text(
            json.dumps({"normalized_name": HIVE_BACKEND, "display_name": "Backend", "created_at": "2026-01-01T00:00:00"})
        )

        write_multi_scope_config(mock_global_bees_dir, {
            SCOPE_PATTERN_WILDCARD_PARENT: {
                "hives": {HIVE_BACKEND: {"path": str(hive_dir), "display_name": "Backend"}},
                "child_tiers": {},
            },
            SCOPE_PATTERN_EXACT_CHILD: {
                "hives": {HIVE_BACKEND: {"path": str(hive_dir), "display_name": "Backend"}},
                "child_tiers": {},
            },
        })

        config_before = (mock_global_bees_dir / "config.json").read_text()

        with repo_root_context(Path("/Users/dev/projects/bees")):
            result = await _rename_hive(HIVE_BACKEND, "new_backend", resolved_root=Path("/Users/dev/projects/bees"))

        assert result["status"] == "error"
        assert result["error_type"] == "config_conflict"
        assert "abandon_hive" in result["message"]
        assert (mock_global_bees_dir / "config.json").read_text() == config_before

    async def test_rename_hive_inherited_scope_succeeds(self, tmp_path, mock_global_bees_dir):
        """Hive in one non-conflicting broader scope → success, only owning scope's config entry updated.

        Regression b.4eb: the owning scope keeps its named queries and unknown keys.
        """
        hive_dir = tmp_path / HIVE_BACKEND
        hive_dir.mkdir()
        hive_marker = hive_dir / ".hive"
        hive_marker.mkdir()
        (hive_marker / "identity.json").write_text(
            json.dumps({"normalized_name": HIVE_BACKEND, "display_name": "Backend", "created_at": "2026-01-01T00:00:00"})
        )

        queries = {"my_query": {"stages": [["status=open"]]}}
        exact_scope = {"hives": {}, "child_tiers": {}, "queries": {"other": {"stages": [["status=closed"]]}}}

        write_multi_scope_config(mock_global_bees_dir, {
            SCOPE_PATTERN_WILDCARD_PARENT: {
                "hives": {HIVE_BACKEND: {"path": str(hive_dir), "display_name": "Backend"}},
                "child_tiers": {},
                "queries": queries,
                "future_key": {"keep": True},
            },
            SCOPE_PATTERN_EXACT_CHILD: exact_scope,
        })

        with repo_root_context(Path("/Users/dev/projects/bees")):
            result = await _rename_hive(HIVE_BACKEND, "api_layer", resolved_root=Path("/Users/dev/projects/bees"))

        assert result["status"] == RESULT_STATUS_SUCCESS

        scopes = json.loads((mock_global_bees_dir / "config.json").read_text())["scopes"]
        owning = scopes[SCOPE_PATTERN_WILDCARD_PARENT]
        assert set(owning["hives"]) == {"api_layer"}
        assert owning["queries"] == queries
        assert owning["future_key"] == {"keep": True}
        assert scopes[SCOPE_PATTERN_EXACT_CHILD] == exact_scope

    async def test_rename_hive_not_visible_to_current_repo(self, tmp_path, mock_global_bees_dir):
        """Hive in scope not matching current repo_root → hive_not_found."""
        hive_dir = tmp_path / HIVE_BACKEND
        hive_dir.mkdir()

        write_multi_scope_config(mock_global_bees_dir, {
            SCOPE_PATTERN_PROJECTS_DEEP: {
                "hives": {HIVE_BACKEND: {"path": str(hive_dir), "display_name": "Backend"}},
                "child_tiers": {},
            },
        })

        with repo_root_context(Path("/Users/dev/projects/bees")):
            result = await _rename_hive(HIVE_BACKEND, "new_name", resolved_root=Path("/Users/dev/projects/bees"))

        assert result["status"] == "error"
        assert result["error_type"] == "hive_not_found"


class TestRenameHiveDescription:
    """Tests for the description parameter on rename_hive."""

    async def test_rename_with_description_update(self, tmp_path, mock_global_bees_dir):
        """Renaming a hive with description updates it in config."""
        hive_dir = tmp_path / HIVE_BACKEND
        hive_dir.mkdir()
        (hive_dir / ".hive").mkdir()
        (hive_dir / ".hive" / "identity.json").write_text(
            json.dumps({"normalized_name": HIVE_BACKEND, "display_name": "Backend"})
        )

        write_multi_scope_config(mock_global_bees_dir, {
            str(tmp_path): {
                "hives": {HIVE_BACKEND: {"path": str(hive_dir), "display_name": "Backend", "created_at": "2026-01-01T00:00:00"}},
            },
        })

        with repo_root_context(tmp_path):
            result = await _rename_hive(
                HIVE_BACKEND, "API Layer", resolved_root=tmp_path,
                description="Hive for backend API tickets",
            )

        assert result["status"] == RESULT_STATUS_SUCCESS
        config = load_global_config()
        hive_data = config["scopes"][str(tmp_path)]["hives"]["api_layer"]
        assert hive_data["description"] == "Hive for backend API tickets"

    async def test_rename_without_description_preserves_existing(self, tmp_path, mock_global_bees_dir):
        """Renaming without description= keeps any existing description."""
        hive_dir = tmp_path / HIVE_BACKEND
        hive_dir.mkdir()
        (hive_dir / ".hive").mkdir()
        (hive_dir / ".hive" / "identity.json").write_text(
            json.dumps({"normalized_name": HIVE_BACKEND, "display_name": "Backend"})
        )

        write_multi_scope_config(mock_global_bees_dir, {
            str(tmp_path): {
                "hives": {HIVE_BACKEND: {
                    "path": str(hive_dir), "display_name": "Backend",
                    "created_at": "2026-01-01T00:00:00",
                    "description": "Original description",
                }},
            },
        })

        with repo_root_context(tmp_path):
            result = await _rename_hive(HIVE_BACKEND, "API Layer", resolved_root=tmp_path)

        assert result["status"] == RESULT_STATUS_SUCCESS
        config = load_global_config()
        hive_data = config["scopes"][str(tmp_path)]["hives"]["api_layer"]
        assert hive_data["description"] == "Original description"
