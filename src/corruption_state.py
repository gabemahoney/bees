"""Corruption state tracking module.

This module manages the corruption state of the ticket database. It provides
functions to mark the database as corrupt with a report, check if the database
is corrupt, and clear the corruption state.

The corruption state is stored in .bees/corruption_report.json and contains:
- is_corrupt: Boolean indicating if database is corrupt
- error_count: Number of validation errors found
- report: Full linter report with validation errors
- timestamp: When the corruption state was set
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from src.linter_report import LinterReport

logger = logging.getLogger(__name__)

# Default path for corruption state file
CORRUPTION_STATE_FILE = Path(".bees/corruption_report.json")


class CorruptionState:
    """Manager for database corruption state."""

    def __init__(self, state_file: Path = CORRUPTION_STATE_FILE):
        """Initialize corruption state manager.

        Args:
            state_file: Path to corruption state JSON file
        """
        self.state_file = state_file

    def mark_corrupt(self, report: LinterReport) -> None:
        """Mark database as corrupt with validation report.

        Saves the corruption state to the state file with full linter
        report details.

        Args:
            report: LinterReport containing validation errors
        """
        # Ensure .bees directory exists
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "is_corrupt": True,
            "error_count": len(report.errors),
            "report": report.to_dict(),
            "timestamp": datetime.now().isoformat()
        }

        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)

        logger.info(f"Marked database as corrupt with {len(report.errors)} errors")

    def mark_clean(self) -> None:
        """Mark database as clean (no validation errors).

        Updates the corruption state to indicate the database is not corrupt.
        """
        # Ensure .bees directory exists
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "is_corrupt": False,
            "error_count": 0,
            "report": None,
            "timestamp": datetime.now().isoformat()
        }

        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)

        logger.info("Marked database as clean")

    def is_corrupt(self) -> bool:
        """Check if database is currently marked as corrupt.

        Returns:
            True if database is corrupt, False otherwise
        """
        if not self.state_file.exists():
            return False

        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            return state.get("is_corrupt", False)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error reading corruption state file: {e}")
            return False

    def get_report(self) -> Optional[Dict[str, Any]]:
        """Get the current corruption report if database is corrupt.

        Returns:
            Dictionary containing corruption report, or None if not corrupt
        """
        if not self.state_file.exists():
            return None

        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            if not state.get("is_corrupt", False):
                return None

            return state.get("report")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error reading corruption report: {e}")
            return None

    def clear(self) -> None:
        """Clear corruption state by removing the state file.

        This is useful when manually fixing corruption issues.
        """
        if self.state_file.exists():
            self.state_file.unlink()
            logger.info("Cleared corruption state")


# Convenience functions for global corruption state management
def mark_corrupt(report: LinterReport) -> None:
    """Mark database as corrupt with validation report.

    Args:
        report: LinterReport containing validation errors
    """
    state = CorruptionState()
    state.mark_corrupt(report)


def mark_clean() -> None:
    """Mark database as clean (no validation errors)."""
    state = CorruptionState()
    state.mark_clean()


def is_corrupt() -> bool:
    """Check if database is currently marked as corrupt.

    Returns:
        True if database is corrupt, False otherwise
    """
    state = CorruptionState()
    return state.is_corrupt()


def get_report() -> Optional[Dict[str, Any]]:
    """Get the current corruption report if database is corrupt.

    Returns:
        Dictionary containing corruption report, or None if not corrupt
    """
    state = CorruptionState()
    return state.get_report()


def clear() -> None:
    """Clear corruption state by removing the state file."""
    state = CorruptionState()
    state.clear()
