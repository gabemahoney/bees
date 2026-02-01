"""Configuration management for Bees MCP Server.

Loads and parses config.yaml to provide HTTP transport settings
and other configuration options for the MCP server.

Also handles .bees/config.json for hive configuration management.
"""

import ipaddress
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional
import yaml


class Config:
    """Configuration object for Bees MCP Server."""

    def __init__(self, config_data: Dict[str, Any]):
        """Initialize configuration from parsed YAML data.

        Args:
            config_data: Dictionary containing configuration values
        """
        self._data = config_data

        # Parse HTTP configuration with defaults
        http_config = config_data.get('http', {})
        raw_host = http_config.get('host', '127.0.0.1')
        self.http_host = self._validate_host(raw_host)

        # Port type coercion and validation
        port_value = http_config.get('port', 8000)
        try:
            self.http_port = int(port_value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Port must be a valid integer, got: {port_value}") from e

        # Port range validation
        if not (1 <= self.http_port <= 65535):
            raise ValueError(f"Port must be an integer between 1 and 65535, got: {self.http_port}")

        # Parse ticket directory configuration
        self.ticket_directory = config_data.get('ticket_directory', './tickets')

    def _validate_host(self, host: str) -> str:
        """Validate that host is a valid IPv4 or IPv6 address.

        Args:
            host: Host string to validate

        Returns:
            The validated host string

        Raises:
            ValueError: If host is not a valid IP address
        """
        if not host:
            raise ValueError("Host cannot be empty")

        try:
            # Try to parse as IP address (IPv4 or IPv6)
            ipaddress.ip_address(host)
            return host
        except ValueError as e:
            raise ValueError(
                f"Invalid host '{host}': must be a valid IPv4 or IPv6 address. "
                f"Examples: '127.0.0.1', '0.0.0.0', '::1', '::'"
            ) from e

    def __repr__(self) -> str:
        return f"Config(http_host='{self.http_host}', http_port={self.http_port}, ticket_directory='{self.ticket_directory}')"


def load_config(config_path: str = 'config.yaml') -> Config:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config.yaml file (default: 'config.yaml')

    Returns:
        Config object with parsed configuration

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is malformed
    """
    config_file = Path(config_path)

    if not config_file.exists():
        # Return default configuration if file doesn't exist
        return Config({})

    with open(config_file, 'r') as f:
        config_data = yaml.safe_load(f) or {}

    return Config(config_data)


def get_config() -> Config:
    """Get configuration, looking for config.yaml in standard locations.

    Searches for config.yaml in:
    1. Current working directory
    2. Project root (parent of src directory if running from src)

    Returns:
        Config object with parsed configuration or defaults
    """
    # Try current directory first
    if Path('config.yaml').exists():
        return load_config('config.yaml')

    # Try parent directory (if we're in src/)
    parent_config = Path('..') / 'config.yaml'
    if parent_config.exists():
        return load_config(str(parent_config))

    # Return default configuration
    return Config({})


# Hive Configuration (for .bees/config.json)

@dataclass
class HiveConfig:
    """Configuration for a single hive."""
    path: str
    display_name: str


@dataclass
class BeesConfig:
    """Configuration stored in .bees/config.json for hive management."""
    hives: Dict[str, HiveConfig] = field(default_factory=dict)
    allow_cross_hive_dependencies: bool = False
    schema_version: str = "1.0"


# Constants for hive config file
BEES_CONFIG_DIR = ".bees"
BEES_CONFIG_FILENAME = "config.json"


def get_config_path() -> Path:
    """Get the path to the .bees/config.json file.

    Returns:
        Path to the config file in the current working directory
    """
    return Path.cwd() / BEES_CONFIG_DIR / BEES_CONFIG_FILENAME


def ensure_bees_dir() -> None:
    """Create .bees/ directory if it doesn't exist."""
    bees_dir = Path.cwd() / BEES_CONFIG_DIR
    bees_dir.mkdir(exist_ok=True)


def load_bees_config() -> Optional[BeesConfig]:
    """Load BeesConfig from .bees/config.json.

    Returns:
        BeesConfig object if file exists and is valid, None if file not found

    Raises:
        ValueError: If JSON is malformed or schema_version is invalid
    """
    config_path = get_config_path()

    if not config_path.exists():
        return None

    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Malformed JSON in {config_path}: {e}")

    # Validate schema_version
    schema_version = data.get('schema_version', '1.0')
    if not isinstance(schema_version, str):
        raise ValueError(f"schema_version must be a string, got {type(schema_version)}")

    # Parse hives
    hives_data = data.get('hives', {})
    hives = {}
    for name, hive_data in hives_data.items():
        if not isinstance(hive_data, dict):
            raise ValueError(f"Hive '{name}' data must be a dict, got {type(hive_data)}")
        hives[name] = HiveConfig(
            path=hive_data.get('path', ''),
            display_name=hive_data.get('display_name', '')
        )

    return BeesConfig(
        hives=hives,
        allow_cross_hive_dependencies=data.get('allow_cross_hive_dependencies', False),
        schema_version=schema_version
    )


def save_bees_config(config: BeesConfig) -> None:
    """Save BeesConfig to .bees/config.json.

    Args:
        config: BeesConfig object to save

    Raises:
        IOError: If writing fails
    """
    # Ensure .bees/ directory exists
    ensure_bees_dir()

    # Set schema_version if not set
    if not config.schema_version:
        config.schema_version = '1.0'

    # Convert hives to dict format
    hives_dict = {}
    for name, hive_config in config.hives.items():
        hives_dict[name] = {
            'path': hive_config.path,
            'display_name': hive_config.display_name
        }

    # Build JSON structure
    data = {
        'hives': hives_dict,
        'allow_cross_hive_dependencies': config.allow_cross_hive_dependencies,
        'schema_version': config.schema_version
    }

    # Write to file
    config_path = get_config_path()
    try:
        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        raise IOError(f"Failed to write config to {config_path}: {e}")


def init_bees_config_if_needed() -> BeesConfig:
    """Initialize .bees/config.json on-demand if it doesn't exist.

    Returns:
        BeesConfig object (either loaded from file or newly created)
    """
    config = load_bees_config()

    if config is None:
        # Create new config with defaults
        config = BeesConfig(
            hives={},
            allow_cross_hive_dependencies=False,
            schema_version='1.0'
        )
        save_bees_config(config)

    return config


def validate_unique_hive_name(normalized_name: str, config: Optional[BeesConfig] = None) -> None:
    """Validate that a normalized hive name is unique.

    Args:
        normalized_name: The normalized name to check (e.g., 'back_end')
        config: BeesConfig object to check against (loads from disk if None)

    Raises:
        ValueError: If the normalized name already exists in the hive registry

    Note:
        This checks against existing hive keys, which are already normalized names.
        This prevents 'Back End' and 'back end' from both being registered since
        they normalize to the same key.
    """
    if config is None:
        config = load_bees_config()

    # If no config exists yet, name is unique by default
    if config is None:
        return

    # Check if normalized name already exists as a hive key
    if normalized_name in config.hives:
        raise ValueError(
            f"A hive with normalized name '{normalized_name}' already exists. "
            f"Display name: '{config.hives[normalized_name].display_name}'"
        )
