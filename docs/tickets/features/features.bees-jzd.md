---
id: features.bees-jzd
type: task
title: Extract ticket CRUD operations to mcp_ticket_ops.py
description: 'Context: The four main ticket operations (create, update, delete, show)
  are the largest operations in mcp_server.py. They need their own module.


  What Needs to Change:

  - Create new file src/mcp_ticket_ops.py

  - Move `_create_ticket()` function (lines 1087-1396)

  - Move `_update_ticket()` function (lines 1398-1637)

  - Move `_delete_ticket()` function (lines 1639-1758)

  - Move `_show_ticket()` function (lines 2001-2117)

  - Import mcp_relationships for bidirectional sync

  - Import mcp_repo_utils for repo root detection

  - Import mcp_id_utils for ticket ID parsing

  - Update imports in src/mcp_server.py


  Why: These are the core operations of the ticket system and form a cohesive module.
  They depend on utilities and relationship sync.


  Files: src/mcp_ticket_ops.py (new), src/mcp_server.py


  Success Criteria:

  - src/mcp_ticket_ops.py exists with all 4 functions

  - Create/update/delete/show all work correctly

  - All validation logic preserved

  - All existing ticket operation tests pass

  - Module is ~700-800 lines


  Epic: features.bees-d6o'
up_dependencies:
- features.bees-pt9
- features.bees-alr
- features.bees-wvm
- features.bees-t9t
down_dependencies:
- features.bees-4u5
parent: features.bees-d6o
children:
- features.bees-zd2
- features.bees-2g6
- features.bees-txf
- features.bees-ay0
- features.bees-h51
- features.bees-7lh
- features.bees-odv
- features.bees-cfz
- features.bees-x0t
- features.bees-elq
created_at: '2026-02-03T17:01:59.766998'
updated_at: '2026-02-03T17:03:50.524945'
priority: 0
status: completed
bees_version: '1.1'
---

Context: The four main ticket operations (create, update, delete, show) are the largest operations in mcp_server.py. They need their own module.

What Needs to Change:
- Create new file src/mcp_ticket_ops.py
- Move `_create_ticket()` function (lines 1087-1396)
- Move `_update_ticket()` function (lines 1398-1637)
- Move `_delete_ticket()` function (lines 1639-1758)
- Move `_show_ticket()` function (lines 2001-2117)
- Import mcp_relationships for bidirectional sync
- Import mcp_repo_utils for repo root detection
- Import mcp_id_utils for ticket ID parsing
- Update imports in src/mcp_server.py

Why: These are the core operations of the ticket system and form a cohesive module. They depend on utilities and relationship sync.

Files: src/mcp_ticket_ops.py (new), src/mcp_server.py

Success Criteria:
- src/mcp_ticket_ops.py exists with all 4 functions
- Create/update/delete/show all work correctly
- All validation logic preserved
- All existing ticket operation tests pass
- Module is ~700-800 lines

Epic: features.bees-d6o
