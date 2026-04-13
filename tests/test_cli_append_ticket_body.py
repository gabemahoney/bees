"""Integration tests for the bees ``append-ticket-body`` CLI subcommand.

Covers Epic 4 of the chunked-ticket-body-API plan (Bee b.87r):
- Happy path append of a small chunk.
- At-cap (10000 char) chunk succeeds.
- Oversized (10001 char) chunk is rejected by ``_reject_oversized_body_cli``
  before any ticket I/O. Stderr names the cap and the subcommand. The
  ticket file on disk is byte-identical to its pre-call snapshot.
- Empty chunk is a success no-op.
- Bogus ``--ticket-id`` returns a structured ``ticket_not_found`` error.
- Direct unit test of ``_reject_oversized_body_cli``.

This file lives in its own module (rather than being added to
``tests/test_cli_commands.py``) so that Epic 5 can independently extend the
CLI surface without colliding on the same file. It deliberately avoids
``tests/test_cli.py``, which has unrelated pre-existing collection errors.
"""

import json

import pytest

from src.constants import BODY_MAX_LENGTH
from src.paths import compute_ticket_path

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

    stdout, exit_code = cli_runner(
        ["append-ticket-body", "--ticket-id", ticket_id, "--chunk", " world"]
    )

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

    stdout, exit_code = cli_runner(
        ["append-ticket-body", "--ticket-id", ticket_id, "--chunk", chunk]
    )

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

    stdout, exit_code = cli_runner(
        ["append-ticket-body", "--ticket-id", ticket_id, "--chunk", ""]
    )

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


def test_append_ticket_body_oversized_chunk_rejected(
    cli_runner, isolated_bees_env, capsys
):
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

    stdout, exit_code = cli_runner(
        ["append-ticket-body", "--ticket-id", "b.zzz", "--chunk", "anything"]
    )

    assert exit_code != 0
    result = json.loads(stdout)
    assert result["status"] == "error"
    assert result["error_type"] == "ticket_not_found"


def test_append_ticket_body_missing_required_flag(cli_runner):
    """argparse should bail out with exit code 2 when --chunk is missing."""
    stdout, exit_code = cli_runner(
        ["append-ticket-body", "--ticket-id", "b.zzz"]
    )
    assert exit_code == 2
    result = json.loads(stdout)
    assert result["status"] == "error"


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
