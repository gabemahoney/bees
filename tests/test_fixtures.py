"""
Demonstration tests for pytest fixtures in conftest.py.

These tests serve dual purposes:
1. Verify each fixture creates the expected structure
2. Provide usage examples for developers writing new tests
"""

import json
from pathlib import Path


def test_bees_repo_fixture(bees_repo):
    """
    Demonstrate bees_repo fixture usage.
    
    Fixture: bees_repo
    Purpose: Creates minimal bees repository with .bees directory
    Returns: repo_root (Path)
    
    Use Case: Foundation for tests that need a bare repo structure
    """
    repo_root = bees_repo
    
    # Verify .bees directory exists
    bees_dir = repo_root / ".bees"
    assert bees_dir.exists(), ".bees directory should exist"
    assert bees_dir.is_dir(), ".bees should be a directory"
    
    # Verify we have a valid Path object
    assert isinstance(repo_root, Path), "bees_repo should return Path object"
    
    # Verify it's a temporary directory (typical test pattern)
    repo_str_lower = str(repo_root).lower()
    assert ("tmp" in repo_str_lower or "temp" in repo_str_lower or 
            "pytest" in repo_str_lower), \
        "Should be using temporary directory for isolation"


def test_single_hive_fixture(single_hive):
    """
    Demonstrate single_hive fixture usage.
    
    Fixture: single_hive
    Purpose: Creates repo with one configured hive ('backend')
    Returns: (repo_root, hive_path)
    
    Use Case: Tests needing a single hive with proper configuration
    """
    repo_root, hive_path = single_hive
    
    # Verify hive directory exists
    assert hive_path.exists(), "Hive directory should exist"
    assert hive_path.is_dir(), "Hive path should be a directory"
    assert hive_path.name == "backend", "Hive should be named 'backend'"
    
    # Verify .hive identity marker exists
    identity_path = hive_path / ".hive" / "identity.json"
    assert identity_path.exists(), ".hive/identity.json should exist"
    
    # Verify identity structure
    with open(identity_path) as f:
        identity = json.load(f)
    assert identity["normalized_name"] == "backend", "Normalized name should be 'backend'"
    assert identity["display_name"] == "Backend", "Display name should be 'Backend'"
    assert "created_at" in identity, "Identity should have created_at timestamp"
    
    # Verify hive is registered in config
    config_path = repo_root / ".bees" / "config.json"
    assert config_path.exists(), "config.json should exist"
    
    with open(config_path) as f:
        config = json.load(f)
    assert "backend" in config["hives"], "Backend hive should be registered"
    assert config["hives"]["backend"]["display_name"] == "Backend"
    assert config["hives"]["backend"]["path"] == str(hive_path)


def test_multi_hive_fixture(multi_hive):
    """
    Demonstrate multi_hive fixture usage.
    
    Fixture: multi_hive
    Purpose: Creates repo with multiple hives ('backend' and 'frontend')
    Returns: (repo_root, backend_path, frontend_path)
    
    Use Case: Tests verifying cross-hive operations or multi-hive queries
    """
    repo_root, backend_path, frontend_path = multi_hive
    
    # Verify both hive directories exist
    assert backend_path.exists(), "Backend hive directory should exist"
    assert frontend_path.exists(), "Frontend hive directory should exist"
    assert backend_path.name == "backend", "Backend hive should be named 'backend'"
    assert frontend_path.name == "frontend", "Frontend hive should be named 'frontend'"
    
    # Verify both hives have identity markers
    backend_identity = backend_path / ".hive" / "identity.json"
    frontend_identity = frontend_path / ".hive" / "identity.json"
    assert backend_identity.exists(), "Backend .hive/identity.json should exist"
    assert frontend_identity.exists(), "Frontend .hive/identity.json should exist"
    
    # Verify backend identity
    with open(backend_identity) as f:
        backend_data = json.load(f)
    assert backend_data["normalized_name"] == "backend"
    assert backend_data["display_name"] == "Backend"
    
    # Verify frontend identity
    with open(frontend_identity) as f:
        frontend_data = json.load(f)
    assert frontend_data["normalized_name"] == "frontend"
    assert frontend_data["display_name"] == "Frontend"
    
    # Verify both hives registered in config
    config_path = repo_root / ".bees" / "config.json"
    with open(config_path) as f:
        config = json.load(f)
    
    assert len(config["hives"]) == 2, "Should have exactly 2 hives"
    assert "backend" in config["hives"], "Backend should be registered"
    assert "frontend" in config["hives"], "Frontend should be registered"
    assert config["hives"]["backend"]["path"] == str(backend_path)
    assert config["hives"]["frontend"]["path"] == str(frontend_path)


def test_hive_with_tickets_fixture(hive_with_tickets):
    """
    Demonstrate hive_with_tickets fixture usage.
    
    Fixture: hive_with_tickets
    Purpose: Creates repo with pre-populated Epic → Task → Subtask hierarchy
    Returns: (repo_root, hive_path, epic_id, task_id, subtask_id)
    
    Use Case: Tests verifying ticket relationships, queries, or hierarchy operations
    """
    from src.reader import read_ticket
    from src.paths import get_ticket_path
    
    repo_root, hive_path, epic_id, task_id, subtask_id = hive_with_tickets
    
    # Verify all ticket IDs are valid strings with correct format
    assert epic_id.startswith("backend.bees-"), "Epic ID should have backend prefix"
    assert task_id.startswith("backend.bees-"), "Task ID should have backend prefix"
    assert subtask_id.startswith("backend.bees-"), "Subtask ID should have backend prefix"
    
    # Verify ticket files exist
    epic_file = hive_path / f"{epic_id}.md"
    task_file = hive_path / f"{task_id}.md"
    subtask_file = hive_path / f"{subtask_id}.md"
    assert epic_file.exists(), f"Epic file {epic_file} should exist"
    assert task_file.exists(), f"Task file {task_file} should exist"
    assert subtask_file.exists(), f"Subtask file {subtask_file} should exist"
    
    # Verify Epic structure
    epic = read_ticket(get_ticket_path(epic_id, "epic"))
    assert epic.type == "epic", "First ticket should be an epic"
    assert epic.title == "Test Epic", "Epic should have correct title"
    assert epic.parent is None, "Epic should not have parent"
    
    # Verify Task structure and parent relationship
    task = read_ticket(get_ticket_path(task_id, "task"))
    assert task.type == "task", "Second ticket should be a task"
    assert task.title == "Test Task", "Task should have correct title"
    assert task.parent == epic_id, "Task should have epic as parent"
    
    # Verify Subtask structure and parent relationship
    subtask = read_ticket(get_ticket_path(subtask_id, "subtask"))
    assert subtask.type == "subtask", "Third ticket should be a subtask"
    assert subtask.title == "Test Subtask", "Subtask should have correct title"
    assert subtask.parent == task_id, "Subtask should have task as parent"
    
    # Note: This fixture creates tickets with parent fields set (child→parent direction)
    # but does not sync bidirectional relationships (parent→child children arrays).
    # For full bidirectional relationships, use MCP functions or call
    # _update_bidirectional_relationships() after ticket creation.
