"""Direct unit tests for the ``_read_body_file_arg`` CLI helper.

Covers Epic 1 / Task 1 of the ``--body-file`` / ``--chunk-file`` feature
(Bee ``b.jsz``). The helper reads body text for a CLI flag from either a
real file path or, when ``path == "-"``, ``sys.stdin``. On UTF-8 decode
errors and I/O errors it writes a single-line ``Error:`` message to
stderr and exits non-zero; on success it returns the decoded contents.

These tests exercise the helper in isolation using ``tmp_path`` for real
files and ``monkeypatch.setattr("sys.stdin", ...)`` for the stdin path
— no mocking of ``open``, ``Path.read_text``, or ``sys.stdin`` at the
module level. They mirror the ``_reject_oversized_body_cli`` unit-test
pattern in ``tests/test_cli_append_ticket_body.py``.
"""

import io

import pytest

# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_read_body_file_arg_returns_utf8_file_contents(tmp_path, capsys):
    from src.cli import _read_body_file_arg

    # Non-ASCII codepoint to confirm UTF-8 decoding (not latin-1 fallback).
    body = "hello ☃ world"  # snowman
    path = tmp_path / "body.txt"
    path.write_text(body, encoding="utf-8")

    result = _read_body_file_arg("--body-file", str(path))

    assert result == body
    assert capsys.readouterr().err == ""


def test_read_body_file_arg_reads_stdin_when_path_is_dash(monkeypatch, capsys):
    from src.cli import _read_body_file_arg

    body = "stdin body é"  # latin small e with acute
    monkeypatch.setattr("sys.stdin", io.StringIO(body))

    result = _read_body_file_arg("--body-file", "-")

    assert result == body
    assert capsys.readouterr().err == ""


def test_read_body_file_arg_returns_empty_string_for_empty_file(tmp_path, capsys):
    from src.cli import _read_body_file_arg

    path = tmp_path / "empty.txt"
    path.write_bytes(b"")

    result = _read_body_file_arg("--body-file", str(path))

    assert result == ""
    assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# Error paths (parametrized: same SystemExit + stderr-substring shape)
# ---------------------------------------------------------------------------


def _setup_missing_file(tmp_path):
    return str(tmp_path / "does_not_exist.txt"), ["file not found"]


def _setup_decode_error(tmp_path):
    path = tmp_path / "bad_utf8.bin"
    # 0xff is never a valid UTF-8 start byte.
    path.write_bytes(b"\xff\xfe\xfd")
    return str(path), ["could not decode", "UTF-8"]


def _setup_directory_as_path(tmp_path):
    # Reading a directory raises OSError (IsADirectoryError on POSIX),
    # which the helper handles via its OSError branch. Preferred over
    # chmod 000 since it works under root and on macOS/Linux CI alike.
    return str(tmp_path), ["could not read"]


@pytest.mark.parametrize(
    "setup,arg_name",
    [
        pytest.param(_setup_missing_file, "--body-file", id="missing_file"),
        pytest.param(_setup_decode_error, "--chunk-file", id="utf8_decode_error"),
        pytest.param(_setup_directory_as_path, "--body-file", id="directory_as_path"),
    ],
)
def test_read_body_file_arg_error_paths_exit_nonzero(setup, arg_name, tmp_path, capsys):
    from src.cli import _read_body_file_arg

    path, expected_substrs = setup(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        _read_body_file_arg(arg_name, path)

    assert excinfo.value.code != 0
    err = capsys.readouterr().err
    assert arg_name in err
    assert path in err
    for substr in expected_substrs:
        assert substr in err


def test_read_body_file_arg_stdin_utf8_decode_error(monkeypatch, capsys):
    # Real CLI sys.stdin is a TextIOWrapper(errors="strict"); piping invalid
    # UTF-8 bytes raises UnicodeDecodeError from .read(). Setup differs from
    # the file-error parametrize (stub object vs. tmp_path), so kept separate.
    from src.cli import _read_body_file_arg

    class _BadStdin:
        def read(self):
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr("sys.stdin", _BadStdin())

    with pytest.raises(SystemExit) as excinfo:
        _read_body_file_arg("--body-file", "-")

    assert excinfo.value.code != 0
    err = capsys.readouterr().err
    assert "--body-file" in err
    assert "could not decode" in err
    assert "stdin" in err
    assert "UTF-8" in err
