# Design Principles

This document explains the core architectural constraints, principles, and error handling philosophy that guide Bees development.

## Design Constraints

Bees operates under strict constraints to maintain simplicity and reliability:

- **No database**: All data stored as markdown files with YAML frontmatter. This ensures human readability, easy version control, and simple backup/restore without database administration overhead.

- **No daemons**: All operations are synchronous and complete within the execution context. No background processes means no daemon management, no process monitoring, and no state synchronization issues.

- **Limited caching**: An mtime-based in-memory cache accelerates `read_ticket()` results while remaining consistent — cache entries are invalidated when the file's modification time changes. No persistent or distributed caching.

- **Scale limit**: Designed for tens of directories (hives) and thousands of tickets. This constraint enables the no-database and no-cache architecture while meeting the needs of small-to-medium development teams.

### Rationale

These constraints trade performance for simplicity and reliability. By eliminating databases, daemons, and complex caching, we avoid entire classes of bugs (cache invalidation, daemon crashes, database corruption, connection pooling) while maintaining a system that's easy to understand, debug, and deploy.

## Design Principles

1. **Markdown-First**: Tickets are human-readable markdown files that can be viewed, edited, and versioned using standard text tools. No proprietary formats or database schemas.

2. **Type Safety**: Dataclasses and validation ensure schema compliance at runtime. Typed ticket objects prevent malformed data from propagating through the system.

3. **Atomicity**: File operations use atomic write patterns (temp file + rename) to prevent corruption if processes crash during writes. Either the old file remains intact or the new file is complete—no partial states.

4. **Simplicity**: Simple factory functions over complex frameworks. Clear function boundaries and minimal abstraction make the codebase easy to understand and modify.

5. **Extensibility**: Clean module boundaries support future features without major refactoring. Reader, Writer, Path Management, Query System, and Configuration modules have well-defined responsibilities.

6. **Explicit Write Operations**: Write operations (create/update/delete) fail fast without recovery attempts. This prevents unintended data mutations and provides clear error messages.

### Trade-offs

These principles prioritize correctness and maintainability over performance. Atomicity adds overhead (temp files), type safety adds validation cost, and fail-fast behavior sacrifices convenience for safety. These trade-offs are acceptable given the scale constraints.

## Error Handling Architecture

### Write vs Read Philosophy

Bees distinguishes between write and read operations with different error handling strategies:

**Write Operations** (`create_ticket`, `update_ticket`, `delete_ticket`):
- Strict validation with fail-fast behavior
- No automatic recovery attempts
- Explicit errors guide users to fix configuration issues
- Prevents unintended data mutations from masked errors

**Read Operations** (queries, path resolution):
- More forgiving with optional recovery mechanisms
- `scan_for_hive()` can search for relocated hives using `.hive` markers
- Graceful degradation when possible

### Rationale for Strict Write Operations

1. **Safety**: Creating tickets in the wrong location due to auto-recovery could cause data integrity issues. Better to fail explicitly than write to an unexpected location.

2. **Consistency**: All write operations (`create_ticket`, `update_ticket`, `delete_ticket`) follow the same pattern—they fail fast when the hive isn't registered in config. Uniform behavior reduces surprises.

3. **Recovery Scope**: The `scan_for_hive()` recovery mechanism is designed for exceptional scenarios (hive relocation during migration). Normal operations should use registered hives from `~/.bees/config.json`.

4. **Error Clarity**: Explicit errors distinguish "hive not registered" from "hive not found anywhere" and provide actionable guidance (e.g., "run colonize_hive to register").

### Implementation Pattern

Write operations validate hive registration before proceeding:

```python
# Example from _create_ticket()
normalized_hive = normalize_hive_name(hive_name)
config = load_bees_config()
if not config or normalized_hive not in config.hives:
    raise ValueError(f"Hive '{hive_name}' not registered. Run colonize_hive first.")
```

Path resolution functions similarly fail fast without recovery attempts (see `get_ticket_path()` in `src/paths.py`).

### Future Considerations

If scan_for_hive recovery is needed for write operations, it should be:
- Opt-in via explicit parameter (e.g., `allow_recovery=True`)
- Logged prominently when recovery is attempted
- Limited to specific use cases (migration tools, recovery commands)

---

**Related Documentation**:
- Configuration system details: `src/config.py` docstrings
- Hive management: `src/hive_utils.py` docstrings
