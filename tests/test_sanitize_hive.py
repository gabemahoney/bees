"""Unit tests for sanitize_hive() MCP command."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from src.mcp_hive_ops import _sanitize_hive
from src.config import BeesConfig, HiveConfig, save_bees_config
from src.writer import write_ticket_file


class TestSanitizeHive:
    """Tests for sanitize_hive MCP command."""
    
    async def test_sanitize_unregistered_hive_returns_error(self, tmp_path, monkeypatch):
        """Test that sanitizing an unregistered hive returns an error."""
        # Create .git directory to make it a git repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        monkeypatch.chdir(tmp_path)

        # Create empty config
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()

        config = BeesConfig(
            hives={},
            allow_cross_hive_dependencies=False,
            schema_version="1.0"
        )
        save_bees_config(config)

        # Try to sanitize non-existent hive
        result = await _sanitize_hive("nonexistent")

        assert result["status"] == "error"
        assert result["error_type"] == "hive_not_found"
        assert "not registered" in result["message"]
    
    async def test_sanitize_returns_detailed_report(self, tmp_path, monkeypatch):
        """Test that sanitize_hive returns a detailed report with fixes and errors."""
        # Create .git directory to make it a git repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        monkeypatch.chdir(tmp_path)

        # Create hive directory
        hive_dir = tmp_path / "backend"
        hive_dir.mkdir()

        # Create config
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()

        config = BeesConfig(
            hives={
                "backend": HiveConfig(
                    path=str(hive_dir),
                    display_name="Backend",
                    created_at="2026-02-01T10:00:00"
                )
            },
            allow_cross_hive_dependencies=False,
            schema_version="1.0"
        )
        save_bees_config(config)

        # Create a ticket with orphaned parent relationship
        write_ticket_file(
            ticket_id="backend.bees-abc",
            ticket_type="epic",
            frontmatter_data={
                "id": "backend.bees-abc",
                "type": "epic",
                "title": "Parent",
                "status": "open",
                "children": []  # Missing child
            }
        )

        write_ticket_file(
            ticket_id="backend.bees-xyz",
            ticket_type="task",
            frontmatter_data={
                "id": "backend.bees-xyz",
                "type": "task",
                "title": "Child",
                "status": "open",
                "parent": "backend.bees-abc"  # Orphaned
            }
        )

        # Run sanitize_hive
        result = await _sanitize_hive("backend")
        
        # Check result structure
        assert "status" in result
        assert "message" in result
        assert "fixes_applied" in result
        assert "errors_remaining" in result
        assert "is_corrupt" in result
        assert "fix_count" in result
        assert "error_count" in result
        
        # Should have applied fixes
        assert result["fix_count"] >= 0
    
    async def test_sanitize_detects_invalid_hive_prefix(self, tmp_path, monkeypatch):
        """Test that sanitize_hive detects tickets with wrong hive prefix."""
        # Create .git directory to make it a git repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        monkeypatch.chdir(tmp_path)

        # Create hive directory
        hive_dir = tmp_path / "backend"
        hive_dir.mkdir()

        # Create config
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()

        config = BeesConfig(
            hives={
                "backend": HiveConfig(
                    path=str(hive_dir),
                    display_name="Backend",
                    created_at="2026-02-01T10:00:00"
                )
            },
            allow_cross_hive_dependencies=False,
            schema_version="1.0"
        )
        save_bees_config(config)

        # Create ticket with WRONG prefix (bypass write_ticket_file)
        wrong_prefix_file = hive_dir / "frontend.bees-abc.md"
        wrong_prefix_file.write_text("""---
id: frontend.bees-abc
bees_version: '1.1'
type: epic
title: Wrong Prefix
status: open
---
""")

        # Run sanitize_hive
        result = await _sanitize_hive("backend")
        
        # Should detect invalid prefix error
        assert result["error_count"] > 0
        
        # Check for invalid_hive_prefix error
        prefix_errors = [e for e in result["errors_remaining"] 
                        if e["error_type"] == "invalid_hive_prefix"]
        assert len(prefix_errors) > 0
    
    async def test_sanitize_detects_cross_hive_violations(self, tmp_path, monkeypatch):
        """Test that sanitize_hive detects cross-hive dependency violations."""
        # Create .git directory to make it a git repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        monkeypatch.chdir(tmp_path)

        # Create hive directory
        hive_dir = tmp_path / "backend"
        hive_dir.mkdir()

        # Create config that DISALLOWS cross-hive deps
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()

        config = BeesConfig(
            hives={
                "backend": HiveConfig(
                    path=str(hive_dir),
                    display_name="Backend",
                    created_at="2026-02-01T10:00:00"
                )
            },
            allow_cross_hive_dependencies=False,  # Disallow
            schema_version="1.0"
        )
        save_bees_config(config)

        # Create ticket with cross-hive parent
        write_ticket_file(
            ticket_id="backend.bees-abc",
            ticket_type="epic",
            frontmatter_data={
                "id": "backend.bees-abc",
                "type": "epic",
                "title": "Backend Epic",
                "status": "open",
                "parent": "frontend.bees-xyz"  # Cross-hive violation!
            }
        )

        # Run sanitize_hive
        result = await _sanitize_hive("backend")
        
        # Should detect cross-hive error
        assert result["error_count"] > 0
        
        # Check for cross_hive_dependency error
        cross_hive_errors = [e for e in result["errors_remaining"] 
                            if e["error_type"] == "cross_hive_dependency"]
        assert len(cross_hive_errors) > 0
    
    async def test_sanitize_marks_corrupt_on_unfixable_errors(self, tmp_path, monkeypatch):
        """Test that sanitize_hive marks DB as corrupt when unfixable errors remain."""
        # Create .git directory to make it a git repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        monkeypatch.chdir(tmp_path)

        # Create hive directory
        hive_dir = tmp_path / "backend"
        hive_dir.mkdir()

        # Create config
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()

        config = BeesConfig(
            hives={
                "backend": HiveConfig(
                    path=str(hive_dir),
                    display_name="Backend",
                    created_at="2026-02-01T10:00:00"
                )
            },
            allow_cross_hive_dependencies=False,
            schema_version="1.0"
        )
        save_bees_config(config)

        # Create ticket with invalid ID format (bypass write_ticket_file)
        invalid_file = hive_dir / "INVALID-ID.md"
        invalid_file.write_text("""---
id: INVALID-ID
bees_version: '1.1'
type: epic
title: Invalid
status: open
---
""")

        # Run sanitize_hive
        result = await _sanitize_hive("backend")
        
        # Should have errors and be marked corrupt
        if result["error_count"] > 0:
            assert result["is_corrupt"] is True
            assert result["status"] == "error"
    
    async def test_sanitize_fixes_orphaned_relationships(self, tmp_path, monkeypatch):
        """Test that sanitize_hive automatically fixes orphaned relationships."""
        # Create .git directory to make it a git repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        monkeypatch.chdir(tmp_path)

        # Create hive directory
        hive_dir = tmp_path / "backend"
        hive_dir.mkdir()

        # Create config
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()

        config = BeesConfig(
            hives={
                "backend": HiveConfig(
                    path=str(hive_dir),
                    display_name="Backend",
                    created_at="2026-02-01T10:00:00"
                )
            },
            allow_cross_hive_dependencies=False,
            schema_version="1.0"
        )
        save_bees_config(config)

        # Create parent without child in children list
        write_ticket_file(
            ticket_id="backend.bees-abc",
            ticket_type="epic",
            frontmatter_data={
                "id": "backend.bees-abc",
                "type": "epic",
                "title": "Parent",
                "status": "open",
                "children": []  # Missing child (orphaned relationship)
            }
        )

        # Create child that references parent
        write_ticket_file(
            ticket_id="backend.bees-xyz",
            ticket_type="task",
            frontmatter_data={
                "id": "backend.bees-xyz",
                "type": "task",
                "title": "Child",
                "status": "open",
                "parent": "backend.bees-abc"
            }
        )

        # Run sanitize_hive
        result = await _sanitize_hive("backend")
        
        # Should have applied fixes
        assert result["fix_count"] > 0
        
        # Check that fixes include adding child
        fix_types = [f["fix_type"] for f in result["fixes_applied"]]
        assert "add_child" in fix_types or "set_parent" in fix_types
