"""Tests for the update_config MCP tool (src/mcp_server.py).

PURPOSE:
  Verifies that the update_config MCP tool delegates to run_pending_migrations()
  or preview_pending_migrations() based on the details_only parameter.

SCOPE - Tests that belong here:
  - up-to-date case: returns success with "Already up to date" message
  - pending-migrations case: returns applied_hops and final_version
  - details_only=True routes to preview_pending_migrations, not run_pending_migrations
  - details_only=False (default) still calls run_pending_migrations

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


def test_update_config_details_only_pending(monkeypatch):
    """update_config(details_only=True) calls preview_pending_migrations and returns pending_hops."""
    preview_result = {
        "status": "success",
        "current_version": "1.0",
        "pending_hops": [{"from_version": "1.0", "to_version": "2.0", "description": "Add field X"}],
    }
    called = []
    monkeypatch.setattr(mcp_mod, "preview_pending_migrations", lambda: called.append(1) or preview_result)
    monkeypatch.setattr(mcp_mod, "run_pending_migrations", lambda: pytest.fail("run_pending_migrations should not be called"))
    result = update_config(details_only=True)
    assert len(called) == 1
    assert result["status"] == "success"
    assert result["pending_hops"] == [{"from_version": "1.0", "to_version": "2.0", "description": "Add field X"}]


def test_update_config_details_only_up_to_date(monkeypatch):
    """update_config(details_only=True) when up to date returns message containing 'up to date'."""
    preview_result = {
        "status": "success",
        "message": "Config is up to date (version 2.0). No pending migrations.",
        "current_version": "2.0",
        "pending_hops": [],
    }
    monkeypatch.setattr(mcp_mod, "preview_pending_migrations", lambda: preview_result)
    result = update_config(details_only=True)
    assert result["status"] == "success"
    assert "up to date" in result["message"]


def test_update_config_default_still_runs_migration(monkeypatch):
    """update_config() with no args (details_only=False) still calls run_pending_migrations."""
    called = []
    monkeypatch.setattr(mcp_mod, "run_pending_migrations", lambda: called.append(1) or _UP_TO_DATE)
    monkeypatch.setattr(mcp_mod, "preview_pending_migrations", lambda: pytest.fail("preview_pending_migrations should not be called"))
    result = update_config()
    assert len(called) == 1
    assert result["status"] == "success"
    assert result["message"] == "Already up to date"
