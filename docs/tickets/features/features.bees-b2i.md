---
id: features.bees-b2i
type: subtask
title: Update src/mcp_server.py to import from mcp_hive_utils
description: 'Context: After extracting hive utilities, update mcp_server.py to use
  the new module.


  What to Do:

  1. Remove validate_hive_path() and scan_for_hive() functions from src/mcp_server.py

  2. Add import: from mcp_hive_utils import validate_hive_path, scan_for_hive

  3. Verify all existing calls to these functions still work

  4. Ensure no duplicate code remains


  Files: src/mcp_server.py


  Acceptance Criteria:

  - Functions removed from mcp_server.py

  - Import statement added

  - All references to validate_hive_path() and scan_for_hive() still work

  - No code duplication'
up_dependencies:
- features.bees-hnv
parent: features.bees-wvm
created_at: '2026-02-03T17:03:26.443645'
updated_at: '2026-02-03T19:45:42.955169'
status: completed
bees_version: '1.1'
---

Context: After extracting hive utilities, update mcp_server.py to use the new module.

What to Do:
1. Remove validate_hive_path() and scan_for_hive() functions from src/mcp_server.py
2. Add import: from mcp_hive_utils import validate_hive_path, scan_for_hive
3. Verify all existing calls to these functions still work
4. Ensure no duplicate code remains

Files: src/mcp_server.py

Acceptance Criteria:
- Functions removed from mcp_server.py
- Import statement added
- All references to validate_hive_path() and scan_for_hive() still work
- No code duplication
