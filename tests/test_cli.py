"""Unit tests for CLI module."""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from src.cli import run_linter, format_error_output, main
from src.linter_report import LinterReport


@pytest.fixture
def sample_report_with_errors():
    """Create sample linter report with errors."""
    report = LinterReport()
    report.add_error(
        ticket_id="bees-abc",
        error_type="id_format",
        message="Ticket ID 'bees-ABC' does not match required format: bees-[a-z0-9]{3}",
        severity="error"
    )
    report.add_error(
        ticket_id="bees-abc",
        error_type="duplicate_id",
        message="Duplicate ticket ID 'bees-abc' found (also in epic)",
        severity="error"
    )
    report.add_error(
        ticket_id="bees-xyz",
        error_type="dependency_cycle",
        message="Cycle detected in blocking dependencies: bees-xyz -> bees-abc -> bees-xyz",
        severity="error"
    )
    return report


@pytest.fixture
def sample_clean_report():
    """Create sample linter report with no errors."""
    return LinterReport()


class TestFormatErrorOutput:
    """Test format_error_output function."""

    def test_format_no_errors(self, sample_clean_report):
        """Test formatting when report has no errors."""
        output = format_error_output(sample_clean_report)
        assert output == "No validation errors found."

    def test_format_with_errors(self, sample_report_with_errors):
        """Test formatting when report has errors."""
        output = format_error_output(sample_report_with_errors)

        assert "Found 3 validation error(s):" in output
        assert "Ticket: bees-abc" in output
        assert "Ticket: bees-xyz" in output
        assert "[ERROR]" in output
        assert "id_format" in output
        assert "duplicate_id" in output
        assert "dependency_cycle" in output

    def test_format_groups_by_ticket_id(self, sample_report_with_errors):
        """Test that errors are grouped by ticket ID."""
        output = format_error_output(sample_report_with_errors)

        # Check that ticket headers appear in sorted order
        abc_pos = output.find("Ticket: bees-abc")
        xyz_pos = output.find("Ticket: bees-xyz")
        assert abc_pos < xyz_pos

        # Check that errors for bees-abc are between its header and next header
        abc_section = output[abc_pos:xyz_pos]
        assert "id_format" in abc_section
        assert "duplicate_id" in abc_section

    def test_format_handles_warnings(self):
        """Test formatting with warning severity."""
        report = LinterReport()
        report.add_error(
            ticket_id="bees-abc",
            error_type="test_warning",
            message="This is a warning",
            severity="warning"
        )

        output = format_error_output(report)
        assert "[WARNING]" in output


class TestRunLinter:
    """Test run_linter function."""

    @patch('src.cli.Linter')
    @patch('src.cli.mark_corrupt')
    @patch('src.cli.mark_clean')
    def test_run_linter_with_errors(self, mock_mark_clean, mock_mark_corrupt, mock_linter_class, sample_report_with_errors):
        """Test run_linter when errors are found."""
        mock_linter = Mock()
        mock_linter.run.return_value = sample_report_with_errors
        mock_linter_class.return_value = mock_linter

        exit_code = run_linter(tickets_dir="tickets", json_output=False)

        assert exit_code == 1
        mock_linter_class.assert_called_once_with(tickets_dir="tickets")
        mock_linter.run.assert_called_once()
        mock_mark_corrupt.assert_called_once_with(sample_report_with_errors)
        mock_mark_clean.assert_not_called()

    @patch('src.cli.Linter')
    @patch('src.cli.mark_corrupt')
    @patch('src.cli.mark_clean')
    def test_run_linter_clean(self, mock_mark_clean, mock_mark_corrupt, mock_linter_class, sample_clean_report):
        """Test run_linter when no errors are found."""
        mock_linter = Mock()
        mock_linter.run.return_value = sample_clean_report
        mock_linter_class.return_value = mock_linter

        exit_code = run_linter(tickets_dir="tickets", json_output=False)

        assert exit_code == 0
        mock_linter_class.assert_called_once_with(tickets_dir="tickets")
        mock_linter.run.assert_called_once()
        mock_mark_clean.assert_called_once()
        mock_mark_corrupt.assert_not_called()

    @patch('src.cli.Linter')
    @patch('src.cli.mark_corrupt')
    @patch('src.cli.mark_clean')
    @patch('builtins.print')
    def test_run_linter_json_output(self, mock_print, mock_mark_clean, mock_mark_corrupt, mock_linter_class, sample_report_with_errors):
        """Test run_linter with JSON output."""
        mock_linter = Mock()
        mock_linter.run.return_value = sample_report_with_errors
        mock_linter_class.return_value = mock_linter

        exit_code = run_linter(tickets_dir="tickets", json_output=True)

        assert exit_code == 1
        # Verify JSON was printed
        mock_print.assert_called_once()
        printed_output = mock_print.call_args[0][0]
        # Should be valid JSON
        json.loads(printed_output)

    @patch('src.cli.Linter')
    @patch('src.cli.mark_corrupt')
    @patch('src.cli.mark_clean')
    @patch('builtins.print')
    def test_run_linter_human_readable_output(self, mock_print, mock_mark_clean, mock_mark_corrupt, mock_linter_class, sample_report_with_errors):
        """Test run_linter with human-readable output."""
        mock_linter = Mock()
        mock_linter.run.return_value = sample_report_with_errors
        mock_linter_class.return_value = mock_linter

        exit_code = run_linter(tickets_dir="tickets", json_output=False)

        assert exit_code == 1
        # Verify formatted output was printed
        mock_print.assert_called_once()
        printed_output = mock_print.call_args[0][0]
        assert "Found 3 validation error(s):" in printed_output

    @patch('src.cli.Linter')
    def test_run_linter_handles_file_not_found(self, mock_linter_class):
        """Test run_linter handles FileNotFoundError."""
        mock_linter = Mock()
        mock_linter.run.side_effect = FileNotFoundError("Tickets directory not found")
        mock_linter_class.return_value = mock_linter

        exit_code = run_linter(tickets_dir="nonexistent", json_output=False)

        assert exit_code == 2

    @patch('src.cli.Linter')
    def test_run_linter_handles_exception(self, mock_linter_class):
        """Test run_linter handles unexpected exceptions."""
        mock_linter = Mock()
        mock_linter.run.side_effect = Exception("Unexpected error")
        mock_linter_class.return_value = mock_linter

        exit_code = run_linter(tickets_dir="tickets", json_output=False)

        assert exit_code == 2

    @patch('src.cli.Linter')
    @patch('src.cli.mark_corrupt')
    @patch('src.cli.mark_clean')
    def test_run_linter_custom_tickets_dir(self, mock_mark_clean, mock_mark_corrupt, mock_linter_class, sample_clean_report):
        """Test run_linter with custom tickets directory."""
        mock_linter = Mock()
        mock_linter.run.return_value = sample_clean_report
        mock_linter_class.return_value = mock_linter

        exit_code = run_linter(tickets_dir="/custom/path", json_output=False)

        assert exit_code == 0
        mock_linter_class.assert_called_once_with(tickets_dir="/custom/path")


class TestMain:
    """Test main CLI entry point."""

    @patch('src.cli.run_linter')
    @patch('sys.argv', ['cli.py'])
    def test_main_default_args(self, mock_run_linter):
        """Test main with default arguments."""
        mock_run_linter.return_value = 0

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        mock_run_linter.assert_called_once_with(tickets_dir="tickets", json_output=False)

    @patch('src.cli.run_linter')
    @patch('sys.argv', ['cli.py', 'lint', '--tickets-dir', '/custom/path'])
    def test_main_custom_tickets_dir(self, mock_run_linter):
        """Test main with custom tickets directory."""
        mock_run_linter.return_value = 0

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        mock_run_linter.assert_called_once_with(tickets_dir="/custom/path", json_output=False)

    @patch('src.cli.run_linter')
    @patch('sys.argv', ['cli.py', 'lint', '--json'])
    def test_main_json_output(self, mock_run_linter):
        """Test main with JSON output flag."""
        mock_run_linter.return_value = 0

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        mock_run_linter.assert_called_once_with(tickets_dir="tickets", json_output=True)

    @patch('src.cli.run_linter')
    @patch('sys.argv', ['cli.py', '-v'])
    @patch('logging.getLogger')
    def test_main_verbose_flag(self, mock_get_logger, mock_run_linter):
        """Test main with verbose flag."""
        mock_run_linter.return_value = 0
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        # Verify logging level was set (indirectly through getLogger call)
        mock_get_logger.assert_called()

    @patch('src.cli.run_linter')
    @patch('sys.argv', ['cli.py'])
    def test_main_propagates_exit_codes(self, mock_run_linter):
        """Test that main propagates exit codes from run_linter."""
        # Test exit code 1 (errors found)
        mock_run_linter.return_value = 1
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

        # Test exit code 2 (exception)
        mock_run_linter.return_value = 2
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2


class TestCLIIntegration:
    """Integration tests for CLI with real linter."""

    def test_cli_with_empty_directory(self, tmp_path):
        """Test CLI with empty tickets directory."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "epics").mkdir()
        (tickets_dir / "tasks").mkdir()
        (tickets_dir / "subtasks").mkdir()

        exit_code = run_linter(tickets_dir=str(tickets_dir), json_output=False)

        assert exit_code == 0  # No errors for empty directory

    @patch('src.cli.Linter')
    @patch('src.cli.mark_corrupt')
    @patch('src.cli.mark_clean')
    def test_cli_error_output_format(self, mock_mark_clean, mock_mark_corrupt, mock_linter_class, sample_report_with_errors, capsys):
        """Test that CLI outputs properly formatted error messages."""
        mock_linter = Mock()
        mock_linter.run.return_value = sample_report_with_errors
        mock_linter_class.return_value = mock_linter

        run_linter(tickets_dir="tickets", json_output=False)

        captured = capsys.readouterr()
        output = captured.out

        assert "Found 3 validation error(s):" in output
        assert "bees-abc" in output
        assert "bees-xyz" in output
