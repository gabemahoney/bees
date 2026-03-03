"""Tests for the ticket read-through cache (src.cache + src.reader caching path).

PURPOSE:
Validates that read_ticket() correctly uses the mtime-based cache:
cache hits skip parse_frontmatter, mtime mismatches trigger re-reads,
deleted files evict the cache entry, and non-FileNotFoundError stat failures leave
the cache entry intact.

SCOPE - Tests that belong here:
- Cache hit: second read of unchanged file skips parse_frontmatter
- Cache miss on mtime change: stale entry triggers re-read and returns new content
- Cache miss on first read: uncached file is parsed and then cached
- FileNotFoundError evicts cache entry and propagates to caller
- PermissionError (non-FileNotFoundError OSError) propagates without evicting cache
- Write-path eviction: update, delete-subtree, and create-with-parent evict stale entries

SCOPE - Tests that DON'T belong here:
- Cache module unit tests (get/put/evict/clear in isolation)
"""

import time
from unittest.mock import patch

import pytest

import src.cache as ticket_cache
from src.mcp_ticket_ops import _create_ticket, _delete_ticket, _update_ticket
from src.parser import parse_frontmatter as real_parse_frontmatter
from src.paths import get_ticket_path
from src.reader import read_ticket
from src.writer import write_ticket_file
from tests.test_constants import TICKET_ID_TEST_BEE


class TestCacheReadThrough:
    """Read-through correctness: hit, mtime miss, and first-read caching."""

    def test_cache_hit_second_read_skips_parse(self, isolated_bees_env):
        """Second read of an unchanged file returns the cached ticket without re-parsing."""
        hive_dir = isolated_bees_env.create_hive("backend")
        ticket_file = isolated_bees_env.create_ticket(hive_dir, TICKET_ID_TEST_BEE, "bee", "Test Bee")

        with patch("src.reader.parse_frontmatter", wraps=real_parse_frontmatter) as mock_parse:
            ticket1 = read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)
            assert mock_parse.call_count == 1

            ticket2 = read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)
            assert mock_parse.call_count == 1  # No additional parse on hit

        assert ticket1.title == "Test Bee"
        assert ticket2.title == "Test Bee"

    def test_cache_miss_on_mtime_change(self, isolated_bees_env):
        """Re-reading a file whose mtime changed returns updated content and re-parses."""
        hive_dir = isolated_bees_env.create_hive("backend")
        isolated_bees_env.create_ticket(hive_dir, TICKET_ID_TEST_BEE, "bee", "Original Title")
        ticket_file = hive_dir / TICKET_ID_TEST_BEE / f"{TICKET_ID_TEST_BEE}.md"

        with patch("src.reader.parse_frontmatter", wraps=real_parse_frontmatter) as mock_parse:
            ticket1 = read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)
            assert mock_parse.call_count == 1
            assert ticket1.title == "Original Title"

            # Small sleep to ensure distinct mtime on filesystems with coarse resolution
            time.sleep(0.01)
            # Overwrite file to change mtime and content
            isolated_bees_env.create_ticket(hive_dir, TICKET_ID_TEST_BEE, "bee", "Updated Title")

            ticket2 = read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)
            assert mock_parse.call_count == 2
            assert ticket2.title == "Updated Title"

    def test_cache_miss_on_new_file_then_cached(self, isolated_bees_env):
        """First read of an uncached file parses from disk and caches; second read is a hit."""
        hive_dir = isolated_bees_env.create_hive("backend")
        ticket_file = isolated_bees_env.create_ticket(hive_dir, TICKET_ID_TEST_BEE, "bee", "New Ticket")

        assert ticket_cache.get(TICKET_ID_TEST_BEE) is None

        with patch("src.reader.parse_frontmatter", wraps=real_parse_frontmatter) as mock_parse:
            read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)
            assert mock_parse.call_count == 1

            # Second read — cache hit, no re-parse
            read_ticket(TICKET_ID_TEST_BEE, file_path=ticket_file)
            assert mock_parse.call_count == 1

        assert ticket_cache.get(TICKET_ID_TEST_BEE) is not None


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
        await _update_ticket(ticket_id=TICKET_ID_TEST_BEE, title="Updated Title", hive_name="backend")

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
        _mtime, cached_path, _ticket = cached
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
        original_mtime = cached_before[0]

        # Overwrite cache entry with a stale (nonexistent) path
        stale_path = hive_dir / "stale_dir" / f"{TICKET_ID_TEST_BEE}.md"
        ticket_cache.put(TICKET_ID_TEST_BEE, original_mtime, stale_path, original_ticket)

        # ID-only read: stale path → FileNotFoundError on stat → evict → fall through
        # to hive discovery via compute_ticket_path, which finds the canonical location
        ticket = read_ticket(TICKET_ID_TEST_BEE)

        # Cache should now hold the canonical path
        cached = ticket_cache.get(TICKET_ID_TEST_BEE)
        assert cached is not None
        _mtime, cached_path, _ticket = cached
        assert cached_path == ticket_file
        assert ticket.title == "Test Bee"
