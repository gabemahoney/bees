"""
Main entry point for the Bees MCP Server.

Provides CLI command to start the MCP server with configuration management.
"""

import logging
import signal
import sys
from pathlib import Path
from typing import Any, Dict

import yaml

from .mcp_server import mcp, start_server, stop_server
from .corruption_state import is_corrupt, get_report

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to configuration file (default: config.yaml)

    Returns:
        dict: Configuration settings

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is malformed
    """
    config_file = Path(config_path)

    if not config_file.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}\n"
            f"Please create a config.yaml file with server settings."
        )

    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)

        if not config:
            raise ValueError("Configuration file is empty")

        # Validate required fields
        required_fields = ['host', 'port', 'ticket_directory']
        missing_fields = [field for field in required_fields if field not in config]

        if missing_fields:
            raise ValueError(
                f"Missing required configuration fields: {', '.join(missing_fields)}"
            )

        return config

    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Failed to parse configuration file: {e}")


def setup_signal_handlers(shutdown_callback):
    """
    Set up signal handlers for graceful shutdown.

    Args:
        shutdown_callback: Function to call on shutdown signal
    """
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        shutdown_callback()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def main():
    """
    Main entry point for starting the MCP server.

    Loads configuration, initializes the server, and handles graceful shutdown.
    """
    try:
        # Check for database corruption before starting
        if is_corrupt():
            logger.error("=" * 60)
            logger.error("DATABASE CORRUPTION DETECTED")
            logger.error("=" * 60)
            logger.error("The ticket database is corrupt. MCP server cannot start.")
            logger.error("Run the linter to see validation errors:")
            logger.error("  python -m src.cli --tickets-dir tickets")
            logger.error("")

            # Display corruption report if available
            report = get_report()
            if report:
                error_count = report.get('error_count', 0)
                logger.error(f"Found {error_count} validation error(s)")

                # Show a sample of errors
                errors = report.get('errors', [])
                if errors:
                    logger.error("\nSample errors:")
                    for error in errors[:5]:  # Show first 5 errors
                        logger.error(f"  - [{error.get('error_type')}] {error.get('message')}")

                    if len(errors) > 5:
                        logger.error(f"  ... and {len(errors) - 5} more error(s)")

            logger.error("")
            logger.error("Fix the validation errors and run the linter again to clear")
            logger.error("the corruption state.")
            logger.error("=" * 60)
            sys.exit(1)

        # Load configuration
        logger.info("Loading configuration...")
        config = load_config()

        host = config.get('host', 'localhost')
        port = config.get('port', 8000)
        ticket_directory = config.get('ticket_directory', './tickets')

        # Validate ticket directory exists
        ticket_dir_path = Path(ticket_directory)
        if not ticket_dir_path.exists():
            logger.warning(
                f"Ticket directory does not exist: {ticket_directory}\n"
                f"Creating directory..."
            )
            ticket_dir_path.mkdir(parents=True, exist_ok=True)

        # Set up signal handlers for graceful shutdown
        setup_signal_handlers(stop_server)

        # Display startup information
        logger.info("=" * 60)
        logger.info("Bees MCP Server")
        logger.info("=" * 60)
        logger.info(f"Host: {host}")
        logger.info(f"Port: {port}")
        logger.info(f"Ticket Directory: {ticket_directory}")
        logger.info("=" * 60)

        # Start the server
        start_server()

        logger.info("MCP Server is running. Press Ctrl+C to stop.")

        # Run the FastMCP server
        mcp.run()

    except FileNotFoundError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error(f"Configuration parsing error: {e}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Configuration validation error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
