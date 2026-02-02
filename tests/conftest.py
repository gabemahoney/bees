"""Pytest configuration and fixtures for Bees tests."""

import json
import pytest
from pathlib import Path


@pytest.fixture
def isolated_bees_env(tmp_path, monkeypatch):
    """
    Create an isolated Bees environment for testing.
    
    Sets up:
    - Changes to tmp_path directory
    - Creates .bees/ directory
    - Returns helper object for creating hives and config
    """
    monkeypatch.chdir(tmp_path)
    bees_dir = tmp_path / ".bees"
    bees_dir.mkdir()
    
    class BeesTestHelper:
        def __init__(self, base_path):
            self.base_path = base_path
            self.hives = {}
            
        def create_hive(self, hive_name: str, display_name: str | None = None):
            """Create a hive directory and register it."""
            hive_dir = self.base_path / hive_name
            hive_dir.mkdir(exist_ok=True)
            self.hives[hive_name] = {
                "path": str(hive_dir),
                "display_name": display_name or hive_name.title()
            }
            return hive_dir
            
        def write_config(self):
            """Write .bees/config.json with registered hives."""
            config = {
                "hives": self.hives,
                "allow_cross_hive_dependencies": False,
                "schema_version": "1.0"
            }
            config_path = self.base_path / ".bees" / "config.json"
            config_path.write_text(json.dumps(config, indent=2))
            
        def create_ticket(self, hive_dir: Path, ticket_id: str, ticket_type: str, 
                         title: str, status: str = "open", **extra_fields):
            """Create a ticket file with proper structure."""
            frontmatter = {
                "id": ticket_id,
                "type": ticket_type,
                "title": title,
                "status": status,
                "bees_version": "1.1",
                "created_at": "2026-01-30T10:00:00",
                "updated_at": "2026-01-30T10:00:00",
                **extra_fields
            }
            
            yaml_lines = ["---"]
            for key, value in frontmatter.items():
                if isinstance(value, str):
                    yaml_lines.append(f"{key}: '{value}'" if ':' in value or value.startswith("'") else f"{key}: {value}")
                else:
                    yaml_lines.append(f"{key}: {value}")
            yaml_lines.append("---")
            yaml_lines.append("")
            yaml_lines.append(f"{title} body content.")
            
            ticket_file = hive_dir / f"{ticket_id}.md"
            ticket_file.write_text('\n'.join(yaml_lines))
            return ticket_file
    
    helper = BeesTestHelper(tmp_path)
    yield helper
    
    # Optional: cleanup happens automatically with tmp_path
