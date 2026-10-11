"""
Tests for MCP server lifecycle reporting (src/mcp_server.py).

PURPOSE:
Tests the version that start_server() and _health_check() report: it comes from
the installed bees-md package metadata, with "unknown" as the fallback.

SCOPE - Tests that belong here:
- start_server() and _health_check() report the bees-md package metadata version
- The reported version falls back to "unknown" when bees-md metadata is missing

SCOPE - Tests that DON'T belong here:
- `bees serve` CLI flags and transport dispatch -> test_cli_serve.py
- MCP ticket operations -> test_mcp_server.py
"""

from importlib.metadata import PackageNotFoundError
from unittest.mock import MagicMock, patch

import pytest

from src import mcp_server

FAKE_VERSION = "9.8.7"


@pytest.fixture(autouse=True)
def restore_server_running(monkeypatch):
    """start_server() flips module state; monkeypatch restores it after each test."""
    monkeypatch.setattr(mcp_server, "_server_running", False)


class TestReportedVersion:
    @pytest.mark.parametrize(
        "report",
        [mcp_server.start_server, mcp_server._health_check],
        ids=["start_server", "health_check"],
    )
    def test_reports_bees_md_metadata_version(self, report):
        """Both report the bees-md package metadata version, not a hardcoded one."""
        mock_version = MagicMock(return_value=FAKE_VERSION)

        with patch("src.version.version", mock_version):
            result = report()

        assert result["version"] == FAKE_VERSION
        mock_version.assert_called_once_with("bees-md")

    def test_health_check_reports_unknown_without_metadata(self):
        """_health_check() reports "unknown" when bees-md metadata is unavailable."""
        with patch("src.version.version", side_effect=PackageNotFoundError("bees-md")):
            result = mcp_server._health_check()

        assert result["version"] == "unknown"
