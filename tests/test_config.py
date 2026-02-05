"""Tests for configuration loading and parsing."""

import json
import pytest
from pathlib import Path
import yaml

from src.config import (
    Config, load_config, get_config,
    BeesConfig, HiveConfig,
    load_bees_config, save_bees_config, init_bees_config_if_needed,
    get_config_path, ensure_bees_dir, validate_unique_hive_name,
    load_hive_config_dict, write_hive_config_dict, register_hive_dict
)
from src.id_utils import normalize_hive_name
from src.repo_context import repo_root_context, set_repo_root, reset_repo_root


@pytest.fixture(autouse=True)
def setup_repo_context(tmp_path, monkeypatch):
    """Automatically set up repo_root context for all tests in this file."""
    # Set the context before each test
    token = set_repo_root(tmp_path)
    yield
    # Reset the context after each test
    reset_repo_root(token)


class TestConfig:
    """Test Config class initialization and attribute access."""

    def test_config_with_http_section(self):
        """Test Config initialization with http section."""
        config_data = {
            'http': {
                'host': '192.168.1.1',
                'port': 9000
            },
            'ticket_directory': './custom_tickets'
        }
        config = Config(config_data)

        assert config.http_host == '192.168.1.1'
        assert config.http_port == 9000
        assert config.ticket_directory == './custom_tickets'

    def test_config_with_missing_http_section(self):
        """Test Config uses defaults when http section missing."""
        config_data = {
            'ticket_directory': './tickets'
        }
        config = Config(config_data)

        assert config.http_host == '127.0.0.1'
        assert config.http_port == 8000
        assert config.ticket_directory == './tickets'

    def test_config_with_partial_http_section(self):
        """Test Config uses defaults for missing http fields."""
        config_data = {
            'http': {
                'host': '0.0.0.0'
                # port missing
            }
        }
        config = Config(config_data)

        assert config.http_host == '0.0.0.0'
        assert config.http_port == 8000  # default

    def test_config_with_empty_dict(self):
        """Test Config with empty config data uses all defaults."""
        config = Config({})

        assert config.http_host == '127.0.0.1'
        assert config.http_port == 8000
        assert config.ticket_directory == './tickets'

    def test_config_repr(self):
        """Test Config string representation."""
        config = Config({'http': {'host': '127.0.0.1', 'port': 8000}})
        repr_str = repr(config)

        assert 'Config' in repr_str
        assert '127.0.0.1' in repr_str
        assert '8000' in repr_str


class TestPortValidation:
    """Test port validation and type coercion."""

    def test_valid_port_minimum(self):
        """Test port value 1 (minimum valid port)."""
        config = Config({'http': {'port': 1}})
        assert config.http_port == 1

    def test_valid_port_typical(self):
        """Test typical port value."""
        config = Config({'http': {'port': 8000}})
        assert config.http_port == 8000

    def test_valid_port_maximum(self):
        """Test port value 65535 (maximum valid port)."""
        config = Config({'http': {'port': 65535}})
        assert config.http_port == 65535

    def test_invalid_port_zero(self):
        """Test port value 0 raises ValueError."""
        with pytest.raises(ValueError, match="Port must be an integer between 1 and 65535, got: 0"):
            Config({'http': {'port': 0}})

    def test_invalid_port_negative(self):
        """Test negative port raises ValueError."""
        with pytest.raises(ValueError, match="Port must be an integer between 1 and 65535, got: -1"):
            Config({'http': {'port': -1}})

    def test_invalid_port_too_large(self):
        """Test port > 65535 raises ValueError."""
        with pytest.raises(ValueError, match="Port must be an integer between 1 and 65535, got: 65536"):
            Config({'http': {'port': 65536}})

    def test_invalid_port_way_too_large(self):
        """Test port >> 65535 raises ValueError."""
        with pytest.raises(ValueError, match="Port must be an integer between 1 and 65535, got: 99999"):
            Config({'http': {'port': 99999}})

    def test_port_string_coercion_valid(self):
        """Test string port '8000' is coerced to integer 8000."""
        config = Config({'http': {'port': '8000'}})
        assert config.http_port == 8000
        assert isinstance(config.http_port, int)

    def test_port_string_coercion_edge_case_minimum(self):
        """Test string port '1' is coerced to integer 1."""
        config = Config({'http': {'port': '1'}})
        assert config.http_port == 1

    def test_port_string_coercion_edge_case_maximum(self):
        """Test string port '65535' is coerced to integer 65535."""
        config = Config({'http': {'port': '65535'}})
        assert config.http_port == 65535

    def test_port_non_numeric_string_raises_error(self):
        """Test non-numeric string port raises ValueError."""
        with pytest.raises(ValueError, match="Port must be a valid integer, got: abc"):
            Config({'http': {'port': 'abc'}})

    def test_port_empty_string_raises_error(self):
        """Test empty string port raises ValueError."""
        with pytest.raises(ValueError, match="Port must be a valid integer, got: "):
            Config({'http': {'port': ''}})

    def test_port_float_string_raises_error(self):
        """Test float string port raises ValueError."""
        with pytest.raises(ValueError, match="Port must be a valid integer, got: 8000.5"):
            Config({'http': {'port': '8000.5'}})

    def test_port_none_raises_error(self):
        """Test None port raises ValueError."""
        with pytest.raises(ValueError, match="Port must be a valid integer, got: None"):
            Config({'http': {'port': None}})


class TestLoadConfig:
    """Test load_config function with various file scenarios."""

    def test_load_valid_config_file(self, tmp_path):
        """Test loading a valid config.yaml file."""
        config_file = tmp_path / 'config.yaml'
        config_data = {
            'http': {
                'host': '10.0.0.1',
                'port': 7000
            },
            'ticket_directory': './my_tickets'
        }
        config_file.write_text(yaml.dump(config_data))

        config = load_config(str(config_file))

        assert config.http_host == '10.0.0.1'
        assert config.http_port == 7000
        assert config.ticket_directory == './my_tickets'

    def test_load_config_missing_file(self, tmp_path):
        """Test loading config when file doesn't exist returns defaults."""
        nonexistent_file = tmp_path / 'nonexistent.yaml'

        config = load_config(str(nonexistent_file))

        assert config.http_host == '127.0.0.1'
        assert config.http_port == 8000
        assert config.ticket_directory == './tickets'

    def test_load_config_empty_file(self, tmp_path):
        """Test loading empty config file uses defaults."""
        config_file = tmp_path / 'config.yaml'
        config_file.write_text('')

        config = load_config(str(config_file))

        assert config.http_host == '127.0.0.1'
        assert config.http_port == 8000

    def test_load_config_malformed_yaml(self, tmp_path):
        """Test loading malformed YAML raises YAMLError."""
        config_file = tmp_path / 'config.yaml'
        config_file.write_text('http:\n  host: 127.0.0.1\n  port: [invalid yaml')

        with pytest.raises(yaml.YAMLError):
            load_config(str(config_file))

    def test_load_config_with_invalid_port_number(self, tmp_path):
        """Test config raises ValueError for port > 65535."""
        config_file = tmp_path / 'config.yaml'
        config_data = {
            'http': {
                'host': '127.0.0.1',
                'port': 99999  # invalid port
            }
        }
        config_file.write_text(yaml.dump(config_data))

        with pytest.raises(ValueError, match="Port must be an integer between 1 and 65535"):
            load_config(str(config_file))

    def test_load_config_with_negative_port(self, tmp_path):
        """Test config raises ValueError for negative port."""
        config_file = tmp_path / 'config.yaml'
        config_data = {
            'http': {
                'port': -100
            }
        }
        config_file.write_text(yaml.dump(config_data))

        with pytest.raises(ValueError, match="Port must be an integer between 1 and 65535"):
            load_config(str(config_file))

    def test_load_config_with_string_port(self, tmp_path):
        """Test config coerces string port value to integer."""
        config_file = tmp_path / 'config.yaml'
        config_data = {
            'http': {
                'port': "8080"
            }
        }
        config_file.write_text(yaml.dump(config_data))

        config = load_config(str(config_file))
        assert config.http_port == 8080  # Type coercion applied


class TestGetConfig:
    """Test get_config function that searches standard locations."""

    def test_get_config_from_cwd(self, tmp_path, monkeypatch):
        """Test get_config finds config.yaml in current directory."""
        config_file = tmp_path / 'config.yaml'
        config_data = {
            'http': {
                'host': '192.168.1.100',
                'port': 5000
            }
        }
        config_file.write_text(yaml.dump(config_data))

        monkeypatch.chdir(tmp_path)

        config = get_config()

        assert config.http_host == '192.168.1.100'
        assert config.http_port == 5000

    def test_get_config_from_parent_directory(self, tmp_path, monkeypatch):
        """Test get_config finds config.yaml in parent directory."""
        config_file = tmp_path / 'config.yaml'
        config_data = {
            'http': {
                'host': '10.1.1.1',
                'port': 3000
            }
        }
        config_file.write_text(yaml.dump(config_data))

        # Change to subdirectory (simulating running from src/)
        subdir = tmp_path / 'src'
        subdir.mkdir()
        monkeypatch.chdir(subdir)

        config = get_config()

        assert config.http_host == '10.1.1.1'
        assert config.http_port == 3000

    def test_get_config_no_file_found(self, tmp_path, monkeypatch):
        """Test get_config returns defaults when no config file found."""
        monkeypatch.chdir(tmp_path)

        config = get_config()

        assert config.http_host == '127.0.0.1'
        assert config.http_port == 8000
        assert config.ticket_directory == './tickets'

    def test_get_config_prefers_cwd_over_parent(self, tmp_path, monkeypatch):
        """Test get_config prefers CWD config over parent directory."""
        # Create config in parent
        parent_config = tmp_path / 'config.yaml'
        parent_config.write_text(yaml.dump({'http': {'port': 1111}}))

        # Create config in subdirectory
        subdir = tmp_path / 'src'
        subdir.mkdir()
        cwd_config = subdir / 'config.yaml'
        cwd_config.write_text(yaml.dump({'http': {'port': 2222}}))

        monkeypatch.chdir(subdir)

        config = get_config()

        # Should use CWD config (port 2222), not parent (port 1111)
        assert config.http_port == 2222


class TestHostValidation:
    """Test host IP validation logic."""

    def test_valid_ipv4_localhost(self):
        """Test valid IPv4 localhost address."""
        config = Config({'http': {'host': '127.0.0.1'}})
        assert config.http_host == '127.0.0.1'

    def test_valid_ipv4_all_interfaces(self):
        """Test valid IPv4 all interfaces address."""
        config = Config({'http': {'host': '0.0.0.0'}})
        assert config.http_host == '0.0.0.0'

    def test_valid_ipv4_typical(self):
        """Test valid typical IPv4 address."""
        config = Config({'http': {'host': '192.168.1.1'}})
        assert config.http_host == '192.168.1.1'

    def test_valid_ipv4_another(self):
        """Test valid IPv4 address."""
        config = Config({'http': {'host': '10.0.0.1'}})
        assert config.http_host == '10.0.0.1'

    def test_valid_ipv6_localhost(self):
        """Test valid IPv6 localhost address."""
        config = Config({'http': {'host': '::1'}})
        assert config.http_host == '::1'

    def test_valid_ipv6_all_interfaces(self):
        """Test valid IPv6 all interfaces address."""
        config = Config({'http': {'host': '::'}})
        assert config.http_host == '::'

    def test_valid_ipv6_full(self):
        """Test valid full IPv6 address."""
        config = Config({'http': {'host': '2001:0db8:85a3:0000:0000:8a2e:0370:7334'}})
        assert config.http_host == '2001:0db8:85a3:0000:0000:8a2e:0370:7334'

    def test_valid_ipv6_compressed(self):
        """Test valid compressed IPv6 address."""
        config = Config({'http': {'host': '2001:db8::1'}})
        assert config.http_host == '2001:db8::1'

    def test_invalid_host_malformed_ip(self):
        """Test malformed IP address raises ValueError."""
        with pytest.raises(ValueError, match="Invalid host '999.999.999.999'"):
            Config({'http': {'host': '999.999.999.999'}})

    def test_invalid_host_not_an_ip(self):
        """Test non-IP string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid host 'not-an-ip'"):
            Config({'http': {'host': 'not-an-ip'}})

    def test_invalid_host_hostname(self):
        """Test hostname raises ValueError (only IP addresses allowed)."""
        with pytest.raises(ValueError, match="Invalid host 'localhost'"):
            Config({'http': {'host': 'localhost'}})

    def test_invalid_host_domain(self):
        """Test domain name raises ValueError."""
        with pytest.raises(ValueError, match="Invalid host 'example.com'"):
            Config({'http': {'host': 'example.com'}})

    def test_invalid_host_empty_string(self):
        """Test empty host string raises ValueError."""
        with pytest.raises(ValueError, match="Host cannot be empty"):
            Config({'http': {'host': ''}})

    def test_invalid_host_partial_ip(self):
        """Test partial IP address raises ValueError."""
        with pytest.raises(ValueError, match="Invalid host '192.168'"):
            Config({'http': {'host': '192.168'}})

    def test_invalid_host_ip_with_port(self):
        """Test IP with port suffix raises ValueError."""
        with pytest.raises(ValueError, match="Invalid host '127.0.0.1:8000'"):
            Config({'http': {'host': '127.0.0.1:8000'}})

    def test_invalid_host_spaces(self):
        """Test host with spaces raises ValueError."""
        with pytest.raises(ValueError, match="Invalid host ' 127.0.0.1 '"):
            Config({'http': {'host': ' 127.0.0.1 '}})

    def test_host_validation_error_message_includes_examples(self):
        """Test error message includes helpful examples."""
        with pytest.raises(ValueError) as exc_info:
            Config({'http': {'host': 'invalid'}})

        error_msg = str(exc_info.value)
        assert "127.0.0.1" in error_msg
        assert "0.0.0.0" in error_msg
        assert "::1" in error_msg
        assert "::" in error_msg


class TestBeesConfigDataclasses:
    """Test BeesConfig and HiveConfig dataclass initialization."""

    def test_hive_config_initialization(self):
        """Test HiveConfig dataclass can be instantiated."""
        hive = HiveConfig(path="/path/to/hive", display_name="My Hive", created_at="2026-02-01T12:00:00")
        assert hive.path == "/path/to/hive"
        assert hive.display_name == "My Hive"
        assert hive.created_at == "2026-02-01T12:00:00"

    def test_hive_config_with_all_fields(self):
        """Test HiveConfig with all three fields."""
        timestamp = "2026-02-01T13:45:30.123456"
        hive = HiveConfig(
            path="/path/to/hive",
            display_name="Backend",
            created_at=timestamp
        )
        assert hive.path == "/path/to/hive"
        assert hive.display_name == "Backend"
        assert hive.created_at == timestamp

    def test_bees_config_initialization_defaults(self):
        """Test BeesConfig with default values."""
        config = BeesConfig()
        assert config.hives == {}
        assert config.allow_cross_hive_dependencies is False
        assert config.schema_version == "1.0"

    def test_bees_config_initialization_with_values(self):
        """Test BeesConfig with custom values."""
        hive = HiveConfig(path="/path", display_name="Test", created_at="2026-02-01T12:00:00")
        config = BeesConfig(
            hives={"test": hive},
            allow_cross_hive_dependencies=True,
            schema_version="2.0"
        )
        assert config.hives == {"test": hive}
        assert config.allow_cross_hive_dependencies is True
        assert config.schema_version == "2.0"


class TestLoadBeesConfig:
    """Test load_bees_config function."""

    def test_load_bees_config_missing_file(self, tmp_path, monkeypatch):
        """Test load_bees_config returns None when file doesn't exist."""
        monkeypatch.chdir(tmp_path)
        with repo_root_context(tmp_path):
            config = load_bees_config()
        assert config is None

    def test_load_bees_config_valid_file(self, tmp_path, monkeypatch):
        """Test load_bees_config with valid config file."""
        monkeypatch.chdir(tmp_path)
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config_file = bees_dir / "config.json"

        config_data = {
            "hives": {
                "backend": {
                    "path": "tickets/backend/",
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00.000000"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        config_file.write_text(json.dumps(config_data))

        config = load_bees_config()
        assert config is not None
        assert len(config.hives) == 1
        assert "backend" in config.hives
        assert config.hives["backend"].path == "tickets/backend/"
        assert config.hives["backend"].display_name == "Backend"
        assert config.hives["backend"].created_at == "2026-02-01T12:00:00.000000"
        assert config.allow_cross_hive_dependencies is False
        assert config.schema_version == "1.0"

    def test_load_bees_config_empty_hives(self, tmp_path, monkeypatch):
        """Test load_bees_config with empty hives dict."""
        monkeypatch.chdir(tmp_path)
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config_file = bees_dir / "config.json"

        config_data = {
            "hives": {},
            "allow_cross_hive_dependencies": True,
            "schema_version": "1.0"
        }
        config_file.write_text(json.dumps(config_data))

        config = load_bees_config()
        assert config is not None
        assert config.hives == {}
        assert config.allow_cross_hive_dependencies is True

    def test_load_bees_config_malformed_json(self, tmp_path, monkeypatch, caplog):
        """Test load_bees_config returns default structure on malformed JSON with warning."""
        import logging
        monkeypatch.chdir(tmp_path)
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config_file = bees_dir / "config.json"
        config_file.write_text("{invalid json")

        with caplog.at_level(logging.WARNING):
            config = load_bees_config()

        # Should return default structure instead of raising
        assert config is not None
        assert config.hives == {}
        assert config.allow_cross_hive_dependencies is False
        assert config.schema_version == '1.0'

        # Should log warning
        assert "Malformed JSON" in caplog.text

    def test_load_bees_config_invalid_schema_version_type(self, tmp_path, monkeypatch):
        """Test load_bees_config raises ValueError for invalid schema_version type."""
        monkeypatch.chdir(tmp_path)
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config_file = bees_dir / "config.json"

        config_data = {
            "hives": {},
            "schema_version": 123  # Should be string
        }
        config_file.write_text(json.dumps(config_data))

        with pytest.raises(ValueError, match="schema_version must be a string"):
            load_bees_config()

    def test_load_bees_config_invalid_hive_data_type(self, tmp_path, monkeypatch):
        """Test load_bees_config raises ValueError for invalid hive data type."""
        monkeypatch.chdir(tmp_path)
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config_file = bees_dir / "config.json"

        config_data = {
            "hives": {
                "backend": "not a dict"  # Should be dict
            }
        }
        config_file.write_text(json.dumps(config_data))

        with pytest.raises(ValueError, match="Hive 'backend' data must be a dict"):
            load_bees_config()

    def test_load_bees_config_returns_valid_structure_after_json_error(self, tmp_path, monkeypatch):
        """Test load_bees_config returns valid default structure on JSON errors."""
        monkeypatch.chdir(tmp_path)
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config_file = bees_dir / "config.json"

        # Write malformed JSON
        config_file.write_text("{broken json}")

        config = load_bees_config()

        # Verify returned default structure is valid
        assert isinstance(config, BeesConfig)
        assert isinstance(config.hives, dict)
        assert isinstance(config.allow_cross_hive_dependencies, bool)
        assert isinstance(config.schema_version, str)


class TestSaveBeesConfig:
    """Test save_bees_config function."""

    def test_save_bees_config_creates_directory(self, tmp_path, monkeypatch):
        """Test save_bees_config creates .bees/ directory if needed."""
        monkeypatch.chdir(tmp_path)
        config = BeesConfig()
        save_bees_config(config)

        bees_dir = tmp_path / ".bees"
        assert bees_dir.exists()
        assert bees_dir.is_dir()

    def test_save_bees_config_creates_valid_json(self, tmp_path, monkeypatch):
        """Test save_bees_config creates valid JSON file."""
        monkeypatch.chdir(tmp_path)
        timestamp = "2026-02-01T13:45:30.123456"
        hive = HiveConfig(path="tickets/backend/", display_name="Backend", created_at=timestamp)
        config = BeesConfig(
            hives={"backend": hive},
            allow_cross_hive_dependencies=False,
            schema_version="1.0"
        )
        save_bees_config(config)

        config_file = tmp_path / ".bees" / "config.json"
        assert config_file.exists()

        with open(config_file, 'r') as f:
            data = json.load(f)

        assert data["hives"]["backend"]["path"] == "tickets/backend/"
        assert data["hives"]["backend"]["display_name"] == "Backend"
        assert data["hives"]["backend"]["created_at"] == timestamp
        assert data["allow_cross_hive_dependencies"] is False
        assert data["schema_version"] == "1.0"

    def test_save_bees_config_serializes_created_at_field(self, tmp_path, monkeypatch):
        """Test save_bees_config properly serializes created_at timestamp field."""
        monkeypatch.chdir(tmp_path)
        timestamp = "2026-02-01T12:00:00.000000"
        hive = HiveConfig(
            path="/path/to/hive",
            display_name="Test Hive",
            created_at=timestamp
        )
        config = BeesConfig(hives={"test": hive})
        save_bees_config(config)

        config_file = tmp_path / ".bees" / "config.json"
        with open(config_file, 'r') as f:
            data = json.load(f)

        # Verify created_at is present in serialized JSON
        assert "created_at" in data["hives"]["test"]
        assert data["hives"]["test"]["created_at"] == timestamp

    def test_save_bees_config_sets_default_schema_version(self, tmp_path, monkeypatch):
        """Test save_bees_config sets schema_version to '1.0' if not set."""
        monkeypatch.chdir(tmp_path)
        config = BeesConfig(schema_version="")
        save_bees_config(config)

        config_file = tmp_path / ".bees" / "config.json"
        with open(config_file, 'r') as f:
            data = json.load(f)

        assert data["schema_version"] == "1.0"

    def test_save_bees_config_formatted_with_indent(self, tmp_path, monkeypatch):
        """Test save_bees_config creates formatted JSON with indent=2."""
        monkeypatch.chdir(tmp_path)
        config = BeesConfig()
        save_bees_config(config)

        config_file = tmp_path / ".bees" / "config.json"
        content = config_file.read_text()

        # Check for indentation (pretty-printed JSON)
        assert "  " in content  # Should have 2-space indentation
        assert "\n" in content  # Should have newlines

    def test_save_bees_config_adds_trailing_newline(self, tmp_path, monkeypatch):
        """Test save_bees_config adds trailing newline after JSON content."""
        monkeypatch.chdir(tmp_path)
        config = BeesConfig()
        save_bees_config(config)

        config_file = tmp_path / ".bees" / "config.json"
        content = config_file.read_text()

        # Verify trailing newline
        assert content.endswith('\n')

    def test_save_bees_config_atomic_write_creates_temp_file(self, tmp_path, monkeypatch):
        """Test save_bees_config uses temp file pattern for atomic writes."""
        import os
        import tempfile
        from unittest.mock import patch, MagicMock

        monkeypatch.chdir(tmp_path)
        config = BeesConfig()

        # Track calls to tempfile.mkstemp
        temp_files_created = []
        original_mkstemp = tempfile.mkstemp

        def mock_mkstemp(*args, **kwargs):
            fd, path = original_mkstemp(*args, **kwargs)
            temp_files_created.append(path)
            return fd, path

        with patch('tempfile.mkstemp', side_effect=mock_mkstemp):
            save_bees_config(config)

        # Verify temp file was created in .bees/ directory
        assert len(temp_files_created) == 1
        temp_file = temp_files_created[0]
        assert '.config.json.' in temp_file
        assert str(tmp_path / ".bees") in temp_file

        # Verify temp file was renamed (no longer exists)
        assert not Path(temp_file).exists()

        # Verify final config file exists
        config_file = tmp_path / ".bees" / "config.json"
        assert config_file.exists()

    def test_save_bees_config_cleanup_on_write_failure(self, tmp_path, monkeypatch):
        """Test save_bees_config cleans up temp file on write failure."""
        import os
        import tempfile
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)
        config = BeesConfig()

        # Track temp file creation
        temp_file_path = None

        def mock_mkstemp(*args, **kwargs):
            nonlocal temp_file_path
            fd, temp_file_path = tempfile.mkstemp(*args, **kwargs)
            return fd, temp_file_path

        # Mock os.fdopen to raise IOError during write
        def mock_fdopen(*args, **kwargs):
            raise IOError("Simulated write failure")

        with patch('tempfile.mkstemp', side_effect=mock_mkstemp):
            with patch('os.fdopen', side_effect=mock_fdopen):
                try:
                    save_bees_config(config)
                except IOError:
                    pass  # Expected failure

        # Verify temp file was cleaned up
        if temp_file_path:
            assert not Path(temp_file_path).exists()

    def test_save_and_load_preserves_created_at(self, tmp_path, monkeypatch):
        """Test round-trip save and load preserves created_at timestamp."""
        monkeypatch.chdir(tmp_path)
        timestamp = "2026-02-01T15:30:45.678901"
        hive = HiveConfig(
            path="/path/to/hive",
            display_name="Backend",
            created_at=timestamp
        )
        original_config = BeesConfig(hives={"backend": hive})

        # Save config
        save_bees_config(original_config)

        # Load it back
        loaded_config = load_bees_config()

        # Verify created_at is preserved
        assert loaded_config is not None
        assert "backend" in loaded_config.hives
        assert loaded_config.hives["backend"].created_at == timestamp
        assert loaded_config.hives["backend"].path == "/path/to/hive"
        assert loaded_config.hives["backend"].display_name == "Backend"

    def test_save_bees_config_no_partial_writes_on_failure(self, tmp_path, monkeypatch):
        """Test save_bees_config preserves existing config on write failure."""
        monkeypatch.chdir(tmp_path)

        # Create initial config
        hive = HiveConfig(path="tickets/backend/", display_name="Backend", created_at="2026-02-01T12:00:00")
        config1 = BeesConfig(hives={"backend": hive}, schema_version="1.0")
        save_bees_config(config1)

        # Verify initial config was saved
        config_file = tmp_path / ".bees" / "config.json"
        original_content = config_file.read_text()
        assert "Backend" in original_content

        # Try to save new config but simulate failure
        config2 = BeesConfig(hives={}, schema_version="2.0")

        import os
        from unittest.mock import patch

        # Mock os.replace to raise error (simulating crash during rename)
        def mock_replace(*args, **kwargs):
            raise OSError("Simulated rename failure")

        with patch('os.replace', side_effect=mock_replace):
            try:
                save_bees_config(config2)
            except IOError:
                pass  # Expected failure

        # Verify original config file is intact (not corrupted)
        config_file_content = config_file.read_text()
        assert config_file_content == original_content
        assert "Backend" in config_file_content
        assert json.loads(config_file_content)["schema_version"] == "1.0"

    def test_save_bees_config_atomic_rename_with_os_replace(self, tmp_path, monkeypatch):
        """Test save_bees_config uses os.replace for atomic rename."""
        from unittest.mock import patch, MagicMock
        import os

        monkeypatch.chdir(tmp_path)
        config = BeesConfig()

        # Track calls to os.replace
        replace_calls = []

        def mock_replace(src, dst):
            replace_calls.append((src, dst))
            # Call original os.replace
            os.replace.__wrapped__(src, dst) if hasattr(os.replace, '__wrapped__') else None
            # Actually perform rename for test to work
            Path(src).rename(dst)

        with patch('os.replace', side_effect=mock_replace) as mock_os_replace:
            save_bees_config(config)

        # Verify os.replace was called
        assert len(replace_calls) == 1
        src, dst = replace_calls[0]

        # Verify source is temp file and destination is config.json
        assert '.config.json.' in str(src)
        assert str(dst) == str(tmp_path / ".bees" / "config.json")


class TestInitBeesConfigIfNeeded:
    """Test init_bees_config_if_needed function."""

    def test_init_bees_config_if_needed_creates_config(self, tmp_path, monkeypatch):
        """Test init_bees_config_if_needed creates config on first call."""
        monkeypatch.chdir(tmp_path)
        config = init_bees_config_if_needed()

        assert config is not None
        assert config.hives == {}
        assert config.allow_cross_hive_dependencies is False
        assert config.schema_version == "1.0"

        # Verify file was created
        config_file = tmp_path / ".bees" / "config.json"
        assert config_file.exists()

    def test_init_bees_config_if_needed_returns_existing_config(self, tmp_path, monkeypatch):
        """Test init_bees_config_if_needed returns existing config on subsequent calls."""
        monkeypatch.chdir(tmp_path)

        # First call creates config
        config1 = init_bees_config_if_needed()
        config1.allow_cross_hive_dependencies = True
        save_bees_config(config1)

        # Second call should load existing config
        config2 = init_bees_config_if_needed()
        assert config2.allow_cross_hive_dependencies is True


class TestConfigPathHelpers:
    """Test get_config_path and ensure_bees_dir helpers."""

    def test_get_config_path(self, tmp_path, monkeypatch):
        """Test get_config_path returns correct path."""
        monkeypatch.chdir(tmp_path)
        config_path = get_config_path()

        assert config_path == tmp_path / ".bees" / "config.json"

    def test_ensure_bees_dir_creates_directory(self, tmp_path, monkeypatch):
        """Test ensure_bees_dir creates .bees/ directory."""
        monkeypatch.chdir(tmp_path)
        bees_dir = tmp_path / ".bees"
        assert not bees_dir.exists()

        ensure_bees_dir()

        assert bees_dir.exists()
        assert bees_dir.is_dir()

    def test_ensure_bees_dir_idempotent(self, tmp_path, monkeypatch):
        """Test ensure_bees_dir is idempotent (safe to call multiple times)."""
        monkeypatch.chdir(tmp_path)
        bees_dir = tmp_path / ".bees"

        ensure_bees_dir()
        ensure_bees_dir()  # Should not raise error

        assert bees_dir.exists()


class TestNormalizeHiveName:
    """Test normalize_hive_name function for hive name normalization."""

    def test_normalize_hive_name_spaces_to_underscores(self):
        """Test 'Back End' normalizes to 'back_end'."""
        assert normalize_hive_name('Back End') == 'back_end'

    def test_normalize_hive_name_uppercase_to_lowercase(self):
        """Test 'UPPERCASE' normalizes to 'uppercase'."""
        assert normalize_hive_name('UPPERCASE') == 'uppercase'

    def test_normalize_hive_name_multi_word(self):
        """Test 'multi word name' normalizes to 'multi_word_name'."""
        assert normalize_hive_name('multi word name') == 'multi_word_name'

    def test_normalize_hive_name_mixed_case_with_spaces(self):
        """Test 'Front End Team' normalizes to 'front_end_team'."""
        assert normalize_hive_name('Front End Team') == 'front_end_team'

    def test_normalize_hive_name_already_normalized(self):
        """Test 'backend' stays 'backend'."""
        assert normalize_hive_name('backend') == 'backend'

    def test_normalize_hive_name_single_word_uppercase(self):
        """Test 'API' normalizes to 'api'."""
        assert normalize_hive_name('API') == 'api'

    def test_normalize_hive_name_multiple_spaces(self):
        """Test 'multiple  spaces' with double space."""
        assert normalize_hive_name('multiple  spaces') == 'multiple__spaces'

    def test_normalize_hive_name_trailing_spaces(self):
        """Test 'trailing ' with trailing space."""
        assert normalize_hive_name('trailing ') == 'trailing_'

    def test_normalize_hive_name_leading_spaces(self):
        """Test ' leading' with leading space."""
        assert normalize_hive_name(' leading') == '_leading'

    def test_normalize_hive_name_empty_string(self):
        """Test empty string returns empty string."""
        assert normalize_hive_name('') == ''

    def test_normalize_hive_name_underscore_preserved(self):
        """Test 'already_normalized' stays 'already_normalized'."""
        assert normalize_hive_name('already_normalized') == 'already_normalized'

    def test_normalize_hive_name_hyphens_to_underscores(self):
        """Test hyphens are converted to underscores."""
        # Note: normalize_hive_name converts hyphens to underscores and removes special chars
        assert normalize_hive_name('test-name') == 'test_name'

    def test_normalize_hive_name_special_chars_removed(self):
        """Test special characters are removed."""
        assert normalize_hive_name('test.name') == 'testname'


class TestValidateUniqueHiveName:
    """Test validate_unique_hive_name function for duplicate detection."""

    def test_validate_unique_hive_name_no_config(self, tmp_path, monkeypatch):
        """Test validation passes when no config file exists."""
        monkeypatch.chdir(tmp_path)
        # Should not raise - no config means name is unique
        validate_unique_hive_name('backend')

    def test_validate_unique_hive_name_empty_hives(self, tmp_path, monkeypatch):
        """Test validation passes with empty hives dict."""
        monkeypatch.chdir(tmp_path)
        config = BeesConfig(hives={})
        save_bees_config(config)

        # Should not raise - no hives registered yet
        validate_unique_hive_name('backend')

    def test_validate_unique_hive_name_new_name(self, tmp_path, monkeypatch):
        """Test validation passes for new unique name."""
        monkeypatch.chdir(tmp_path)
        hive = HiveConfig(path='tickets/frontend/', display_name='Frontend', created_at='2026-02-01T12:00:00')
        config = BeesConfig(hives={'frontend': hive})
        save_bees_config(config)

        # Should not raise - 'backend' is different from 'frontend'
        validate_unique_hive_name('backend')

    def test_validate_unique_hive_name_duplicate_normalized_name(self, tmp_path, monkeypatch):
        """Test validation raises ValueError for duplicate normalized name."""
        monkeypatch.chdir(tmp_path)
        hive = HiveConfig(path='tickets/backend/', display_name='Back End', created_at='2026-02-01T12:00:00')
        config = BeesConfig(hives={'back_end': hive})
        save_bees_config(config)

        # Should raise - 'back_end' already exists
        with pytest.raises(ValueError, match="normalized name 'back_end' already exists"):
            validate_unique_hive_name('back_end')

    def test_validate_unique_hive_name_prevents_collision(self, tmp_path, monkeypatch):
        """Test validation prevents 'Back End' and 'back end' collision."""
        monkeypatch.chdir(tmp_path)
        # Register 'Back End' (normalized to 'back_end')
        hive = HiveConfig(path='tickets/backend/', display_name='Back End', created_at='2026-02-01T12:00:00')
        config = BeesConfig(hives={'back_end': hive})
        save_bees_config(config)

        # Trying to register 'back end' should fail (also normalizes to 'back_end')
        normalized = normalize_hive_name('back end')
        with pytest.raises(ValueError, match="normalized name 'back_end' already exists"):
            validate_unique_hive_name(normalized)

    def test_validate_unique_hive_name_multiple_hives(self, tmp_path, monkeypatch):
        """Test validation with multiple registered hives."""
        monkeypatch.chdir(tmp_path)
        timestamp = '2026-02-01T12:00:00'
        config = BeesConfig(hives={
            'frontend': HiveConfig(path='tickets/fe/', display_name='Frontend', created_at=timestamp),
            'backend': HiveConfig(path='tickets/be/', display_name='Backend', created_at=timestamp),
            'api': HiveConfig(path='tickets/api/', display_name='API', created_at=timestamp)
        })
        save_bees_config(config)

        # New name should pass
        validate_unique_hive_name('mobile')

        # Existing name should fail
        with pytest.raises(ValueError, match="normalized name 'backend' already exists"):
            validate_unique_hive_name('backend')

    def test_validate_unique_hive_name_case_insensitive_collision(self, tmp_path, monkeypatch):
        """Test 'BACKEND' and 'backend' are treated as the same."""
        monkeypatch.chdir(tmp_path)
        hive = HiveConfig(path='tickets/backend/', display_name='BACKEND', created_at='2026-02-01T12:00:00')
        config = BeesConfig(hives={'backend': hive})
        save_bees_config(config)

        # Normalized 'BACKEND' is 'backend', which already exists
        normalized = normalize_hive_name('BACKEND')
        with pytest.raises(ValueError, match="normalized name 'backend' already exists"):
            validate_unique_hive_name(normalized)

    def test_validate_unique_hive_name_display_name_in_error(self, tmp_path, monkeypatch):
        """Test error message includes original display name."""
        monkeypatch.chdir(tmp_path)
        hive = HiveConfig(path='tickets/backend/', display_name='Back End Services', created_at='2026-02-01T12:00:00')
        config = BeesConfig(hives={'back_end_services': hive})
        save_bees_config(config)

        with pytest.raises(ValueError, match="Display name: 'Back End Services'"):
            validate_unique_hive_name('back_end_services')


class TestLoadHiveConfigDict:
    """Test load_hive_config_dict function for dict-based config loading."""

    def test_load_hive_config_dict_missing_file(self, tmp_path, monkeypatch):
        """Test load_hive_config_dict returns default dict when file doesn't exist."""
        monkeypatch.chdir(tmp_path)
        config = load_hive_config_dict()

        assert config == {
            'hives': {},
            'allow_cross_hive_dependencies': False,
            'schema_version': '1.0'
        }

    def test_load_hive_config_dict_valid_file(self, tmp_path, monkeypatch):
        """Test load_hive_config_dict returns correct dict structure."""
        monkeypatch.chdir(tmp_path)
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config_file = bees_dir / "config.json"

        config_data = {
            "hives": {
                "backend": {
                    "path": "tickets/backend/",
                    "display_name": "Backend"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        config_file.write_text(json.dumps(config_data))

        config = load_hive_config_dict()
        assert config['hives']['backend']['path'] == "tickets/backend/"
        assert config['hives']['backend']['display_name'] == "Backend"
        assert config['allow_cross_hive_dependencies'] is False
        assert config['schema_version'] == "1.0"

    def test_load_hive_config_dict_empty_hives(self, tmp_path, monkeypatch):
        """Test load_hive_config_dict with empty hives dict."""
        monkeypatch.chdir(tmp_path)
        hive_config = BeesConfig(hives={}, allow_cross_hive_dependencies=True)
        save_bees_config(hive_config)

        config = load_hive_config_dict()
        assert config['hives'] == {}
        assert config['allow_cross_hive_dependencies'] is True

    def test_load_hive_config_dict_malformed_json(self, tmp_path, monkeypatch, caplog):
        """Test load_hive_config_dict returns default dict on malformed JSON with warning."""
        import logging
        monkeypatch.chdir(tmp_path)
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config_file = bees_dir / "config.json"
        config_file.write_text("{invalid json")

        with caplog.at_level(logging.WARNING):
            config = load_hive_config_dict()

        # Should return default structure instead of raising
        assert config == {
            'hives': {},
            'allow_cross_hive_dependencies': False,
            'schema_version': '1.0'
        }

        # Should log warning
        assert "Malformed JSON" in caplog.text

    def test_load_hive_config_dict_io_error(self, tmp_path, monkeypatch, caplog):
        """Test load_hive_config_dict returns default dict on IO errors with warning."""
        import logging
        monkeypatch.chdir(tmp_path)
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config_file = bees_dir / "config.json"

        # Create valid config file
        config_data = {
            "hives": {},
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        config_file.write_text(json.dumps(config_data))

        # Remove read permissions to trigger IO error
        config_file.chmod(0o000)

        try:
            with caplog.at_level(logging.WARNING):
                config = load_hive_config_dict()

            # Should return default structure instead of raising
            assert config == {
                'hives': {},
                'allow_cross_hive_dependencies': False,
                'schema_version': '1.0'
            }

            # Should log warning
            assert "IO error reading" in caplog.text
        finally:
            # Restore permissions for cleanup
            config_file.chmod(0o644)

    def test_load_hive_config_dict_valid_config_still_loads(self, tmp_path, monkeypatch):
        """Test load_hive_config_dict successfully loads valid config after error cases."""
        monkeypatch.chdir(tmp_path)
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config_file = bees_dir / "config.json"

        # Create valid config
        config_data = {
            "hives": {
                "backend": {
                    "path": "tickets/backend/",
                    "display_name": "Backend"
                }
            },
            "allow_cross_hive_dependencies": True,
            "schema_version": "1.0"
        }
        config_file.write_text(json.dumps(config_data))

        # Should load successfully
        config = load_hive_config_dict()
        assert config['hives']['backend']['path'] == "tickets/backend/"
        assert config['allow_cross_hive_dependencies'] is True

    def test_load_hive_config_dict_returns_valid_structure_after_json_error(self, tmp_path, monkeypatch):
        """Test load_hive_config_dict returns valid default dict on JSON errors."""
        monkeypatch.chdir(tmp_path)
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config_file = bees_dir / "config.json"

        # Write malformed JSON
        config_file.write_text("{broken json}")

        config = load_hive_config_dict()

        # Verify returned default structure is valid
        assert isinstance(config, dict)
        assert 'hives' in config
        assert 'allow_cross_hive_dependencies' in config
        assert 'schema_version' in config
        assert config['hives'] == {}
        assert config['allow_cross_hive_dependencies'] is False
        assert config['schema_version'] == '1.0'


class TestWriteHiveConfigDict:
    """Test write_hive_config_dict function for dict-based config writing."""

    def test_write_hive_config_dict_creates_directory(self, tmp_path, monkeypatch):
        """Test write_hive_config_dict creates .bees/ directory if needed."""
        monkeypatch.chdir(tmp_path)
        config = {
            'hives': {},
            'allow_cross_hive_dependencies': False,
            'schema_version': '1.0'
        }
        write_hive_config_dict(config)

        bees_dir = tmp_path / ".bees"
        assert bees_dir.exists()
        assert bees_dir.is_dir()

    def test_write_hive_config_dict_converts_and_saves(self, tmp_path, monkeypatch):
        """Test write_hive_config_dict correctly converts dict to BeesConfig and saves."""
        monkeypatch.chdir(tmp_path)
        config = {
            'hives': {
                'backend': {
                    'path': 'tickets/backend/',
                    'display_name': 'Backend'
                }
            },
            'allow_cross_hive_dependencies': False,
            'schema_version': '1.0'
        }
        write_hive_config_dict(config)

        config_file = tmp_path / ".bees" / "config.json"
        assert config_file.exists()

        with open(config_file, 'r') as f:
            data = json.load(f)

        assert data["hives"]["backend"]["path"] == "tickets/backend/"
        assert data["hives"]["backend"]["display_name"] == "Backend"

    def test_write_hive_config_dict_handles_created_at_timestamp(self, tmp_path, monkeypatch):
        """Test write_hive_config_dict handles 'created_at' timestamps in hive entries."""
        monkeypatch.chdir(tmp_path)
        config = {
            'hives': {
                'backend': {
                    'path': 'tickets/backend/',
                    'display_name': 'Backend',
                    'created_at': '2026-02-01T12:00:00'  # Timestamp present in dict
                }
            },
            'allow_cross_hive_dependencies': False,
            'schema_version': '1.0'
        }
        # Should not raise - created_at is ignored during conversion
        write_hive_config_dict(config)

        # Verify file was created successfully
        config_file = tmp_path / ".bees" / "config.json"
        assert config_file.exists()

    def test_write_hive_config_dict_error_handling(self, tmp_path, monkeypatch):
        """Test write_hive_config_dict error handling for IOError."""
        monkeypatch.chdir(tmp_path)

        # Create .bees directory as read-only to trigger permission error
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        bees_dir.chmod(0o444)  # Read-only

        config = {
            'hives': {},
            'allow_cross_hive_dependencies': False,
            'schema_version': '1.0'
        }

        try:
            with pytest.raises(IOError):
                write_hive_config_dict(config)
        finally:
            # Restore permissions for cleanup
            bees_dir.chmod(0o755)

    def test_write_hive_config_dict_empty_hives(self, tmp_path, monkeypatch):
        """Test write_hive_config_dict with empty hives dict."""
        monkeypatch.chdir(tmp_path)
        config = {
            'hives': {},
            'allow_cross_hive_dependencies': True,
            'schema_version': '2.0'
        }
        write_hive_config_dict(config)

        config_file = tmp_path / ".bees" / "config.json"
        with open(config_file, 'r') as f:
            data = json.load(f)

        assert data['hives'] == {}
        assert data['allow_cross_hive_dependencies'] is True
        assert data['schema_version'] == '2.0'


class TestRegisterHiveDict:
    """Test register_hive_dict function for dict-based hive registration."""

    def test_register_hive_dict_adds_new_hive(self, tmp_path, monkeypatch):
        """Test register_hive_dict adds new hive with correct structure."""
        from datetime import datetime
        monkeypatch.chdir(tmp_path)

        # Create initial empty config
        init_bees_config_if_needed()

        timestamp = datetime(2026, 2, 1, 12, 0, 0)
        config = register_hive_dict('backend', 'Backend', 'tickets/backend/', timestamp)

        assert 'backend' in config['hives']
        assert config['hives']['backend']['path'] == 'tickets/backend/'
        assert config['hives']['backend']['display_name'] == 'Backend'
        assert config['hives']['backend']['created_at'] == '2026-02-01T12:00:00'

    def test_register_hive_dict_includes_timestamp(self, tmp_path, monkeypatch):
        """Test register_hive_dict includes timestamp in ISO format."""
        from datetime import datetime
        monkeypatch.chdir(tmp_path)

        timestamp = datetime(2026, 2, 1, 15, 30, 45)
        config = register_hive_dict('api', 'API', 'tickets/api/', timestamp)

        assert config['hives']['api']['created_at'] == '2026-02-01T15:30:45'

    def test_register_hive_dict_does_not_write_to_disk(self, tmp_path, monkeypatch):
        """Test register_hive_dict doesn't write to disk (returns updated dict only)."""
        from datetime import datetime
        monkeypatch.chdir(tmp_path)

        timestamp = datetime.now()
        config = register_hive_dict('frontend', 'Frontend', 'tickets/frontend/', timestamp)

        # Config should be returned but not persisted
        assert 'frontend' in config['hives']

        # Verify file doesn't exist (or doesn't contain the new hive if it existed before)
        config_file = tmp_path / ".bees" / "config.json"
        if config_file.exists():
            with open(config_file, 'r') as f:
                data = json.load(f)
            # If file exists, it shouldn't have the frontend hive
            assert 'frontend' not in data.get('hives', {})

    def test_register_hive_dict_adds_to_existing_hives(self, tmp_path, monkeypatch):
        """Test register_hive_dict adds to existing hives without removing them."""
        from datetime import datetime
        monkeypatch.chdir(tmp_path)

        # Create config with one hive
        hive = HiveConfig(path='tickets/backend/', display_name='Backend', created_at='2026-02-01T12:00:00')
        config = BeesConfig(hives={'backend': hive})
        save_bees_config(config)

        # Add another hive
        timestamp = datetime.now()
        updated_config = register_hive_dict('frontend', 'Frontend', 'tickets/frontend/', timestamp)

        # Both hives should be in the returned dict
        assert 'backend' in updated_config['hives']
        assert 'frontend' in updated_config['hives']

    def test_register_hive_dict_with_no_existing_config(self, tmp_path, monkeypatch):
        """Test register_hive_dict works when no config file exists."""
        from datetime import datetime
        monkeypatch.chdir(tmp_path)

        # No config file exists yet
        config_file = tmp_path / ".bees" / "config.json"
        assert not config_file.exists()

        timestamp = datetime.now()
        config = register_hive_dict('mobile', 'Mobile', 'tickets/mobile/', timestamp)

        # Should return valid config with new hive
        assert config['hives']['mobile']['path'] == 'tickets/mobile/'
        assert config['hives']['mobile']['display_name'] == 'Mobile'
        assert 'created_at' in config['hives']['mobile']
