---
id: features.bees-pt9
type: task
title: Extract ID parsing utilities to mcp_id_utils.py
description: 'Context: mcp_server.py contains two ticket ID parsing functions that
  are used throughout the codebase. These are small, focused utilities that should
  be extracted first as they have no dependencies.


  What Needs to Change:

  - Create new file src/mcp_id_utils.py

  - Move `parse_ticket_id()` function (lines 52-91) with full docstrings and type
  hints

  - Move `parse_hive_from_ticket_id()` function (lines 93-122) with full docstrings

  - Update imports in src/mcp_server.py to import from mcp_id_utils

  - Update any test files that directly import these functions


  Why: These utilities are foundational and used by multiple other modules. Extracting
  them first prevents circular dependencies.


  Files: src/mcp_id_utils.py (new), src/mcp_server.py


  Success Criteria:

  - src/mcp_id_utils.py exists and contains both functions

  - All imports in mcp_server.py updated

  - All existing tests pass

  - Module is ~50-100 lines


  Epic: features.bees-d6o'
down_dependencies:
- features.bees-t9t
- features.bees-jzd
- features.bees-2hp
- features.bees-txe
- features.bees-4u5
- features.bees-tho
- features.bees-w4v
- features.bees-yss
parent: features.bees-d6o
children:
- features.bees-jc5
- features.bees-60z
- features.bees-57n
- features.bees-l2e
- features.bees-z9t
- features.bees-uey
- features.bees-0k5
created_at: '2026-02-03T17:00:56.124363'
updated_at: '2026-02-03T19:07:13.564523'
priority: 0
status: completed
bees_version: '1.1'
---

Context: mcp_server.py contains two ticket ID parsing functions that are used throughout the codebase. These are small, focused utilities that should be extracted first as they have no dependencies.

What Needs to Change:
- Create new file src/mcp_id_utils.py
- Move `parse_ticket_id()` function (lines 52-91) with full docstrings and type hints
- Move `parse_hive_from_ticket_id()` function (lines 93-122) with full docstrings
- Update imports in src/mcp_server.py to import from mcp_id_utils
- Update any test files that directly import these functions

Why: These utilities are foundational and used by multiple other modules. Extracting them first prevents circular dependencies.

Files: src/mcp_id_utils.py (new), src/mcp_server.py

Success Criteria:
- src/mcp_id_utils.py exists and contains both functions
- All imports in mcp_server.py updated
- All existing tests pass
- Module is ~50-100 lines

Epic: features.bees-d6o
