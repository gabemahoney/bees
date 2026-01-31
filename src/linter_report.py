"""Linter report module for validation error collection and formatting.

This module provides structured error reporting for linter validation results,
including error collection, querying, and formatted output generation.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
import json


@dataclass
class ValidationError:
    """Represents a single validation error found during linting.

    Attributes:
        ticket_id: ID of the ticket with the validation error
        error_type: Category of error (e.g., 'id_format', 'duplicate_id', 'missing_backlink')
        message: Human-readable error description
        severity: Error severity level ('error' or 'warning')
    """
    ticket_id: str
    error_type: str
    message: str
    severity: str = "error"

    def __post_init__(self):
        """Validate severity is either 'error' or 'warning'."""
        if self.severity not in ('error', 'warning'):
            raise ValueError(f"Invalid severity: {self.severity}. Must be 'error' or 'warning'")


@dataclass
class LinterReport:
    """Collection of validation errors with query and formatting capabilities.

    Provides methods to:
    - Add validation errors
    - Query errors by various criteria
    - Check if database is corrupt
    - Generate formatted reports (JSON, Markdown)
    """

    errors: List[ValidationError] = field(default_factory=list)

    def add_error(self, ticket_id: str, error_type: str, message: str, severity: str = "error") -> None:
        """Add a validation error to the report.

        Args:
            ticket_id: ID of the ticket with the error
            error_type: Category of error
            message: Human-readable error description
            severity: Error severity level (default: 'error')
        """
        error = ValidationError(
            ticket_id=ticket_id,
            error_type=error_type,
            message=message,
            severity=severity
        )
        self.errors.append(error)

    def get_errors(self, ticket_id: str = None, error_type: str = None,
                   severity: str = None) -> List[ValidationError]:
        """Query validation errors by criteria.

        Args:
            ticket_id: Filter by ticket ID (optional)
            error_type: Filter by error type (optional)
            severity: Filter by severity level (optional)

        Returns:
            List of validation errors matching all specified criteria
        """
        results = self.errors

        if ticket_id is not None:
            results = [e for e in results if e.ticket_id == ticket_id]

        if error_type is not None:
            results = [e for e in results if e.error_type == error_type]

        if severity is not None:
            results = [e for e in results if e.severity == severity]

        return results

    def is_corrupt(self) -> bool:
        """Check if database is corrupt (has any errors with severity='error').

        Returns:
            True if database has validation errors (not just warnings)
        """
        return any(e.severity == 'error' for e in self.errors)

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the report
        """
        return {
            'is_corrupt': self.is_corrupt(),
            'error_count': len(self.get_errors(severity='error')),
            'warning_count': len(self.get_errors(severity='warning')),
            'errors': [
                {
                    'ticket_id': e.ticket_id,
                    'error_type': e.error_type,
                    'message': e.message,
                    'severity': e.severity
                }
                for e in self.errors
            ]
        }

    def to_json(self) -> str:
        """Generate JSON report.

        Returns:
            JSON string with validation errors and summary statistics
        """
        return json.dumps(self.to_dict(), indent=2)

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics of validation errors.

        Returns:
            Dictionary with error counts by type and severity
        """
        summary = {
            'total_errors': len(self.get_errors(severity='error')),
            'total_warnings': len(self.get_errors(severity='warning')),
            'by_type': {},
            'affected_tickets': len(set(e.ticket_id for e in self.errors))
        }

        # Count errors by type
        for error in self.errors:
            if error.error_type not in summary['by_type']:
                summary['by_type'][error.error_type] = {'errors': 0, 'warnings': 0}

            if error.severity == 'error':
                summary['by_type'][error.error_type]['errors'] += 1
            else:
                summary['by_type'][error.error_type]['warnings'] += 1

        return summary

    def to_markdown(self) -> str:
        """Generate human-readable Markdown report.

        Returns:
            Markdown-formatted report with errors grouped by type
        """
        if not self.errors:
            return "# Linter Report\n\n✓ No validation errors found. Database is clean.\n"

        lines = ["# Linter Report\n"]

        # Summary section
        summary = self.get_summary()
        lines.append("## Summary\n")
        lines.append(f"- **Status**: {'❌ CORRUPT' if self.is_corrupt() else '⚠️  Warnings only'}")
        lines.append(f"- **Total Errors**: {summary['total_errors']}")
        lines.append(f"- **Total Warnings**: {summary['total_warnings']}")
        lines.append(f"- **Affected Tickets**: {summary['affected_tickets']}\n")

        # Errors by type
        lines.append("## Validation Errors by Type\n")

        errors_by_type = {}
        for error in self.errors:
            if error.error_type not in errors_by_type:
                errors_by_type[error.error_type] = []
            errors_by_type[error.error_type].append(error)

        for error_type in sorted(errors_by_type.keys()):
            type_errors = errors_by_type[error_type]
            error_count = len([e for e in type_errors if e.severity == 'error'])
            warning_count = len([e for e in type_errors if e.severity == 'warning'])

            lines.append(f"### {error_type.replace('_', ' ').title()}")
            lines.append(f"*{error_count} errors, {warning_count} warnings*\n")

            for error in type_errors:
                icon = "❌" if error.severity == "error" else "⚠️"
                lines.append(f"- {icon} **{error.ticket_id}**: {error.message}")

            lines.append("")

        return "\n".join(lines)
