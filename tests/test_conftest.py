"""
Tests for conftest.py fixture patching behavior.

Validates that the mock_git_repo_check fixture properly patches
get_repo_root_from_path and allows tests to run in non-git temp directories,
and that a test session never reads or writes the real home directory (b.319).
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from src import mcp_repo_utils, mcp_server

REPO_ROOT = Path(__file__).resolve().parent.parent

# Test modules run as their own pytest session on this suite's conftest, started with
# HOME={home}, the "real" home. Each records the home the session resolved in {record}.
_INNER_PRELUDE = """
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path({home!r})
Path({record!r}).write_text(str(Path.home()))
"""
_INNER_LEAVES_HOME_ALONE = _INNER_PRELUDE + """

def test_run():
    # Another tool changes the real config while the session runs
    script = "import pathlib, sys; pathlib.Path(sys.argv[1]).write_text('changed')"
    subprocess.run([sys.executable, "-c", script, str(HOME / ".bees" / "config.json")], check=True)

    import src.mcp_server  # creates ~/.bees/ and sets up logging into it at import time
    from src.cli import _configure_file_logging

    assert not _configure_file_logging().is_relative_to(HOME)
    # Subprocesses look for `pip install --user` packages where they are, not in the temp home
    script = "import site; print(site.getuserbase())"
    user_base = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True).stdout
    assert not Path(user_base.strip()).is_relative_to(Path.home())
"""
_INNER_WRITES_REAL_HOME = _INNER_PRELUDE + """

def test_run():
    try:
        (HOME / ".bees" / "leak.txt").write_text("leak")
    except Exception:
        pass  # a swallowed error must not hide the access
"""
_INNER_WRITES_REAL_HOME_AT_IMPORT = _INNER_PRELUDE + """
try:
    (HOME / ".bees" / "leak.txt").write_text("leak")
except Exception:
    pass  # outside any test: only the session-end check sees it


def test_run():
    pass
"""
_INNER_LEAKS_HOME_ENV = _INNER_PRELUDE + """

def test_run():
    os.environ["HOME"] = str(HOME)  # never restored
"""
# Run with the cwd at the real home
_INNER_RELATIVE_PATHS = _INNER_PRELUDE + """

def test_run(tmp_path):
    for name in (".bees", ".claude"):
        (tmp_path / "tree" / name).mkdir(parents=True)
        (tmp_path / "tree" / name / "file").write_text("")
    (tmp_path / "tree" / ".claude.json").write_text("")
    shutil.rmtree(tmp_path / "tree")  # removes entries by bare name relative to a dir fd, not the cwd
    try:
        Path(".bees", "leak.txt").write_text("leak")  # relative to the cwd
    except Exception:
        pass
"""


def _run_pytest(tmp_path: Path, home: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """Run pytest with this suite's conftest in a subprocess started with HOME={home}, temp files in tmp_path/temp.

    The outer run's PYTEST_ADDOPTS and PYTEST_PLUGINS are left out, so they can't change the inner run.
    """
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir(exist_ok=True)
    env = {var: value for var, value in os.environ.items() if var not in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS")}
    env |= dict.fromkeys(("HOME", "USERPROFILE"), str(home)) | dict.fromkeys(("TMPDIR", "TEMP", "TMP"), str(temp_dir))
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO_ROOT), os.environ.get("PYTHONPATH")]))
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "tests.conftest", "-p", "no:cacheprovider", "-rA", *args],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=120,
    )


class TestMockGitRepoCheck:
    """Test the mock_git_repo_check fixture behavior."""

    def test_mcp_repo_utils_is_patched(self, tmp_path, monkeypatch):
        """Verify mcp_repo_utils.get_repo_root_from_path returns resolved path."""
        monkeypatch.chdir(tmp_path)

        # Should return the resolved start_path
        result = mcp_repo_utils.get_repo_root_from_path(tmp_path)
        assert result == tmp_path.resolve()

    def test_mcp_server_requires_separate_patch(self):
        """Verify mcp_server requires separate patching due to import binding."""
        # Python imports create name bindings at import time
        # mcp_server.py imports get_repo_root_from_path from repo_utils
        # This creates a local binding in mcp_server's namespace to the function object
        assert hasattr(mcp_server, 'get_repo_root_from_path')
        assert hasattr(mcp_repo_utils, 'get_repo_root_from_path')

        # Both should return start_path.resolve() — same behavior
        test_path = Path("/tmp/test")
        assert mcp_server.get_repo_root_from_path(test_path) == test_path.resolve()
        assert mcp_repo_utils.get_repo_root_from_path(test_path) == test_path.resolve()

    def test_mock_allows_non_git_directory(self, tmp_path, monkeypatch):
        """Verify function works in non-git temporary directories."""
        monkeypatch.chdir(tmp_path)

        # tmp_path has no .git or .bees directory
        assert not (tmp_path / '.git').exists()
        assert not (tmp_path / '.bees').exists()

        # Should return the resolved start_path without error
        result = mcp_repo_utils.get_repo_root_from_path(tmp_path)
        assert result == tmp_path.resolve()
        assert result.exists()

    def test_mock_handles_nested_directories(self, tmp_path, monkeypatch):
        """Verify function returns the resolved nested path, not a parent."""
        monkeypatch.chdir(tmp_path)

        # Create nested directory structure
        nested = tmp_path / 'a' / 'b' / 'c'
        nested.mkdir(parents=True)

        # Should return the resolved start_path (not cwd or a parent)
        result = mcp_repo_utils.get_repo_root_from_path(nested)
        assert result == nested.resolve()

    def test_mock_with_git_directory_present(self, tmp_path, monkeypatch):
        """Verify function works when .git is present (but doesn't depend on it)."""
        monkeypatch.chdir(tmp_path)

        # Create .git directory
        git_dir = tmp_path / '.git'
        git_dir.mkdir()

        # Should return the resolved start_path
        result = mcp_repo_utils.get_repo_root_from_path(tmp_path)
        assert result == tmp_path

    def test_mock_with_bees_directory_present(self, tmp_path, monkeypatch):
        """Verify function works when .bees is present (but doesn't depend on it)."""
        monkeypatch.chdir(tmp_path)

        # Create .bees directory
        bees_dir = tmp_path / '.bees'
        bees_dir.mkdir()

        # Should return the resolved start_path
        result = mcp_repo_utils.get_repo_root_from_path(tmp_path)
        assert result == tmp_path

    def test_mock_returns_resolved_start_path(self, tmp_path, monkeypatch):
        """Verify function returns the resolved start_path for subdirectories."""
        monkeypatch.chdir(tmp_path)

        # Create subdirectory without .git or .bees
        subdir = tmp_path / 'subdir'
        subdir.mkdir()

        # Should return the resolved start_path
        result = mcp_repo_utils.get_repo_root_from_path(subdir)
        assert result == subdir.resolve()


class TestMockGitRepoCheckMarker:
    """Test the @pytest.mark.needs_real_git_check marker."""

    @pytest.mark.needs_real_git_check
    def test_marker_bypasses_mock(self, tmp_path):
        """Verify tests marked with needs_real_git_check bypass the mock."""
        # This test is marked to bypass the mock
        # Note: This test validates the marker exists and is recognized by pytest
        # The actual bypass behavior is tested in integration tests
        pass


class TestMockGitRepoCheckEdgeCases:
    """Test edge cases in mock_git_repo_check fixture."""

    def test_mock_with_symlinked_directory(self, tmp_path, monkeypatch):
        """Verify function resolves symlinks correctly."""
        monkeypatch.chdir(tmp_path)

        # Create target directory and symlink
        target = tmp_path / 'target'
        target.mkdir()
        symlink = tmp_path / 'link'
        symlink.symlink_to(target)

        # Should resolve symlinks and return target
        result = mcp_repo_utils.get_repo_root_from_path(symlink)
        assert result == target.resolve()

    def test_mock_returns_resolved_paths(self, tmp_path, monkeypatch):
        """Verify function returns resolved (absolute) paths."""
        monkeypatch.chdir(tmp_path)

        result = mcp_repo_utils.get_repo_root_from_path(tmp_path)
        assert result.is_absolute()
        assert result == result.resolve()


class TestFixtureIntegration:
    """Test fixture integration with other test fixtures."""

    def test_isolated_bees_env_uses_mock(self, isolated_bees_env):
        """Verify isolated_bees_env fixture benefits from mock_git_repo_check."""
        helper = isolated_bees_env

        # The environment should be usable without a real git repo
        # Create a hive and verify it works
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        assert hive_dir.exists()

        # Config operations should work with the mock
        helper.write_config()
        config_path = helper.global_bees_dir / 'config.json'
        assert config_path.exists()

    def test_setup_tickets_dir_uses_mock(self, tmp_path, monkeypatch):
        """Verify fixtures using tmp_path work correctly with function."""
        monkeypatch.chdir(tmp_path)

        # Create .bees directory
        bees_dir = tmp_path / '.bees'
        bees_dir.mkdir()

        # Should be able to find repo root
        result = mcp_repo_utils.get_repo_root_from_path(tmp_path)
        assert result == tmp_path


class TestRealHomeIsolation:
    """b.319: a test session never reads or writes the home directory it was started with."""

    @pytest.mark.parametrize(
        "inner_test,cwd_at_home,exit_code,outcomes,outputs,config_after",
        [
            pytest.param(
                _INNER_LEAVES_HOME_ALONE, False, 0, ["PASSED"], [], "changed", id="concurrent_config_change_kept",
            ),
            pytest.param(
                _INNER_WRITES_REAL_HOME, False, 1, ["PASSED", "ERROR"],
                ["open on {leak}: tests must not touch the real home directory"], "original",
                id="swallowed_write_blocked_and_fails_test",
            ),
            pytest.param(
                _INNER_WRITES_REAL_HOME_AT_IMPORT, False, 1, ["PASSED"],
                ["real home directory touched", "open on {leak}"], "original",
                id="write_outside_tests_fails_run",
            ),
            pytest.param(
                _INNER_WRITES_REAL_HOME_AT_IMPORT + "\nraise RuntimeError('broken test module')\n", False, 2,
                ["ERROR"], ["real home directory touched"], "original",
                id="worse_exit_status_kept",
            ),
            pytest.param(
                _INNER_LEAKS_HOME_ENV, False, 1, ["PASSED", "ERROR"],
                ["Path.home() resolves to {home}, in the real home directory"], "original",
                id="leaked_home_env_fails_test",
            ),
            pytest.param(
                _INNER_RELATIVE_PATHS, True, 1, ["PASSED", "ERROR"], ["open on {leak}"], "original",
                id="cwd_at_home_dir_fd_paths_allowed_relative_write_blocked",
            ),
        ],
    )
    def test_session_leaves_real_home_alone(
        self, tmp_path, inner_test, cwd_at_home, exit_code, outcomes, outputs, config_after,
    ):
        """The session resolves a temp home, deleted at the end, and leaves the real ~/.bees/ as other tools left it."""
        home, record = tmp_path / "home", tmp_path / "resolved_home.txt"
        (home / ".bees").mkdir(parents=True)
        (home / ".bees" / "config.json").write_text("original")
        (tmp_path / "pytest.ini").write_text("[pytest]\n")
        (tmp_path / "test_inner.py").write_text(inner_test.format(home=str(home), record=str(record)))

        result = _run_pytest(
            tmp_path, home, home if cwd_at_home else tmp_path,
            f"--basetemp={tmp_path / 'basetemp'}", str(tmp_path / "test_inner.py"),
        )

        session_output = result.stdout + result.stderr
        assert (home / ".bees" / "config.json").read_text() == config_after, session_output
        assert sorted(p.relative_to(home).as_posix() for p in home.rglob("*")) == [".bees", ".bees/config.json"]
        assert result.returncode == exit_code, session_output
        # The -rA result lines, e.g. "ERROR test_inner.py::test_run - ..."; the counts line changes with warnings
        assert re.findall(r"^(PASSED|FAILED|ERROR) \S*test_inner\.py", result.stdout, re.M) == outcomes, session_output
        for output in outputs:
            assert output.format(home=home, leak=home / ".bees" / "leak.txt") in result.stdout, session_output
        session_home = Path(record.read_text())
        assert session_home.parent == tmp_path / "temp"
        assert not session_home.exists()

    def test_temp_home_deleted_when_session_never_configured(self, tmp_path):
        """`pytest --version` imports the conftest but never runs pytest_unconfigure."""
        result = _run_pytest(tmp_path, tmp_path, tmp_path, "--version")

        assert result.returncode == 0, result.stdout + result.stderr
        assert list((tmp_path / "temp").glob("bees-test-home-*")) == []
