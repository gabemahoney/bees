"""
Unit tests for hive config registration functions.

Tests load_hive_config_dict(), write_hive_config_dict(), and register_hive_dict()
functions for atomic write behavior, error handling, and integration with
colonize_hive workflow.
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, mock_open, MagicMock
from src.config import (
    load_hive_config_dict,
    write_hive_config_dict,
    register_hive_dict
)
from src.mcp_server import colonize_hive


class TestLoadHiveConfigDict:
    """Tests for load_hive_config_dict() function."""

    def test_load_missing_file_returns_default_structure(self, tmp_path, monkeypatch):
        """Test that load_hive_config_dict returns default structure when config.json doesn't exist."""
        monkeypatch.chdir(tmp_path)

        result = load_hive_config_dict()

        assert result == {
            'hives': {},
            'allow_cross_hive_dependencies': False,
            'schema_version': '1.0'
        }

    def test_load_valid_json(self, tmp_path, monkeypatch):
        """Test loading valid config.json file."""
        monkeypatch.chdir(tmp_path)

        # Create config file
        config_dir = tmp_path / '.bees'
        config_dir.mkdir()
        config_file = config_dir / 'config.json'

        config_data = {
            'hives': {
                'backend': {
                    'path': '/path/to/backend',
                    'display_name': 'Backend',
                    'created_at': '2026-02-01T12:00:00'
                }
            },
            'allow_cross_hive_dependencies': False,
            'schema_version': '1.0'
        }
        config_file.write_text(json.dumps(config_data))

        result = load_hive_config_dict()

        assert result == config_data
        assert 'backend' in result['hives']
        assert result['hives']['backend']['display_name'] == 'Backend'

    def test_load_malformed_json_returns_default(self, tmp_path, monkeypatch, caplog):
        """Test that malformed JSON returns default structure."""
        monkeypatch.chdir(tmp_path)

        # Create malformed config file
        config_dir = tmp_path / '.bees'
        config_dir.mkdir()
        config_file = config_dir / 'config.json'
        config_file.write_text("{invalid json")

        result = load_hive_config_dict()

        assert result == {
            'hives': {},
            'allow_cross_hive_dependencies': False,
            'schema_version': '1.0'
        }

    def test_load_io_error_returns_default(self, tmp_path, monkeypatch, caplog):
        """Test that IOError returns default structure."""
        monkeypatch.chdir(tmp_path)

        # Create config dir and file
        config_dir = tmp_path / '.bees'
        config_dir.mkdir()
        config_file = config_dir / 'config.json'
        config_file.write_text('{}')

        # Make file unreadable
        config_file.chmod(0o000)

        try:
            result = load_hive_config_dict()

            assert result == {
                'hives': {},
                'allow_cross_hive_dependencies': False,
                'schema_version': '1.0'
            }
        finally:
            # Restore permissions for cleanup
            config_file.chmod(0o644)

    def test_load_empty_file(self, tmp_path, monkeypatch):
        """Test loading empty config file."""
        monkeypatch.chdir(tmp_path)

        config_dir = tmp_path / '.bees'
        config_dir.mkdir()
        config_file = config_dir / 'config.json'
        config_file.write_text('{}')

        result = load_hive_config_dict()

        assert isinstance(result, dict)


class TestWriteHiveConfigDict:
    """Tests for write_hive_config_dict() function."""

    def test_write_valid_config(self, tmp_path, monkeypatch):
        """Test writing valid config to file."""
        monkeypatch.chdir(tmp_path)

        config = {
            'hives': {
                'backend': {
                    'path': '/path/to/backend',
                    'display_name': 'Backend',
                    'created_at': '2026-02-01T12:00:00'
                }
            },
            'allow_cross_hive_dependencies': False,
            'schema_version': '1.0'
        }

        write_hive_config_dict(config)

        # Verify file was written
        config_file = tmp_path / '.bees' / 'config.json'
        assert config_file.exists()

        # Verify content
        loaded = json.loads(config_file.read_text())
        assert loaded == config

    def test_write_creates_directory(self, tmp_path, monkeypatch):
        """Test that write_hive_config_dict creates .bees directory if it doesn't exist."""
        monkeypatch.chdir(tmp_path)

        config = {'hives': {}, 'allow_cross_hive_dependencies': False, 'schema_version': '1.0'}

        write_hive_config_dict(config)

        assert (tmp_path / '.bees').exists()
        assert (tmp_path / '.bees' / 'config.json').exists()

    def test_write_formatting(self, tmp_path, monkeypatch):
        """Test that JSON is written with proper indentation."""
        monkeypatch.chdir(tmp_path)

        config = {
            'hives': {'backend': {'path': '/path'}},
            'schema_version': '1.0'
        }

        write_hive_config_dict(config)

        config_file = tmp_path / '.bees' / 'config.json'
        content = config_file.read_text()

        # Check for indentation (should have spaces/newlines)
        assert '\n' in content
        assert '  ' in content  # indent=2

    def test_write_atomic_behavior(self, tmp_path, monkeypatch):
        """Test atomic write behavior using temp file."""
        monkeypatch.chdir(tmp_path)

        config = {'hives': {}, 'schema_version': '1.0'}

        # Write config
        write_hive_config_dict(config)

        # Verify no temp files left behind
        temp_files = list((tmp_path / '.bees').glob('.config.json.*'))
        assert len(temp_files) == 0

    def test_write_permission_error(self, tmp_path, monkeypatch):
        """Test that write_hive_config_dict raises IOError on permission error."""
        monkeypatch.chdir(tmp_path)

        # Create .bees directory and make it read-only
        config_dir = tmp_path / '.bees'
        config_dir.mkdir()
        config_dir.chmod(0o444)

        config = {'hives': {}, 'schema_version': '1.0'}

        try:
            with pytest.raises(IOError, match="Failed to write config"):
                write_hive_config_dict(config)
        finally:
            # Restore permissions for cleanup
            config_dir.chmod(0o755)

    def test_write_overwrites_existing(self, tmp_path, monkeypatch):
        """Test that write_hive_config_dict overwrites existing config file."""
        monkeypatch.chdir(tmp_path)

        config_dir = tmp_path / '.bees'
        config_dir.mkdir()
        config_file = config_dir / 'config.json'

        # Write initial config
        old_config = {'hives': {'old': {'path': '/old'}}, 'schema_version': '1.0'}
        config_file.write_text(json.dumps(old_config))

        # Write new config
        new_config = {'hives': {'new': {'path': '/new'}}, 'schema_version': '1.0'}
        write_hive_config_dict(new_config)

        # Verify new content
        loaded = json.loads(config_file.read_text())
        assert 'new' in loaded['hives']
        assert 'old' not in loaded['hives']


class TestRegisterHiveDict:
    """Tests for register_hive_dict() function."""

    def test_register_adds_hive_entry(self, tmp_path, monkeypatch):
        """Test that register_hive_dict adds new hive entry to config."""
        monkeypatch.chdir(tmp_path)

        timestamp = datetime.now()
        config = register_hive_dict(
            normalized_name='backend',
            display_name='Backend',
            path='/path/to/backend',
            timestamp=timestamp
        )

        assert 'backend' in config['hives']
        assert config['hives']['backend']['path'] == '/path/to/backend'
        assert config['hives']['backend']['display_name'] == 'Backend'
        assert config['hives']['backend']['created_at'] == timestamp.isoformat()

    def test_register_preserves_existing_hives(self, tmp_path, monkeypatch):
        """Test that registering a new hive preserves existing hives."""
        monkeypatch.chdir(tmp_path)

        # Create initial config
        config_dir = tmp_path / '.bees'
        config_dir.mkdir()
        config_file = config_dir / 'config.json'
        initial_config = {
            'hives': {'frontend': {'path': '/frontend', 'display_name': 'Frontend', 'created_at': '2026-01-01'}},
            'schema_version': '1.0'
        }
        config_file.write_text(json.dumps(initial_config))

        # Register new hive
        timestamp = datetime.now()
        config = register_hive_dict(
            normalized_name='backend',
            display_name='Backend',
            path='/backend',
            timestamp=timestamp
        )

        # Verify both hives present
        assert 'frontend' in config['hives']
        assert 'backend' in config['hives']
        assert config['hives']['frontend']['path'] == '/frontend'
        assert config['hives']['backend']['path'] == '/backend'

    def test_register_returns_updated_config(self, tmp_path, monkeypatch):
        """Test that register_hive_dict returns updated config dict."""
        monkeypatch.chdir(tmp_path)

        timestamp = datetime.now()
        config = register_hive_dict(
            normalized_name='test',
            display_name='Test',
            path='/test',
            timestamp=timestamp
        )

        assert isinstance(config, dict)
        assert 'hives' in config
        assert 'schema_version' in config

    def test_register_does_not_persist_to_disk(self, tmp_path, monkeypatch):
        """Test that register_hive_dict doesn't write to disk (caller's responsibility)."""
        monkeypatch.chdir(tmp_path)

        timestamp = datetime.now()
        register_hive_dict(
            normalized_name='test',
            display_name='Test',
            path='/test',
            timestamp=timestamp
        )

        # Config file should not exist yet
        config_file = tmp_path / '.bees' / 'config.json'
        # Either doesn't exist or doesn't contain 'test' hive
        if config_file.exists():
            loaded = json.loads(config_file.read_text())
            # If file exists from load_hive_config_dict, it should be default
            assert 'test' not in loaded.get('hives', {})


class TestColonizeHiveConfigIntegration:
    """Tests for colonize_hive() integration with config registration."""

    @pytest.fixture
    def temp_repo(self, tmp_path, monkeypatch):
        """Create temporary repository structure."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()
        monkeypatch.chdir(repo_root)
        return repo_root

    def test_colonize_registers_hive_in_config(self, temp_repo):
        """Test that colonize_hive successfully registers hive in config.json."""
        hive_path = temp_repo / "tickets"
        hive_path.mkdir()

        result = colonize_hive('Backend', str(hive_path))

        assert result['status'] == 'success'

        # Verify config was written
        config_file = temp_repo / '.bees' / 'config.json'
        assert config_file.exists()

        # Verify config content
        config = json.loads(config_file.read_text())
        assert 'backend' in config['hives']
        assert config['hives']['backend']['path'] == str(hive_path)
        assert config['hives']['backend']['display_name'] == 'Backend'
        assert 'created_at' in config['hives']['backend']

    def test_colonize_handles_config_write_error(self, temp_repo, monkeypatch):
        """Test that colonize_hive handles config write errors gracefully."""
        hive_path = temp_repo / "tickets"
        hive_path.mkdir()

        # Mock write_hive_config_dict to raise IOError
        def mock_write_error(config, repo_root=None):
            raise IOError("Disk full")

        monkeypatch.setattr("src.mcp_server.write_hive_config_dict", mock_write_error)

        result = colonize_hive('Backend', str(hive_path))

        assert result['status'] == 'error'
        assert 'config_write_error' in result['error_type']
        assert 'Disk full' in result['message']

    def test_colonize_handles_permission_error(self, temp_repo, monkeypatch):
        """Test that colonize_hive handles PermissionError when writing config."""
        hive_path = temp_repo / "tickets"
        hive_path.mkdir()

        # Mock write_hive_config_dict to raise PermissionError
        def mock_permission_error(config, repo_root=None):
            raise PermissionError("Permission denied")

        monkeypatch.setattr("src.mcp_server.write_hive_config_dict", mock_permission_error)

        result = colonize_hive('Backend', str(hive_path))

        assert result['status'] == 'error'
        assert 'Permission denied' in result['message']

    def test_colonize_config_includes_timestamp(self, temp_repo):
        """Test that colonize_hive includes timestamp in config entry."""
        hive_path = temp_repo / "tickets"
        hive_path.mkdir()

        before = datetime.now()
        result = colonize_hive('Backend', str(hive_path))
        after = datetime.now()

        assert result['status'] == 'success'

        # Check timestamp in config
        config_file = temp_repo / '.bees' / 'config.json'
        config = json.loads(config_file.read_text())

        created_at = datetime.fromisoformat(config['hives']['backend']['created_at'])
        assert before <= created_at <= after

    def test_colonize_multiple_hives(self, temp_repo):
        """Test colonizing multiple hives updates config correctly."""
        hive1_path = temp_repo / "backend"
        hive1_path.mkdir()
        hive2_path = temp_repo / "frontend"
        hive2_path.mkdir()

        # Colonize first hive
        result1 = colonize_hive('Backend', str(hive1_path))
        assert result1['status'] == 'success'

        # Colonize second hive
        result2 = colonize_hive('Frontend', str(hive2_path))
        assert result2['status'] == 'success'

        # Verify both in config
        config_file = temp_repo / '.bees' / 'config.json'
        config = json.loads(config_file.read_text())

        assert 'backend' in config['hives']
        assert 'frontend' in config['hives']
        assert config['hives']['backend']['path'] == str(hive1_path)
        assert config['hives']['frontend']['path'] == str(hive2_path)
