---
id: features.bees-hnv
type: subtask
title: Create src/mcp_hive_utils.py with extracted functions
description: 'Context: Extract hive utilities from mcp_server.py to deduplicate code
  and organize hive-related logic.


  What to Do:

  1. Create new file src/mcp_hive_utils.py

  2. Extract validate_hive_path() function from src/mcp_server.py (lines 255-316)

  3. Extract scan_for_hive() function from src/mcp_server.py (lines 318-427)

  4. Add all necessary imports (pathlib.Path, json, logging, config utilities, id_utils
  if needed)

  5. Ensure both functions retain all validation logic and error handling


  Files: src/mcp_hive_utils.py (new)


  Acceptance Criteria:

  - File exists with both validate_hive_path() and scan_for_hive()

  - All validation and scanning logic preserved

  - Module is ~200-250 lines

  - No syntax errors'
down_dependencies:
- features.bees-b2i
- features.bees-4qm
- features.bees-2uq
- features.bees-98n
parent: features.bees-wvm
created_at: '2026-02-03T17:03:01.207260'
updated_at: '2026-02-03T17:03:37.925727'
status: open
bees_version: '1.1'
---

Context: Extract hive utilities from mcp_server.py to deduplicate code and organize hive-related logic.

What to Do:
1. Create new file src/mcp_hive_utils.py
2. Extract validate_hive_path() function from src/mcp_server.py (lines 255-316)
3. Extract scan_for_hive() function from src/mcp_server.py (lines 318-427)
4. Add all necessary imports (pathlib.Path, json, logging, config utilities, id_utils if needed)
5. Ensure both functions retain all validation logic and error handling

Files: src/mcp_hive_utils.py (new)

Acceptance Criteria:
- File exists with both validate_hive_path() and scan_for_hive()
- All validation and scanning logic preserved
- Module is ~200-250 lines
- No syntax errors
