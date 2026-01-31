"""CLI module for running the linter.

This module provides a command-line interface for running the ticket linter
and displaying validation results. It integrates with the corruption state
tracking system to mark the database as corrupt when errors are found.
"""

import argparse
import logging
import sys
from pathlib import Path

from src.linter import Linter
from src.corruption_state import mark_corrupt, mark_clean
from src.index_generator import generate_index, is_index_stale
from src.paths import get_index_path, TICKETS_DIR
from src.watcher import start_watcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def format_error_output(report) -> str:
    """Format linter report errors for CLI output.

    Args:
        report: LinterReport containing validation errors

    Returns:
        Formatted string with error details
    """
    if not report.errors:
        return "No validation errors found."

    lines = [f"Found {len(report.errors)} validation error(s):\n"]

    # Group errors by ticket ID for better readability
    errors_by_ticket = {}
    for error in report.errors:
        ticket_id = error.ticket_id
        if ticket_id not in errors_by_ticket:
            errors_by_ticket[ticket_id] = []
        errors_by_ticket[ticket_id].append(error)

    # Format errors by ticket
    for ticket_id, errors in sorted(errors_by_ticket.items()):
        lines.append(f"\nTicket: {ticket_id}")
        for error in errors:
            severity_marker = "ERROR" if error.severity == "error" else "WARNING"
            lines.append(f"  [{severity_marker}] {error.error_type}: {error.message}")

    return "\n".join(lines)


def regenerate_index(force: bool = False) -> int:
    """Regenerate the index.md file.

    Scans all tickets and regenerates index.md with current state.

    Args:
        force: If True, regenerate even if index is up-to-date

    Returns:
        Exit code: 0 if successful, 2 if exception
    """
    try:
        # Check if regeneration is needed
        if not force and not is_index_stale():
            logger.info("Index is up-to-date, skipping regeneration (use --force to regenerate anyway)")
            print("Index is already up-to-date")
            return 0

        # Generate index markdown
        logger.info("Generating index...")
        index_content = generate_index()

        # Get index path
        index_path = get_index_path()

        # Write index file
        logger.info(f"Writing index to {index_path}")
        index_path.write_text(index_content)

        print(f"Index regenerated successfully: {index_path}")
        return 0

    except Exception as e:
        logger.error(f"Error regenerating index: {e}", exc_info=True)
        print(f"Error: {e}", file=sys.stderr)
        return 2


def run_linter(tickets_dir: str = "tickets", json_output: bool = False) -> int:
    """Run linter and display results.

    Args:
        tickets_dir: Path to tickets directory
        json_output: If True, output as JSON; otherwise human-readable format

    Returns:
        Exit code: 0 if no errors, 1 if errors found, 2 if exception
    """
    try:
        # Run linter
        logger.info(f"Running linter on {tickets_dir}")
        linter = Linter(tickets_dir=tickets_dir)
        report = linter.run()

        # Update corruption state
        if report.errors:
            mark_corrupt(report)
            logger.warning(f"Database marked as corrupt ({len(report.errors)} errors)")
        else:
            mark_clean()
            logger.info("Database marked as clean")

        # Output results
        if json_output:
            print(report.to_json())
        else:
            print(format_error_output(report))

        # Return exit code
        return 1 if report.errors else 0

    except FileNotFoundError as e:
        logger.error(f"Tickets directory not found: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        logger.error(f"Unexpected error running linter: {e}", exc_info=True)
        print(f"Error: {e}", file=sys.stderr)
        return 2


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Bees ticket system CLI"
    )

    # Add subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Linter subcommand (default)
    linter_parser = subparsers.add_parser(
        "lint",
        help="Run ticket linter to validate ticket database"
    )
    linter_parser.add_argument(
        "--tickets-dir",
        default="tickets",
        help="Path to tickets directory (default: tickets)"
    )
    linter_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    # Regenerate index subcommand
    regen_parser = subparsers.add_parser(
        "regenerate-index",
        help="Regenerate the index.md file"
    )
    regen_parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration even if index is up-to-date"
    )

    # Watch subcommand
    watch_parser = subparsers.add_parser(
        "watch",
        help="Watch tickets directory and auto-regenerate index on changes"
    )
    watch_parser.add_argument(
        "--debounce",
        type=float,
        default=2.0,
        help="Seconds to wait after last change before regenerating (default: 2.0)"
    )

    # Global arguments
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Execute command
    if args.command == "regenerate-index":
        force = getattr(args, "force", False)
        exit_code = regenerate_index(force=force)
    elif args.command == "watch":
        debounce = getattr(args, "debounce", 2.0)
        try:
            start_watcher(tickets_dir=TICKETS_DIR, debounce_seconds=debounce)
            exit_code = 0
        except KeyboardInterrupt:
            exit_code = 0
        except Exception as e:
            logger.error(f"Watcher error: {e}", exc_info=True)
            print(f"Error: {e}", file=sys.stderr)
            exit_code = 2
    elif args.command == "lint" or args.command is None:
        # Default to lint for backward compatibility
        tickets_dir = getattr(args, "tickets_dir", "tickets")
        json_output = getattr(args, "json", False)
        exit_code = run_linter(tickets_dir=tickets_dir, json_output=json_output)
    else:
        parser.print_help()
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
