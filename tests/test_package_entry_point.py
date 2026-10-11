"""Tests for the bees package metadata.

Verifies that `bees` is correctly registered as a console_scripts entry point,
that invoking it via subprocess does not crash with an ImportError, that
`bees --version` / `-V` report the installed bees-md version (JSON, "unknown"
without metadata), and that the
`serve` extra in pyproject.toml keeps fastmcp and mcp below their next major
version, in agreement with the Poetry constraints.
"""

import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_bees_entry_point_registered():
    """bees console_scripts entry point is present in package metadata."""
    eps = importlib.metadata.entry_points(group="console_scripts")
    names = [ep.name for ep in eps]
    assert "bees" in names


def test_bees_entry_point_value():
    """bees entry point resolves to src.cli:main."""
    eps = importlib.metadata.entry_points(group="console_scripts")
    bees_ep = next((ep for ep in eps if ep.name == "bees"), None)
    assert bees_ep is not None
    assert bees_ep.value == "src.cli:main"


def test_bees_help_exits_zero():
    """subprocess bees --help returns exit code 0 without ImportError."""
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert "ImportError" not in result.stderr
    assert result.returncode == 0


@pytest.mark.parametrize("flag", ["--version", "-V"])
def test_bees_version_flag_prints_installed_version_json(cli_runner, flag, tmp_path, monkeypatch, mock_global_bees_dir):
    """`bees --version` and `bees -V` print the bees-md version as JSON and exit 0 (b.qnz).

    Run from a directory that is no bees repo, with a malformed global config: the flag
    needs neither, so it must not read the config (any config load would fail on it).
    """
    monkeypatch.chdir(tmp_path)
    (mock_global_bees_dir / "config.json").write_text("{invalid json")

    stdout, exit_code = cli_runner([flag])

    assert exit_code == 0
    assert json.loads(stdout) == {"status": "success", "version": importlib.metadata.version("bees-md")}


def test_bees_version_flag_reports_unknown_without_metadata(cli_runner):
    """`bees --version` reports "unknown", still as a success, when bees-md metadata is missing."""
    with patch("src.version.version", side_effect=importlib.metadata.PackageNotFoundError("bees-md")):
        stdout, exit_code = cli_runner(["--version"])

    assert exit_code == 0
    assert json.loads(stdout) == {"status": "success", "version": "unknown"}


@pytest.mark.parametrize("flag", ["--version", "-V"])
def test_bees_version_flag_in_subprocess(flag):
    """The installed entry module answers `--version` with JSON on stdout, exit 0, nothing on stderr."""
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", flag],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout) == {"status": "success", "version": importlib.metadata.version("bees-md")}


def test_bees_version_flag_listed_in_help(cli_runner):
    """Top-level `bees --help` lists both spellings of the version flag."""
    stdout, exit_code = cli_runner(["--help"])

    assert exit_code == 0
    assert "-V, --version" in stdout


def test_bees_version_flag_is_top_level_only(cli_runner):
    """`bees list-hives --version` is a usage error (JSON, exit 2), not a version report."""
    stdout, exit_code = cli_runner(["list-hives", "--version"])

    assert exit_code == 2
    result = json.loads(stdout)
    assert result["status"] == "error"
    assert "--version" in result["message"]


@pytest.mark.parametrize(
    "package,next_major",
    [
        pytest.param("fastmcp", "4.0.0", id="fastmcp_below_4"),
        pytest.param("mcp", "2.0.0", id="mcp_below_2"),
    ],
)
def test_serve_extra_excludes_next_major(package, next_major):
    """PyPI serve extra excludes the next major and matches the Poetry caret pin (b.h2e)."""
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    serve = {
        req.name: req.specifier for req in map(Requirement, pyproject["project"]["optional-dependencies"]["serve"])
    }
    assert package in serve
    assert not serve[package].contains(next_major)

    poetry_pin = pyproject["tool"]["poetry"]["dependencies"][package]["version"]
    assert poetry_pin.startswith("^")
    lower = Version(poetry_pin[1:])
    assert serve[package] == SpecifierSet(f">={lower},<{lower.major + 1}")
    assert package in pyproject["tool"]["poetry"]["extras"]["serve"]
