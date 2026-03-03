"""Tests for the bees package entry point.

Verifies that `bees` is correctly registered as a console_scripts entry point
and that invoking it via subprocess does not crash with an ImportError.
"""

import importlib.metadata
import subprocess
import sys


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
