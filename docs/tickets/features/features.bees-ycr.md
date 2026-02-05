---
id: features.bees-ycr
type: task
title: Force reimport of dependent modules
description: 'Context: Python caches imported modules, so mocks applied after initial
  imports may not take effect. This causes intermittent test failures depending on
  import order.


  **CANCELLED**: Task 1 (features.bees-gjg) revealed that multi-site patching is the
  correct solution, not module reloading. The conftest.py already patches get_repo_root_from_path
  at all 4 import sites (mcp_repo_utils, mcp_server, mcp_ticket_ops, mcp_query_ops),
  which solves the import timing issue. Module reload logic is unnecessary and would
  add complexity without benefit.'
down_dependencies:
- features.bees-tv7
parent: features.bees-w0c
children:
- features.bees-02n
- features.bees-wza
- features.bees-40m
- features.bees-r9t
- features.bees-47c
- features.bees-a2g
created_at: '2026-02-05T12:44:30.690635'
updated_at: '2026-02-05T15:45:42.799223'
priority: 0
status: cancelled
bees_version: '1.1'
---

Context: Python caches imported modules, so mocks applied after initial imports may not take effect. This causes intermittent test failures depending on import order.

**CANCELLED**: Task 1 (features.bees-gjg) revealed that multi-site patching is the correct solution, not module reloading. The conftest.py already patches get_repo_root_from_path at all 4 import sites (mcp_repo_utils, mcp_server, mcp_ticket_ops, mcp_query_ops), which solves the import timing issue. Module reload logic is unnecessary and would add complexity without benefit.
