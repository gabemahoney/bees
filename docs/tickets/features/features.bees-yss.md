---
id: features.bees-yss
type: task
title: Update test imports for clarity
description: '**Context**: test_mcp_server.py:22-23 imports parse functions through
  mcp_server, but these functions now live in mcp_id_utils. Direct imports improve
  clarity.


  **What to do**:

  - Update tests/test_mcp_server.py imports on lines 22-23

  - Import parse_ticket_id and parse_hive_from_ticket_id directly from mcp_id_utils

  - This makes it clear where the functions come from


  **Why**: Improves test code clarity and makes module dependencies explicit.


  **Files**: tests/test_mcp_server.py'
labels:
- bug
up_dependencies:
- features.bees-pt9
parent: features.bees-d6o
children:
- features.bees-c0m
- features.bees-o34
created_at: '2026-02-03T19:07:13.555463'
updated_at: '2026-02-03T19:15:19.674872'
priority: 1
status: completed
bees_version: '1.1'
---

**Context**: test_mcp_server.py:22-23 imports parse functions through mcp_server, but these functions now live in mcp_id_utils. Direct imports improve clarity.

**What to do**:
- Update tests/test_mcp_server.py imports on lines 22-23
- Import parse_ticket_id and parse_hive_from_ticket_id directly from mcp_id_utils
- This makes it clear where the functions come from

**Why**: Improves test code clarity and makes module dependencies explicit.

**Files**: tests/test_mcp_server.py
