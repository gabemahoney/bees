# Validation Architecture

This document covers the linter infrastructure, index generation, and corruption detection systems that maintain data integrity in the Bees ticket management system.

## Overview

Bees uses three complementary systems to prevent data corruption:

1. **Linter**: Validates ticket schema and relationship consistency
2. **Index Generator**: Creates per-hive markdown indexes with validation
3. **Corruption Detection**: Identifies integrity issues and generates structured reports

These systems work together to ensure the ticket database remains consistent despite having no centralized database or daemon processes.

## Linter Architecture

The linter validates ticket structure and relationships through a two-phase scanning and validation process. Implementation spans `src/linter.py`, `src/linter_report.py`, and integrates with existing reader and ID utilities.

### Core Components

**LinterReport Module** (`src/linter_report.py`):
- `ValidationError` dataclass represents individual validation errors with fields: `ticket_id`, `error_type`, `message`, `severity`
- Severity levels: `error` (critical) or `warning` (non-critical)
- `LinterReport` class collects and queries validation errors
- Methods: `add_error()`, `get_errors()` with filtering, `is_corrupt()` for database health check
- Output formats: `to_json()`, `to_markdown()`, `to_dict()` for different consumers
- Summary statistics via `get_summary()` for error counts by type and severity

**Linter Module** (`src/linter.py`):
- `TicketScanner` class loads tickets from filesystem using `src/reader.py`
- Scans hive root directories (flat storage: `{hive_name}/*.md`)
- Returns generator of typed `Ticket` objects (Epic, Task, Subtask)
- Handles filesystem errors gracefully, logging and skipping invalid files
- `Linter` class orchestrates validation through `run()` method:
  - Loads all tickets via TicketScanner
  - Runs per-ticket validations
  - Runs cross-ticket validations (uniqueness, relationships)
  - Returns `LinterReport` with collected errors

### Validation Rules

**Schema Validation**:
- ID format validation: matches `{hive}.bees-[a-z0-9]{3}` pattern
- Reuses `is_valid_ticket_id()` from `src/id_utils.py` for consistency
- ID uniqueness check across all ticket types

**Relationship Validation**:
- Parent/children bidirectional consistency (added by task bees-ivvz)
- Dependency bidirectional consistency (up_dependencies ↔ down_dependencies)
- Cycle detection in both blocking dependencies and hierarchical relationships (added by task bees-2u6v)

**Hive Validation**:
- Validates ticket IDs match hive prefix format
- Validates cross-hive dependencies respect configuration rules
- Integrates with `sanitize_hive` MCP tool for per-hive checks

### Algorithm Choices

**DFS with Path Tracking**: Selected for cycle detection to achieve O(V+E) time complexity while naturally maintaining the path from root to current node. DFS is proven correct for detecting cycles in directed graphs.

**Dual Representation for Path Tracking**: Uses both a list (ordered cycle extraction) and a set (O(1) cycle detection) to balance human-readable error reporting with performance. Global visited set prevents redundant traversals across disconnected components.

**Separate Passes by Relationship Type**: Runs independent DFS traversals for blocking dependencies versus hierarchical relationships, enabling targeted error messages and preventing false positives from mixing relationship semantics.

### Integration Points

- Uses `src/reader.py` to load tickets with schema validation
- Reuses `Ticket`, `Epic`, `Task`, `Subtask` models from `src/models.py`
- Reader's validator catches schema violations during load; linter focuses on cross-ticket validation
- Integrates with corruption state module via `mark_corrupt(report)` or `mark_clean()`

### Auto-Fix Capability

Future enhancement: Auto-fix using relationship sync functions from `src/relationship_sync.py`. Current approach: detect issues (linter), then repair (sync tools). Two-phase design prevents automatic corruption propagation.

## Input Validation and Security

Bees implements defense-in-depth input validation to prevent path traversal attacks and malicious file operations. This section covers the security validation architecture added in task features.bees-y9a.

### Design Decision: Validate at Entry Point

**Rationale**: Input validation must occur at the earliest possible point before any filesystem operations to prevent path traversal attacks. The `write_ticket_file()` function in `src/writer.py` is the entry point for all ticket file creation operations.

**Implementation**: Validation happens before `get_ticket_path()` call, ensuring malicious ticket IDs never reach filesystem path construction logic.

**Alternative Rejected**: Validating inside `get_ticket_path()` would be too late - path construction might already have security implications. Entry point validation provides strongest security guarantee.

### Security Validation Architecture

**write_ticket_file() Entry Point** (`src/writer.py:67-102`):
```python
def write_ticket_file(ticket_id: str, ticket_type: TicketType, ...):
    # Validate ticket_id format before any filesystem operations
    if not validate_id_format(ticket_id):
        raise ValueError(f"Invalid ticket ID format: {ticket_id}")
    
    # Only after validation do we construct filesystem paths
    target_path = get_ticket_path(ticket_id, ticket_type)
    ...
```

**validate_id_format() Function** (`src/validator.py:104-124`):
- Validates ticket ID matches regex: `^([a-z_][a-z0-9_]*\.)?bees-[a-z0-9]{3}$`
- Rejects path traversal attempts: `../etc/passwd`, `../../sensitive/file`
- Rejects malformed IDs: `bees-INVALID`, `invalid-format`, empty strings
- Returns boolean: `True` for valid format, `False` for invalid

**Integration with Existing Validator Module**:
- `validate_id_format()` was already present in `src/validator.py` for schema validation
- Task features.bees-464 added import and validation call to `write_ticket_file()`
- Reuses existing ID validation logic for consistency across codebase

### Attack Surface Reduction

**Before**: `write_ticket_file()` accepted any string as `ticket_id` parameter and passed it directly to filesystem operations without validation.

**After**: All ticket IDs validated against strict format requirements before filesystem path construction.

**Prevented Attack Vectors**:
- Path traversal: `../../../etc/passwd` rejected before filesystem access
- Directory escaping: `../../sensitive/data.md` blocked by format validation
- Malformed paths: empty strings, special characters, uppercase rejected
- Cross-hive attacks: IDs without proper hive prefix format rejected

### Testing Strategy

**Unit Tests** (`tests/test_writer_factory.py:177-240`):
- `test_write_rejects_invalid_ticket_id_format` - Verifies uppercase/special char rejection
- `test_write_rejects_path_traversal_attempts` - Confirms `../` patterns blocked
- `test_write_rejects_empty_ticket_id` - Validates empty string rejection
- `test_write_accepts_valid_hive_prefixed_id` - Ensures valid IDs continue working

**Test Coverage**: 100% coverage of validation code paths including edge cases and attack vectors.

### Error Handling

**User-Facing Errors**: Invalid ticket IDs raise `ValueError` with descriptive message: `"Invalid ticket ID format: {ticket_id}"`

**Early Failure**: Validation fails immediately before any filesystem operations, preventing partial state or security vulnerabilities.

**Consistency**: Error messages match existing validator module patterns for consistent user experience.

### Performance Considerations

**Validation Cost**: Single regex match operation - negligible overhead compared to filesystem I/O.

**Caching**: No caching needed - validation is stateless and extremely fast (< 1μs per call).

**Impact**: Zero measurable performance impact on ticket creation operations.

## Index Generation Architecture

Index generation creates per-hive markdown indexes that provide isolated ticket visibility at hive roots. Implementation in `src/index_generator.py`.

### Design Rationale: Per-Hive vs Global

**Decision**: Each hive maintains its own `index.md` at hive root directory.

**Rationale**: Hives represent separate ticket collections; independent indexing avoids mixing concerns across projects. Enables per-project ticket visibility and simplifies navigation.

**Alternative Rejected**: Single global index would require filtering logic in all readers and complicate multi-project workflows.

### Implementation Flow

```
generate_index(hive_name="backend")
  ↓
scan_tickets(hive_name="backend")
  ↓
Filter tickets by hive prefix (backend.bees-*)
  ↓
format_index_markdown(tickets)
  ↓
Write to {hive_path}/index.md
```

### Core Functions

**generate_index()** (`src/index_generator.py`):
- Signature: `generate_index(status_filter, type_filter, hive_name) -> str`
- With `hive_name` provided: generates index only for specified hive, writes to `{hive_path}/index.md`
- With `hive_name` omitted: iterates all registered hives from `.bees/config.json`, generates separate index.md for each
- Returns markdown content as string
- Requires at least one configured hive

**scan_tickets()** (`src/index_generator.py`):
- Uses `list_tickets()` from `paths.py` which scans hive root directories (flat storage)
- Validates `bees_version` field presence and filters by YAML `type` field
- Excludes `/eggs` and `/evicted` subdirectories automatically
- Groups tickets by type using YAML frontmatter `type` field
- With `hive_name` parameter: only returns tickets matching hive prefix (extracts prefix from ticket ID before first dot)
- Without `hive_name`: returns all tickets from all hives

**format_index_markdown()** (`src/index_generator.py`):
- Generates markdown with hierarchical organization: Epic → Task → Subtask
- Link format: `[ticket-id: title](ticket-id.md)` - relative paths from index to ticket files
- Works with flat storage: no type subdirectories in paths
- Supports filtering by status and type

### Link Generation Strategy

**Decision**: Use relative paths `{ticket_id}.md` from index location to ticket files.

**Rationale**: Simple, works with flat storage, no redundant path information, portable across environments.

**Alternative Rejected**: Absolute paths would require hardcoded hive paths and break portability.

### Index Staleness Detection

**is_index_stale()** (`src/index_generator.py`):
- Scans hive root directory with glob pattern `*.md`
- Skips `index.md` itself when checking modification times
- Compares all ticket files against index modification time
- Returns `True` if any ticket file is newer than index

### MCP Integration

**_generate_index()** tool in `src/mcp_server.py`:
- Accepts optional `hive_name` parameter
- Passes through to `generate_index()` function
- Enables per-hive or all-hive index regeneration via MCP protocol

### Use Cases

- Regenerate index for specific hive: `generate_index(hive_name="backend")`
- Regenerate all hive indexes: `generate_index()`
- Generate filtered index: `generate_index(hive_name="backend", status="open")`

## Corruption Detection

Corruption detection identifies database integrity issues through linter validation and generates structured reports for troubleshooting and recovery.

### Error Categories

**Critical Errors** (mark database as corrupt):
- Malformed ticket IDs not matching `{hive}.bees-[a-z0-9]{3}` pattern
- Duplicate ticket IDs across system
- Bidirectional relationship inconsistencies (parent/children, dependencies)
- Circular dependencies in blocking relationships or hierarchical structure
- Invalid cross-hive dependencies violating configuration rules

**Warnings** (non-critical):
- Missing optional fields
- Style guideline violations
- Deprecated field usage

### Corruption Report Structure

Reports persist to `.bees/corruption_report.json` with structured error information:
- Ticket ID and error type for each validation failure
- Error message and severity level
- Summary statistics (error counts by type and severity)
- Timestamp of validation run

### Detection Flow

```
Linter.run()
  ↓
Validate all tickets
  ↓
Generate LinterReport
  ↓
Check is_corrupt()
  ↓
mark_corrupt(report) OR mark_clean()
  ↓
Persist to .bees/corruption_report.json
```

### Auto-Fix vs Manual Intervention

**Auto-fixable Issues**:
- Future capability using relationship sync functions
- Bidirectional relationship repairs
- ID normalization where safe

**Requires Manual Intervention**:
- Circular dependency resolution (requires understanding intended structure)
- Duplicate ID conflicts (requires choosing which ticket to preserve)
- Cross-hive dependency violations (requires architectural decisions)

### Database Integrity Guarantees

**MCP Server Validation**:
- MCP server checks corruption state on startup
- Refuses to start if database has critical errors
- Prevents propagating corrupt data through API operations
- Forces manual fix before allowing ticket operations

**sanitize_hive Tool** (`src/mcp_server.py`):
- Runs linter on specified hive with hive-aware validations
- Validates ticket IDs match hive prefix format
- Validates cross-hive dependencies respect configuration
- Attempts automatic fixes where possible
- Returns structured report with fixes applied and remaining errors

### Integration with Corruption State

**Corruption State Module** (`src/corruption_state.py`):
- `mark_corrupt(report)` persists LinterReport to `.bees/corruption_report.json`
- `mark_clean()` removes corruption report file
- `is_corrupt()` checks for existence of corruption report
- Provides persistent record of last validation state

### Error Reporting Formats

**JSON Format**: Machine-readable for tooling integration, includes full error details and summary statistics.

**Markdown Format**: Human-readable for CLI display, formatted for terminal output with section headers.

**Dict Format**: Internal representation for programmatic access within Python codebase.

## References

- Linter implementation: `src/linter.py`, `src/linter_report.py`
- Index generator: `src/index_generator.py`
- Corruption state: `src/corruption_state.py`
- ID utilities: `src/id_utils.py`
- Reader module: `src/reader.py`, `src/parser.py`, `src/validator.py`
- Writer module: `src/writer.py`, `src/ticket_factory.py`
- Relationship sync: `src/relationship_sync.py`
- MCP server tools: `src/mcp_server.py`
