---
id: features.bees-jlu
type: task
title: Extract help documentation to mcp_help.py
description: 'Context: The help system is a large documentation function that should
  be in its own module for easy maintenance.


  What Needs to Change:

  - Create new file src/mcp_help.py

  - Move `_help()` function (lines 2992-end)

  - Preserve all help documentation and formatting

  - Update imports in src/mcp_server.py


  Why: Help documentation is easier to maintain when isolated, especially as it grows
  with new features.


  Files: src/mcp_help.py (new), src/mcp_server.py


  Success Criteria:

  - src/mcp_help.py exists with _help function

  - Help command returns complete documentation

  - All tool documentation is accurate

  - Module is ~200-300 lines


  Epic: features.bees-d6o'
down_dependencies:
- features.bees-4u5
parent: features.bees-d6o
children:
- features.bees-u51
- features.bees-72w
- features.bees-ats
- features.bees-f5o
- features.bees-b77
- features.bees-mlw
created_at: '2026-02-03T17:02:15.405118'
updated_at: '2026-02-04T04:00:00.000000'
priority: 0
status: completed
bees_version: '1.1'
---

Context: The help system is a large documentation function that should be in its own module for easy maintenance.

What Needs to Change:
- Create new file src/mcp_help.py
- Move `_help()` function (lines 2992-end)
- Preserve all help documentation and formatting
- Update imports in src/mcp_server.py

Why: Help documentation is easier to maintain when isolated, especially as it grows with new features.

Files: src/mcp_help.py (new), src/mcp_server.py

Success Criteria:
- src/mcp_help.py exists with _help function
- Help command returns complete documentation
- All tool documentation is accurate
- Module is ~200-300 lines

Epic: features.bees-d6o
