"""Integration tests for the symmetric --body cap on create-ticket / update-ticket.

Covers Epic 5 of the chunked-ticket-body-API plan (Bee b.87r):
- Oversized --body on create-ticket is rejected by ``_reject_oversized_body_cli``
  before any ticket I/O. Stderr names the cap, the flag, and ``append-ticket-body``.
- Oversized --body on update-ticket is rejected the same way and the on-disk
  file remains byte-identical.
- At-cap (10000) and just-under-cap (9999) bodies still succeed on both surfaces.
- The ``args.body is None`` (create) and ``args.body is _UNSET`` (update) sentinel
  paths do NOT fire the helper.
- ``--body`` help text on both subcommands names ``append-ticket-body`` and
  ``10000`` so Claude can pick the right tool from the help signal.

This file lives in its own module (rather than being added to ``tests/test_cli.py``
which has unrelated pre-existing collection errors, or to Epic 4's
``tests/test_cli_append_ticket_body.py`` which is scoped to its own subcommand) so
each Epic of the plan owns a self-contained test surface.
"""

import json

import pytest

from src.constants import BODY_MAX_LENGTH
from src.paths import compute_ticket_path
from tests.helpers import run_cli_capture_both

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_test_hive(isolated_bees_env):
    isolated_bees_env.create_hive("test", "Test")
    isolated_bees_env.write_config()


def _create_bee(cli_runner, isolated_bees_env, body: str | None = None) -> str:
    _setup_test_hive(isolated_bees_env)
    argv = [
        "create-ticket",
        "--ticket-type",
        "bee",
        "--title",
        "Cap Target",
        "--hive",
        "test",
    ]
    if body is not None:
        argv += ["--body", body]
    stdout, exit_code = cli_runner(argv)
    assert exit_code == 0, f"create-ticket failed: {stdout}"
    return json.loads(stdout)["ticket_id"]


def _ticket_path(isolated_bees_env, ticket_id: str):
    hive_dir = isolated_bees_env.base_path / "test"
    return compute_ticket_path(ticket_id, hive_dir)


def _read_body_via_show(cli_runner, ticket_id: str) -> str:
    stdout, exit_code = cli_runner(["show-ticket", "--ids", ticket_id])
    assert exit_code == 0
    return json.loads(stdout)["tickets"][0]["body"]


# ---------------------------------------------------------------------------
# create-ticket --body cap
# ---------------------------------------------------------------------------


def test_create_ticket_body_oversized_rejected(cli_runner, isolated_bees_env, capsys):
    """SR-10.6 #15: 10001-char --body on create-ticket exits non-zero before any I/O."""
    _setup_test_hive(isolated_bees_env)
    # Drain capsys before the call we care about.
    capsys.readouterr()

    oversized = "x" * (BODY_MAX_LENGTH + 1)
    _stdout, stderr, exit_code = run_cli_capture_both(
        [
            "create-ticket",
            "--ticket-type",
            "bee",
            "--title",
            "Should Not Exist",
            "--hive",
            "test",
            "--body",
            oversized,
        ],
        capsys,
    )

    assert exit_code != 0
    assert "10000" in stderr
    assert "--body" in stderr
    assert "append-ticket-body" in stderr

    # No ticket file was created anywhere in the hive (excluding hive metadata).
    hive_dir = isolated_bees_env.base_path / "test"
    md_files = list(hive_dir.rglob("*.md"))
    assert md_files == [], f"unexpected ticket files written: {md_files}"


def test_create_ticket_body_at_cap_succeeds(cli_runner, isolated_bees_env):
    """A --body of exactly BODY_MAX_LENGTH (10000) characters is accepted."""
    body = "y" * BODY_MAX_LENGTH
    ticket_id = _create_bee(cli_runner, isolated_bees_env, body=body)
    assert _read_body_via_show(cli_runner, ticket_id) == body


def test_create_ticket_body_just_under_cap_succeeds(cli_runner, isolated_bees_env):
    """A --body of 9999 characters is accepted (just-under sanity)."""
    body = "z" * (BODY_MAX_LENGTH - 1)
    ticket_id = _create_bee(cli_runner, isolated_bees_env, body=body)
    assert _read_body_via_show(cli_runner, ticket_id) == body


def test_create_ticket_without_body_succeeds(cli_runner, isolated_bees_env):
    """When --body is omitted (args.body is None) the helper must NOT fire."""
    # Just calling _create_bee with body=None exercises the None-guard path.
    ticket_id = _create_bee(cli_runner, isolated_bees_env, body=None)
    assert ticket_id  # got a real ID back


# ---------------------------------------------------------------------------
# update-ticket --body cap
# ---------------------------------------------------------------------------


def test_update_ticket_body_oversized_rejected(cli_runner, isolated_bees_env, capsys):
    """SR-10.6 #16: 10001-char --body on update-ticket exits non-zero, .md unchanged."""
    ticket_id = _create_bee(cli_runner, isolated_bees_env, body="seed")
    path = _ticket_path(isolated_bees_env, ticket_id)
    snapshot = path.read_bytes()
    capsys.readouterr()

    oversized = "x" * (BODY_MAX_LENGTH + 1)
    _stdout, stderr, exit_code = run_cli_capture_both(
        ["update-ticket", "--ids", ticket_id, "--body", oversized],
        capsys,
    )

    assert exit_code != 0
    assert "10000" in stderr
    assert "--body" in stderr
    assert "append-ticket-body" in stderr

    # On-disk file is byte-identical to its pre-call snapshot.
    assert path.read_bytes() == snapshot


def test_update_ticket_body_at_cap_succeeds(cli_runner, isolated_bees_env):
    """A --body of exactly BODY_MAX_LENGTH (10000) characters is accepted."""
    ticket_id = _create_bee(cli_runner, isolated_bees_env, body="seed")
    new_body = "u" * BODY_MAX_LENGTH

    stdout, exit_code = cli_runner(
        ["update-ticket", "--ids", ticket_id, "--body", new_body]
    )
    assert exit_code == 0, f"update at cap failed: {stdout}"
    assert _read_body_via_show(cli_runner, ticket_id) == new_body


def test_update_ticket_without_body_does_not_fire_helper(cli_runner, isolated_bees_env):
    """When --body is omitted (args.body is _UNSET) the helper must NOT fire.

    Proves the sentinel guard works: an update touching only --add-tags must
    succeed without invoking ``_reject_oversized_body_cli`` at all.
    """
    ticket_id = _create_bee(cli_runner, isolated_bees_env, body="seed")

    stdout, exit_code = cli_runner(
        ["update-ticket", "--ids", ticket_id, "--add-tags", '["x"]']
    )
    assert exit_code == 0, f"update without --body failed: {stdout}"

    # Body is unchanged.
    assert _read_body_via_show(cli_runner, ticket_id) == "seed"


# ---------------------------------------------------------------------------
# Help-text nudges
# ---------------------------------------------------------------------------


def _normalize_help(text: str) -> str:
    """Collapse argparse's wrapped/hyphenated whitespace into a flat string.

    argparse wraps long help lines and re-flows on word boundaries. A literal
    substring like ``append-ticket-body`` may appear as
    ``append-ticket-\\n                        body``. Stitch hyphenated
    line-breaks back together, then collapse all remaining whitespace runs
    so substring assertions check semantic content, not layout.
    """
    import re

    rejoined = re.sub(r"-\s*\n\s*", "-", text)
    return " ".join(rejoined.split())


def test_create_ticket_help_text_mentions_append_subcommand_and_cap(cli_runner):
    """`bees create-ticket --help` --body line names append-ticket-body and 10000."""
    stdout, exit_code = cli_runner(["create-ticket", "--help"])
    # argparse --help exits 0
    assert exit_code == 0
    flat = _normalize_help(stdout)
    assert "append-ticket-body" in flat
    assert "10000" in flat


def test_update_ticket_help_text_mentions_append_subcommand_and_cap(cli_runner):
    """`bees update-ticket --help` --body line names append-ticket-body and 10000."""
    stdout, exit_code = cli_runner(["update-ticket", "--help"])
    assert exit_code == 0
    flat = _normalize_help(stdout)
    assert "append-ticket-body" in flat
    assert "10000" in flat
