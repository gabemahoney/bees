"""Tests for the ticket read-through cache (src.cache + src.reader caching path).

PURPOSE:
Validates that read_ticket() correctly uses the file-signature-based cache
(path, device, inode, size, mtime_ns): cache hits skip parse_frontmatter,
signature mismatches trigger re-reads, deleted files evict the cache entry,
and non-FileNotFoundError stat failures leave the cache entry intact.

SCOPE - Tests that belong here:
- Cache hit: second read of unchanged file skips parse_frontmatter
- Cache miss when one signature field changes: path, inode, size or mtime
- Cache miss after a racy read (file read within RACY_WINDOW_NS of its mtime), even with identical stat output
- trusted_signature(): the RACY_WINDOW_NS boundary
- Cache miss on first read: uncached file is parsed and then cached
- FileNotFoundError evicts cache entry and propagates to caller
- PermissionError (non-FileNotFoundError OSError) propagates without evicting cache
- Write-path eviction: update, delete-subtree, and create-with-parent evict stale entries

SCOPE - Tests that DON'T belong here:
- Cache module unit tests (get/put/evict/clear in isolation)

Tests that expect a cache hit backdate() the file first: a file read within RACY_WINDOW_NS of its
mtime is cached untrusted and re-read on every lookup.
"""

import os
import time
from unittest.mock import patch

import pytest

import src.cache as ticket_cache
from src.mcp_ticket_ops import _create_ticket, _delete_ticket, _update_ticket
from src.parser import parse_frontmatter as real_parse_frontmatter
from src.paths import get_ticket_path
from src.reader import read_ticket
from src.writer import write_ticket_file
from tests.helpers import backdate
from tests.test_constants import TICKET_ID_TEST_BEE


class TestCacheReadThrough:
    """Read-through correctness: hit, miss on any signature change or after a racy read, and first-read caching."""

    def test_cache_hit_second_read_skips_parse(self, isolated_bees_env):
        """Second read of an unchanged file returns the cached ticket without re-parsing."""
        hive_dir = isolated_bees_env.create_hive("backend")
        ticket_file = isolated_bees_env.create_ticket(hive_dir, TICKET_ID_TEST_BEE, "bee", "Test Bee")
        backdate(ticket_file)

        with patch("src.reader.parse_frontmatter", wraps=real_parse_frontmatter) as mock_parse:
            ticket1 = read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)
            assert mock_parse.call_count == 1

            ticket2 = read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)
            assert mock_parse.call_count == 1  # No additional parse on hit

        assert ticket1.title == "Test Bee"
        assert ticket2.title == "Test Bee"

    @pytest.mark.parametrize(
        "by_path", [pytest.param(True, id="path_lookup"), pytest.param(False, id="id_only_lookup")]
    )
    @pytest.mark.parametrize(
        "changed",
        [
            pytest.param("st_mtime_ns", id="mtime_change"),
            pytest.param("st_size", id="in_place_rewrite"),
            pytest.param("st_ino", id="atomic_replace"),
            pytest.param(None, id="racy_read_then_identical_stat"),
        ],
    )
    def test_rewritten_file_is_reread(self, isolated_bees_env, monkeypatch, changed, by_path):
        """A rewritten file is re-read when one stat field changed, or, after a racy read, when none did.

        changed is the only stat field the rewrite changes. None: the first read happens 1 ns after
        the file's mtime, and the rewrite keeps inode, size and mtime, as two same-size atomic saves
        within one timestamp tick that reuse the inode do.
        """
        hive_dir = isolated_bees_env.create_hive("backend")
        ticket_file = isolated_bees_env.create_ticket(hive_dir, TICKET_ID_TEST_BEE, "bee", "Title A")
        stamp = backdate(ticket_file)
        if changed is None:
            # src.cache reads the clock through time.time_ns
            monkeypatch.setattr(time, "time_ns", lambda: stamp + 1)
        before = ticket_file.stat()
        assert read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file).title == "Title A"

        new_title = "Title Bee" if changed == "st_size" else "Title B"
        if changed == "st_ino":
            staging = isolated_bees_env.create_hive("staging")
            os.replace(isolated_bees_env.create_ticket(staging, TICKET_ID_TEST_BEE, "bee", new_title), ticket_file)
        else:
            isolated_bees_env.create_ticket(hive_dir, TICKET_ID_TEST_BEE, "bee", new_title)
        new_stamp = stamp + 10**9 if changed == "st_mtime_ns" else stamp
        os.utime(ticket_file, ns=(new_stamp, new_stamp))
        after = ticket_file.stat()
        fields = ("st_ino", "st_size", "st_mtime_ns")
        assert {f for f in fields if getattr(after, f) != getattr(before, f)} == ({changed} if changed else set())

        ticket = read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file if by_path else None)
        assert ticket.title == new_title

    def test_cache_miss_on_new_file_then_cached(self, isolated_bees_env):
        """First read of an uncached file parses from disk and caches; second read is a hit."""
        hive_dir = isolated_bees_env.create_hive("backend")
        ticket_file = isolated_bees_env.create_ticket(hive_dir, TICKET_ID_TEST_BEE, "bee", "New Ticket")
        backdate(ticket_file)

        assert ticket_cache.get(TICKET_ID_TEST_BEE) is None

        with patch("src.reader.parse_frontmatter", wraps=real_parse_frontmatter) as mock_parse:
            read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)
            assert mock_parse.call_count == 1

            # Second read — cache hit, no re-parse
            read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)
            assert mock_parse.call_count == 1

        assert ticket_cache.get(TICKET_ID_TEST_BEE) is not None

    def test_same_id_from_another_path_with_same_mtime_reads_that_file(self, isolated_bees_env):
        """Reading one ticket ID from two files that share size and an old mtime returns each file's own contents."""
        file_a, file_b = (
            isolated_bees_env.create_ticket(isolated_bees_env.create_hive(hive), TICKET_ID_TEST_BEE, "bee", title)
            for hive, title in [("hive_a", "Title A"), ("hive_b", "Title B")]
        )
        backdate(file_a, file_b)
        assert file_a.stat().st_size == file_b.stat().st_size

        assert read_ticket(TICKET_ID_TEST_BEE, file_path=file_a).title == "Title A"
        assert read_ticket(TICKET_ID_TEST_BEE, file_path=file_b).title == "Title B"
        assert read_ticket(TICKET_ID_TEST_BEE, file_path=file_a).title == "Title A"


class TestTrustedSignature:
    """trusted_signature(): only a file whose mtime is more than RACY_WINDOW_NS old keys a trusted entry."""

    @pytest.mark.parametrize(
        "past_window_ns, trusted",
        [pytest.param(0, False, id="mtime_at_window_edge"), pytest.param(1, True, id="mtime_past_window")],
    )
    def test_trusted_only_past_racy_window(self, monkeypatch, past_window_ns, trusted):
        """The signature is returned once now - mtime exceeds RACY_WINDOW_NS, else None."""
        mtime_ns = 1_700_000_000 * 10**9
        signature = ("/hive/b.x/b.x.md", 1, 2, 3, mtime_ns)
        monkeypatch.setattr(time, "time_ns", lambda: mtime_ns + ticket_cache.RACY_WINDOW_NS + past_window_ns)

        assert ticket_cache.trusted_signature(signature) == (signature if trusted else None)


class TestCacheErrorCases:
    """Error and edge-case scenarios: external deletion and stat permission failure."""

    def test_file_deletion_raises_and_evicts_cache(self, isolated_bees_env):
        """Reading a deleted file raises FileNotFoundError and evicts the cache entry."""
        hive_dir = isolated_bees_env.create_hive("backend")
        ticket_file = isolated_bees_env.create_ticket(hive_dir, TICKET_ID_TEST_BEE, "bee", "Test Bee")

        # Populate the cache via a normal read
        read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)
        assert ticket_cache.get(TICKET_ID_TEST_BEE) is not None

        # Delete the file directly on the filesystem (bypass bees API)
        ticket_file.unlink()

        with pytest.raises(FileNotFoundError):
            read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)

        assert ticket_cache.get(TICKET_ID_TEST_BEE) is None

    def test_permission_error_propagates_and_preserves_cache(self, isolated_bees_env):
        """PermissionError on stat propagates unchanged; cache entry is not evicted."""
        hive_dir = isolated_bees_env.create_hive("backend")
        ticket_file = isolated_bees_env.create_ticket(hive_dir, TICKET_ID_TEST_BEE, "bee", "Test Bee")
        ticket_dir = ticket_file.parent

        # Populate the cache
        read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)
        assert ticket_cache.get(TICKET_ID_TEST_BEE) is not None

        # Remove execute permission from the containing directory so stat() raises PermissionError
        ticket_dir.chmod(0o000)
        try:
            with pytest.raises((PermissionError, OSError)):
                read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)

            # Cache entry must still be present — non-FileNotFoundError must NOT evict
            assert ticket_cache.get(TICKET_ID_TEST_BEE) is not None
        finally:
            # Restore permissions so pytest can clean up tmp_path
            ticket_dir.chmod(0o755)


class TestCacheWriteEviction:
    """Write-path cache eviction: update, delete-subtree, and create-with-parent."""

    async def test_update_evicts_cache(self, isolated_bees_env):
        """Read ticket (caches), update via _update_ticket(), read again → fresh content."""
        hive_dir = isolated_bees_env.create_hive("backend")
        isolated_bees_env.write_config()
        ticket_file = isolated_bees_env.create_ticket(hive_dir, TICKET_ID_TEST_BEE, "bee", "Original Title")

        # Populate the cache via a normal read
        ticket1 = read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)
        assert ticket_cache.get(TICKET_ID_TEST_BEE) is not None
        assert ticket1.title == "Original Title"

        # Write via MCP update path — must evict the cache entry
        await _update_ticket(ticket_ids=TICKET_ID_TEST_BEE, title="Updated Title", hive_name="backend")

        assert ticket_cache.get(TICKET_ID_TEST_BEE) is None

        # Re-reading returns fresh content from disk, not the stale cached value
        ticket2 = read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)
        assert ticket2.title == "Updated Title"

    async def test_delete_evicts_subtree_cache(self, isolated_bees_env):
        """Read bee+children (caches all), delete bee → full subtree evicted."""
        isolated_bees_env.create_hive("backend")
        isolated_bees_env.write_config(child_tiers={"t1": ["Task", "Tasks"]})

        # Create parent bee then child so parent.children is populated
        bee_result = await _create_ticket(ticket_type="bee", title="Parent Bee", hive_name="backend")
        bee_id = bee_result["ticket_id"]
        child_result = await _create_ticket(
            ticket_type="t1", title="Child Task", hive_name="backend", parent=bee_id
        )
        child_id = child_result["ticket_id"]

        # Populate cache for both tickets
        bee_path = get_ticket_path(bee_id, "bee", "backend")
        child_path = get_ticket_path(child_id, "t1", "backend")
        read_ticket(bee_id, file_path=bee_path)
        read_ticket(child_id, file_path=child_path)
        assert ticket_cache.get(bee_id) is not None
        assert ticket_cache.get(child_id) is not None

        # Delete bee (cascades to child)
        await _delete_ticket(ticket_ids=bee_id, hive_name="backend")

        # Both cache entries must be evicted
        assert ticket_cache.get(bee_id) is None
        assert ticket_cache.get(child_id) is None

    async def test_create_child_evicts_parent_cache(self, isolated_bees_env):
        """Create child (triggers parent children-list update), read parent → fresh children list."""
        hive_dir = isolated_bees_env.create_hive("backend")
        isolated_bees_env.write_config(child_tiers={"t1": ["Task", "Tasks"]})

        ticket_file = isolated_bees_env.create_ticket(hive_dir, TICKET_ID_TEST_BEE, "bee", "Parent Bee")

        # Cache the parent before any children exist
        parent_before = read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)
        assert ticket_cache.get(TICKET_ID_TEST_BEE) is not None
        assert not parent_before.children

        # Creating a child rewrites the parent file and evicts its cache entry
        result = await _create_ticket(
            ticket_type="t1", title="New Task", hive_name="backend", parent=TICKET_ID_TEST_BEE
        )
        child_id = result["ticket_id"]

        # Parent cache must be evicted (parent file was rewritten with updated children list)
        assert ticket_cache.get(TICKET_ID_TEST_BEE) is None

        # Re-reading the parent returns the updated children list including the new child
        parent_after = read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)
        assert child_id in (parent_after.children or [])


class TestWriterEviction:
    """write_ticket_file() owns cache eviction: evicts on success, preserves on failure."""

    def test_eviction_on_successful_write(self, isolated_bees_env):
        """write_ticket_file() evicts cache entry after a successful write."""
        hive_dir = isolated_bees_env.create_hive("backend")
        isolated_bees_env.write_config()
        ticket_file = isolated_bees_env.create_ticket(hive_dir, TICKET_ID_TEST_BEE, "bee", "Original Title")

        read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)
        assert ticket_cache.contains(TICKET_ID_TEST_BEE)

        write_ticket_file(
            ticket_id=TICKET_ID_TEST_BEE,
            ticket_type="bee",
            frontmatter_data={"id": TICKET_ID_TEST_BEE, "type": "bee", "title": "Updated Title", "egg": None},
            body="Updated body",
            hive_name="backend",
        )

        assert not ticket_cache.contains(TICKET_ID_TEST_BEE)

    def test_no_error_on_new_ticket_write(self, isolated_bees_env):
        """write_ticket_file() succeeds without error when no prior cache entry exists."""
        hive_dir = isolated_bees_env.create_hive("backend")
        isolated_bees_env.write_config()

        assert not ticket_cache.contains(TICKET_ID_TEST_BEE)

        # Should not raise even with no prior cache entry
        write_ticket_file(
            ticket_id=TICKET_ID_TEST_BEE,
            ticket_type="bee",
            frontmatter_data={"id": TICKET_ID_TEST_BEE, "type": "bee", "title": "New Ticket", "egg": None},
            body="",
            hive_name="backend",
        )

    def test_no_eviction_on_failed_write(self, isolated_bees_env):
        """write_ticket_file() does not evict cache entry when os.rename raises OSError."""
        hive_dir = isolated_bees_env.create_hive("backend")
        isolated_bees_env.write_config()
        ticket_file = isolated_bees_env.create_ticket(hive_dir, TICKET_ID_TEST_BEE, "bee", "Original Title")

        read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)
        assert ticket_cache.contains(TICKET_ID_TEST_BEE)

        with patch("src.writer.os.rename", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                write_ticket_file(
                    ticket_id=TICKET_ID_TEST_BEE,
                    ticket_type="bee",
                    frontmatter_data={"id": TICKET_ID_TEST_BEE, "type": "bee", "title": "Failed Write", "egg": None},
                    body="",
                    hive_name="backend",
                )

        # Cache entry preserved — failed write must NOT evict
        assert ticket_cache.contains(TICKET_ID_TEST_BEE)


class TestCachePathStorage:
    """Tests for path storage and ID-only lookup behavior (3-tuple cache)."""

    def test_path_stored_in_cache_after_read(self, isolated_bees_env):
        """Path passed to read_ticket() is stored as second element of the cache tuple."""
        hive_dir = isolated_bees_env.create_hive("backend")
        ticket_file = isolated_bees_env.create_ticket(hive_dir, TICKET_ID_TEST_BEE, "bee", "Test Bee")

        read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)

        cached = ticket_cache.get(TICKET_ID_TEST_BEE)
        assert cached is not None
        _signature, cached_path, _ticket = cached
        assert cached_path == ticket_file

    def test_id_only_warm_cache_skips_discovery(self, isolated_bees_env):
        """ID-only read after a warm cache hit does not call find_ticket_file."""
        hive_dir = isolated_bees_env.create_hive("backend")
        isolated_bees_env.write_config()
        ticket_file = isolated_bees_env.create_ticket(hive_dir, TICKET_ID_TEST_BEE, "bee", "Test Bee")

        # Populate cache with explicit path
        read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)

        # ID-only read should use cached path, NOT call find_ticket_file
        with patch("src.paths.find_ticket_file") as mock_find:
            ticket = read_ticket(TICKET_ID_TEST_BEE)
            mock_find.assert_not_called()

        assert ticket.title == "Test Bee"

    def test_stale_path_triggers_hive_discovery(self, isolated_bees_env):
        """Stale cached path (FileNotFoundError on stat) evicts entry; re-discovery via compute_ticket_path finds the ticket."""
        hive_dir = isolated_bees_env.create_hive("backend")
        isolated_bees_env.write_config()
        ticket_file = isolated_bees_env.create_ticket(hive_dir, TICKET_ID_TEST_BEE, "bee", "Test Bee")

        # Populate cache normally first
        original_ticket = read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)
        cached_before = ticket_cache.get(TICKET_ID_TEST_BEE)
        assert cached_before is not None
        original_signature = cached_before[0]

        # Overwrite cache entry with a stale (nonexistent) path
        stale_path = hive_dir / "stale_dir" / f"{TICKET_ID_TEST_BEE}.md"
        ticket_cache.put(TICKET_ID_TEST_BEE, original_signature, stale_path, original_ticket)

        # ID-only read: stale path → FileNotFoundError on stat → evict → fall through
        # to hive discovery via compute_ticket_path, which finds the canonical location
        ticket = read_ticket(TICKET_ID_TEST_BEE)

        # Cache should now hold the canonical path
        cached = ticket_cache.get(TICKET_ID_TEST_BEE)
        assert cached is not None
        _signature, cached_path, _ticket = cached
        assert cached_path == ticket_file
        assert ticket.title == "Test Bee"
