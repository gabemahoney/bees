"""Integration tests for the bees ``append-ticket-body`` CLI subcommand.

Covers Epic 4 of the chunked-ticket-body-API plan (Bee b.87r) and Epic 3 /
Task 1 (``t1.jsz.nb``) of Bee ``b.jsz``, which adds ``--chunk-file PATH``
as a sibling of ``--chunk`` inside a required mutually-exclusive group.

- Happy path append of a small inline chunk (``--chunk``).
- Happy path append from a UTF-8 file (``--chunk-file PATH``) and from
  stdin (``--chunk-file -``).
- At-cap (10000 char) chunk and at-cap file both succeed.
- Oversized (10001 char) chunk and oversized file are rejected by
  ``_reject_oversized_body_cli`` before any ticket I/O. Stderr names the
  cap, the subcommand, and the originating flag (``--chunk`` for inline,
  ``--chunk-file`` for file). The ticket file on disk is byte-identical
  to its pre-call snapshot.
- Empty inline chunk and empty ``--chunk-file`` are both success no-ops:
  ticket bytes are unchanged. NOTE: append + empty = concatenation
  (no-op) deliberately diverges from ``update-ticket --body-file`` whose
  empty-file case overwrites the body to empty.
- Mutex errors: passing both ``--chunk`` and ``--chunk-file``, or
  passing neither, exits with argparse code 2 and leaves the ticket
  byte-identical.
- ``--chunk-file`` missing-file and UTF-8-decode errors are rejected
  with diagnostic stderr and the ticket byte-identical.
- Bogus ``--ticket-id`` returns a structured ``ticket_not_found`` error.
- Direct unit test of ``_reject_oversized_body_cli``.

This file lives in its own module (rather than being added to
``tests/test_cli_commands.py``) so that Epic 5 can independently extend the
CLI surface without colliding on the same file. It deliberately avoids
``tests/test_cli.py``, which has unrelated pre-existing collection errors.
"""

import io
import json

import pytest

from src.constants import BODY_MAX_LENGTH
from src.paths import compute_ticket_path
from tests.helpers import make_body_at_cap, make_body_over_cap

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_bee_with_body(cli_runner, isolated_bees_env, body: str = "hello"):
    """Create a single bee in the 'test' hive with a known body. Returns ticket_id."""
    isolated_bees_env.create_hive("test", "Test")
    isolated_bees_env.write_config()
    stdout, exit_code = cli_runner(
        [
            "create-ticket",
            "--ticket-type",
            "bee",
            "--title",
            "Append Target",
            "--hive",
            "test",
            "--body",
            body,
        ]
    )
    assert exit_code == 0, f"create-ticket failed: {stdout}"
    return json.loads(stdout)["ticket_id"]


def _ticket_path(isolated_bees_env, ticket_id: str):
    hive_dir = isolated_bees_env.base_path / "test"
    return compute_ticket_path(ticket_id, hive_dir)


def _read_body_via_show(cli_runner, ticket_id: str) -> str:
    stdout, exit_code = cli_runner(["show-ticket", "--ids", ticket_id])
    assert exit_code == 0
    payload = json.loads(stdout)
    return payload["tickets"][0]["body"]


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_append_ticket_body_happy_path(cli_runner, isolated_bees_env):
    ticket_id = _create_bee_with_body(cli_runner, isolated_bees_env, body="hello")

    stdout, exit_code = cli_runner(["append-ticket-body", "--ticket-id", ticket_id, "--chunk", " world"])

    assert exit_code == 0, f"append failed: {stdout}"
    result = json.loads(stdout)
    assert result["status"] == "success"
    assert result["appended"] == [ticket_id]

    body = _read_body_via_show(cli_runner, ticket_id)
    assert body == "hello world"


def test_append_ticket_body_at_cap(cli_runner, isolated_bees_env):
    """A chunk exactly at BODY_MAX_LENGTH (10000 chars) is accepted."""
    ticket_id = _create_bee_with_body(cli_runner, isolated_bees_env, body="")
    chunk = "x" * BODY_MAX_LENGTH

    stdout, exit_code = cli_runner(["append-ticket-body", "--ticket-id", ticket_id, "--chunk", chunk])

    assert exit_code == 0, f"at-cap append failed: {stdout}"
    result = json.loads(stdout)
    assert result["status"] == "success"

    body = _read_body_via_show(cli_runner, ticket_id)
    assert body.endswith(chunk)
    assert len(body) >= BODY_MAX_LENGTH


def test_append_ticket_body_empty_chunk_noop(cli_runner, isolated_bees_env):
    """Empty chunk succeeds without modifying the ticket file."""
    ticket_id = _create_bee_with_body(cli_runner, isolated_bees_env, body="hello")
    path = _ticket_path(isolated_bees_env, ticket_id)
    snapshot = path.read_bytes()

    stdout, exit_code = cli_runner(["append-ticket-body", "--ticket-id", ticket_id, "--chunk", ""])

    assert exit_code == 0, f"empty-chunk append failed: {stdout}"
    result = json.loads(stdout)
    assert result["status"] == "success"

    assert path.read_bytes() == snapshot


def test_append_ticket_body_with_hive_hint(cli_runner, isolated_bees_env):
    """Optional --hive flag is accepted and the append still works."""
    ticket_id = _create_bee_with_body(cli_runner, isolated_bees_env, body="a")

    stdout, exit_code = cli_runner(
        [
            "append-ticket-body",
            "--ticket-id",
            ticket_id,
            "--chunk",
            "b",
            "--hive",
            "test",
        ]
    )

    assert exit_code == 0, f"append with --hive failed: {stdout}"
    body = _read_body_via_show(cli_runner, ticket_id)
    assert body == "ab"


# ---------------------------------------------------------------------------
# Happy paths — Epic 3 / t1.jsz.nb (--chunk-file)
# ---------------------------------------------------------------------------


def test_append_ticket_body_chunk_file_happy_path_file(cli_runner, isolated_bees_env, tmp_path):
    """``--chunk-file <path>`` reads UTF-8 (incl. non-ASCII) and appends it.

    Verifies the wired path: parser dispatches to ``_read_body_file_arg``,
    the cap check accepts the result, and the persisted body equals the
    pre-call body concatenated with the file content (no separator).
    """
    ticket_id = _create_bee_with_body(cli_runner, isolated_bees_env, body="seed")
    file_content = " world é"  # non-ASCII codepoint exercises UTF-8 decoding
    path = tmp_path / "chunk.txt"
    path.write_text(file_content, encoding="utf-8")

    stdout, exit_code = cli_runner(
        [
            "append-ticket-body",
            "--ticket-id",
            ticket_id,
            "--chunk-file",
            str(path),
        ]
    )

    assert exit_code == 0, f"file-append failed: {stdout}"
    result = json.loads(stdout)
    assert result["status"] == "success"
    assert result["appended"] == [ticket_id]

    body = _read_body_via_show(cli_runner, ticket_id)
    assert body == "seed" + file_content


def test_append_ticket_body_chunk_file_happy_path_stdin(cli_runner, isolated_bees_env, monkeypatch):
    """``--chunk-file -`` reads from sys.stdin via in-process patching.

    ``cli_runner`` invokes ``src.cli.main()`` IN-PROCESS (see
    ``tests/conftest.py:618-637``); it does NOT spawn a subprocess. Stdin
    must be patched on the live ``sys`` module — ``subprocess.run(input=...)``
    would never reach the in-process call.
    """
    ticket_id = _create_bee_with_body(cli_runner, isolated_bees_env, body="seed")
    monkeypatch.setattr("sys.stdin", io.StringIO("from-stdin"))

    stdout, exit_code = cli_runner(
        [
            "append-ticket-body",
            "--ticket-id",
            ticket_id,
            "--chunk-file",
            "-",
        ]
    )

    assert exit_code == 0, f"stdin-append failed: {stdout}"
    result = json.loads(stdout)
    assert result["status"] == "success"

    body = _read_body_via_show(cli_runner, ticket_id)
    assert body == "seed" + "from-stdin"


def test_append_ticket_body_chunk_file_at_cap(cli_runner, isolated_bees_env, tmp_path):
    """A file with exactly ``BODY_MAX_LENGTH`` characters appends successfully.

    Mirrors the inline ``test_append_ticket_body_at_cap`` boundary; the cap
    check uses the same helper but with ``arg_name="--chunk-file"``.
    """
    ticket_id = _create_bee_with_body(cli_runner, isolated_bees_env, body="")
    file_content = make_body_at_cap()
    path = tmp_path / "atcap.txt"
    path.write_text(file_content, encoding="utf-8")

    stdout, exit_code = cli_runner(
        [
            "append-ticket-body",
            "--ticket-id",
            ticket_id,
            "--chunk-file",
            str(path),
        ]
    )

    assert exit_code == 0, f"at-cap file append failed: {stdout}"
    body = _read_body_via_show(cli_runner, ticket_id)
    assert body == file_content


def test_append_ticket_body_chunk_file_empty_file_noop(cli_runner, isolated_bees_env, tmp_path):
    """An empty ``--chunk-file`` is a no-op: ticket bytes are unchanged.

    LOCKED semantic. Append + empty = concatenation, which is identity.
    Diverges deliberately from ``update-ticket --body-file <empty>``
    (which overwrites the body to empty).
    """
    ticket_id = _create_bee_with_body(cli_runner, isolated_bees_env, body="hello")
    snapshot = _ticket_path(isolated_bees_env, ticket_id).read_bytes()
    path = tmp_path / "empty.txt"
    path.write_bytes(b"")

    stdout, exit_code = cli_runner(
        [
            "append-ticket-body",
            "--ticket-id",
            ticket_id,
            "--chunk-file",
            str(path),
        ]
    )

    assert exit_code == 0, f"empty-file append failed: {stdout}"
    result = json.loads(stdout)
    assert result["status"] == "success"

    assert _ticket_path(isolated_bees_env, ticket_id).read_bytes() == snapshot


# ---------------------------------------------------------------------------
# Rejection / error paths
# ---------------------------------------------------------------------------


def _run_cli_capture_both(argv, capsys):
    """Invoke src.cli.main() with given argv. Returns (stdout, stderr, exit_code).

    Mirrors the conftest ``cli_runner`` fixture but also returns stderr,
    which the shared fixture discards. Needed for asserting on rejection
    messages that the helper writes to stderr.
    """
    import sys
    from unittest.mock import patch

    from src.cli import main

    with patch.object(sys, "argv", ["bees", *argv]):
        try:
            main()
            exit_code = 0
        except SystemExit as exc:
            exit_code = exc.code if exc.code is not None else 0

    captured = capsys.readouterr()
    return captured.out.strip(), captured.err, exit_code


def test_append_ticket_body_oversized_chunk_rejected(cli_runner, isolated_bees_env, capsys):
    """A chunk one byte over the cap is rejected before any ticket I/O.

    SR-10.6 #17: stderr must mention the cap and the subcommand, and the
    target ``.md`` file must be byte-identical to its pre-call snapshot.
    """
    ticket_id = _create_bee_with_body(cli_runner, isolated_bees_env, body="hello")
    path = _ticket_path(isolated_bees_env, ticket_id)
    snapshot = path.read_bytes()
    # Drain capsys so the next assertions see only the rejection output.
    capsys.readouterr()

    oversized = "x" * (BODY_MAX_LENGTH + 1)
    _stdout, stderr, exit_code = _run_cli_capture_both(
        ["append-ticket-body", "--ticket-id", ticket_id, "--chunk", oversized],
        capsys,
    )

    assert exit_code != 0
    assert "10000" in stderr
    assert "append-ticket-body" in stderr
    assert "--chunk" in stderr

    # The on-disk file must be byte-identical (no read, no write).
    assert path.read_bytes() == snapshot


def test_append_ticket_body_not_found(cli_runner, isolated_bees_env):
    """A bogus --ticket-id returns a structured ticket_not_found error."""
    isolated_bees_env.create_hive("test", "Test")
    isolated_bees_env.write_config()

    stdout, exit_code = cli_runner(["append-ticket-body", "--ticket-id", "b.zzz", "--chunk", "anything"])

    assert exit_code != 0
    result = json.loads(stdout)
    assert result["status"] == "error"
    assert result["error_type"] == "ticket_not_found"


def test_append_ticket_body_missing_required_chunk_or_chunk_file(cli_runner):
    """argparse should bail out with exit code 2 when NEITHER ``--chunk`` nor
    ``--chunk-file`` is supplied (the mutex group is required at group level).
    """
    stdout, exit_code = cli_runner(["append-ticket-body", "--ticket-id", "b.zzz"])
    assert exit_code == 2
    result = json.loads(stdout)
    assert result["status"] == "error"


def test_append_ticket_body_help_text_mentions_chunk_file_stdin_and_cap(cli_runner):
    """`bees append-ticket-body --help` advertises --chunk-file with stdin and the cap (AC #8)."""
    import re

    stdout, exit_code = cli_runner(["append-ticket-body", "--help"])
    assert exit_code == 0
    rejoined = re.sub(r"-\s*\n\s*", "-", stdout)
    flat = " ".join(rejoined.split())
    assert "--chunk-file" in flat
    assert "'-'" in flat
    assert "10000" in flat


# ---------------------------------------------------------------------------
# Rejection / error paths — Epic 3 / t1.jsz.nb (--chunk-file)
# ---------------------------------------------------------------------------


def test_append_ticket_body_chunk_file_mutex_with_chunk_rejected(cli_runner, isolated_bees_env, tmp_path, capsys):
    """``--chunk`` and ``--chunk-file`` are mutually exclusive (argparse exit 2).

    The file is written so the failure is unambiguously the mutex (not a
    missing-file error from ``_read_body_file_arg``).
    """
    ticket_id = _create_bee_with_body(cli_runner, isolated_bees_env, body="hello")
    path = tmp_path / "chunk.txt"
    path.write_text("file content", encoding="utf-8")
    snapshot = _ticket_path(isolated_bees_env, ticket_id).read_bytes()
    capsys.readouterr()

    _stdout, _stderr, exit_code = _run_cli_capture_both(
        [
            "append-ticket-body",
            "--ticket-id",
            ticket_id,
            "--chunk",
            "inline",
            "--chunk-file",
            str(path),
        ],
        capsys,
    )

    assert exit_code == 2
    assert _ticket_path(isolated_bees_env, ticket_id).read_bytes() == snapshot


def test_append_ticket_body_chunk_file_mutex_neither_rejected(cli_runner, isolated_bees_env, capsys):
    """Passing NEITHER ``--chunk`` nor ``--chunk-file`` exits 2 with a message
    naming both flags. Argparse-default for a required mutex group when
    nothing in the group is supplied; complement to the "both flags" mutex
    case above.

    NOTE: ``BeesArgumentParser.error`` (``src/cli.py:52-58``) routes the
    argparse error message to STDOUT as a JSON ``{"status": "error",
    "message": ...}`` payload, then exits 2. The substring assertions
    therefore target stdout, not stderr.
    """
    ticket_id = _create_bee_with_body(cli_runner, isolated_bees_env, body="hello")
    snapshot = _ticket_path(isolated_bees_env, ticket_id).read_bytes()
    capsys.readouterr()

    stdout, _stderr, exit_code = _run_cli_capture_both(
        ["append-ticket-body", "--ticket-id", ticket_id, "--hive", "test"],
        capsys,
    )

    assert exit_code == 2
    # Loose substring check across Python versions — argparse wording may
    # change but both flag names should always appear in the error message.
    assert "--chunk" in stdout
    assert "--chunk-file" in stdout
    assert _ticket_path(isolated_bees_env, ticket_id).read_bytes() == snapshot


def test_append_ticket_body_chunk_file_missing_file_rejected(cli_runner, isolated_bees_env, tmp_path, capsys):
    """A missing ``--chunk-file`` path names both the path and the flag.

    Helper-level error (``_read_body_file_arg``); ticket bytes unchanged.
    """
    ticket_id = _create_bee_with_body(cli_runner, isolated_bees_env, body="hello")
    snapshot = _ticket_path(isolated_bees_env, ticket_id).read_bytes()
    capsys.readouterr()

    missing = tmp_path / "does_not_exist.txt"
    _stdout, stderr, exit_code = _run_cli_capture_both(
        [
            "append-ticket-body",
            "--ticket-id",
            ticket_id,
            "--chunk-file",
            str(missing),
        ],
        capsys,
    )

    assert exit_code != 0
    assert str(missing) in stderr
    assert "--chunk-file" in stderr
    assert _ticket_path(isolated_bees_env, ticket_id).read_bytes() == snapshot


def test_append_ticket_body_chunk_file_decode_error_rejected(cli_runner, isolated_bees_env, tmp_path, capsys):
    """Invalid UTF-8 in ``--chunk-file`` exits non-zero with a UTF-8 diagnostic.

    Helper-level error (``_read_body_file_arg``); ticket bytes unchanged.
    """
    ticket_id = _create_bee_with_body(cli_runner, isolated_bees_env, body="hello")
    snapshot = _ticket_path(isolated_bees_env, ticket_id).read_bytes()
    capsys.readouterr()

    path = tmp_path / "bad_utf8.bin"
    # 0xff is never a valid UTF-8 start byte.
    path.write_bytes(b"\xff\xfe")

    _stdout, stderr, exit_code = _run_cli_capture_both(
        [
            "append-ticket-body",
            "--ticket-id",
            ticket_id,
            "--chunk-file",
            str(path),
        ],
        capsys,
    )

    assert exit_code != 0
    assert "UTF-8" in stderr
    assert "decode" in stderr.lower()
    assert _ticket_path(isolated_bees_env, ticket_id).read_bytes() == snapshot


def test_append_ticket_body_chunk_file_oversized_rejected(cli_runner, isolated_bees_env, tmp_path, capsys):
    """An oversized ``--chunk-file`` is rejected with stderr naming the cap,
    the subcommand, and ``--chunk-file`` as a standalone token.

    The cap-check ``arg_name`` parameterization is what surfaces
    ``--chunk-file`` (rather than ``--chunk``) in the error. Asserting the
    flag as a standalone token (split by whitespace) prevents accidental
    pass-through of a loose substring match (the existing
    ``test_append_ticket_body_oversized_chunk_rejected`` exercises the
    ``--chunk`` path and remains unchanged).
    """
    ticket_id = _create_bee_with_body(cli_runner, isolated_bees_env, body="hello")
    snapshot = _ticket_path(isolated_bees_env, ticket_id).read_bytes()
    capsys.readouterr()

    path = tmp_path / "oversized.txt"
    path.write_text(make_body_over_cap(), encoding="utf-8")

    _stdout, stderr, exit_code = _run_cli_capture_both(
        [
            "append-ticket-body",
            "--ticket-id",
            ticket_id,
            "--chunk-file",
            str(path),
        ],
        capsys,
    )

    assert exit_code != 0
    assert "10000" in stderr
    assert str(BODY_MAX_LENGTH + 1) in stderr
    assert "append-ticket-body" in stderr
    assert "--chunk-file" in stderr.split()
    assert _ticket_path(isolated_bees_env, ticket_id).read_bytes() == snapshot


# ---------------------------------------------------------------------------
# Direct unit test of the shared helper
# ---------------------------------------------------------------------------


def test_reject_oversized_body_cli_under_cap_returns_none(capsys):
    from src.cli import _reject_oversized_body_cli

    # Should return without raising and without writing to stderr.
    result = _reject_oversized_body_cli("--chunk", "x" * BODY_MAX_LENGTH)
    assert result is None
    captured = capsys.readouterr()
    assert captured.err == ""


def test_reject_oversized_body_cli_over_cap_exits_nonzero(capsys):
    from src.cli import _reject_oversized_body_cli

    with pytest.raises(SystemExit) as excinfo:
        _reject_oversized_body_cli("--body", "x" * (BODY_MAX_LENGTH + 1))

    assert excinfo.value.code != 0
    captured = capsys.readouterr()
    assert "10000" in captured.err
    assert "append-ticket-body" in captured.err
    assert "--body" in captured.err
    assert str(BODY_MAX_LENGTH + 1) in captured.err
