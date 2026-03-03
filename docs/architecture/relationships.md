# Relationship Synchronization Architecture

## Overview

The relationship synchronization module (`src/mcp_relationships.py`) maintains bidirectional consistency for all ticket relationships. All create/update/delete operations use this module to ensure atomicity and data integrity.

**Core Principle**: When a relationship is created or modified, both sides must be updated. For example:
- Adding ticket B as child of A updates both A's `children` array and B's `parent` field
- Adding B as dependent on A updates both A's `down_dependencies` and B's `up_dependencies`

This bidirectional sync prevents inconsistencies and ensures graph traversal works correctly in both directions.

## Parent/Child Relationships

### Valid Hierarchies

The system enforces strict parent/child rules based on ticket tier:

- **Bee (t0) ↔ t1**: Bees can have t1 children
- **t1 ↔ t2**: t1 tickets can have t2 children
- **t2 ↔ t3**: t2 tickets can have t3 children (if configured)
- Hierarchy follows configured `child_tiers` in `~/.bees/config.json`

Type validation uses `infer_ticket_type_from_id()` for lightweight checks without full ticket parsing.

### Immutable Parent Relationships

Parent/child relationships are **immutable after ticket creation**:

- Parent is set at ticket creation time via `create_ticket`
- Children are managed only through `create_ticket` and `delete_ticket` operations
- `update_ticket` rejects any attempts to modify `parent` or `children` fields
- To change parent relationships, delete and recreate the ticket

**Child Tier Constraint**: All child tiers defined in `~/.bees/config.json` under `child_tiers` (e.g., t1, t2, t3...) require a parent at creation time. The parent field cannot be null for these tiers.

### Bidirectional Sync

Parent/child relationships are synchronized bidirectionally at creation:

1. **Setting Parent at Creation**: Specifying `parent` in `create_ticket` automatically adds the new ticket to parent's `children` array
2. **Adding Child at Creation**: Creating a child ticket with a parent automatically sets the child's `parent` field

The bidirectional sync ensures both sides of the relationship are always consistent.

### Delete Cascade (Two-Phase Bottom-Up Algorithm)

Deleting a ticket cascades to its entire child subtree using a two-phase approach:

**Phase 1 — Collection**: Traverses the filesystem using `os.scandir` to discover child ticket directories without parsing YAML. Builds an ordered list of ticket IDs (leaves first, root last). The root ticket's existence is validated before traversal begins; if it does not exist, the operation raises `ValueError` and nothing is deleted.

**Phase 2 — Deletion**: Iterates the collected list bottom-up, removing each ticket's directory with `shutil.rmtree`. A safety guard prevents accidental deletion of the hive root directory.

**Parent cleanup**: When a child ticket is deleted, the parent's `children` array is automatically updated to remove the deleted ticket's ID.

**What delete does NOT modify by default**: Other relationship fields (`up_dependencies`, `down_dependencies`) in surviving tickets are not modified. Dangling dependency references are detected by the linter during validation.

**Optional dependency cleanup**: When the global config key `delete_with_dependencies` is set to `true` in `~/.bees/config.json`, a pre-deletion cleanup phase runs before any directory is removed. This phase iterates every ticket in the subtree being deleted and removes its ID from all external tickets' `up_dependencies` and `down_dependencies` arrays. The two-phase directory deletion then proceeds as normal. This setting is global-only and cannot be passed as a parameter to `delete_ticket`.

## Dependency Relationships

### Up and Down Dependencies

Dependencies represent blocking relationships between tickets of the **same type**:

- **up_dependencies**: Tickets this one depends on (blockers)
- **down_dependencies**: Tickets depending on this one (blocked items)
- **Same-type only**: Bees→Bees, t1→t1, t2→t2, etc.

**Validation**: The linter enforces same-type dependency restriction during validation. See [validation.md](../architecture/validation.md) for details on dependency field validators including `cross_type_dependency` error.

### Bidirectional Sync

When dependencies change:

1. **Adding Dependency**: Setting `A.up_dependencies = [B]` automatically adds A to `B.down_dependencies`
2. **Removing Dependency**: Removing B from `A.up_dependencies` removes A from `B.down_dependencies`
3. **Inverse Operation**: Adding A to `B.down_dependencies` automatically adds B to `A.up_dependencies`

### Circular Dependency Prevention

The system validates against dependency cycles using DFS traversal:

- Direct cycles: A depends on B, B depends on A
- Transitive cycles: A→B→C→A
- Validation runs before committing any dependency changes

### Delete and Dependency References

When a ticket is deleted, its dependency arrays are removed with the ticket. By default, surviving tickets that referenced the deleted ticket in their `up_dependencies` or `down_dependencies` are **not** modified — dangling dependency references are detected by the linter during validation.

To remove the deleted subtree from external tickets' dependency arrays before deletion, set `delete_with_dependencies: true` in the global config (`~/.bees/config.json`). This triggers a pre-deletion cleanup phase that removes the subtree's ticket IDs from all external tickets' `up_dependencies` and `down_dependencies` fields before any directory is removed. Alternatively, dangling references left after deletion can be automatically cleaned up by running `sanitize-hive` with `auto_fix_dangling_refs: true` in global config.

## Core Functions

The `mcp_relationships.py` module contains 9 functions for relationship synchronization:

### Main Entry Point

- `_update_bidirectional_relationships()`: Main function that syncs all relationships (parent/child, dependencies) for a ticket

### Helper Functions

**Parent/Child Operations:**
- `_add_child_to_parent()`: Adds child to parent's children array with bidirectional sync
- `_remove_child_from_parent()`: Removes child from parent's children array with bidirectional sync
- `_set_parent_on_child()`: Sets parent field on child ticket with bidirectional sync
- `_remove_parent_from_child()`: Removes parent field from child ticket (not allowed for child tiers based on config)
- `_requires_parent()`: Helper function to determine if a ticket type requires a parent based on `child_tiers` config

**Dependency Operations:**
- `_add_to_down_dependencies()`: Adds ticket to blocking ticket's down_dependencies array
- `_remove_from_down_dependencies()`: Removes ticket from blocking ticket's down_dependencies array
- `_add_to_up_dependencies()`: Adds ticket to blocked ticket's up_dependencies array
- `_remove_from_up_dependencies()`: Removes ticket from blocked ticket's up_dependencies array

All operations are **idempotent** - calling multiple times has same effect as calling once.

## Integration Points

### MCP Tools

All MCP tools use relationship sync:

- **create_ticket**: Establishes parent/child and dependencies for new tickets
- **update_ticket**: Modifies dependency relationships with bidirectional sync (rejects parent/children changes)
- **delete_ticket**: Accepts one or more ticket IDs (`ticket_ids: str | list[str]`). For each ticket ID, cascades deletion to its entire child subtree using the two-phase bottom-up algorithm; automatically removes the deleted ticket from its parent's `children` array. Set `delete_with_dependencies: true` in global config to also remove each deleted subtree from external tickets' dependency arrays before deletion.

### Module Dependencies

Relationship sync integrates with:

- `src/paths.py`: Uses `infer_ticket_type_from_id()` for type checking
- `src/reader.py`: Uses `read_ticket()` for ticket parsing
- `src/writer.py`: Uses `write_ticket_file()` for atomic writes with file locking

## Module Architecture

The relationship synchronization logic was extracted from `src/mcp_server.py` into a dedicated module `src/mcp_relationships.py` for better code organization and maintainability.

**Design Rationale:**
- Relationship sync is a complex subsystem (~400-500 lines) with 9 functions
- Isolating it improves code clarity and makes the logic easier to understand and test
- The module is a discrete unit with clear boundaries and responsibilities
- Used by ticket create, update, and delete operations in mcp_server.py

**Integration:**
The module is imported by mcp_server.py and called during ticket operations to maintain bidirectional consistency. It relies on core utilities from reader.py, writer.py, and paths.py modules.

Full implementation: `src/mcp_relationships.py`

Key design principles:
- Bidirectional consistency enforced at all times
- Atomic operations (all succeed or all fail)
- Idempotent operations (safe to retry)
- Type hierarchy validation
- Circular dependency prevention
- Two-phase bottom-up delete cascade for hierarchical relationships
