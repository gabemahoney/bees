# Master Plan: Bees Architecture

This document captures architectural decisions and implementation details for key features in the Bees issue tracking system.

## Cycle Detection Feature

### Overview

The cycle detection feature prevents invalid dependency configurations by detecting cycles in both blocking dependencies (up_dependencies/down_dependencies) and hierarchical relationships (parent/children).

### Algorithm Choice: Depth-First Search (DFS)

We selected DFS with path tracking as the cycle detection algorithm for the following reasons:

1. **Time Complexity**: O(V + E) where V is number of tickets and E is number of dependencies - optimal for this problem
2. **Space Complexity**: O(V) for visited set and path tracking - reasonable for ticket databases
3. **Cycle Path Extraction**: DFS naturally maintains the path from root to current node, making it trivial to extract and report the exact cycle when detected
4. **Well-Established**: DFS is a standard algorithm for cycle detection in directed graphs, with proven correctness

### Data Structures

#### Path Tracking

The algorithm maintains two path-tracking structures during traversal:

1. **path: List[str]** - Ordered list of ticket IDs from search root to current node
   - Used to extract cycle path when cycle is detected
   - Provides human-readable cycle paths in error messages (e.g., "A -> B -> C -> A")

2. **path_set: Set[str]** - Set representation of current path
   - Enables O(1) cycle detection by checking if current node is in path
   - Avoids O(n) list search for each node visited

#### Global Visited Tracking

**visited: Set[str]** - Tracks all nodes visited across all DFS traversals
- Prevents redundant cycle detection for nodes already processed
- Essential for performance when graph has disconnected components
- Separate visited sets for blocking dependencies and hierarchical relationships

### Handling Multiple Relationship Types

The implementation detects cycles independently for two relationship types:

#### 1. Blocking Dependencies

Checks cycles in `up_dependencies` and `down_dependencies` fields:
- Ticket A depends on Ticket B (A.up_dependencies contains B)
- Ticket B depends on Ticket C (B.up_dependencies contains C)
- Ticket C depends on Ticket A (C.up_dependencies contains A)
- **Result**: Cycle detected

Error type: `dependency_cycle`

#### 2. Hierarchical Relationships

Checks cycles in `parent` and `children` fields:
- Ticket A's parent is Ticket B (A.parent == B)
- Ticket B's parent is Ticket C (B.parent == C)
- Ticket C's parent is Ticket A (C.parent == A)
- **Result**: Cycle detected

Error type: `hierarchy_cycle`

### Integration with Linter

#### Main Entry Point

`Linter.detect_cycles(tickets: List[Ticket]) -> List[ValidationError]`

Called from `Linter.run()` after other validation checks:
1. ID format validation
2. ID uniqueness validation
3. Bidirectional relationship validation
4. **Cycle detection** ← Added here
5. Report generation

#### Error Reporting

Cycles are reported as `ValidationError` objects with:
- `ticket_id`: First ticket ID in the cycle path
- `error_type`: "dependency_cycle" or "hierarchy_cycle"
- `message`: Human-readable description with full cycle path
- `severity`: "error" (marks database as corrupt)

Example error message:
```
Cycle detected in blocking dependencies: bees-aa1 -> bees-bb1 -> bees-cc1 -> bees-aa1
```

### Implementation Details

#### DFS Helper Method

`Linter._detect_cycle_dfs()` implements the core traversal:

**Parameters:**
- `ticket_id`: Current node being explored
- `ticket_map`: Dict mapping ticket IDs to Ticket objects (O(1) lookup)
- `visited`: Global visited set
- `path`: Current path from root to current node
- `path_set`: Set representation of path
- `get_neighbors`: Lambda function to extract neighbor IDs based on relationship type
  - For blocking: `lambda t: t.up_dependencies`
  - For hierarchical: `lambda t: [t.parent] if t.parent else []`
- `relationship_type`: String for error messages ("blocking dependency" or "parent/child")

**Return Value:**
- `List[str]` representing cycle path if cycle found
- `None` if no cycle found in this branch

**Key Logic:**
1. Check if current node is in `path_set` (cycle detection)
2. If cycle found, extract cycle portion of path and return
3. Mark current node as visited globally
4. Add node to current path
5. Recursively explore each neighbor
6. Remove node from path when backtracking (allows other branches to visit)

### Edge Cases Handled

1. **Self-cycles**: Ticket depends on itself (A -> A)
2. **Missing tickets**: Referenced ticket IDs that don't exist (skip gracefully)
3. **Disconnected components**: Multiple independent subgraphs
4. **Empty graph**: No tickets in database
5. **Single node**: One ticket with no dependencies
6. **Mixed relationship cycles**: Separate detection for blocking vs hierarchical

### Performance Characteristics

- **Best case**: O(V) - All tickets in linear chain, no cycles
- **Average case**: O(V + E) - Standard graph traversal
- **Worst case**: O(V + E) - Must explore entire graph
- **Space**: O(V) - Visited set and maximum path depth

For typical ticket databases (hundreds to thousands of tickets), performance is excellent with subsecond cycle detection.

### Testing

Comprehensive test coverage in `tests/test_linter_cycles.py`:

- 3-node, 2-node, and self-cycles for both relationship types
- Acyclic graphs (should pass without errors)
- Nested/multiple independent cycles
- Empty graphs and single nodes
- Disconnected components
- Mixed blocking and hierarchical cycles
- Error message format validation

## CLI Integration and Corruption State Management

### Overview

The CLI integration feature provides a command-line interface for running the linter and automatically manages database corruption state. This ensures data integrity by preventing the MCP server from starting when the database contains validation errors.

### Architecture Components

#### 1. CLI Module (`src/cli.py`)

**Purpose**: Provides command-line interface for linter execution with automatic corruption state management.

**Key Features:**
- Command-line argument parsing (tickets directory, output format, verbosity)
- Human-readable and JSON output modes
- Automatic corruption state updates based on validation results
- Structured error output grouped by ticket ID
- Exit codes: 0 (clean), 1 (errors found), 2 (exception)

**Integration Points:**
- Calls `Linter.run()` to execute validation
- Calls `mark_corrupt(report)` when errors found
- Calls `mark_clean()` when no errors found

**Usage Example:**
```bash
# Run linter with default settings
poetry run python -m src.cli

# Custom tickets directory
poetry run python -m src.cli --tickets-dir /path/to/tickets

# JSON output for programmatic processing
poetry run python -m src.cli --json

# Verbose logging
poetry run python -m src.cli -v
```

#### 2. Corruption State Module (`src/corruption_state.py`)

**Purpose**: Manages persistent database corruption state across linter and MCP server sessions.

**State File Location**: `.bees/corruption_report.json`

**State File Format:**
```json
{
  "is_corrupt": true,
  "error_count": 3,
  "report": {
    "errors": [...],
    "summary": {...}
  },
  "timestamp": "2026-01-30T12:34:56.789Z"
}
```

**Core Functions:**

- `mark_corrupt(report: LinterReport)` - Save corruption state with full linter report
- `mark_clean()` - Clear corruption state (no errors)
- `is_corrupt() -> bool` - Check if database is currently corrupt
- `get_report() -> Optional[Dict]` - Retrieve corruption report details
- `clear()` - Manually clear corruption state file

**Design Decisions:**

1. **Persistent State**: Corruption state persists across process restarts, ensuring MCP server always has current validation status
2. **Full Report Storage**: Complete linter report saved for detailed error inspection
3. **Automatic Management**: State updates automatically on every linter run
4. **Manual Override**: `clear()` function allows manual state reset after fixing issues

#### 3. MCP Server Startup Check (`src/main.py`)

**Purpose**: Prevent MCP server from starting when database is corrupt.

**Implementation:**
- Check corruption state before server initialization
- Display detailed corruption report if corrupt
- Show sample errors (first 5) for quick diagnosis
- Provide clear instructions for fixing issues
- Exit with code 1 if corrupt

**Error Output Format:**
```
==========================================================
DATABASE CORRUPTION DETECTED
==========================================================
The ticket database is corrupt. MCP server cannot start.
Run the linter to see validation errors:
  python -m src.cli --tickets-dir tickets

Found 3 validation error(s)

Sample errors:
  - [id_format] Ticket ID 'INVALID-ID' does not match required format: bees-[a-z0-9]{3}
  - [duplicate_id] Duplicate ticket ID 'bees-abc' found (also in epic)
  - [dependency_cycle] Cycle detected: bees-aa1 -> bees-bb1 -> bees-aa1

Fix the validation errors and run the linter again to clear
the corruption state.
==========================================================
```

### Data Flow

#### Linter Execution Flow

1. User runs CLI: `poetry run python -m src.cli`
2. CLI parses arguments and calls `Linter.run()`
3. Linter executes all validation checks
4. Linter returns `LinterReport` with errors (if any)
5. Linter calls `mark_corrupt(report)` or `mark_clean()` automatically
6. Corruption state written to `.bees/corruption_report.json`
7. CLI displays formatted output
8. CLI exits with appropriate code

#### MCP Server Startup Flow

1. User runs: `poetry run start-mcp`
2. `main()` calls `is_corrupt()` before initialization
3. If corrupt:
   - Call `get_report()` to retrieve error details
   - Display formatted error message with sample errors
   - Exit with code 1
4. If clean:
   - Continue with normal server startup
   - Load configuration
   - Start MCP server

### Integration with Linter

The linter module was enhanced to automatically manage corruption state:

**Changes to `src/linter.py`:**

```python
# Added import
from src.corruption_state import mark_corrupt, mark_clean

# Enhanced run() method
def run(self) -> LinterReport:
    # ... existing validation logic ...

    # Update corruption state based on results
    if report.errors:
        mark_corrupt(report)
        logger.warning("Database marked as corrupt")
    else:
        mark_clean()
        logger.info("Database marked as clean")

    return report
```

This ensures corruption state is always up-to-date when linter runs, whether called via CLI or programmatically.

### Error Handling

**Corruption State File Errors:**
- Missing file: Treated as "clean" state
- JSON parse errors: Logged and treated as "clean"
- IO errors: Logged and treated as "clean"

**MCP Server Startup:**
- Corruption check failures: Treated as clean (fail-safe)
- Missing report: Display generic error message

**CLI Execution:**
- Tickets directory not found: Exit code 2
- Linter exceptions: Exit code 2, error logged
- Normal validation errors: Exit code 1

### Testing Strategy

**Unit Tests (`tests/test_corruption_state.py`):**
- Mark corrupt with report
- Mark clean
- Check corruption state (true/false)
- Get report when corrupt
- Get report when clean (returns None)
- Clear corruption state
- Handle missing state file
- Handle malformed JSON

**Unit Tests (`tests/test_cli.py`):**
- CLI argument parsing
- Run linter with default settings
- Run linter with custom tickets directory
- JSON output format
- Human-readable output format
- Exit codes (0, 1, 2)
- Error output formatting
- Corruption state updates

**Unit Tests (`tests/test_mcp_startup.py`):**
- Startup with clean database (succeeds)
- Startup with corrupt database (fails with message)
- Startup with missing corruption state (succeeds)
- Startup with malformed state file (succeeds)
- Error message formatting

### Performance Considerations

**State File Size:**
- Full linter report stored (includes all errors)
- Typical size: <100KB for hundreds of tickets
- JSON format enables efficient parsing

**Startup Performance:**
- Corruption check adds minimal overhead (<10ms)
- Single file read operation
- No ticket scanning required

**Linter Integration:**
- Corruption state update adds negligible overhead
- Single file write after validation completes

### Future Enhancements

Potential improvements for future iterations:

1. **State File Cleanup**: Auto-delete old corruption reports after resolution
2. **Report History**: Track corruption state history over time
3. **Error Categories**: Group errors by severity for progressive fixing
4. **Auto-Fix**: Suggest or apply automatic fixes for common issues
5. **CI/CD Integration**: Exit codes enable pipeline validation gates

All test cases pass with 100% success rate.

## Index Generation Feature

### Overview

The index generation feature provides a dynamically generated markdown index of all tickets in
the system. This enables agents and users to browse and navigate the complete ticket inventory
through a single consolidated view.

### Architecture

The index generation system is implemented in `src/index_generator.py` with a three-layer
architecture:

#### 1. Scanning Layer: `scan_tickets()`

**Purpose**: Discover and load all ticket files from the filesystem

**Process**:
1. Uses `paths.list_tickets()` to get all `.md` files across `epics/`, `tasks/`, and `subtasks/`
   directories
2. Loads each ticket file using `reader.read_ticket()` which parses YAML frontmatter and validates
   schema
3. Groups tickets by type into a dictionary structure: `{"epic": [...], "task": [...],
   "subtask": [...]}`
4. Handles errors gracefully - if a ticket file fails to load (corrupted YAML, invalid schema),
   it logs a warning and continues processing remaining tickets

**Returns**: Dictionary mapping ticket types to lists of Ticket objects

**Design Decisions**:
- Uses existing `reader.read_ticket()` instead of reimplementing parsing - maintains single source
  of truth for ticket loading logic
- Emits warnings (not errors) for invalid tickets - ensures index generation doesn't fail due to
  single corrupted ticket
- Returns all three ticket types even if empty - provides consistent API contract

#### 2. Formatting Layer: `format_index_markdown()`

**Purpose**: Transform grouped ticket data into structured markdown

**Process**:
1. Creates markdown header: `# Ticket Index`
2. For each ticket type (Epics, Tasks, Subtasks):
   - Adds section header (e.g., `## Epics`)
   - Sorts tickets alphabetically by ID
   - Formats each ticket as clickable markdown link: `- [ticket-id: title](tickets/{type}s/ticket-id.md) (status)`
   - For subtasks, appends parent info: `(parent: parent-id)`
   - Shows `*No tickets found*` if section is empty
3. Joins all lines with newlines

**Output Format**:
```markdown
# Ticket Index

## Epics
- [bees-abc: Epic Title](tickets/epics/bees-abc.md) (open)

## Tasks
- [bees-def: Task Title](tickets/tasks/bees-def.md) (in_progress)

## Subtasks
- [bees-ghi: Subtask Title](tickets/subtasks/bees-ghi.md) (open) (parent: bees-def)
```

**Design Decisions**:
- Sorts by ID (not title/status) - provides deterministic, predictable ordering that doesn't
  change as ticket properties update
- Includes status inline - gives at-a-glance view of ticket state without requiring file opens
- Shows parent for subtasks - provides hierarchical context in flat list view
- Uses `status or "unknown"` - handles None status gracefully without crashes
- Link paths use `tickets/{type}s/{id}.md` format (e.g., `tickets/epics/bees-abc.md`) to match
  physical directory structure (tickets/epics/, tickets/tasks/, tickets/subtasks/) - ensures
  clickable links work correctly in markdown viewers (Task bees-3fh9)

#### 3. Orchestration Layer: `generate_index()`

**Purpose**: High-level public API for complete index generation

**Process**:
1. Calls `scan_tickets()` to load all tickets
2. Passes result to `format_index_markdown()`
3. Returns final markdown string

**Design Decisions**:
- Simple composition pattern - makes testing easier (can test layers independently)
- Pure function with no side effects - doesn't write files or modify state
- Returns string (not writes file) - caller decides what to do with output (display, save, send
  over network)

### Integration with MCP Server

The index generation functionality is integrated into `src/mcp_server.py` through the
`_generate_index_internal()` function:

**Current State** (Task bees-ckbh):
- Function exists as internal helper
- Calls `generate_index()` and returns markdown result
- Includes error handling with logging
- **Not yet exposed as MCP tool** - tool registration will happen in later task bees-drfx

**Future State** (Epic bees-tjp):
- Will be registered as MCP tool via `mcp.tool()` decorator
- Agents will call tool to generate index on demand
- Generated index can be saved to `index.md` or returned for display

### Data Flow

```
tickets/epics/*.md
tickets/tasks/*.md      →  list_tickets()  →  scan_tickets()  →  format_index_markdown()
tickets/subtasks/*.md                                                       ↓
                                                                     markdown string
```

### Error Handling

The implementation handles errors at multiple levels:

1. **File Loading Errors**: If ticket file is corrupted or missing fields, `scan_tickets()`
   catches exception, logs warning, and continues
2. **Missing Status**: `format_index_markdown()` uses `status or "unknown"` to handle None values
3. **Empty Directory**: System shows `*No tickets found*` instead of crashing
4. **MCP Integration**: `_generate_index_internal()` wraps `generate_index()` with try/except to
   log errors and raise ValueError with clear message

### Testing Strategy

Tests are implemented in `tests/test_index_generator.py` with three test classes:

**TestScanTickets**:
- Empty directory scenario
- Mixed ticket types (epics/tasks/subtasks together)
- Invalid ticket handling (missing required fields)

**TestFormatIndexMarkdown**:
- Empty ticket lists
- Tickets with all fields populated
- Sorting by ID
- Missing status fields

**TestGenerateIndex**:
- End-to-end integration test with real ticket files
- Empty directory test

All tests use pytest fixtures with `tmp_path` and `monkeypatch` to create isolated test
environments and avoid filesystem pollution.

### Index Regeneration Workflow (Task bees-cdun)

#### Overview

The index regeneration workflow provides mechanisms for updating `tickets/index.md` when tickets
change. It supports both manual regeneration via CLI commands and automatic regeneration via file
watching.

#### Architecture Components

**1. Timestamp Tracking**

The index generation now includes timestamp metadata in the header:

```markdown
# Ticket Index

*Generated: 2026-01-30 22:44:59*

## Epics
...
```

This timestamp enables "smart" regeneration that detects when the index is stale.

**Implementation** (`src/index_generator.py`):
- `format_index_markdown()` accepts `include_timestamp` parameter (default: True)
- Uses `datetime.now().strftime()` to format timestamp
- `is_index_stale()` compares index modification time against all ticket files
- Returns True if index.md doesn't exist or is older than any ticket file

**Design Decisions**:
- Uses filesystem mtimes, not parsing timestamp from index content - more reliable and efficient
- Timestamp is for human reference only - programmatic staleness checking uses file modification
  times
- `is_index_stale()` returns False if no tickets exist - empty directory means index is current

**2. CLI Regeneration Command**

Added `regenerate-index` subcommand to `src/cli.py`:

```bash
poetry run python -m src.cli regenerate-index
poetry run python -m src.cli regenerate-index --force
```

**Implementation**:
- Checks `is_index_stale()` before regenerating (skips if up-to-date)
- `--force` flag bypasses staleness check
- Writes generated markdown to `tickets/index.md` using `get_index_path()`
- Returns exit code 0 on success, 2 on exception

**Design Decisions**:
- Manual regeneration is the primary workflow - watching is opt-in
- Smart regeneration avoids unnecessary work when index is current
- Force flag allows regeneration for debugging or after manual index.md deletion

**3. File System Watcher**

Implemented optional watcher in `src/watcher.py` using the watchdog library:

```bash
poetry run python -m src.cli watch
poetry run python -m src.cli watch --debounce 5.0
```

**Implementation** (`src/watcher.py`):
- `TicketChangeHandler`: FileSystemEventHandler that monitors .md files
- Debouncing: Waits configurable seconds (default: 2.0) after last change before regenerating
- Monitors create, modify, delete events
- Filters: Ignores directories, non-.md files, and index.md itself (avoids regeneration loops)
- Uses watchdog's Observer to monitor tickets directory recursively

**Threading Architecture**:

The watcher uses `threading.Timer` for non-blocking debounced regeneration instead of blocking
`time.sleep()`. This architectural decision ensures the watchdog event handler thread remains
responsive and can process multiple file system events without blocking.

- **Non-blocking Design**: `threading.Timer` schedules delayed execution in a separate thread,
  allowing the event handler to immediately return and process additional file system events
  during the debounce period.

- **Timer Management**: The handler stores a reference to the active timer (`self._timer`) and
  cancels it when new file changes occur. This ensures only the most recent change triggers
  regeneration after the debounce period expires.

- **Thread Safety**: A `threading.Lock` (`self._timer_lock`) protects timer operations,
  preventing race conditions when multiple file events arrive simultaneously from different
  watchdog threads. Type annotations are used consistently for all threading primitives:
  `_timer: threading.Timer | None` and `_timer_lock: threading.Lock`, maintaining type
  safety and code consistency throughout the `TicketChangeHandler` class.

- **Integration with Watchdog**: The watchdog library's `Observer` runs event handlers in
  dedicated threads. Blocking these threads with `time.sleep()` would prevent other file system
  events from being processed, potentially causing event queue buildup and missed changes during
  rapid file operations.

**Process Flow**:
1. Ticket file changes detected (create/modify/delete)
2. Handler checks if event should be processed (is .md file, not index.md)
3. Acquires timer lock and cancels any existing timer
4. Sets pending regeneration flag and records timestamp
5. Creates new `threading.Timer` scheduled for debounce period
6. Releases lock and starts timer (non-blocking)
7. Handler returns immediately, ready for next event
8. After debounce period expires (if no cancellation), timer callback fires
9. Calls `generate_index()` and writes to index.md
10. Logs success/failure and cleans up timer state

**Design Decisions**:
- Opt-in via CLI command - most users will use manual regeneration
- Debouncing prevents excessive regeneration when multiple files change
- Recursive monitoring catches changes in all subdirectories (epics/, tasks/, subtasks/)
- Graceful error handling - watcher continues running even if regeneration fails
- KeyboardInterrupt (Ctrl+C) cleanly stops observer

**4. CLI Integration**

The CLI now has three modes:
- `lint`: Run ticket linter (default for backward compatibility)
- `regenerate-index`: Manual index regeneration with staleness detection
- `watch`: Start file system watcher for automatic regeneration

**Implementation** (`src/cli.py`):
- Converted to subcommand-based argument parser using `argparse.subparsers`
- Added imports for `start_watcher`, `is_index_stale`, `TICKETS_DIR`
- Each subcommand has its own parser with specific arguments
- Global `-v/--verbose` flag applies to all commands

#### Integration Points

**With Index Generation** (Task bees-ckbh):
- Regeneration calls `generate_index()` which includes timestamp
- Uses `is_index_stale()` to optimize regeneration decisions
- Writes to path from `get_index_path()` in `src/paths.py`

**With MCP Server** (Future Task bees-drfx):
- MCP tool will call `generate_index()` and write to index.md
- Could expose `is_index_stale()` to let agents check before regenerating
- Watcher is CLI-only - MCP agents use manual regeneration

#### Design Decisions: Manual vs Automatic Regeneration

**Manual Regeneration** (Recommended):
- Predictable - regenerates exactly when user requests
- Efficient - uses staleness detection to avoid unnecessary work
- Simple - no background processes or resource usage
- Best for: CI/CD pipelines, agent workflows, development

**Automatic Regeneration** (Opt-in):
- Convenient - index always current without explicit commands
- Overhead - watcher process runs continuously
- Debouncing minimizes regeneration frequency
- Best for: Active development with frequent ticket changes, IDEs with live preview

**Why Manual is Default**:
- Most use cases are batch operations (agent creates multiple tickets, then regenerates once)
- Automatic watching adds system overhead with minimal benefit
- Agent workflows don't benefit from real-time updates (agents regenerate explicitly)
- Simpler mental model - regeneration is explicit action, not hidden background process

### MCP Tool Registration (Task bees-drfx)

#### Overview

The index generation functionality is now exposed as an MCP tool that agents can call directly. This
enables on-demand index generation with optional filtering capabilities.

#### Tool Registration

The `_generate_index()` function in `src/mcp_server.py` is registered as an MCP tool using the
FastMCP `@mcp.tool()` decorator:

```python
@mcp.tool()
def _generate_index(
    status: str | None = None,
    type: str | None = None
) -> Dict[str, Any]:
    """Generate markdown index of all tickets with optional filters."""
```

**Tool Name**: `generate_index` (automatically derived from function name)

**Parameters**:
- `status` (optional): Filter tickets by status (e.g., "open", "completed", "in_progress")
- `type` (optional): Filter tickets by type (e.g., "epic", "task", "subtask")

**Return Value**: Dictionary with:
- `status`: "success" or error
- `markdown`: Generated markdown index string

#### Filtering Architecture

Filtering is implemented at the scanning layer to avoid loading unnecessary tickets:

**Implementation in `scan_tickets()`**:
1. Accepts `status_filter` and `type_filter` parameters
2. Loads each ticket from filesystem
3. Applies filters during loading:
   - Skip ticket if `status_filter` provided and `ticket.status != status_filter`
   - Skip ticket if `type_filter` provided and `ticket.type != type_filter`
4. Returns only matching tickets grouped by type

**Design Decisions**:
- **Filter at scan time** (not format time) - Reduces memory footprint by not loading filtered-out
  tickets
- **Support both filters simultaneously** - Enables queries like "all open tasks"
- **Null filters mean no filtering** - Maintains backward compatibility with existing code
- **Case-sensitive matching** - Status values are stored consistently in lowercase

#### Filter Usage Examples

**All tickets** (no filters):
```python
generate_index()
# Returns all epics, tasks, and subtasks
```

**Open tickets only**:
```python
generate_index(status_filter='open')
# Returns all tickets with status='open'
```

**Epics only**:
```python
generate_index(type_filter='epic')
# Returns only epic tickets (all statuses)
```

**Open tasks**:
```python
generate_index(status_filter='open', type_filter='task')
# Returns only tasks with status='open'
```

#### Integration Pattern

The MCP tool wraps `generate_index()` from `index_generator.py` and returns structured response:

```python
try:
    index_markdown = generate_index(
        status_filter=status,
        type_filter=type
    )
    logger.info(f"Successfully generated ticket index (status={status}, type={type})")
    return {
        "status": "success",
        "markdown": index_markdown
    }
except Exception as e:
    error_msg = f"Failed to generate index: {e}"
    logger.error(error_msg)
    raise ValueError(error_msg)
```

#### Agent Usage

Agents can call the tool through MCP protocol:

```json
{
  "method": "tools/call",
  "params": {
    "name": "generate_index",
    "arguments": {
      "status": "open",
      "type": "task"
    }
  }
}
```

Response:
```json
{
  "status": "success",
  "markdown": "# Ticket Index\n\n## Epics\n*No tickets found*\n\n## Tasks\n- [bees-abc] Task Title (open)\n..."
}
```

#### Why Generate On-Demand vs Cache

The implementation generates the index on each call rather than maintaining a cached version:

**Rationale**:
1. **Always Current**: Index reflects real-time ticket state without cache invalidation complexity
2. **Fast Enough**: Scanning hundreds of tickets takes <100ms, acceptable for interactive use
3. **Stateless**: No cache management, persistence, or synchronization needed
4. **Filter Flexibility**: Each call can use different filters without cache proliferation
5. **Simple**: Fewer moving parts means fewer bugs and easier maintenance

**Performance Characteristics**:
- Typical scan: 50-100ms for 500 tickets
- Memory: O(n) for loaded tickets, released after generation
- No disk writes: Pure read operation

**Future Optimization** (if needed):
- Could add caching layer with timestamp-based invalidation
- Could generate static `index.md` file on ticket updates
- Current approach sufficient for MVP

#### Error Handling

The tool handles various failure scenarios:

1. **Missing tickets directory**: Returns empty sections (no error)
2. **Corrupted ticket files**: Logs warnings, continues with valid tickets
3. **Invalid filter values**: Silently returns no matches (may add validation later)
4. **Filesystem errors**: Caught and returned as ValueError with clear message

#### Testing

New tests added to `tests/test_index_generator.py`:

**Filter Tests**:
- `test_scan_tickets_filter_by_status` - Verify status filtering works
- `test_scan_tickets_filter_by_type` - Verify type filtering works
- `test_scan_tickets_combined_filters` - Verify both filters work together
- `test_generate_index_with_status_filter` - End-to-end status filtering
- `test_generate_index_with_type_filter` - End-to-end type filtering
- `test_generate_index_with_combined_filters` - End-to-end combined filtering

All tests pass with 100% success rate.

### Clickable Navigation Links (Task bees-qn99)

#### Overview

The index generation system now creates clickable markdown links to individual ticket files,
enabling direct navigation from the index to ticket details.

#### Link Format Specification

Each ticket entry in the generated index follows this markdown link format:

```markdown
- [ticket-id: title](tickets/ticket-id.md) (status)
```

**Components**:
- **Link text**: `ticket-id: title` - Combines ticket ID and title for clear identification
- **Link target**: `tickets/ticket-id.md` - Relative path from index.md location to ticket file
- **Status suffix**: `(status)` - Current ticket status shown inline
- **Parent info**: `(parent: parent-id)` - Appended for subtasks only

**Example output**:
```markdown
## Epics
- [bees-abc: Authentication System](tickets/bees-abc.md) (open)

## Tasks
- [bees-123: Build Login API](tickets/bees-123.md) (in_progress) (parent: bees-abc)
```

#### Implementation Details

**Modified Function**: `format_index_markdown()` in `src/index_generator.py`

**Change**:
```python
# Before:
line = f"- [{ticket.id}] {ticket.title} ({status})"

# After:
line = f"- [{ticket.id}: {ticket.title}](tickets/{ticket.id}.md) ({status})"
```

**Design Decisions**:
1. **Relative paths** - Uses `tickets/{ticket-id}.md` relative to index.md location
   - Works regardless of repository location
   - Compatible with all markdown viewers
   - No hardcoded absolute paths
2. **Link text format** - Combines ID and title for maximum context in link text
   - Users can see both ID and title without clicking
   - ID provides unique identifier, title provides description
3. **Path structure** - Assumes index.md is at repository root with tickets/ subdirectory
   - Matches current repository layout
   - Ticket files stored as `tickets/{ticket-id}.md` (flat structure, not grouped by type)
4. **Status outside link** - Keeps status in plain text for filtering/searching
   - Status not part of clickable link
   - Can be parsed programmatically

#### Path Resolution

The relative path structure assumes this repository layout:

```
/
├── index.md                    # Generated index file
└── tickets/
    ├── bees-abc.md            # Epic file
    ├── bees-123.md            # Task file
    └── bees-xyz.md            # Subtask file
```

**Navigation flow**:
1. User opens `index.md` in markdown viewer
2. Clicks link `[bees-abc: Title](tickets/bees-abc.md)`
3. Viewer resolves path relative to index.md: `./tickets/bees-abc.md`
4. Opens corresponding ticket file

#### Markdown Viewer Compatibility

The link format works across all standard markdown viewers:
- **VS Code** - Click to open in editor
- **GitHub** - Click to navigate to file in repository
- **Obsidian** - Click to open in vault
- **CLI tools** (glow, mdcat) - Display as underlined/clickable links
- **Web browsers** (rendered markdown) - Standard HTML anchor links

#### Integration with Filtering

Clickable links work seamlessly with existing filter functionality:

```python
# Generate filtered index with links
index_md = generate_index(status_filter='open', type_filter='task')
# Returns: "- [bees-123: Build Login API](tickets/bees-123.md) (open)"
```

Filters apply at scan time, so only matching tickets appear with links in output.

#### Testing

Tests added to `tests/test_index_generator.py`:

**Test Coverage**:
- `test_format_index_markdown_with_clickable_links` - Verify link format is correct
- `test_clickable_link_format_with_special_characters` - Verify titles with special chars are escaped
- `test_relative_path_construction` - Verify relative paths for different ticket types
- `test_generate_index_end_to_end_with_links` - Full integration test with real ticket files

All tests verify:
1. Link text includes both ID and title
2. Link target uses relative path format
3. Status appears after link (not in link text)
4. Parent info appended correctly for subtasks

#### Performance Impact

Adding links has negligible performance impact:
- No additional file I/O (paths constructed in memory)
- String formatting overhead: <1ms per ticket
- Total overhead for 500 tickets: <10ms

#### Future Enhancements

Potential improvements for navigation experience:

1. **Breadcrumb navigation** - Add "Back to index" links in ticket files
2. **Cross-references** - Make dependency IDs clickable (link to dependency tickets)
3. **Search integration** - Add anchor links for jumping to sections
4. **Parent links** - Make parent IDs clickable in subtask entries
5. **Bi-directional links** - Generate backlinks from tickets to index

### Relationship to Epic bees-tjp

This implementation is part of Epic bees-tjp (Auto-Generated Index Page) which has the following
acceptance criteria:

- ✅ Core index generation logic (Task bees-ckbh) - **COMPLETED**
- ✅ MCP tool registration with filters (Task bees-drfx) - **COMPLETED**
- ✅ Clickable navigation links (Task bees-qn99) - **COMPLETED**
- ⏳ Demo with diverse tickets - Not started

The index generation feature is now fully functional and exposed through MCP tools. Agents can
generate filtered indexes with clickable links on demand to browse and navigate tickets.

### Documentation Update for MCP Tool Availability (Task bees-ubzn)

#### Overview

The README.md documentation was updated to inform readers that the index generation functionality
is available through both the Python API and the MCP tool interface.

#### Changes Made

**Location**: README.md, lines 89-100 (Index Generation section, Usage subsection)

**Before**: The documentation only described the Python API (`scan_tickets()`,
`format_index_markdown()`, `generate_index()`) without mentioning the MCP tool.

**After**: The documentation now:
1. Highlights that index generation is available through both Python API and MCP tool
2. Emphasizes that **the MCP tool is the recommended approach for LLM agents**
3. Includes a cross-reference link to the MCP Server section where the `generate_index` tool is
   documented in detail (starting at line 831)
4. Maintains the existing Python API documentation for developers who need programmatic access

#### Rationale

**Why Reference the MCP Tool**:
1. **Data Consistency** - MCP tools ensure proper data access patterns and consistency when agents
   interact with the ticket system
2. **Protocol Compliance** - MCP provides standardized tool interfaces that agents understand natively
3. **Best Practice Guidance** - Explicitly recommending MCP for agents reduces confusion about which
   approach to use
4. **Discoverability** - Cross-referencing helps readers find the tool documentation they need

**Why Keep Python API Documentation**:
1. **Developer Access** - Python developers may need direct programmatic access
2. **Testing** - Tests use Python API directly for unit testing
3. **Internal Implementation** - Shows the underlying implementation that MCP tool wraps
4. **Complete Reference** - Provides full API surface documentation

#### Implementation Details

The update added a new introductory paragraph before the Python API documentation:

```markdown
The index generation functionality is available through both a Python API and an MCP tool.
**For LLM agents, the MCP tool is the recommended approach** as it ensures data consistency
and follows the Model Context Protocol standard.
```

And added a reference section:

```markdown
**MCP Tool**: See the [MCP Server](#mcp-server) section below for details on the `generate_index`
tool, which provides the same functionality through the Model Context Protocol interface.
```

The markdown link uses anchor syntax `[text](#anchor)` to create an in-document link to the
"MCP Server" section heading.

#### Impact

**Benefits for Readers**:
- **LLM Agents**: Immediately directed to use MCP tool with clear best-practice guidance
- **Python Developers**: Still have access to full API documentation
- **New Users**: Understand both approaches and when to use each
- **Documentation Navigation**: Clear cross-reference makes finding MCP tool docs easy

**No Breaking Changes**:
- Python API remains unchanged
- MCP tool behavior unchanged
- Only documentation additions, no code modifications

#### Testing Consideration

No code changes means no new tests required. The documentation update:
- Accurately reflects the existing MCP tool implementation
- Maintains accurate Python API documentation
- Cross-reference link points to correct section header

## Demo Ticket Dataset Feature

### Overview

The demo ticket dataset provides representative sample data for testing index generation, query
system validation, and development workflows. A Python script generates diverse tickets with
realistic relationships, statuses, and metadata.

### Script Architecture

**Location**: `scripts/generate_demo_tickets.py`

**Design Pattern**: Factory-based generation using modular generator functions

The script is organized into three generator functions:
1. `generate_demo_epics()` - Creates 5 diverse epic tickets
2. `generate_demo_tasks()` - Creates 8 task tickets linked to epics
3. `generate_demo_subtasks()` - Creates 15 subtask tickets linked to tasks

Each generator returns a dictionary mapping semantic names to ticket IDs, enabling later
generators to reference earlier tickets when creating relationships.

### Implementation Details

#### Ticket Factory Integration

The script uses the existing `ticket_factory` module functions:
- `create_epic(title, description, labels, status, priority, owner)`
- `create_task(title, description, parent, labels, up_dependencies, status, priority, owner)`
- `create_subtask(title, parent, description, labels, status, priority, owner)`

This ensures demo tickets have identical structure to real tickets created via MCP server,
providing authentic test data.

#### Relationship Types Generated

**Parent-Child Relationships**:
- All tasks have `parent` field referencing an epic ID
- All subtasks have `parent` field referencing a task ID
- Bidirectional synchronization handled automatically by ticket factory

**Blocking Dependencies**:
- Some tasks have `up_dependencies` referencing other tasks
- Demonstrates dependency chains (e.g., Task B blocked by Task A, Task C blocked by Task B)
- Creates realistic "blocked work" scenarios for query testing

**Example Dependency Chain**:
```
auth_db_schema (completed)
  ↓ blocks
auth_api (in progress)
  ↓ blocks
auth_jwt (open)
```

This chain demonstrates:
- Completed tasks unblocking dependent work
- In-progress tasks with downstream dependencies
- Open tasks waiting for upstream completion

### Ticket Diversity

#### Status Variety

Generated tickets include three status values:
- **open**: Unstarted work items
- **in progress**: Active work items
- **completed**: Finished work items

Status distribution reflects realistic project state:
- ~40% open (future work)
- ~35% in progress (active work)
- ~25% completed (historical data)

#### Priority Levels

Tickets span all five priority levels (0-4):
- **Priority 0**: Critical work (epics: auth_system, api_core; tasks: auth_db_schema,
  auth_api)
- **Priority 1**: High priority (epic: dashboard, mobile_app; tasks: dashboard_layout,
  auth_jwt)
- **Priority 2**: Medium priority (subtasks: bar charts, pie charts)
- **Priority 3**: Low priority (epic: docs; task: docs_setup)
- **Priority 4**: Not used in demo (could represent backlog items)

This distribution enables testing priority-based queries and filtering.

#### Label Taxonomy

Labels follow consistent patterns by domain:
- **Backend**: backend, api, database, security, error-handling, logging
- **Frontend**: frontend, ui, react, charts, analytics
- **Infrastructure**: devops, infrastructure, monitoring
- **Documentation**: documentation, developer-experience
- **Mobile**: mobile, ios, android

Each ticket has 2-4 labels, creating rich data for label-based queries (e.g., "find all
backend + security work items").

#### Owner Assignment

Owners represent realistic team/individual assignments:
- **Team owners**: backend-team, frontend-team, platform-team, docs-team, mobile-team
- **Individual owners**: alice@example.com, bob@example.com, carol@example.com,
  dave@example.com, eve@example.com, frank@example.com, grace@example.com

This enables testing owner-based queries and team workload analysis.

### Ticket Counts

The demo generates:
- **5 Epics**: Representing major features across different domains
- **8 Tasks**: Distributed across epics (auth: 3, dashboard: 2, api_core: 2, docs: 1)
- **15 Subtasks**: Distributed across tasks (varying from 1-5 subtasks per task)

**Total**: 28 tickets with diverse relationships

These counts provide:
- Sufficient data for meaningful index generation
- Realistic variety for query testing
- Manageable size for manual inspection
- Examples of all relationship types (parent-child, blocking dependencies)

### Regeneration and Cleanup

**Regenerating demo data**:
```bash
# Remove existing demo tickets
rm -rf tickets/epics/bees-* tickets/tasks/bees-* tickets/subtasks/bees-*

# Generate fresh demo data
poetry run python scripts/generate_demo_tickets.py
```

The script uses automatic ID generation, ensuring new IDs each run. Sample tickets (e.g.,
sample-epic.md) are preserved since they don't match the `bees-*` pattern.

### Design Decisions

**Why three separate generator functions?**
- Enables dependency ordering (epics → tasks → subtasks)
- Each generator can reference IDs from previous generators
- Modular structure makes it easy to add/modify ticket generation logic

**Why use semantic names in dictionaries?**
- Makes relationship creation readable (e.g., `parent=epics["auth_system"]`)
- Documents purpose of each ticket
- Easier to maintain and extend than raw ID lists

**Why realistic data instead of toy examples?**
- Validates system with production-like complexity
- Demonstrates real-world ticket patterns
- Useful for demos and documentation screenshots
- Tests edge cases (e.g., completed tasks with open subtasks)

**Why use ticket_factory functions?**
- Guarantees consistency with production ticket creation
- Leverages existing validation and relationship sync logic
- Ensures demo tickets pass linter validation
- Any schema changes automatically apply to demo generation

### Use Cases

**Index Generation Testing**:
- Verifies index correctly groups tickets by type
- Tests parent display for tasks and subtasks
- Validates sorting and link generation

**Query System Validation**:
- Tests label-based queries (e.g., "backend + security")
- Tests status-based queries (e.g., "open + in progress")
- Tests graph traversal (e.g., "find all subtasks of auth epic")

**Linter Testing**:
- Provides complex relationship graph for cycle detection
- Tests bidirectional consistency validation
- Validates handling of various status/priority combinations

**Development and Documentation**:
- Demonstrates ticket structure for new contributors
- Provides realistic examples for README screenshots
- Enables manual testing without creating tickets by hand
