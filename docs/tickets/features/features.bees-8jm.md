---
id: features.bees-8jm
type: subtask
title: Create src/mcp_hive_ops.py with all hive lifecycle functions
description: 'Context: Need to extract hive lifecycle operations from src/mcp_server.py
  into a new dedicated module.


  What to Do:

  - Create new file src/mcp_hive_ops.py

  - Move colonize_hive_core() function (lines 429-687 from mcp_server.py)

  - Move _colonize_hive() MCP wrapper (lines 2175-2260 from mcp_server.py)

  - Move _list_hives() function (lines 2262-2349 from mcp_server.py)

  - Move _abandon_hive() function (lines 2351-2436 from mcp_server.py)

  - Move _rename_hive() function (lines 2438-2840 from mcp_server.py)

  - Move _sanitize_hive() function (lines 2842-2990 from mcp_server.py)

  - Add necessary imports (fastmcp, pathlib, typing, json, etc.)

  - Import mcp_hive_utils for path validation and scanning

  - Import mcp_repo_utils for repo root detection

  - Add module docstring explaining hive lifecycle operations


  Files: src/mcp_hive_ops.py (new), src/mcp_server.py


  Acceptance Criteria:

  - src/mcp_hive_ops.py exists with all 6 functions

  - All functions retain their original logic and signatures

  - Module is approximately 700-800 lines

  - Module has proper imports and docstring'
down_dependencies:
- features.bees-lhh
- features.bees-zxe
- features.bees-o5g
parent: features.bees-2hp
created_at: '2026-02-03T17:03:05.678707'
updated_at: '2026-02-03T17:03:30.096521'
status: completed
bees_version: '1.1'
---

Context: Need to extract hive lifecycle operations from src/mcp_server.py into a new dedicated module.

What to Do:
- Create new file src/mcp_hive_ops.py
- Move colonize_hive_core() function (lines 429-687 from mcp_server.py)
- Move _colonize_hive() MCP wrapper (lines 2175-2260 from mcp_server.py)
- Move _list_hives() function (lines 2262-2349 from mcp_server.py)
- Move _abandon_hive() function (lines 2351-2436 from mcp_server.py)
- Move _rename_hive() function (lines 2438-2840 from mcp_server.py)
- Move _sanitize_hive() function (lines 2842-2990 from mcp_server.py)
- Add necessary imports (fastmcp, pathlib, typing, json, etc.)
- Import mcp_hive_utils for path validation and scanning
- Import mcp_repo_utils for repo root detection
- Add module docstring explaining hive lifecycle operations

Files: src/mcp_hive_ops.py (new), src/mcp_server.py

Acceptance Criteria:
- src/mcp_hive_ops.py exists with all 6 functions
- All functions retain their original logic and signatures
- Module is approximately 700-800 lines
- Module has proper imports and docstring
