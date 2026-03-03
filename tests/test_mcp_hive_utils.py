"""
Unit tests for hive utility functions.

PURPOSE:
Tests hive-related utilities including path validation, hive discovery
via .hive markers, and hive configuration access.

SCOPE - Tests that belong here:
- validate_hive_path(): Path validation (absolute, within repo, exists)
- scan_for_hive(): .hive marker discovery and parsing
- get_hive_config(): Retrieve HiveConfig for a specific hive
- load_hives_config(): Load all hive configurations
- Security checks (symlink handling, path escaping)
- .hive/identity.json parsing
- Error handling: missing markers, malformed files, invalid paths

SCOPE - Tests that DON'T belong here:
- Hive creation -> test_colonize_hive.py
- Repository root detection -> test_mcp_repo_utils.py
- MCP integration tests -> test_mcp_scan_validate.py (uses these utilities)

RELATED FILES:
- test_mcp_scan_validate.py: Integration tests using these utilities
- test_colonize_hive.py: Creates .hive markers
- test_mcp_repo_utils.py: Repository detection utilities
"""

import json

import pytest

from src.config import set_test_config_override
from src.hive_utils import get_hive_config, load_hives_config
from src.mcp_hive_utils import scan_for_hive, validate_hive_path
from src.repo_context import repo_root_context
from tests.conftest import write_scoped_config

# Tests for validate_hive_path()


@pytest.mark.parametrize(
    "subpath",
    [
        "tickets/backend",
        "tickets-with-dashes/backend_underscore",
        "tickets/backend_\u4e2d\u6587",
        "my tickets/backend team",
        "hive",
    ],
    ids=["basic", "special-chars", "unicode", "spaces", "repo-root"],
)
def test_validate_hive_path_accepts_valid_absolute_paths(tmp_path, subpath):
    """Test validate_hive_path accepts various valid absolute paths within repo."""
    repo_root = tmp_path
    hive_path = repo_root / subpath
    hive_path.parent.mkdir(parents=True, exist_ok=True)

    with repo_root_context(repo_root):
        result = validate_hive_path(str(hive_path))

    assert result == hive_path.resolve()


def test_validate_hive_path_rejects_relative_path(tmp_path):
    """Test validate_hive_path raises ValueError for relative paths."""
    repo_root = tmp_path

    with repo_root_context(repo_root):
        with pytest.raises(ValueError, match="Hive path must be absolute"):
            validate_hive_path("tickets/backend")


def test_validate_hive_path_rejects_path_outside_repo(tmp_path):
    """Test validate_hive_path raises ValueError for paths outside repo root."""
    repo_root = tmp_path / "myrepo"
    repo_root.mkdir()
    outside_path = tmp_path / "other" / "location"
    outside_path.mkdir(parents=True)

    with repo_root_context(repo_root):
        with pytest.raises(ValueError, match="Hive path must be within repository root"):
            validate_hive_path(str(outside_path))


def test_validate_hive_path_creates_parent_if_missing(tmp_path):
    """Test validate_hive_path creates parent directory if it doesn't exist."""
    repo_root = tmp_path
    hive_path = repo_root / "deeply" / "nested" / "tickets" / "backend"

    assert not hive_path.parent.exists()

    with repo_root_context(repo_root):
        result = validate_hive_path(str(hive_path))

    assert hive_path.parent.exists()
    assert result == hive_path.resolve()


def test_validate_hive_path_normalizes_trailing_slashes(tmp_path):
    """Test validate_hive_path removes trailing slashes."""
    repo_root = tmp_path
    hive_path = repo_root / "tickets" / "backend"
    hive_path.parent.mkdir(parents=True, exist_ok=True)

    with repo_root_context(repo_root):
        result = validate_hive_path(str(hive_path) + "/")

    assert not str(result).endswith("/")
    assert result == hive_path.resolve()


def test_validate_hive_path_handles_symlinks(tmp_path):
    """Test validate_hive_path resolves symlinks correctly."""
    repo_root = tmp_path
    actual_dir = repo_root / "actual_tickets"
    actual_dir.mkdir()
    symlink_path = repo_root / "link_tickets"
    symlink_path.symlink_to(actual_dir)

    with repo_root_context(repo_root):
        result = validate_hive_path(str(symlink_path))

    assert result == actual_dir.resolve()


# Tests for scan_for_hive()


def _setup_hive_with_marker(mock_global_bees_dir, repo_root, hive_dir, normalized_name, display_name):
    """Helper to create a hive with .hive marker and scoped config."""
    hive_dir.mkdir(parents=True, exist_ok=True)
    hive_marker = hive_dir / ".hive"
    hive_marker.mkdir(exist_ok=True)
    identity_data = {
        "normalized_name": normalized_name,
        "display_name": display_name,
        "created_at": "2026-02-03T12:00:00",
        "version": "0.1",
    }
    with open(hive_marker / "identity.json", "w") as f:
        json.dump(identity_data, f)

    scope_data = {
        "hives": {
            normalized_name: {
                "path": str(hive_dir),
                "display_name": display_name,
                "created_at": "2026-02-03T12:00:00",
            }
        },
        "child_tiers": {},
    }
    write_scoped_config(mock_global_bees_dir, repo_root, scope_data)


@pytest.mark.needs_real_git_check
def test_scan_for_hive_finds_hive_with_marker(tmp_path, monkeypatch, mock_global_bees_dir):
    """Test scan_for_hive finds hive by .hive marker."""
    repo_root = tmp_path
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(repo_root)

    hive_dir = repo_root / "tickets" / "backend"
    _setup_hive_with_marker(mock_global_bees_dir, repo_root, hive_dir, "backend", "Backend")

    result = scan_for_hive("backend")
    assert result == hive_dir


@pytest.mark.needs_real_git_check
def test_scan_for_hive_returns_none_when_not_found(tmp_path, monkeypatch, mock_global_bees_dir):
    """Test scan_for_hive returns None when hive not found."""
    repo_root = tmp_path
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(repo_root)

    assert scan_for_hive("nonexistent") is None


@pytest.mark.needs_real_git_check
def test_scan_for_hive_raises_outside_git_repo(tmp_path, monkeypatch, mock_global_bees_dir):
    """Test scan_for_hive returns None when no hive found outside git repository."""
    monkeypatch.chdir(tmp_path)

    result = scan_for_hive("backend")
    assert result is None


@pytest.mark.needs_real_git_check
def test_scan_for_hive_respects_depth_limit(tmp_path, monkeypatch, mock_global_bees_dir, caplog):
    """Test scan_for_hive skips markers beyond depth limit."""
    import logging

    repo_root = tmp_path
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(repo_root)

    deep_dir = repo_root
    for i in range(12):
        deep_dir = deep_dir / f"level{i}"
    deep_dir.mkdir(parents=True)
    hive_marker = deep_dir / ".hive"
    hive_marker.mkdir()
    with open(hive_marker / "identity.json", "w") as f:
        json.dump(
            {"normalized_name": "deep", "display_name": "Deep", "created_at": "2026-02-03T12:00:00", "version": "0.1"},
            f,
        )

    with caplog.at_level(logging.DEBUG):
        result = scan_for_hive("deep")

    assert result is None
    assert any("beyond depth limit" in record.message for record in caplog.records)


@pytest.mark.needs_real_git_check
def test_scan_for_hive_handles_malformed_identity_json(tmp_path, monkeypatch, mock_global_bees_dir, caplog):
    """Test scan_for_hive handles malformed identity.json gracefully."""
    import logging

    repo_root = tmp_path
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(repo_root)

    hive_dir = repo_root / "tickets"
    hive_marker = hive_dir / ".hive"
    hive_marker.mkdir(parents=True)
    with open(hive_marker / "identity.json", "w") as f:
        f.write("{ invalid json }")

    with caplog.at_level(logging.WARNING):
        result = scan_for_hive("backend")

    assert result is None
    assert any("Could not read identity" in record.message for record in caplog.records)


@pytest.mark.needs_real_git_check
def test_scan_for_hive_finds_hive_in_subdirectory(tmp_path, monkeypatch, mock_global_bees_dir):
    """Test scan_for_hive recursively searches subdirectories."""
    repo_root = tmp_path
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(repo_root)

    hive_dir = repo_root / "docs" / "tickets" / "features"
    _setup_hive_with_marker(mock_global_bees_dir, repo_root, hive_dir, "features", "Features")

    result = scan_for_hive("features")
    assert result == hive_dir


@pytest.mark.needs_real_git_check
def test_scan_for_hive_respects_in_memory_override(tmp_path, monkeypatch, mock_global_bees_dir):
    """scan_for_hive uses load_global_config() which respects set_test_config_override."""
    repo_root = tmp_path
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(repo_root)

    hive_dir = repo_root / "tickets" / "backend"
    hive_dir.mkdir(parents=True)
    hive_marker = hive_dir / ".hive"
    hive_marker.mkdir()
    with open(hive_marker / "identity.json", "w") as f:
        json.dump(
            {"normalized_name": "backend", "display_name": "Backend", "created_at": "2026-02-03T12:00:00"},
            f,
        )

    override_config = {
        "scopes": {
            str(repo_root): {
                "hives": {
                    "backend": {
                        "path": str(hive_dir),
                        "display_name": "Backend",
                        "created_at": "2026-02-03T12:00:00",
                    }
                },
                "child_tiers": {},
            }
        },
        "schema_version": "2.0",
    }
    try:
        set_test_config_override(override_config)
        result = scan_for_hive("backend")
        assert result == hive_dir
    finally:
        set_test_config_override(None)


# Tests for get_hive_config() and load_hives_config()


class TestGetHiveConfig:
    """Tests for get_hive_config function."""

    def test_get_hive_config_existing_and_by_display_name(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test getting config for an existing hive, including normalization."""
        monkeypatch.chdir(tmp_path)

        from src.repo_context import repo_root_context
        from tests.conftest import write_scoped_config

        scope_data = {
            "hives": {
                "backend": {
                    "path": str(tmp_path / "backend"),
                    "display_name": "Backend",
                    "created_at": "2026-02-01T10:00:00",
                }
            },
            "child_tiers": {},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        with repo_root_context(tmp_path):
            # By normalized name
            result = get_hive_config("backend")
            assert result is not None
            assert result["path"] == str(tmp_path / "backend")
            assert result["display_name"] == "Backend"

            # By display name (should normalize)
            result = get_hive_config("Backend")
            assert result is not None
            assert result["path"] == str(tmp_path / "backend")

    @pytest.mark.parametrize(
        "setup_config,hive_name",
        [
            pytest.param(True, "nonexistent", id="nonexistent_hive"),
            pytest.param(False, "backend", id="no_config_file"),
        ],
    )
    def test_get_hive_config_returns_none(self, tmp_path, monkeypatch, setup_config, hive_name):
        """Test getting config returns None when hive or config missing."""
        monkeypatch.chdir(tmp_path)
        if setup_config:
            bees_dir = tmp_path / ".bees"
            bees_dir.mkdir()
            with open(bees_dir / "config.json", "w") as f:
                json.dump({"hives": {}, "schema_version": "1.0"}, f)
        assert get_hive_config(hive_name) is None


class TestLoadHivesConfig:
    """Tests for load_hives_config function."""

    def test_load_hives_config_existing(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test loading existing config."""
        monkeypatch.chdir(tmp_path)

        from src.repo_context import repo_root_context
        from tests.conftest import write_scoped_config

        scope_data = {
            "hives": {
                "backend": {
                    "path": str(tmp_path / "backend"),
                    "display_name": "Backend",
                    "created_at": "2026-02-01T10:00:00",
                }
            },
            "child_tiers": {},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        with repo_root_context(tmp_path):
            loaded = load_hives_config()
            assert loaded is not None
            assert len(loaded.hives) == 1
            assert "backend" in loaded.hives

    def test_load_hives_config_nonexistent(self, tmp_path, monkeypatch):
        """Test loading config when file doesn't exist returns None."""
        monkeypatch.chdir(tmp_path)
        assert load_hives_config() is None
