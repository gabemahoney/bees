"""
Tests for the `bees serve` dependency self-check (src/serve_deps.py, b.zhu / b.bop).

PURPOSE:
`check_serve_dependencies()` finds a missing, half-installed (empty namespace package) or
out-of-range fastmcp or mcp before `bees serve` imports the server, and returns the message that
tells the user how to reinstall cleanly.

SCOPE - Tests that belong here:
- each failure kind: ImportError, namespace package, missing name, out-of-range version
- missing package metadata is tolerated; a healthy install returns None
- the message: installed versions, supported ranges, both clean-reinstall commands
- version parsing

SCOPE - Tests that DON'T belong here:
- how `bees serve` reports the message (stderr, mcp.log, exit code) -> test_cli_serve.py
- the `serve` extra's pins in pyproject.toml -> test_package_entry_point.py

The tests install fake fastmcp and mcp packages in sys.modules and fake the installed versions, so
they do not depend on what the test environment holds.
"""

import importlib.metadata
import shlex
import sys
import types

import pytest

from src import serve_deps
from src.serve_deps import PIPX_FIX, check_serve_dependencies, parse_version, pip_fix_command

HEALTHY_VERSIONS = {"fastmcp": "3.4.8", "fastmcp-slim": "3.4.8", "mcp": "1.26.0"}


def _module(name, **attrs):
    module = types.ModuleType(name)
    module.__file__ = f"/fake/{name.replace('.', '/')}.py"
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


def _healthy_modules():
    """Fake modules holding every name src/ imports from fastmcp and mcp."""
    return {
        "fastmcp": _module("fastmcp", Context=object, FastMCP=object),
        "fastmcp.exceptions": _module("fastmcp.exceptions", NotFoundError=Exception),
        "fastmcp.tools": _module("fastmcp.tools", FunctionTool=object),
        "mcp": _module("mcp"),
        "mcp.shared": _module("mcp.shared"),
        "mcp.shared.exceptions": _module("mcp.shared.exceptions", McpError=Exception),
    }


@pytest.fixture
def fake_install(monkeypatch):
    """Healthy fake fastmcp and mcp. Returns a function installing overrides: modules (None removes, a module replaces) and versions."""

    versions = dict(HEALTHY_VERSIONS)

    def fake_version(distribution):
        if versions.get(distribution) is None:
            raise importlib.metadata.PackageNotFoundError(distribution)
        return versions[distribution]

    monkeypatch.setattr(importlib.metadata, "version", fake_version)
    for name, module in _healthy_modules().items():
        monkeypatch.setitem(sys.modules, name, module)

    def customize(*, modules=None, versions_override=None):
        for name, module in (modules or {}).items():
            # None in sys.modules makes the import raise ImportError
            monkeypatch.setitem(sys.modules, name, module)
        versions.update(versions_override or {})

    return customize


class TestHealthyInstall:
    def test_healthy_install_returns_none(self, fake_install):
        assert check_serve_dependencies() is None

    def test_real_environment_is_healthy(self):
        """The fastmcp and mcp this suite runs against pass the check (the dev extras are installed)."""
        assert check_serve_dependencies() is None

    @pytest.mark.parametrize(
        "versions",
        [
            pytest.param({"fastmcp": None}, id="no_fastmcp_metadata"),
            pytest.param({"mcp": None}, id="no_mcp_metadata"),
            pytest.param({"fastmcp": None, "fastmcp-slim": None, "mcp": None}, id="no_metadata_at_all"),
        ],
    )
    def test_missing_metadata_is_tolerated(self, fake_install, versions):
        """Packages that import fine but report no version (vendored, source checkout) pass: the import probe decides."""
        fake_install(versions_override=versions)

        assert check_serve_dependencies() is None

    @pytest.mark.parametrize(
        "versions",
        [
            pytest.param({"fastmcp": "3.0.2"}, id="fastmcp_lower_bound"),
            pytest.param({"fastmcp": "3.99.0"}, id="fastmcp_late_3x"),
            pytest.param({"fastmcp": "3.5.0rc1"}, id="fastmcp_prerelease_suffix"),
            pytest.param({"mcp": "1.24.0"}, id="mcp_lower_bound"),
            pytest.param({"mcp": "1.99.9"}, id="mcp_late_1x"),
        ],
    )
    def test_boundary_versions_inside_the_range_pass(self, fake_install, versions):
        fake_install(versions_override=versions)

        assert check_serve_dependencies() is None


class TestFailureKinds:
    @pytest.mark.parametrize(
        "module_name,expected_fragment",
        [
            pytest.param("fastmcp", "cannot start: fastmcp cannot be imported", id="missing_fastmcp"),
            pytest.param("mcp", "cannot start: mcp cannot be imported", id="missing_mcp"),
            pytest.param("mcp.shared.exceptions", "cannot import mcp.shared.exceptions", id="missing_submodule"),
        ],
    )
    def test_missing_module_is_an_import_error(self, fake_install, module_name, expected_fragment):
        fake_install(modules={module_name: None})

        message = check_serve_dependencies()

        assert message is not None
        assert expected_fragment in message

    def test_import_that_raises_another_exception_is_reported(self, fake_install, monkeypatch):
        """A package that blows up on import (any exception, not only ImportError) is a failed check, never a traceback."""
        real_import_module = serve_deps.importlib.import_module

        def exploding_import(name, *args, **kwargs):
            if name == "mcp":
                raise TypeError("broken at import")
            return real_import_module(name, *args, **kwargs)

        monkeypatch.setattr(serve_deps.importlib, "import_module", exploding_import)

        message = check_serve_dependencies()

        assert message is not None
        assert "importing mcp failed" in message
        assert "TypeError" in message

    @pytest.mark.parametrize("package", [pytest.param("fastmcp", id="fastmcp"), pytest.param("mcp", id="mcp")])
    def test_namespace_package_is_incomplete(self, fake_install, package):
        """A package folder with no package files imports as a namespace package (`__file__` is None), which is the b.zhu half-install."""
        namespace = types.ModuleType(package)
        namespace.__file__ = None
        namespace.__path__ = []
        fake_install(modules={package: namespace})

        message = check_serve_dependencies()

        assert message is not None
        assert f"cannot start: {package} is installed incompletely" in message

    @pytest.mark.parametrize(
        "module_name,missing_name",
        [
            pytest.param("fastmcp", "Context", id="fastmcp_Context"),
            pytest.param("fastmcp", "FastMCP", id="fastmcp_FastMCP"),
            pytest.param("fastmcp.exceptions", "NotFoundError", id="fastmcp_NotFoundError"),
            pytest.param("fastmcp.tools", "FunctionTool", id="fastmcp_FunctionTool"),
            pytest.param("mcp.shared.exceptions", "McpError", id="mcp_McpError"),
        ],
    )
    def test_missing_required_name_is_reported(self, fake_install, module_name, missing_name):
        """Every name src/ imports from fastmcp or mcp is checked (mcp 2 renamed McpError, b.q4x)."""
        module = _healthy_modules()[module_name]
        delattr(module, missing_name)
        fake_install(modules={module_name: module})

        message = check_serve_dependencies()

        assert message is not None
        assert f"cannot import name '{missing_name}' from '{module_name}'" in message

    @pytest.mark.parametrize(
        "versions,package,found",
        [
            pytest.param({"fastmcp": "4.1.0"}, "fastmcp", "4.1.0", id="fastmcp_4"),
            pytest.param({"fastmcp": "3.0.1"}, "fastmcp", "3.0.1", id="fastmcp_below_floor"),
            pytest.param({"fastmcp": "4.0.0rc1"}, "fastmcp", "4.0.0rc1", id="fastmcp_4_prerelease"),
            pytest.param({"mcp": "2.3.0"}, "mcp", "2.3.0", id="mcp_2"),
            pytest.param({"mcp": "1.23.9"}, "mcp", "1.23.9", id="mcp_below_floor"),
            pytest.param({"mcp": "garbage"}, "mcp", "garbage", id="mcp_unparseable"),
        ],
    )
    def test_out_of_range_version_is_reported(self, fake_install, versions, package, found):
        """The check fails on the installed version even though the modules import fine (they do, in b.q4x-style installs)."""
        fake_install(versions_override=versions)

        message = check_serve_dependencies()

        assert message is not None
        assert f"installed {package} {found} is outside the supported range" in message

    def test_never_raises_on_unreadable_metadata(self, fake_install, monkeypatch):
        """Metadata that raises something other than PackageNotFoundError is treated as absent."""

        def broken_version(distribution):
            raise OSError("metadata unreadable")

        monkeypatch.setattr(importlib.metadata, "version", broken_version)

        assert check_serve_dependencies() is None


class TestMessage:
    def test_message_lists_versions_ranges_and_both_fixes(self, fake_install):
        fake_install(modules={"fastmcp": None}, versions_override={"fastmcp": "3.2.4", "fastmcp-slim": None})

        message = check_serve_dependencies()

        assert "fastmcp 3.2.4" in message
        assert "fastmcp-slim not installed" in message
        assert "mcp 1.26.0" in message
        assert "fastmcp>=3.0.2,<4" in message
        assert "mcp>=1.24.0,<2" in message
        assert PIPX_FIX in message
        assert pip_fix_command() in message


class TestPipFixCommand:
    """The pip clean-reinstall command runs the interpreter that runs bees, not a bare `python`."""

    def test_command_starts_with_the_quoted_running_interpreter(self):
        command = pip_fix_command()

        assert command.startswith(f"{shlex.quote(sys.executable)} -m pip uninstall -y bees-md fastmcp fastmcp-slim mcp && ")
        assert command.endswith(f"{shlex.quote(sys.executable)} -m pip install 'bees-md[serve]'")

    def test_interpreter_path_with_spaces_is_quoted(self, monkeypatch):
        monkeypatch.setattr(sys, "executable", "/opt/my tools/venv/bin/python")

        command = pip_fix_command()

        assert command == (
            "'/opt/my tools/venv/bin/python' -m pip uninstall -y bees-md fastmcp fastmcp-slim mcp && "
            "'/opt/my tools/venv/bin/python' -m pip install 'bees-md[serve]'"
        )
        assert shlex.split(command.split(" && ")[0])[0] == "/opt/my tools/venv/bin/python"

    @pytest.mark.parametrize("executable", [pytest.param("", id="empty"), pytest.param(None, id="none")])
    def test_falls_back_to_python3_when_the_interpreter_is_unknown(self, monkeypatch, executable):
        monkeypatch.setattr(sys, "executable", executable)

        assert pip_fix_command().startswith("python3 -m pip uninstall -y ")

    def test_message_carries_the_command_for_the_running_interpreter(self, fake_install, monkeypatch):
        monkeypatch.setattr(sys, "executable", "/opt/my tools/bin/python")
        fake_install(modules={"fastmcp": None})

        message = check_serve_dependencies()

        assert "'/opt/my tools/bin/python' -m pip install 'bees-md[serve]'" in message


class TestParseVersion:
    @pytest.mark.parametrize(
        "text,expected",
        [
            pytest.param("3.4.8", (3, 4, 8), id="plain"),
            pytest.param("3.4.8rc1", (3, 4, 8), id="prerelease_suffix"),
            pytest.param("4", (4,), id="single_part"),
            pytest.param(" 1.24.0 ", (1, 24, 0), id="whitespace"),
            pytest.param("garbage", (), id="unparseable"),
        ],
    )
    def test_parse_version(self, text, expected):
        assert parse_version(text) == expected
