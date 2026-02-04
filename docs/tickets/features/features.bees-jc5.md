---
id: features.bees-jc5
type: subtask
title: Create src/mcp_id_utils.py with parse_ticket_id() and parse_hive_from_ticket_id()
description: 'Context: Extract ID parsing utilities from mcp_server.py to a dedicated
  module to prevent circular dependencies and improve modularity.


  Requirements:

  - Create new file src/mcp_id_utils.py

  - Copy parse_ticket_id() function (lines 52-91 from mcp_server.py) with full docstrings
  and type hints

  - Copy parse_hive_from_ticket_id() function (lines 93-122 from mcp_server.py) with
  full docstrings and type hints

  - Preserve all existing functionality, error handling, and return types

  - Add module-level docstring explaining purpose


  Files: src/mcp_id_utils.py (new)


  Acceptance Criteria:

  - src/mcp_id_utils.py exists and is ~50-100 lines

  - Both functions present with complete docstrings and type hints

  - No modifications to function logic (pure extraction)'
down_dependencies:
- features.bees-l2e
- features.bees-z9t
- features.bees-uey
parent: features.bees-pt9
created_at: '2026-02-03T17:02:59.708687'
updated_at: '2026-02-03T18:58:00.559463'
status: completed
bees_version: '1.1'
---

Context: Extract ID parsing utilities from mcp_server.py to a dedicated module to prevent circular dependencies and improve modularity.

Requirements:
- Create new file src/mcp_id_utils.py
- Copy parse_ticket_id() function (lines 52-91 from mcp_server.py) with full docstrings and type hints
- Copy parse_hive_from_ticket_id() function (lines 93-122 from mcp_server.py) with full docstrings and type hints
- Preserve all existing functionality, error handling, and return types
- Add module-level docstring explaining purpose

Files: src/mcp_id_utils.py (new)

Acceptance Criteria:
- src/mcp_id_utils.py exists and is ~50-100 lines
- Both functions present with complete docstrings and type hints
- No modifications to function logic (pure extraction)
