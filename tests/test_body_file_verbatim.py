"""Regression tests for b.va7: file-sourced ticket bodies are stored verbatim.

Every body-from-file path must store the file's text exactly, with no escape
interpretation: the two-character sequences backslash+n / backslash+t stay as
written. Paths covered, each for create, update and append:

- CLI ``--body-file PATH`` / ``--chunk-file PATH`` and their ``-`` (stdin) form.
- MCP ``body_file`` / ``chunk_file`` (the tool functions in ``src/mcp_server.py``).

Inline ``--body`` / ``--chunk`` (CLI) and ``body`` / ``chunk`` (MCP) still
expand backslash+n / backslash+t on purpose, to undo LLM JSON double-escaping.
``test_inline_body_still_expands_escapes`` pins that for all three operations
on both surfaces; core-level inline expansion on create/update is covered by
``TestSanitizeEscapeSequencesVia*`` in ``test_mcp_ticket_ops.py``.

The parser strips leading/trailing whitespace from a body on read, so no
test body starts or ends with whitespace.
"""

import asyncio
import io
import json

import pytest

from src.mcp_server import append_ticket_body, create_ticket, update_ticket
from src.paths import compute_ticket_path
from src.reader import read_ticket
from src.repo_context import repo_root_context

_HIVE = "test"

# In these Python literals "\\n" is the two characters backslash + n and
# "\\\\" is two backslashes. Each body is corrupted by escape expansion.
_BACKSLASH_N = "printf '%s\\n' \"$x\""
_BACKSLASH_T = "cut -d'\\t' -f1 data.tsv"
_DOUBLE_BACKSLASH = 'path = "C:\\\\new\\\\tmp"'
_TRAILING_BACKSLASH = "printf 'a\\tb\\n' \\"  # last character is a backslash

_FILE_BODIES = [
    pytest.param(_BACKSLASH_N, id="backslash_n"),
    pytest.param(_BACKSLASH_T, id="backslash_t"),
    pytest.param(_DOUBLE_BACKSLASH, id="double_backslash"),
    pytest.param(_TRAILING_BACKSLASH, id="trailing_backslash"),
    pytest.param(
        "\n".join([_BACKSLASH_N, _BACKSLASH_T, _DOUBLE_BACKSLASH, _TRAILING_BACKSLASH]),
        id="all_four",
    ),
]


@pytest.fixture
def hive_dir(isolated_bees_env):
    """One registered hive in an isolated tmp repo, with the repo context pinned to it."""
    hive = isolated_bees_env.create_hive(_HIVE)
    isolated_bees_env.write_config()
    with repo_root_context(isolated_bees_env.base_path):
        yield hive


def _cli(cli_runner, *argv):
    stdout, exit_code = cli_runner(list(argv))
    assert exit_code == 0, stdout
    result = json.loads(stdout)
    assert result["status"] == "success", result
    return result


def _mcp(coro):
    result = asyncio.run(coro)
    assert result["status"] == "success", result
    return result


def _cli_create(cli_runner, *body_args):
    argv = ["create-ticket", "--ticket-type", "bee", "--title", "Verbatim", "--hive", _HIVE, *body_args]
    return _cli(cli_runner, *argv)["ticket_id"]


def _write(op, via, value, cli_runner, *, from_file):
    """Write ``value`` through one body path and return the ticket ID.

    ``value`` is the file path (``from_file``) or the inline text. update
    overwrites a "seed" body and append extends an empty body, so in every
    case the stored body is exactly the written text.
    """
    noun = "chunk" if op == "append" else "body"
    tid = None
    if op == "update":
        tid = _cli_create(cli_runner, "--body", "seed")
    elif op == "append":
        tid = _cli_create(cli_runner)

    if via == "cli":
        flag = f"--{noun}-file" if from_file else f"--{noun}"
        if op == "create":
            return _cli_create(cli_runner, flag, value)
        command = ["update-ticket", "--ids"] if op == "update" else ["append-ticket-body", "--ticket-id"]
        _cli(cli_runner, *command, tid, flag, value)
        return tid

    kwargs = {f"{noun}_file" if from_file else noun: value}
    if op == "create":
        return _mcp(create_ticket(ticket_type="bee", title="Verbatim", hive=_HIVE, **kwargs))["ticket_id"]
    if op == "update":
        _mcp(update_ticket(ticket_ids=tid, **kwargs))
    else:
        _mcp(append_ticket_body(ticket_id=tid, **kwargs))
    return tid


def _stored_body(hive_dir, ticket_id):
    return read_ticket(ticket_id, file_path=compute_ticket_path(ticket_id, hive_dir)).body


@pytest.mark.parametrize("content", _FILE_BODIES)
@pytest.mark.parametrize(
    "via,stdin",
    [
        pytest.param("cli", False, id="cli_file"),
        pytest.param("cli", True, id="cli_stdin"),
        pytest.param("mcp", False, id="mcp_file"),
    ],
)
@pytest.mark.parametrize("op", ["create", "update", "append"])
def test_file_sourced_body_stored_verbatim(hive_dir, cli_runner, tmp_path, monkeypatch, op, via, stdin, content):
    """A body read from a file or stdin round-trips exactly: no escape expansion."""
    if stdin:
        monkeypatch.setattr("sys.stdin", io.StringIO(content))
        source = "-"
    else:
        path = tmp_path / "input.md"
        path.write_bytes(content.encode("utf-8"))  # exact bytes, no trailing newline
        source = str(path)

    ticket_id = _write(op, via, source, cli_runner, from_file=True)

    assert _stored_body(hive_dir, ticket_id) == content


@pytest.mark.parametrize("via", ["cli", "mcp"])
@pytest.mark.parametrize("op", ["create", "update", "append"])
def test_inline_body_still_expands_escapes(hive_dir, cli_runner, op, via):
    """Inline body/chunk text still turns backslash+n / backslash+t into a newline / tab."""
    ticket_id = _write(op, via, "line1\\nline2\\tcol", cli_runner, from_file=False)

    assert _stored_body(hive_dir, ticket_id) == "line1\nline2\tcol"
