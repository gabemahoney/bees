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
   - Formats each ticket as: `- [ticket-id] Title (status)`
   - For subtasks, appends parent info: `(parent: parent-id)`
   - Shows `*No tickets found*` if section is empty
3. Joins all lines with newlines

**Output Format**:
```markdown
# Ticket Index

## Epics
- [bees-abc] Epic Title (open)

## Tasks
- [bees-def] Task Title (in_progress)

## Subtasks
- [bees-ghi] Subtask Title (open) (parent: bees-def)
```

**Design Decisions**:
- Sorts by ID (not title/status) - provides deterministic, predictable ordering that doesn't
  change as ticket properties update
- Includes status inline - gives at-a-glance view of ticket state without requiring file opens
- Shows parent for subtasks - provides hierarchical context in flat list view
- Uses `status or "unknown"` - handles None status gracefully without crashes

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

### Relationship to Epic bees-tjp

This implementation is part of Epic bees-tjp (Auto-Generated Index Page) which has the following
acceptance criteria:

- ✅ Core index generation logic (Task bees-ckbh) - **COMPLETED**
- ⏳ MCP tool registration (Task bees-drfx) - Not started
- ⏳ Demo with diverse tickets - Not started

The current implementation provides the foundation for the complete feature. Future tasks will
expose this functionality through MCP tools and demonstrate the full workflow.
