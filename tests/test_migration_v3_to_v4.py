"""Unit tests for src/migrations/upgrade_v3_to_v4.py.

PURPOSE:
Tests the upgrade() function that renames the "default" resolver to "file-path"
across: the resolver registry, allowed_resolvers lists, and ticket .md files.
"""

import pytest
import yaml

from src.migrations.upgrade_v3_to_v4 import upgrade


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_md(resolver_name: str, extra_fields: dict | None = None) -> str:
    """Return a minimal .md ticket with a reference_materials entry."""
    ref_entry = {"value": "/some/path.txt", "resolver": resolver_name}
    frontmatter = {
        "id": "b.abc",
        "type": "bee",
        "title": "Test",
        "reference_materials": [ref_entry],
    }
    if extra_fields:
        frontmatter.update(extra_fields)
    yaml_text = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return f"---\n{yaml_text}---\nBody text.\n"


def _hive_scope(hive_path: str, allowed_resolvers: list | None = None) -> dict:
    hive_data: dict = {"path": hive_path, "display_name": "Test"}
    if allowed_resolvers is not None:
        hive_data["allowed_resolvers"] = allowed_resolvers
    return {"hives": {"myhive": hive_data}}


# ===========================================================================
# Phase 1: Config resolver registry
# ===========================================================================


def test_empty_config_is_noop():
    config: dict = {}
    upgrade(config)
    assert config == {}


def test_default_resolver_renamed_to_file_path():
    config = {"resolvers": {"default": {"path": "/bin/default", "timeout": 10}}}
    upgrade(config)
    assert "default" not in config["resolvers"]
    assert config["resolvers"]["file-path"] == {"path": "/bin/default", "timeout": 10}


def test_no_default_resolver_is_noop():
    config = {"resolvers": {"custom": {"path": "/bin/custom"}}}
    upgrade(config)
    assert config["resolvers"] == {"custom": {"path": "/bin/custom"}}


def test_collision_default_removed_file_path_kept():
    """If both 'default' and 'file-path' exist, 'default' is removed; 'file-path' wins."""
    config = {
        "resolvers": {
            "default": {"path": "/bin/old"},
            "file-path": {"path": "/bin/new"},
        }
    }
    upgrade(config)
    assert "default" not in config["resolvers"]
    assert config["resolvers"]["file-path"] == {"path": "/bin/new"}


# ===========================================================================
# Phase 2: allowed_resolvers migration
# ===========================================================================


def test_allowed_resolvers_default_renamed(tmp_path):
    hive_path = str(tmp_path / "myhive")
    config = {
        "scopes": {
            str(tmp_path): _hive_scope(hive_path, allowed_resolvers=["default", "custom"])
        }
    }
    upgrade(config)
    allowed = config["scopes"][str(tmp_path)]["hives"]["myhive"]["allowed_resolvers"]
    assert "default" not in allowed
    assert "file-path" in allowed
    assert "custom" in allowed


def test_allowed_resolvers_no_default_is_noop(tmp_path):
    hive_path = str(tmp_path / "myhive")
    config = {
        "scopes": {
            str(tmp_path): _hive_scope(hive_path, allowed_resolvers=["custom", "other"])
        }
    }
    upgrade(config)
    allowed = config["scopes"][str(tmp_path)]["hives"]["myhive"]["allowed_resolvers"]
    assert allowed == ["custom", "other"]


def test_allowed_resolvers_collision_no_duplicate(tmp_path):
    """If 'file-path' already in list alongside 'default', no duplicate is added."""
    hive_path = str(tmp_path / "myhive")
    config = {
        "scopes": {
            str(tmp_path): _hive_scope(hive_path, allowed_resolvers=["default", "file-path"])
        }
    }
    upgrade(config)
    allowed = config["scopes"][str(tmp_path)]["hives"]["myhive"]["allowed_resolvers"]
    assert "default" not in allowed
    assert allowed.count("file-path") == 1


# ===========================================================================
# Phase 3: Ticket .md file migration
# ===========================================================================


def test_ticket_resolver_default_renamed(tmp_path):
    hive_dir = tmp_path / "myhive"
    hive_dir.mkdir()
    md_file = hive_dir / "b.abc.md"
    md_file.write_text(_make_md("default"))

    config = {
        "scopes": {str(tmp_path): _hive_scope(str(hive_dir))}
    }
    upgrade(config)

    content = md_file.read_text()
    assert "resolver: file-path" in content
    assert "resolver: default" not in content


def test_ticket_resolver_file_path_unchanged(tmp_path):
    hive_dir = tmp_path / "myhive"
    hive_dir.mkdir()
    md_file = hive_dir / "b.xyz.md"
    md_file.write_text(_make_md("file-path"))

    config = {
        "scopes": {str(tmp_path): _hive_scope(str(hive_dir))}
    }
    upgrade(config)

    content = md_file.read_text()
    assert "resolver: file-path" in content


def test_ticket_custom_resolver_unchanged(tmp_path):
    hive_dir = tmp_path / "myhive"
    hive_dir.mkdir()
    md_file = hive_dir / "b.cst.md"
    md_file.write_text(_make_md("github"))

    config = {
        "scopes": {str(tmp_path): _hive_scope(str(hive_dir))}
    }
    upgrade(config)

    content = md_file.read_text()
    assert "resolver: github" in content


def test_idempotency(tmp_path):
    """Running upgrade twice produces the same result as running it once."""
    hive_dir = tmp_path / "myhive"
    hive_dir.mkdir()
    md_file = hive_dir / "b.abc.md"
    md_file.write_text(_make_md("default"))

    config = {
        "resolvers": {"default": {"path": "/bin/d"}},
        "scopes": {
            str(tmp_path): _hive_scope(str(hive_dir), allowed_resolvers=["default"])
        },
    }

    upgrade(config)
    state_after_first = {
        "config": dict(config),
        "md_content": md_file.read_text(),
    }

    upgrade(config)
    assert config == state_after_first["config"]
    assert md_file.read_text() == state_after_first["md_content"]
