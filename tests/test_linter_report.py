"""Unit tests for linter report module."""

import pytest
import json

from src.linter_report import ValidationError, LinterReport


class TestValidationError:
    """Tests for ValidationError dataclass."""

    def test_create_validation_error(self):
        """Should create validation error with required fields."""
        error = ValidationError(
            ticket_id="bees-abc",
            error_type="id_format",
            message="Invalid ID format",
            severity="error"
        )

        assert error.ticket_id == "bees-abc"
        assert error.error_type == "id_format"
        assert error.message == "Invalid ID format"
        assert error.severity == "error"

    def test_default_severity_is_error(self):
        """Should default to 'error' severity."""
        error = ValidationError(
            ticket_id="bees-abc",
            error_type="id_format",
            message="Invalid ID"
        )

        assert error.severity == "error"

    def test_warning_severity(self):
        """Should accept 'warning' severity."""
        error = ValidationError(
            ticket_id="bees-abc",
            error_type="minor_issue",
            message="Minor issue",
            severity="warning"
        )

        assert error.severity == "warning"

    def test_invalid_severity_raises_error(self):
        """Should raise error for invalid severity."""
        with pytest.raises(ValueError, match="Invalid severity"):
            ValidationError(
                ticket_id="bees-abc",
                error_type="test",
                message="Test",
                severity="invalid"
            )


class TestLinterReport:
    """Tests for LinterReport class."""

    def test_create_empty_report(self):
        """Should create empty report with no errors."""
        report = LinterReport()

        assert len(report.errors) == 0
        assert not report.is_corrupt()

    def test_add_error(self):
        """Should add error to report."""
        report = LinterReport()
        report.add_error(
            ticket_id="bees-abc",
            error_type="id_format",
            message="Invalid ID",
            severity="error"
        )

        assert len(report.errors) == 1
        assert report.errors[0].ticket_id == "bees-abc"
        assert report.errors[0].error_type == "id_format"

    def test_add_multiple_errors(self):
        """Should add multiple errors."""
        report = LinterReport()
        report.add_error("bees-abc", "id_format", "Error 1")
        report.add_error("bees-xyz", "duplicate_id", "Error 2")

        assert len(report.errors) == 2

    def test_get_errors_no_filter(self):
        """Should return all errors when no filter specified."""
        report = LinterReport()
        report.add_error("bees-abc", "id_format", "Error 1")
        report.add_error("bees-xyz", "duplicate_id", "Error 2")

        errors = report.get_errors()

        assert len(errors) == 2

    def test_get_errors_filter_by_ticket_id(self):
        """Should filter errors by ticket ID."""
        report = LinterReport()
        report.add_error("bees-abc", "id_format", "Error 1")
        report.add_error("bees-xyz", "duplicate_id", "Error 2")
        report.add_error("bees-abc", "missing_parent", "Error 3")

        errors = report.get_errors(ticket_id="bees-abc")

        assert len(errors) == 2
        assert all(e.ticket_id == "bees-abc" for e in errors)

    def test_get_errors_filter_by_error_type(self):
        """Should filter errors by error type."""
        report = LinterReport()
        report.add_error("bees-abc", "id_format", "Error 1")
        report.add_error("bees-xyz", "id_format", "Error 2")
        report.add_error("bees-abc", "duplicate_id", "Error 3")

        errors = report.get_errors(error_type="id_format")

        assert len(errors) == 2
        assert all(e.error_type == "id_format" for e in errors)

    def test_get_errors_filter_by_severity(self):
        """Should filter errors by severity."""
        report = LinterReport()
        report.add_error("bees-abc", "id_format", "Error", severity="error")
        report.add_error("bees-xyz", "minor", "Warning", severity="warning")
        report.add_error("bees-123", "bad_id", "Error", severity="error")

        errors = report.get_errors(severity="error")
        warnings = report.get_errors(severity="warning")

        assert len(errors) == 2
        assert len(warnings) == 1

    def test_get_errors_multiple_filters(self):
        """Should filter by multiple criteria."""
        report = LinterReport()
        report.add_error("bees-abc", "id_format", "Error", severity="error")
        report.add_error("bees-abc", "id_format", "Warning", severity="warning")
        report.add_error("bees-xyz", "id_format", "Error", severity="error")

        errors = report.get_errors(ticket_id="bees-abc", severity="error")

        assert len(errors) == 1
        assert errors[0].ticket_id == "bees-abc"
        assert errors[0].severity == "error"

    def test_is_corrupt_with_errors(self):
        """Should return True when report has errors."""
        report = LinterReport()
        report.add_error("bees-abc", "id_format", "Error", severity="error")

        assert report.is_corrupt()

    def test_is_corrupt_with_only_warnings(self):
        """Should return False when only warnings present."""
        report = LinterReport()
        report.add_error("bees-abc", "minor", "Warning", severity="warning")

        assert not report.is_corrupt()

    def test_is_corrupt_empty_report(self):
        """Should return False for empty report."""
        report = LinterReport()

        assert not report.is_corrupt()

    def test_to_dict(self):
        """Should convert report to dictionary."""
        report = LinterReport()
        report.add_error("bees-abc", "id_format", "Error 1", severity="error")
        report.add_error("bees-xyz", "minor", "Warning 1", severity="warning")

        result = report.to_dict()

        assert result['is_corrupt'] is True
        assert result['error_count'] == 1
        assert result['warning_count'] == 1
        assert len(result['errors']) == 2

    def test_to_json(self):
        """Should generate valid JSON."""
        report = LinterReport()
        report.add_error("bees-abc", "id_format", "Error")

        json_str = report.to_json()
        parsed = json.loads(json_str)

        assert parsed['is_corrupt'] is True
        assert parsed['error_count'] == 1
        assert len(parsed['errors']) == 1

    def test_get_summary(self):
        """Should return summary statistics."""
        report = LinterReport()
        report.add_error("bees-abc", "id_format", "Error 1", severity="error")
        report.add_error("bees-xyz", "id_format", "Error 2", severity="error")
        report.add_error("bees-123", "duplicate_id", "Error 3", severity="error")
        report.add_error("bees-abc", "minor", "Warning", severity="warning")

        summary = report.get_summary()

        assert summary['total_errors'] == 3
        assert summary['total_warnings'] == 1
        assert summary['affected_tickets'] == 3
        assert summary['by_type']['id_format']['errors'] == 2
        assert summary['by_type']['id_format']['warnings'] == 0
        assert summary['by_type']['duplicate_id']['errors'] == 1
        assert summary['by_type']['minor']['warnings'] == 1

    def test_to_markdown_empty(self):
        """Should generate markdown for empty report."""
        report = LinterReport()

        markdown = report.to_markdown()

        assert "No validation errors found" in markdown
        assert "Database is clean" in markdown

    def test_to_markdown_with_errors(self):
        """Should generate markdown with errors grouped by type."""
        report = LinterReport()
        report.add_error("bees-abc", "id_format", "Invalid format", severity="error")
        report.add_error("bees-xyz", "id_format", "Invalid format", severity="error")
        report.add_error("bees-123", "duplicate_id", "Duplicate", severity="error")

        markdown = report.to_markdown()

        assert "# Linter Report" in markdown
        assert "CORRUPT" in markdown
        assert "**Total Errors**: 3" in markdown
        assert "Id Format" in markdown
        assert "Duplicate Id" in markdown
        assert "bees-abc" in markdown
        assert "bees-xyz" in markdown
        assert "bees-123" in markdown

    def test_to_markdown_with_warnings(self):
        """Should handle warnings in markdown output."""
        report = LinterReport()
        report.add_error("bees-abc", "minor", "Minor issue", severity="warning")

        markdown = report.to_markdown()

        assert "Warnings only" in markdown or "Total Warnings: 1" in markdown
