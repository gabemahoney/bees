"""Tests for mcp_resolver_ops: _extract_convention, _set_resolver, and _get_resolvers."""

import json

import pytest

from src.mcp_reference_ops import DEFAULT_RESOLVER_CONVENTION
from src.mcp_resolver_ops import _extract_convention, _get_resolvers, _set_resolver


# ---------------------------------------------------------------------------
# Script templates
# ---------------------------------------------------------------------------

_SCRIPT_WITH_CONVENTION = '''\
"""Module docstring.

## RESOLVER CONVENTION
Resolve by matching ticket prefix to directory name.
"""
'''

_SCRIPT_WITH_CONVENTION_SINGLE_QUOTES = """\
'''
## RESOLVER CONVENTION
Single-quote convention text.
'''
"""

_SCRIPT_NO_CONVENTION = '''\
"""Plain docstring without a convention section."""
'''

_SCRIPT_EMPTY_DOCSTRING = '''\
"""
"""
'''

_SCRIPT_NO_DOCSTRING = "x = 1\n"


# ===========================================================================
# _extract_convention
# ===========================================================================


@pytest.mark.parametrize(
    "content,expected",
    [
        pytest.param(
            _SCRIPT_WITH_CONVENTION,
            "Resolve by matching ticket prefix to directory name.",
            id="convention_present",
        ),
        pytest.param(
            _SCRIPT_WITH_CONVENTION_SINGLE_QUOTES,
            "Single-quote convention text.",
            id="single_quoted_docstring",
        ),
        pytest.param(_SCRIPT_NO_CONVENTION, None, id="no_convention_section"),
        pytest.param(_SCRIPT_EMPTY_DOCSTRING, None, id="empty_docstring"),
        pytest.param(_SCRIPT_NO_DOCSTRING, None, id="no_docstring"),
    ],
)
def test_extract_convention(tmp_path, content, expected):
    script = tmp_path / "resolver.py"
    script.write_text(content)
    assert _extract_convention(str(script)) == expected


def test_extract_convention_missing_file(tmp_path):
    assert _extract_convention(str(tmp_path / "nonexistent.py")) is None


# ===========================================================================
# _set_resolver – reserved name "default"
# ===========================================================================


@pytest.mark.parametrize(
    "name,kwargs",
    [
        pytest.param("default", {"path": "/some/path.py"}, id="default_register"),
        pytest.param("default", {"unset": True}, id="default_unset"),
        pytest.param("file-path", {"path": "/some/path.py"}, id="file_path_register"),
        pytest.param("github", {"path": "/some/path.py"}, id="github_register"),
        pytest.param("bees", {"path": "/some/path.py"}, id="bees_register"),
    ],
)
def test_set_resolver_reserved_name(name, kwargs):
    result = _set_resolver(name, **kwargs)
    assert result["status"] == "error"
    assert result["error_type"] == "reserved_name"


# ===========================================================================
# _set_resolver – register mode
# ===========================================================================


def test_set_resolver_register_with_convention(tmp_path, mock_global_bees_dir):
    """New resolver with a convention section: entry persisted, convention in result."""
    script = tmp_path / "my_resolver.py"
    script.write_text(_SCRIPT_WITH_CONVENTION)

    result = _set_resolver("my_resolver", path=str(script))

    assert result["status"] == "success"
    assert result["action"] == "set"
    assert result["name"] == "my_resolver"
    assert result["convention"] == "Resolve by matching ticket prefix to directory name."

    config = json.loads((mock_global_bees_dir / "config.json").read_text())
    entry = config["resolvers"]["my_resolver"]
    assert entry["path"] == str(script)
    assert entry["convention"] == "Resolve by matching ticket prefix to directory name."


def test_set_resolver_register_no_convention(tmp_path, mock_global_bees_dir):
    """Resolver script without convention section: convention omitted from result and storage."""
    script = tmp_path / "plain.py"
    script.write_text(_SCRIPT_NO_CONVENTION)

    result = _set_resolver("plain", path=str(script))

    assert result["status"] == "success"
    assert "convention" not in result

    config = json.loads((mock_global_bees_dir / "config.json").read_text())
    assert "convention" not in config["resolvers"]["plain"]


def test_set_resolver_register_with_timeout(tmp_path, mock_global_bees_dir):
    """Timeout is included in both result and stored entry."""
    script = tmp_path / "resolver.py"
    script.write_text(_SCRIPT_NO_CONVENTION)

    result = _set_resolver("timed", path=str(script), timeout=30)

    assert result["status"] == "success"
    assert result["timeout"] == 30

    config = json.loads((mock_global_bees_dir / "config.json").read_text())
    assert config["resolvers"]["timed"]["timeout"] == 30


@pytest.mark.parametrize(
    "path_value",
    [
        pytest.param(None, id="none"),
        pytest.param("", id="empty_string"),
    ],
)
def test_set_resolver_missing_path(path_value):
    result = _set_resolver("myresolver", path=path_value)
    assert result["status"] == "error"
    assert result["error_type"] == "missing_path"


def test_set_resolver_file_not_found(tmp_path):
    result = _set_resolver("myresolver", path=str(tmp_path / "missing.py"))
    assert result["status"] == "error"
    assert result["error_type"] == "file_not_found"


# ===========================================================================
# _set_resolver – update mode
# ===========================================================================


def test_set_resolver_update_overwrites(tmp_path, mock_global_bees_dir):
    """Second call with same name replaces path, timeout, and convention."""
    script_v1 = tmp_path / "v1.py"
    script_v1.write_text(_SCRIPT_NO_CONVENTION)
    _set_resolver("updatable", path=str(script_v1), timeout=10)

    script_v2 = tmp_path / "v2.py"
    script_v2.write_text(_SCRIPT_WITH_CONVENTION)
    result = _set_resolver("updatable", path=str(script_v2), timeout=60)

    assert result["status"] == "success"
    assert result["path"] == str(script_v2)
    assert result["timeout"] == 60
    assert result["convention"] == "Resolve by matching ticket prefix to directory name."

    config = json.loads((mock_global_bees_dir / "config.json").read_text())
    entry = config["resolvers"]["updatable"]
    assert entry["path"] == str(script_v2)
    assert entry["timeout"] == 60


# ===========================================================================
# _set_resolver – unset mode
# ===========================================================================


def test_set_resolver_unset_success(tmp_path, mock_global_bees_dir):
    """Unset removes the named entry from the registry."""
    script = tmp_path / "to_remove.py"
    script.write_text(_SCRIPT_NO_CONVENTION)
    _set_resolver("to_remove", path=str(script))

    result = _set_resolver("to_remove", unset=True)

    assert result["status"] == "success"
    assert result["action"] == "unset"
    assert result["name"] == "to_remove"

    config = json.loads((mock_global_bees_dir / "config.json").read_text())
    assert "to_remove" not in config.get("resolvers", {})


def test_set_resolver_unset_not_found():
    result = _set_resolver("nonexistent", unset=True)
    assert result["status"] == "error"
    assert result["error_type"] == "not_found"


def test_set_resolver_unset_in_use(tmp_path, mock_global_bees_dir):
    """Unset blocked when a hive's allowed_resolvers references the resolver."""
    script = tmp_path / "in_use.py"
    script.write_text(_SCRIPT_NO_CONVENTION)
    _set_resolver("in_use", path=str(script))

    # Inject a scope where a hive references this resolver
    config_path = mock_global_bees_dir / "config.json"
    config = json.loads(config_path.read_text())
    config["scopes"] = {
        str(tmp_path): {
            "hives": {
                "features": {
                    "path": str(tmp_path / "features"),
                    "display_name": "Features",
                    "allowed_resolvers": ["in_use"],
                }
            }
        }
    }
    config_path.write_text(json.dumps(config))

    result = _set_resolver("in_use", unset=True)
    assert result["status"] == "error"
    assert result["error_type"] == "resolver_in_use"


# ===========================================================================
# _get_resolvers
# ===========================================================================


def test_get_resolvers_empty_registry(mock_global_bees_dir):
    """Empty registry: exactly 3 built-ins (file-path, github, bees) are returned."""
    result = _get_resolvers()

    assert result["status"] == "success"
    resolvers = result["resolvers"]
    assert len(resolvers) == 3

    names = [r["name"] for r in resolvers]
    assert names == ["file-path", "github", "bees"]

    for entry in resolvers:
        assert entry["built_in"] is True
        assert entry["path"] is None
        assert entry["timeout"] is None
        assert isinstance(entry["convention"], str) and entry["convention"]


def test_get_resolvers_file_path_convention_matches_constant(mock_global_bees_dir):
    """file-path built-in convention equals DEFAULT_RESOLVER_CONVENTION."""
    result = _get_resolvers()
    file_path_entry = result["resolvers"][0]
    assert file_path_entry["name"] == "file-path"
    assert file_path_entry["convention"] == DEFAULT_RESOLVER_CONVENTION


def test_get_resolvers_single_registered(tmp_path, mock_global_bees_dir):
    """Single registered resolver: 3 built-ins prepended, registered entry has built_in=False."""
    script = tmp_path / "custom.py"
    script.write_text(_SCRIPT_WITH_CONVENTION)
    _set_resolver("custom", path=str(script))

    result = _get_resolvers()

    assert result["status"] == "success"
    resolvers = result["resolvers"]
    assert len(resolvers) == 4  # 3 built-ins + 1 registered

    names = [r["name"] for r in resolvers]
    assert names[0] == "file-path"
    assert "custom" in names

    custom = next(r for r in resolvers if r["name"] == "custom")
    assert custom["built_in"] is False
    assert custom["path"] == str(script)
    assert custom["convention"] == "Resolve by matching ticket prefix to directory name."


def test_get_resolvers_multiple_registered(tmp_path, mock_global_bees_dir):
    """Multiple registered resolvers: all present with correct fields."""
    scripts = {}
    for name in ("alpha", "beta", "gamma"):
        s = tmp_path / f"{name}.py"
        s.write_text(_SCRIPT_NO_CONVENTION)
        scripts[name] = s
        _set_resolver(name, path=str(s), timeout=10)

    result = _get_resolvers()

    assert result["status"] == "success"
    resolvers = result["resolvers"]
    assert len(resolvers) == 6  # 3 built-ins + 3 registered

    names = [r["name"] for r in resolvers]
    assert names[0] == "file-path"
    for name in ("alpha", "beta", "gamma"):
        assert name in names
        entry = next(r for r in resolvers if r["name"] == name)
        assert entry["built_in"] is False
        assert entry["path"] == str(scripts[name])
        assert entry["timeout"] == 10
