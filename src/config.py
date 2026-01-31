"""Configuration management for Bees MCP Server.

Loads and parses config.yaml to provide HTTP transport settings
and other configuration options for the MCP server.
"""

import ipaddress
import os
from pathlib import Path
from typing import Dict, Any
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
