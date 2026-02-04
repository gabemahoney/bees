"""Tests for MCP hive utilities (path validation and filesystem scanning)."""
import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from src.mcp_hive_utils import validate_hive_path, scan_for_hive
from src.config import BeesConfig, HiveConfig


# Tests for validate_hive_path()

def test_validate_hive_path_with_valid_absolute_path(tmp_path):
    """Test validate_hive_path accepts valid absolute path within repo."""
    repo_root = tmp_path
    hive_path = repo_root / "tickets" / "backend"
    hive_path.parent.mkdir(parents=True, exist_ok=True)

    result = validate_hive_path(str(hive_path), repo_root)

    assert result == hive_path.resolve()


def test_validate_hive_path_rejects_relative_path(tmp_path):
    """Test validate_hive_path raises ValueError for relative paths."""
    repo_root = tmp_path
    relative_path = "tickets/backend"

    with pytest.raises(ValueError, match="Hive path must be absolute"):
        validate_hive_path(relative_path, repo_root)


def test_validate_hive_path_rejects_path_outside_repo(tmp_path):
    """Test validate_hive_path raises ValueError for paths outside repo root."""
    repo_root = tmp_path / "myrepo"
    repo_root.mkdir()
    outside_path = tmp_path / "other" / "location"
    outside_path.mkdir(parents=True)

    with pytest.raises(ValueError, match="Hive path must be within repository root"):
        validate_hive_path(str(outside_path), repo_root)


def test_validate_hive_path_creates_parent_if_missing(tmp_path):
    """Test validate_hive_path creates parent directory if it doesn't exist."""
    repo_root = tmp_path
    hive_path = repo_root / "deeply" / "nested" / "tickets" / "backend"

    # Parent doesn't exist initially
    assert not hive_path.parent.exists()

    result = validate_hive_path(str(hive_path), repo_root)

    # Parent should be created
    assert hive_path.parent.exists()
    assert result == hive_path.resolve()


def test_validate_hive_path_normalizes_trailing_slashes(tmp_path):
    """Test validate_hive_path removes trailing slashes."""
    repo_root = tmp_path
    hive_path = repo_root / "tickets" / "backend"
    hive_path.parent.mkdir(parents=True, exist_ok=True)

    result = validate_hive_path(str(hive_path) + "/", repo_root)

    # Result should not have trailing slash
    assert not str(result).endswith("/")
    assert result == hive_path.resolve()


def test_validate_hive_path_handles_symlinks(tmp_path):
    """Test validate_hive_path resolves symlinks correctly."""
    repo_root = tmp_path
    actual_dir = repo_root / "actual_tickets"
    actual_dir.mkdir()
    symlink_path = repo_root / "link_tickets"
    symlink_path.symlink_to(actual_dir)

    result = validate_hive_path(str(symlink_path), repo_root)

    # Should resolve to actual path
    assert result == actual_dir.resolve()


def test_validate_hive_path_with_special_characters(tmp_path):
    """Test validate_hive_path handles paths with special characters."""
    repo_root = tmp_path
    hive_path = repo_root / "tickets-with-dashes" / "backend_underscore"
    hive_path.parent.mkdir(parents=True, exist_ok=True)

    result = validate_hive_path(str(hive_path), repo_root)

    assert result == hive_path.resolve()


def test_validate_hive_path_accepts_hive_at_repo_root(tmp_path):
    """Test validate_hive_path accepts hive directly at repo root."""
    repo_root = tmp_path
    hive_path = repo_root / "hive"

    result = validate_hive_path(str(hive_path), repo_root)

    assert result == hive_path.resolve()


# Tests for scan_for_hive()

@pytest.mark.needs_real_git_check
def test_scan_for_hive_finds_hive_with_marker(tmp_path, monkeypatch):
    """Test scan_for_hive finds hive by .hive marker."""
    # Create a git repo structure
    repo_root = tmp_path
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(repo_root)

    # Create hive with .hive marker
    hive_dir = repo_root / "tickets" / "backend"
    hive_dir.mkdir(parents=True)
    hive_marker = hive_dir / ".hive"
    hive_marker.mkdir()
    identity_data = {
        "normalized_name": "backend",
        "display_name": "Backend",
        "created_at": "2026-02-03T12:00:00",
        "version": "1.0.0"
    }
    identity_file = hive_marker / "identity.json"
    with open(identity_file, 'w') as f:
        json.dump(identity_data, f)

    # Create config
    config_dir = repo_root / ".bees"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_data = {
        "hives": {
            "backend": {
                "path": str(hive_dir),
                "display_name": "Backend",
                "created_at": "2026-02-03T12:00:00"
            }
        },
        "allow_cross_hive_dependencies": False,
        "schema_version": "1.0"
    }
    with open(config_file, 'w') as f:
        json.dump(config_data, f)

    result = scan_for_hive("backend")

    assert result == hive_dir


@pytest.mark.needs_real_git_check
def test_scan_for_hive_returns_none_when_not_found(tmp_path, monkeypatch):
    """Test scan_for_hive returns None when hive not found."""
    repo_root = tmp_path
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(repo_root)

    result = scan_for_hive("nonexistent")

    assert result is None


@pytest.mark.needs_real_git_check
def test_scan_for_hive_raises_outside_git_repo(tmp_path, monkeypatch):
    """Test scan_for_hive raises ValueError outside git repository."""
    # Don't create .git directory
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="Not in a git repository"):
        scan_for_hive("backend")


@pytest.mark.needs_real_git_check
def test_scan_for_hive_warns_on_missing_identity_file(tmp_path, monkeypatch, caplog):
    """Test scan_for_hive logs warning for .hive marker without identity.json."""
    import logging

    repo_root = tmp_path
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(repo_root)

    # Create hive marker without identity file
    hive_dir = repo_root / "tickets"
    hive_marker = hive_dir / ".hive"
    hive_marker.mkdir(parents=True)

    with caplog.at_level(logging.WARNING):
        result = scan_for_hive("backend")

    assert result is None
    assert any("without identity.json" in record.message for record in caplog.records)


@pytest.mark.needs_real_git_check
def test_scan_for_hive_warns_on_orphaned_marker(tmp_path, monkeypatch, caplog):
    """Test scan_for_hive warns about orphaned .hive markers not in config."""
    import logging

    repo_root = tmp_path
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(repo_root)

    # Create orphaned hive (marker exists but not in config)
    orphan_dir = repo_root / "orphan"
    orphan_marker = orphan_dir / ".hive"
    orphan_marker.mkdir(parents=True)
    identity_data = {
        "normalized_name": "orphan",
        "display_name": "Orphan",
        "created_at": "2026-02-03T12:00:00",
        "version": "1.0.0"
    }
    with open(orphan_marker / "identity.json", 'w') as f:
        json.dump(identity_data, f)

    # Create config without orphan
    config_dir = repo_root / ".bees"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_data = {
        "hives": {},
        "allow_cross_hive_dependencies": False,
        "schema_version": "1.0"
    }
    with open(config_file, 'w') as f:
        json.dump(config_data, f)

    with caplog.at_level(logging.WARNING):
        result = scan_for_hive("backend")

    assert result is None
    assert any("orphaned .hive marker" in record.message for record in caplog.records)


@pytest.mark.needs_real_git_check
def test_scan_for_hive_updates_config_on_recovery(tmp_path, monkeypatch):
    """Test scan_for_hive updates config.json when recovering moved hive."""
    repo_root = tmp_path
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(repo_root)

    # Create hive at new location
    new_hive_dir = repo_root / "new_location" / "backend"
    new_hive_dir.mkdir(parents=True)
    hive_marker = new_hive_dir / ".hive"
    hive_marker.mkdir()
    identity_data = {
        "normalized_name": "backend",
        "display_name": "Backend",
        "created_at": "2026-02-03T12:00:00",
        "version": "1.0.0"
    }
    with open(hive_marker / "identity.json", 'w') as f:
        json.dump(identity_data, f)

    # Create config with old path
    config_dir = repo_root / ".bees"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    old_path = repo_root / "old_location" / "backend"
    config_data = {
        "hives": {
            "backend": {
                "path": str(old_path),
                "display_name": "Backend",
                "created_at": "2026-02-03T12:00:00"
            }
        },
        "allow_cross_hive_dependencies": False,
        "schema_version": "1.0"
    }
    with open(config_file, 'w') as f:
        json.dump(config_data, f)

    result = scan_for_hive("backend")

    assert result == new_hive_dir

    # Verify config was updated
    with open(config_file, 'r') as f:
        updated_config = json.load(f)
    assert updated_config["hives"]["backend"]["path"] == str(new_hive_dir)


@pytest.mark.needs_real_git_check
def test_scan_for_hive_respects_depth_limit(tmp_path, monkeypatch, caplog):
    """Test scan_for_hive skips markers beyond depth limit."""
    import logging

    repo_root = tmp_path
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(repo_root)

    # Create deeply nested hive (beyond MAX_SCAN_DEPTH=10)
    deep_dir = repo_root
    for i in range(12):
        deep_dir = deep_dir / f"level{i}"
    deep_dir.mkdir(parents=True)
    hive_marker = deep_dir / ".hive"
    hive_marker.mkdir()
    identity_data = {
        "normalized_name": "deep",
        "display_name": "Deep",
        "created_at": "2026-02-03T12:00:00",
        "version": "1.0.0"
    }
    with open(hive_marker / "identity.json", 'w') as f:
        json.dump(identity_data, f)

    with caplog.at_level(logging.DEBUG):
        result = scan_for_hive("deep")

    assert result is None
    # Should log that it's skipping the deep marker
    assert any("beyond depth limit" in record.message for record in caplog.records)


@pytest.mark.needs_real_git_check
def test_scan_for_hive_with_config_parameter(tmp_path, monkeypatch):
    """Test scan_for_hive accepts optional config parameter."""
    repo_root = tmp_path
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(repo_root)

    # Create hive
    hive_dir = repo_root / "tickets"
    hive_marker = hive_dir / ".hive"
    hive_marker.mkdir(parents=True)
    identity_data = {
        "normalized_name": "tickets",
        "display_name": "Tickets",
        "created_at": "2026-02-03T12:00:00",
        "version": "1.0.0"
    }
    with open(hive_marker / "identity.json", 'w') as f:
        json.dump(identity_data, f)

    # Create config object
    hive_config = HiveConfig(
        path=str(hive_dir),
        display_name="Tickets",
        created_at="2026-02-03T12:00:00"
    )
    config = BeesConfig(
        hives={"tickets": hive_config},
        allow_cross_hive_dependencies=False,
        schema_version="1.0"
    )

    # Create config file for scan_for_hive to update
    config_dir = repo_root / ".bees"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_data = {
        "hives": {
            "tickets": {
                "path": str(hive_dir),
                "display_name": "Tickets",
                "created_at": "2026-02-03T12:00:00"
            }
        },
        "allow_cross_hive_dependencies": False,
        "schema_version": "1.0"
    }
    with open(config_file, 'w') as f:
        json.dump(config_data, f)

    result = scan_for_hive("tickets", config=config)

    assert result == hive_dir


@pytest.mark.needs_real_git_check
def test_scan_for_hive_handles_malformed_identity_json(tmp_path, monkeypatch, caplog):
    """Test scan_for_hive handles malformed identity.json gracefully."""
    import logging

    repo_root = tmp_path
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(repo_root)

    # Create hive with malformed identity file
    hive_dir = repo_root / "tickets"
    hive_marker = hive_dir / ".hive"
    hive_marker.mkdir(parents=True)
    identity_file = hive_marker / "identity.json"
    with open(identity_file, 'w') as f:
        f.write("{ invalid json }")

    with caplog.at_level(logging.WARNING):
        result = scan_for_hive("backend")

    assert result is None
    assert any("Could not read identity" in record.message for record in caplog.records)


@pytest.mark.needs_real_git_check
def test_scan_for_hive_finds_hive_in_subdirectory(tmp_path, monkeypatch):
    """Test scan_for_hive recursively searches subdirectories."""
    repo_root = tmp_path
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(repo_root)

    # Create hive in nested subdirectory
    hive_dir = repo_root / "docs" / "tickets" / "features"
    hive_dir.mkdir(parents=True)
    hive_marker = hive_dir / ".hive"
    hive_marker.mkdir()
    identity_data = {
        "normalized_name": "features",
        "display_name": "Features",
        "created_at": "2026-02-03T12:00:00",
        "version": "1.0.0"
    }
    with open(hive_marker / "identity.json", 'w') as f:
        json.dump(identity_data, f)

    # Create config
    config_dir = repo_root / ".bees"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_data = {
        "hives": {
            "features": {
                "path": str(hive_dir),
                "display_name": "Features",
                "created_at": "2026-02-03T12:00:00"
            }
        },
        "allow_cross_hive_dependencies": False,
        "schema_version": "1.0"
    }
    with open(config_file, 'w') as f:
        json.dump(config_data, f)

    result = scan_for_hive("features")

    assert result == hive_dir


# Edge case tests

def test_validate_hive_path_with_unicode_characters(tmp_path):
    """Test validate_hive_path handles Unicode characters in paths."""
    repo_root = tmp_path
    hive_path = repo_root / "tickets" / "backend_中文"
    hive_path.parent.mkdir(parents=True, exist_ok=True)

    result = validate_hive_path(str(hive_path), repo_root)

    assert result == hive_path.resolve()


def test_validate_hive_path_with_spaces(tmp_path):
    """Test validate_hive_path handles spaces in path."""
    repo_root = tmp_path
    hive_path = repo_root / "my tickets" / "backend team"
    hive_path.parent.mkdir(parents=True, exist_ok=True)

    result = validate_hive_path(str(hive_path), repo_root)

    assert result == hive_path.resolve()
