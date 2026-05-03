"""Tests for the `bees update-config` CLI command (src/cli.py handle_update_config).

PURPOSE:
  Verifies that the update-config subcommand correctly proxies run_pending_migrations()
  output as JSON, exits with code 0 on success, and accepts the --test-config and
  --details flags.

SCOPE - Tests that belong here:
  - exit code and JSON output for the already-up-to-date case
  - exit code and JSON output for the pending-migrations case
  - --test-config flag acceptance on update-config
  - --details flag routes to preview_pending_migrations, not run_pending_migrations
"""

import json
from unittest.mock import patch

import pytest

_UP_TO_DATE = {"status": "success", "message": "Already up to date", "version": "2.0"}
_ERROR = {"status": "error", "message": "Migration failed", "error_type": "migration_error"}
_APPLIED = {
    "status": "success",
    "message": "Applied 1 migration(s)",
    "applied_hops": [{"from_version": "1.0", "to_version": "2.0"}],
    "final_version": "2.0",
}


class TestUpdateConfigCLI:
    @pytest.mark.parametrize(
        "mock_result,expected_message",
        [
            pytest.param(_UP_TO_DATE, "Already up to date", id="already_up_to_date"),
            pytest.param(_APPLIED, "Applied 1 migration(s)", id="pending_migrations"),
        ],
    )
    def test_exits_0_and_outputs_message(self, cli_runner, mock_result, expected_message):
        """update-config exits 0 and includes the migration message in JSON output."""
        with patch("src.cli.run_pending_migrations", return_value=mock_result):
            stdout, exit_code = cli_runner(["update-config"])

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"
        assert result["message"] == expected_message

    def test_applied_hops_present_in_output(self, cli_runner):
        """Pending-migrations result includes applied_hops and final_version."""
        with patch("src.cli.run_pending_migrations", return_value=_APPLIED):
            stdout, exit_code = cli_runner(["update-config"])

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["applied_hops"] == [{"from_version": "1.0", "to_version": "2.0"}]
        assert result["final_version"] == "2.0"

    def test_error_exits_1(self, cli_runner):
        """update-config exits 1 when run_pending_migrations returns an error."""
        with patch("src.cli.run_pending_migrations", return_value=_ERROR):
            stdout, exit_code = cli_runner(["update-config"])

        assert exit_code == 1
        result = json.loads(stdout)
        assert result["status"] == "error"

    def test_test_config_flag_accepted(self, cli_runner):
        """--test-config (no value) is accepted and update-config still exits 0."""
        with patch("src.cli.run_pending_migrations", return_value=_UP_TO_DATE):
            stdout, exit_code = cli_runner(["update-config", "--test-config"])

        assert exit_code == 0
        assert json.loads(stdout)["status"] == "success"

    def test_details_flag_pending_migrations(self, cli_runner):
        """--details calls preview_pending_migrations (not run_pending_migrations) and returns pending_hops."""
        preview_result = {
            "status": "success",
            "current_version": "1.0",
            "pending_hops": [{"from_version": "1.0", "to_version": "2.0", "description": "Add field X"}],
        }
        with patch("src.cli.preview_pending_migrations", return_value=preview_result) as mock_preview, \
             patch("src.cli.run_pending_migrations") as mock_run:
            stdout, exit_code = cli_runner(["update-config", "--details"])

        assert exit_code == 0
        mock_preview.assert_called_once()
        mock_run.assert_not_called()
        result = json.loads(stdout)
        assert result["status"] == "success"
        assert result["pending_hops"] == [{"from_version": "1.0", "to_version": "2.0", "description": "Add field X"}]

    def test_details_flag_up_to_date(self, cli_runner):
        """--details when up to date returns success with a message containing 'up to date'."""
        preview_result = {
            "status": "success",
            "message": "Config is up to date (version 2.0). No pending migrations.",
            "current_version": "2.0",
            "pending_hops": [],
        }
        with patch("src.cli.preview_pending_migrations", return_value=preview_result):
            stdout, exit_code = cli_runner(["update-config", "--details"])

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"
        assert "up to date" in result["message"]

    def test_no_details_flag_uses_run_pending(self, cli_runner):
        """Without --details, run_pending_migrations is called (existing behavior unchanged)."""
        with patch("src.cli.run_pending_migrations", return_value=_UP_TO_DATE) as mock_run, \
             patch("src.cli.preview_pending_migrations") as mock_preview:
            stdout, exit_code = cli_runner(["update-config"])

        assert exit_code == 0
        mock_run.assert_called_once()
        mock_preview.assert_not_called()
        result = json.loads(stdout)
        assert result["status"] == "success"
