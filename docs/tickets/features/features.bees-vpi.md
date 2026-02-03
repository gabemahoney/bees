---
id: features.bees-vpi
type: subtask
title: Verify module line counts under 800 lines
description: 'Context: Success criteria requires each refactored module to be < 800
  lines and mcp_server.py to be ~300-500 lines.


  What to Do:

  - Run: `wc -l src/mcp_*.py`

  - Check each module is < 800 lines

  - Verify mcp_server.py is in 300-500 line range

  - Document actual line counts


  Why: Confirms modules are LLM-friendly and fit in context windows.


  Parent Task: features.bees-dkp


  Acceptance Criteria:

  - All mcp_*.py modules are < 800 lines

  - mcp_server.py is between 300-500 lines

  - Line counts documented'
parent: features.bees-dkp
status: open
created_at: '2026-02-03T17:03:17.573059'
updated_at: '2026-02-03T17:03:17.573062'
bees_version: '1.1'
---

Context: Success criteria requires each refactored module to be < 800 lines and mcp_server.py to be ~300-500 lines.

What to Do:
- Run: `wc -l src/mcp_*.py`
- Check each module is < 800 lines
- Verify mcp_server.py is in 300-500 line range
- Document actual line counts

Why: Confirms modules are LLM-friendly and fit in context windows.

Parent Task: features.bees-dkp

Acceptance Criteria:
- All mcp_*.py modules are < 800 lines
- mcp_server.py is between 300-500 lines
- Line counts documented
