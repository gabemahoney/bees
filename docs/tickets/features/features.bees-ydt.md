---
id: features.bees-ydt
type: subtask
title: Verify mcp_server.py is reduced to ~300-500 lines
description: 'Context: The goal of this refactoring is to shrink mcp_server.py from
  3,222 lines to ~300-500 lines.


  What to Do:

  - Count lines in src/mcp_server.py

  - Verify it''s between 300-500 lines

  - If over 500 lines, identify what can be further extracted

  - Verify all @mcp.tool() registrations are present

  - Verify no orphaned code remains

  - Verify no duplicate function implementations (one in module, one in mcp_server.py)


  Files: src/mcp_server.py


  Acceptance: File is 300-500 lines and contains only server setup, lifecycle, and
  tool registration wrappers.'
parent: features.bees-4u5
status: completed
created_at: '2026-02-03T17:03:25.604215'
updated_at: '2026-02-03T17:03:25.604219'
bees_version: '1.1'
---

Context: The goal of this refactoring is to shrink mcp_server.py from 3,222 lines to ~300-500 lines.

What to Do:
- Count lines in src/mcp_server.py
- Verify it's between 300-500 lines
- If over 500 lines, identify what can be further extracted
- Verify all @mcp.tool() registrations are present
- Verify no orphaned code remains
- Verify no duplicate function implementations (one in module, one in mcp_server.py)

Files: src/mcp_server.py

Acceptance: File is 300-500 lines and contains only server setup, lifecycle, and tool registration wrappers.
