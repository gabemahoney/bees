# MCP Server Architecture

## Overview

The Bees MCP (Model Context Protocol) server provides a standardized interface for ticket operations while maintaining relationship consistency. Built with FastMCP 2.14.4, the server exposes tools that AI agents and clients can use to manipulate tickets and hives safely.

## Design Goals

1. **Relationship Consistency**: Automatically maintain reciprocal relationships (see `relationships.md`)
2. **Schema Validation**: Enforce ticket type rules (e.g., subtasks must have parent, bees cannot)
3. **Atomic Operations**: All relationship updates succeed or fail together
4. **Tool-Based Interface**: Standard MCP tool schemas for interoperability
5. **Health Monitoring**: Server lifecycle management and readiness checks
6. **Consistent Error Handling**: All MCP tools raise `ValueError` for errors (validation failures, missing resources, config errors) rather than returning error dicts

## HTTP Transport Architecture

HTTP transport uses uvicorn ASGI server for MCP communication.

**Entry point**: `bees serve --http` starts the HTTP server. The `--host` flag sets the bind address (default `127.0.0.1`) and `--port` sets the port (default `8000`). Use `--test-config` to run with an ephemeral in-memory config that bypasses `~/.bees/config.json` (see [Test Mode](configuration.md#test-mode---test-config)). Configuration comes from CLI flags only — there is no config file for HTTP transport.

**Startup sequence**: The handler validates the bees config (undertaker schedule), starts the undertaker scheduler, registers SIGINT/SIGTERM signal handlers, then passes the Starlette ASGI app from `mcp.http_app` to uvicorn.

**Implementation**: The FastMCP framework provides HTTP transport through its `mcp.http_app` property, which returns a Starlette ASGI application instance. This application is passed to uvicorn, which handles the HTTP server hosting with configurable host, port, and logging settings. The architecture separates the MCP protocol handling (FastMCP) from the HTTP transport layer (uvicorn), allowing flexible deployment configurations.

**Deferred imports**: uvicorn, Starlette, and FastMCP are imported inside the `--http` handler rather than at module level, matching the same strategy used by `--stdio`. This keeps CLI startup fast for users who have not installed the `[serve]` extra.

**Documentation Structure**: The README includes a brief note about stdio transport for common usage.

## Stdio Transport Architecture

Stdio transport runs the MCP server as a subprocess communicating over stdin/stdout, the standard model for local MCP clients (Claude Code, OpenCode, etc.).

**How it works**: `bees serve --stdio` calls `mcp.run(transport="stdio")`, which hands control to FastMCP's stdio loop. The process blocks until the client terminates it.

**File-only logging**: All log output is redirected to `~/.bees/mcp.log` before the stdio loop starts. This is required because MCP JSON-RPC uses stdout for protocol messages — any log line written to stdout would corrupt the wire format.

**No undertaker**: The undertaker scheduler is not started in stdio mode. Stdio servers live and die with the client process, making background scheduling unnecessary and potentially harmful (the scheduler could interfere with clean shutdown).

**Config path override**: The `--config` flag calls `set_config_path()` before server initialization, allowing the caller to point at a non-default config file. This is useful for isolated test environments or multi-tenant setups.

**Deferred import strategy**: `start_server` and `mcp` are imported inside the `serve` command handler rather than at module level. This prevents `fastmcp` from being pulled in on every `bees` invocation, keeping CLI startup fast for users who have not installed the `[serve]` extra.

**`[serve]` extra guard**: The `serve` subcommand opens with `import fastmcp`. If the package is not installed, Python raises `ImportError` and the handler prints a message directing the user to install `bees-cli[serve]`. Users who only need the ticket CLI commands are not required to install FastMCP.

**`--http` flag**: Starts the HTTP server via uvicorn. See the HTTP Transport Architecture section for full details.

## Repository Root Resolution Strategy

Repository root resolution follows an adapter pattern. `mcp_server.py` owns this responsibility exclusively: each MCP tool adapter resolves the repo root from the client context (via `resolve_repo_root` from `mcp_roots.py`), sets `repo_root_context`, then delegates to the corresponding core function. Core functions read the repo root from the `repo_root_context` contextvar; they have no knowledge of MCP context.

**MCP Roots Protocol Support**:
- The MCP roots protocol is an optional protocol that allows MCP servers to automatically detect which repository the client is working in
- **Implementation**: `get_client_repo_root(ctx)` and `resolve_repo_root(ctx, explicit_root)` live in `src/mcp_roots.py`
  - `get_client_repo_root` reads the roots list from the FastMCP Context and returns the first root as a Path, or None if roots protocol is unsupported
  - `resolve_repo_root` tries roots protocol first, falls back to explicit `repo_root` parameter, raises ValueError if neither is available
- **Client compatibility**:
  - Roots-enabled clients (Claude Desktop, OpenCode): Never need to provide `repo_root` parameter
  - Basic MCP clients without roots support: Must provide `repo_root` parameter explicitly

**MCP Adapter Layer**:
- Each tool registered in `mcp_server.py` is a thin adapter: it accepts `ctx` and optional `repo_root` from the MCP client, resolves the repo root, and delegates to a core function
- Core functions (`_create_ticket`, `_update_ticket`, etc.) are pure business logic with no fastmcp or mcp imports
- No module other than `mcp_server.py` and `mcp_roots.py` imports from `fastmcp` or `mcp`

**Parameter Design**:
- MCP adapter functions in `mcp_server.py` accept `ctx: Context | None` and optional `repo_root: str | None`; they handle resolution and inject it via `repo_root_context`
- Core functions do not accept `ctx` or `repo_root`; they read the repo root from the `repo_root_context` contextvar set by the adapter

## Module Architecture

### mcp_id_utils Module

The `mcp_id_utils` module provides foundational ticket ID parsing utilities extracted from `mcp_server.py` to prevent circular dependencies. This module has zero dependencies on other Bees modules and serves as a base utility layer.

**Design Rationale**:
- Extracted during MCP server refactoring to break circular dependency chains
- Contains frequently-used parsing functions needed by multiple modules
- No external dependencies beyond Python standard library
- Position: Foundational utility with no dependencies

**Functions**:
- `parse_ticket_id(ticket_id: str) -> tuple[str, str]`: Splits ticket ID into type prefix and shortID. Examples: `b.amx` → `("b", "amx")`, `t1.amx.12` → `("t1", "amx.12")`.

**Module Dependencies**:
- Used by: `mcp_server.py`, `paths.py`, validation modules
- Imports: None (Python standard library only)

**File Location**: `src/mcp_id_utils.py`

### repo_utils Module

The `repo_utils` module provides transport-agnostic repository root detection. It contains a single function for path-based git repository discovery.

**Design Rationale**:
- Isolates the git-walk logic so it can be used by any module without pulling in MCP dependencies
- MCP-context-aware functions (`get_client_repo_root`, `resolve_repo_root`, `get_repo_root`) live in `mcp_roots.py` and are re-exported from `repo_utils` for backward compatibility

**Functions**:
- `get_repo_root_from_path(start_path: Path) -> Path`: Walks up the directory tree from the given path looking for a `.git` directory. Returns the repo root if found, or the resolved start path if no git repository exists (supporting scope-based config matching without a git repo).

**Module Dependencies**:
- Used by: `mcp_roots.py`, `mcp_hive_utils.py`, and other modules needing path-based repo detection
- Imports: `pathlib.Path`, `logging`

**File Location**: `src/repo_utils.py`

### mcp_roots Module

The `mcp_roots` module contains all MCP-context-aware repository root detection functions. It is the only non-server module that imports from `fastmcp`/`mcp`.

**Functions**:
- `get_client_repo_root(ctx: Context) -> Path | None`: Extracts repository root from MCP client context using the roots protocol. Returns `None` if the client doesn't support roots or the protocol fails.
- `resolve_repo_root(ctx: Context, explicit_root: str | None) -> Path`: Resolves repo root by trying roots protocol first, then falling back to the explicit parameter. Raises `ValueError` if neither is available.
- `get_repo_root(ctx: Context | None) -> Path | None`: Wrapper for context-optional callers. Uses roots protocol when context is provided; falls back to `get_repo_root_from_path(Path.cwd())` when called without context (tests, CLI).

**Module Dependencies**:
- Used by: `mcp_server.py` (adapter layer)
- Imports: `fastmcp.Context`, `repo_utils.get_repo_root_from_path`

**File Location**: `src/mcp_roots.py`

### mcp_hive_utils Module

The `mcp_hive_utils` module provides hive path validation and filesystem scanning utilities used by MCP server hive operations. Extracted from `mcp_server.py` to isolate hive-specific infrastructure code.

**Design Rationale**: Hive path validation and scanning are shared across multiple hive operations; extracted to avoid duplicating logic in `mcp_server.py`.

**Functions**:
- `validate_hive_path(path: str, repo_root: Path) -> Path`: Validates hive path is absolute, within repository, and has existing parent directory. Returns normalized absolute path. Raises `ValueError` for invalid paths.
- `scan_for_hive(name: str, config: BeesConfig | None = None) -> Path | None`: Recursively searches repository for `.hive` marker matching hive name. Returns hive directory path if found, `None` otherwise. Updates config.json with recovered path when hive is found. Logs warnings for orphaned markers.

**Module Dependencies**:
- Used by: `mcp_server.py` (hive management tools)
- Imports: `pathlib.Path`, `json`, `logging`, `config` module, `repo_utils.get_repo_root_from_path()`

**Integration Points**:
- `colonize_hive()` uses `validate_hive_path()` to ensure hive location is valid before creation
- `scan_for_hive()` provides fallback mechanism when hive path in config.json is stale
- Both functions log detailed information for debugging hive configuration issues

**File Location**: `src/mcp_hive_utils.py`

### mcp_ticket_ops Module

The `mcp_ticket_ops` module contains the core ticket CRUD (Create, Read, Update, Delete) operations extracted from `mcp_server.py`. These are the primary ticket manipulation functions that form the foundation of the ticket management system.

**Design Rationale**: Ticket CRUD is a distinct subsystem extracted from `mcp_server.py` so the server module focuses on MCP tool registration and infrastructure.

**Functions**:
- `_create_ticket()`: Creates new tickets (bee or configured tier types like t1, t2, etc.) with comprehensive validation, hive path verification, write permissions checking, and bidirectional relationship synchronization
- `_update_ticket()`: Updates existing ticket fields with optional parameter sentinel pattern (`_UNSET`), tracking old/new relationships to sync only changes, and atomic file writes
- `_delete_ticket()`: Accepts a single ticket ID or a list of ticket IDs. For each ticket, performs cascade deletion of all children recursively, cleanup of parent and dependency references in related tickets, and proper error handling. When given a single string, returns a single-ticket result. When given a list, returns a bulk response with deleted, not_found, and failed arrays.
- `_show_ticket()`: Accepts a list of ticket ID strings, retrieves complete ticket data for each with hive auto-detection, type inference, and JSON serialization. Returns a bulk response with three lists: `tickets` (resolved ticket data), `not_found` (IDs that could not be located), and `errors` (IDs that were found but failed during egg resolution, with reason).

**Module Dependencies**:
- Used by: `mcp_server.py` (imports and registers as MCP tools via adapter wrappers)
- Imports: `mcp_relationships` (bidirectional sync), `repo_utils` (path-based repo detection for test monkeypatching), `mcp_id_utils` (ticket ID parsing), `ticket_factory`, `reader`, `writer`, `paths`, `config`, `id_utils`

**Integration Points**:
- All four functions are imported by `mcp_server.py` and wrapped in MCP tool adapters
- Functions use `_update_bidirectional_relationships()` from `mcp_relationships` module to maintain consistency
- Functions read repo root from `repo_root_context` (set by `mcp_server.py` adapters before delegation)
- Functions use `parse_ticket_id()` from `mcp_id_utils` for ticket ID parsing

**Key constraints**:
- Functions are async to support concurrent operations
- `_UNSET` sentinel in `_update_ticket()` distinguishes "not provided" from "explicitly None"
- Write operations (`_create_ticket`, `_update_ticket`) are strict and fail-fast; `_delete_ticket` in bulk mode is resilient — IDs that cannot be found are collected in `not_found` and IDs that error during deletion are collected in `failed`, while remaining IDs continue to be processed. Cascade deletion is always enabled to prevent orphaned tickets.

**File Location**: `src/mcp_ticket_ops.py` (~820 lines)

### mcp_move_bee Module

The `mcp_move_bee` module implements bee ticket relocation between hives within the same scope.

**Design Rationale**: Move logic is isolated from ticket CRUD to keep `mcp_ticket_ops` focused on in-place mutations; synchronous core (`_move_bee_core`) is separated from async MCP wrapper to simplify testing.

**Functions**:
- `_move_bee_core(bee_ids, destination_hive)`: Synchronous core logic. Validates destination hive exists, checks that each bee is in the same scope as the destination, and performs filesystem moves via `shutil.move`. Returns a dict with `status`, `moved`, `skipped`, `not_found`, and `failed` lists.
- `_move_bee(bee_ids, destination_hive, ctx, repo_root)`: Async MCP wrapper. Resolves repo root, sets `repo_root_context`, and delegates to `_move_bee_core`.

**Module Dependencies**:
- Used by: `mcp_server.py` (registered as `move_bee` MCP tool)
- Imports: `config` (hive lookup, scope resolution), `id_utils` (ticket ID validation), `repo_utils` (path-based repo detection), `paths` (ticket file location), `repo_context`

**Integration Points**:
- Only bee tickets (`b.` prefix) can be moved; non-bee IDs are rejected with a descriptive failure reason
- Scope validation uses `get_scope_key_for_hive()` to prevent cross-scope moves
- Bees already in the destination hive are silently skipped and reported in `skipped`

**File Location**: `src/mcp_move_bee.py`

### mcp_clone_bee Module

The `mcp_clone_bee` module implements deep cloning of a bee and its full ticket subtree within the same hive or into a named destination hive, assigning fresh IDs, GUIDs, and timestamps to every cloned ticket. Cross-hive cloning includes a compatibility check that rejects the clone if source ticket statuses or tier types are incompatible with the destination hive's configuration; the `force` flag bypasses this check.

**Design Rationale**: Clone logic is isolated from ticket CRUD and move operations because it combines tree traversal, ID remapping, and multi-ticket writes into a single atomic-ish workflow. Synchronous core (`_clone_bee_core`) is separated from async MCP wrapper to simplify testing, following the same pattern as `mcp_move_bee`.

**Key Functions**:
- `_clone_bee_core(bee_id, destination_hive, force)`: Synchronous core logic. Validates the source is a bee-type ticket, resolves the destination hive (defaulting to source hive when omitted), checks scope compatibility, runs a compatibility scan against destination hive config (skipped when `force=True`), collects the full subtree in parent-before-children order, builds an old-to-new ID map with fresh IDs and GUIDs, then writes each cloned ticket with cross-references remapped to new IDs. External cross-references are preserved unchanged.
- `_clone_bee(bee_id, destination_hive, force, resolved_root)`: Async wrapper. Sets `repo_root_context` and delegates to `_clone_bee_core`.

**Module Dependencies**:
- Used by: `mcp_server.py` (registered as `clone_bee` MCP tool)
- Imports: `config` (hive lookup, scope resolution, status and tier resolution), `id_utils` (ID generation and validation), `paths` (ticket file location), `reader` (ticket reading), `writer` (ticket writing), `repo_context`

**Integration Points**:
- Only bee tickets (`b.` prefix) can be cloned; non-bee IDs return `invalid_source_type` error
- Six error types: `invalid_source_type`, `bee_not_found`, `clone_write_error`, `hive_not_found`, `cross_scope_error`, `compatibility_error`
- Root write failure aborts the entire clone; child write failures are collected in `failed` list while remaining children continue
- Internal cross-references (parent, children, dependencies) are remapped to new IDs; external references are preserved
- Cross-hive clones are rejected with `cross_scope_error` when source and destination hives belong to different scopes
- `compatibility_error` response includes `incompatible_status_values` and `incompatible_tier_types` lists; pass `force=True` to bypass

**File Location**: `src/mcp_clone_bee.py`

## Available MCP Tools

### Ticket Operations

- **create_ticket**: Create new ticket (bee or tier types) with automatic relationship synchronization. Requires `hive_name` parameter.
- **update_ticket**: Update existing ticket fields with bidirectional relationship updates
- **delete_ticket**: Delete one or more tickets with cascade deletion of all children and automatic relationship cleanup. Accepts a single ID string or a list of IDs.
- **show_ticket**: Retrieve complete ticket data for a list of ticket IDs. Returns `{"status": "success", "tickets": [...], "not_found": [...], "errors": [...]}` — `tickets` contains full ticket data for each resolved ID, `not_found` lists IDs that could not be located, `errors` lists IDs that exist but failed egg resolution (with reason).
- **get_types**: Read raw child_tiers from global, scope, and hive configuration levels without inheritance resolution
- **set_types**: Set or unset child_tiers configuration at the global, repo_scope, or hive level in ~/.bees/config.json. Config-only operation; no tickets are read or modified.
- **clone_bee**: Deep-clone a bee and its full ticket subtree. Takes `bee_id` (required), `destination_hive` (optional string — destination hive name; defaults to source hive when omitted), and `force` (optional bool — when true, bypasses cross-hive status-value and tier-type compatibility checks). Returns `{"status": "success", "ticket_id": "<new-root-id>", "written": N, "failed": [...]}` on success, with `failed` listing any child tickets that could not be written. Source and destination hives must be in the same scope.
- **resolve_eggs**: Resolve egg field from bee tickets into list of resource strings using configured resolver. Takes `ticket_id` parameter and returns dict with `status`, `ticket_id`, and `resources` (list[str] | None). Uses config resolution order (hive → scope → global → default). Default resolver handles inline conversion (null → null, string → [string], other → [json.dumps(value)]). Custom resolvers invoke subprocess with --repo-root and --egg-value arguments, parse JSON output (array of strings or null), and enforce timeout. See configuration.md for egg_resolver and egg_resolver_timeout config fields.

### Query Operations
- **execute_named_query**: Execute a named query registered in `~/.bees/config.json`
- **execute_freeform_query**: Execute ad-hoc YAML query pipeline without persisting
- **add_named_query**: Register a new named query for reuse
- **delete_named_query**: Delete a named query by name and scope
- **list_named_queries**: List registered named queries, optionally showing all scopes

### Hive Management
- **colonize_hive**: Create and register new hive directory with validation
- **list_hives**: List all registered hives with display names, normalized names, and paths
- **abandon_hive**: Stop tracking a hive without deleting ticket files
- **rename_hive**: Rename hive by updating config and identity markers (ticket IDs remain unchanged)
- **sanitize_hive**: Validate and auto-fix malformed tickets in a hive
- **move_bee**: Move one or more bee tickets to a different hive within the same scope. Takes `bee_ids` (list of bee IDs), `destination_hive` (normalized hive name), and `force` (optional bool — when true, bypasses cross-hive status-value and tier-type compatibility checks). Before any moves are performed, bees scans the source tree against the destination hive's configuration; if any bee has incompatible status values or tier types, all moves are aborted with a `compatibility_error`. Pass `force=True` to skip that check. Returns counts of moved, skipped, not_found, and failed tickets. Error types: `hive_not_found`, `cemetery_destination`, `compatibility_error`.

### Utility
- **generate_index**: Generate markdown index of all tickets with optional filters. When `hive_name` is provided, generates index for that hive only. When `hive_name` is omitted (global mode), iterates all registered hives and generates index for each. The response always includes `status`, `markdown`, and `skipped_hives` keys (`skipped_hives` is always an empty list).
- **health_check**: Check server health status and readiness

## CLI Entry Point

The `bees` command is registered as a Poetry script pointing to `src/cli.py`. This file is the sole entry point for all CLI operations and has no MCP dependencies.

argparse dispatches each subcommand (`create-ticket`, `show-ticket`, `update-ticket`, `delete-ticket`, `get-types`, `set-types`, `serve`) to a dedicated handler function. The ticket subcommands use `asyncio.run()` to bridge into the async execution model. The `serve` subcommand is synchronous — it blocks on `mcp.run(transport="stdio")` until the client process exits.

Output is always written as JSON to stdout. Errors are also written to stdout as a JSON error dict — nothing goes to stderr. This keeps CLI output pipeable and machine-readable with no mixed-stream surprises.

The CLI handlers call the same core functions used by the MCP adapter layer (`_create_ticket`, `_show_ticket`, `_update_ticket`, `_delete_ticket`, `_get_types`, `_set_types`). There is no separate CLI business logic — the CLI is a different entry point into the same shared implementation.

## Server Startup and CLI Integration

**Entry point architecture**: Both `bees serve --stdio` and `bees serve --http` live in the `serve` subcommand handler in `src/cli.py`. The `--http` path adds undertaker scheduler startup and signal handling on top of the shared server initialization. There is no standalone `src/main.py` entry point for the HTTP server.

**Per-hive integrity model**: The server always starts regardless of hive state. Use `sanitize_hive` to detect and repair corruption in a specific hive.

**Signal handling** registers SIGINT and SIGTERM handlers to ensure cleanup before exit, supporting standard Unix process management.

## Relationship Synchronization

The relationship synchronization module (`src/relationship_sync.py`) provides core functionality for maintaining bidirectional consistency of all ticket relationships. Shared by create/update/delete MCP tools to ensure atomicity and data integrity.

**Key Functions**:
- `add_child_to_parent()`, `remove_child_from_parent()`: Handle parent-child relationships with idempotency
- `add_dependency()`, `remove_dependency()`: Handle dependency relationships bidirectionally
- `validate_ticket_exists()`, `validate_parent_child_relationship()`, `check_for_circular_dependency()`: Enforce rules and prevent cycles

**Batch Operations**: `sync_relationships_batch()` handles multiple relationship updates atomically using seven-phase execution: validation, loading, deduplication, backup (WAL), update, write-with-rollback, and cleanup.

For complete details, see `relationships.md`.

## Query System Integration

The MCP server exposes query operations through `execute_named_query()` and `execute_freeform_query()` tools. The query system implements a multi-stage pipeline for filtering and traversing tickets using search terms (type=, id=, title~, tag~, parent=) and graph terms (parent, children, up_dependencies, down_dependencies).

For complete architecture details, see `queries.md`.
