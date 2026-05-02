"""
Unit tests for the body_file and chunk_file parameters on MCP tools.

Covers:
- _read_file_content helper (src/mcp_server.py:94-126)
- create_ticket body_file parameter
- update_ticket body_file parameter
- append_ticket_body chunk_file parameter
"""

import json

import pytest

from src.constants import BODY_MAX_LENGTH
from src.mcp_server import (
    _read_file_content,
    _show_ticket,
    append_ticket_body,
    create_ticket,
    update_ticket,
)
from src.repo_context import repo_root_context
from src.ticket_factory import create_bee
from tests.conftest import write_scoped_config


_HIVE = "backend"


# ---------------------------------------------------------------------------
# Module-level helpers for parametrized error paths
# ---------------------------------------------------------------------------


def _missing_path(tmp_path):
    return str(tmp_path / "nonexistent.txt")


def _bad_utf8_path(tmp_path):
    path = tmp_path / "bad.bin"
    path.write_bytes(b"\xff\xfe\xfd")
    return str(path)


def _directory_path(tmp_path):
    # Reading a directory raises OSError on POSIX.
    return str(tmp_path)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def body_file_hive(tmp_path, monkeypatch, mock_global_bees_dir):
    """Single-hive repo for MCP body_file / chunk_file tests."""
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)

    hive_path = tmp_path / _HIVE
    hive_path.mkdir()

    hive_id_dir = hive_path / ".hive"
    hive_id_dir.mkdir()
    (hive_id_dir / "identity.json").write_text(
        json.dumps({
            "normalized_name": _HIVE,
            "display_name": "Backend",
            "created_at": "2026-02-05T00:00:00",
        })
    )

    write_scoped_config(
        mock_global_bees_dir,
        tmp_path,
        {"hives": {_HIVE: {"path": str(hive_path), "display_name": "Backend"}}, "child_tiers": {}},
    )

    with repo_root_context(tmp_path):
        yield hive_path


# ============================================================================
# _read_file_content helper
# ============================================================================


class TestReadFileContent:

    def test_happy_path(self, tmp_path):
        """Reads UTF-8 file and returns decoded content."""
        body = "hello ☃ world"  # non-ASCII to exercise real UTF-8 decode path
        f = tmp_path / "body.txt"
        f.write_text(body, encoding="utf-8")
        assert _read_file_content("body_file", str(f)) == body

    def test_at_cap_succeeds(self, tmp_path):
        """Exactly BODY_MAX_LENGTH chars: accepted and returned unchanged."""
        body = "a" * BODY_MAX_LENGTH
        f = tmp_path / "atcap.txt"
        f.write_text(body, encoding="utf-8")
        assert _read_file_content("body_file", str(f)) == body

    def test_oversized_raises(self, tmp_path):
        """BODY_MAX_LENGTH + 1 chars: raises ValueError mentioning the cap."""
        f = tmp_path / "big.txt"
        f.write_text("a" * (BODY_MAX_LENGTH + 1), encoding="utf-8")
        with pytest.raises(ValueError, match=str(BODY_MAX_LENGTH)):
            _read_file_content("body_file", str(f))

    def test_stdin_rejected(self):
        """path='-' raises ValueError; stdin is not supported in MCP context."""
        with pytest.raises(ValueError, match="does not support stdin"):
            _read_file_content("body_file", "-")

    @pytest.mark.parametrize(
        "setup_fn,match",
        [
            pytest.param(_missing_path, "file not found", id="not_found"),
            pytest.param(_bad_utf8_path, "could not decode", id="utf8_decode_error"),
            pytest.param(_directory_path, "could not read", id="os_error"),
        ],
    )
    def test_error_paths(self, tmp_path, setup_fn, match):
        """File-not-found, UTF-8 decode error, and OS error each raise ValueError."""
        with pytest.raises(ValueError, match=match):
            _read_file_content("body_file", setup_fn(tmp_path))


# ============================================================================
# create_ticket — body_file parameter
# ============================================================================


class TestCreateTicketBodyFile:

    async def test_body_file_creates_ticket_with_file_contents(self, body_file_hive, tmp_path):
        """body_file reads a UTF-8 file and the ticket body matches that content."""
        content = "ticket body from file ☃"
        f = tmp_path / "body.txt"
        f.write_text(content, encoding="utf-8")

        result = await create_ticket(ticket_type="bee", title="File Body", hive=_HIVE, body_file=str(f))

        assert result["status"] == "success"
        shown = await _show_ticket([result["ticket_id"]])
        assert shown["tickets"][0]["body"] == content

    async def test_body_and_body_file_mutually_exclusive(self, body_file_hive, tmp_path):
        """Providing both body and body_file raises ValueError before any ticket I/O."""
        f = tmp_path / "body.txt"
        f.write_text("file content", encoding="utf-8")

        with pytest.raises(ValueError, match="mutually exclusive"):
            await create_ticket(
                ticket_type="bee", title="Test", hive=_HIVE,
                body="inline body", body_file=str(f),
            )

    async def test_body_file_nonexistent_raises(self, body_file_hive, tmp_path):
        """A missing body_file path raises ValueError."""
        with pytest.raises(ValueError, match="file not found"):
            await create_ticket(
                ticket_type="bee", title="Test", hive=_HIVE,
                body_file=str(tmp_path / "nonexistent.txt"),
            )


# ============================================================================
# update_ticket — body_file parameter
# ============================================================================


class TestUpdateTicketBodyFile:

    async def test_body_file_updates_ticket_body(self, body_file_hive, tmp_path):
        """body_file reads file and sets the result as the ticket's body."""
        ticket_id, _ = create_bee(title="Seed", hive_name=_HIVE, body="seed")
        new_content = "updated body from file ☃"
        f = tmp_path / "update.txt"
        f.write_text(new_content, encoding="utf-8")

        result = await update_ticket(ticket_ids=ticket_id, body_file=str(f))

        assert result["status"] == "success"
        shown = await _show_ticket([ticket_id])
        assert shown["tickets"][0]["body"] == new_content

    async def test_body_and_body_file_mutually_exclusive(self, body_file_hive, tmp_path):
        """Providing both body and body_file on update raises ValueError."""
        ticket_id, _ = create_bee(title="Seed", hive_name=_HIVE, body="seed")
        f = tmp_path / "body.txt"
        f.write_text("file content", encoding="utf-8")

        with pytest.raises(ValueError, match="mutually exclusive"):
            await update_ticket(ticket_ids=ticket_id, body="inline", body_file=str(f))


# ============================================================================
# append_ticket_body — chunk_file parameter
# ============================================================================


class TestAppendTicketBodyChunkFile:

    async def test_chunk_file_appends_to_body(self, body_file_hive, tmp_path):
        """chunk_file reads file and appends its contents to the existing body."""
        ticket_id, _ = create_bee(title="Append Target", hive_name=_HIVE, body="seed")
        chunk = " appended chunk"
        f = tmp_path / "chunk.txt"
        f.write_text(chunk, encoding="utf-8")

        result = await append_ticket_body(ticket_id=ticket_id, chunk_file=str(f))

        assert result["status"] == "success"
        shown = await _show_ticket([ticket_id])
        assert shown["tickets"][0]["body"] == "seed" + chunk

    async def test_chunk_and_chunk_file_mutually_exclusive(self, body_file_hive, tmp_path):
        """Providing both chunk and chunk_file raises ValueError."""
        ticket_id, _ = create_bee(title="Append Target", hive_name=_HIVE, body="seed")
        f = tmp_path / "chunk.txt"
        f.write_text("file content", encoding="utf-8")

        with pytest.raises(ValueError, match="mutually exclusive"):
            await append_ticket_body(ticket_id=ticket_id, chunk="inline", chunk_file=str(f))

    async def test_neither_chunk_nor_chunk_file_raises(self, body_file_hive):
        """Omitting both chunk and chunk_file raises ValueError."""
        ticket_id, _ = create_bee(title="Append Target", hive_name=_HIVE, body="seed")
        with pytest.raises(ValueError, match="Either chunk or chunk_file"):
            await append_ticket_body(ticket_id=ticket_id)
