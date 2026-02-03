#!/usr/bin/env python3
"""Mass fix for test_index_generator.py remaining failures."""

import re
from pathlib import Path

test_file = Path("tests/test_index_generator.py")
content = test_file.read_text()

# Fix test_scan_tickets_combined_filters
content = content.replace(
    '''    def test_scan_tickets_combined_filters(self, tmp_path, monkeypatch):
        """Should apply both status and type filters."""
        tickets_dir = tmp_path / "tickets"
        epics_dir = tickets_dir / "epics"
        tasks_dir = tickets_dir / "tasks"
        epics_dir.mkdir(parents=True)
        tasks_dir.mkdir(parents=True)

        # Create diverse tickets
        (epics_dir / "bees-ep1.md").write_text("""---
id: bees-ep1
bees_version: '1.1'
type: epic
title: Open Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Open epic.""")

        (epics_dir / "bees-ep2.md").write_text("""---
id: bees-ep2
bees_version: '1.1'
type: epic
title: Completed Epic
status: completed
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Completed epic.""")

        (tasks_dir / "bees-ts1.md").write_text("""---
id: bees-ts1
bees_version: '1.1'
type: task
title: Open Task
status: open
created_at: '2026-01-30T12:00:00'
updated_at: '2026-01-30T12:00:00'
---

Open task.""")

        # Filter for open epics only
        result = scan_tickets(status_filter='open', type_filter='epic')
        assert len(result["epic"]) == 1
        assert len(result["task"]) == 0
        assert result["epic"][0].id == "default.bees-ep1"

        # Filter for completed tasks (should be empty)
        result = scan_tickets(status_filter='completed', type_filter='task')
        assert len(result["epic"]) == 0
        assert len(result["task"]) == 0''',
    '''    def test_scan_tickets_combined_filters(self, tmp_path, monkeypatch):
        """Should apply both status and type filters."""
        import json
        monkeypatch.chdir(tmp_path)
        
        hive_dir = tmp_path / "default"
        hive_dir.mkdir()

        # Create diverse tickets
        (hive_dir / "default.bees-ep1.md").write_text("""---
id: default.bees-ep1
type: epic
title: Open Epic
status: open
bees_version: '1.1'
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Open epic.""")

        (hive_dir / "default.bees-ep2.md").write_text("""---
id: default.bees-ep2
type: epic
title: Completed Epic
status: completed
bees_version: '1.1'
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Completed epic.""")

        (hive_dir / "default.bees-ts1.md").write_text("""---
id: default.bees-ts1
type: task
title: Open Task
status: open
bees_version: '1.1'
created_at: '2026-01-30T12:00:00'
updated_at: '2026-01-30T12:00:00'
---

Open task.""")

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

        # Filter for open epics only
        result = scan_tickets(status_filter='open', type_filter='epic')
        assert len(result["epic"]) == 1
        assert len(result["task"]) == 0
        assert result["epic"][0].id == "default.bees-ep1"

        # Filter for completed tasks (should be empty)
        result = scan_tickets(status_filter='completed', type_filter='task')
        assert len(result["epic"]) == 0
        assert len(result["task"]) == 0'''
)

test_file.write_text(content)
print("Fixed test_scan_tickets_combined_filters")
