"""Tests for configuration loading and parsing."""

import pytest
from pathlib import Path
import yaml

from src.config import Config, load_config, get_config


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
