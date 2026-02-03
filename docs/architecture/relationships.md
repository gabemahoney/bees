# Relationship Synchronization Architecture

## Overview

The relationship synchronization module (`src/relationship_sync.py`) maintains bidirectional consistency for all ticket relationships. All create/update/delete operations use this module to ensure atomicity and data integrity.

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

### Relationship Operations

- `add_child_to_parent()`: Adds child with bidirectional sync
- `remove_child_from_parent()`: Removes child with bidirectional sync
- `add_dependency()`: Adds dependency with bidirectional sync
- `remove_dependency()`: Removes dependency with bidirectional sync

All operations are **idempotent** - calling multiple times has same effect as calling once.

### Validation Functions

- `validate_ticket_exists()`: Ensures ticket file exists
- `validate_parent_child_relationship()`: Enforces type hierarchy rules
- `check_for_circular_dependency()`: Prevents cycles using DFS

## Batch Operations

### sync_relationships_batch()

Handles multiple relationship updates atomically using seven-phase execution:

1. **Validation**: Check all tickets exist and relationships are valid
2. **Loading**: Load all affected tickets into memory
3. **Deduplication**: Convert operations to set (prevents redundant I/O)
4. **Backup (WAL)**: Store in-memory copies before changes
5. **Update**: Apply relationship changes to in-memory tickets
6. **Write-with-rollback**: Write to disk; restore from backup if any fail
7. **Cleanup**: Clear backup data

**Atomicity Guarantee**: If any write fails, all tickets are restored from in-memory backups.

## Integration Points

### MCP Tools

All MCP tools use relationship sync:

- **create_ticket**: Establishes parent/child and dependencies for new tickets
- **update_ticket**: Modifies relationships with bidirectional sync
- **delete_ticket**: Uses `sync_relationships_batch()` for efficient cleanup in single atomic operation

### Module Dependencies

Relationship sync integrates with:

- `src/paths.py`: Uses `infer_ticket_type_from_id()` for type checking
- `src/reader.py`: Uses `read_ticket()` for ticket parsing
- `src/writer.py`: Uses `write_ticket_file()` for atomic writes with file locking

## Implementation Reference

Full implementation: `src/relationship_sync.py`

Key design principles:
- Bidirectional consistency enforced at all times
- Atomic operations (all succeed or all fail)
- Idempotent operations (safe to retry)
- Type hierarchy validation
- Circular dependency prevention
- Delete cascade for hierarchical relationships
