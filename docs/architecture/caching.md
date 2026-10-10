# Caching Architecture

## Overview

Bees maintains a module-level in-memory cache of parsed ticket data, keyed by `ticket_id`. The cache is scoped to the MCP server process lifetime and is populated lazily on first read. Its purpose is to avoid redundant file I/O and parse operations when ticket files have not changed since the last read.

The cache is an internal implementation detail of `read_ticket()` in `src/reader.py`. Callers do not interact with the cache directly.

## Data Structure

The cache maps a key to a tuple of file signature, file path, and parsed ticket data:

- **Key**: `ticket_id` — the ticket's unique identifier.
- **Value**: `(FileSignature | None, Path, Ticket)` — `FileSignature` is the value returned by `file_signature()` in `src/cache.py`: the file's absolute path, device, inode, size, and nanosecond mtime (`st_mtime_ns`), taken from one `stat()` call. The stored signature is `None` when the file was too recently modified to trust (see Freshness Check). `Path` is the absolute filesystem path to the ticket's markdown file. `Ticket` is the parsed dataclass defined in `src/models.py`.

The backing store (`src/cache.py`) is a plain dict with five operations: `get`, `put`, `evict`, `clear`, and `contains`. `get` returns `(FileSignature | None, Path, Ticket) | None`. `put` takes `(ticket_id, signature, path, ticket)`, where `signature` may be `None`. Callers outside `src/reader.py` must not access it directly.

## Freshness Check

A cache entry is fresh only when the file's current signature equals the stored one. A change to any of the five fields causes a re-read, and an entry cached from a different path never matches.

Equal signatures do not prove equal contents. A write that lands within one timestamp tick of the version that was read and keeps its size can leave every field unchanged, whether it rewrites the file in place or atomically replaces it onto a reused inode. The racy-timestamp guard covers this case: after the `stat()` and before reading the contents, the signature is passed through `trusted_signature()`. If the file's mtime is within `RACY_WINDOW_NS` (3 seconds) of the current time, it returns `None`, and the entry is stored with a `None` signature. `None` never equals a current signature, so a file modified in the last 3 seconds is re-read on every lookup. Once the file is older, the next read stores its signature and later lookups are served from the cache.

Two cases can still serve stale contents: a writer that sets the mtime back to an exact earlier value while keeping the same size and inode (e.g. `os.utime` or archive extraction), and clock skew larger than the window, which makes a just-written file look old enough to trust.

`file_signature()`, `trusted_signature()`, and `FileSignature` are shared by every in-memory cache of on-disk file contents. The global config and `.hive/identity.json` caches in `src/config.py` use the same signature and guard as their freshness key (see [configuration.md](configuration.md), Config API).

## Lazy-Loading Lifecycle

The cache is empty on server startup. No pre-warming or background population occurs. Entries are added on demand as tickets are read:

1. **First read**: Cache miss. File is read from disk, parsed, and the result is stored under `ticket_id` with the file's current signature, or `None` if the file was modified within the racy window.
2. **Subsequent reads (unchanged file)**: `stat()` is called to compute the current signature. If it matches the cached signature, the cached `Ticket` is returned with no file I/O.
3. **Subsequent reads (changed file)**: Signature mismatch. File is re-read, re-parsed, and the cache entry is updated.

The cache has no eviction policy — entries are retained for the lifetime of the server process.

## Read-Through Behavior

`read_ticket(ticket_id, file_path=None)` is the single entry point for all ticket reads in the server. It operates in two modes depending on whether `file_path` is provided.

**Path-provided mode** (`file_path` is given):

1. Calls `stat()` on the provided path to compute its current signature.
2. Checks the cache for a `ticket_id` entry with a matching signature. The signature includes the path, so an entry cached from a different path never matches.
3. Returns the cached ticket on signature match; otherwise reads, parses, and caches the file.

**ID-only mode** (`file_path` is omitted):

1. Checks the cache for a `ticket_id` entry to retrieve its stored `Path`.
2. If found, calls `stat()` on the cached path.
   - Signature match: returns cached ticket immediately.
   - Signature mismatch: re-reads from cached path and updates cache.
   - `FileNotFoundError`: evicts the stale entry and falls through to discovery.
3. On cache miss or after stale eviction, searches all configured hives via `find_ticket_file()`.
4. Once a path is found, reads, parses, and caches the result (including the discovered path).
5. Raises `FileNotFoundError` if the ticket is not found in any hive.

## Bulk Read Path Caching

Bulk operations that iterate ticket files also flow through `read_ticket()` and are therefore fully cache-backed. These callers pass an explicit `file_path` after discovery:

- **`list_tickets()`** (`src/paths.py`): Discovers ticket files via `iter_ticket_files()`, then calls `read_ticket(ticket_id, file_path=path)` for each. Ticket parsing is cache-backed; only directory traversal touches the disk unconditionally.
- **`infer_ticket_type_from_id()`** (`src/paths.py`): Finds a ticket file via `find_ticket_file()`, then calls `read_ticket(ticket_id, file_path=path)` to extract the type field. Cache hit avoids re-parsing on repeat calls.
- **`PipelineEvaluator._load_tickets()`** (`src/pipeline.py`): Iterates all ticket files across all hives and calls `read_ticket(ticket_id, file_path=path)` for each. On repeated `PipelineEvaluator` instantiations within the same server process, unchanged tickets are served from the cache.

File discovery itself (`iter_ticket_files()`, `find_ticket_file()`) still performs direct directory traversal — the cache operates at the parsed-ticket level, not the filesystem-scan level. After discovery, every parse operation goes through the cache store.

## Error Handling

Three distinct error cases arise during `stat()` calls in the read path:

- **`FileNotFoundError` on a provided or cached path**: The ticket file no longer exists at the expected location. The cache entry is evicted, and the exception propagates to the caller unchanged. No warning is logged — external deletion is a valid state.
- **`FileNotFoundError` on a cached path in ID-only mode (stale path recovery)**: The cached path no longer exists, but the ticket may have moved to a different location. The cache entry is evicted and `read_ticket()` falls through to hive discovery (`find_ticket_file()`). This is distinct from a deleted ticket — if discovery succeeds, the ticket is read and cached with its new path.
- **Any other `OSError`** (e.g., `PermissionError`): The file still exists but is temporarily unreadable. The cache entry is **not** evicted, and the exception propagates to the caller unchanged. The cache layer does not swallow or transform these errors.

## Write Path Eviction

The write path is eviction-only. Write operations never populate the cache — they only remove stale entries. After a filesystem write succeeds, the affected ticket's cache entry is evicted so the next read fetches fresh data from disk.

### Eviction Timing

Eviction always occurs **after** the filesystem operation completes successfully. If the write fails, no eviction occurs and the cache retains the last-known-good entry.

### Single Eviction Owner: `write_ticket_file()`

`write_ticket_file()` (`src/writer.py`) is the **sole owner** of write-path cache eviction. It evicts the affected ticket's cache entry immediately after `os.rename()` succeeds. Eviction does **not** occur in the except/cleanup branch — a failed write leaves the cache entry intact.

**Callers must not call `cache.evict()` themselves after `write_ticket_file()`.** The writer handles eviction internally, so adding a caller-side evict would result in a redundant (harmless but incorrect) double eviction.

### Non-Writer Eviction Sites

A small number of filesystem operations outside `write_ticket_file()` must still evict directly, because they mutate ticket state without going through the writer:

- **`_delete_ticket()`** (`src/mcp_ticket_ops.py`): Evicts each ticket after `shutil.rmtree()` removes its directory. Deletion is not a write operation and does not call `write_ticket_file()`.
- **`enforce_directory_structure()`** (`src/linter.py`): `_move_ticket_dir()` evicts each ticket after relocating its directory (a refused move, or one that fails partway, evicts nothing). Moving is not a write operation.
- **`read_ticket()`** (`src/reader.py`): Evicts the cache entry on `FileNotFoundError` during `stat()` — the file no longer exists at the cached path.

### Create Operations

Creating a new ticket does not evict any cache entry for the new ticket itself — there is no prior cache entry to remove. `write_ticket_file()` calls `cache.evict()` internally, which is a no-op when no entry exists. Relationship sync during creation (wiring up parent, children, and dependencies) calls `write_ticket_file()` for each related ticket; the writer handles their evictions.

