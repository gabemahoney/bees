"""bees setup claude — install sting hooks.

Subcommands:
  bees setup claude cli          Install SessionStart + PreCompact hooks

All output is plain text (not JSON).  Exit 0 on success, exit 1 on error.
"""

import json
import sys
from pathlib import Path

_HOOK_ENTRY = {"hooks": [{"type": "command", "command": "bees sting"}]}

_HOOK_EVENTS = ["SessionStart", "PreCompact"]


# ---------------------------------------------------------------------------
# Settings file helpers
# ---------------------------------------------------------------------------


def _resolve_settings_path(args) -> Path:
    """Return the target settings.json path based on CLI flags."""
    if getattr(args, "project", False):
        repo_root = Path.cwd().resolve()
        return repo_root / ".claude" / "settings.local.json"
    return Path.home() / ".claude" / "settings.json"


def _read_settings(path: Path) -> dict:
    """Read and parse a JSON settings file.

    Returns an empty dict if the file does not exist.
    Raises SystemExit(1) on malformed JSON (caller must not write).
    """
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Error: {path} contains invalid JSON: {exc}", file=sys.stdout)
        sys.exit(1)


def _write_settings(path: Path, data: dict) -> None:
    """Write data to a settings file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Hook helpers
# ---------------------------------------------------------------------------


def _add_hooks(settings: dict) -> bool:
    """Add bees sting hooks to settings dict in-place.

    Returns True if any change was made, False if already present (idempotent).
    """
    hooks = settings.setdefault("hooks", {})
    changed = False
    for event in _HOOK_EVENTS:
        event_list = hooks.setdefault(event, [])
        if _HOOK_ENTRY not in event_list:
            event_list.append(_HOOK_ENTRY)
            changed = True
    return changed


def _remove_hooks(settings: dict) -> bool:
    """Remove bees sting hook entries from settings dict in-place.

    Returns True if any change was made.
    """
    hooks = settings.get("hooks", {})
    changed = False
    for event in _HOOK_EVENTS:
        event_list = hooks.get(event, [])
        new_list = [e for e in event_list if e != _HOOK_ENTRY]
        if len(new_list) != len(event_list):
            hooks[event] = new_list
            changed = True
    return changed


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def handle_setup_claude_cli(args):
    """Handle `bees setup claude cli`."""
    path = _resolve_settings_path(args)
    settings = _read_settings(path)  # exits 1 on malformed JSON

    if getattr(args, "remove", False):
        changed = _remove_hooks(settings)
        _write_settings(path, settings)
        if changed:
            print(f"Removed bees sting hooks from {path}")
        else:
            print(f"No bees sting hooks found in {path}")
        sys.exit(0)

    changed = _add_hooks(settings)
    _write_settings(path, settings)
    if changed:
        print(f"Installed bees sting hooks in {path}")
    else:
        print(f"bees sting hooks already present in {path}")
    sys.exit(0)


