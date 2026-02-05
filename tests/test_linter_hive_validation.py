"""Unit tests for linter hive-specific validations."""

import tempfile
from pathlib import Path
import pytest

from src.linter import Linter
from src.linter_report import LinterReport
from src.models import Epic, Task
from src.config import BeesConfig, HiveConfig
from src.writer import write_ticket_file


class TestLinterValidateHivePrefix:
    """Tests for linter hive prefix validation."""
    
    def test_linter_validates_hive_prefixes(self, tmp_path, monkeypatch):
        """Test that linter validates ticket IDs match hive prefix."""
        monkeypatch.chdir(tmp_path)
        
        # Create tickets directory
        tickets_dir = tmp_path / "backend"
        tickets_dir.mkdir()
        
        # Create config with backend hive
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        
        from src.config import BeesConfig, HiveConfig, save_bees_config
        config = BeesConfig(
            hives={
                "backend": HiveConfig(
                    path=str(tickets_dir),
                    display_name="Backend",
                    created_at="2026-02-01T10:00:00"
                )
            },
            allow_cross_hive_dependencies=False,
            schema_version="1.0"
        )
        save_bees_config(config)
        
        # Create ticket with correct prefix
        write_ticket_file(
            ticket_id="backend.bees-abc",
            ticket_type="epic",
            frontmatter_data={
                "id": "backend.bees-abc",
                "type": "epic",
                "title": "Correct Prefix",
                "status": "open"
            }
        )
        
        # Create ticket with wrong prefix (bypass write_ticket_file to avoid validation)
        wrong_prefix_file = tickets_dir / "frontend.bees-xyz.md"
        wrong_prefix_file.write_text("""---
id: frontend.bees-xyz
bees_version: '1.1'
type: epic
title: Wrong Prefix
status: open
---
""")
        
        # Run linter with hive prefix validation
        linter = Linter(
            tickets_dir=str(tickets_dir),
            hive_name="backend",
            validate_hive_prefix=True
        )
        
        report = linter.run()
        
        # Should have error for wrong prefix
        prefix_errors = [e for e in report.errors if e.error_type == "invalid_hive_prefix"]
        assert len(prefix_errors) == 1
        assert "frontend.bees-xyz" in prefix_errors[0].ticket_id
    
    def test_linter_skips_prefix_validation_when_disabled(self, tmp_path, monkeypatch):
        """Test that linter skips prefix validation when not enabled."""
        monkeypatch.chdir(tmp_path)
        
        tickets_dir = tmp_path / "backend"
        tickets_dir.mkdir()
        
        # Create config
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        
        from src.config import BeesConfig, HiveConfig, save_bees_config
        config = BeesConfig(
            hives={
                "backend": HiveConfig(
                    path=str(tickets_dir),
                    display_name="Backend",
                    created_at="2026-02-01T10:00:00"
                )
            },
            allow_cross_hive_dependencies=False,
            schema_version="1.0"
        )
        save_bees_config(config)
        
        # Create ticket with wrong prefix (bypass write_ticket_file)
        wrong_prefix_file = tickets_dir / "frontend.bees-xyz.md"
        wrong_prefix_file.write_text("""---
id: frontend.bees-xyz
bees_version: '1.1'
type: epic
title: Wrong Prefix
status: open
---
""")
        
        # Run linter WITHOUT hive prefix validation
        linter = Linter(
            tickets_dir=str(tickets_dir),
            hive_name="backend",
            validate_hive_prefix=False
        )
        
        report = linter.run()
        
        # Should NOT have prefix errors
        prefix_errors = [e for e in report.errors if e.error_type == "invalid_hive_prefix"]
        assert len(prefix_errors) == 0


class TestLinterValidateCrossHiveDeps:
    """Tests for linter cross-hive dependency validation."""
    
    def test_linter_validates_cross_hive_deps_when_disallowed(self, tmp_path, monkeypatch):
        """Test that linter detects cross-hive dependencies when config disallows them."""
        monkeypatch.chdir(tmp_path)
        
        tickets_dir = tmp_path / "backend"
        tickets_dir.mkdir()
        
        # Create config that disallows cross-hive deps
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        
        config = BeesConfig(
            hives={
                "backend": HiveConfig(
                    path=str(tickets_dir),
                    display_name="Backend",
                    created_at="2026-02-01T10:00:00"
                )
            },
            allow_cross_hive_dependencies=False,
            schema_version="1.0"
        )
        
        from src.config import save_bees_config
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
                "parent": "frontend.bees-xyz"  # Cross-hive reference
            }
        )
        
        # Run linter with config
        linter = Linter(
            tickets_dir=str(tickets_dir),
            hive_name="backend",
            config=config
        )
        
        report = linter.run()
        
        # Should have cross-hive dependency error
        cross_hive_errors = [e for e in report.errors if e.error_type == "cross_hive_dependency"]
        assert len(cross_hive_errors) == 1
        assert "frontend.bees-xyz" in cross_hive_errors[0].message
    
    def test_linter_allows_cross_hive_deps_when_enabled(self, tmp_path, monkeypatch):
        """Test that linter allows cross-hive dependencies when config enables them."""
        monkeypatch.chdir(tmp_path)
        
        tickets_dir = tmp_path / "backend"
        tickets_dir.mkdir()
        
        # Create config that ALLOWS cross-hive deps
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        
        config = BeesConfig(
            hives={
                "backend": HiveConfig(
                    path=str(tickets_dir),
                    display_name="Backend",
                    created_at="2026-02-01T10:00:00"
                )
            },
            allow_cross_hive_dependencies=True,
            schema_version="1.0"
        )
        
        from src.config import save_bees_config
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
                "parent": "frontend.bees-xyz"
            }
        )
        
        # Run linter with config
        linter = Linter(
            tickets_dir=str(tickets_dir),
            hive_name="backend",
            config=config
        )
        
        report = linter.run()
        
        # Should NOT have cross-hive dependency errors
        cross_hive_errors = [e for e in report.errors if e.error_type == "cross_hive_dependency"]
        assert len(cross_hive_errors) == 0


class TestLinterAutoFixMode:
    """Tests for linter auto-fix functionality."""
    
    def test_linter_auto_fix_orphaned_relationships(self, tmp_path, monkeypatch):
        """Test that auto-fix mode repairs orphaned parent/child relationships."""
        monkeypatch.chdir(tmp_path)
        
        tickets_dir = tmp_path / "backend"
        tickets_dir.mkdir()
        
        # Create config
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        
        from src.config import BeesConfig, HiveConfig, save_bees_config
        config = BeesConfig(
            hives={
                "backend": HiveConfig(
                    path=str(tickets_dir),
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
                "title": "Parent Epic",
                "status": "open",
                "children": []  # Missing child
            }
        )
        
        # Create child that references parent
        write_ticket_file(
            ticket_id="backend.bees-xyz",
            ticket_type="task",
            frontmatter_data={
                "id": "backend.bees-xyz",
                "type": "task",
                "title": "Child Task",
                "status": "open",
                "parent": "backend.bees-abc"
            }
        )
        
        # Run linter with auto-fix enabled
        linter = Linter(
            tickets_dir=str(tickets_dir),
            hive_name="backend",
            auto_fix=True
        )
        
        report = linter.run()
        
        # Should have applied fixes
        assert len(report.fixes) > 0
        fix_types = [f.fix_type for f in report.fixes]
        assert "add_child" in fix_types
        
        # Should NOT have orphaned_child errors (fixed)
        orphaned_errors = [e for e in report.errors if e.error_type == "orphaned_child"]
        assert len(orphaned_errors) == 0
    
    def test_linter_tracks_fixes_in_report(self, tmp_path, monkeypatch):
        """Test that auto-fix mode tracks all fixes in report."""
        monkeypatch.chdir(tmp_path)
        
        tickets_dir = tmp_path / "backend"
        tickets_dir.mkdir()
        
        # Create config
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        
        from src.config import BeesConfig, HiveConfig, save_bees_config
        config = BeesConfig(
            hives={
                "backend": HiveConfig(
                    path=str(tickets_dir),
                    display_name="Backend",
                    created_at="2026-02-01T10:00:00"
                )
            },
            allow_cross_hive_dependencies=False,
            schema_version="1.0"
        )
        save_bees_config(config)
        
        # Create tickets with bidirectional dependency mismatch
        write_ticket_file(
            ticket_id="backend.bees-abc",
            ticket_type="task",
            frontmatter_data={
                "id": "backend.bees-abc",
                "type": "task",
                "title": "Task A",
                "status": "open",
                "up_dependencies": ["backend.bees-xyz"]  # Missing backlink
            }
        )
        
        write_ticket_file(
            ticket_id="backend.bees-xyz",
            ticket_type="task",
            frontmatter_data={
                "id": "backend.bees-xyz",
                "type": "task",
                "title": "Task B",
                "status": "open",
                "down_dependencies": []  # Should have backend.bees-abc
            }
        )
        
        # Run linter with auto-fix
        linter = Linter(
            tickets_dir=str(tickets_dir),
            hive_name="backend",
            auto_fix=True
        )
        
        report = linter.run()
        
        # Should have fix for adding down_dependency
        assert len(report.fixes) > 0
        add_dep_fixes = [f for f in report.fixes if f.fix_type == "add_down_dependency"]
        assert len(add_dep_fixes) > 0
        assert "backend.bees-abc" in add_dep_fixes[0].description
