"""Tests for `bees setup claude` (src/setup_claude.py).

Covers:
  - bees setup claude cli  (hooks only)
  - Idempotency, --remove, --project, malformed JSON, preserving existing keys
  - Regression: MCP install functions no longer exist
"""

import importlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.setup_claude import (
    handle_setup_claude_cli,
    _HOOK_ENTRY,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(**kwargs):
    """Build a minimal argparse-style namespace."""
    import argparse

    defaults = {
        "remove": False,
        "project": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _run(handler, args) -> tuple[str, int]:
    """Call a handler and return (stdout, exit_code)."""
    exit_code = 0
    try:
        handler(args)
    except SystemExit as exc:
        exit_code = exc.code if exc.code is not None else 0
    return exit_code


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _hooks_present(data: dict) -> bool:
    """Return True if both hook events contain the bees sting entry."""
    hooks = data.get("hooks", {})
    for event in ("SessionStart", "PreCompact"):
        if _HOOK_ENTRY not in hooks.get(event, []):
            return False
    return True


# ---------------------------------------------------------------------------
# TestSetupClaudeCli
# ---------------------------------------------------------------------------


class TestSetupClaudeCli:
    def test_install_hooks_creates_file(self, tmp_path, capsys):
        """Target file does not exist → created with hooks."""
        settings_path = tmp_path / ".claude" / "settings.json"
        assert not settings_path.exists()

        args = _make_args()
        with patch("src.setup_claude.Path.home", return_value=tmp_path):
            code = _run(handle_setup_claude_cli, args)

        assert code == 0
        assert settings_path.exists()
        data = _read_json(settings_path)
        assert _hooks_present(data)
        out = capsys.readouterr().out
        assert "Installed" in out

    def test_install_hooks_idempotent(self, tmp_path, capsys):
        """Running twice produces no duplicate hook entries."""
        args = _make_args()
        with patch("src.setup_claude.Path.home", return_value=tmp_path):
            _run(handle_setup_claude_cli, args)
            _run(handle_setup_claude_cli, args)

        settings_path = tmp_path / ".claude" / "settings.json"
        data = _read_json(settings_path)
        for event in ("SessionStart", "PreCompact"):
            entries = data["hooks"][event]
            assert entries.count(_HOOK_ENTRY) == 1, f"Duplicate entry in {event}"

        out = capsys.readouterr().out
        assert "already present" in out

    def test_remove_hooks(self, tmp_path, capsys):
        """Install then --remove → hooks gone."""
        args_install = _make_args()
        args_remove = _make_args(remove=True)
        with patch("src.setup_claude.Path.home", return_value=tmp_path):
            _run(handle_setup_claude_cli, args_install)
            code = _run(handle_setup_claude_cli, args_remove)

        assert code == 0
        settings_path = tmp_path / ".claude" / "settings.json"
        data = _read_json(settings_path)
        assert not _hooks_present(data)
        out = capsys.readouterr().out
        assert "Removed" in out

    def test_remove_when_not_present(self, tmp_path, capsys):
        """--remove when hooks were never installed → exit 0, no error."""
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps({"someKey": "value"}), encoding="utf-8")

        args = _make_args(remove=True)
        with patch("src.setup_claude.Path.home", return_value=tmp_path):
            code = _run(handle_setup_claude_cli, args)

        assert code == 0
        out = capsys.readouterr().out
        assert "No bees sting hooks found" in out

    def test_project_flag(self, tmp_path, monkeypatch, capsys):
        """--project writes to .claude/settings.local.json in CWD, creates dir."""
        monkeypatch.chdir(tmp_path)
        local_path = tmp_path / ".claude" / "settings.local.json"
        assert not local_path.exists()

        args = _make_args(project=True)
        with patch("src.setup_claude.Path.home", return_value=tmp_path / "fakehome"):
            code = _run(handle_setup_claude_cli, args)

        assert code == 0
        assert local_path.exists()
        data = _read_json(local_path)
        assert _hooks_present(data)

        # Global settings should NOT have been written
        global_path = tmp_path / "fakehome" / ".claude" / "settings.json"
        assert not global_path.exists()


# ---------------------------------------------------------------------------
# TestMalformedJson
# ---------------------------------------------------------------------------


class TestMalformedJson:
    def test_malformed_settings_exits_1(self, tmp_path, capsys):
        """Invalid JSON in target file → error message, exit 1, file unchanged."""
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        original = "{ this is not valid json }"
        settings_path.write_text(original, encoding="utf-8")

        args = _make_args()
        with patch("src.setup_claude.Path.home", return_value=tmp_path):
            code = _run(handle_setup_claude_cli, args)

        assert code == 1
        # File must not have been corrupted
        assert settings_path.read_text(encoding="utf-8") == original
        out = capsys.readouterr().out
        assert "invalid JSON" in out or "Error" in out

    def test_preserves_existing_settings(self, tmp_path, capsys):
        """Existing non-hooks settings keys are not clobbered."""
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {"theme": "dark", "editor": "vim", "someList": [1, 2, 3]}
        settings_path.write_text(json.dumps(existing), encoding="utf-8")

        args = _make_args()
        with patch("src.setup_claude.Path.home", return_value=tmp_path):
            _run(handle_setup_claude_cli, args)

        data = _read_json(settings_path)
        assert data["theme"] == "dark"
        assert data["editor"] == "vim"
        assert data["someList"] == [1, 2, 3]
        assert _hooks_present(data)


# ---------------------------------------------------------------------------
# TestMcpFunctionalityRemoved
# ---------------------------------------------------------------------------

_REMOVED_MCP_NAMES = [
    "handle_setup_claude_mcp",
    "_add_mcp_stdio",
    "_add_mcp_http",
    "_remove_mcp",
    "_key_matches_bees",
]


class TestMcpFunctionalityRemoved:
    """Regression: MCP install functions must not exist in src.setup_claude."""

    @pytest.mark.parametrize("name", _REMOVED_MCP_NAMES, ids=_REMOVED_MCP_NAMES)
    def test_mcp_function_not_in_module(self, name):
        """src.setup_claude must not export removed MCP helpers."""
        import src.setup_claude as mod

        # Force a fresh look at the module's actual attributes
        importlib.reload(mod)
        assert not hasattr(mod, name), f"{name} should have been removed from src.setup_claude"
