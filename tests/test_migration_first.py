"""Tests for the v2 → v3 migration: egg_resolver config and egg ticket fields → reference_materials,
and "default" → "file-path" resolver rename (registry, allowed_resolvers, ticket files)."""

from __future__ import annotations

import copy

import pytest
import yaml

from src.migrations.upgrade_v2_to_v3 import upgrade


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_script(tmp_path, stem: str, convention: str | None = None) -> str:
    """Create a minimal resolver script and return its path string."""
    if convention:
        content = f'"""A resolver.\n\n## RESOLVER CONVENTION\n{convention}\n"""\n'
    else:
        content = '"""A resolver with no convention."""\n'
    p = tmp_path / f"{stem}.py"
    p.write_text(content)
    return str(p)


def _md(egg_value) -> str:
    """Return minimal bee .md with the given egg value in YAML frontmatter."""
    egg_line = "egg: null" if egg_value is None else f"egg: {egg_value}"
    return f"---\nid: b.xx\ntype: bee\ntitle: T\nstatus: open\n{egg_line}\n---\nBody.\n"


def _write(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _frontmatter(md_path) -> dict:
    """Parse the YAML frontmatter from a .md file."""
    parts = md_path.read_text().split("---")
    return yaml.safe_load(parts[1])


def _hive_config(hive_dir, resolver: str | None = None) -> dict:
    """Minimal config dict with one hive, optionally with egg_resolver."""
    hive_data: dict = {"path": str(hive_dir)}
    if resolver:
        hive_data["egg_resolver"] = resolver
    return {"scopes": {"/repo": {"hives": {"my_hive": hive_data}}}}


# ---------------------------------------------------------------------------
# Config — no egg_resolver is a no-op
# ---------------------------------------------------------------------------


def test_no_egg_resolver_is_noop():
    config = {"scopes": {"/repo": {"hives": {"bugs": {"path": "/bugs"}}}}}
    before = copy.deepcopy(config)
    upgrade(config)
    assert config == before


# ---------------------------------------------------------------------------
# Config — egg_resolver extracted at each level
# ---------------------------------------------------------------------------


def test_global_egg_resolver_extracted(tmp_path):
    script = _make_script(tmp_path, "my_res")
    config = {"egg_resolver": script, "egg_resolver_timeout": 30, "scopes": {}}
    upgrade(config)
    assert "egg_resolver" not in config
    assert "egg_resolver_timeout" not in config
    assert config["resolvers"]["my_res"] == {"path": script, "timeout": 30}


def test_scope_egg_resolver_extracted(tmp_path):
    script = _make_script(tmp_path, "scope_res")
    config = {"scopes": {"/repo": {"egg_resolver": script, "hives": {}}}}
    upgrade(config)
    assert "egg_resolver" not in config["scopes"]["/repo"]
    assert "scope_res" in config["resolvers"]


def test_hive_egg_resolver_extracted(tmp_path):
    hive_dir = tmp_path / "h"
    hive_dir.mkdir()
    script = _make_script(tmp_path, "hive_res")
    config = {
        "scopes": {
            "/repo": {
                "hives": {
                    "h": {"path": str(hive_dir), "egg_resolver": script, "egg_resolver_timeout": 10}
                }
            }
        }
    }
    upgrade(config)
    hive = config["scopes"]["/repo"]["hives"]["h"]
    assert "egg_resolver" not in hive
    assert config["resolvers"]["hive_res"] == {"path": script, "timeout": 10}


def test_multiple_unique_resolvers_captured(tmp_path):
    script_a = _make_script(tmp_path, "res_a")
    script_b = _make_script(tmp_path, "res_b")
    hive_a = tmp_path / "ha"
    hive_b = tmp_path / "hb"
    hive_a.mkdir()
    hive_b.mkdir()
    config = {
        "scopes": {
            "/repo": {
                "hives": {
                    "ha": {"path": str(hive_a), "egg_resolver": script_a},
                    "hb": {"path": str(hive_b), "egg_resolver": script_b},
                }
            }
        }
    }
    upgrade(config)
    assert "res_a" in config["resolvers"]
    assert "res_b" in config["resolvers"]


def test_collision_raises_before_mutations(tmp_path):
    """Two different paths with same stem → ValueError; config unchanged."""
    s1 = tmp_path / "dir1" / "clash.py"
    s2 = tmp_path / "dir2" / "clash.py"
    s1.parent.mkdir()
    s2.parent.mkdir()
    s1.write_text('"""A."""')
    s2.write_text('"""B."""')
    hive_a = tmp_path / "ha"
    hive_b = tmp_path / "hb"
    hive_a.mkdir()
    hive_b.mkdir()
    config = {
        "scopes": {
            "/repo": {
                "hives": {
                    "ha": {"path": str(hive_a), "egg_resolver": str(s1)},
                    "hb": {"path": str(hive_b), "egg_resolver": str(s2)},
                }
            }
        }
    }
    before = copy.deepcopy(config)
    with pytest.raises(ValueError, match="collision"):
        upgrade(config)
    assert config == before


def test_old_keys_removed_from_all_levels(tmp_path):
    script = _make_script(tmp_path, "r")
    hive_dir = tmp_path / "h"
    hive_dir.mkdir()
    config = {
        "egg_resolver": script,
        "egg_resolver_timeout": 5,
        "scopes": {
            "/repo": {
                "egg_resolver": script,
                "egg_resolver_timeout": 5,
                "hives": {
                    "h": {"path": str(hive_dir), "egg_resolver": script, "egg_resolver_timeout": 5},
                },
            }
        },
    }
    upgrade(config)
    for level in [
        config,
        config["scopes"]["/repo"],
        config["scopes"]["/repo"]["hives"]["h"],
    ]:
        assert "egg_resolver" not in level
        assert "egg_resolver_timeout" not in level


def test_convention_extracted_from_script(tmp_path):
    script = _make_script(tmp_path, "smart", convention="Use format X: Y")
    config = {"egg_resolver": script, "scopes": {}}
    upgrade(config)
    assert config["resolvers"]["smart"]["convention"] == "Use format X: Y"


def test_existing_resolver_not_overwritten(tmp_path):
    """If resolver name already in resolvers, skip — don't overwrite."""
    script = _make_script(tmp_path, "res", convention="New convention")
    config = {
        "egg_resolver": script,
        "resolvers": {"res": {"path": "/old/path.py", "convention": "Old"}},
        "scopes": {},
    }
    upgrade(config)
    assert config["resolvers"]["res"]["path"] == "/old/path.py"
    assert config["resolvers"]["res"]["convention"] == "Old"


def test_idempotent_already_migrated_config(tmp_path):
    """Config with no egg_resolver keys is unchanged by upgrade."""
    script = _make_script(tmp_path, "res")
    config = {"resolvers": {"res": {"path": script}}, "scopes": {}}
    before = copy.deepcopy(config)
    upgrade(config)
    assert config == before


# ---------------------------------------------------------------------------
# Ticket migration
# ---------------------------------------------------------------------------


def test_egg_converted_to_reference_materials(tmp_path):
    hive_dir = tmp_path / "h"
    hive_dir.mkdir()
    md = hive_dir / "b.xx" / "b.xx.md"
    _write(md, _md("my_val"))
    upgrade(_hive_config(hive_dir))
    fm = _frontmatter(md)
    assert "egg" not in fm
    assert fm["reference_materials"] == [{"value": "my_val"}]


def test_egg_with_hive_resolver_adds_resolver_key(tmp_path):
    hive_dir = tmp_path / "h"
    hive_dir.mkdir()
    script = _make_script(tmp_path, "hive_res")
    md = hive_dir / "b.xx" / "b.xx.md"
    _write(md, _md("val"))
    upgrade(_hive_config(hive_dir, resolver=script))
    fm = _frontmatter(md)
    assert fm["reference_materials"] == [{"value": "val", "resolver": "hive_res"}]


def test_egg_without_hive_resolver_no_resolver_key(tmp_path):
    hive_dir = tmp_path / "h"
    hive_dir.mkdir()
    md = hive_dir / "b.xx" / "b.xx.md"
    _write(md, _md("val"))
    upgrade(_hive_config(hive_dir))
    fm = _frontmatter(md)
    assert "resolver" not in fm["reference_materials"][0]


def test_null_egg_becomes_null_reference_materials(tmp_path):
    hive_dir = tmp_path / "h"
    hive_dir.mkdir()
    md = hive_dir / "b.xx" / "b.xx.md"
    _write(md, _md(None))
    upgrade(_hive_config(hive_dir))
    fm = _frontmatter(md)
    assert "egg" not in fm
    assert fm["reference_materials"] is None


def test_already_migrated_ticket_skipped(tmp_path):
    """Ticket with reference_materials but no egg key is left untouched."""
    hive_dir = tmp_path / "h"
    hive_dir.mkdir()
    md = hive_dir / "b.xx" / "b.xx.md"
    content = (
        "---\nid: b.xx\ntype: bee\ntitle: T\nstatus: open\n"
        "reference_materials:\n- value: old\n---\nBody.\n"
    )
    _write(md, content)
    upgrade(_hive_config(hive_dir))
    assert md.read_text() == content


def test_egg_and_reference_materials_both_present(tmp_path):
    """When both egg and reference_materials keys exist, egg is removed and reference_materials is preserved unchanged."""
    hive_dir = tmp_path / "h"
    hive_dir.mkdir()
    md = hive_dir / "b.xx" / "b.xx.md"
    content = (
        "---\nid: b.xx\ntype: bee\ntitle: T\nstatus: open\n"
        "egg: some_val\nreference_materials:\n- value: existing\n---\nBody.\n"
    )
    _write(md, content)
    upgrade(_hive_config(hive_dir))
    fm = _frontmatter(md)
    assert "egg" not in fm
    assert fm["reference_materials"] == [{"value": "existing"}]


def test_empty_hive_no_error(tmp_path):
    hive_dir = tmp_path / "h"
    hive_dir.mkdir()
    upgrade(_hive_config(hive_dir))  # should not raise


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------


def test_full_upgrade(tmp_path):
    """Old config + old tickets → resolvers populated + reference_materials set."""
    hive_dir = tmp_path / "h"
    hive_dir.mkdir()
    script = _make_script(tmp_path, "full_res", convention="My convention")
    md = hive_dir / "b.aa" / "b.aa.md"
    _write(md, _md("egg_val"))
    config = {
        "scopes": {
            "/repo": {
                "hives": {
                    "my_hive": {
                        "path": str(hive_dir),
                        "egg_resolver": script,
                        "egg_resolver_timeout": 20,
                    }
                }
            }
        }
    }

    upgrade(config)

    hive = config["scopes"]["/repo"]["hives"]["my_hive"]
    assert "egg_resolver" not in hive
    r = config["resolvers"]["full_res"]
    assert r["path"] == script
    assert r["timeout"] == 20
    assert r["convention"] == "My convention"

    fm = _frontmatter(md)
    assert "egg" not in fm
    assert fm["reference_materials"] == [{"value": "egg_val", "resolver": "full_res"}]


def test_upgrade_idempotent(tmp_path):
    """Running upgrade twice leaves config and ticket files identical after first run."""
    hive_dir = tmp_path / "h"
    hive_dir.mkdir()
    script = _make_script(tmp_path, "idem_res")
    md = hive_dir / "b.bb" / "b.bb.md"
    _write(md, _md("val"))
    config = {
        "scopes": {
            "/repo": {
                "hives": {"my_hive": {"path": str(hive_dir), "egg_resolver": script}}
            }
        }
    }

    upgrade(config)
    config_snap = copy.deepcopy(config)
    ticket_snap = md.read_text()

    upgrade(config)
    assert config == config_snap
    assert md.read_text() == ticket_snap


# ---------------------------------------------------------------------------
# "default" → "file-path" resolver rename — registry
# ---------------------------------------------------------------------------


def test_default_resolver_registry_renamed_to_file_path():
    """upgrade() renames 'default' → 'file-path' in the resolver registry."""
    config = {"resolvers": {"default": {"path": "/bin/default", "timeout": 10}}}
    upgrade(config)
    assert "default" not in config["resolvers"]
    assert config["resolvers"]["file-path"] == {"path": "/bin/default", "timeout": 10}


def test_no_default_resolver_registry_is_noop():
    config = {"resolvers": {"custom": {"path": "/bin/custom"}}}
    upgrade(config)
    assert config["resolvers"] == {"custom": {"path": "/bin/custom"}}


def test_default_resolver_collision_file_path_wins():
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


# ---------------------------------------------------------------------------
# "default" → "file-path" resolver rename — allowed_resolvers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "initial,expected",
    [
        pytest.param(["default", "custom"], ["file-path", "custom"], id="default_renamed"),
        pytest.param(["custom", "other"], ["custom", "other"], id="no_default_noop"),
        pytest.param(["default", "file-path"], ["file-path"], id="collision_no_duplicate"),
    ],
)
def test_allowed_resolvers_default_renamed(tmp_path, initial, expected):
    hive_path = str(tmp_path / "myhive")
    config = {
        "scopes": {
            str(tmp_path): {
                "hives": {"myhive": {"path": hive_path, "allowed_resolvers": initial}}
            }
        }
    }
    upgrade(config)
    allowed = config["scopes"][str(tmp_path)]["hives"]["myhive"]["allowed_resolvers"]
    assert allowed == expected


# ---------------------------------------------------------------------------
# "default" → "file-path" resolver rename — ticket reference_materials
# ---------------------------------------------------------------------------


def _make_ticket_md(resolver_name: str) -> str:
    """Return a .md ticket with a reference_materials entry using the given resolver."""
    frontmatter = {
        "id": "b.abc",
        "type": "bee",
        "title": "Test",
        "reference_materials": [{"value": "/some/path.txt", "resolver": resolver_name}],
    }
    yaml_text = yaml.dump(
        frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False
    )
    return f"---\n{yaml_text}---\nBody text.\n"


def test_ticket_resolver_default_renamed_to_file_path(tmp_path):
    """upgrade() renames resolver: default → resolver: file-path in ticket .md files."""
    hive_dir = tmp_path / "myhive"
    hive_dir.mkdir()
    md_file = hive_dir / "b.abc.md"
    md_file.write_text(_make_ticket_md("default"))

    config = {"scopes": {str(tmp_path): {"hives": {"myhive": {"path": str(hive_dir)}}}}}
    upgrade(config)

    content = md_file.read_text()
    assert "resolver: file-path" in content
    assert "resolver: default" not in content


def test_ticket_non_default_resolver_unchanged(tmp_path):
    """upgrade() does not touch tickets whose resolver is already 'file-path' or another name."""
    hive_dir = tmp_path / "myhive"
    hive_dir.mkdir()

    fp_file = hive_dir / "b.fp.md"
    fp_file.write_text(_make_ticket_md("file-path"))
    gh_file = hive_dir / "b.gh.md"
    gh_file.write_text(_make_ticket_md("github"))

    config = {"scopes": {str(tmp_path): {"hives": {"myhive": {"path": str(hive_dir)}}}}}
    upgrade(config)

    assert "resolver: file-path" in fp_file.read_text()
    assert "resolver: github" in gh_file.read_text()


def test_default_rename_idempotent(tmp_path):
    """Running upgrade twice on a 'default' resolver config is idempotent."""
    hive_dir = tmp_path / "myhive"
    hive_dir.mkdir()
    md_file = hive_dir / "b.abc.md"
    md_file.write_text(_make_ticket_md("default"))

    config = {
        "resolvers": {"default": {"path": "/bin/d"}},
        "scopes": {
            str(tmp_path): {
                "hives": {"myhive": {"path": str(hive_dir), "allowed_resolvers": ["default"]}}
            }
        },
    }

    upgrade(config)
    config_snap = copy.deepcopy(config)
    md_snap = md_file.read_text()

    upgrade(config)
    assert config == config_snap
    assert md_file.read_text() == md_snap
