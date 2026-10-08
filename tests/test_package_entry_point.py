"""Tests for the bees package metadata.

Verifies that `bees` is correctly registered as a console_scripts entry point,
that invoking it via subprocess does not crash with an ImportError, and that the
`serve` extra in pyproject.toml keeps fastmcp and mcp below their next major
version, in agreement with the Poetry constraints.
"""

import importlib.metadata
import subprocess
import sys
from pathlib import Path

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
