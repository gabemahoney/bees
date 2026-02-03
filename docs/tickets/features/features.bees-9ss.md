---
id: features.bees-9ss
type: subtask
title: Create src/mcp_relationships.py with relationship sync functions
description: "Context: Extract the 9 relationship synchronization functions from src/mcp_server.py\
  \ into a dedicated module for better organization and maintainability.\n\nWhat to\
  \ Create:\n- Create new file src/mcp_relationships.py\n- Move `_update_bidirectional_relationships()`\
  \ function (lines 689-816 from mcp_server.py)\n- Move all 8 helper functions:\n\
  \  - `_remove_child_from_parent()`\n  - `_add_child_to_parent()`\n  - `_remove_parent_from_child()`\n\
  \  - `_set_parent_on_child()`\n  - `_remove_from_down_dependencies()`\n  - `_add_to_down_dependencies()`\n\
  \  - `_remove_from_up_dependencies()`\n  - `_add_to_up_dependencies()`\n- Import\
  \ necessary utilities (reader/writer functions) from existing modules\n- Add module\
  \ docstring explaining the purpose\n\nFiles: src/mcp_relationships.py (new)\n\n\
  Acceptance Criteria:\n- src/mcp_relationships.py exists with all 9 functions\n-\
  \ All functions retain their original logic\n- Proper imports added for dependencies\n\
  - Module is approximately 400-500 lines"
down_dependencies:
- features.bees-s35
- features.bees-8mt
- features.bees-fcs
parent: features.bees-t9t
created_at: '2026-02-03T17:03:02.898705'
updated_at: '2026-02-03T17:03:22.810779'
status: open
bees_version: '1.1'
---

Context: Extract the 9 relationship synchronization functions from src/mcp_server.py into a dedicated module for better organization and maintainability.

What to Create:
- Create new file src/mcp_relationships.py
- Move `_update_bidirectional_relationships()` function (lines 689-816 from mcp_server.py)
- Move all 8 helper functions:
  - `_remove_child_from_parent()`
  - `_add_child_to_parent()`
  - `_remove_parent_from_child()`
  - `_set_parent_on_child()`
  - `_remove_from_down_dependencies()`
  - `_add_to_down_dependencies()`
  - `_remove_from_up_dependencies()`
  - `_add_to_up_dependencies()`
- Import necessary utilities (reader/writer functions) from existing modules
- Add module docstring explaining the purpose

Files: src/mcp_relationships.py (new)

Acceptance Criteria:
- src/mcp_relationships.py exists with all 9 functions
- All functions retain their original logic
- Proper imports added for dependencies
- Module is approximately 400-500 lines
