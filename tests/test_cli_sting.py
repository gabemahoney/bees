"""Tests for the `bees sting` command (src/sting.py).

PURPOSE:
  Verifies scope detection, MCP detection across all four config locations,
  the frisbees / bees-mcp boundary cases, and that the CLI reference is
  printed exactly when expected.

SCOPE - Tests that belong here:
  - Step 1: scope detection (no config, no match, match)
  - Step 2: MCP detection in each of the four config locations
  - Step 2: pattern edge cases (frisbees, bees-mcp, different-project)
  - Step 2: malformed JSON skipped silently
  - Step 3: CLI reference output
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


from src.sting import handle_sting, _CLI_REFERENCE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MOCK_REPO_ROOT = Path("/fake/repo")


def _make_args():
    """Return a minimal mock args namespace."""
    return MagicMock()


def _run_sting(capsys) -> tuple[str, int]:
    """Invoke handle_sting and return (stdout, exit_code)."""
    args = _make_args()
    exit_code = 0
    try:
        handle_sting(args)
    except SystemExit as exc:
        exit_code = exc.code if exc.code is not None else 0
    captured = capsys.readouterr()
    return captured.out, exit_code


def _scope_config(repo_root: Path = MOCK_REPO_ROOT) -> dict:
    """Return a minimal global config with one scope matching repo_root."""
    return {
        "schema_version": "2.0",
        "scopes": {
            str(repo_root): {
                "hives": {},
            }
        },
    }


# ---------------------------------------------------------------------------
# TestScopeDetection
# ---------------------------------------------------------------------------


class TestScopeDetection:
    def test_no_bees_config_exits_silently(self, capsys):
        """load_global_config returns empty scopes → no output, exit 0."""
        with (
            patch("src.sting.get_repo_root_from_path", return_value=MOCK_REPO_ROOT),
            patch(
                "src.sting.load_global_config",
                return_value={"schema_version": "2.0", "scopes": {}},
            ),
            patch("src.sting.find_matching_scope", return_value=None),
        ):
            out, code = _run_sting(capsys)

        assert code == 0
        assert out == ""

    def test_no_matching_scope_exits_silently(self, capsys):
        """Config exists but CWD doesn't match any scope → no output, exit 0."""
        config = {"schema_version": "2.0", "scopes": {"/some/other/project": {}}}
        with (
            patch("src.sting.get_repo_root_from_path", return_value=MOCK_REPO_ROOT),
            patch("src.sting.load_global_config", return_value=config),
            patch("src.sting.find_matching_scope", return_value=None),
        ):
            out, code = _run_sting(capsys)

        assert code == 0
        assert out == ""

    def test_matching_scope_continues(self, capsys, tmp_path):
        """Scope matches → continues to MCP detection (no MCP → outputs reference)."""
        # No Claude config files exist in tmp_path, so MCP detection returns False
        with (
            patch("src.sting.get_repo_root_from_path", return_value=tmp_path),
            patch("src.sting.load_global_config", return_value=_scope_config(tmp_path)),
            patch("src.sting.find_matching_scope", return_value=str(tmp_path)),
            patch("src.sting.Path.home", return_value=tmp_path),
        ):
            out, code = _run_sting(capsys)

        assert code == 0
        assert _CLI_REFERENCE in out


# ---------------------------------------------------------------------------
# TestMcpDetection
# ---------------------------------------------------------------------------


class TestMcpDetection:
    def _sting_with_home(self, capsys, home_dir: Path, repo_root: Path | None = None) -> tuple[str, int]:
        """Run sting with scope matched and home pointing at home_dir."""
        rr = repo_root or MOCK_REPO_ROOT
        with (
            patch("src.sting.get_repo_root_from_path", return_value=rr),
            patch("src.sting.load_global_config", return_value=_scope_config(rr)),
            patch("src.sting.find_matching_scope", return_value=str(rr)),
            patch("src.sting.Path.home", return_value=home_dir),
        ):
            return _run_sting(capsys)

    def test_mcp_in_claude_json_global(self, capsys, tmp_path):
        """~/.claude.json top-level mcpServers with 'bees' key → silent exit 0."""
        claude_json = tmp_path / ".claude.json"
        claude_json.write_text(
            json.dumps({"mcpServers": {"bees": {"command": "bees", "args": ["serve", "--stdio"]}}}),
            encoding="utf-8",
        )
        out, code = self._sting_with_home(capsys, tmp_path)
        assert code == 0
        assert out == ""

    def test_mcp_in_claude_json_project(self, capsys, tmp_path):
        """~/.claude.json projects entry matching repo root with bees MCP → silent exit 0."""
        repo_root = tmp_path / "myrepo"
        repo_root.mkdir()
        claude_json = tmp_path / ".claude.json"
        claude_json.write_text(
            json.dumps({
                "projects": {
                    str(repo_root): {
                        "mcpServers": {
                            "bees": {"command": "bees", "args": ["serve", "--stdio"]}
                        }
                    }
                }
            }),
            encoding="utf-8",
        )
        out, code = self._sting_with_home(capsys, tmp_path, repo_root=repo_root)
        assert code == 0
        assert out == ""

    def test_mcp_in_dot_mcp_json(self, capsys, tmp_path):
        """.mcp.json in repo root has 'bees' key → silent exit 0."""
        repo_root = tmp_path / "myrepo"
        repo_root.mkdir()
        dot_mcp = repo_root / ".mcp.json"
        dot_mcp.write_text(
            json.dumps({"mcpServers": {"bees": {"command": "bees", "args": ["serve", "--stdio"]}}}),
            encoding="utf-8",
        )
        # No ~/.claude.json in tmp_path home — only .mcp.json in repo_root
        with (
            patch("src.sting.get_repo_root_from_path", return_value=repo_root),
            patch("src.sting.load_global_config", return_value=_scope_config(repo_root)),
            patch("src.sting.find_matching_scope", return_value=str(repo_root)),
            patch("src.sting.Path.home", return_value=tmp_path),
        ):
            out, code = _run_sting(capsys)

        assert code == 0
        assert out == ""

    def test_mcp_in_settings_json(self, capsys, tmp_path):
        """~/.claude/settings.json has mcpServers with 'bees' key → silent exit 0."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = claude_dir / "settings.json"
        settings.write_text(
            json.dumps({"mcpServers": {"bees": {"command": "bees", "args": ["serve", "--stdio"]}}}),
            encoding="utf-8",
        )
        out, code = self._sting_with_home(capsys, tmp_path)
        assert code == 0
        assert out == ""

    def test_frisbees_does_not_match(self, capsys, tmp_path):
        """Key 'frisbees' does NOT match the bees pattern → outputs reference."""
        claude_json = tmp_path / ".claude.json"
        claude_json.write_text(
            json.dumps({"mcpServers": {"frisbees": {"command": "frisbees"}}}),
            encoding="utf-8",
        )
        out, code = self._sting_with_home(capsys, tmp_path)
        assert code == 0
        assert _CLI_REFERENCE in out

    def test_bees_mcp_matches(self, capsys, tmp_path):
        """Key 'bees-mcp' matches the bees pattern → silent exit 0."""
        claude_json = tmp_path / ".claude.json"
        claude_json.write_text(
            json.dumps({"mcpServers": {"bees-mcp": {"command": "bees", "args": ["serve", "--stdio"]}}}),
            encoding="utf-8",
        )
        out, code = self._sting_with_home(capsys, tmp_path)
        assert code == 0
        assert out == ""

    def test_different_project_mcp_does_not_match(self, capsys, tmp_path):
        """~/.claude.json project scoped to /other/project → NOT a match → outputs reference."""
        claude_json = tmp_path / ".claude.json"
        claude_json.write_text(
            json.dumps({
                "projects": {
                    "/other/project": {
                        "mcpServers": {
                            "bees": {"command": "bees", "args": ["serve", "--stdio"]}
                        }
                    }
                }
            }),
            encoding="utf-8",
        )
        out, code = self._sting_with_home(capsys, tmp_path)
        assert code == 0
        assert _CLI_REFERENCE in out

    def test_malformed_json_skipped(self, capsys, tmp_path):
        """~/.claude.json contains invalid JSON → skipped, continues to output reference."""
        claude_json = tmp_path / ".claude.json"
        claude_json.write_text("{ this is not valid json }", encoding="utf-8")
        out, code = self._sting_with_home(capsys, tmp_path)
        assert code == 0
        assert _CLI_REFERENCE in out


# ---------------------------------------------------------------------------
# TestOutput
# ---------------------------------------------------------------------------


class TestOutput:
    def _run_no_mcp(self, capsys, tmp_path) -> tuple[str, int]:
        """Run sting with scope matched and no MCP config files present."""
        with (
            patch("src.sting.get_repo_root_from_path", return_value=MOCK_REPO_ROOT),
            patch("src.sting.load_global_config", return_value=_scope_config()),
            patch("src.sting.find_matching_scope", return_value=str(MOCK_REPO_ROOT)),
            patch("src.sting.Path.home", return_value=tmp_path),
        ):
            return _run_sting(capsys)

    def test_outputs_cli_reference(self, capsys, tmp_path):
        """Scope matches, no MCP → outputs the full CLI reference template."""
        out, code = self._run_no_mcp(capsys, tmp_path)
        assert code == 0
        assert out.strip() == _CLI_REFERENCE.strip()

    def test_output_contains_key_commands(self, capsys, tmp_path):
        """Key command strings appear in the output."""
        out, code = self._run_no_mcp(capsys, tmp_path)
        assert "show-ticket" in out
        assert "create-ticket" in out
        assert "update-ticket" in out
        assert "delete-ticket" in out
        assert "execute-freeform-query" in out
        assert "execute-named-query" in out
        assert "bees-managed project" in out
