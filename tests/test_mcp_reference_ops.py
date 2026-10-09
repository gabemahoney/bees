"""
Unit tests for MCP reference_materials resolution operations.

PURPOSE:
Tests the _resolve_references pipeline and helper functions in mcp_reference_ops:
  - resolve_file_path(): default resolver for file-path entries
  - _invoke_custom_resolver(): custom subprocess resolver, including timeout and
    cancellation killing the resolver's child processes
  - _resolve_references(): orchestrates resolution for a full reference_materials list
"""

import asyncio
import gc
import json
import logging
import os
import signal
import sys
import threading
import time
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_reference_ops import (
    DEFAULT_RESOLVER_CONVENTION,
    _invoke_custom_resolver,
    _resolve_references,
    resolve_file_path,
)
from src.repo_context import repo_root_context
from tests.conftest import write_scoped_config
from tests.test_constants import GITHUB_API_COMMENTS, GITHUB_API_ISSUE, GITHUB_ISSUE_URL, HIVE_BACKEND


@pytest.fixture
def hive_env_with_refs(tmp_path, monkeypatch, mock_global_bees_dir):
    """Create a test environment with a hive containing bee tickets with reference_materials."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()

    hive_dir = tmp_path / HIVE_BACKEND
    hive_dir.mkdir(parents=True)

    # Create .hive identity marker
    hive_identity_dir = hive_dir / ".hive"
    hive_identity_dir.mkdir(parents=True, exist_ok=True)
    identity_data = {
        "normalized_name": HIVE_BACKEND,
        "display_name": "Backend",
        "created_at": "2026-02-05T00:00:00",
    }
    (hive_identity_dir / "identity.json").write_text(json.dumps(identity_data, indent=2))

    # Write scoped config
    scope_data = {
        "hives": {HIVE_BACKEND: {"path": str(hive_dir), "display_name": "Backend"}},
        "child_tiers": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
    }
    write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

    with repo_root_context(tmp_path):
        yield tmp_path, hive_dir


# ============================================================================
# DEFAULT_RESOLVER_CONVENTION CONSTANT
# ============================================================================


class TestDefaultResolverConvention:
    """Tests that DEFAULT_RESOLVER_CONVENTION is a non-empty string."""

    def test_is_string(self):
        """DEFAULT_RESOLVER_CONVENTION is a string."""
        assert isinstance(DEFAULT_RESOLVER_CONVENTION, str)

    def test_is_non_empty(self):
        """DEFAULT_RESOLVER_CONVENTION is not empty."""
        assert DEFAULT_RESOLVER_CONVENTION.strip() != ""


# ============================================================================
# resolve_file_path TESTS
# ============================================================================


class TestResolveFilePath:
    """Tests for resolve_file_path() — the default resolver."""

    def test_existing_absolute_path_succeeds(self, tmp_path):
        """Existing absolute path returns success with resolved_path."""
        existing = tmp_path / "spec.md"
        existing.touch()

        result = resolve_file_path(str(existing))

        assert result["status"] == "success"
        assert result["resolved_path"] == str(existing.resolve())

    def test_nonexistent_absolute_path_fails(self, tmp_path):
        """Non-existent absolute path returns error."""
        missing = tmp_path / "nonexistent.md"

        result = resolve_file_path(str(missing))

        assert result["status"] == "error"
        assert "raw_value" in result
        assert "does not exist" in result["error"]

    def test_relative_path_with_repo_root(self, tmp_path):
        """Relative path resolved against repo_root returns success when file exists."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").touch()

        result = resolve_file_path("docs/guide.md", repo_root=tmp_path)

        assert result["status"] == "success"
        assert "guide.md" in result["resolved_path"]

    def test_relative_path_without_repo_root_fails(self):
        """Relative path without repo_root returns error."""
        result = resolve_file_path("relative/path.md", repo_root=None)

        assert result["status"] == "error"
        assert "repo_root is required" in result["error"]

    def test_non_string_value_fails(self, tmp_path):
        """Non-string value returns error (value must be a string file path)."""
        result = resolve_file_path({"url": "http://example.com"})

        assert result["status"] == "error"
        assert "raw_value" in result
        assert "string file path" in result["error"]

    def test_none_value_fails(self, tmp_path):
        """None value returns error."""
        result = resolve_file_path(None)

        assert result["status"] == "error"
        assert "raw_value" in result


# ============================================================================
# _invoke_custom_resolver TESTS
# ============================================================================


class TestInvokeCustomResolver:
    """Tests for custom resolver subprocess invocation (_invoke_custom_resolver)."""

    async def test_custom_resolver_success(self, tmp_path):
        """Custom resolver executes successfully and returns parsed JSON."""
        resolver_script = tmp_path / "resolver.sh"
        resolver_script.write_text(
            "#!/bin/bash\necho '[\"file1.txt\", \"file2.txt\"]'\n"
        )
        resolver_script.chmod(0o755)

        result = await _invoke_custom_resolver(
            command=str(resolver_script),
            value="test-value",
            repo_root=tmp_path,
            timeout=5,
        )

        assert result == ["file1.txt", "file2.txt"]

    async def test_custom_resolver_with_null_output(self, tmp_path):
        """Custom resolver returning null is parsed correctly."""
        resolver_script = tmp_path / "resolver_null.sh"
        resolver_script.write_text("#!/bin/bash\necho 'null'\n")
        resolver_script.chmod(0o755)

        result = await _invoke_custom_resolver(
            command=str(resolver_script),
            value="test-value",
            repo_root=tmp_path,
            timeout=5,
        )

        assert result is None

    async def test_custom_resolver_none_value_returns_none(self, tmp_path):
        """None value short-circuits before subprocess invocation, returns None."""
        invoked_file = tmp_path / "resolver_was_invoked.txt"

        resolver_script = tmp_path / "resolver_none.sh"
        resolver_script.write_text(
            f"#!/bin/bash\ntouch {invoked_file}\necho 'null'\n"
        )
        resolver_script.chmod(0o755)

        result = await _invoke_custom_resolver(
            command=str(resolver_script),
            value=None,
            repo_root=tmp_path,
            timeout=5,
        )

        assert result is None
        assert not invoked_file.exists(), "Resolver subprocess should not have been invoked for None value"

    async def test_custom_resolver_non_zero_exit(self, tmp_path):
        """Custom resolver with non-zero exit code raises RuntimeError with stderr."""
        resolver_script = tmp_path / "resolver_fail.sh"
        resolver_script.write_text(
            "#!/bin/bash\necho 'Resolver failed' >&2\nexit 1\n"
        )
        resolver_script.chmod(0o755)

        with pytest.raises(RuntimeError, match=r"Resolver exited with code 1.*Resolver failed"):
            await _invoke_custom_resolver(
                command=str(resolver_script),
                value="test-value",
                repo_root=tmp_path,
                timeout=5,
            )

    async def test_custom_resolver_invalid_json(self, tmp_path):
        """Custom resolver with invalid JSON output raises RuntimeError."""
        resolver_script = tmp_path / "resolver_bad_json.sh"
        resolver_script.write_text("#!/bin/bash\necho 'not valid json'\n")
        resolver_script.chmod(0o755)

        with pytest.raises(RuntimeError, match=r"Resolver returned invalid JSON"):
            await _invoke_custom_resolver(
                command=str(resolver_script),
                value="test-value",
                repo_root=tmp_path,
                timeout=5,
            )

    async def test_custom_resolver_receives_value_arg(self, tmp_path):
        """Custom resolver is invoked with --repo-root and --value args."""
        output_file = tmp_path / "resolver_output.txt"

        resolver_script = tmp_path / "resolver_echo_args.sh"
        resolver_script.write_text(
            f"#!/bin/bash\necho \"$@\" > {output_file}\necho '[\"verified\"]'\n"
        )
        resolver_script.chmod(0o755)

        result = await _invoke_custom_resolver(
            command=str(resolver_script),
            value="my-spec-value",
            repo_root=tmp_path,
            timeout=5,
        )

        assert result == ["verified"]
        assert output_file.exists()
        args_content = output_file.read_text().strip()
        assert "--repo-root" in args_content
        assert "--value" in args_content

    async def test_custom_resolver_string_value_passed_raw(self, tmp_path):
        """String values are passed raw (not JSON-encoded) to the resolver."""
        captured_file = tmp_path / "captured_value.txt"

        resolver_script = tmp_path / "resolver_capture.sh"
        resolver_script.write_text(
            f"""#!/bin/bash
while [[ $# -gt 0 ]]; do
    case "$1" in
        --value) echo -n "$2" > {captured_file}; shift 2;;
        *) shift;;
    esac
done
echo '["resolved"]'
"""
        )
        resolver_script.chmod(0o755)

        raw_value = "abc-123-def-456"
        result = await _invoke_custom_resolver(
            command=str(resolver_script),
            value=raw_value,
            repo_root=tmp_path,
            timeout=5,
        )

        assert result == ["resolved"]
        assert captured_file.exists()
        captured = captured_file.read_text()
        assert captured == raw_value

    async def test_custom_resolver_non_string_value_json_encoded(self, tmp_path):
        """Non-string values are JSON-encoded before being passed to the resolver."""
        captured_file = tmp_path / "captured_value.txt"

        resolver_script = tmp_path / "resolver_capture_dict.sh"
        resolver_script.write_text(
            f"""#!/bin/bash
while [[ $# -gt 0 ]]; do
    case "$1" in
        --value) echo -n "$2" > {captured_file}; shift 2;;
        *) shift;;
    esac
done
echo '["verified"]'
"""
        )
        resolver_script.chmod(0o755)

        dict_value = {"url": "https://example.com", "version": 1}
        result = await _invoke_custom_resolver(
            command=str(resolver_script),
            value=dict_value,
            repo_root=tmp_path,
            timeout=5,
        )

        assert result == ["verified"]
        assert captured_file.exists()
        captured = captured_file.read_text()
        # Dict values are JSON-encoded
        assert captured == json.dumps(dict_value)

    # -------------------------------------------------------------------------
    # Interpreter-detection tests (mock subprocess to capture command string)
    # -------------------------------------------------------------------------

    def _make_mock_process(self, stdout_data=b'["ok"]', returncode=0):
        """Build an AsyncMock that mimics asyncio.subprocess.Process."""
        proc = MagicMock()
        proc.returncode = returncode
        proc.communicate = AsyncMock(return_value=(stdout_data, b""))
        proc.kill = MagicMock()
        proc.wait = AsyncMock(return_value=None)
        return proc

    async def test_py_extension_uses_sys_executable(self, tmp_path):
        """Command ending in .py uses sys.executable as interpreter — no executable bit required."""
        script = tmp_path / "my_resolver.py"
        script.write_text("# python resolver\n")
        # Intentionally NOT setting executable bit

        captured_args = []

        async def fake_create_subprocess_exec(*args, **kwargs):
            captured_args.append(list(args))
            return self._make_mock_process()

        with patch("asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec):
            result = await _invoke_custom_resolver(
                command=str(script),
                value="some-value",
                repo_root=tmp_path,
                timeout=5,
            )

        assert result == ["ok"]
        assert len(captured_args) == 1
        args = captured_args[0]
        # sys.executable must be the first argument
        assert args[0] == sys.executable
        # The script path must follow the interpreter
        assert str(script) in args

    async def test_shebang_line_uses_extracted_interpreter(self, tmp_path):
        """Command with #!/usr/bin/env python3 shebang uses /usr/bin/env python3 as interpreter."""
        script = tmp_path / "my_resolver.sh"
        script.write_text("#!/usr/bin/env python3\n# not really python\n")
        # No executable bit needed — shebang detection handles it

        captured_args = []

        async def fake_create_subprocess_exec(*args, **kwargs):
            captured_args.append(list(args))
            return self._make_mock_process()

        with patch("asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec):
            result = await _invoke_custom_resolver(
                command=str(script),
                value="some-value",
                repo_root=tmp_path,
                timeout=5,
            )

        assert result == ["ok"]
        assert len(captured_args) == 1
        args = captured_args[0]
        # The shebang interpreter must be the first argument
        assert args[0] == "/usr/bin/env"
        assert str(script) in args

    async def test_no_interpreter_falls_back_to_direct_invocation(self, tmp_path):
        """Command with no .py extension and no shebang invokes the script directly."""
        script = tmp_path / "my_resolver.sh"
        # Plain content, no shebang
        script.write_text("echo 'nothing'\n")
        script.chmod(0o755)

        captured_args = []

        async def fake_create_subprocess_exec(*args, **kwargs):
            captured_args.append(list(args))
            return self._make_mock_process()

        with patch("asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec):
            result = await _invoke_custom_resolver(
                command=str(script),
                value="some-value",
                repo_root=tmp_path,
                timeout=5,
            )

        assert result == ["ok"]
        assert len(captured_args) == 1
        args = captured_args[0]
        # Must not contain sys.executable or /usr/bin/env as a leading arg
        assert args[0] == str(script)

    async def test_unreadable_script_falls_back_to_direct_invocation(self, tmp_path):
        """If the script file cannot be read (OSError), falls back to direct invocation."""
        # Use a path that doesn't exist — open() will raise FileNotFoundError (subclass of OSError)
        nonexistent = tmp_path / "ghost_resolver.sh"

        captured_args = []

        async def fake_create_subprocess_exec(*args, **kwargs):
            captured_args.append(list(args))
            return self._make_mock_process()

        with patch("asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec):
            result = await _invoke_custom_resolver(
                command=str(nonexistent),
                value="some-value",
                repo_root=tmp_path,
                timeout=5,
            )

        assert result == ["ok"]
        assert len(captured_args) == 1
        args = captured_args[0]
        # Direct invocation: first arg is the script path itself
        assert args[0] == str(nonexistent)


# ============================================================================
# _invoke_custom_resolver — timeout and cancellation kill the resolver's children
# ============================================================================

# A child left running holds the resolver's stdout/stderr pipes open, so a call
# that does not kill it blocks until this sleep ends.
_CHILD_SLEEP_SECONDS = 10
_RESOLVER_TIMEOUT = 1
# Upper bound for a timed-out call: the timeout, the 1 s post-kill drain, slack.
_TIMEOUT_BOUND = _RESOLVER_TIMEOUT + 3

# Starts a `sleep` child (in the resolver's process group, or in its own session),
# records the PIDs atomically, then waits for the child or exits leaving it behind.
_SPAWNING_RESOLVER = """\
import json, os, subprocess
child = subprocess.Popen(["sleep", "{sleep}"], start_new_session={own_session})
with open({tmp!r}, "w") as f:
    json.dump({{"resolver": os.getpid(), "pgid": os.getpgid(0), "child": child.pid}}, f)
os.replace({tmp!r}, {pid_file!r})
if {wait}:
    child.wait()
"""


def _is_running(pid: int) -> bool:
    """True while pid is a live process; a zombie (exited, not yet reaped) counts as gone."""
    if Path("/proc/self/stat").exists():
        try:
            state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except OSError:
            return False
        return state not in ("Z", "X")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass  # Exists, owned by another user
    return True


def _runs_resolver_or_child(pid: int, script: Path) -> bool:
    """True if pid still runs `script` or a `sleep`, so a reused PID is never killed; without /proc, if it runs."""
    if not _is_running(pid):
        return False
    if not Path("/proc").exists():
        return True  # No procfs (e.g. macOS) to read the command line from
    try:
        argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except OSError:
        return False
    return argv[0] == b"sleep" or os.fsencode(script) in argv


def _gone_within(pid: int, seconds: float = 3.0) -> bool:
    """Poll until pid is no longer running; False if it still runs after `seconds`."""
    deadline = time.monotonic() + seconds
    while _is_running(pid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


@pytest.fixture
def run_cleanly(caplog, capfd):
    """Run a coroutine with asyncio.run, as `bees show-ticket` does; return elapsed seconds.

    Then asserts the run left nothing that prints a traceback: no asyncio error log, no exception in a __del__.
    """

    def _run(main: Coroutine[Any, Any, None]) -> float:
        # Collect an earlier test's garbage first, outside this run's checks, so this test is not blamed for it.
        gc.collect()
        logged_before = len(caplog.records)
        # Catch exceptions raised in a __del__ here; pytest's own hook only warns, and maybe in another test.
        unraisable: list = []
        pytest_hook = sys.unraisablehook
        sys.unraisablehook = unraisable.append
        try:
            threads_before = set(threading.enumerate())
            started = time.monotonic()
            asyncio.run(main)
            elapsed = time.monotonic() - started
            # asyncio's child watcher threads hold the subprocess transports until they finish; collect after them.
            for thread in set(threading.enumerate()) - threads_before:
                thread.join(timeout=5)
                # Still running, it frees its transport in a later test; fail this one instead.
                assert not thread.is_alive(), f"{thread.name} still running 5 s after the event loop closed"
            gc.collect()  # A leaked future or transport reports itself when collected
        finally:
            # Restore here, not at teardown: whatever is raised after this run must not land in an unchecked list.
            sys.unraisablehook = pytest_hook

        logged = caplog.records[logged_before:]
        assert [r.getMessage() for r in logged if r.name == "asyncio" and r.levelno >= logging.ERROR] == []
        assert [f"{u.object!r}: {u.exc_value!r}" for u in unraisable] == []
        err = capfd.readouterr().err
        for leak_sign in ("Traceback", "never retrieved", "Event loop is closed"):
            assert leak_sign not in err
        return elapsed

    return _run


@pytest.fixture
def run_to_timeout(tmp_path, run_cleanly):
    """Run a resolver until the call reports its timeout, via `run_cleanly`; return elapsed seconds."""

    async def _call(script: Path) -> None:
        with pytest.raises(RuntimeError, match=rf"^Resolver timed out after {_RESOLVER_TIMEOUT} seconds$"):
            await _invoke_custom_resolver(command=str(script), value="v", repo_root=tmp_path, timeout=_RESOLVER_TIMEOUT)

    def _run(script: Path) -> float:
        return run_cleanly(_call(script))

    return _run


@pytest.fixture
def run_to_cancel(tmp_path, run_cleanly):
    """Cancel the call (the caller gives up, e.g. Ctrl-C) once the resolver has started its child, via `run_cleanly`."""

    async def _call(script: Path, pid_file: Path) -> None:
        task = asyncio.create_task(
            _invoke_custom_resolver(command=str(script), value="v", repo_root=tmp_path, timeout=None)
        )
        while not pid_file.exists() and not task.done():
            await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    def _run(script: Path, pid_file: Path) -> None:
        run_cleanly(asyncio.wait_for(_call(script, pid_file), timeout=10))

    return _run


@pytest.fixture
def spawning_resolver(tmp_path):
    """Factory for a .py resolver that starts a `sleep` child; kills those still running on teardown."""
    made: list[tuple[Path, Path]] = []

    def _make(*, wait: bool = True, own_session: bool = False) -> tuple[Path, Path]:
        script = tmp_path / f"spawning_resolver_{len(made)}.py"
        pid_file = tmp_path / f"spawning_resolver_{len(made)}.json"
        script.write_text(
            _SPAWNING_RESOLVER.format(
                sleep=_CHILD_SLEEP_SECONDS,
                own_session=own_session,
                wait=wait,
                tmp=f"{pid_file}.tmp",
                pid_file=str(pid_file),
            )
        )
        made.append((script, pid_file))
        return script, pid_file

    yield _make

    for script, pid_file in made:
        if not pid_file.exists():
            continue
        pids = json.loads(pid_file.read_text())
        for pid in (pids["resolver"], pids["child"]):
            if _runs_resolver_or_child(pid, script):
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass  # Exited since the check


@pytest.mark.skipif(os.name != "posix", reason="process groups and `sleep` are POSIX-only")
class TestCustomResolverKillsChildren:
    """A timed-out or cancelled resolver's children must not outlive the call or block it (b.bh8)."""

    @pytest.mark.parametrize(
        "wait",
        [
            pytest.param(True, id="resolver_waits_on_child"),
            pytest.param(False, id="resolver_exits_leaving_child"),
        ],
    )
    def test_timeout_kills_children_and_returns_within_bound(self, spawning_resolver, run_to_timeout, wait):
        """On timeout the resolver and its child are killed and the call returns promptly, with no traceback."""
        script, pid_file = spawning_resolver(wait=wait)

        assert run_to_timeout(script) < _TIMEOUT_BOUND
        pids = json.loads(pid_file.read_text())
        assert _gone_within(pids["resolver"])
        assert _gone_within(pids["child"])

    @pytest.mark.parametrize(
        "wait, kill_errors",
        [
            pytest.param(True, [], id="resolver_waits_on_child"),
            pytest.param(False, [ProcessLookupError], id="resolver_exited_and_reaped"),
        ],
    )
    def test_child_outside_group_cannot_block_past_bound(
        self, spawning_resolver, run_to_timeout, monkeypatch, wait, kill_errors
    ):
        """A child in its own session escapes the kill but holds the pipes; the call still returns within the bound.

        A resolver already exited and reaped leaves its group empty, so killing the group raises ProcessLookupError.
        """
        real_killpg = os.killpg
        raised: list[type[OSError]] = []

        def _recording_killpg(pgid: int, sig: int) -> None:
            try:
                real_killpg(pgid, sig)
            except OSError as e:
                raised.append(type(e))
                raise

        monkeypatch.setattr("src.mcp_reference_ops.os.killpg", _recording_killpg)
        script, pid_file = spawning_resolver(own_session=True, wait=wait)

        assert run_to_timeout(script) < _TIMEOUT_BOUND
        assert raised == kill_errors
        assert _gone_within(json.loads(pid_file.read_text())["resolver"])

    def test_without_process_groups_kills_resolver_only(self, spawning_resolver, run_to_timeout, monkeypatch):
        """Without process groups the resolver shares the caller's group, is killed itself, and the call is bounded."""
        monkeypatch.setattr("src.mcp_reference_ops._KILL_PROCESS_GROUP", False)
        script, pid_file = spawning_resolver()

        assert run_to_timeout(script) < _TIMEOUT_BOUND
        pids = json.loads(pid_file.read_text())
        assert pids["pgid"] == os.getpgid(0)  # not started in a new session
        assert _gone_within(pids["resolver"])

    def test_cancelled_call_kills_resolver_and_children(self, spawning_resolver, run_to_cancel):
        """Cancelling the call kills and reaps the resolver and its child, with no traceback once the loop closes."""
        script, pid_file = spawning_resolver()

        run_to_cancel(script, pid_file)

        pids = json.loads(pid_file.read_text())
        assert _gone_within(pids["resolver"])
        assert _gone_within(pids["child"])

    @pytest.mark.parametrize("ending", ["timeout", "cancel"])
    def test_kill_refused_still_ends_call(self, spawning_resolver, run_to_timeout, run_to_cancel, monkeypatch, ending):
        """PermissionError from killing the group (macOS, only zombies left) is ignored; the call ends as usual."""

        def _refuse(pgid: int, sig: int) -> None:
            raise PermissionError

        monkeypatch.setattr("src.mcp_reference_ops.os.killpg", _refuse)
        # As where EPERM really happens, the resolver itself has exited; here its child still holds the pipes.
        script, pid_file = spawning_resolver(wait=False)

        if ending == "timeout":
            assert run_to_timeout(script) < _TIMEOUT_BOUND  # the timeout error, not "Failed to invoke resolver"
        else:
            run_to_cancel(script, pid_file)  # CancelledError still propagates
        # The refused kill left the child running; spawning_resolver kills it on teardown.
        assert _is_running(json.loads(pid_file.read_text())["child"])


# ============================================================================
# _resolve_references TESTS
# ============================================================================


class TestResolveReferencesNull:
    """Tests for _resolve_references with None input."""

    async def test_none_returns_none(self, tmp_path):
        """None reference_materials returns None directly."""
        result = await _resolve_references(None, repo_root=tmp_path)
        assert result is None


class TestResolveReferencesDefaultResolver:
    """Tests for _resolve_references with default resolver."""

    async def test_single_entry_existing_file(self, tmp_path):
        """Single entry with existing file resolves successfully."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "spec.md").touch()

        reference_materials = [{"value": "docs/spec.md"}]
        result = await _resolve_references(reference_materials, repo_root=tmp_path)

        assert result is not None
        assert len(result) == 1
        assert result[0]["value"] == "docs/spec.md"
        assert result[0]["resolved"]["status"] == "success"
        assert "spec.md" in result[0]["resolved"]["resolved_path"]

    async def test_single_entry_missing_file(self, tmp_path):
        """Single entry with missing file returns error in resolved."""
        reference_materials = [{"value": "docs/missing.md"}]
        result = await _resolve_references(reference_materials, repo_root=tmp_path)

        assert result is not None
        assert len(result) == 1
        assert result[0]["resolved"]["status"] == "error"

    async def test_multiple_entries_resolved_independently(self, tmp_path):
        """Multiple entries are each resolved independently."""
        (tmp_path / "a.md").touch()

        reference_materials = [
            {"value": "a.md"},
            {"value": "missing.md"},
        ]
        result = await _resolve_references(reference_materials, repo_root=tmp_path)

        assert result is not None
        assert len(result) == 2
        assert result[0]["resolved"]["status"] == "success"
        assert result[1]["resolved"]["status"] == "error"

    async def test_entry_preserves_original_fields(self, tmp_path):
        """Each resolved entry preserves all original entry fields plus 'resolved'."""
        (tmp_path / "spec.md").touch()

        entry = {"value": "spec.md", "label": "API Spec"}
        result = await _resolve_references([entry], repo_root=tmp_path)

        assert result is not None
        assert result[0]["value"] == "spec.md"
        assert result[0]["label"] == "API Spec"
        assert "resolved" in result[0]


class TestResolveReferencesCustomResolver:
    """Tests for _resolve_references with registered custom resolver."""

    async def test_registered_resolver_invoked(self, tmp_path, mock_global_bees_dir, monkeypatch):
        """Entry with a registered resolver name invokes the custom resolver."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir(exist_ok=True)

        # Create resolver script
        resolver_script = tmp_path / "custom_resolver.sh"
        resolver_script.write_text(
            "#!/bin/bash\necho '{\"resolved\": true}'\n"
        )
        resolver_script.chmod(0o755)

        # Register the resolver in the global config
        from src.config import ResolverEntry, save_resolver_registry
        registry = {"my_resolver": ResolverEntry(path=str(resolver_script), timeout=5)}
        save_resolver_registry(registry)

        reference_materials = [{"value": "some-spec", "resolver": "my_resolver"}]

        with repo_root_context(tmp_path):
            result = await _resolve_references(reference_materials, repo_root=tmp_path)

        assert result is not None
        assert len(result) == 1
        assert result[0]["resolved"] == {"resolved": True}

    async def test_unregistered_resolver_returns_error(self, tmp_path):
        """Entry with unregistered resolver name returns error in resolved."""
        reference_materials = [{"value": "spec", "resolver": "nonexistent_resolver"}]
        result = await _resolve_references(reference_materials, repo_root=tmp_path)

        assert result is not None
        assert len(result) == 1
        assert result[0]["resolved"]["status"] == "error"
        assert "unregistered resolver" in result[0]["resolved"]["error"]

    async def test_mixed_default_and_custom_resolvers(self, tmp_path, mock_global_bees_dir, monkeypatch):
        """Mix of default and custom resolver entries are each resolved correctly."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir(exist_ok=True)
        (tmp_path / "spec.md").touch()

        resolver_script = tmp_path / "custom.sh"
        resolver_script.write_text("#!/bin/bash\necho '\"custom-result\"'\n")
        resolver_script.chmod(0o755)

        from src.config import ResolverEntry, save_resolver_registry
        registry = {"custom": ResolverEntry(path=str(resolver_script), timeout=5)}
        save_resolver_registry(registry)

        reference_materials = [
            {"value": "spec.md"},                      # default resolver
            {"value": "input", "resolver": "custom"},  # custom resolver
        ]

        with repo_root_context(tmp_path):
            result = await _resolve_references(reference_materials, repo_root=tmp_path)

        assert result is not None
        assert len(result) == 2
        assert result[0]["resolved"]["status"] == "success"
        assert result[1]["resolved"] == "custom-result"


# ============================================================================
# _resolve_references — built-in resolvers (bees, github, file-path)
# ============================================================================


class TestResolveReferencesBuiltinResolvers:
    """Tests for _resolve_references dispatching to the new built-in resolvers.

    These tests verify the behavior AFTER the bug fix that added 'bees' and 'github'
    as built-in resolvers. Before the fix, both would return 'unregistered resolver'
    errors; after the fix they resolve correctly.
    """

    async def test_bees_resolver_returns_success(self, tmp_path):
        """resolver: 'bees' dispatches to resolve_bee — returns status=success with value."""
        reference_materials = [{"value": "b.abc", "resolver": "bees"}]
        result = await _resolve_references(reference_materials, repo_root=tmp_path)

        assert result is not None
        resolved = result[0]["resolved"]
        assert resolved["status"] == "success"
        assert resolved["value"] == "b.abc"

    async def test_file_path_resolver_explicit(self, tmp_path):
        """resolver: 'file-path' resolves existing file."""
        target = tmp_path / "doc.md"
        target.write_text("content")

        reference_materials = [{"value": str(target), "resolver": "file-path"}]
        result = await _resolve_references(reference_materials, repo_root=tmp_path)

        assert result is not None
        assert result[0]["resolved"]["status"] == "success"
        assert result[0]["resolved"]["resolved_path"] == str(target.resolve())

    async def test_no_resolver_key_uses_file_path(self, tmp_path):
        """Entry with no resolver key defaults to file-path behavior."""
        target = tmp_path / "readme.md"
        target.write_text("hello")

        reference_materials = [{"value": str(target)}]
        result = await _resolve_references(reference_materials, repo_root=tmp_path)

        assert result is not None
        assert result[0]["resolved"]["status"] == "success"

    async def test_github_resolver_dispatches(self, tmp_path):
        """resolver: 'github' dispatches to resolve_github (mocked gh CLI)."""
        def _gh_side_effect(*args, **kwargs):
            mock = MagicMock()
            mock.returncode = 0
            cmd = args[0]
            api_path = cmd[cmd.index("api") + 1]
            if "/comments" in api_path:
                mock.stdout = json.dumps(GITHUB_API_COMMENTS)
            else:
                mock.stdout = json.dumps(GITHUB_API_ISSUE)
            mock.stderr = ""
            return mock

        reference_materials = [{"value": GITHUB_ISSUE_URL, "resolver": "github"}]

        with patch("src.builtin_resolvers.shutil.which", return_value="/usr/bin/gh"):
            with patch("src.builtin_resolvers.subprocess.run", side_effect=_gh_side_effect):
                result = await _resolve_references(reference_materials, repo_root=tmp_path)

        assert result is not None
        resolved = result[0]["resolved"]
        assert resolved == {"issue": GITHUB_API_ISSUE, "comments": GITHUB_API_COMMENTS}

    async def test_github_resolver_gh_absent_returns_error(self, tmp_path):
        """resolver: 'github' with gh absent → error dict (not an exception)."""
        reference_materials = [{"value": GITHUB_ISSUE_URL, "resolver": "github"}]

        with patch("src.builtin_resolvers.shutil.which", return_value=None):
            result = await _resolve_references(reference_materials, repo_root=tmp_path)

        assert result is not None
        resolved = result[0]["resolved"]
        assert resolved["status"] == "error"
        assert resolved["raw_value"] == GITHUB_ISSUE_URL

    @pytest.mark.parametrize(
        "resolver_name",
        [
            pytest.param("bees", id="bees"),
            pytest.param("github", id="github"),
        ],
    )
    async def test_builtin_resolvers_not_treated_as_unregistered(self, tmp_path, resolver_name):
        """Built-in resolvers must NOT produce 'unregistered resolver' errors.

        This is the key regression test: before the fix, 'bees' and 'github'
        fell through to the unregistered-resolver branch and returned an error.
        After the fix they are dispatched to their built-in implementations.
        """
        # Use a valid bee ID for bees, a valid URL (but gh absent) for github
        value = "b.abc" if resolver_name == "bees" else GITHUB_ISSUE_URL
        reference_materials = [{"value": value, "resolver": resolver_name}]

        with patch("src.builtin_resolvers.shutil.which", return_value=None):
            result = await _resolve_references(reference_materials, repo_root=tmp_path)

        assert result is not None
        resolved = result[0]["resolved"]
        # The error must NOT be "unregistered resolver" — it is now dispatched
        assert not (
            resolved.get("status") == "error"
            and "unregistered resolver" in resolved.get("error", "")
        )
