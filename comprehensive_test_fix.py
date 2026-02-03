#!/usr/bin/env python3
"""
Comprehensive fix for test_index_generator.py.
This script carefully transforms each test from hierarchical to flat storage.
"""
import re
from pathlib import Path

def fix_test_index_generator():
    test_file = Path("tests/test_index_generator.py")
    content = test_file.read_text()
    
    # Fix 1: test_scan_tickets_empty_directory
    content = content.replace(
        '''    def test_scan_tickets_empty_directory(self, tmp_path, monkeypatch):
        """Should return empty lists when no tickets exist."""
        # Create empty tickets directory structure
        tickets_dir = tmp_path / "tickets"
        (tickets_dir / "epics").mkdir(parents=True)
        (tickets_dir / "tasks").mkdir(parents=True)
        (tickets_dir / "subtasks").mkdir(parents=True)

        result = scan_tickets()

        assert result == {
            "epic": [],
            "task": [],
            "subtask": []
        }''',
        '''    def test_scan_tickets_empty_directory(self, tmp_path, monkeypatch):
        """Should return empty lists when no tickets exist."""
        monkeypatch.chdir(tmp_path)
        
        # Create empty bees config (no hives)
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()

        result = scan_tickets()

        assert result == {
            "epic": [],
            "task": [],
            "subtask": []
        }'''
    )
    
    # Fix 2: test_scan_tickets_with_mixed_types
    content = content.replace(
        '''    def test_scan_tickets_with_mixed_types(self, tmp_path, monkeypatch):
        """Should group tickets by type correctly."""
        tickets_dir = tmp_path / "tickets"
        epics_dir = tickets_dir / "epics"
        tasks_dir = tickets_dir / "tasks"
        subtasks_dir = tickets_dir / "subtasks"

        epics_dir.mkdir(parents=True)
        tasks_dir.mkdir(parents=True)
        subtasks_dir.mkdir(parents=True)

        # Create sample tickets
        (epics_dir / "bees-ep1.md").write_text("""---
id: bees-ep1
bees_version: '1.1'
type: epic
title: Test Epic 1
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Epic description.""")

        (epics_dir / "bees-ep2.md").write_text("""---
id: bees-ep2
bees_version: '1.1'
type: epic
title: Test Epic 2
status: closed
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Another epic.""")

        (tasks_dir / "bees-ts1.md").write_text("""---
id: bees-ts1
bees_version: '1.1'
type: task
title: Test Task 1
status: open
created_at: '2026-01-30T12:00:00'
updated_at: '2026-01-30T12:00:00'
---

Task description.""")

        (subtasks_dir / "bees-sb1.md").write_text("""---
id: bees-sb1
bees_version: '1.1'
type: subtask
title: Test Subtask 1
parent: bees-ts1
status: open
created_at: '2026-01-30T13:00:00'
updated_at: '2026-01-30T13:00:00'
---

Subtask description.""")

        result = scan_tickets()

        assert len(result["epic"]) == 2
        assert len(result["task"]) == 1
        assert len(result["subtask"]) == 1

        # Verify ticket IDs
        epic_ids = [t.id for t in result["epic"]]
        assert "default.bees-ep1" in epic_ids
        assert "default.bees-ep2" in epic_ids

        assert result["task"][0].id == "default.bees-ts1"
        assert result["subtask"][0].id == "default.bees-sb1"''',
        '''    def test_scan_tickets_with_mixed_types(self, tmp_path, monkeypatch):
        """Should group tickets by type correctly."""
        import json
        monkeypatch.chdir(tmp_path)
        
        # Create hive directory with flat storage
        hive_dir = tmp_path / "default"
        hive_dir.mkdir()

        # Create sample tickets in hive root (flat storage)
        (hive_dir / "default.bees-ep1.md").write_text("""---
id: default.bees-ep1
type: epic
title: Test Epic 1
status: open
bees_version: '1.1'
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Epic description.""")

        (hive_dir / "default.bees-ep2.md").write_text("""---
id: default.bees-ep2
type: epic
title: Test Epic 2
status: closed
bees_version: '1.1'
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Another epic.""")

        (hive_dir / "default.bees-ts1.md").write_text("""---
id: default.bees-ts1
type: task
title: Test Task 1
status: open
bees_version: '1.1'
created_at: '2026-01-30T12:00:00'
updated_at: '2026-01-30T12:00:00'
---

Task description.""")

        (hive_dir / "default.bees-sb1.md").write_text("""---
id: default.bees-sb1
type: subtask
title: Test Subtask 1
parent: default.bees-ts1
status: open
bees_version: '1.1'
created_at: '2026-01-30T13:00:00'
updated_at: '2026-01-30T13:00:00'
---

Subtask description.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "default": {
                    "path": str(hive_dir),
                    "display_name": "Default"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))

        result = scan_tickets()

        assert len(result["epic"]) == 2
        assert len(result["task"]) == 1
        assert len(result["subtask"]) == 1

        # Verify ticket IDs
        epic_ids = [t.id for t in result["epic"]]
        assert "default.bees-ep1" in epic_ids
        assert "default.bees-ep2" in epic_ids

        assert result["task"][0].id == "default.bees-ts1"
        assert result["subtask"][0].id == "default.bees-sb1"'''
    )
    
    test_file.write_text(content)
    print("Applied comprehensive fixes to test_index_generator.py")

if __name__ == "__main__":
    fix_test_index_generator()
