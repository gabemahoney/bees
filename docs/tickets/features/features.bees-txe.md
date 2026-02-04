---
id: features.bees-txe
type: task
title: Extract query operations to mcp_query_ops.py
description: 'Context: Query operations (add named query, execute named/freeform queries)
  are a distinct subsystem for the query engine.


  What Needs to Change:

  - Create new file src/mcp_query_ops.py

  - Move `_add_named_query()` function (lines 1760-1816)

  - Move `_execute_query()` function (lines 1818-1902)

  - Move `_execute_freeform_query()` function (lines 1904-1999)

  - Import query_storage and pipeline evaluator

  - Import mcp_repo_utils for repo root detection

  - Update imports in src/mcp_server.py


  Why: Query operations are a cohesive subsystem for the query engine and should be
  isolated.


  Files: src/mcp_query_ops.py (new), src/mcp_server.py


  Success Criteria:

  - src/mcp_query_ops.py exists with all 3 functions

  - Named query registration works

  - Query execution with hive filtering works

  - Freeform queries work

  - All existing query tests pass

  - Module is ~300-400 lines


  Epic: features.bees-d6o'
up_dependencies:
- features.bees-pt9
- features.bees-alr
down_dependencies:
- features.bees-4u5
parent: features.bees-d6o
children:
- features.bees-af3
- features.bees-7gj
- features.bees-f0o
- features.bees-izl
- features.bees-wiq
- features.bees-uxv
created_at: '2026-02-03T17:02:08.200431'
updated_at: '2026-02-03T17:03:40.742757'
priority: 0
status: closed
bees_version: '1.1'
---

Context: Query operations (add named query, execute named/freeform queries) are a distinct subsystem for the query engine.

What Needs to Change:
- Create new file src/mcp_query_ops.py
- Move `_add_named_query()` function (lines 1760-1816)
- Move `_execute_query()` function (lines 1818-1902)
- Move `_execute_freeform_query()` function (lines 1904-1999)
- Import query_storage and pipeline evaluator
- Import mcp_repo_utils for repo root detection
- Update imports in src/mcp_server.py

Why: Query operations are a cohesive subsystem for the query engine and should be isolated.

Files: src/mcp_query_ops.py (new), src/mcp_server.py

Success Criteria:
- src/mcp_query_ops.py exists with all 3 functions
- Named query registration works
- Query execution with hive filtering works
- Freeform queries work
- All existing query tests pass
- Module is ~300-400 lines

Epic: features.bees-d6o
