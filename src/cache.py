"""Ticket read cache module.

Provides a module-level singleton cache for read_ticket() results.
Key: ticket_id → Value: (FileSignature | None, Path, Ticket)

Also provides file_signature() and trusted_signature(), the freshness check
shared by every cache of on-disk file contents (ticket reads, global config,
hive identity.json).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Ticket

__all__ = [
    "RACY_WINDOW_NS",
    "FileSignature",
    "file_signature",
    "trusted_signature",
    "contains",
    "get",
    "put",
    "evict",
    "clear",
]

# (absolute path, st_dev, st_ino, st_size, st_mtime_ns)
FileSignature = tuple[str, int, int, int, int]

# A file whose mtime is within this window of the moment its contents are read
# is "racy" (as in git's racy-clean check): a later write can land in the same
# timestamp tick, keep the size, and reuse the inode, so its signature does not
# change. The window must exceed the coarsest file timestamp granularity in
# common use (2 s on FAT; 1 s on ext3, HFS+ and some network filesystems) plus
# the lag of the coarse kernel clock that stamps files (one scheduler tick, at
# most ~10 ms). The spare second absorbs small clock offsets between a client
# and a network filesystem server. The cost is small: a file changed within the
# window is re-read on each lookup, as if uncached, until it is older.
RACY_WINDOW_NS = 3_000_000_000

# Module-private backing store: ticket_id -> (FileSignature | None, Path, Ticket)
_cache: dict[str, tuple[FileSignature | None, Path, Ticket]] = {}


def file_signature(path: Path) -> FileSignature:
    """Return a stat signature for the file at path: (abspath, dev, inode, size, mtime_ns).

    Equal signatures do not prove equal contents. A write that lands within one
    timestamp tick of the version that was read and keeps its size leaves every
    field unchanged, whether it rewrites the file in place or atomically replaces
    it onto a reused inode (mkstemp + os.replace can alternate between two
    inodes). Key cache entries on trusted_signature() of it, not on the raw
    signature.

    Raises:
        OSError: Propagated from stat(), including FileNotFoundError.
    """
    st = path.stat()
    return (os.path.abspath(path), st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)


def trusted_signature(signature: FileSignature) -> FileSignature | None:
    """Return signature if it can key a cache entry for contents read after this call, else None.

    Call between file_signature() and reading the file's contents. When the
    file's mtime is within RACY_WINDOW_NS of now, a later write could leave the
    signature unchanged, so this returns None. Store the result as the entry's
    signature: None never equals a current signature, so the next lookup re-reads
    the file and caches it with a trusted signature once it is old enough.

    Explicitly backdating an mtime (os.utime, archive extraction) or a clock
    offset larger than the window can still defeat this check.
    """
    if time.time_ns() - signature[4] > RACY_WINDOW_NS:
        return signature
    return None


def contains(ticket_id: str) -> bool:
    """Return True if ticket_id is present in the cache, regardless of freshness."""
    return ticket_id in _cache


def get(ticket_id: str) -> tuple[FileSignature | None, Path, Ticket] | None:
    """Return (signature, Path, Ticket) for the given ticket_id, or None if not cached.

    The signature is None when the entry must be re-validated on the next read
    (see trusted_signature()).
    """
    return _cache.get(ticket_id)


def put(ticket_id: str, signature: FileSignature | None, path: Path, ticket: Ticket) -> None:
    """Store (signature, Path, Ticket) under the given ticket_id.

    Pass trusted_signature() of the file's signature; None stores an entry that
    is never served as fresh.
    """
    _cache[ticket_id] = (signature, path, ticket)


def evict(ticket_id: str) -> None:
    """Remove entry for the given ticket_id if present."""
    _cache.pop(ticket_id, None)


def clear() -> None:
    """Remove all entries from the cache."""
    _cache.clear()
