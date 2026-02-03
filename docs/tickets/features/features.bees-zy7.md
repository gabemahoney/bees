---
id: features.bees-zy7
type: task
title: Extract index generation to mcp_index_ops.py
description: 'Context: Index generation is a single focused operation that should
  have its own small module.


  What Needs to Change:

  - Create new file src/mcp_index_ops.py

  - Move `_generate_index()` function (lines 2119-2173)

  - Import index_generator module

  - Import mcp_repo_utils for repo root detection

  - Update imports in src/mcp_server.py


  Why: Index generation is a discrete operation that''s easier to find and maintain
  in its own module.


  Files: src/mcp_index_ops.py (new), src/mcp_server.py


  Success Criteria:

  - src/mcp_index_ops.py exists with _generate_index function

  - Index generation with filtering works

  - Per-hive and all-hive index generation works

  - All existing index tests pass

  - Module is ~100-150 lines


  Epic: features.bees-d6o'
up_dependencies:
- features.bees-alr
down_dependencies:
- features.bees-4u5
parent: features.bees-d6o
children:
- features.bees-mhy
- features.bees-wo5
- features.bees-wqo
- features.bees-84q
- features.bees-fe7
- features.bees-4ib
created_at: '2026-02-03T17:02:11.672904'
updated_at: '2026-02-03T17:03:45.446355'
priority: 0
status: open
bees_version: '1.1'
---

Context: Index generation is a single focused operation that should have its own small module.

What Needs to Change:
- Create new file src/mcp_index_ops.py
- Move `_generate_index()` function (lines 2119-2173)
- Import index_generator module
- Import mcp_repo_utils for repo root detection
- Update imports in src/mcp_server.py

Why: Index generation is a discrete operation that's easier to find and maintain in its own module.

Files: src/mcp_index_ops.py (new), src/mcp_server.py

Success Criteria:
- src/mcp_index_ops.py exists with _generate_index function
- Index generation with filtering works
- Per-hive and all-hive index generation works
- All existing index tests pass
- Module is ~100-150 lines

Epic: features.bees-d6o
