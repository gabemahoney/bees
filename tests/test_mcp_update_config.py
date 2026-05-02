"""Tests for the update_config MCP tool (src/mcp_server.py).

PURPOSE:
  Verifies that the update_config MCP tool delegates to run_pending_migrations()
  and returns its result unchanged.

SCOPE - Tests that belong here:
  - up-to-date case: returns success with "Already up to date" message
  - pending-migrations case: returns applied_hops and final_version

SCOPE - Tests that DON'T belong here:
  - Migration logic itself -> test_migration_runner.py
  - CLI surface -> test_cli_update_config.py
"""

import pytest

import src.mcp_server as mcp_mod
from src.mcp_server import update_config

_UP_TO_DATE = {"status": "success", "message": "Already up to date", "version": "2.0"}
_ERROR = {"status": "error", "message": "Migration failed", "error_type": "migration_error"}
_APPLIED = {
    "status": "success",
    "message": "Applied 1 migration(s)",
    "applied_hops": [{"from_version": "1.0", "to_version": "2.0"}],
    "final_version": "2.0",
}


@pytest.mark.parametrize(
    "mock_result,expected_message",
    [
        pytest.param(_UP_TO_DATE, "Already up to date", id="already_up_to_date"),
        pytest.param(_APPLIED, "Applied 1 migration(s)", id="pending_migrations"),
    ],
)
def test_update_config_returns_migration_result(mock_result, expected_message, monkeypatch):
    """update_config MCP tool returns run_pending_migrations() result directly."""
    monkeypatch.setattr(mcp_mod, "run_pending_migrations", lambda: mock_result)
    result = update_config()
    assert result["status"] == "success"
    assert result["message"] == expected_message


def test_update_config_returns_error(monkeypatch):
    """update_config MCP tool passes through error results."""
    monkeypatch.setattr(mcp_mod, "run_pending_migrations", lambda: _ERROR)
    result = update_config()
    assert result["status"] == "error"
    assert result["error_type"] == "migration_error"
