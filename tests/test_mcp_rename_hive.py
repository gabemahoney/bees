"""Unit tests for MCP rename_hive() command."""

import pytest
import json
from pathlib import Path

from src.mcp_server import _rename_hive
from src.config import BeesConfig, HiveConfig, save_bees_config, load_bees_config
from datetime import datetime


@pytest.fixture
def temp_hive_setup(tmp_path, monkeypatch):
    """Create temporary hive directories with test tickets."""
    # Create hive directories
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    api_layer_dir = tmp_path / "api_layer"
    api_layer_dir.mkdir()
    
    # Change to temp directory
    monkeypatch.chdir(tmp_path)
    
    # Initialize config with test hives
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
        },
        allow_cross_hive_dependencies=True,
        schema_version='1.0'
    )
    save_bees_config(config, repo_root=tmp_path)
    
    # Create sample tickets in backend hive
    ticket1_path = backend_dir / "backend.bees-abc1.md"
    ticket1_path.write_text("""---
id: backend.bees-abc1
title: Test Ticket 1
type: task
status: open
created_at: '2024-01-01T00:00:00'
---
Test ticket 1 body
""")
    
    ticket2_path = backend_dir / "backend.bees-xyz2.md"
    ticket2_path.write_text("""---
id: backend.bees-xyz2
title: Test Ticket 2
type: task
status: open
parent: backend.bees-abc1
created_at: '2024-01-01T00:00:00'
---
Test ticket 2 body
""")
    
    # Create ticket in frontend with cross-hive reference
    frontend_ticket = frontend_dir / "frontend.bees-def3.md"
    frontend_ticket.write_text("""---
id: frontend.bees-def3
title: Frontend Ticket
type: task
status: open
dependencies:
- backend.bees-abc1
up_dependencies:
- backend.bees-xyz2
created_at: '2024-01-01T00:00:00'
---
Frontend ticket body
""")
    
    # Create .hive marker directory with identity.json
    hive_marker_dir = backend_dir / ".hive"
    hive_marker_dir.mkdir()
    identity_file = hive_marker_dir / "identity.json"
    identity_file.write_text(json.dumps({
        "normalized_name": "backend",
        "display_name": "Backend",
        "created_at": "2024-01-01T00:00:00"
    }, indent=2))
    
    yield tmp_path, backend_dir, frontend_dir, api_layer_dir


class TestRenameHiveSuccess:
    """Tests for successful rename_hive() operations."""
    
    async def test_basic_rename(self, temp_hive_setup):
        """Should successfully rename hive with basic operation."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        result = await _rename_hive("backend", "api_layer")
        
        assert result["status"] == "success"
        assert result["old_name"] == "backend"
        assert result["new_name"] == "api_layer"
        assert result["tickets_updated"] >= 0
        
        # Verify config updated
        config = load_bees_config()
        assert "backend" not in config.hives
        assert "api_layer" in config.hives
        assert config.hives["api_layer"].display_name == "api_layer"
        
        # Verify files renamed
        assert not (backend_dir / "backend.bees-abc1.md").exists()
        assert (backend_dir / "api_layer.bees-abc1.md").exists()
        assert not (backend_dir / "backend.bees-xyz2.md").exists()
        assert (backend_dir / "api_layer.bees-xyz2.md").exists()
    
    async def test_rename_updates_ticket_ids_in_frontmatter(self, temp_hive_setup):
        """Should update 'id' field in ticket frontmatter."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        await _rename_hive("backend", "api_layer")
        
        # Read renamed ticket and verify ID updated
        ticket_path = backend_dir / "api_layer.bees-abc1.md"
        content = ticket_path.read_text()
        
        assert "id: api_layer.bees-abc1" in content
        assert "id: backend.bees-abc1" not in content
    
    async def test_rename_updates_cross_hive_references(self, temp_hive_setup):
        """Should update references to renamed tickets in other hives."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        await _rename_hive("backend", "api_layer")
        
        # Read frontend ticket and verify references updated
        frontend_ticket_path = frontend_dir / "frontend.bees-def3.md"
        content = frontend_ticket_path.read_text()
        
        assert "api_layer.bees-abc1" in content
        assert "api_layer.bees-xyz2" in content
        assert "backend.bees-abc1" not in content
        assert "backend.bees-xyz2" not in content
    
    async def test_rename_updates_parent_references(self, temp_hive_setup):
        """Should update parent field in child tickets."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        await _rename_hive("backend", "api_layer")
        
        # Read child ticket and verify parent updated
        ticket_path = backend_dir / "api_layer.bees-xyz2.md"
        content = ticket_path.read_text()
        
        assert "parent: api_layer.bees-abc1" in content
        assert "parent: backend.bees-abc1" not in content
    
    async def test_rename_updates_hive_marker(self, temp_hive_setup):
        """Should update .hive/identity.json with new name."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        await _rename_hive("backend", "api_layer")
        
        # Read identity file
        identity_path = backend_dir / ".hive" / "identity.json"
        with open(identity_path) as f:
            identity = json.load(f)
        
        assert identity["normalized_name"] == "api_layer"
        assert identity["display_name"] == "api_layer"
    
    async def test_rename_empty_hive(self, temp_hive_setup):
        """Should successfully rename hive with no tickets."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        # Remove all tickets from frontend hive
        for ticket_file in frontend_dir.glob("*.md"):
            ticket_file.unlink()
        
        result = await _rename_hive("frontend", "ui_layer")
        
        assert result["status"] == "success"
        assert result["old_name"] == "frontend"
        assert result["new_name"] == "ui_layer"
        
        # Verify config updated
        config = load_bees_config()
        assert "frontend" not in config.hives
        assert "ui_layer" in config.hives
    
    async def test_rename_with_complex_dependencies(self, temp_hive_setup):
        """Should handle complex dependency graphs correctly."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        # Create ticket with multiple dependency types
        ticket3_path = backend_dir / "backend.bees-test3.md"
        ticket3_path.write_text("""---
id: backend.bees-test3
title: Complex Ticket
type: task
status: open
parent: backend.bees-abc1
children:
- backend.bees-xyz2
dependencies:
- backend.bees-abc1
up_dependencies:
- backend.bees-xyz2
down_dependencies:
- backend.bees-abc1
created_at: '2024-01-01T00:00:00'
---
Complex dependencies
""")
        
        await _rename_hive("backend", "api_layer")
        
        # Verify all dependency fields updated
        content = (backend_dir / "api_layer.bees-test3.md").read_text()
        
        assert "parent: api_layer.bees-abc1" in content
        assert "- api_layer.bees-xyz2" in content
        assert "- api_layer.bees-abc1" in content


class TestRenameHiveErrors:
    """Tests for error cases in rename_hive()."""
    
    async def test_missing_hive_error(self, temp_hive_setup):
        """Should return error when old hive doesn't exist."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        result = await _rename_hive("nonexistent", "new_name")
        
        assert result["status"] == "error"
        assert result["error_type"] == "hive_not_found"
        assert "nonexistent" in result["message"]
    
    async def test_name_conflict_error(self, temp_hive_setup):
        """Should return error when new name conflicts with existing hive."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        result = await _rename_hive("backend", "frontend")
        
        assert result["status"] == "error"
        assert result["error_type"] == "name_conflict"
        assert "already exists" in result["message"]
    
    async def test_invalid_old_name_empty_after_normalization(self, temp_hive_setup):
        """Should return error when old name normalizes to empty string."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        result = await _rename_hive("---", "new_name")
        
        assert result["status"] == "error"
        # When normalized name is empty, hive lookup fails with hive_not_found
        assert result["error_type"] == "hive_not_found"
        assert "does not exist" in result["message"]
    
    async def test_invalid_new_name_empty_after_normalization(self, temp_hive_setup):
        """Should return error when new name normalizes to empty string."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        result = await _rename_hive("backend", "!!!")
        
        assert result["status"] == "error"
        assert result["error_type"] == "validation_error"
        assert "normalizes to empty string" in result["message"]
    
    async def test_file_conflict_error(self, temp_hive_setup):
        """Should return error when renamed file would conflict with existing file."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        # Create a file that would conflict with renamed file
        conflict_file = backend_dir / "api_layer.bees-abc1.md"
        conflict_file.write_text("---\nid: api_layer.bees-abc1\n---\nConflict")
        
        result = await _rename_hive("backend", "api_layer")
        
        assert result["status"] == "error"
        assert result["error_type"] == "file_conflict"
        assert "already exists" in result["message"]


class TestRenameHiveEdgeCases:
    """Tests for edge cases in rename_hive()."""
    
    async def test_rename_with_special_characters(self, temp_hive_setup):
        """Should normalize special characters in hive names."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        result = await _rename_hive("backend", "API-Layer")
        
        assert result["status"] == "success"
        
        # Verify normalization
        config = load_bees_config()
        assert "api_layer" in config.hives
        assert config.hives["api_layer"].display_name == "API-Layer"
    
    async def test_rename_preserves_display_name_case(self, temp_hive_setup):
        """Should preserve case in display_name while normalizing key."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        await _rename_hive("backend", "API Layer")
        
        config = load_bees_config()
        assert config.hives["api_layer"].display_name == "API Layer"
    
    async def test_rename_handles_missing_marker_file(self, temp_hive_setup):
        """Should handle missing .hive/identity.json gracefully."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        # Remove marker file
        identity_path = backend_dir / ".hive" / "identity.json"
        identity_path.unlink()
        
        result = await _rename_hive("backend", "api_layer")
        
        # Should still succeed and create new marker
        assert result["status"] == "success"
        assert identity_path.exists()
    
    async def test_rename_with_no_cross_references(self, temp_hive_setup):
        """Should handle rename when no cross-references exist."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        # Remove frontend ticket (which has cross-references)
        (frontend_dir / "frontend.bees-def3.md").unlink()
        
        result = await _rename_hive("backend", "api_layer")
        
        assert result["status"] == "success"
        assert result["tickets_updated"] >= 0
    
    async def test_rename_with_malformed_frontmatter(self, temp_hive_setup):
        """Should handle tickets with malformed frontmatter gracefully."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        # Create ticket with malformed frontmatter
        bad_ticket = backend_dir / "backend.bees-bad.md"
        bad_ticket.write_text("No frontmatter here\nJust plain text")
        
        result = await _rename_hive("backend", "api_layer")
        
        # Should still succeed, skipping malformed ticket
        assert result["status"] == "success"
    
    async def test_rename_linter_integration_deferred(self, temp_hive_setup):
        """Linter integration is deferred to future work (per implementation comments)."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        # Rename should succeed even though linter is stubbed
        result = await _rename_hive("backend", "api_layer")
        
        assert result["status"] == "success"
        # Note: Full linter integration deferred per src/mcp_server.py:2407-2415
    
    async def test_rename_normalizes_both_names(self, temp_hive_setup):
        """Should normalize both old and new names for lookup."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        # Use non-normalized old name
        result = await _rename_hive("Back End", "api_layer")
        
        # Should fail because "Back End" normalizes to "back_end", not "backend"
        assert result["status"] == "error"
        assert result["error_type"] == "hive_not_found"
    
    async def test_rename_handles_children_field(self, temp_hive_setup):
        """Should update children field in parent tickets."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        # Add children field to ticket1
        ticket1_path = backend_dir / "backend.bees-abc1.md"
        ticket1_path.write_text("""---
id: backend.bees-abc1
title: Test Ticket 1
type: task
status: open
children:
- backend.bees-xyz2
created_at: '2024-01-01T00:00:00'
---
Test ticket 1 body
""")
        
        await _rename_hive("backend", "api_layer")
        
        # Verify children updated
        content = (backend_dir / "api_layer.bees-abc1.md").read_text()
        assert "- api_layer.bees-xyz2" in content
        assert "- backend.bees-xyz2" not in content


class TestRenameHiveChildrenFieldBugFix:
    """Tests for children field update bug fix (bees-crw6l)."""
    
    async def test_children_update_when_parent_unchanged(self, temp_hive_setup):
        """Should update children field even when parent field doesn't change."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        # Create ticket with children but no parent
        ticket_path = backend_dir / "backend.bees-parent.md"
        ticket_path.write_text("""---
id: backend.bees-parent
title: Parent Ticket
type: task
status: open
children:
- backend.bees-abc1
- backend.bees-xyz2
created_at: '2024-01-01T00:00:00'
---
Parent ticket with children only
""")
        
        await _rename_hive("backend", "api_layer")
        
        # Verify children list was updated despite no parent field change
        content = (backend_dir / "api_layer.bees-parent.md").read_text()
        assert "- api_layer.bees-abc1" in content
        assert "- api_layer.bees-xyz2" in content
        assert "- backend.bees-abc1" not in content
        assert "- backend.bees-xyz2" not in content
    
    async def test_parent_update_when_children_unchanged(self, temp_hive_setup):
        """Should update parent field even when children list doesn't change."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        # Create ticket with parent but children pointing to other hive
        ticket_path = backend_dir / "backend.bees-child.md"
        ticket_path.write_text("""---
id: backend.bees-child
title: Child Ticket
type: task
status: open
parent: backend.bees-abc1
children:
- frontend.bees-def3
created_at: '2024-01-01T00:00:00'
---
Child with cross-hive children
""")
        
        await _rename_hive("backend", "api_layer")
        
        # Verify parent was updated despite children list having no mapped IDs
        content = (backend_dir / "api_layer.bees-child.md").read_text()
        assert "parent: api_layer.bees-abc1" in content
        assert "parent: backend.bees-abc1" not in content
        # Children should remain unchanged
        assert "- frontend.bees-def3" in content
    
    async def test_both_parent_and_children_update(self, temp_hive_setup):
        """Should update both parent and children when both need changes."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        # Create ticket with both parent and children in same hive
        ticket_path = backend_dir / "backend.bees-middle.md"
        ticket_path.write_text("""---
id: backend.bees-middle
title: Middle Ticket
type: task
status: open
parent: backend.bees-abc1
children:
- backend.bees-xyz2
created_at: '2024-01-01T00:00:00'
---
Middle ticket
""")
        
        await _rename_hive("backend", "api_layer")
        
        # Verify both fields updated
        content = (backend_dir / "api_layer.bees-middle.md").read_text()
        assert "parent: api_layer.bees-abc1" in content
        assert "- api_layer.bees-xyz2" in content
        assert "backend.bees-abc1" not in content
        assert "backend.bees-xyz2" not in content
    
    async def test_neither_parent_nor_children_update(self, temp_hive_setup):
        """Should handle case where neither parent nor children need updates."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        # Create ticket with cross-hive references only
        ticket_path = backend_dir / "backend.bees-cross.md"
        ticket_path.write_text("""---
id: backend.bees-cross
title: Cross-hive Ticket
type: task
status: open
parent: frontend.bees-def3
children:
- frontend.bees-def3
created_at: '2024-01-01T00:00:00'
---
Cross-hive references
""")
        
        await _rename_hive("backend", "api_layer")
        
        # Verify neither field changed (but ticket ID did)
        content = (backend_dir / "api_layer.bees-cross.md").read_text()
        assert "id: api_layer.bees-cross" in content
        assert "parent: frontend.bees-def3" in content
        assert "- frontend.bees-def3" in content


class TestRenameHiveIntegration:
    """Integration tests verifying end-to-end rename operations."""
    
    async def test_full_rename_workflow(self, temp_hive_setup):
        """Should complete full rename workflow successfully."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        # Perform rename
        result = await _rename_hive("backend", "api_layer")
        
        assert result["status"] == "success"
        
        # Verify all 10 steps completed:
        # 1. Config updated
        config = load_bees_config()
        assert "api_layer" in config.hives
        assert "backend" not in config.hives
        
        # 2. IDs regenerated (verified by filename changes)
        assert (backend_dir / "api_layer.bees-abc1.md").exists()
        assert (backend_dir / "api_layer.bees-xyz2.md").exists()
        
        # 3. Filenames renamed
        assert not (backend_dir / "backend.bees-abc1.md").exists()
        
        # 4. Frontmatter updated
        content1 = (backend_dir / "api_layer.bees-abc1.md").read_text()
        assert "id: api_layer.bees-abc1" in content1
        
        # 5. Cross-references updated
        frontend_content = (frontend_dir / "frontend.bees-def3.md").read_text()
        assert "api_layer.bees-abc1" in frontend_content
        
        # 6. Marker updated
        identity_path = backend_dir / ".hive" / "identity.json"
        with open(identity_path) as f:
            identity = json.load(f)
        assert identity["normalized_name"] == "api_layer"
    
    async def test_rename_does_not_affect_other_hives(self, temp_hive_setup):
        """Should not modify tickets in other hives except references."""
        tmp_path, backend_dir, frontend_dir, api_layer_dir = temp_hive_setup
        
        # Record original frontend ticket ID
        frontend_ticket_path = frontend_dir / "frontend.bees-def3.md"
        original_content = frontend_ticket_path.read_text()
        
        await _rename_hive("backend", "api_layer")
        
        # Frontend ticket ID should remain unchanged
        assert frontend_ticket_path.exists()
        new_content = frontend_ticket_path.read_text()
        assert "id: frontend.bees-def3" in new_content
        
        # But references should be updated
        assert "api_layer.bees-abc1" in new_content
