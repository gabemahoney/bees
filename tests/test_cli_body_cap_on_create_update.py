"""Integration tests for the --body cap on create-ticket / update-ticket.

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

Also covers Epic 1 / Task 2 of the ``--body-file`` / ``--chunk-file`` feature
(Bee ``b.jsz``, plan ``t1.jsz.de``):
- ``create-ticket --body-file PATH`` reads UTF-8 file contents (or stdin when
  ``PATH == "-"``). The BODY_MAX_LENGTH cap does NOT apply to file-sourced
  content — only inline ``--body`` values are capped.
- ``--body`` and ``--body-file`` are mutually exclusive (argparse mutex group).
- File-surface error paths (missing file, UTF-8 decode error) exit non-zero,
  write a stderr diagnostic, and write no ticket files. Oversized files succeed.

Also covers Epic 2 of the same feature (Bee ``b.jsz``, plan ``t1.jsz.sh``):
- ``update-ticket --body-file PATH`` mirrors create-ticket's wiring on the
  update surface: UTF-8 file contents (or stdin when ``PATH == "-"``) are
  read without a size cap.
- ``--body`` and ``--body-file`` are mutually exclusive on update-ticket
  (argparse mutex group).
- The ``args.body is _UNSET`` sentinel-skip path (no ``--body`` and no
  ``--body-file``) survives the parser restructure into a mutex group: see
  the load-bearing ``test_update_ticket_without_body_does_not_fire_helper``
  regression guard below.

This file lives in its own module (rather than being added to ``tests/test_cli.py``
which has unrelated pre-existing collection errors, or to Epic 4's
``tests/test_cli_append_ticket_body.py`` which is scoped to its own subcommand) so
each Epic of the plan owns a self-contained test surface.
"""

import io
import json

from src.constants import BODY_MAX_LENGTH
from src.paths import compute_ticket_path
from tests.helpers import make_body_at_cap, make_body_over_cap, run_cli_capture_both

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

    stdout, exit_code = cli_runner(["update-ticket", "--ids", ticket_id, "--body", new_body])
    assert exit_code == 0, f"update at cap failed: {stdout}"
    assert _read_body_via_show(cli_runner, ticket_id) == new_body


def test_update_ticket_without_body_does_not_fire_helper(cli_runner, isolated_bees_env):
    """When --body is omitted (args.body is _UNSET) the helper must NOT fire.

    Proves the sentinel guard works: an update touching only --add-tags must
    succeed without invoking ``_reject_oversized_body_cli`` at all.
    """
    ticket_id = _create_bee(cli_runner, isolated_bees_env, body="seed")

    stdout, exit_code = cli_runner(["update-ticket", "--ids", ticket_id, "--add-tags", '["x"]'])
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


def test_create_ticket_help_text_mentions_body_file_and_stdin(cli_runner):
    """`bees create-ticket --help` advertises --body-file with stdin and no-cap note."""
    stdout, exit_code = cli_runner(["create-ticket", "--help"])
    assert exit_code == 0
    flat = _normalize_help(stdout)
    assert "--body-file" in flat
    assert "'-'" in flat
    # File-sourced content has no cap — the help text must NOT claim a 10000 limit
    # for --body-file (the 10000 mention in the flat output comes only from --body).
    assert "No size cap" in flat or "no size cap" in flat.lower()


def test_update_ticket_help_text_mentions_body_file_and_stdin(cli_runner):
    """`bees update-ticket --help` advertises --body-file with stdin and no-cap note."""
    stdout, exit_code = cli_runner(["update-ticket", "--help"])
    assert exit_code == 0
    flat = _normalize_help(stdout)
    assert "--body-file" in flat
    assert "'-'" in flat
    assert "No size cap" in flat or "no size cap" in flat.lower()


# ---------------------------------------------------------------------------
# create-ticket --body-file happy paths (Epic 1 / t1.jsz.de)
# ---------------------------------------------------------------------------


def _create_bee_with_body_file(cli_runner, isolated_bees_env, body_file_arg: str) -> str:
    """Run ``create-ticket --body-file <body_file_arg>`` and return the ticket id."""
    _setup_test_hive(isolated_bees_env)
    stdout, exit_code = cli_runner(
        [
            "create-ticket",
            "--ticket-type",
            "bee",
            "--title",
            "Cap Target",
            "--hive",
            "test",
            "--body-file",
            body_file_arg,
        ]
    )
    assert exit_code == 0, f"create-ticket --body-file failed: {stdout}"
    return json.loads(stdout)["ticket_id"]


def test_create_ticket_body_file_happy_path_file(cli_runner, isolated_bees_env, tmp_path):
    """A UTF-8 file with non-ASCII content round-trips through --body-file."""
    body = "hello ☃ world"  # snowman exercises non-ASCII UTF-8 decoding.
    path = tmp_path / "input.md"
    path.write_text(body, encoding="utf-8")

    ticket_id = _create_bee_with_body_file(cli_runner, isolated_bees_env, str(path))

    assert _read_body_via_show(cli_runner, ticket_id) == body


def test_create_ticket_body_file_stdin_happy_path(cli_runner, isolated_bees_env, monkeypatch):
    """``--body-file -`` reads from sys.stdin via in-process patching.

    ``cli_runner`` invokes ``src.cli.main()`` IN-PROCESS (see
    ``tests/conftest.py:618-637``); it does NOT spawn a subprocess. Stdin
    must be patched on the live ``sys`` module — ``subprocess.run(input=...)``
    would never reach the in-process call.
    """
    body = "from-stdin\nbody é"
    monkeypatch.setattr("sys.stdin", io.StringIO(body))

    ticket_id = _create_bee_with_body_file(cli_runner, isolated_bees_env, "-")

    assert _read_body_via_show(cli_runner, ticket_id) == body


def test_create_ticket_body_file_at_cap_succeeds(cli_runner, isolated_bees_env, tmp_path):
    """A file with exactly BODY_MAX_LENGTH characters is accepted via --body-file."""
    body = make_body_at_cap()
    path = tmp_path / "atcap.md"
    path.write_text(body, encoding="utf-8")

    ticket_id = _create_bee_with_body_file(cli_runner, isolated_bees_env, str(path))

    assert _read_body_via_show(cli_runner, ticket_id) == body


def test_create_ticket_body_file_empty_succeeds(cli_runner, isolated_bees_env, tmp_path):
    """An empty --body-file produces a ticket with an empty body."""
    path = tmp_path / "empty.md"
    path.write_bytes(b"")

    ticket_id = _create_bee_with_body_file(cli_runner, isolated_bees_env, str(path))

    assert _read_body_via_show(cli_runner, ticket_id) == ""


# ---------------------------------------------------------------------------
# create-ticket --body-file error paths (Epic 1 / t1.jsz.de)
# ---------------------------------------------------------------------------


def test_create_ticket_body_file_mutex_with_body_rejected(cli_runner, isolated_bees_env, tmp_path, capsys):
    """``--body`` and ``--body-file`` are mutually exclusive (argparse default)."""
    _setup_test_hive(isolated_bees_env)
    capsys.readouterr()

    # File must exist so the failure is unambiguously the mutex, not a
    # missing-file error from ``_read_body_file_arg``.
    path = tmp_path / "input.md"
    path.write_text("file content", encoding="utf-8")

    _stdout, _stderr, exit_code = run_cli_capture_both(
        [
            "create-ticket",
            "--ticket-type",
            "bee",
            "--title",
            "Should Not Exist",
            "--hive",
            "test",
            "--body",
            "inline content",
            "--body-file",
            str(path),
        ],
        capsys,
    )

    # argparse mutex violations exit with code 2.
    assert exit_code == 2

    hive_dir = isolated_bees_env.base_path / "test"
    md_files = list(hive_dir.rglob("*.md"))
    assert md_files == [], f"unexpected ticket files written: {md_files}"


def test_create_ticket_body_file_missing_file_rejected(cli_runner, isolated_bees_env, tmp_path, capsys):
    """A missing --body-file path names both the path and the flag in stderr."""
    _setup_test_hive(isolated_bees_env)
    capsys.readouterr()

    missing = tmp_path / "does_not_exist.md"

    _stdout, stderr, exit_code = run_cli_capture_both(
        [
            "create-ticket",
            "--ticket-type",
            "bee",
            "--title",
            "Should Not Exist",
            "--hive",
            "test",
            "--body-file",
            str(missing),
        ],
        capsys,
    )

    assert exit_code != 0
    assert str(missing) in stderr
    assert "--body-file" in stderr

    hive_dir = isolated_bees_env.base_path / "test"
    md_files = list(hive_dir.rglob("*.md"))
    assert md_files == [], f"unexpected ticket files written: {md_files}"


def test_create_ticket_body_file_decode_error_rejected(cli_runner, isolated_bees_env, tmp_path, capsys):
    """Invalid UTF-8 in --body-file exits non-zero with a UTF-8/decoding diagnostic."""
    _setup_test_hive(isolated_bees_env)
    capsys.readouterr()

    path = tmp_path / "bad_utf8.bin"
    # 0xff is never a valid UTF-8 start byte.
    path.write_bytes(b"\xff\xfe")

    _stdout, stderr, exit_code = run_cli_capture_both(
        [
            "create-ticket",
            "--ticket-type",
            "bee",
            "--title",
            "Should Not Exist",
            "--hive",
            "test",
            "--body-file",
            str(path),
        ],
        capsys,
    )

    assert exit_code != 0
    assert "UTF-8" in stderr
    assert "decode" in stderr.lower()
    assert "--body-file" in stderr

    hive_dir = isolated_bees_env.base_path / "test"
    md_files = list(hive_dir.rglob("*.md"))
    assert md_files == [], f"unexpected ticket files written: {md_files}"


def test_create_ticket_body_file_oversized_succeeds(cli_runner, isolated_bees_env, tmp_path):
    """A file larger than BODY_MAX_LENGTH is accepted via --body-file.

    The BODY_MAX_LENGTH cap applies only to inline --body values. File-sourced
    content goes through a direct filesystem read with no size constraint.
    """
    _setup_test_hive(isolated_bees_env)

    body = make_body_over_cap()
    path = tmp_path / "big.md"
    path.write_text(body, encoding="utf-8")

    ticket_id = _create_bee_with_body_file(cli_runner, isolated_bees_env, str(path))

    assert _read_body_via_show(cli_runner, ticket_id) == body


# ---------------------------------------------------------------------------
# update-ticket --body-file happy paths (Epic 2 / t1.jsz.sh)
# ---------------------------------------------------------------------------


def test_update_ticket_body_file_happy_path_file(cli_runner, isolated_bees_env, tmp_path):
    """A UTF-8 file with non-ASCII content round-trips through update --body-file."""
    ticket_id = _create_bee(cli_runner, isolated_bees_env, body="seed")
    new_body = "updated ☃ body"  # snowman exercises non-ASCII UTF-8 decoding.
    path = tmp_path / "input.md"
    path.write_text(new_body, encoding="utf-8")

    stdout, exit_code = cli_runner(["update-ticket", "--ids", ticket_id, "--body-file", str(path)])
    assert exit_code == 0, f"update --body-file failed: {stdout}"
    assert _read_body_via_show(cli_runner, ticket_id) == new_body


def test_update_ticket_body_file_stdin_happy_path(cli_runner, isolated_bees_env, monkeypatch):
    """``update-ticket --body-file -`` reads from sys.stdin via in-process patching.

    ``cli_runner`` invokes ``src.cli.main()`` IN-PROCESS (see
    ``tests/conftest.py:618-637``); it does NOT spawn a subprocess. Stdin
    must be patched on the live ``sys`` module — ``subprocess.run(input=...)``
    would never reach the in-process call.
    """
    ticket_id = _create_bee(cli_runner, isolated_bees_env, body="seed")
    new_body = "from-stdin\nupdate é"
    monkeypatch.setattr("sys.stdin", io.StringIO(new_body))

    stdout, exit_code = cli_runner(["update-ticket", "--ids", ticket_id, "--body-file", "-"])
    assert exit_code == 0, f"update --body-file - failed: {stdout}"
    assert _read_body_via_show(cli_runner, ticket_id) == new_body


def test_update_ticket_body_file_at_cap_succeeds(cli_runner, isolated_bees_env, tmp_path):
    """A file with exactly BODY_MAX_LENGTH characters is accepted via update --body-file."""
    ticket_id = _create_bee(cli_runner, isolated_bees_env, body="seed")
    new_body = make_body_at_cap()
    path = tmp_path / "atcap.md"
    path.write_text(new_body, encoding="utf-8")

    stdout, exit_code = cli_runner(["update-ticket", "--ids", ticket_id, "--body-file", str(path)])
    assert exit_code == 0, f"update --body-file at cap failed: {stdout}"
    assert _read_body_via_show(cli_runner, ticket_id) == new_body


def test_update_ticket_body_file_empty_succeeds(cli_runner, isolated_bees_env, tmp_path):
    """An empty --body-file overwrites the target body to the empty string.

    LOCKED SEMANTIC: empty file is an *explicit overwrite to empty*, NOT a
    no-op. The helper returns ``""``; the handler then sets ``args.body =
    ""`` and (since ``"" is not _UNSET`` and ``"" is not None``) writes
    ``body=""`` into the update kwargs. This mirrors ``--body ""`` exactly.
    """
    ticket_id = _create_bee(cli_runner, isolated_bees_env, body="seed")
    # Sanity: pre-call body is "seed" (so the assertion below is a real change).
    assert _read_body_via_show(cli_runner, ticket_id) == "seed"

    path = tmp_path / "empty.md"
    path.write_bytes(b"")

    stdout, exit_code = cli_runner(["update-ticket", "--ids", ticket_id, "--body-file", str(path)])
    assert exit_code == 0, f"update --body-file empty failed: {stdout}"
    assert _read_body_via_show(cli_runner, ticket_id) == ""


# ---------------------------------------------------------------------------
# update-ticket --body-file error paths (Epic 2 / t1.jsz.sh)
# ---------------------------------------------------------------------------


def test_update_ticket_body_file_mutex_with_body_rejected(cli_runner, isolated_bees_env, tmp_path, capsys):
    """``--body`` and ``--body-file`` are mutually exclusive on update-ticket.

    Argparse mutex violations exit with code 2 specifically (distinct from
    the ``exit_code != 0`` shape of the missing/decode/oversized cases).
    The on-disk ticket must be byte-identical to its pre-call snapshot.
    """
    ticket_id = _create_bee(cli_runner, isolated_bees_env, body="seed")
    path_obj = _ticket_path(isolated_bees_env, ticket_id)
    snapshot = path_obj.read_bytes()
    capsys.readouterr()

    # File MUST exist so the failure is unambiguously the mutex, not a
    # missing-file error from ``_read_body_file_arg``.
    body_file = tmp_path / "input.md"
    body_file.write_text("file content", encoding="utf-8")

    _stdout, _stderr, exit_code = run_cli_capture_both(
        [
            "update-ticket",
            "--ids",
            ticket_id,
            "--body",
            "inline content",
            "--body-file",
            str(body_file),
        ],
        capsys,
    )

    assert exit_code == 2
    assert path_obj.read_bytes() == snapshot


def _seed_and_snapshot(cli_runner, isolated_bees_env, capsys):
    """Create a seeded ticket, snapshot its on-disk bytes, and drain capsys.

    Shared setup for the three byte-identity error tests (missing / decode /
    oversized). Returns ``(ticket_id, on_disk_path, snapshot_bytes)``.
    """
    ticket_id = _create_bee(cli_runner, isolated_bees_env, body="seed")
    on_disk = _ticket_path(isolated_bees_env, ticket_id)
    snapshot = on_disk.read_bytes()
    capsys.readouterr()
    return ticket_id, on_disk, snapshot


def test_update_ticket_body_file_missing_file_rejected(cli_runner, isolated_bees_env, tmp_path, capsys):
    """A missing --body-file path names both the path and the flag in stderr."""
    ticket_id, on_disk, snapshot = _seed_and_snapshot(cli_runner, isolated_bees_env, capsys)

    missing = tmp_path / "does_not_exist.md"

    _stdout, stderr, exit_code = run_cli_capture_both(
        ["update-ticket", "--ids", ticket_id, "--body-file", str(missing)],
        capsys,
    )

    assert exit_code != 0
    assert str(missing) in stderr
    assert "--body-file" in stderr

    assert on_disk.read_bytes() == snapshot


def test_update_ticket_body_file_decode_error_rejected(cli_runner, isolated_bees_env, tmp_path, capsys):
    """Invalid UTF-8 in update --body-file exits non-zero with a decode diagnostic."""
    ticket_id, on_disk, snapshot = _seed_and_snapshot(cli_runner, isolated_bees_env, capsys)

    bad = tmp_path / "bad_utf8.bin"
    # 0xff is never a valid UTF-8 start byte.
    bad.write_bytes(b"\xff\xfe")

    _stdout, stderr, exit_code = run_cli_capture_both(
        ["update-ticket", "--ids", ticket_id, "--body-file", str(bad)],
        capsys,
    )

    assert exit_code != 0
    assert "UTF-8" in stderr
    assert "decode" in stderr.lower()
    assert "--body-file" in stderr

    assert on_disk.read_bytes() == snapshot


def test_update_ticket_body_file_oversized_succeeds(cli_runner, isolated_bees_env, tmp_path):
    """A file larger than BODY_MAX_LENGTH is accepted via update --body-file.

    The BODY_MAX_LENGTH cap applies only to inline --body values. File-sourced
    content goes through a direct filesystem read with no size constraint.
    """
    ticket_id = _create_bee(cli_runner, isolated_bees_env, body="seed")
    new_body = make_body_over_cap()
    path = tmp_path / "big.md"
    path.write_text(new_body, encoding="utf-8")

    stdout, exit_code = cli_runner(["update-ticket", "--ids", ticket_id, "--body-file", str(path)])
    assert exit_code == 0, f"update --body-file oversized failed: {stdout}"
    assert _read_body_via_show(cli_runner, ticket_id) == new_body
