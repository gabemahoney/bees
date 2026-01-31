"""
Main entry point for the Bees MCP Server.

Provides CLI command to start the MCP server with configuration management.
"""

import logging
import signal
import sys
from pathlib import Path
import uvicorn

from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import Config, load_config
from .mcp_server import mcp, start_server, stop_server, _health_check
from .corruption_state import is_corrupt, get_report

# Ensure log directory exists
log_dir = Path.home() / '.bees'
log_dir.mkdir(exist_ok=True)

# Configure logging to file for MCP stdio compatibility
# Note: This may not take effect if mcp_server is imported first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename=log_dir / 'mcp.log',
    filemode='a'
)
logger = logging.getLogger(__name__)


async def health_endpoint(request: Request) -> JSONResponse:
    """
    HTTP endpoint handler for /health route.

    Returns JSON health status from the MCP server's health check function.
    Supports both GET and POST methods.

    Returns:
        JSONResponse: Health status with 200 OK
    """
    try:
        health_data = _health_check()
        return JSONResponse(content=health_data, status_code=200)
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            content={"status": "error", "message": str(e)},
            status_code=500
        )


def setup_http_routes(app):
    """
    Configure HTTP endpoint routes on the Starlette application.

    Adds custom route for /health endpoint. The /mcp endpoint is already
    provided by FastMCP's http_app and handles MCP JSON-RPC protocol.

    Args:
        app: Starlette application instance
    """
    # Add /health endpoint (supports GET and POST)
    app.add_route("/health", health_endpoint, methods=["GET", "POST"])

    logger.info("HTTP routes configured: /health")
    logger.info("MCP endpoint /mcp provided by FastMCP")


def setup_signal_handlers(shutdown_callback):
    """
    Set up signal handlers for graceful shutdown.

    Args:
        shutdown_callback: Function to call on shutdown signal
    """
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        shutdown_callback()
        # Don't call sys.exit(0) - let uvicorn complete its graceful shutdown

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

        host = config.http_host
        port = config.http_port
        ticket_directory = config.ticket_directory

        # Validate ticket directory exists
        ticket_dir_path = Path(ticket_directory)
        if not ticket_dir_path.exists():
            logger.warning(
                f"Ticket directory does not exist: {ticket_directory}\n"
                f"Creating directory..."
            )
            ticket_dir_path.mkdir(parents=True, exist_ok=True)

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

        # Get the Starlette app from FastMCP
        http_app = mcp.http_app()

        # Set up HTTP routes on FastMCP's Starlette app
        setup_http_routes(http_app)

        # Set up signal handlers for graceful shutdown (after server initialization)
        setup_signal_handlers(stop_server)

        logger.info(f"Launching HTTP server on {host}:{port}...")
        logger.info("MCP Server is running. Press Ctrl+C to stop.")

        # Run the FastMCP server with HTTP transport via uvicorn
        uvicorn.run(
            http_app,
            host=host,
            port=port,
            log_level="info"
        )

    except FileNotFoundError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Configuration validation error: {e}")
        sys.exit(1)
    except OSError as e:
        # Handle HTTP server errors (port in use, permission denied, etc.)
        if "Address already in use" in str(e) or e.errno == 48:
            logger.error(f"Failed to start server: Port {port} is already in use")
            logger.error(f"Please stop the other service using port {port} or change the port in config.yaml")
        elif "Permission denied" in str(e) or e.errno == 13:
            logger.error(f"Failed to start server: Permission denied for {host}:{port}")
            logger.error(f"Try using a port number above 1024 or run with appropriate permissions")
        else:
            logger.error(f"Failed to start server: Network error - {e}")
            logger.error(f"Check that {host}:{port} is a valid address")
        sys.exit(1)
    except ImportError as e:
        logger.error(f"Failed to start server: Missing dependency - {e}")
        logger.error("Please install required dependencies with: poetry install")
        sys.exit(1)
    except RuntimeError as e:
        logger.error(f"Failed to start server: Runtime error - {e}")
        logger.error("Check server configuration and logs for details")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
