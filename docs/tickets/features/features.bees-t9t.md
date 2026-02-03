---
id: features.bees-t9t
type: task
title: Extract relationship synchronization to mcp_relationships.py
description: 'Context: Bidirectional relationship sync (parent/child, dependencies)
  is a complex subsystem with 9 helper functions. This logic should be isolated in
  its own module.


  What Needs to Change:

  - Create new file src/mcp_relationships.py

  - Move `_update_bidirectional_relationships()` function (lines 689-816)

  - Move all 8 helper functions: `_remove_child_from_parent()`, `_add_child_to_parent()`,
  `_remove_parent_from_child()`, `_set_parent_on_child()`, `_remove_from_down_dependencies()`,
  `_add_to_down_dependencies()`, `_remove_from_up_dependencies()`, `_add_to_up_dependencies()`

  - Import reader/writer utilities from existing modules

  - Update imports in src/mcp_server.py


  Why: Relationship sync is a discrete subsystem that''s easier to understand and
  maintain when isolated. It''s used by ticket update/delete operations.


  Files: src/mcp_relationships.py (new), src/mcp_server.py


  Success Criteria:

  - src/mcp_relationships.py exists with all 9 functions

  - Bidirectional sync still works for parent/child relationships

  - Bidirectional sync still works for dependencies

  - All existing relationship tests pass

  - Module is ~400-500 lines


  Epic: features.bees-d6o'
up_dependencies:
- features.bees-pt9
- features.bees-alr
- features.bees-wvm
down_dependencies:
- features.bees-jzd
- features.bees-4u5
parent: features.bees-d6o
children:
- features.bees-9ss
- features.bees-oe3
- features.bees-s35
- features.bees-8mt
- features.bees-fcs
- features.bees-a90
created_at: '2026-02-03T17:01:55.537206'
updated_at: '2026-02-03T17:03:27.594189'
priority: 0
status: open
bees_version: '1.1'
---

Context: Bidirectional relationship sync (parent/child, dependencies) is a complex subsystem with 9 helper functions. This logic should be isolated in its own module.

What Needs to Change:
- Create new file src/mcp_relationships.py
- Move `_update_bidirectional_relationships()` function (lines 689-816)
- Move all 8 helper functions: `_remove_child_from_parent()`, `_add_child_to_parent()`, `_remove_parent_from_child()`, `_set_parent_on_child()`, `_remove_from_down_dependencies()`, `_add_to_down_dependencies()`, `_remove_from_up_dependencies()`, `_add_to_up_dependencies()`
- Import reader/writer utilities from existing modules
- Update imports in src/mcp_server.py

Why: Relationship sync is a discrete subsystem that's easier to understand and maintain when isolated. It's used by ticket update/delete operations.

Files: src/mcp_relationships.py (new), src/mcp_server.py

Success Criteria:
- src/mcp_relationships.py exists with all 9 functions
- Bidirectional sync still works for parent/child relationships
- Bidirectional sync still works for dependencies
- All existing relationship tests pass
- Module is ~400-500 lines

Epic: features.bees-d6o
