"""Regression tests for b.va7 and b.pp8: file-sourced ticket bodies are stored verbatim.

Every body-from-file path must store the file's text exactly, with no escape
interpretation (b.va7: the two-character sequences backslash+n / backslash+t
stay as written) and no whitespace trimming (b.pp8: leading whitespace and
trailing newlines are kept, so appended chunks that end in a newline stay on
their own lines). Paths covered, each for create, update and append:

- CLI ``--body-file PATH`` / ``--chunk-file PATH`` and their ``-`` (stdin) form.
- MCP ``body_file`` / ``chunk_file`` (the tool functions in ``src/mcp_server.py``).

Inline ``--body`` / ``--chunk`` (CLI) and ``body`` / ``chunk`` (MCP) still
expand backslash+n / backslash+t on purpose, to undo LLM JSON double-escaping.
``test_inline_body_still_expands_escapes`` pins that for all three operations
on both surfaces; core-level inline expansion on create/update is covered by
``TestSanitizeEscapeSequencesVia*`` in ``test_mcp_ticket_ops.py``.

The parser-level round trip of whitespace-edge bodies is in ``test_reader.py``,
as is the one exception to "verbatim": CR line endings read back as LF
(``test_cr_line_endings_read_back_as_lf``).
"""

import io

import pytest

from src.mcp_server import append_ticket_body, create_ticket, show_ticket, update_ticket
from src.paths import compute_ticket_path
from src.reader import read_ticket
from tests.helpers import cli_success, mcp_success
from tests.test_constants import HIVE_BACKEND

_HIVE = HIVE_BACKEND  # the hive conftest's hive_env registers

# In these Python literals "\\n" is the two characters backslash + n and
# "\\\\" is two backslashes. Each body is corrupted by escape expansion.
_BACKSLASH_N = "printf '%s\\n' \"$x\""
_BACKSLASH_T = "cut -d'\\t' -f1 data.tsv"
_DOUBLE_BACKSLASH = 'path = "C:\\\\new\\\\tmp"'
_TRAILING_BACKSLASH = "printf 'a\\tb\\n' \\"  # last character is a backslash

# The b.pp8 report's body file: ends in a newline, with a literal backslash+t.
_REPORTED_BODY = "line one\nliteral \\t here\n"

_FILE_BODIES = [
    pytest.param(_BACKSLASH_N, id="backslash_n"),
    pytest.param(_BACKSLASH_T, id="backslash_t"),
    pytest.param(_DOUBLE_BACKSLASH, id="double_backslash"),
    pytest.param(_TRAILING_BACKSLASH, id="trailing_backslash"),
    pytest.param(
        "\n".join([_BACKSLASH_N, _BACKSLASH_T, _DOUBLE_BACKSLASH, _TRAILING_BACKSLASH]),
        id="all_four",
    ),
    pytest.param(_REPORTED_BODY, id="one_trailing_newline"),
    pytest.param("x\n\n\n", id="three_trailing_newlines"),
    pytest.param("\n  \tleading whitespace", id="leading_whitespace"),
]

_SOURCES = [
    pytest.param("cli", False, id="cli_file"),
    pytest.param("cli", True, id="cli_stdin"),
    pytest.param("mcp", False, id="mcp_file"),
]


def _cli_create(cli_runner, *body_args):
    argv = ["create-ticket", "--ticket-type", "bee", "--title", "Verbatim", "--hive", _HIVE, *body_args]
    return cli_success(cli_runner, *argv)["ticket_id"]


def _write(op, via, value, cli_runner, *, from_file, ticket_id=None):
    """Write ``value`` through one body path and return the ticket ID.

    ``value`` is the file path (``from_file``) or the inline text. Without
    ``ticket_id``, update overwrites a new "seed" body and append extends a new
    empty body, so in every case the stored body is exactly the written text.
    """
    noun = "chunk" if op == "append" else "body"
    tid = ticket_id
    if tid is None and op == "update":
        tid = _cli_create(cli_runner, "--body", "seed")
    elif tid is None and op == "append":
        tid = _cli_create(cli_runner)

    if via == "cli":
        flag = f"--{noun}-file" if from_file else f"--{noun}"
        if op == "create":
            return _cli_create(cli_runner, flag, value)
        command = ["update-ticket", "--ids"] if op == "update" else ["append-ticket-body", "--ticket-id"]
        cli_success(cli_runner, *command, tid, flag, value)
        return tid

    kwargs = {f"{noun}_file" if from_file else noun: value}
    if op == "create":
        return mcp_success(create_ticket(ticket_type="bee", title="Verbatim", hive=_HIVE, **kwargs))["ticket_id"]
    if op == "update":
        mcp_success(update_ticket(ticket_ids=tid, **kwargs))
    else:
        mcp_success(append_ticket_body(ticket_id=tid, **kwargs))
    return tid


def _source(content, stdin, tmp_path, monkeypatch):
    """Put ``content`` on stdin (returns "-") or in a file (returns its path), byte for byte."""
    if stdin:
        monkeypatch.setattr("sys.stdin", io.StringIO(content))
        return "-"
    path = tmp_path / "input.md"
    path.write_bytes(content.encode("utf-8"))
    return str(path)


def _stored_body(hive_dir, ticket_id):
    return read_ticket(ticket_id, file_path=compute_ticket_path(ticket_id, hive_dir)).body


@pytest.mark.parametrize("content", _FILE_BODIES)
@pytest.mark.parametrize("via,stdin", _SOURCES)
@pytest.mark.parametrize("op", ["create", "update", "append"])
def test_file_sourced_body_stored_verbatim(hive_env, cli_runner, tmp_path, monkeypatch, op, via, stdin, content):
    """A body read from a file or stdin round-trips exactly: no escape expansion, no trimming."""
    _, hive_dir, _ = hive_env
    source = _source(content, stdin, tmp_path, monkeypatch)

    ticket_id = _write(op, via, source, cli_runner, from_file=True)

    assert _stored_body(hive_dir, ticket_id) == content


@pytest.mark.parametrize("via,stdin", _SOURCES)
def test_appended_chunks_keep_their_newlines(hive_env, cli_runner, tmp_path, monkeypatch, via, stdin):
    """b.pp8 report: two "chunk\\n" appends to a newline-ended body each stay on their own line."""
    ticket_id = _write("create", via, _source(_REPORTED_BODY, stdin, tmp_path, monkeypatch), cli_runner, from_file=True)
    for _ in range(2):
        source = _source("chunk\n", stdin, tmp_path, monkeypatch)
        _write("append", via, source, cli_runner, from_file=True, ticket_id=ticket_id)

    if via == "cli":
        shown = cli_success(cli_runner, "show-ticket", "--ids", ticket_id)
    else:
        shown = mcp_success(show_ticket(ticket_ids=[ticket_id]))
    assert shown["tickets"][0]["body"] == "line one\nliteral \\t here\nchunk\nchunk\n"


@pytest.mark.parametrize("via", ["cli", "mcp"])
@pytest.mark.parametrize("op", ["create", "update", "append"])
def test_inline_body_still_expands_escapes(hive_env, cli_runner, op, via):
    """Inline body/chunk text still turns backslash+n / backslash+t into a newline / tab, kept at the end too."""
    _, hive_dir, _ = hive_env
    ticket_id = _write(op, via, "line1\\nline2\\tcol\\n", cli_runner, from_file=False)

    assert _stored_body(hive_dir, ticket_id) == "line1\nline2\tcol\n"
