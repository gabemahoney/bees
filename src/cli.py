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
        description="Run ticket linter to validate ticket database"
    )
    parser.add_argument(
        "--tickets-dir",
        default="tickets",
        help="Path to tickets directory (default: tickets)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Run linter
    exit_code = run_linter(tickets_dir=args.tickets_dir, json_output=args.json)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
