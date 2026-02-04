# Relationship Synchronization Architecture

## Overview

The relationship synchronization module (`src/mcp_relationships.py`) maintains bidirectional consistency for all ticket relationships. All create/update/delete operations use this module to ensure atomicity and data integrity.

**Core Principle**: When a relationship is created or modified, both sides must be updated. For example:
- Adding ticket B as child of A updates both A's `children` array and B's `parent` field
- Adding B as dependent on A updates both A's `down_dependencies` and B's `up_dependencies`

This bidirectional sync prevents inconsistencies and ensures graph traversal works correctly in both directions.

## Parent/Child Relationships

### Valid Hierarchies

The system enforces strict parent/child rules based on ticket type:

- **Epic ↔ Task**: Epics can have Tasks as children
- **Task ↔ Subtask**: Tasks can have Subtasks as children
- **No other combinations allowed**

Type validation uses `infer_ticket_type_from_id()` for lightweight checks without full ticket parsing.

### Bidirectional Sync

When parent/child relationships change:

1. **Adding Child**: Setting `A.children = [B]` automatically sets `B.parent = A`
2. **Removing Child**: Removing B from `A.children` nullifies `B.parent` (except for subtasks, which require parent)
3. **Setting Parent**: Setting `B.parent = A` automatically adds B to `A.children`
4. **Nullifying Parent**: Setting `B.parent = null` removes B from parent's children array (not allowed for subtasks)

**Subtask Constraint**: Subtasks always require a parent (Task). The parent field cannot be nullified.

### Delete Cascade

Deleting a parent ticket **cascades to all children**:

- Deleting an Epic recursively deletes all child Tasks and their Subtasks
- Deleting a Task recursively deletes all child Subtasks
- The entire subtree is deleted
- Parent is removed from all remaining children's parent field

This ensures no orphaned tickets exist in the system.

## Dependency Relationships

### Up and Down Dependencies

Dependencies represent blocking relationships between tickets of the **same type**:

- **up_dependencies**: Tickets this one depends on (blockers)
- **down_dependencies**: Tickets depending on this one (blocked items)
- **Same-type only**: Epics→Epics, Tasks→Tasks, Subtasks→Subtasks

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

### Delete Cleanup

When a ticket is deleted:

- Removed from all related tickets' `up_dependencies` arrays
- Removed from all related tickets' `down_dependencies` arrays
- No dangling references remain in the system

## Core Functions

The `mcp_relationships.py` module contains 9 functions for relationship synchronization:

### Main Entry Point

- `_update_bidirectional_relationships()`: Main function that syncs all relationships (parent/child, dependencies) for a ticket

### Helper Functions

**Parent/Child Operations:**
- `_add_child_to_parent()`: Adds child to parent's children array with bidirectional sync
- `_remove_child_from_parent()`: Removes child from parent's children array with bidirectional sync
- `_set_parent_on_child()`: Sets parent field on child ticket with bidirectional sync
- `_remove_parent_from_child()`: Removes parent field from child ticket (not allowed for subtasks)

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
- **update_ticket**: Modifies relationships with bidirectional sync
- **delete_ticket**: Cleans up relationships with cascade delete and dependency cleanup

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
- Delete cascade for hierarchical relationships
